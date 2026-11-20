"""FastAPI uygulamasi: arayuz dosyalari + /api uclari. Uzun isler SSE (text/event-stream) akitir."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from app import URUN_ADI, URUN_SAHIBI, URUN_SAHIBI_GITHUB, URUN_SAHIBI_X, __version__
from app.agent import akis as akis_mod
from app.agent import cli_ajan, mcp_ice, mcp_oauth
from app.agent import koordinasyon as koord
from app.agent import review as rv
from app.agent import worktree as wt
from app.agent.ajanlar import AJAN_NOTU_ARACI, AJANA_MESAJ_ARACI, AjanDeposu, KuyrukOgesi
from app.agent.akis import Akis, AkisDeposu
from app.agent.checkpoints import CheckpointDeposu
from app.agent.dosyalar import AjanDosyaAraclari, KokKapsami
from app.agent.hooks import OLAYLAR as HOOK_OLAYLARI
from app.agent.hooks import HookDeposu
from app.agent.izolasyon import adaptor_olustur
from app.agent.masaustu import Masaustu
from app.agent.mcp import McpYoneticisi
from app.agent.policy import Istek, PolitikaMotoru, YanEtki, maskele, yerel_host_mu
from app.agent.runner import BITMIS as BITMIS_RUN
from app.agent.runner import YAZAN_ARACLAR, AgentRunner, Butce, Run, RunDeposu, RunDurum, olay_akisi
from app.agent.takim import TakimPanosu
from app.agent.tarayici import Tarayici, playwright_var
from app.agent.terminal import KomutServisi
from app.agent.webhook import WebhookDeposu, WebhookHatasi, hedef_olustur
from app.agent.workspaces import Guven, Mod, WorkspaceDeposu
from app.agent.yetenek import ModelYetenegi, dogrula, uzak_yetenek, yerel_yetenek
from app.agent.zamanlayici import Tetik, Zamanlayici
from app.config import web_dizini
from app.exceptions import (
    Bulunamadi,
    GecersizEk,
    OnayGerekli,
    UygulamaHatasi,
    YerelLLMHatasi,
    YetkiYok,
)
from app.services import cc_plugin as ccp
from app.services import ekler as ekler_modulu
from app.services import masaustu_ayar as mda
from app.services import sirlar, sistem
from app.services import skiller as skl
from app.services.agecidi import AgGecidi, agecidi_uygulamasi
from app.services.arac_paketleri import AracPaketleri
from app.services.araclar import ARACLAR, ORNEK_ISTEMLER
from app.services.ayarlar import AyarDeposu
from app.services.composio import Composio
from app.services.ekler import EkDeposu
from app.services.hafiza import HafizaDeposu
from app.services.model_magaza import Indirici, Magaza, ModelKaydi, uyumluluk
from app.services.model_yonetici import LLMFabrikasi, ModelYonetici
from app.services.ollama import Ollama, ollama_baglam
from app.services.oneriler import oneriler as oneriler_hesapla
from app.services.openrouter import OpenRouterDeposu
from app.services.oturumlar import Mesaj, OturumDeposu
from app.services.pluginler import PluginDeposu
from app.services.skiller import SKILL_KAYDET_ARACI, SkillDeposu
from app.services.sohbet import VARSAYILAN_ALAN_ID, MesajIstegi, SohbetServisi, tahmini_token
from app.services.talimatlar import TalimatDeposu
from app.services.telegram import TelegramKanali
from app.services.testler import (
    ORNEK_SATIRLAR,
    AracIstegi,
    KarsilastirmaIstegi,
    OcrIstegi,
    PaketIstegi,
    TestServisi,
    ornek_belge,
)
from app.services.uyanik import Uyanik
from app.services.uzantilar import ONIZLEME_CSP, UzantiYoneticisi
from app.services.yerel_llm import DUSUNME_SECENEKLERI, MODELLER, YerelLLM

UPLOAD_PARCA_BAYT = 1024 * 1024  # upload akisinda tek seferde okunan parca
OTURUM_BASLIGI = "x-yas-oturum"  # loopback API'de oturum kimligi (A1.9)
ACIK_YOLLAR = ("/", "/web", "/docs", "/openapi.json", "/favicon.ico")


class ProjeIstegi(BaseModel):
    yol: str = Field(min_length=1, max_length=4096)
    ad: str = Field(default="", max_length=80)
    guven: Guven = Guven.sinirli


class YolIstegi(BaseModel):
    yol: str = Field(min_length=1, max_length=4096)


class ModIstegi(BaseModel):
    mod: Mod


class GuvenIstegi(BaseModel):
    guven: Guven


class ModellerIstegi(BaseModel):
    koordinator_model: str = Field(default="", max_length=200)
    uygulayici_model: str = Field(default="", max_length=200)


class OnayIstegi(BaseModel):
    onayla: bool
    kapsam: Literal["tek", "sohbet", "her_zaman"] = "tek"


class GorevIstegi(BaseModel):
    hedef: str = Field(min_length=1, max_length=8000)
    kabul: list[str] = Field(default=[], max_length=20)
    butce: Butce = Field(default_factory=Butce)
    izole: bool = False  # ayri git worktree'de calis (A8.3)
    onceki: str = Field(default="", max_length=12)  # ayni sohbetteki onceki gorev (sureklilik)
    etkilesimli: bool = False  # sohbetten: ajan soru_sor ile kullaniciya soru sorabilir


class IsEmriIstegi(BaseModel):
    gorev: str = Field(default="", max_length=8000)
    baslik: str = Field(default="", max_length=120)
    proje_kok: str = Field(default="", max_length=4096)
    kaynak: Literal["elle", "sohbet"] = "elle"


class EntegreIstegi(BaseModel):
    test_komutu: str = Field(default="", max_length=2000)


class GorevMesaji(BaseModel):
    metin: str = Field(min_length=1, max_length=4000)


OZET_TALIMATI = (
    "Asagidaki sohbeti, devam edilebilmesi icin ozetle. Su basliklari kullan: Amac, Alinan "
    "kararlar, Onemli bilgiler (dosya yolu, ad, sayi, kod parcasi gibi birebir gerekenler), Acik "
    "kalan isler. Uydurma; yalniz sohbette geceni yaz. Kisa ve maddeli yaz."
)
OZET_ONAY = "Anlaşıldı; bu özet üzerinden devam ediyorum."

HAFIZA_ARACI = {
    "type": "function",
    "function": {
        "name": "hafizaya_ekle",
        "description": "Sonraki oturumlarda isine yarayacak KALICI bir bilgiyi kaydeder. SU "
        "DURUMLARDA HEMEN CAGIR: calistir/test/derleme komutunu bulunca, bir hatanin kalici "
        "cozumunu bulunca, kullanici bir tercih/kural soyleyince ('hep sunu yap', 'bunu "
        "kullanma'), proje yapisi/onemli dosya yeri ogrenince, bir yol/arac kisitina "
        "takilip calisan yolu bulunca. Kisa, tek cumle, kendi basina anlasilir yaz. Sir, "
        "gecici durum ya da tahmin yazma.",
        "parameters": {
            "type": "object",
            "properties": {
                "metin": {"type": "string"},
                "dayanak": {
                    "type": "array", "maxItems": 4, "items": {"type": "string"},
                    "description": "Kanit: 'dosya_tam_yolu::dosyada gecen kisa metin'. Dosya "
                    "degisip metin kaybolursa not otomatik eskir.",
                },
            },
            "required": ["metin"],
        },
    },
}  # fmt: skip

# Sohbetteki PR karti: gh pr view --json alanlari ve kabul edilen adres bicimi
PR_ALANLARI = "number,title,url,state,isDraft,additions,deletions,changedFiles,author,createdAt"
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")

HAFIZA_TALIMATI = (
    "\n\n## Kalici hafiza\nOtomatik ogrenme acik. Gorev boyunca kalici ve tekrar kullanilabilir "
    "bir bilgi ogrendiginde (komut, cozum, kullanici tercihi, proje yapisi, arac kisiti) "
    "`hafizaya_ekle` ile hemen kaydet; gorevi bitirmeden once de bu gorevde ogrendigin en az "
    "bir kalici bilgi var mi diye bak. Zaten hafizada olani tekrar yazma."
)

HAFIZA_YARGI_ARACI = {
    "type": "function",
    "function": {
        "name": "hafiza_yargila",
        "description": "Sistemdeki HAFIZA notlarindan birini degerlendirir: yararli (ise yaradi), "
        "eski (artik gecerli degil), yanlis. Yanlis/eski ise dogrusunu `duzeltme` ile yaz.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "yargi": {"type": "string", "enum": ["yararli", "eski", "yanlis"]},
                "duzeltme": {"type": "string"},
            },
            "required": ["id", "yargi"],
        },
    },
}  # fmt: skip


class HafizaIstegi(BaseModel):
    metin: str = Field(min_length=1, max_length=1000)
    kapsam: str = Field(default="genel", max_length=40)
    guven: str = "orta"
    gecerlilik: str | None = None


class KararIstegi(BaseModel):
    adim: int
    karar: str


DIKTE_MAX_SN = 30  # Gemma 4 ses girisi ~30 sn
DIKTE_UZAK = (
    "Bulut dikte kapali: ses buluta gonderilmez. Ayarlar > 'Sesli dikte bulutta' acilirsa "
    "ayri dikte modeli (OpenRouter) kullanilir."
)
DIKTE_UZAK_SESSIZ = (
    "Dikte modeli sesi anlamiyor ya da listede yok; Ayarlar'da ses girisli bir dikte modeli "
    "yazin (or. google/gemini-2.5-flash)."
)
DIKTE_SESSIZ = "Secili model sesi anlamiyor; dikte icin Gemma 4 (E4B/12B) secin."
DIKTE_TALIMATI = "Bu ses kaydini oldugu gibi yaziya dok. Yalniz soylenen metni yaz."
DIKTE_MAX_BAYT = 16000 * 2 * DIKTE_MAX_SN + 4096  # 16 kHz mono 16 bit WAV


class TazeStatik(StaticFiles):
    """Basliksiz statik dosyayi tarayici tahminle onbellekler; guncellemeden sonra eski JS
    calisir. no-cache: her seferinde ETag ile dogrulanir (yerelde maliyetsiz)."""

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        r = super().file_response(*args, **kwargs)
        r.headers["Cache-Control"] = "no-cache"
        return r


class GeriAlIstegi(BaseModel):
    yollar: list[str] = []


class HunkIstegi(BaseModel):
    yol: str
    hunklar: list[int] = Field(min_length=1)


class GirdiIstegi(BaseModel):
    metin: str = Field(max_length=10000)


class AdIstegi(BaseModel):
    baslik: str


class AjanRunKaydi(BaseModel):
    run: str = Field(min_length=1, max_length=64)
    metin: str = ""


class SkillIceIstegi(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class SkillIceAdIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=64)


class SkillIceKurIstegi(BaseModel):
    adlar: list[str] = Field(min_length=1, max_length=50)
    riskli_onay: bool = False
    yeni_adlar: dict[str, str] = {}  # zaten var olan ada sahip skill farkli adla kurulur


class AltOturumIstegi(BaseModel):
    baslik: str = Field(min_length=1, max_length=200)
    kaynak: str = Field(default="", max_length=64)  # onerinin arac cagrisi id'si


class SonrakiOneriIstegi(BaseModel):
    kullanici: str = Field(default="", max_length=4000)
    asistan: str = Field(default="", max_length=6000)


class GeriSarIstegi(BaseModel):
    mesaj_id: str = Field(default="", max_length=64)
    run: str = Field(default="", max_length=64)


class OneriRedIstegi(BaseModel):
    kaynak: str = Field(min_length=1, max_length=64)
    karar: str = Field(default="reddedildi", pattern=r"^(reddedildi|is:[0-9a-f]{12})$")


class AnahtarIstegi(BaseModel):
    anahtar: str = Field(max_length=300)


class ModelIstegi(BaseModel):
    model: str | None = None


class DurdurIstegi(BaseModel):
    harici: bool = False


class OllamaIndirIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=200)


class IndirIstegi(BaseModel):
    repo: str = Field(pattern=r"^[\w.-]+/[\w.-]+$", max_length=200)


class TalimatIstegi(BaseModel):
    metin: str = Field(default="", max_length=40000)


class SkillIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=64)
    aciklama: str = Field(min_length=1, max_length=600)
    icerik: str = Field(min_length=1, max_length=40000)
    surum: str = Field(default="", max_length=40)
    gereken_araclar: list[str] = Field(default=[], max_length=30)


class SkillDurumIstegi(BaseModel):
    acik: bool


def dogrulama_mesaji(e: ValidationError) -> str:
    """pydantic hatasini kullaniciya gosterilebilir kisa metne cevirir."""
    return (
        "; ".join(str(h.get("msg", "")).removeprefix("Value error, ") for h in e.errors())
        or "Gecersiz deger."
    )


def sse(olaylar: AsyncIterator[dict]) -> StreamingResponse:
    async def akis() -> AsyncIterator[str]:
        try:
            async for olay in olaylar:
                yield f"data: {json.dumps(olay, ensure_ascii=False, default=str)}\n\n"
        except (UygulamaHatasi, YerelLLMHatasi) as e:
            mesaj = e.mesaj if isinstance(e, UygulamaHatasi) else str(e)
            yield f"data: {json.dumps({'tur': 'hata', 'mesaj': mesaj}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        akis(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


def uygulama_olustur(
    veri_dizini: Path,
    fabrika: LLMFabrikasi = YerelLLM,
    skill_deposu: SkillDeposu | None = None,
    magaza: Magaza | None = None,
    kapat: Callable[[], None] | None = None,
    or_transport: Any = None,
    ollama_transport: Any = None,
    gecit: bool = True,
) -> FastAPI:
    kayit = ModelKaydi(veri_dizini)
    kayit.yukle()  # magazadan indirilen modeller MODELLER'e (ayar dogrulamasindan once)
    ayarlar = AyarDeposu(veri_dizini)
    oturumlar = OturumDeposu(veri_dizini)
    ekler = EkDeposu(veri_dizini)
    openrouter = OpenRouterDeposu(veri_dizini, transport=or_transport)
    ollama = Ollama(
        lambda: ayarlar.oku().ollama_adres,
        lambda: ollama_baglam(ayarlar.oku().baglam_token),
        transport=ollama_transport,
        site_transport=ollama_transport,
    )
    yonetici = ModelYonetici(ayarlar, fabrika, uzak=openrouter, ollama=ollama)
    talimatlar = TalimatDeposu(veri_dizini)
    skiller = skill_deposu or SkillDeposu(veri_dizini)
    projeler = WorkspaceDeposu(veri_dizini)
    _adaptorler: dict[tuple[str, str], Any] = {}

    def izolasyon() -> Any:
        a = ayarlar.oku()
        k = (a.izolasyon, a.konteyner_imaj)  # ayni secimde ayni nesne: durum onbellegi korunur
        if k not in _adaptorler:
            _adaptorler[k] = adaptor_olustur(*k)
        return _adaptorler[k]

    politika = PolitikaMotoru(veri_dizini, izolasyon=izolasyon)
    politika.kullanici_ag = lambda: ayarlar.oku().ag_acik
    politika.tam_yetki = lambda: ayarlar.oku().tam_yetki
    checkpointler = CheckpointDeposu(veri_dizini)
    komutlar = KomutServisi(izolasyon=izolasyon)
    sohbet = SohbetServisi(
        yonetici,
        oturumlar,
        ekler,
        talimatlar,
        skiller,
        projeler,
        politika,
        checkpointler,
        komutlar,
    )

    def proje_skill_kaynaklari() -> list[tuple[str, Path]]:
        alan = sohbet.aktif_alan()
        # kisisel klasorler proje degil; guvenilmeyen repo skill/talimat ekleyemez
        if alan.id == VARSAYILAN_ALAN_ID or not alan.talimat_okunur_mu():
            return []
        return [("proje", Path(k) / ".claude" / "skills") for k in alan.kokler]

    pluginler = PluginDeposu(veri_dizini)
    skiller.proje_kaynaklari = lambda: [*proje_skill_kaynaklari(), *pluginler.skill_kaynaklari()]
    hafiza = HafizaDeposu(veri_dizini)
    sirlar.KASA = sirlar.SirKasasi(veri_dizini)
    hooklar = HookDeposu(veri_dizini)
    mcp = McpYoneticisi(veri_dizini)
    uzantilar = UzantiYoneticisi(veri_dizini)
    arac_paketleri = AracPaketleri(veri_dizini, mcp)
    hooklar.ek_kaynak = pluginler.hook_tanimlari  # Claude Code plugin hook'lari (acilirsa)
    composio = Composio(veri_dizini)

    def _mcp_ek() -> list[dict]:
        ek = list(pluginler.mcp_tanimlari())  # Claude Code plugin .mcp.json (acilirsa)
        try:  # Composio anahtari varsa tool router MCP'si ajan baglayicisi olur
            if (d := composio.mcp_tanimi()) is not None:
                ek.append(d)
        except Exception as e:  # noqa: BLE001 - ag yoksa diger baglayicilar calismaya devam eder
            logger.debug("Composio baglayicisi eklenmedi: {}", e)
        return ek

    mcp.ek_kaynak = _mcp_ek
    # filesystem gibi sunucular izinli klasoru MCP roots'tan alir (klasorsuz aktarilan sunucu
    # her dosyayi "path outside allowed directories" ile reddediyordu)
    mcp.kokler = lambda: [str(k) for k in sohbet.aktif_alan().izinli_kokler]
    sohbet.uzantilar = uzantilar
    sohbet.tarayici = Tarayici(veri_dizini)
    sohbet.masaustu = Masaustu(
        lambda: ayarlar.oku().masaustu_izinli, veri_dizini / "ekran-goruntuleri"
    )
    sohbet.mcp = mcp
    sohbet.hafiza = hafiza

    def ajan_baglami(
        hedef: str, model_secimi: str | None = None
    ) -> tuple[str, list, dict, str | None]:
        alan = sohbet.aktif_alan()
        if sohbet.ajan_araclari(alan) is None:
            raise UygulamaHatasi("Ajan araclari hazir degil.")
        a = ayarlar.oku()
        sistem, araclar_, isleyiciler, skill_adi = sohbet.baglam_hazirla(
            a, hedef, [], model_secimi, ajan_gorevi=True
        )
        if a.otomatik_ogrenme:  # kullanici actiysa ajan kalici not ekleyebilir (dusuk guven)
            araclar_ = [*araclar_, HAFIZA_ARACI]
            sistem += HAFIZA_TALIMATI

            def hafizaya_ekle(metin: str, dayanak: list | None = None) -> dict:
                try:
                    dayanak_ = [str(x)[:500] for x in (dayanak or [])][:4]
                    return hafiza.ekle(
                        metin, kaynak="ajan", guven="dusuk", kapsam=alan.id, dayanak=dayanak_
                    )
                except (UygulamaHatasi, ValueError) as e:
                    return {"hata": getattr(e, "mesaj", str(e))}

            isleyiciler = {**isleyiciler, "hafizaya_ekle": hafizaya_ekle}
        if a.hafiza_acik:  # notlar sisteme giriyorsa ajan onlari degerlendirebilir (SAGE)
            araclar_ = [*araclar_, HAFIZA_YARGI_ARACI]

            def hafiza_yargila(id: str, yargi: str, duzeltme: str = "") -> dict:  # noqa: A002
                try:
                    k = hafiza.yargila(id, yargi, duzeltme)
                    return {"tamam": True, "revizyon": k["revizyon"]}
                except (UygulamaHatasi, Bulunamadi) as e:
                    return {"hata": e.mesaj}

            isleyiciler = {**isleyiciler, "hafiza_yargila": hafiza_yargila}

        def skill_kaydet(ad: str, aciklama: str, icerik: str, okunan_revizyon: int = 0) -> dict:
            # Skill sonraki islere talimat olur: yazma gibi izin motorundan gecer (onayli: sorar)
            try:
                istek = Istek(arac="skill_kaydet", yan_etki=YanEtki.yaz,
                              ozet=f"Skill kaydet: {ad}", komut=icerik[:2000])  # fmt: skip
                politika.uygula(istek, alan)
                return skiller.ajan_kaydet(ad, aciklama, icerik, okunan_revizyon)
            except OnayGerekli:
                raise
            except (UygulamaHatasi, YetkiYok) as e:
                return {"hata": getattr(e, "mesaj", str(e))}

        araclar_ = [*araclar_, SKILL_KAYDET_ARACI]
        isleyiciler = {**isleyiciler, "skill_kaydet": skill_kaydet}
        return sistem, araclar_, isleyiciler, skill_adi

    def model_yetenegi(model: str = "") -> ModelYetenegi:
        """model: projenin koordinator modeli (bos: aktif model). MODELLER disi = uzak."""
        a = ayarlar.oku()
        model = model or (a.aktif_model if a.saglayici == "ollama" else "")
        if model.startswith("ollama:"):
            y = ollama.yetenekler.get(model.removeprefix("ollama:")) or {}
            return ModelYetenegi(
                model=model, saglayici="ollama", araclar=y.get("araclar", True),
                json_cikti=True, goruntu=y.get("goruntu", False),
                baglam=min(y.get("baglam", 8192), ollama_baglam(a.baglam_token)),
                dusunme=y.get("dusunme", False), tokenizer="tahmin",
            )  # fmt: skip
        if model and model not in MODELLER:
            openrouter.eksik_modeli_getir(model)
            return uzak_yetenek(model, openrouter.liste_yolu)
        if model:
            return yerel_yetenek(model, a.baglam_token)
        if a.saglayici == "openrouter" and a.or_model:
            openrouter.eksik_modeli_getir(a.or_model)
            return uzak_yetenek(a.or_model, openrouter.liste_yolu)
        return yerel_yetenek(a.model, a.baglam_token)

    def onay_durumu(onay_id: str) -> str:
        return next(
            (o["karar"] for o in politika.onaylar.gecmis(500) if o["id"] == onay_id), "bekliyor"
        )

    run_deposu = RunDeposu(veri_dizini)
    run_deposu.kurtar()  # onceki oturumda yarim kalanlar: belirsiz yan etki kullaniciya sorulur

    async def gorev_baglami(run: Run) -> tuple[str, list, dict]:
        secim = run.skill_adi
        ayar = ayarlar.oku()
        if (
            run.calisma_koku
            and run.dal
            and not run.parent
            and not run.kullanim.model_cagrisi
            and secim is None
            and ayar.skiller_acik
        ):
            model = run.model if run.model_sabit or run.ajan_id else None
            try:
                async with asyncio.timeout(45), yonetici.kullan(model or None) as llm:
                    secim = await sohbet.skill_sec(llm, ayar, run.hedef, [], genis=True)
            except Exception as e:  # noqa: BLE001 - secim hatasi gorevi durdurmaz
                logger.debug("Gorev skill secimi basarisiz: {}", e)
        sistem, araclar_, isleyiciler, skill_adi = await asyncio.to_thread(
            ajan_baglami, run.hedef, secim
        )
        run.skill_adi = skill_adi or ""
        if run.calisma_koku:
            # Izole gorev araclari yalniz worktree kokunde calisir.
            alan = sohbet.aktif_alan().model_copy(
                update={"kokler": [run.calisma_koku], "ek_klasorler": []}
            )
            kayit = sohbet.ajan_araclari(alan)
            isleyiciler = {**isleyiciler, **kayit.isleyiciler()}
        return sistem, araclar_, isleyiciler

    ajan = AgentRunner(
        run_deposu,
        lambda hedef: ajan_baglami(hedef)[:3],
        lambda model=None: yonetici.kullan(model or None),
        onay_durumu,
        yetenek=model_yetenegi,
        hooks=hooklar,
        hafiza=lambda: (
            hafiza.sistem_metni(sohbet.aktif_alan().id) if ayarlar.oku().hafiza_acik else ""
        ),
    )
    ajan.gorev_baglami = gorev_baglami
    ajan.kok = lambda: next(iter(sohbet.aktif_alan().kokler), "")
    ajan.paralel_model = lambda: ayarlar.oku().saglayici == "openrouter"
    ajan.uygulayici_model = lambda: sohbet.aktif_alan().uygulayici_model

    def _proje_modeli(rol: str) -> dict:
        """Aktif projenin 'koordinator' / 'uygulayici' modeli; secilmemisse aktif model."""
        alan = sohbet.aktif_alan()
        ozel = getattr(alan, f"{rol}_model")
        return {
            "model": ozel or ayarlar.oku().aktif_model,
            "model_sabit": bool(ozel),
            "model_rol": rol,
            "uygulayici_model": alan.uygulayici_model if rol == "koordinator" else "",
        }

    # ---- kalici ajanlar (openbot tasarimindan): kimlik + kuyruk + ajanlar arasi mesaj ----
    from app.agent.dersler import DersDefteri

    ajan.dersler = DersDefteri(veri_dizini)  # gorevler arasi hatalardan ogrenme

    async def _gorev_incele(run) -> dict | None:
        """D (Chimera): gorevin yazdigi dosyalarin git diff'i -> review (model varsayimi)."""
        if not ayarlar.oku().otomatik_inceleme:
            return None
        kok = run.calisma_koku or ajan.kok()
        dosyalar = sorted({a.dosya for a in run.adimlar if a.dosya and a.arac in YAZAN_ARACLAR})
        if not kok or not dosyalar:
            return None

        def _diff() -> str:
            r = subprocess.run(
                ["git", "-C", kok, "diff", "HEAD", "--", *dosyalar], capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )  # fmt: skip
            return r.stdout if r.returncode == 0 else ""

        diff = await asyncio.to_thread(_diff)
        if not diff.strip():
            return None
        async with yonetici.kullan() as llm:
            cevap = await llm.json_cikti(
                rv.istem(diff), rv.SEMA, ad="review", max_tokens=3000, dusunme="kapali"
            )
        return rv.sonuclandir(cevap if isinstance(cevap, dict) else {}, diff)

    ajan.inceleyici = _gorev_incele
    ajan_deposu = AjanDeposu(veri_dizini)
    sohbet.ajan_olusturucu = ajan_deposu.olustur  # sohbette ajan_olustur araci
    ajan_dinleyicileri: list = []  # (ajan, is, run) -> None; Telegram cevabi vb.

    def _ajan_araclari(run) -> tuple[list, dict]:
        def ajana_mesaj(ajan: str, mesaj: str) -> dict:
            try:
                gonderen = ajan_deposu.getir(run.ajan_id)
                hedef = ajan_deposu.getir(ajan)
                if hedef.id == gonderen.id:
                    return {"hata": "Kendine mesaj atamazsin."}
                zincir = (gonderen.aktif_is.zincir if gonderen.aktif_is else 0) + 1
                ajan_deposu.kuyruga_ekle(hedef.id, KuyrukOgesi(
                    metin=f"[{gonderen.ad} ajanindan] {mesaj}", kimden=f"ajan:{gonderen.id}",
                    zincir=zincir, cevap_ajan=gonderen.id))  # fmt: skip
            except (UygulamaHatasi, ValueError) as e:
                return {"hata": getattr(e, "mesaj", str(e))}
            return {"gonderildi": hedef.ad, "not": "Cevap bitince sana yeni mesaj olarak gelir."}

        def ajan_notu(**kw) -> dict:
            try:
                a = ajan_deposu.hafizaya_ekle(run.ajan_id, str(kw.get("not") or ""))
            except UygulamaHatasi as e:
                return {"hata": e.mesaj}
            return {"kaydedildi": True, "not_sayisi": len(a.hafiza)}

        return [AJANA_MESAJ_ARACI, AJAN_NOTU_ARACI], {
            "ajana_mesaj": ajana_mesaj, "ajan_notu": ajan_notu}  # fmt: skip

    ajan.ajan_araclari = _ajan_araclari

    cli_isleri: dict[str, asyncio.Task] = {}  # ajan id -> calisan CLI isi (Claude Code / Codex)
    cli_canli: dict[str, list[str]] = {}  # ajan id -> canli ilerleme satirlari

    async def _cli_baslat(a, oge) -> str:
        cli_canli[a.id] = []
        digerleri = [x for x in ajan_deposu.liste() if x.id != a.id]
        ek = ajan_deposu.sistem_metni(a, digerleri)
        is_id = f"cli:{uuid.uuid4().hex[:10]}"

        async def calis():
            return await cli_ajan.calistir(
                a.saglayici, oge.metin, ajan_deposu.klasor(a), oturum=a.cli_oturum,
                tam_yetki=ayarlar.oku().tam_yetki, ek_sistem=ek, model=a.model,
                canli=cli_canli[a.id],
            )  # fmt: skip

        cli_isleri[a.id] = asyncio.create_task(calis())
        return is_id

    def _cli_sonucu(a) -> tuple[str, str] | None:
        """CLI isi bittiyse (durum, ozet); surerse None."""
        t = cli_isleri.get(a.id)
        if t is None:
            return "basarisiz", "CLI isi bulunamadi (uygulama yeniden baslatilmis olabilir)."
        if not t.done():
            return None
        cli_isleri.pop(a.id, None)
        if t.cancelled():
            return "iptal", "Iptal edildi."
        if (e := t.exception()) is not None:
            return "basarisiz", f"CLI calistirilamadi: {e}"
        s = t.result()
        if s.oturum and s.oturum != a.cli_oturum:
            ajan_deposu.duzenle(a.id, {"cli_oturum": s.oturum})
        maliyet = f" (CLI maliyet raporu: ${s.maliyet_usd:.4f})" if s.maliyet_usd else ""
        return s.durum, (s.ozet or s.durum) + maliyet

    async def _ajan_dagit() -> None:
        """Biten isi kapatir (cevap gonderene/dinleyicilere), bostaki ajana siradakini verir."""
        for a in ajan_deposu.liste():
            if a.aktif_run and a.aktif_run.startswith("cli:"):
                bitti = _cli_sonucu(a)
                if bitti is None:
                    continue
                durum, ozet = bitti
            elif a.aktif_run and a.aktif_run != "baslatiliyor":
                try:
                    r = run_deposu.getir(a.aktif_run)
                except Exception:  # noqa: BLE001 - silinmis run bitmis sayilir
                    r = None
                if r is not None and r.durum not in BITMIS_RUN:
                    continue  # calisiyor / onay bekliyor
                durum = str(r.durum.value) if r else "basarisiz"
                ozet = ((r.sonuc.ozet or r.hata) if r else "Gorev kaydi bulunamadi.") or durum
            else:
                durum = ""
            if durum:
                a, is_ = ajan_deposu.bitti(a.id, a.aktif_run, durum, ozet)
                if is_ and is_.cevap_ajan:  # ajanlar arasi: cevap gonderenin kuyruguna
                    try:
                        ajan_deposu.kuyruga_ekle(is_.cevap_ajan, KuyrukOgesi(
                            metin=f"[{a.ad} cevabi ({durum})] {ozet}", kimden=f"ajan:{a.id}",
                            zincir=is_.zincir))  # fmt: skip
                    except (UygulamaHatasi, Bulunamadi) as e:
                        logger.warning(f"Ajan cevabi iletilemedi: {e}")
                for dinle in ajan_dinleyicileri:
                    try:
                        await dinle(a, is_, durum, ozet)
                    except Exception as e:  # noqa: BLE001 - kanal hatasi kuyrugu durdurmaz
                        logger.warning(f"Ajan dinleyicisi: {e}")
            alinan = ajan_deposu.al(a.id)
            if alinan is None:
                continue
            a, oge = alinan
            if a.saglayici in ("claude", "codex", "antigravity"):
                try:
                    ajan_deposu.basladi(a.id, await _cli_baslat(a, oge))
                except Exception as e:  # noqa: BLE001
                    ajan_deposu.baslamadi(a.id, str(e))
                continue
            try:
                digerleri = [x for x in ajan_deposu.liste() if x.id != a.id]
                run = await ajan.baslat(
                    oge.metin, model=a.model or ayarlar.oku().aktif_model,
                    onceki=a.son_run, ajan_id=a.id,
                    ek_sistem=ajan_deposu.sistem_metni(a, digerleri),
                    calisma_koku=str(ajan_deposu.klasor(a)),
                )  # fmt: skip
                ajan_deposu.basladi(a.id, run.id)
            except Exception as e:  # noqa: BLE001
                ajan_deposu.baslamadi(a.id, getattr(e, "mesaj", str(e)))

    # ---- Telegram kanali: izinli sohbetten ajana mesaj, cevap Telegram'a ----
    telegram = TelegramKanali(veri_dizini)

    async def _telegram_mesaj(chat: int, metin: str, ad: str) -> str | None:
        t = telegram.ayar()
        if metin in ("/start", "/yardim", "/help"):
            liste = ", ".join(x.ad for x in ajan_deposu.liste()) or "yok"
            return (f"Kairo'ya bagli. Ajanlar: {liste}\nMesajin varsayilan ajana gider. "
                    "Baska ajana: '/ajan Ad mesaj'. Durum: /durum")  # fmt: skip
        if metin == "/durum":
            return (
                "\n".join(
                    f"{x.avatar} {x.ad}: {x.ozet()['durum']}, {len(x.kuyruk)} sirada"
                    for x in ajan_deposu.liste()
                )
                or "Ajan yok."
            )
        hedef = t.get("ajan", "")
        if metin.startswith("/ajan "):
            parca = metin[6:].strip().split(" ", 1)
            hedef, metin = parca[0], (parca[1] if len(parca) > 1 else "")
            if not metin:
                return "Kullanim: /ajan Ad mesaj"
        if not hedef:
            ilk = next(iter(ajan_deposu.liste()), None)
            if ilk is None:
                return "Kairo'da hic ajan yok; once Ajanlar sayfasindan olustur."
            hedef = ilk.id
        a = ajan_deposu.kuyruga_ekle(hedef, KuyrukOgesi(
            metin=metin, kimden=f"telegram:{chat}"))  # fmt: skip
        await _ajan_dagit()
        sira = len(ajan_deposu.getir(a.id).kuyruk)
        return f"{a.avatar} {a.ad} ise aldi" + (f" ({sira} is sirada)." if sira else ".")

    async def _telegram_cevap(a, is_, durum: str, ozet: str) -> None:
        if is_ and is_.kimden.startswith("telegram:"):
            chat = int(is_.kimden.split(":", 1)[1])
            await telegram.gonder(chat, f"{a.avatar} {a.ad} ({durum}):\n{ozet}")

    ajan_dinleyicileri.append(_telegram_cevap)

    # ---- Superajan: is emirleri (dsh-superagent tasarimi; SUPERAJAN-PLANI.md) ----
    from app.agent import superajan as sa

    superajan_deposu = sa.SuperajanDeposu(veri_dizini)

    def _aktif_kok() -> str:
        alan = sohbet.projeler.aktif() if sohbet.projeler else None
        return str(Path(alan.kokler[0])) if alan and alan.kokler else ""

    def _durum_ozet(is_: sa.IsEmri) -> tuple[str | None, str]:
        if not is_.runlar:
            return None, ""
        try:
            r = run_deposu.getir(is_.runlar[-1])
        except Exception:  # noqa: BLE001 - silinmis run bitmis sayilir
            return "basarisiz", "Gorev kaydi bulunamadi."
        return str(r.durum.value), (r.sonuc.ozet or r.hata or "")

    def _is_ozet(is_: sa.IsEmri) -> dict:
        durum, ozet = _durum_ozet(is_)
        asama = sa.asama(is_, durum, ozet)
        bekleme = ""
        if asama == "sirada" and _aktif_kok() != is_.proje_kok:
            bekleme = "Projesi açık değil; proje açılınca başlar."
        soru: dict = {}
        if durum == "cevap_bekliyor":  # T3: thread'in sorusu sohbette secenekli kart olur
            with contextlib.suppress(Exception):
                a = next(x for x in reversed(run_deposu.getir(is_.runlar[-1]).adimlar)
                         if x.arac == "soru_sor")  # fmt: skip
                secenek = [str(s)[:120] for s in (a.argumanlar.get("secenekler") or [])][:4]
                soru = {"metin": str(a.argumanlar.get("soru", ""))[:600], "secenekler": secenek}
        return {**is_.model_dump(exclude={"gorev"}), "gorev": is_.gorev[:400], "asama": asama,
                "run": is_.runlar[-1] if is_.runlar else "", "run_durum": durum or "",
                "ozet": ozet[:600], "bekleme": bekleme, "soru": soru}  # fmt: skip

    def _sohbet_is_ac(baslik: str, gorev: str) -> dict:
        """Sohbetten thread: aktif projede is emri; dongu (2 sn) baslatir."""
        kok = _aktif_kok()
        if not kok:
            raise UygulamaHatasi("Once bir proje ac.")
        if not wt.git_mi(Path(kok)):
            raise UygulamaHatasi("Proje bir git deposu degil; thread ayri dalda calisir.")
        is_ = superajan_deposu.olustur(baslik, gorev, kok, "sohbet",
                                       {"yazan": "model", "guc": "cikarim"})  # fmt: skip
        return _is_ozet(is_)

    def _sohbet_is_liste() -> list[dict]:
        kok = _aktif_kok()
        isler = [_is_ozet(x) for x in reversed(superajan_deposu.liste()) if x.proje_kok == kok]
        sira = {a: i for i, a in enumerate((*sa.INSAN_BEKLIYOR, "calisiyor", "sirada"))}
        return sorted(isler, key=lambda x: sira.get(x["asama"], 99))

    sohbet.is_emirleri = (_sohbet_is_ac, _sohbet_is_liste)
    sohbet.goruntu_var = lambda: model_yetenegi(sohbet.aktif_alan().koordinator_model).goruntu
    sohbet.model_baglami = lambda: model_yetenegi(sohbet.aktif_alan().koordinator_model).baglam
    sohbet.openrouter = openrouter

    async def _is_baslat(is_: sa.IsEmri) -> None:
        """Bir atama: ilk atamada worktree + dal olusur; sonrakiler ayni dalda onceki ozetle."""
        izole_kur = None
        if not is_.calisma_koku:
            proje = Path(is_.proje_kok)

            def izole_kur(run_id: str) -> tuple[str, str]:
                yol, dal = wt.olustur(proje, veri_dizini / "worktrees", run_id, "is")
                return str(yol), dal

        run = await ajan.baslat(
            sa.gorev_metni(is_, is_.bekleyen_mesaj), [], **_proje_modeli("uygulayici"),
            izole_kur=izole_kur, onceki=is_.runlar[-1] if is_.runlar else "",
            etkilesimli=True, calisma_koku=is_.calisma_koku,
        )  # fmt: skip
        is_ = superajan_deposu.getir(is_.id)
        is_.runlar = [*is_.runlar, run.id]
        is_.calisma_koku = is_.calisma_koku or run.calisma_koku
        is_.dal = is_.dal or run.dal
        is_.bekleyen_mesaj = ""
        is_.olay(f"Atama baslatildi ({run.id}).")
        superajan_deposu.guncelle(is_)

    # ---- Superajan GitHub (D3-D5): /kairo yoklama, teslim (PR), takip, PR kapanisi ----
    def _gh_yokla() -> dict:
        """Yorum + issue listelerinden yeni /kairo isteklerini is emrine cevirir (ETag'li)."""
        g = superajan_deposu.github()
        a = g["ayar"]
        if not (a.aktif and a.depo and a.proje_kok):
            return {"durum": "kapali"}
        yol = f"repos/{a.depo}/issues"
        d1, e1, yorumlar = sa.gh_liste(
            f"{yol}/comments?sort=updated&direction=desc&per_page=30", g["etag"].get("c", "")
        )
        d2, e2, konular = sa.gh_liste(
            f"{yol}?state=all&sort=updated&direction=desc&per_page=30", g["etag"].get("i", "")
        )
        if d1 not in (200, 304) or d2 not in (200, 304):
            raise UygulamaHatasi(f"GitHub okunamadi (HTTP {d1}/{d2}); gh girisini kontrol et.")
        yeni = sa.adaylar(yorumlar, konular, set(a.izinli), set(g["gorulen"]))
        acilan = takip = 0
        for x in yeni:
            konu = f"{a.depo}#{x['no']}"
            isler_ = reversed(superajan_deposu.liste())
            mevcut = next((i for i in isler_ if konu in i.konular), None)
            if mevcut and mevcut.durum != "durduruldu":  # D5: ayni konuya takip / yeniden acma
                mevcut.bekleyen_mesaj = maskele(x["metin"])[:4000]
                mevcut.durum, mevcut.onay_bekliyor = "acik", a.mod == "gozle"
                if mevcut.calisma_koku and not Path(mevcut.calisma_koku).is_dir():
                    mevcut.calisma_koku, mevcut.dal = "", ""  # birlestirilmis/atilmis: yeni dal
                mevcut.olay(f"GitHub takip: @{x['login']}")
                superajan_deposu.guncelle(mevcut)
                takip += 1
            else:
                ilk_satir = x["metin"].splitlines()[0][:80] if x["metin"] else ""
                superajan_deposu.olustur(
                    x["baslik"] or ilk_satir or konu, sa.github_gorev(a.depo, x),
                    a.proje_kok, "github",
                    {"yazan": x["login"], "guc": "acik", "mod": a.mod}, [konu], a.mod == "gozle",
                )  # fmt: skip
                acilan += 1
        superajan_deposu.github_yaz(
            a, [*g["gorulen"], *(x["anahtar"] for x in yeni)], {"c": e1, "i": e2}
        )
        return {"durum": "tamam", "acilan": acilan, "takip": takip}

    def _teslim(iid: str) -> dict:
        """D4: is emri dalini commit + push eder, PR acar, ilgili issue'lara yorum yazar."""
        is_ = superajan_deposu.getir(iid)
        if is_.pr_url:
            return {"durum": "zaten", "pr_url": is_.pr_url}
        if not is_.calisma_koku or not Path(is_.calisma_koku).is_dir() or not is_.dal:
            raise UygulamaHatasi("Bu is emrinin teslim edilecek dali yok.")
        depo = superajan_deposu.github()["ayar"].depo
        kok = Path(is_.calisma_koku)
        wt._git(kok, "add", "-A")
        wt._git(kok, "-c", "user.name=Kairo", "-c", "user.email=ajan@yerel", "commit", "-m",
                f"Is emri: {is_.baslik}"[:200])  # fmt: skip
        kod, cikti = wt._git(kok, "push", "-u", "origin", is_.dal, sure=300)
        if kod != 0:
            raise UygulamaHatasi(f"git push basarisiz: {cikti[-400:]}")
        ozet = maskele(_durum_ozet(is_)[1])[:3000]
        ilgili = "\n".join(f"Ilgili: #{k.split('#')[-1]}" for k in is_.konular)
        govde = f"{sa.ISARET}\nKairo is emri: {is_.baslik}\n\n{ozet}\n\n{ilgili}".strip()
        arg = ["pr", "create", "--head", is_.dal, "--title", is_.baslik[:120], "--body", govde]
        kod, cikti = sa.gh(*arg, *(["--repo", depo] if depo else []), cwd=str(kok))
        url = next((s for s in reversed(cikti.split()) if "/pull/" in s), "")
        if kod != 0 or not url:
            raise UygulamaHatasi(f"PR acilamadi: {cikti[-400:]}")
        for k in is_.konular:
            sa.gh("issue", "comment", k.split("#")[-1], "--repo", k.split("#")[0],
                  "--body", f"{sa.ISARET}\nKairo PR acti: {url}")  # fmt: skip
        is_ = superajan_deposu.getir(iid)
        is_.pr_url = url
        is_.olay(f"Teslim: {url}")
        superajan_deposu.guncelle(is_)
        return {"durum": "acildi", "pr_url": url}

    def _pr_durumlari() -> None:
        """D5: PR birlesti/kapandiysa is emri biter."""
        for is_ in [x for x in superajan_deposu.liste() if x.durum == "acik" and x.pr_url]:
            kod, cikti = sa.gh("pr", "view", is_.pr_url, "--json", "state", "-q", ".state")
            if kod == 0 and cikti.strip() in ("MERGED", "CLOSED"):
                is_.durum = "bitti"
                is_.olay(f"PR {cikti.strip().lower()}.")
                superajan_deposu.guncelle(is_)

    gh_zaman = {"son": 0.0}

    async def _gh_tick() -> None:
        """60 sn'de bir: yoklama, yap modunda dogrulanmis isi teslim, PR durumu."""
        a = superajan_deposu.github()["ayar"]
        if not a.aktif or time.monotonic() - gh_zaman["son"] < 60:
            return
        gh_zaman["son"] = time.monotonic()
        await asyncio.to_thread(_gh_yokla)
        if a.mod == "yap":
            for is_ in superajan_deposu.liste():
                if is_.kaynak != "github" or is_.durum != "acik" or is_.pr_url or not is_.runlar:
                    continue
                durum, ozet = _durum_ozet(is_)
                if sa.asama(is_, durum, ozet) != "inceleme":
                    continue
                with contextlib.suppress(Exception):  # dogrulanmamis/kayip run teslim edilmez
                    if run_deposu.getir(is_.runlar[-1]).sonuc.dogrulandi:
                        await asyncio.to_thread(_teslim, is_.id)
        await asyncio.to_thread(_pr_durumlari)

    async def _superajan_tick() -> None:
        """Siradaki is emirlerini baslatir: ayni anda en fazla ESZAMANLI, yalniz projesi acikken
        (araclar aktif projeye baglidir; kullanicinin acik projesi sessizce degistirilmez)."""
        try:
            await _gh_tick()
        except Exception as e:  # noqa: BLE001 - GitHub hatasi yerel isleri durdurmaz
            logger.warning(f"Superajan GitHub: {e}")
        isler = [x for x in superajan_deposu.liste() if x.durum == "acik"]
        asamalar = {x.id: sa.asama(x, *_durum_ozet(x)) for x in isler}
        calisan = sum(1 for a in asamalar.values() if a == "calisiyor")
        kok = _aktif_kok()
        for is_ in isler:
            if calisan >= sa.ESZAMANLI:
                return
            if asamalar[is_.id] != "sirada" or is_.proje_kok != kok:
                continue
            try:
                await _is_baslat(is_)
                calisan += 1
            except Exception as e:  # noqa: BLE001 - kaydedilir, dongu durmaz
                is_ = superajan_deposu.getir(is_.id)
                is_.durum = "durduruldu"
                is_.olay(f"Baslatilamadi: {e}")
                superajan_deposu.guncelle(is_)

    async def _ajan_dongusu() -> None:
        while True:
            try:
                await _ajan_dagit()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Ajan kuyrugu: {e}")
            try:
                await _superajan_tick()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Superajan: {e}")
            await asyncio.sleep(2)

    ajan.takim = TakimPanosu(veri_dizini)
    ajan.uzantilar = uzantilar
    ajan.ajan_profilleri = pluginler.ajan_profilleri
    isitmalar: set[asyncio.Task] = set()
    agecidi = AgGecidi(agecidi_uygulamasi(yonetici, ayarlar, kapat))
    magaza = magaza or Magaza()
    indirici = Indirici(magaza, kayit, lambda: Path(ayarlar.oku().llm_dizin))
    testler = TestServisi(yonetici, ekler)

    @asynccontextmanager
    def _isit_baglam() -> None:
        try:
            ajan_baglami("")
        except Exception as e:  # noqa: BLE001 - isitma yardimci; proje yoksa vb. sessiz
            logger.debug("Baglam isitma atlandi: {}", e)

    async def omur(_: FastAPI):
        komutlar.loop = asyncio.get_running_loop()  # arka plan komutlari bu loop'ta yasar
        a = ayarlar.oku()
        if gecit and a.sunucu_acik:
            await agecidi.baslat(a.sunucu_port)
        zd = asyncio.create_task(_zamanlayici_dongusu()) if gecit else None
        ad_ = asyncio.create_task(_ajan_dongusu())  # kalici ajan kuyruklari
        if gecit:
            telegram.baslat(_telegram_mesaj)
        if gecit:  # genel "hizli ac" kisayolu (Claude Desktop Quick Entry)
            kisayol.ayarla(a.hizli_kisayol)
        if gecit:  # Claude Code plugin'lerini arka planda ice aktar (acilisi bekletmez).
            # daemon: buyuk plugin taramasi (telegram ~3600 dosya, ~1 dk) kapanisi bekletmesin;
            # yarim kalan is sonraki acilista bastan yapilir (durum en sonda yazilir).
            threading.Thread(target=_cc_esitle, name="cc-esitle", daemon=True).start()
        if gecit:  # MCP sunuculari ve arac semalari ilk mesajdan once arka planda isinsin
            asyncio.get_running_loop().run_in_executor(None, _isit_baglam)
        if a.saglayici == "openrouter":  # baglanti havuzu (SSL ~1.5 sn) ilk mesajdan once
            asyncio.get_running_loop().run_in_executor(None, openrouter._tasima)
        yield
        cc_dur.set()  # surmekte olan plugin esitlemesi sureci acik tutmasin
        if zd:
            zd.cancel()
        ad_.cancel()
        telegram.durdur()
        await uzak_sunucu.kapat()  # A12: uzak erisim uygulamayla birlikte kapanir
        await ajan.kapat()  # calisan gorevler guvenli sinirda duraklatilir
        mcp.kapat()  # MCP sunucu surecleri yetim kalmasin
        uzantilar.kapat()
        kisayol.kapat()
        for kz in sohbet.kod_zekasi.values():  # dil sunuculari
            kz.kapat()
        if sohbet.tarayici.acik_mi():
            await asyncio.to_thread(sohbet.tarayici.kapat)
        await komutlar.hepsini_durdur()  # yetim test/dev-server surecleri kalmasin
        await agecidi.durdur()
        await yonetici.kapat()  # yalniz bizim baslattigimiz model sunucusunu durdurur
        await magaza.kapat()
        await ollama.kapat()  # yalniz Kairo'nun baslattigi Ollama surecini durdurur

    app = FastAPI(title=URUN_ADI, version=__version__, lifespan=omur)
    app.state.ajan_deposu = ajan_deposu
    app.state.superajan = superajan_deposu
    app.state.superajan_tick = _superajan_tick
    app.state.ajan_dagit = _ajan_dagit
    app.state.ajan_runner = ajan

    # ---- Superajan rotalari: elle is emri, takip, teslim (birlestir / at), durdur ----
    @app.get("/api/superajan")
    async def superajan_liste() -> dict:
        isler = [_is_ozet(x) for x in reversed(superajan_deposu.liste())]
        bekleyen = sum(1 for x in isler if x["asama"] in sa.INSAN_BEKLIYOR)
        return {"isler": isler, "aktif_proje": _aktif_kok(), "insan_bekliyor": bekleyen}

    @app.post("/api/superajan/isler")
    async def superajan_yeni(istek: IsEmriIstegi) -> dict:
        kok = istek.proje_kok or _aktif_kok()
        if not kok:
            raise UygulamaHatasi("Once bir proje ac ya da proje klasoru sec.")
        if not await asyncio.to_thread(wt.git_mi, Path(kok)):
            # arayuz bu kodu gorunce kullaniciya "git deposu olusturulsun mu?" diye sorar
            raise UygulamaHatasi(
                "GIT_YOK: Is emri ayri dalda calisir; proje bir git deposu olmali."
            )
        dogrula(model_yetenegi(), araclar_gerekli=True, dusunme=ayarlar.oku().dusunme)
        baslik = istek.baslik.strip() or istek.gorev.strip().splitlines()[0][:80]
        is_ = superajan_deposu.olustur(baslik, istek.gorev, kok, istek.kaynak,
                                       {"yazan": "kullanici", "guc": "acik"})  # fmt: skip
        await _superajan_tick()
        return _is_ozet(superajan_deposu.getir(is_.id))

    @app.post("/api/superajan/git-baslat")
    async def superajan_git_baslat(istek: IsEmriIstegi) -> dict:
        kok = istek.proje_kok or _aktif_kok()
        if not kok:
            raise UygulamaHatasi("Once bir proje ac.")
        return await asyncio.to_thread(wt.git_baslat, Path(kok))

    @app.post("/api/superajan/isler/{iid}/mesaj")
    async def superajan_mesaj(iid: str, istek: GorevMesaji) -> dict:
        """Takip: calisan atamaya yonlendirme olur; bitmis is emrine yeni atama acar."""
        is_ = superajan_deposu.getir(iid)
        if is_.durum != "acik":
            raise UygulamaHatasi("Bu is emri kapali.")
        durum, _ = _durum_ozet(is_)
        if durum in ("calisiyor", "duraklatildi", "onay_bekliyor", "cevap_bekliyor"):
            await ajan.mesaj(is_.runlar[-1], istek.metin)
        else:
            is_.bekleyen_mesaj = istek.metin.strip()[:4000]
            is_.olay("Takip mesaji: yeni atama sirada.")
            superajan_deposu.guncelle(is_)
            await _superajan_tick()
        return _is_ozet(superajan_deposu.getir(iid))

    @app.post("/api/superajan/isler/{iid}/tekrar")
    async def superajan_tekrar(iid: str) -> dict:
        is_ = superajan_deposu.getir(iid)
        is_.durum, is_.bekleyen_mesaj = "acik", "Onceki atama bitti; isi tamamla ya da duzelt."
        is_.olay("Tekrar istendi.")
        superajan_deposu.guncelle(is_)
        await _superajan_tick()
        return _is_ozet(superajan_deposu.getir(iid))

    @app.post("/api/superajan/isler/{iid}/durdur")
    async def superajan_durdur(iid: str) -> dict:
        """Kalici durdurma (yalniz kullanici): calisan atama iptal, yeni girdi baslatmaz."""
        is_ = superajan_deposu.getir(iid)
        if is_.runlar and ajan.calisiyor_mu(is_.runlar[-1]):
            await ajan.iptal(is_.runlar[-1])
        is_.durum = "durduruldu"
        is_.olay("Kullanici durdurdu.")
        superajan_deposu.guncelle(is_)
        return _is_ozet(is_)

    @app.post("/api/superajan/isler/{iid}/birlestir")
    async def superajan_birlestir(iid: str, istek: EntegreIstegi) -> dict:
        is_ = superajan_deposu.getir(iid)
        if not is_.calisma_koku or not is_.dal:
            raise UygulamaHatasi("Bu is emrinin birlestirilecek dali yok.")
        s = await asyncio.to_thread(
            wt.entegre_et, Path(is_.proje_kok), Path(is_.calisma_koku), is_.dal,
            f"Is emri: {is_.baslik}", istek.test_komutu,
        )  # fmt: skip
        if s.get("durum") == "birlestirildi":
            is_.durum = "bitti"
            is_.olay("Ana dala birlestirildi.")
            superajan_deposu.guncelle(is_)
        return {**s, "is": _is_ozet(is_)}

    @app.post("/api/superajan/isler/{iid}/baslat")
    async def superajan_baslat(iid: str) -> dict:
        """Gozle modu: GitHub'dan gelen is emrini kullanici onaylar."""
        is_ = superajan_deposu.getir(iid)
        is_.onay_bekliyor = False
        is_.olay("Kullanici baslatti.")
        superajan_deposu.guncelle(is_)
        await _superajan_tick()
        return _is_ozet(superajan_deposu.getir(iid))

    @app.post("/api/superajan/isler/{iid}/teslim")
    async def superajan_teslim(iid: str) -> dict:
        s = await asyncio.to_thread(_teslim, iid)
        return {**s, "is": _is_ozet(superajan_deposu.getir(iid))}

    @app.get("/api/superajan/github")
    async def superajan_github() -> dict:
        return superajan_deposu.github()["ayar"].model_dump() | {"gh": bool(sa.gh_yolu())}

    @app.put("/api/superajan/github")
    async def superajan_github_kaydet(veri: dict) -> dict:
        g = superajan_deposu.github()
        ayar = sa.GithubAyar(**{k: v for k, v in veri.items() if k != "gh"}).dogrula()
        ayar.proje_kok = ayar.proje_kok or _aktif_kok()
        if ayar.aktif and not ayar.izinli:  # varsayilan izinli: gh hesabinin kendisi
            kod, cikti = await asyncio.to_thread(sa.gh, "api", "user", "-q", ".login")
            if kod != 0 or not cikti.strip():
                raise UygulamaHatasi("gh hesabi okunamadi; once GitHub'a baglan.")
            ayar.izinli = [cikti.strip().lower()]
        if ayar.aktif and not (ayar.depo and ayar.proje_kok):
            raise UygulamaHatasi("Depo ve proje klasoru gerekli.")
        ayni = ayar.depo == g["ayar"].depo
        superajan_deposu.github_yaz(ayar, g["gorulen"] if ayni else [], g["etag"] if ayni else {})
        return ayar.model_dump()

    @app.post("/api/superajan/yokla")
    async def superajan_yokla() -> dict:
        s = await asyncio.to_thread(_gh_yokla)
        await _superajan_tick()
        return s

    @app.post("/api/superajan/isler/{iid}/at")
    async def superajan_at(iid: str) -> dict:
        is_ = superajan_deposu.getir(iid)
        if is_.runlar and ajan.calisiyor_mu(is_.runlar[-1]):
            await ajan.iptal(is_.runlar[-1])
        if is_.calisma_koku and is_.dal:
            await asyncio.to_thread(wt.at, Path(is_.proje_kok), Path(is_.calisma_koku), is_.dal)
        is_.durum = "bitti"
        is_.olay("Degisiklikler atildi (ana dala dokunulmadi).")
        superajan_deposu.guncelle(is_)
        return _is_ozet(is_)

    @app.delete("/api/superajan/isler/{iid}")
    async def superajan_sil(iid: str) -> dict:
        is_ = superajan_deposu.getir(iid)
        if is_.durum == "acik" and is_.runlar:
            raise UygulamaHatasi("Acik is emri silinmez; once birlestir, at ya da durdur.")
        superajan_deposu.sil(iid)
        return {"silindi": iid}

    @app.get("/api/ajanlar")
    async def ajan_listesi() -> dict:
        return {"ajanlar": [a.ozet() for a in ajan_deposu.liste()]}

    @app.post("/api/ajanlar")
    async def ajan_olustur(veri: dict) -> dict:
        return ajan_deposu.olustur(veri).ozet()

    @app.get("/api/ajanlar/{ajan_id}")
    async def ajan_getir(ajan_id: str) -> dict:
        a = ajan_deposu.getir(ajan_id)
        return {**a.ozet(), "konusma": [m.model_dump() for m in a.konusma],
                "canli": cli_canli.get(a.id, [])[-40:] if a.aktif_run.startswith("cli:") else [],
                "kuyruk": [k.model_dump() for k in a.kuyruk],
                "klasor_yolu": str(ajan_deposu.klasor(a))}  # fmt: skip

    @app.put("/api/ajanlar/{ajan_id}")
    async def ajan_duzenle(ajan_id: str, veri: dict) -> dict:
        return ajan_deposu.duzenle(ajan_id, veri).ozet()

    @app.delete("/api/ajanlar/{ajan_id}")
    async def ajan_sil(ajan_id: str) -> dict:
        a = ajan_deposu.getir(ajan_id)
        if a.id in cli_isleri:
            cli_isleri.pop(a.id).cancel()
        elif a.aktif_run and a.aktif_run != "baslatiliyor":
            with contextlib.suppress(Exception):
                await ajan.iptal(a.aktif_run)
        ajan_deposu.sil(a.id)
        return {"silindi": a.id}

    @app.post("/api/ajanlar/{ajan_id}/mesaj")
    async def ajana_yaz(ajan_id: str, veri: dict) -> dict:
        metin = str(veri.get("metin") or "").strip()
        if not metin:
            raise UygulamaHatasi("Mesaj bos olamaz.")
        a = ajan_deposu.kuyruga_ekle(ajan_id, KuyrukOgesi(metin=metin, kimden="kullanici"))
        await _ajan_dagit()  # bostaysa hemen basla
        return ajan_deposu.getir(a.id).ozet()

    @app.get("/api/ajanlar-saglayicilar")
    async def ajan_saglayicilari() -> dict:
        return {"saglayicilar": cli_ajan.SAGLAYICILAR, "kurulu": cli_ajan.durum()}

    @app.post("/api/ajanlar/{ajan_id}/iptal")
    async def ajan_is_iptal(ajan_id: str) -> dict:
        a = ajan_deposu.getir(ajan_id)
        if a.id in cli_isleri:
            cli_isleri[a.id].cancel()
        elif a.aktif_run and a.aktif_run != "baslatiliyor":
            await ajan.iptal(a.aktif_run)
        return {"iptal": True}

    @app.get("/api/skiller/{ad}/revizyonlar")
    async def skill_revizyonlari(ad: str) -> dict:
        return {"simdiki": skiller.revizyon(ad), "revizyonlar": skiller.revizyonlar(ad)}

    @app.post("/api/skiller/{ad}/geri-al")
    async def skill_geri_al(ad: str, veri: dict) -> dict:
        s = skiller.geri_al(ad, int(veri.get("revizyon") or 0))
        return {"ad": s.ad, "simdiki": skiller.revizyon(s.ad)}

    @app.get("/api/telegram")
    async def telegram_durum() -> dict:
        return telegram.durum()

    @app.put("/api/telegram")
    async def telegram_kaydet(veri: dict) -> dict:
        d = telegram.kaydet(veri)
        if d["aktif"] and d["token_var"]:
            telegram.baslat(_telegram_mesaj)
        return d

    @app.post("/api/telegram/dene")
    async def telegram_dene(veri: dict) -> dict:
        chat = int(veri.get("chat") or 0)
        if chat not in telegram.ayar().get("izinli", []):
            raise UygulamaHatasi("Bu sohbet izin listesinde degil.")
        await telegram.gonder(chat, "Kairo baglantisi calisiyor.")
        return {"gonderildi": True}

    @app.delete("/api/ajanlar/{ajan_id}/kuyruk/{oge_id}")
    async def ajan_kuyruk_sil(ajan_id: str, oge_id: str) -> dict:
        return ajan_deposu.kuyruktan_sil(ajan_deposu.getir(ajan_id).id, oge_id).ozet()

    app.state.yonetici = yonetici
    app.state.sohbet = sohbet
    app.state.agecidi = agecidi
    app.state.oturum_anahtari = oturum_anahtari = secrets.token_urlsafe(24)
    app.state.politika = politika

    @app.middleware("http")
    async def _loopback_koruma(istek: Request, sonraki):
        """Loopback API sertlestirmesi (A1.9).

        Yerel bir surecte acik port, "yalniz ben erisebilirim" demek degil: tarayicidaki
        herhangi bir sayfa da 127.0.0.1'e istek atabilir. Bu nedenle:
        - Host yalniz loopback olabilir (DNS rebinding)
        - Origin/Referer varsa loopback olmali (CSRF)
        - /api cagrilari oturum anahtari ister; anahtar yalniz bizim sundugumuz sayfaya gomulur,
          baska origin onu OKUYAMAZ.
        Bu, isletim sistemi duzeyinde yetkilendirme DEGILDIR: ayni kullanicinin baska bir yerel
        programi index.html'i okuyup anahtari alabilir. Gercek izolasyon icin A1.8 notuna bak.
        """
        konak = (istek.headers.get("host") or "").rsplit(":", 1)[0]
        if not yerel_host_mu(konak):
            return JSONResponse({"hata": "Yalniz bu bilgisayardan erisilir."}, status_code=403)
        kaynak = istek.headers.get("origin") or istek.headers.get("referer") or ""
        # OAuth geri donusu saglayicinin sitesinden (or. vercel.com) yonlendirmeyle gelir;
        # Referer dis olur. Tek kullanimlik state ile korunur, yalniz GET.
        oauth_geri = istek.method == "GET" and istek.url.path == "/api/mcp/oauth/geri"
        if kaynak and not oauth_geri:
            try:
                kaynak_konak = urlsplit(kaynak).hostname
            except ValueError:
                kaynak_konak = None
            if not yerel_host_mu(kaynak_konak):
                return JSONResponse({"hata": "Dis kaynakli istek reddedildi."}, status_code=403)
        yol = istek.url.path
        # yalniz urun bilgisi ve HMAC imzali webhook tetikleme ucu oturum anahtarsiz
        korunan = (
            yol.startswith("/api") and yol != "/api/bilgi"
            and not yol.startswith("/api/webhook/")
            and yol != "/api/mcp/oauth/geri"  # tek kullanimlik state ile korunur
        )  # fmt: skip
        if korunan and istek.headers.get(OTURUM_BASLIGI) != oturum_anahtari:
            return JSONResponse(
                {"hata": "Oturum anahtari gecersiz; uygulamayi yeniden acin."}, status_code=403
            )
        return await sonraki(istek)

    @app.exception_handler(OnayGerekli)
    async def _onay_gerekli(_: Request, e: OnayGerekli) -> JSONResponse:
        return JSONResponse({"hata": e.mesaj, "onay": e.onay}, status_code=e.durum)

    @app.exception_handler(UygulamaHatasi)
    async def _uygulama_hatasi(_: Request, e: UygulamaHatasi) -> JSONResponse:
        return JSONResponse({"hata": e.mesaj}, status_code=e.durum)

    @app.exception_handler(YerelLLMHatasi)
    async def _llm_hatasi(_: Request, e: YerelLLMHatasi) -> JSONResponse:
        return JSONResponse({"hata": str(e)}, status_code=503)

    @app.exception_handler(ValidationError)
    async def _dogrulama_hatasi(_: Request, e: ValidationError) -> JSONResponse:
        return JSONResponse({"hata": dogrulama_mesaji(e)}, status_code=422)

    @app.exception_handler(ValueError)
    async def _deger_hatasi(_: Request, e: ValueError) -> JSONResponse:
        return JSONResponse({"hata": str(e)}, status_code=422)

    # ---- genel ----
    @app.get("/api/bilgi")
    async def bilgi() -> dict:
        return {
            "urun": URUN_ADI,
            "surum": __version__,
            "urun_sahibi": URUN_SAHIBI,
            "x": URUN_SAHIBI_X,
            "github": URUN_SAHIBI_GITHUB,
            "dusunme_secenekleri": DUSUNME_SECENEKLERI,
            "veri_dizini": str(veri_dizini),
        }

    @app.get("/api/durum")
    async def durum() -> dict:
        return await yonetici.bilgi()

    @app.post("/api/model/hazirla")
    async def model_hazirla(istek: ModelIstegi) -> dict:
        sonuc = await yonetici.hazirla(istek.model)
        isitmalar.add(gorev := asyncio.create_task(sohbet.isit()))  # arka planda onbellek
        gorev.add_done_callback(isitmalar.discard)
        return sonuc

    @app.post("/api/model/durdur")
    async def model_durdur(istek: DurdurIstegi) -> dict:
        return await yonetici.durdur(harici=istek.harici)

    # ---- OpenRouter (anahtar backend'de kalir; arayuze yalniz maskeli hali gider) ----
    @app.get("/api/openrouter/anahtar")
    async def or_anahtar() -> dict:
        return openrouter.anahtar_durumu()

    @app.put("/api/openrouter/anahtar")
    async def or_anahtar_kaydet(istek: AnahtarIstegi) -> dict:
        return openrouter.anahtar_kaydet(istek.anahtar)

    @app.delete("/api/openrouter/anahtar")
    async def or_anahtar_sil() -> dict:
        return openrouter.anahtar_sil()

    @app.get("/api/openrouter/limit")
    async def or_limit() -> dict:
        return await openrouter.limit()

    @app.get("/api/openrouter/modeller")
    async def or_modeller(yenile: bool = False, cikti: str = "") -> dict:
        return await openrouter.modeller(yenile, cikti)

    @app.post("/api/openrouter/test")
    async def or_test(istek: ModelIstegi) -> dict:
        return await openrouter.test(istek.model or ayarlar.oku().or_model)

    # ---- ayarlar ----
    @app.get("/api/ayarlar")
    async def ayar_oku() -> dict:
        return ayarlar.oku().model_dump()

    @app.put("/api/ayarlar")
    async def ayar_yaz(degisiklik: dict) -> dict:
        once = ayarlar.oku()
        yeni = ayarlar.guncelle(degisiklik)
        if "baslangicta_ac" in degisiklik:  # gercek durum kisayol dosyasidir
            await asyncio.to_thread(mda.baslangic_ayarla, yeni.baslangicta_ac)
        if (
            gecit
            and once.hizli_kisayol != yeni.hizli_kisayol
            and not kisayol.ayarla(yeni.hizli_kisayol)
            and yeni.hizli_kisayol
        ):
            raise UygulamaHatasi(kisayol.hata or "Kisayol kaydedilemedi.")
        if (once.sunucu_acik, once.sunucu_port) != (yeni.sunucu_acik, yeni.sunucu_port):
            if yeni.sunucu_acik:
                await agecidi.baslat(yeni.sunucu_port)
            else:
                await agecidi.durdur()
        return yeni.model_dump()

    @app.get("/api/sunucu")
    async def sunucu_durumu() -> dict:
        a = ayarlar.oku()
        return {**agecidi.durum(), "ayar_acik": a.sunucu_acik, "ayar_port": a.sunucu_port}

    @app.post("/api/sunucu/yeniden")
    async def sunucu_yeniden() -> dict:
        a = ayarlar.oku()
        await agecidi.baslat(a.sunucu_port)
        return agecidi.durum()

    @app.post("/api/ayarlar/test")
    async def ayar_test(istek: ModelIstegi) -> dict:
        """Secili modeli uygulamanin gercek kullandigi bicimde (json_schema) kisa istekle dener."""
        bas = time.perf_counter()
        async with yonetici.kullan(istek.model) as llm:
            veri = await llm.json_cikti(
                "Turkiye'nin baskenti ve plaka kodu?",
                {
                    "type": "object",
                    "properties": {"sehir": {"type": "string"}, "plaka": {"type": "integer"}},
                    "required": ["sehir", "plaka"],
                },
                max_tokens=100,
                dusunme="kapali",
            )
        return {
            "basarili": "ankara" in str(veri.get("sehir", "")).lower(),
            "sonuc": veri,
            "sure_sn": round(time.perf_counter() - bas, 1),
            "yukleme_sn": yonetici.yukleme_sn,
            "maliyet": "0 (yerel)",
            "uretim_tok_sn": round((llm.son_zamanlama or {}).get("predicted_per_second") or 0, 1),
        }

    # ---- oturumlar ----
    akistaki: set[str] = set()  # duz sohbet cevabi suren oturumlar (telefon "calisiyor" gosterir)

    @app.get("/api/oturumlar")
    async def oturum_liste(q: str = "") -> list[dict]:
        return [{**o, "akista": o["id"] in akistaki} for o in oturumlar.liste(q)]

    @app.post("/api/oturumlar")
    async def oturum_yeni() -> dict:
        return oturumlar.olustur(sohbet.aktif_alan().id).model_dump()  # sohbet projeye ozgu

    @app.get("/api/oturumlar/{oturum_id}/baglam")
    async def oturum_baglam(oturum_id: str) -> dict:
        """Sag panel 'Baglam' dokumu (Claude Code Context gibi): bir sonraki istekte modele
        gidecek parcalarin tahmini token'i. Mesajlar + sistem + talimatlar + araclar + skill."""
        o = oturumlar.getir(oturum_id)
        mesaj = sum(tahmini_token(m.metin) + tahmini_token(m.dusunce) for m in o.mesajlar)
        ayar = ayarlar.oku()
        try:
            _, araclar, _, _ = await asyncio.to_thread(sohbet.baglam_hazirla, ayar, "", o.mesajlar)
            p = getattr(sohbet, "son_parcalar", {})
        except Exception as e:  # noqa: BLE001 - dokum gosterge; hesaplanamazsa yalniz mesajlar
            logger.debug("Baglam dokumu hesaplanamadi: {}", e)
            araclar, p = [], {}
        tok = lambda x: tahmini_token(x) if x else 0  # noqa: E731
        jtok = lambda x: tok(x and json.dumps(x, ensure_ascii=False))  # noqa: E731
        mcp = [a for a in araclar if str(a.get("function", {}).get("name", "")).startswith("mcp")]
        yerlesik = [a for a in araclar if a not in mcp]
        kalemler = [
            {"ad": "Mesajlar", "tur": "mesaj", "token": mesaj},
            {"ad": "Sistem talimatı", "tur": "sistem", "token": tok(p.get("sistem"))},
            {"ad": "KAIRO.md ve talimatlar", "tur": "talimat", "token": tok(p.get("talimat"))},
            {"ad": "Proje talimatı", "tur": "proje", "token": tok(p.get("proje"))},
            {"ad": "Hafıza", "tur": "hafiza", "token": tok(p.get("hafiza"))},
            {"ad": "Skill'ler", "tur": "skill", "token": tok(p.get("skill"))},
            {"ad": "Araçlar", "tur": "arac", "token": jtok(yerlesik),
             "sayi": len(yerlesik)},
            {"ad": "MCP araçları", "tur": "mcp", "token": jtok(mcp),
             "sayi": len(mcp)},
        ]  # fmt: skip
        kalemler = [k for k in kalemler if k["token"] or k["tur"] == "mesaj"]
        boyut = model_yetenegi().baglam or 1
        kullanilan = sum(k["token"] for k in kalemler)
        for k in kalemler:
            k["yuzde"] = round(k["token"] * 100 / boyut, 1)
        return {"kullanilan": kullanilan, "boyut": boyut, "kalemler": kalemler,
                "bos": max(0, boyut - kullanilan),
                "yuzde": min(100, round(kullanilan * 100 / boyut))}  # fmt: skip

    @app.get("/api/oturumlar/{oturum_id}")
    async def oturum_getir(oturum_id: str) -> dict:
        return oturumlar.getir(oturum_id).model_dump()

    # ---- oturum catal / temizle / disa aktar (A4.5); temizle hafizaya dokunmaz ----
    @app.post("/api/oturumlar/{oturum_id}/geri-sar")
    async def oturum_geri_sar(oturum_id: str, istek: GeriSarIstegi) -> dict:
        o, metin = oturumlar.geri_sar(oturum_id, istek.mesaj_id, istek.run)
        return {"oturum": o.model_dump(), "metin": metin}

    @app.post("/api/oturumlar/{oturum_id}/catal")
    async def oturum_catal(oturum_id: str, istek: GeriSarIstegi | None = None) -> dict:
        return oturumlar.catal(oturum_id, istek.mesaj_id if istek else "").model_dump()

    @app.post("/api/oturumlar/{oturum_id}/mesajlar/{mesaj_id}/sabitle")
    async def mesaj_sabitle(oturum_id: str, mesaj_id: str) -> dict:
        return oturumlar.sabitle(oturum_id, mesaj_id).model_dump()

    @app.post("/api/oturumlar/{oturum_id}/alt")
    async def oturum_alt(oturum_id: str, istek: AltOturumIstegi) -> dict:
        return oturumlar.alt_olustur(oturum_id, istek.baslik, istek.kaynak).model_dump()

    @app.post("/api/sonraki-oneri")
    async def sonraki_oneri(istek: SonrakiOneriIstegi) -> dict:
        """Claude Code gibi: tur bitince kullanicinin muhtemel sonraki mesajini tek satir onerir.
        Girdi kutusunda soluk gorunur, Tab ile alinir. Oneri yoksa bos doner; hata sessizdir."""
        if not istek.asistan.strip():
            return {"oneri": ""}
        istem = (
            "Asagida bir kullanici ile kodlama asistaninin son konusma turu var. Kullanicinin "
            "BIR SONRAKI mesajini, kullanicinin agzindan, Turkce, en fazla 70 karakterlik tek "
            "emir cumlesi olarak tahmin et (or. 'main'e birlestir ve DURUM.md guncelle'). "
            "Asistanin sundugu acik bir sonraki adim, soru ya da onay bekleyen is varsa onu sec. "
            "Belirgin bir sonraki adim yoksa bos dize dondur.\n\n"
            f"KULLANICI: {istek.kullanici[-1500:]}\n\nASISTAN: {istek.asistan[-4000:]}"
        )
        try:
            async with asyncio.timeout(45), yonetici.kullan() as llm:
                v = await llm.json_cikti(
                    istem,
                    {"type": "object", "properties": {"oneri": {"type": "string"}},
                     "required": ["oneri"]},
                    ad="sonraki_oneri", max_tokens=80, dusunme="kapali",
                )  # fmt: skip
        except Exception as e:  # noqa: BLE001 - oneri istege bagli; sohbeti bozmaz
            logger.debug("Sonraki oneri alinamadi: {}", e)
            return {"oneri": ""}
        oneri = " ".join(str(v.get("oneri") or "").split()).strip(" .\"'")
        # kucuk modeller istemdeki etiketi tekrarlayabilir ("SONRAKI mesaj: ...", "KULLANICI: ...")
        oneri = re.sub(r"^[^:]{0,40}(sonraki|kullanici|mesaj)[^:]{0,20}:\s*", "", oneri, flags=re.I)
        oneri = oneri.strip(" .\"'")
        if oneri.casefold() == " ".join(istek.kullanici.split()).strip(" .\"'").casefold():
            oneri = ""  # az once yazdigini tekrar onermek anlamsiz
        return {"oneri": oneri[:100]}

    @app.post("/api/oturumlar/{oturum_id}/oneri-reddet")
    async def oturum_oneri_reddet(oturum_id: str, istek: OneriRedIstegi) -> dict:
        o = oturumlar.oneri_reddet(oturum_id, istek.kaynak, istek.karar)
        return {"oneri_kararlari": o.oneri_kararlari}

    @app.post("/api/oturumlar/{oturum_id}/temizle")
    async def oturum_temizle(oturum_id: str) -> dict:
        return oturumlar.temizle(oturum_id).model_dump()

    @app.get("/api/oturumlar/{oturum_id}/disa-aktar")
    async def oturum_disa_aktar(oturum_id: str, bicim: str = "json") -> Response:
        if bicim == "md":
            return Response(
                oturumlar.disa_aktar_md(oturum_id),
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="sohbet-{oturum_id}.md"'},
            )
        return JSONResponse(
            oturumlar.getir(oturum_id).model_dump(),
            headers={"Content-Disposition": f'attachment; filename="sohbet-{oturum_id}.json"'},
        )

    # /compact (sohbet): eski mesajlar model ozetiyle degistirilir; son soru-cevap ham kalir.
    # Ozet uretilemezse sohbet DEGISMEZ. Rol sirasi korunur (kullanici/asistan donusumlu).
    @app.post("/api/oturumlar/{oturum_id}/ozetle")
    async def oturum_ozetle(oturum_id: str) -> dict:
        o = oturumlar.getir(oturum_id)
        son_kullanici = max(
            (i for i, m in enumerate(o.mesajlar) if m.rol == "kullanici"), default=0
        )
        eski = o.mesajlar[:son_kullanici]
        if len(eski) < 2:
            raise UygulamaHatasi("Ozetlenecek kadar eski mesaj yok.")
        dokum = "\n\n".join(f"{m.rol.upper()}: {m.metin[:4000]}" for m in eski if m.metin)
        try:
            async with yonetici.kullan() as llm:
                ozet = await llm.metin(
                    dokum[-48000:], sistem=OZET_TALIMATI, max_tokens=1200, dusunme="kapali"
                )
        except YerelLLMHatasi as e:
            raise UygulamaHatasi(f"Ozet uretilemedi: {e}") from e
        ozet = (ozet or "").strip()
        if not ozet:
            raise UygulamaHatasi("Model ozet uretmedi; sohbet degismedi.")
        guncel = oturumlar.getir(oturum_id)  # ozet surerken eklenen mesaj kaybolmasin
        guncel.mesajlar = [
            Mesaj(rol="kullanici", metin=f"[Önceki konuşmanın özeti]\n\n{ozet}"),
            Mesaj(rol="asistan", metin=OZET_ONAY),
            *guncel.mesajlar[son_kullanici:],
        ]
        oturumlar.kaydet(guncel)
        return {"ozetlenen": len(eski), "kalan": len(guncel.mesajlar), "ozet": ozet}

    # ---- hafiza (A4.4) ----
    @app.get("/api/hafiza")
    async def hafiza_listesi(kapsam: str | None = None) -> dict:
        return {"kayitlar": hafiza.liste(kapsam)}

    @app.post("/api/hafiza/ice-aktar")
    async def hafiza_ice_aktar(veri: dict) -> dict:
        """Grok Bot gibi: baska asistandan hafiza tasima (yapistirilan metin)."""
        metin = str(veri.get("metin") or "")[:100_000]
        return hafiza.ice_aktar(metin, str(veri.get("kaynak") or ""))

    @app.post("/api/hafiza")
    async def hafiza_ekle(istek: HafizaIstegi) -> dict:
        return hafiza.ekle(istek.metin, **istek.model_dump(exclude={"metin"}))

    @app.patch("/api/hafiza/{kayit_id}")
    async def hafiza_guncelle(kayit_id: str, degisiklik: dict) -> dict:
        return hafiza.guncelle(kayit_id, degisiklik)

    @app.delete("/api/hafiza/{kayit_id}")
    async def hafiza_sil(kayit_id: str) -> dict:
        return hafiza.sil(kayit_id)

    @app.get("/api/hafiza-disa-aktar")
    async def hafiza_disa_aktar() -> JSONResponse:
        return JSONResponse(
            hafiza.disa_aktar(),
            headers={"Content-Disposition": 'attachment; filename="hafiza.json"'},
        )

    # ---- review (A5.4) ----
    def _proje_git():
        alan = sohbet.aktif_alan()
        kayit = sohbet.ajan_araclari(alan)
        if kayit is None:
            raise UygulamaHatasi("Review icin once bir proje acin.")
        return alan, kayit

    @app.get("/api/review/diff")
    async def review_diff(staged: bool = False) -> dict:
        _, kayit = _proje_git()
        return await asyncio.to_thread(kayit.git.git_diff, "", staged)

    pr_onbellek: dict[tuple[str, str], tuple[float, dict | None]] = {}

    def _dal_pr(klasor: str, dal: str) -> dict | None:
        """Dalin PR'i (gh). Ag cagrisi: 5 dk onbellek; gh yok / giris yok / PR yok -> None."""
        kayit = pr_onbellek.get((klasor, dal))
        if kayit and time.monotonic() - kayit[0] < 300:
            return kayit[1]
        pr = None
        try:
            kod, cikti = sa.gh("pr", "view", "--json", "number,title,url,additions,deletions,state",
                               cwd=klasor, sure=15)  # fmt: skip
            pr = json.loads(cikti) if kod == 0 else None
        except (UygulamaHatasi, subprocess.TimeoutExpired, OSError, ValueError):
            pass
        pr_onbellek[(klasor, dal)] = (time.monotonic(), pr)
        return pr

    @app.get("/api/github/pr")
    async def github_pr(url: str) -> dict:
        """Sohbetteki PR linki icin kart bilgisi (gh). Yalniz github.com PR adresi kabul edilir."""
        if not PR_URL.fullmatch(url):
            raise UygulamaHatasi("Gecersiz PR adresi.")
        kayit = pr_onbellek.get(("url", url))
        if kayit and time.monotonic() - kayit[0] < 120:
            return kayit[1] or {}

        def _getir() -> dict | None:
            try:
                kod, cikti = sa.gh("pr", "view", url, "--json", PR_ALANLARI, sure=15)
                return json.loads(cikti) if kod == 0 else None
            except (UygulamaHatasi, subprocess.TimeoutExpired, OSError, ValueError):
                return None

        pr = await asyncio.to_thread(_getir)
        pr_onbellek[("url", url)] = (time.monotonic(), pr)
        return pr or {}

    @app.get("/api/proje/degisiklikler")
    async def proje_degisiklikler() -> dict:
        """Sag panel 'Degisiklikler': dal, commit edilmemis +/- ve varsa dalin PR'i."""
        kayit = sohbet.ajan_araclari(sohbet.aktif_alan())
        makine = {"bilgisayar": platform.node()}  # Claude Code'daki ortam satiri
        if kayit is None:
            return {"repo": False} | makine
        ozet = await asyncio.to_thread(kayit.git.git_ozet) | makine
        if ozet.get("klasor"):  # worktree'de .git bir dosyadir (ana depoya isaret eder)
            ozet["worktree"] = (Path(ozet["klasor"]) / ".git").is_file()
        if ozet["repo"] and ayarlar.oku().ag_acik:
            ozet["pr"] = await asyncio.to_thread(_dal_pr, ozet["klasor"], ozet["dal"])
        return ozet

    @app.post("/api/review")
    async def review_yap(staged: bool = False, derin: bool = False) -> dict:
        alan, kayit = _proje_git()
        d = await asyncio.to_thread(kayit.git.git_diff, "", staged)
        if d.get("hata"):
            raise UygulamaHatasi(d["hata"])
        diff = d.get("diff") or ""
        if not diff.strip():
            return {"ozet": "Incelenecek degisiklik yok (git diff bos).", "bulgular": [],
                    "dosyalar": [], "diff_kesildi": False}  # fmt: skip
        kural = rv.review_md_oku(alan.izinli_kokler) if alan.talimat_okunur_mu() else ""
        odaklar = list(rv.ODAKLAR) if derin else [None]  # derin: ayri baglamli odakli gecisler
        gecisler: dict[str, dict] = {}
        async with yonetici.kullan() as llm:
            for odak in odaklar:
                istem_ = rv.odakli_istem(diff, kural, odak) if odak else rv.istem(diff, kural)
                try:
                    cevap = await llm.json_cikti(
                        istem_, rv.SEMA, ad="review", max_tokens=3000, dusunme="kapali"
                    )
                except YerelLLMHatasi as e:
                    raise UygulamaHatasi(f"Review yapilamadi: {e}") from e
                gecisler[odak or "genel"] = cevap if isinstance(cevap, dict) else {}
        sonuc = rv.birlestir(gecisler, diff) if derin else rv.sonuclandir(gecisler["genel"], diff)
        sonuc["review_md"] = bool(kural)
        return sonuc

    # ---- plugin'ler (A7.4): karantina -> inceleme -> kur; scriptler calistirilmaz ----
    @app.get("/api/pluginler")
    async def plugin_listesi() -> dict:
        return {"pluginler": pluginler.liste()}

    @app.post("/api/pluginler/karantina")
    async def plugin_karantina(veri: dict) -> dict:
        return await asyncio.to_thread(
            pluginler.karantinaya_al, str(veri.get("yol", "")), str(veri.get("ad", ""))
        )

    @app.get("/api/pluginler/katalog")
    async def plugin_katalog() -> dict:
        return {"katalog": pluginler.katalog()}

    @app.post("/api/pluginler/katalog/{ad}")
    async def plugin_katalogdan(ad: str) -> dict:
        return await asyncio.to_thread(pluginler.katalogdan_karantina, ad)

    # ---- Claude Code plugin uyumlulugu ----
    cc_dur = threading.Event()  # kapanista arka plan esitlemesini keser

    def _cc_esitle() -> dict:
        try:
            o = pluginler.claude_code_esitle(cc_dur)
            logger.info("Claude Code plugin esitleme: {}", o)
            return o
        except Exception as e:  # noqa: BLE001 - acilisi bozmaz
            logger.warning("Claude Code plugin esitleme basarisiz: {}", e)
            return {"hata": str(e)}

    @app.post("/api/pluginler/claude-code/esitle")
    async def plugin_cc_esitle() -> dict:
        return await asyncio.to_thread(_cc_esitle)

    @app.get("/api/pluginler/claude-code")
    async def plugin_claude_code() -> dict:
        """Bu bilgisayardaki Claude Code'un kurulu plugin'leri (ice aktarmak icin)."""
        return {"pluginler": pluginler.claude_code_pluginleri()}

    @app.post("/api/pluginler/marketplace")
    async def plugin_marketplace(veri: dict) -> dict:
        return pluginler.marketplace(str(veri.get("kaynak", "")))

    @app.post("/api/pluginler/marketplace/kur")
    async def plugin_marketplace_karantina(veri: dict) -> dict:
        return await asyncio.to_thread(
            pluginler.marketplace_karantina, str(veri.get("kaynak", "")), str(veri.get("ad", ""))
        )

    @app.post("/api/pluginler/git")
    async def plugin_git(veri: dict) -> dict:
        return await asyncio.to_thread(
            pluginler.git_karantina, str(veri.get("url", "")), str(veri.get("ref", ""))
        )

    # Claude Code ozel slash komutlari: proje .claude/commands (YALNIZ guvenilir projede; proje
    # ayni adli kullanici komutunu ezer) + kullanici ~/.claude/commands. Govde modele MESAJ olarak
    # gider; komut dosyasi yetki vermez, '!`...`' kabuk on-calistirmasi yapilmaz.
    app.state.kullanici_komut_dizini = lambda: Path.home() / ".claude" / "commands"

    def ozel_komutlar() -> list[dict]:
        kaynaklar: list[tuple[str, Path]] = []
        alan = sohbet.aktif_alan()
        if alan.id != VARSAYILAN_ALAN_ID and alan.talimat_okunur_mu():
            kaynaklar += [("proje", Path(k) / ".claude" / "commands") for k in alan.kokler]
        kaynaklar.append(("kullanici", app.state.kullanici_komut_dizini()))
        out: list[dict] = []
        gorulen: set[str] = set()
        for kaynak, dizin in kaynaklar:
            for k in ccp.komut_dosyalari(dizin):
                if k["ad"] not in gorulen:
                    gorulen.add(k["ad"])
                    out.append({**k, "kaynak": kaynak, "kok": dizin})
        return out

    @app.get("/api/pluginler/komutlar")
    async def plugin_komutlari() -> dict:
        ozel = [
            {"komut": k["ad"], "kisa": k["ad"], "plugin": "", "kaynak": k["kaynak"],
             "aciklama": k["aciklama"], "ipucu": k["ipucu"]}
            for k in await asyncio.to_thread(ozel_komutlar)
        ]  # fmt: skip
        return {"komutlar": [*ozel, *pluginler.komutlar()]}

    @app.post("/api/pluginler/komut")
    async def plugin_komut(veri: dict) -> dict:
        komut, arg = str(veri.get("komut", "")), str(veri.get("arg", ""))[:4000]
        for k in await asyncio.to_thread(ozel_komutlar):
            if k["ad"] == komut:
                istem = ccp.komut_genislet(k["govde"], arg, k["kok"])
                return {"plugin": "", "kaynak": k["kaynak"], "komut": komut, "istem": istem}
        return pluginler.komut_genislet(komut, arg)

    @app.put("/api/pluginler/{ad}/bilesen")
    async def plugin_bilesen(ad: str, veri: dict) -> dict:
        return pluginler.bilesen_ac(ad, str(veri.get("tur", "")), bool(veri.get("acik")))

    @app.post("/api/pluginler/kur")
    async def plugin_kur(veri: dict) -> dict:
        return await asyncio.to_thread(pluginler.kur, str(veri.get("karantina", "")))

    @app.post("/api/pluginler/{ad}/geri-al")
    async def plugin_geri_al(ad: str) -> dict:
        return pluginler.geri_al(ad)

    @app.put("/api/pluginler/{ad}/durum")
    async def plugin_durum(ad: str, veri: dict) -> dict:
        return pluginler.ac_kapat(ad, bool(veri.get("acik")))

    @app.delete("/api/pluginler/{ad}")
    async def plugin_kaldir(ad: str) -> dict:
        pluginler.kaldir(ad)
        return {"silindi": ad}

    # ---- tarayici acil durdurma (A9.6): ajan calisirken bile hemen kapatir ----
    @app.post("/api/tarayici/kapat")
    async def tarayici_kapat() -> dict:
        return await asyncio.to_thread(sohbet.tarayici.kapat)

    @app.get("/api/koordinasyon")
    async def koordinasyon_durumu() -> dict:
        """Sag panel 'Koordinasyon' (aktif proje) + kenar cubugu rozetleri (tum projeler)."""
        return {"proje": koord.KOORD.aktifler(sohbet.aktif_alan().id), "tum": koord.KOORD.tumu()}

    @app.put("/api/tarayici/panel")
    async def tarayici_paneli(istek: dict) -> dict:
        """Arayuzdeki tarayici panelinin adresi; modele sistem notu olarak gider (bos = kapali)."""
        adres = str(istek.get("adres", "")).strip()[:2000]
        u = urlsplit(adres)
        if adres and (u.scheme not in ("http", "https") or not u.hostname or u.username):
            raise UygulamaHatasi("Gecersiz adres.")
        sohbet.tarayici_paneli = adres
        return {"adres": adres}

    @app.get("/api/tarayici")
    async def tarayici_durum() -> dict:
        return {"acik": sohbet.tarayici.acik_mi(), "playwright": playwright_var()}

    # ---- masaustu acil durdurma (A9.6) ----
    @app.post("/api/masaustu/durdur")
    async def masaustu_durdur() -> dict:
        return sohbet.masaustu.durdur()

    @app.post("/api/masaustu/devam")
    async def masaustu_devam() -> dict:
        return sohbet.masaustu.devam()

    # ---- /doctor (A10.7): sir degerleri gosterilmez ----
    @app.get("/api/doctor")
    async def doktor_tani() -> dict:
        from app.doktor import tani

        a = ayarlar.oku()
        sonuc = await asyncio.to_thread(
            tani, veri_dizini, Path(a.llm_dizin), openrouter.anahtar_durumu()["var"]
        )
        return {"kontroller": sonuc}

    # ---- uzantilar (A7.6): ayri surec, yalniz ilan edilen yetenek, arac her zaman onay ----
    @app.get("/api/uzantilar")
    async def uzanti_listesi() -> dict:
        return {"uzantilar": uzantilar.liste(), "komutlar": uzantilar.komut_listesi()}

    @app.post("/api/uzantilar/karantina")
    async def uzanti_karantina(veri: dict) -> dict:
        yol = str(veri.get("yol", "")).strip()
        if yol.startswith("https://"):  # Mods gibi: git adresinden (hook kapali, calistirilmaz)
            return await asyncio.to_thread(uzantilar.git_karantina, yol)
        return await asyncio.to_thread(uzantilar.karantinaya_al, yol)

    @app.get("/api/uzantilar/ui")
    async def uzanti_ui() -> dict:
        """Mods UI yuzeyleri: durum cubugu metni, bildirim (toast), istem ustu bant."""
        return {"yuzeyler": await asyncio.to_thread(uzantilar.ui)}

    @app.post("/api/uzantilar/kur")
    async def uzanti_kur(veri: dict) -> dict:
        return await asyncio.to_thread(uzantilar.kur, str(veri.get("ad", "")))

    @app.put("/api/uzantilar/{ad}/durum")
    async def uzanti_durum(ad: str, veri: dict) -> dict:
        return uzantilar.ac_kapat(ad, bool(veri.get("acik")))

    @app.delete("/api/uzantilar/{ad}")
    async def uzanti_kaldir(ad: str) -> dict:
        uzantilar.kaldir(ad)
        return {"silindi": ad}

    @app.post("/api/uzantilar/komut")
    async def uzanti_komut(veri: dict) -> dict:
        return await asyncio.to_thread(
            uzantilar.komut, str(veri.get("komut", "")), str(veri.get("arg", ""))
        )

    @app.get("/api/uzantilar/{ad}/panel")
    async def uzanti_panel(ad: str) -> dict:
        p = await asyncio.to_thread(uzantilar.panel, ad)
        return {**p, "csp": ONIZLEME_CSP}

    # ---- MCP (A7): sunucular yalniz oturumlu arayuzden; sirlar maskeli doner ----
    oauth_bekleyen: dict[str, dict] = {}  # state -> {ad, ...}; 10 dk gecerli, tek kullanimlik

    @app.post("/api/mcp/{ad}/oauth")
    async def mcp_oauth_baslat(ad: str, istek: Request) -> dict:
        s = next((x for x in mcp.liste() if x.ad == ad), None)
        if s is None or not s.url:
            raise UygulamaHatasi("OAuth girisi yalniz uzak (URL) baglayicilar icin.")
        geri = str(istek.base_url).rstrip("/") + "/api/mcp/oauth/geri"

        def _baslat() -> tuple[str, dict]:
            with httpx.Client(timeout=mcp_oauth.ZAMAN) as c:
                return mcp_oauth.baslat(s.url, geri, c, s.oauth.get("client_id", ""))

        adres, b = await asyncio.to_thread(_baslat)
        simdi = time.time()
        for k in [k for k, v in oauth_bekleyen.items() if simdi - v["zaman"] > 600]:
            oauth_bekleyen.pop(k)
        oauth_bekleyen[b["durum"]] = b | {"ad": ad}
        await asyncio.to_thread(webbrowser.open, adres)
        return {"adres": adres}

    @app.get("/api/mcp/oauth/geri")
    async def mcp_oauth_geri(state: str = "", code: str = "", error: str = "") -> Response:
        b = oauth_bekleyen.pop(state, None)
        if b is None or time.time() - b["zaman"] > 600:
            sonuc = "Gecersiz ya da suresi dolmus giris istegi."
        elif error or not code:
            sonuc = f"Giris iptal edildi: {error or 'kod yok'}"
        else:
            try:

                def _tamamla() -> dict:
                    with httpx.Client(timeout=mcp_oauth.ZAMAN) as c:
                        return mcp_oauth.tamamla(b, code, c)

                mcp.oauth_kaydet(b["ad"], await asyncio.to_thread(_tamamla))
                sonuc = f"'{b['ad']}' baglayicisina giris yapildi. Bu sekmeyi kapatabilirsin."
            except UygulamaHatasi as e:
                sonuc = str(e)
        govde = (
            "<!doctype html><meta charset=utf-8><title>Kairo</title>"
            f"<body style='font:16px system-ui;padding:40px'>{sonuc.replace('<', '&lt;')}</body>"
        )
        return Response(govde, media_type="text/html; charset=utf-8")

    @app.get("/api/mcp/ice-aktar")
    async def mcp_bulunanlar() -> dict:
        """Claude Code / Claude Desktop'taki baglayicilar + hazir dizin (yalniz okunur)."""
        var = {s.ad for s in mcp.liste()}
        bulunan = await asyncio.to_thread(mcp_ice.bul)
        return {"bulunan": [b | {"var": b["ad"] in var} for b in bulunan],
                "dizin": [d | {"var": d["ad"] in var} for d in mcp_ice.DIZIN]}  # fmt: skip

    @app.post("/api/mcp/ice-aktar")
    async def mcp_ice_aktar(veri: dict) -> dict:
        istenen = set(veri.get("anahtarlar") or [])
        eklenen, hatalar = [], []
        for b in await asyncio.to_thread(mcp_ice.bul):
            if b["anahtar"] not in istenen:
                continue
            try:
                mcp.ekle(b["veri"])
                eklenen.append(b["ad"])
            except (UygulamaHatasi, ValueError) as e:
                hatalar.append(f"{b['ad']}: {str(e)[:120]}")
        return {"eklenen": eklenen, "hatalar": hatalar}

    # ---- arac paketleri: surumu/ozeti sabit hazir arac setleri (REA, Craft Anything) ----
    # Kurulum YALNIZ oturumlu arayuzden; adres/surum istekten ALINMAZ (tablo sabit).
    app.state.arac_paketleri = arac_paketleri  # testler sahte kurucu baglar

    @app.get("/api/arac-paketleri")
    async def arac_paketi_listesi() -> dict:
        return {"paketler": await asyncio.to_thread(app.state.arac_paketleri.liste)}

    @app.post("/api/arac-paketleri/{ad}/kur")
    async def arac_paketi_kur(ad: str) -> dict:
        return await asyncio.to_thread(app.state.arac_paketleri.kur, ad)

    @app.delete("/api/arac-paketleri/{ad}")
    async def arac_paketi_kaldir(ad: str) -> dict:
        return await asyncio.to_thread(app.state.arac_paketleri.kaldir, ad)

    @app.get("/api/mcp")
    async def mcp_listesi() -> dict:
        # rozet: her bagliyicinin canli durumu (bagli/baglaniyor/hata/kapali); plugin ve Composio
        # gibi ek kaynaklar da listelenir ama "ek" isaretlidir (ayarlari kendi yerinden yonetilir)
        durum = await asyncio.to_thread(mcp.durumlar)
        kendi = {s.ad for s in mcp.liste()}
        return {"sunucular": [
            {**s.disari(), "ek": s.ad not in kendi, "baglanti": durum.get(s.ad, {})}
            for s in mcp.tum()
        ]}  # fmt: skip

    @app.post("/api/github/baglan")
    async def github_baglan(kontrol: bool = False) -> dict:
        """GitHub'a token yapistirmadan baglanir (openbot'un cihaz kodu girisi gibi).

        GitHub CLI'nin kendi tarayici/cihaz kodu girisi kullanilir; token yalniz backend'de
        MCP basligina yazilir, arayuze ve modele gitmez."""
        gh = shutil.which("gh") or next(
            (str(p) for p in [Path(os.environ.get("PROGRAMFILES", "")) / "GitHub CLI" / "gh.exe"]
             if p.is_file()), None,
        )  # fmt: skip
        if not gh:
            return {"durum": "gh_yok", "komut": "winget install --id GitHub.cli -e"}

        def _token() -> str:
            r = subprocess.run(
                [gh, "auth", "token", "-h", "github.com"],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )  # fmt: skip
            return r.stdout.strip() if r.returncode == 0 else ""

        token = await asyncio.to_thread(_token)
        if not token and kontrol:  # bekleme dongusu: yeni pencere acma
            return {"durum": "giris_bekliyor"}
        if not token:
            # Giris penceresi: tek seferlik kod gosterir ve tarayiciyi acar; kullanici tamamlar
            subprocess.Popen(
                [gh, "auth", "login", "-h", "github.com", "-p", "https", "-w", "-s",
                 "repo,read:org,gist"],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )  # fmt: skip
            return {"durum": "giris_bekliyor"}
        # aktif: onceden kapatilmis kayit token yazilinca da kapali kaliyordu ("giris gelmiyor")
        veri = {"ad": "github", "url": "https://api.githubcopilot.com/mcp/", "aktif": True,
                "basliklar": {"Authorization": f"Bearer {token}"}}  # fmt: skip
        if any(x.ad == "github" for x in mcp.liste()):
            mcp.guncelle("github", veri)
        else:
            mcp.ekle(veri)
        return {"durum": "bagli"}

    @app.post("/api/mcp")
    async def mcp_ekle(veri: dict) -> dict:
        return mcp.ekle(veri)

    @app.put("/api/mcp/{ad}")
    async def mcp_guncelle(ad: str, veri: dict) -> dict:
        return mcp.guncelle(ad, veri)

    @app.delete("/api/mcp/{ad}")
    async def mcp_sil(ad: str) -> dict:
        mcp.sil(ad)
        return {"silindi": ad}

    @app.post("/api/mcp/{ad}/test")
    async def mcp_test(ad: str) -> dict:
        return await asyncio.to_thread(mcp.test, ad)

    # ---- hooks (A6.4-5): yalniz oturumlu arayuzden eklenir; model/skill/proje ekleyemez ----
    @app.get("/api/hooks")
    async def hook_listesi() -> dict:
        return {"hooks": [h.model_dump() for h in hooklar.liste()], "olaylar": list(HOOK_OLAYLARI)}

    @app.post("/api/hooks")
    async def hook_ekle(veri: dict) -> dict:
        return hooklar.ekle(veri).model_dump()

    @app.put("/api/hooks/{hook_id}")
    async def hook_guncelle(hook_id: str, veri: dict) -> dict:
        return hooklar.guncelle(hook_id, veri).model_dump()

    @app.delete("/api/hooks/{hook_id}")
    async def hook_sil(hook_id: str) -> dict:
        hooklar.sil(hook_id)
        return {"silindi": hook_id}

    @app.post("/api/hooks/{hook_id}/test")
    async def hook_test(hook_id: str) -> dict:
        return await asyncio.to_thread(hooklar.test_et, hook_id)

    # ---- model yetenegi (A4.7) ----
    @app.get("/api/model/yetenek")
    async def model_yetenek() -> dict:
        return model_yetenegi().model_dump()

    @app.patch("/api/oturumlar/{oturum_id}")
    async def oturum_adlandir(oturum_id: str, istek: AdIstegi) -> dict:
        return oturumlar.yeniden_adlandir(oturum_id, istek.baslik).model_dump()

    @app.post("/api/oturumlar/{oturum_id}/ajan-run")
    async def oturum_ajan_run(oturum_id: str, istek: AjanRunKaydi) -> dict:
        o = oturumlar.ajan_run_ekle(oturum_id, istek.run, istek.metin)
        return {"ajan_runlari": o.ajan_runlari}

    @app.delete("/api/oturumlar/{oturum_id}")
    async def oturum_sil(oturum_id: str) -> dict:
        oturumlar.sil(oturum_id)
        return {"silindi": oturum_id}

    @app.post("/api/oturumlar/{oturum_id}/mesaj")
    async def mesaj(oturum_id: str, istek: MesajIstegi) -> StreamingResponse:
        oturumlar.getir(oturum_id)  # yoksa 404 (akis baslamadan)

        async def izlenen() -> AsyncIterator[dict]:
            akistaki.add(oturum_id)
            try:
                async for olay in sohbet.mesaj_gonder(oturum_id, istek):
                    yield olay
            finally:
                akistaki.discard(oturum_id)

        return sse(izlenen())

    # ---- ekler ----
    @app.post("/api/ekler")
    async def ek_yukle(dosya: UploadFile) -> dict:
        """Akista parca parca okur: sinir asilinca hemen keser, RAM'e tum dosya alinmaz (A0.7)."""
        ad = dosya.filename or "dosya"
        ekler_modulu.tur_bul(ad)  # desteklenmeyen uzanti: dosya hic okunmadan reddedilir
        parcalar: list[bytes] = []
        toplam = 0
        while parca := await dosya.read(UPLOAD_PARCA_BAYT):
            toplam += len(parca)
            if toplam > ekler_modulu.MAX_BOYUT:
                mb = ekler_modulu.MAX_BOYUT / (1024 * 1024)
                raise GecersizEk(f"Dosya {mb:.0f} MB sinirindan buyuk; yukleme durduruldu.")
            parcalar.append(parca)
        return ekler.kaydet(ad, b"".join(parcalar)).model_dump(exclude={"metin"})

    # ---- ses dikte (A5.7): YALNIZ yerel ses destekli model; buluta ses gonderilmez ----
    def dikte_durumu() -> dict:
        a = ayarlar.oku()
        # bulut dikte + anahtar: ayri dikte modeli (sohbet saglayicisindan bagimsiz)
        if a.dikte_bulut and openrouter.anahtar():
            m = a.dikte_model or a.or_model
            if not (openrouter.model_bilgisi(m) or {}).get("ses"):
                return {"kullanilabilir": False, "model": m, "neden": DIKTE_UZAK_SESSIZ}
            return {
                "kullanilabilir": True, "model": m, "neden": "", "max_sn": DIKTE_MAX_SN,
                "bulut": True,
            }  # fmt: skip
        if a.saglayici == "openrouter" and a.or_model:
            return {"kullanilabilir": False, "model": a.or_model, "neden": DIKTE_UZAK}
        p = MODELLER.get(a.model)
        if p is None or not p.ses:
            return {"kullanilabilir": False, "model": a.model, "neden": DIKTE_SESSIZ}
        return {"kullanilabilir": True, "model": a.model, "neden": "", "max_sn": DIKTE_MAX_SN}

    @app.get("/api/dikte/durum")
    async def dikte_durum() -> dict:
        return dikte_durumu()

    @app.post("/api/dikte")
    async def dikte(ses: UploadFile) -> dict:
        d = dikte_durumu()
        if not d["kullanilabilir"]:
            raise UygulamaHatasi(d["neden"])
        veri = await ses.read(DIKTE_MAX_BAYT + 1)
        if len(veri) > DIKTE_MAX_BAYT:
            raise UygulamaHatasi(f"Kayit en fazla {DIKTE_MAX_SN} saniye olabilir.")
        if veri[:4] != b"RIFF" or veri[8:12] != b"WAVE":
            raise UygulamaHatasi("Ses WAV biciminde olmali.")
        bas = time.perf_counter()
        async with yonetici.kullan(d["model"]) as llm:
            metin = await llm.ses(
                veri,
                DIKTE_TALIMATI,
                bicim="wav",
                dusunme="kapali",
                max_tokens=512,
            )
        return {"metin": metin.strip(), "sure_sn": round(time.perf_counter() - bas, 1)}

    @app.get("/api/ekler/{ek_id}")
    async def ek_getir(ek_id: str) -> FileResponse:
        ek = ekler.getir(ek_id)
        return FileResponse(ekler.yol(ek), media_type=ek.mime, filename=ek.ad)

    @app.post("/api/ekler/ornek-belge")
    async def ek_ornek() -> dict:
        ek = ekler.kaydet("ornek-hakedis.png", ornek_belge())
        return {**ek.model_dump(exclude={"metin"}), "beklenen": "\n".join(ORNEK_SATIRLAR)}

    # ---- model magazasi (Hugging Face) ----
    def _sistem_bilgisi() -> dict:
        b = sistem.bellek()
        return {
            "toplam_ram_gb": b.get("toplam_gb"),
            "bos_ram_gb": b.get("bos_gb"),
            "disk_bos_gb": indirici.disk_bos_gb(),
            "model_klasoru": str(indirici.model_klasoru),
        }

    @app.get("/api/magaza/ara")
    async def magaza_ara(q: str = "", imlec: str = "") -> dict:
        """Bos q = tum GGUF modelleri; filtre/siralama arayuzde (yuklenen sayfalar uzerinde)."""
        s = _sistem_bilgisi()
        bellek = {"toplam_gb": s["toplam_ram_gb"], "bos_gb": s["bos_ram_gb"]}
        yuklu = {p.dosya for p in MODELLER.values()}
        adaylar, sonraki = await magaza.ara(q, imlec=imlec[:500])
        sonuclar = [
            a | {
                "uyumluluk": uyumluluk(a["tahmini_gb"], bellek, s["disk_bos_gb"]),
                "yuklu": a["model_dosyasi"] in yuklu,
            }
            for a in adaylar
        ]  # fmt: skip
        return {"sistem": s, "sonuclar": sonuclar, "sonraki": sonraki}

    @app.get("/api/magaza/yuklu")
    async def magaza_yuklu() -> dict:
        klasor = indirici.model_klasoru / "models"
        liste = []
        for p in MODELLER.values():
            dosyalar = [klasor / d for d in (p.dosya, p.mmproj) if d]
            boyut = sum(d.stat().st_size for d in dosyalar if d.exists())
            liste.append(
                {
                    "anahtar": p.anahtar,
                    "ad": p.ad,
                    "aciklama": p.aciklama,
                    "ses": p.ses,
                    "gorsel": bool(p.mmproj) and (klasor / p.mmproj).exists(),
                    "dosya_var": (klasor / p.dosya).exists(),
                    "boyut_gb": round(boyut / 1024**3, 1),
                    "yerlesik": p.anahtar in kayit.yerlesik,
                    "repo": kayit.kaynak(p.anahtar),
                    "acik": yonetici.yuklenen_model == p.anahtar,
                }
            )
        return {"sistem": _sistem_bilgisi(), "modeller": liste}

    @app.delete("/api/magaza/yuklu/{anahtar}")
    async def magaza_sil(anahtar: str) -> dict:
        if yonetici.yuklenen_model == anahtar:
            await yonetici.durdur()  # acik modelin dosyasi silinemez
        return indirici.sil(anahtar)

    @app.post("/api/magaza/indir")
    async def magaza_indir(istek: IndirIstegi) -> dict:
        return (await indirici.baslat(istek.repo)).ozet()

    @app.get("/api/magaza/indirmeler")
    async def magaza_indirmeler() -> list[dict]:
        return [i.ozet() for i in indirici.indirmeler.values()]

    @app.post("/api/magaza/indirmeler/{indirme_id}/iptal")
    async def magaza_iptal(indirme_id: str) -> dict:
        indirici.iptal(indirme_id)
        return {"iptal": indirme_id}

    # ---- Ollama: saglayici + model magazasi ----
    @app.get("/api/ollama/durum")
    async def ollama_durum() -> dict:
        return await ollama.durum()

    @app.post("/api/ollama/baslat")
    async def ollama_baslat() -> dict:
        return await ollama.baslat()

    @app.get("/api/ollama/yuklu")
    async def ollama_yuklu() -> dict:
        return {"sistem": _sistem_bilgisi(), "modeller": await ollama.yuklu()}

    @app.get("/api/ollama/detay")
    async def ollama_detay(ad: str) -> dict:
        return await ollama.detay(ad[:200])

    @app.delete("/api/ollama/yuklu")
    async def ollama_sil(ad: str) -> dict:
        a = ayarlar.oku()
        sonuc = await ollama.sil(ad[:200])
        if a.ollama_model == ad:  # secili model silindi: sessizce baska modele gecilmez
            ayarlar.guncelle({"ollama_model": ""})
        return sonuc

    @app.get("/api/ollama/ara")
    async def ollama_ara(
        q: str = "", sayfa: int = 1, sira: str = "popular", yetenek: str = ""
    ) -> dict:
        v = await ollama.ara(q[:100], sayfa, sira, yetenek)
        return v | {"sistem": _sistem_bilgisi()}

    @app.get("/api/ollama/etiketler")
    async def ollama_etiketler(ad: str) -> dict:
        s = _sistem_bilgisi()
        bellek = {"toplam_gb": s["toplam_ram_gb"], "bos_gb": s["bos_ram_gb"]}
        yuklu = {m["ad"] for m in await ollama.yuklu()} if await ollama.surum() else set()
        return {"etiketler": [
            e | {"uyumluluk": uyumluluk(e["boyut_gb"], bellek, s["disk_bos_gb"]),
                 "yuklu": e["tam_ad"] in yuklu or (e["etiket"] == "latest" and ad in yuklu)}
            for e in await ollama.etiketler(ad[:100])
        ]}  # fmt: skip

    @app.post("/api/ollama/indir")
    async def ollama_indir(istek: OllamaIndirIstegi) -> dict:
        return (await ollama.indir(istek.ad)).ozet()

    @app.get("/api/ollama/indirmeler")
    async def ollama_indirmeler() -> list[dict]:
        return [i.ozet() for i in ollama.indirmeler.values()]

    @app.post("/api/ollama/indirmeler/{indirme_id}/iptal")
    async def ollama_iptal(indirme_id: str) -> dict:
        ollama.iptal(indirme_id)
        return {"iptal": indirme_id}

    # ---- talimatlar ve skill'ler ----
    @app.get("/api/talimatlar")
    async def talimat_oku() -> dict:
        a = ayarlar.oku()
        kaynaklar = talimatlar.kaynaklar(claude=True, uygulama=True)
        kisa = lambda tur: [{**k, "metin": k["metin"][:4000]} for k in kaynaklar if k["tur"] == tur]  # noqa: E731
        return {
            "kairo": kisa("uygulama"),  # KAIRO.md + importlari (BRAIN-POLICY)
            "claude": kisa("claude"),  # ~/.claude/CLAUDE.md'den yalniz KAIRO.md'de olmayanlar
            "claude_acik": a.claude_talimatlari,
            "uygulama": talimatlar.uygulama_oku(),
            "uygulama_acik": a.uygulama_talimati,
            "uygulama_yol": str(talimatlar.uygulama_yolu),
            "baglam_token": a.baglam_token,
        }

    @app.put("/api/talimatlar")
    async def talimat_yaz(istek: TalimatIstegi) -> dict:
        return {"uygulama": talimatlar.uygulama_yaz(istek.metin)}

    @app.get("/api/skiller")
    async def skill_liste() -> dict:
        kapali = set(ayarlar.oku().kapali_skiller)
        liste = [{**s.ozet(), "acik": s.ad not in kapali} for s in skiller.kesfet()]
        return {
            "skiller": liste,
            "kaynaklar": [
                {"kaynak": k, "yol": str(p), "var": p.is_dir()} for k, p in skiller.kaynak_listesi
            ],
        }

    # ---- GitHub'dan skill: indir -> karantina -> kural + Claude Code denetimi -> onayla kur ----
    from app.services.skill_ice import SkillIceAktarici

    skill_ice = app.state.skill_ice = SkillIceAktarici(veri_dizini, skiller)

    @app.post("/api/skill-ice")
    async def skill_ice_indir(istek: SkillIceIstegi) -> dict:
        return skill_ice.disari(await asyncio.to_thread(skill_ice.indir, istek.url))

    @app.post("/api/skill-ice/{iid}/denetle")
    async def skill_ice_denetle(iid: str, istek: SkillIceAdIstegi) -> dict:
        return await asyncio.to_thread(skill_ice.denetle, iid, istek.ad)

    @app.post("/api/skill-ice/{iid}/kur")
    async def skill_ice_kur(iid: str, istek: SkillIceKurIstegi) -> dict:
        return await asyncio.to_thread(
            skill_ice.kur, iid, istek.adlar, istek.riskli_onay, istek.yeni_adlar
        )

    @app.delete("/api/skill-ice/{iid}")
    async def skill_ice_iptal(iid: str) -> dict:
        return await asyncio.to_thread(skill_ice.iptal, iid)

    @app.get("/api/skiller/{ad}")
    async def skill_getir(ad: str) -> dict:
        s = skiller.getir(ad)
        return {**s.ozet(), "icerik": s.dosya.read_text(encoding="utf-8", errors="replace")[:20000]}

    @app.post("/api/skiller")
    async def skill_ekle(istek: SkillIstegi) -> dict:
        return skiller.olustur(
            istek.ad, istek.aciklama, istek.icerik, istek.surum, istek.gereken_araclar
        ).ozet()

    @app.put("/api/skiller/{ad}")
    async def skill_guncelle(ad: str, istek: SkillIstegi) -> dict:
        return skiller.guncelle(
            ad, istek.aciklama, istek.icerik, istek.surum, istek.gereken_araclar
        ).ozet()

    @app.get("/api/skiller/{ad}/test")
    async def skill_test(ad: str) -> dict:
        """Modelin gorecegi sonuc: bozuk mu, hangi araclari istiyor, hangileri su an yok."""
        a = ayarlar.oku()
        sistem_, araclar_, _, _ = sohbet.baglam_hazirla(a, "", [])
        mevcut = {x["function"]["name"] for x in araclar_}
        isl = skl.arac_isleyicileri(skiller, set(a.kapali_skiller), lambda: mevcut)
        return {"skill": skiller.getir(ad).ozet(), "model_gorur": isl["skill_kullan"](ad)}

    @app.delete("/api/skiller/{ad}")
    async def skill_sil(ad: str) -> dict:
        skiller.sil(ad)
        return {"silindi": ad}

    @app.put("/api/skiller/{ad}/durum")
    async def skill_durum(ad: str, istek: SkillDurumIstegi) -> dict:
        skiller.getir(ad)
        kapali = set(ayarlar.oku().kapali_skiller)
        kapali = kapali - {ad} if istek.acik else kapali | {ad}
        ayarlar.guncelle({"kapali_skiller": sorted(kapali)})
        return {"ad": ad, "acik": istek.acik}

    # ---- testler ----
    @app.post("/api/karsilastir")
    async def karsilastir(istek: KarsilastirmaIstegi) -> StreamingResponse:
        return sse(testler.karsilastir(istek))

    @app.post("/api/ocr")
    async def ocr(istek: OcrIstegi) -> StreamingResponse:
        ekler.getir(istek.ek_id)
        return sse(testler.ocr(istek))

    @app.get("/api/araclar")
    async def araclar() -> dict:
        return {"araclar": ARACLAR, "ornekler": ORNEK_ISTEMLER}

    @app.post("/api/arac-testi")
    async def arac_testi(istek: AracIstegi) -> StreamingResponse:
        return sse(testler.arac(istek))

    @app.post("/api/test-paketi")
    async def test_paketi(istek: PaketIstegi) -> StreamingResponse:
        return sse(testler.paket(istek))

    # ---- projeler / calisma alani (A1.1) ----
    @app.get("/api/projeler")
    async def proje_listesi() -> dict:
        aktif = projeler.aktif()
        return {
            "alanlar": [a.model_dump(mode="json") for a in projeler.liste()],
            "aktif": aktif.model_dump(mode="json") if aktif else None,
            "etkin": sohbet.aktif_alan().model_dump(mode="json"),
            "modlar": [str(m) for m in Mod],
            "guvenler": [str(g) for g in Guven],
        }

    # Sag panel dosya gezgini (Claude Code Desktop gibi): yalniz etkin projenin izinli kokleri,
    # gizli/hassas ve .gitignore'daki dosyalar ajanin okuma araciyla ayni kurala gore elenir.
    def _okuyucu() -> AjanDosyaAraclari:
        return AjanDosyaAraclari(KokKapsami(sohbet.aktif_alan().izinli_kokler))

    @app.get("/api/proje/dosyalar")
    async def proje_dosyalar(yol: str = "") -> dict:
        r = await asyncio.to_thread(_okuyucu().klasor_listele, yol, 1)
        if "hata" in r:
            raise UygulamaHatasi(r["hata"])
        return {"klasor": r["klasor"], "ogeler": [
            {"ad": o.removeprefix("[klasor] "), "klasor": o.startswith("[klasor] ")}
            for o in r["ogeler"]]}  # fmt: skip

    @app.get("/api/proje/dosya")
    async def proje_dosya(yol: str) -> dict:
        r = await asyncio.to_thread(_okuyucu().dosya_oku, yol, 1, 2000)
        if "hata" in r:
            raise UygulamaHatasi(r["hata"])
        return r

    @app.post("/api/projeler")
    async def proje_ac(istek: ProjeIstegi) -> dict:
        a = ayarlar.oku()
        varsayilan = (a.varsayilan_koordinator, a.varsayilan_uygulayici)
        return projeler.ac(istek.yol, istek.ad, istek.guven, varsayilan).model_dump(mode="json")

    @app.post("/api/projeler/{alan_id}/etkin")
    async def proje_etkin(alan_id: str) -> dict:
        # Projeye ait sohbet acilinca o proje etkin olur; kisisel alan = proje kapali
        if alan_id == VARSAYILAN_ALAN_ID:
            projeler.kapat()
        else:
            projeler.etkinlestir(alan_id)
        return {"etkin": sohbet.aktif_alan().model_dump(mode="json")}

    @app.post("/api/projeler/kapat")
    async def proje_kapat() -> dict:
        projeler.kapat()
        return {"aktif": None, "etkin": sohbet.aktif_alan().model_dump(mode="json")}

    @app.delete("/api/projeler/{alan_id}")
    async def proje_sil(alan_id: str) -> dict:
        """Projeyi Kairo'dan kaldirir + ona bagli sohbetleri siler. Diskteki dosyalara DOKUNMAZ."""
        projeler.sil(alan_id)  # yoksa 404; sohbetler ancak proje gercekten varsa silinir
        return {"silindi": alan_id, "silinen_sohbet": alan_sohbetlerini_sil(alan_id)}

    def alan_sohbetlerini_sil(alan_id: str) -> int:
        bagli = [o["id"] for o in oturumlar.liste() if o.get("alan", "") == alan_id]
        for oid in bagli:
            with contextlib.suppress(Bulunamadi):
                oturumlar.sil(oid)
        return len(bagli)

    @app.delete("/api/oturumlar/grup/{grup}")
    async def proje_disi_sohbetleri_sil(grup: Literal["projesiz", "kisisel"]) -> dict:
        alan_id = VARSAYILAN_ALAN_ID if grup == "kisisel" else ""
        return {"silinen_sohbet": alan_sohbetlerini_sil(alan_id)}

    @app.put("/api/projeler/{alan_id}/mod")
    async def proje_mod(alan_id: str, istek: ModIstegi) -> dict:
        return projeler.mod_ayarla(alan_id, istek.mod).model_dump(mode="json")

    @app.put("/api/projeler/{alan_id}/modeller")
    async def proje_modeller(alan_id: str, istek: ModellerIstegi) -> dict:
        if ayarlar.oku().saglayici == "openrouter":
            for m in (istek.koordinator_model, istek.uygulayici_model):
                if m.strip() in MODELLER:  # kullan() bunu her mesajda reddederdi; burada soyle
                    raise UygulamaHatasi(f"OpenRouter seçili; yerel model ({m}) kullanılamaz.")
        return projeler.modeller_ayarla(
            alan_id, istek.koordinator_model, istek.uygulayici_model
        ).model_dump(mode="json")

    @app.put("/api/projeler/{alan_id}/guven")
    async def proje_guven(alan_id: str, istek: GuvenIstegi) -> dict:
        return projeler.guven_ayarla(alan_id, istek.guven).model_dump(mode="json")

    @app.post("/api/projeler/{alan_id}/kok")
    async def proje_kok_ekle(alan_id: str, istek: YolIstegi) -> dict:
        return projeler.kok_ekle(alan_id, istek.yol).model_dump(mode="json")

    @app.post("/api/projeler/{alan_id}/klasor")
    async def proje_klasor(alan_id: str, istek: YolIstegi) -> dict:
        return projeler.klasor_yetkilendir(alan_id, istek.yol).model_dump(mode="json")

    # ---- izinler ve onaylar (A1.3, A1.4) ----
    @app.get("/api/izinler")
    async def izinler() -> dict:
        alan = sohbet.aktif_alan()
        return {**politika.bilgi(alan), "alan": alan.model_dump(mode="json")}

    @app.get("/api/onaylar")
    async def onay_gecmisi() -> dict:
        return {"onaylar": politika.onaylar.gecmis()}

    # ---- Composio: yuzlerce uygulamaya OAuth ile tek tikla baglanti ----
    @app.get("/api/composio")
    async def composio_durum() -> dict:
        return composio.durum()

    @app.post("/api/composio/anahtar")
    async def composio_anahtar(veri: dict) -> dict:
        return await asyncio.to_thread(composio.anahtar_kaydet, str(veri.get("anahtar", "")))

    @app.delete("/api/composio/anahtar")
    async def composio_anahtar_sil() -> dict:
        return composio.anahtar_sil()

    @app.get("/api/composio/uygulamalar")
    async def composio_uygulamalar(arama: str = "", bagli: bool | None = None,
                                   imlec: str = "") -> dict:  # fmt: skip
        return await asyncio.to_thread(composio.uygulamalar, arama, bagli, imlec)

    @app.post("/api/composio/baglan/{toolkit}")
    async def composio_baglan(toolkit: str) -> dict:
        """Onay adresini sistem tarayicisinda acar (pywebview icinde OAuth acilmaz)."""
        sonuc = await asyncio.to_thread(composio.baglan, toolkit)
        import webbrowser

        await asyncio.to_thread(webbrowser.open, sonuc["adres"])
        return sonuc

    @app.delete("/api/composio/baglanti/{baglanti_id}")
    async def composio_baglanti_kes(baglanti_id: str) -> dict:
        return await asyncio.to_thread(composio.baglanti_kes, baglanti_id)

    @app.get("/api/etkinlik")
    async def etkinlik(adet: int = 200, yalniz_yan_etkili: bool = False) -> dict:
        """OpenBot 'Activity': ajanlarin yaptigi islemler tek zaman cizelgesinde (denetim)."""
        onay_kapsami = {o["id"]: o for o in politika.onaylar.gecmis(500)}
        satirlar = []
        for r in run_deposu.liste():
            for a in r.adimlar:
                if a.arac in ("plan_guncelle", "gorevi_bitir"):
                    continue
                if yalniz_yan_etkili and not a.yan_etkili:
                    continue
                o = onay_kapsami.get(a.onay_id) if a.onay_id else None
                satirlar.append({
                    "zaman": a.zaman, "run": r.id, "gorev": r.hedef[:120], "no": a.no,
                    "arac": a.arac, "durum": str(a.durum.value), "yan_etkili": a.yan_etkili,
                    "aciklama": a.aciklama[:200], "dosya": a.dosya,
                    "onay": {"karar": o["karar"], "kapsam": o.get("kapsam", "tek")} if o else None,
                })  # fmt: skip
        satirlar.sort(key=lambda x: x["zaman"], reverse=True)
        return {"etkinlik": satirlar[: max(1, min(adet, 1000))]}

    @app.get("/api/onay-kurallari")
    async def onay_kurallari() -> dict:
        return {"kurallar": politika.onaylar.kurallar()}

    @app.delete("/api/onay-kurallari/{onay_id}")
    async def onay_kurali_sil(onay_id: str) -> dict:
        politika.onaylar.kural_sil(onay_id)
        return {"kurallar": politika.onaylar.kurallar()}

    @app.post("/api/onaylar/{onay_id}")
    async def onay_karar(onay_id: str, istek: OnayIstegi) -> dict:
        sonuc = politika.onaylar.karar_ver(onay_id, istek.onayla, istek.kapsam).model_dump(
            mode="json"
        )
        for r in run_deposu.liste():  # bu onayi bekleyen ajan gorevi kaldigi yerden surer
            if r.durum is RunDurum.onay_bekliyor and any(a.onay_id == onay_id for a in r.adimlar):
                await ajan.devam(r.id)
        return sonuc

    # ---- ajan gorevleri (A3) ----
    @app.post("/api/gorevler")
    async def gorev_baslat(istek: GorevIstegi) -> dict:
        # proje yoksa hemen Turkce hata; MCP soguk acilisi olay dongusunu kilitlemesin
        await asyncio.to_thread(ajan_baglami, istek.hedef)
        dogrula(model_yetenegi(), araclar_gerekli=True, dusunme=ayarlar.oku().dusunme)
        izole_kur = None
        if istek.izole:
            proje = Path(sohbet.aktif_alan().kokler[0])
            wt.depo_koku(proje)  # git yoksa hemen Turkce hata

            def izole_kur(run_id: str) -> tuple[str, str]:
                onek = ayarlar.oku().branch_oneki
                yol, dal = wt.olustur(proje, veri_dizini / "worktrees", run_id, onek)
                return str(yol), dal

        run = await ajan.baslat(
            istek.hedef, istek.kabul, istek.butce, **_proje_modeli("koordinator"),
            izole_kur=izole_kur, onceki=istek.onceki, etkilesimli=istek.etkilesimli,
        )  # fmt: skip
        return run.ozet()

    # ---- zamanlamalar (A11): YALNIZ uygulama acikken; gozetimsiz onay yok ----
    zamanlayici = Zamanlayici(veri_dizini)
    BITMIS_DURUMLAR = {"basarili", "dogrulanmadi", "basarisiz", "iptal"}  # noqa: N806

    def _run_durumu(run_id: str) -> str:
        try:
            return str(run_deposu.getir(run_id).durum.value)
        except Exception:  # noqa: BLE001 - silinmis run bitmis sayilir
            return "basarisiz"

    HEDEF_ISARETI = "HEDEF_TAMAM"

    async def _tetikle(t: Tetik) -> None:
        z = next((x for x in zamanlayici.liste() if x.id == t.zamanlama), None)
        alan = sohbet.projeler.aktif() if sohbet.projeler else None
        if (
            z is None
            or alan is None
            or not alan.kokler
            or Path(alan.kokler[0]) != Path(z.proje_kok)
        ):
            # kullanicinin acik projesi sessizce degistirilmez
            zamanlayici.baslatildi(t, "", "zamanlamanin projesi acik degil")
            return
        try:
            hedef = f"[zamanlanmis: {z.ad}] {z.hedef}"
            if z.davranis == "bildir":  # OpenBot check-in: yalniz bakar ve haber verir
                hedef += (
                    "\n\nYALNIZ BILDIR: dosya yazma, komut, gonderme gibi hicbir degisiklik "
                    "yapma; yalniz incele ve kullanicinin bilmesi gerekenleri raporla."
                )
            if z.bitis_kosulu:  # OpenBot goal: hedefe ulasinca rutin durur
                hedef += (
                    f"\n\nBITIS KOSULU: {z.bitis_kosulu}\nBu kosul artik saglaniyorsa "
                    f"raporunun ilk satirina tam olarak {HEDEF_ISARETI} yaz."
                )
            run = await ajan.baslat(
                hedef, [], Butce(max_adim=z.max_adim), model=ayarlar.oku().aktif_model,
            )  # fmt: skip
            zamanlayici.baslatildi(t, run.id)
        except Exception as e:  # noqa: BLE001 - kaydedilir, dongu durmaz
            zamanlayici.baslatildi(t, "", str(e))

    async def zamanlayici_tick(simdi: datetime | None = None) -> list[Tetik]:
        tetikler = await asyncio.to_thread(
            zamanlayici.tick, simdi or datetime.now(UTC), _run_durumu
        )
        for t in tetikler:
            await _tetikle(t)
        _hedefleri_kontrol_et(simdi or datetime.now(UTC))
        return tetikler

    def _hedefleri_kontrol_et(simdi: datetime) -> None:
        """Bitis kosullu rutin: son biten calismanin raporu hedefe ulasildi diyorsa durdur."""
        for z in zamanlayici.liste():
            if not (z.aktif and z.bitis_kosulu):
                continue
            son = next((t for t in reversed(zamanlayici.gecmis(z.id)) if t.get("run_id")), None)
            if not son:
                continue
            try:
                r = run_deposu.getir(son["run_id"])
            except Exception:  # noqa: BLE001, S112 - silinmis run
                continue
            if r.durum in BITMIS_RUN and HEDEF_ISARETI in ((r.sonuc.ozet or "")[:200]):
                zamanlayici.hedefe_ulasti(z.id, simdi)

    app.state.zamanlayici_tick = zamanlayici_tick

    @app.get("/api/oneriler")
    async def oneri_listesi() -> dict:
        """Yeni sohbet ekrani: DURUM.md maddeleri, insan bekleyen thread'ler, yaklasan rutinler."""
        alanlar = sorted(projeler.liste(), key=lambda a: a.guncelleme, reverse=True)
        isler = [_is_ozet(x) for x in superajan_deposu.liste()]
        return {"oneriler": await asyncio.to_thread(
            oneriler_hesapla, alanlar, isler, zamanlayici.liste(), datetime.now(UTC))}  # fmt: skip

    async def _zamanlayici_dongusu() -> None:
        while True:
            try:
                await zamanlayici_tick()
                for w in webhooklar.liste():  # sira bekleyen olaylar
                    await _webhook_isle(w["id"])
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Zamanlayici: {e}")
            await asyncio.sleep(30)

    @app.get("/api/zamanlamalar")
    async def zamanlama_listesi() -> dict:
        return {"zamanlamalar": [z.model_dump() for z in zamanlayici.liste()],
                "gecmis": zamanlayici.gecmis()[-50:],
                "not": "Zamanlamalar yalniz uygulama acikken calisir."}  # fmt: skip

    @app.post("/api/zamanlamalar")
    async def zamanlama_ekle(veri: dict) -> dict:
        veri = {"saat_dilimi": ayarlar.oku().saat_dilimi, **veri}
        if not veri.get("proje_kok"):
            alan = sohbet.projeler.aktif() if sohbet.projeler else None
            if alan is None or not alan.kokler:
                raise UygulamaHatasi("Zamanlama icin once bir proje acin.")
            veri["proje_kok"] = alan.kokler[0]
        try:
            return zamanlayici.ekle(veri).model_dump()
        except ValidationError as e:
            raise UygulamaHatasi(f"Gecersiz zamanlama: {e.errors()[0].get('msg')}") from e

    @app.patch("/api/zamanlamalar/{zid}")
    async def zamanlama_guncelle(zid: str, veri: dict) -> dict:
        try:
            return zamanlayici.guncelle(zid, veri).model_dump()
        except ValidationError as e:
            raise UygulamaHatasi(f"Gecersiz zamanlama: {e.errors()[0].get('msg')}") from e

    @app.post("/api/zamanlamalar/{zid}/calistir")
    async def zamanlama_calistir(zid: str) -> dict:
        """Rutini simdi calistir (Claude Desktop 'Run now'); projesi acik olmali."""
        z = next((x for x in zamanlayici.liste() if x.id == zid), None)
        if z is None:
            raise UygulamaHatasi("Rutin bulunamadi.")
        alan = sohbet.projeler.aktif() if sohbet.projeler else None
        if alan is None or not alan.kokler or Path(alan.kokler[0]) != Path(z.proje_kok):
            raise UygulamaHatasi(f"Once rutinin projesini acin: {z.proje_kok}")
        run = await ajan.baslat(
            f"[rutin: {z.ad}] {z.hedef}", [], Butce(max_adim=z.max_adim),
            model=ayarlar.oku().aktif_model,
        )  # fmt: skip
        return {"run": run.id}

    @app.delete("/api/zamanlamalar/{zid}")
    async def zamanlama_sil(zid: str) -> dict:
        zamanlayici.sil(zid)
        return {"silindi": zid}

    # ---- webhook tetikleyicileri (A11.3): HMAC + zaman + tek kullanimlik teslim ----
    webhooklar = WebhookDeposu(veri_dizini)
    webhook_kilidi = asyncio.Lock()

    async def _webhook_isle(wid: str) -> str:
        """Onceki calisma bitmisse siradaki olayi baslatir; donus: durum."""
        async with webhook_kilidi:
            w = webhooklar.getir(wid)
            if w.ajan:  # kalici ajana: olay ajanin FIFO kuyruguna, sirasi gelince calisir
                sira = webhooklar.siradaki(wid)
                if sira is None:
                    return "bos"
                w, olay = sira
                a = ajan_deposu.kuyruga_ekle(w.ajan, KuyrukOgesi(
                    metin=hedef_olustur(w, olay["olay"]), kimden=f"webhook:{w.id}"))  # fmt: skip
                await _ajan_dagit()
                return f"ajan kuyrugunda: {a.ad}"
            if w.son_run and _run_durumu(w.son_run) not in BITMIS_DURUMLAR:
                return "kuyrukta"
            alan = sohbet.projeler.aktif() if sohbet.projeler else None
            if alan is None or not alan.kokler or Path(alan.kokler[0]) != Path(w.proje_kok):
                return "kuyrukta (webhook'un projesi acik degil)"
            sira = webhooklar.siradaki(wid)
            if sira is None:
                return "bos"
            w, olay = sira
            run = await ajan.baslat(
                hedef_olustur(w, olay["olay"]), [], Butce(max_adim=w.max_adim),
                model=ayarlar.oku().aktif_model,
            )  # fmt: skip
            w = webhooklar.getir(wid)
            w.son_run = run.id
            webhooklar.kaydet(w)
            return f"basladi:{run.id}"

    @app.post("/api/webhook/{wid}")
    async def webhook_tetikle(wid: str, istek: Request) -> Response:
        govde = await istek.body()
        try:
            basliklar = {k.lower(): v for k, v in istek.headers.items()}
            w = webhooklar.dogrula(wid, basliklar, govde)
            sira = webhooklar.kuyruga_al(
                w, basliklar["x-yas-teslim"], govde.decode("utf-8", errors="replace")
            )
        except WebhookHatasi as e:
            return JSONResponse({"hata": e.mesaj}, status_code=e.kod)
        try:
            durum_ = await _webhook_isle(wid)
        except Exception as e:  # noqa: BLE001 - olay kuyrukta kalir
            durum_ = f"kuyrukta ({e})"
        return JSONResponse({"kabul": True, "sira": sira, "durum": durum_}, status_code=202)

    @app.get("/api/webhooklar")
    async def webhook_listesi() -> dict:
        return {"webhooklar": webhooklar.liste()}

    @app.post("/api/webhooklar")
    async def webhook_ekle(veri: dict) -> dict:
        if veri.get("ajan"):  # kalici ajana giden webhook: proje gerekmez
            veri["ajan"] = ajan_deposu.getir(str(veri["ajan"])).id  # yoksa Turkce hata
        elif not veri.get("proje_kok"):
            alan = sohbet.projeler.aktif() if sohbet.projeler else None
            if alan is None or not alan.kokler:
                raise UygulamaHatasi("Webhook icin once bir proje acin.")
            veri["proje_kok"] = alan.kokler[0]
        try:
            w = webhooklar.ekle(veri)
        except ValidationError as e:
            raise UygulamaHatasi(f"Gecersiz webhook: {e.errors()[0].get('msg')}") from e
        return w.model_dump(exclude={"kuyruk"}) | {
            "adres": f"/api/webhook/{w.id}",
            "not": "Sir yalniz simdi gosterilir; saklayin.",
        }

    @app.delete("/api/webhooklar/{wid}")
    async def webhook_sil(wid: str) -> dict:
        webhooklar.sil(wid)
        return {"silindi": wid}

    # ---- Remote Control (A12): varsayilan kapali, ayri TLS sunucu, beyaz liste ----
    from app import uzak as uzak_mod

    uzak_depo = uzak_mod.UzakDeposu(veri_dizini)
    uzak_sunucu = uzak_mod.UzakSunucu()
    app.state.uzak_depo = uzak_depo

    async def _ic_cagri(metod: str, yol: str, govde: Any) -> tuple[int, Any]:
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1",
            headers={OTURUM_BASLIGI: oturum_anahtari}, timeout=60,
        ) as c:  # fmt: skip
            r = await c.request(metod, yol, json=govde)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"hata": "Gecersiz cevap."}

    app.state.uzak_ic_cagri = _ic_cagri

    def _uzak_hostlar() -> list[str]:
        if ayarlar.oku().uzak_ag == "tailscale":
            ts = uzak_mod.tailscale_ip()
            return [ts] if ts else []
        return [i for i in uzak_mod.yerel_ipler() if i != "127.0.0.1"]

    def _uzak_durum() -> dict:
        _, _, parmak = uzak_mod.sertifika(veri_dizini / "uzak-tls")
        a = ayarlar.oku()
        hostlar = _uzak_hostlar()
        return {
            "acik": uzak_sunucu.acik_mi(), "port": a.uzak_port, "ag": a.uzak_ag,
            "parmak_izi": parmak, "adresler": [f"https://{h}:{a.uzak_port}/" for h in hostlar],
            "tailscale_yok": a.uzak_ag == "tailscale" and not hostlar,
            "cihazlar": uzak_depo.liste(), "denetim": uzak_depo.denetim(20),
        }  # fmt: skip

    @app.get("/api/uzak")
    async def uzak_durum() -> dict:
        return await asyncio.to_thread(_uzak_durum)

    @app.post("/api/uzak/ac")
    async def uzak_ac() -> dict:
        a = ayarlar.oku()
        hostlar = await asyncio.to_thread(_uzak_hostlar)
        if not hostlar:
            raise UygulamaHatasi(
                "Tailscale bagli degil: Tailscale'i acip oturum acin."
                if a.uzak_ag == "tailscale" else "Yerel ag adresi bulunamadi."
            )  # fmt: skip
        cert, key, parmak = await asyncio.to_thread(
            uzak_mod.sertifika, veri_dizini / "uzak-tls", hostlar
        )
        uapp = uzak_mod.uzak_uygulamasi(uzak_depo, _ic_cagri, parmak, lambda: ayarlar.oku().dil)
        aglar = uzak_mod.TAILSCALE_AGLARI if a.uzak_ag == "tailscale" else None
        asgi = uzak_mod.tam_erisim_asgi(uzak_depo, uapp, app, oturum_anahtari, aglar)
        try:
            await uzak_sunucu.ac(asgi, a.uzak_port, cert, key, hostlar[0])
        except OSError as e:
            raise UygulamaHatasi(f"Uzak erisim acilamadi: {e}") from e
        return await asyncio.to_thread(_uzak_durum)

    @app.post("/api/uzak/kapat")
    async def uzak_kapat() -> dict:
        await uzak_sunucu.kapat()
        return {"acik": False}

    @app.post("/api/uzak/kod")
    async def uzak_kod(veri: dict) -> dict:
        try:
            return uzak_depo.kod_olustur(veri.get("rol", "izleyici"))
        except uzak_mod.UzakHata as e:
            raise UygulamaHatasi(e.mesaj) from e

    @app.delete("/api/uzak/cihaz/{cihaz_id}")
    async def uzak_cihaz_iptal(cihaz_id: str) -> dict:
        try:
            uzak_depo.iptal(cihaz_id)
        except uzak_mod.UzakHata as e:
            raise UygulamaHatasi(e.mesaj) from e
        return {"iptal": cihaz_id}

    # ---- dinamik is akislari (A8.6): tipli adimlar, kod calistirma yok ----
    akislar = AkisDeposu(veri_dizini)
    akis_gorevleri: set[asyncio.Task] = set()

    def _akis_baslat(a: Akis) -> None:
        alan = sohbet.aktif_alan()
        kayit = sohbet.ajan_araclari(alan)
        if kayit is None:
            raise UygulamaHatasi("Is akisi icin once bir proje acin.")

        async def ajan_adimi(hedef: str) -> tuple[str, str, str]:
            r = await ajan.baslat(hedef, model=ayarlar.oku().aktif_model)
            g = ajan._gorevler.get(r.id)
            if g:
                await asyncio.wait({g})
            r = run_deposu.getir(r.id)
            return str(r.durum), r.sonuc.ozet or r.hata, r.id

        t = asyncio.create_task(
            akis_mod.calistir(
                a, akislar, ajan_adimi, lambda k: kayit.komut_calistir(k, timeout=600)
            )
        )
        akis_gorevleri.add(t)
        t.add_done_callback(akis_gorevleri.discard)

    @app.post("/api/akislar")
    async def akis_olustur(veri: dict) -> dict:
        a = akis_mod.dogrula_veri(veri)
        for x in a.adimlar:  # istemci durum gonderip adim atlatamaz
            x.durum, x.deneme, x.sonuc, x.run_id = "bekliyor", 0, "", ""
        akislar.kaydet(a)
        _akis_baslat(a)
        return a.model_dump()

    @app.get("/api/akislar")
    async def akis_listesi() -> dict:
        return {"akislar": akislar.liste()}

    @app.get("/api/akislar/{akis_id}")
    async def akis_getir(akis_id: str) -> dict:
        return akislar.getir(akis_id).model_dump()

    @app.post("/api/akislar/{akis_id}/devam")
    async def akis_devam(akis_id: str) -> dict:
        a = akislar.getir(akis_id)
        if a.durum == "calisiyor":
            raise UygulamaHatasi("Akis zaten calisiyor.")
        for x in a.adimlar:
            if x.durum in ("onay_bekliyor", "calisiyor"):
                x.durum = "bekliyor"
        _akis_baslat(a)
        return a.model_dump()

    @app.post("/api/gorevler/{run_id}/entegre")
    async def gorev_entegre(run_id: str, istek: EntegreIstegi) -> dict:
        r = run_deposu.getir(run_id)
        if not r.calisma_koku:
            raise UygulamaHatasi("Bu gorev izole calismadi; entegre edilecek dal yok.")
        if r.durum not in (RunDurum.basarili, RunDurum.dogrulanmadi):
            raise UygulamaHatasi("Once gorev bitmeli.")
        proje = Path(sohbet.aktif_alan().kokler[0])
        return await asyncio.to_thread(
            wt.entegre_et, proje, Path(r.calisma_koku), r.dal, r.hedef, istek.test_komutu
        )

    @app.post("/api/gorevler/{run_id}/at")
    async def gorev_at(run_id: str) -> dict:
        r = run_deposu.getir(run_id)
        if not r.calisma_koku:
            raise UygulamaHatasi("Bu gorev izole calismadi.")
        proje = Path(sohbet.aktif_alan().kokler[0])
        return await asyncio.to_thread(wt.at, proje, Path(r.calisma_koku), r.dal)

    @app.get("/api/gorevler")
    async def gorev_listesi() -> dict:
        return {"gorevler": [r.ozet() for r in run_deposu.liste()[:50]]}

    @app.get("/api/gorevler/{run_id}")
    async def gorev_getir(run_id: str) -> dict:
        return run_deposu.getir(run_id).ozet()

    @app.get("/api/gorevler/{run_id}/takim")
    async def gorev_takim(run_id: str) -> dict:
        r = run_deposu.getir(run_id)
        return ajan.takim.pano(r.parent or r.id)

    @app.get("/api/gorevler/{run_id}/olaylar")
    async def gorev_olaylari(run_id: str) -> StreamingResponse:
        run_deposu.getir(run_id)
        return sse(olay_akisi(run_deposu, run_id))

    @app.post("/api/gorevler/{run_id}/mesaj")
    async def gorev_mesaj(run_id: str, istek: GorevMesaji) -> dict:
        return (await ajan.mesaj(run_id, istek.metin)).ozet()

    @app.post("/api/gorevler/{run_id}/karar")  # genel {islem} rotasindan ONCE tanimlanmali
    async def gorev_karar(run_id: str, istek: KararIstegi) -> dict:
        return (await ajan.karar(run_id, istek.adim, istek.karar)).ozet()

    @app.post("/api/gorevler/{run_id}/{islem}")
    async def gorev_islem(run_id: str, islem: str) -> dict:
        fonk = {
            "duraklat": ajan.duraklat,
            "devam": ajan.devam,
            "iptal": ajan.iptal,
            "tekrar": ajan.tekrar,
        }.get(islem)
        if fonk is None:
            raise UygulamaHatasi("Islem: duraklat, devam, iptal ya da tekrar.")
        return (await fonk(run_id)).ozet()

    # ---- checkpoint / geri alma (A2.7) ----
    @app.get("/api/checkpointler")
    async def checkpoint_listesi() -> dict:
        return {"checkpointler": checkpointler.liste()}

    @app.get("/api/checkpointler/{cp_id}")
    async def checkpoint_onizle(cp_id: str) -> dict:
        return checkpointler.onizle(cp_id)

    @app.post("/api/checkpointler/{cp_id}/geri-al")
    async def checkpoint_geri_al(cp_id: str, istek: GeriAlIstegi) -> dict:
        return checkpointler.geri_al(cp_id, istek.yollar or None)

    @app.get("/api/checkpointler/{cp_id}/hunklar")
    async def checkpoint_hunklar(cp_id: str, yol: str) -> dict:
        return checkpointler.hunklar(cp_id, yol)

    @app.post("/api/checkpointler/{cp_id}/hunk-geri-al")
    async def checkpoint_hunk_geri_al(cp_id: str, istek: HunkIstegi) -> dict:
        return checkpointler.hunk_geri_al(cp_id, istek.yol, istek.hunklar)

    @app.post("/api/komutlar/{is_id}/girdi")
    async def komut_girdi_ucu(is_id: str, istek: GirdiIstegi) -> dict:
        return await komutlar.girdi_gonder(is_id, istek.metin)

    # ---- calisan komutlar ----
    @app.get("/api/komutlar")
    async def komut_listesi() -> dict:
        return {"isler": [komutlar.ozet(i) for i in komutlar.isler.values()]}

    uyanik = Uyanik()
    app.state.one_getir = lambda: None  # masaustu penceresi (main baglar)
    kisayol = mda.GenelKisayol(lambda: app.state.one_getir())

    @app.get("/api/masaustu")
    async def masaustu_durum() -> dict:
        return {"baslangicta_ac": mda.baslangic_durumu(), "kisayol_hata": kisayol.hata,
                "depolama": await asyncio.to_thread(mda.depolama, veri_dizini),
                "veri_dizini": str(veri_dizini)}  # fmt: skip

    @app.post("/api/bildirim")
    async def bildirim_gonder(veri: dict) -> dict:
        ok = await asyncio.to_thread(
            mda.bildirim, str(veri.get("baslik", URUN_ADI)), str(veri.get("metin", ""))
        )
        return {"gonderildi": ok}

    @app.get("/api/sirlar")
    async def sir_listesi() -> dict:
        """Yalniz adlar; deger hicbir uctan geri okunmaz."""
        return {"adlar": sirlar.KASA.adlar()}

    @app.post("/api/sirlar")
    async def sir_ekle(istek: dict) -> dict:
        ad = await asyncio.to_thread(
            sirlar.KASA.ekle, str(istek.get("deger", "")), str(istek.get("ad", ""))
        )
        return {"ad": ad}

    @app.delete("/api/sirlar/{ad}")
    async def sir_sil(ad: str) -> dict:
        await asyncio.to_thread(sirlar.KASA.sil, ad)
        return {"silindi": ad}

    @app.post("/api/dosya/goster")
    async def dosya_goster(istek: dict) -> dict:
        """Sohbetteki yolu Gezgin'de secili gosterir; dosyayi ACMAZ/CALISTIRMAZ."""
        ham = str(istek.get("yol", "")).strip().strip('"')
        p = Path(ham)
        if not ham or not p.is_absolute() or not p.exists():
            raise UygulamaHatasi("Bu yol bulunamadi.")
        hedef = ["explorer", str(p)] if p.is_dir() else ["explorer", f"/select,{p}"]
        subprocess.Popen(hedef)  # noqa: S603 - sabit program, kabuk yok, yalniz gosterir
        return {"gosterildi": True}

    @app.post("/api/masaustu/klasor-ac")
    async def veri_klasoru_ac() -> dict:
        os.startfile(veri_dizini)  # noqa: S606 - kullanicinin kendi veri klasoru
        return {"acildi": True}

    @app.get("/api/uyanik")
    async def uyanik_durum() -> dict:
        return {"acik": uyanik.acik}

    @app.put("/api/uyanik")
    async def uyanik_ayarla(veri: dict) -> dict:
        return {"acik": uyanik.ayarla(bool(veri.get("acik")))}

    # Terminal paneli: kullanicinin KENDI yazdigi komut, etkin projede calisir.
    # Model degil kullanici calistirdigi icin onay sorulmaz; izolasyon adaptoru yine uygulanir.
    @app.post("/api/terminal")
    async def terminal_calistir(veri: dict) -> dict:
        kokler = sohbet.aktif_alan().izinli_kokler
        cwd = Path(kokler[0]) if kokler else Path.home()
        is_ = await komutlar.baslat(
            str(veri.get("komut", ""))[:4000],
            cwd,
            arka_plan=True,
            timeout=3600,
            sahip="terminal",
            bash=False,  # kullanicinin terminali: Windows komutlari (dir, set) cmd.exe'de kalir
        )
        return komutlar.ozet(is_)

    @app.get("/api/komutlar/{is_id}")
    async def komut_getir(is_id: str) -> dict:
        return komutlar.ozet(komutlar.getir(is_id))

    @app.post("/api/komutlar/{is_id}/durdur")
    async def komut_durdur_ucu(is_id: str) -> dict:
        return await komutlar.durdur(is_id)

    # ---- arayuz ----
    web = web_dizini()

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(web_dizini() / "kairo.ico", media_type="image/x-icon")

    @app.get("/")
    async def ana_sayfa(istek: Request) -> Response:
        """index.html'e oturum anahtarini gomer: baska origin bu sayfayi OKUYAMAZ (A1.9)."""
        try:
            html = (web / "index.html").read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - paket hatasi
            return JSONResponse({"hata": "Arayuz dosyasi bulunamadi."}, status_code=500)
        # uzak (telefon) istemciye gercek anahtar GONDERILMEZ; uzak gecit kendisi ekler
        anahtar = "uzak" if istek.headers.get("x-yas-uzak-cihaz") else oturum_anahtari
        etiket = f'<meta name="yas-oturum" content="{anahtar}">'
        html = html.replace("</head>", f"  {etiket}\n</head>", 1)
        return Response(
            html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"}
        )

    if web.exists():
        app.mount("/web", TazeStatik(directory=web), name="web")
    else:  # pragma: no cover - paket hatasi
        logger.error("Arayuz klasoru yok: {}", web)
    return app
