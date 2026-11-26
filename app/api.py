"""FastAPI uygulamasi: servis baglama, yasam dongusu, loopback guvenlik ara katmani ve routerlar."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import secrets
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import ValidationError

from app import URUN_ADI, __version__
from app import uzak as uzak_mod
from app.agent import cli_ajan, kum
from app.agent import koordinasyon as koord
from app.agent import review as rv
from app.agent import superajan as sa
from app.agent import worktree as wt
from app.agent.ajanlar import AJAN_NOTU_ARACI, AJANA_MESAJ_ARACI, AjanDeposu, KuyrukOgesi
from app.agent.akis import AkisDeposu, SablonDeposu
from app.agent.checkpoints import CheckpointDeposu
from app.agent.dersler import DersDefteri
from app.agent.dosyalar import ortam_allowlist
from app.agent.hooks import HookDeposu
from app.agent.izolasyon import adaptor_olustur
from app.agent.masaustu import Masaustu
from app.agent.mcp import McpYoneticisi
from app.agent.policy import Istek, PolitikaMotoru, YanEtki, maskele, yerel_host_mu
from app.agent.runner import BITMIS as BITMIS_RUN
from app.agent.runner import YAZAN_ARACLAR, AgentRunner, Butce, Run, RunDeposu, RunDurum
from app.agent.takim import TakimPanosu
from app.agent.tarayici import Tarayici
from app.agent.terminal import KomutServisi
from app.agent.webhook import WebhookDeposu, hedef_olustur
from app.agent.workspaces import CalismaAlani, Mod, WorkspaceDeposu
from app.agent.yetenek import ModelYetenegi, dogrula, uzak_yetenek, yerel_yetenek
from app.agent.zamanlayici import Tetik, Zamanlayici
from app.config import web_dizini
from app.exceptions import (
    Bulunamadi,
    OnayGerekli,
    UygulamaHatasi,
    YerelLLMHatasi,
    YetkiYok,
)
from app.routers import (
    ACIK_YOLLAR,
    DIKTE_MAX_BAYT,
    DIKTE_MAX_SN,
    DIKTE_SESSIZ,
    DIKTE_TALIMATI,
    DIKTE_UZAK,
    DIKTE_UZAK_SESSIZ,
    OTURUM_BASLIGI,
    OZET_ONAY,
    OZET_TALIMATI,
    UPLOAD_PARCA_BAYT,
    AdIstegi,
    AjanRunKaydi,
    AltOturumIstegi,
    AnahtarIstegi,
    CcIzinIstegi,
    DurdurIstegi,
    EditorBaglamIstegi,
    EntegreIstegi,
    GeriAlIstegi,
    GeriSarIstegi,
    GirdiIstegi,
    GizliProjeIstegi,
    GorevIstegi,
    GorevMesaji,
    GuvenIstegi,
    HafizaIstegi,
    HunkIstegi,
    IndirIstegi,
    IsEmriIstegi,
    KararIstegi,
    KartKomutIstegi,
    ModelIstegi,
    ModellerIstegi,
    ModIstegi,
    OllamaIndirIstegi,
    OnayIstegi,
    OneriRedIstegi,
    ProjeIstegi,
    SaglayiciIstegi,
    SkillDurumIstegi,
    SkillIceAdIstegi,
    SkillIceIstegi,
    SkillIceKurIstegi,
    SkillIstegi,
    SonrakiOneriIstegi,
    TalimatIstegi,
    YolIstegi,
    ajan_ve_otomasyon,
    dogrulama_mesaji,
    eklentiler,
    modeller,
    proje_ve_sistem,
    sohbet_hafiza,
    sse,
)
from app.routers.proje_ve_sistem import PR_ALANLARI, PR_URL
from app.services import cc_plugin as ccp
from app.services import masaustu_ayar as mda
from app.services import sirlar
from app.services import skiller as skl
from app.services.agecidi import AgGecidi, agecidi_uygulamasi
from app.services.arac_paketleri import AracPaketleri
from app.services.ayarlar import AyarDeposu
from app.services.composio import Composio
from app.services.ekler import EkDeposu
from app.services.guncelleme import GuncellemeDenetleyici
from app.services.hafiza import HafizaDeposu
from app.services.model_magaza import Indirici, Magaza, ModelKaydi
from app.services.model_yonetici import LLMFabrikasi, ModelYonetici
from app.services.ollama import Ollama, ollama_baglam
from app.services.openrouter import OpenRouterDeposu
from app.services.oturumlar import OturumDeposu
from app.services.pluginler import PluginDeposu
from app.services.saglayicilar import SaglayiciDeposu, _reasoning_destekli
from app.services.saglayicilar import ayir as saglayici_ayir
from app.services.skill_ice import SkillIceAktarici
from app.services.skiller import SKILL_KAYDET_ARACI, SkillDeposu
from app.services.sohbet import VARSAYILAN_ALAN_ID, SohbetServisi
from app.services.talimatlar import TalimatDeposu
from app.services.telegram import TelegramKanali
from app.services.testler import TestServisi
from app.services.uyanik import Uyanik
from app.services.uzantilar import UzantiYoneticisi
from app.services.yerel_llm import MODELLER, YerelLLM
from app.services.yonlendirici import gunluk_maliyet_usd, model_sec

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
                    "type": "array",
                    "maxItems": 4,
                    "items": {"type": "string"},
                    "description": "Kanit: 'dosya_tam_yolu::dosyada gecen kisa metin'. Dosya "
                    "degisip metin kaybolursa not otomatik eskir.",
                },
            },
            "required": ["metin"],
        },
    },
}

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
}


class TazeStatik(StaticFiles):
    """Basliksiz statik dosyayi tarayici tahminle onbellekler; guncellemeden sonra eski JS
    calisir. no-cache: her seferinde ETag ile dogrulanir (yerelde maliyetsiz)."""

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        r = super().file_response(*args, **kwargs)
        r.headers["Cache-Control"] = "no-cache"
        return r


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
    kayit.yukle()
    ayarlar = AyarDeposu(veri_dizini)
    oturumlar = OturumDeposu(veri_dizini)
    ekler = EkDeposu(veri_dizini)
    guncelleme = GuncellemeDenetleyici(veri_dizini)
    openrouter = OpenRouterDeposu(veri_dizini, transport=or_transport)
    ollama = Ollama(
        lambda: ayarlar.oku().ollama_adres,
        lambda: ollama_baglam(ayarlar.oku().baglam_token),
        transport=ollama_transport,
        site_transport=ollama_transport,
    )
    saglayicilar = SaglayiciDeposu(veri_dizini, transport=or_transport)
    yonetici = ModelYonetici(ayarlar, fabrika, uzak=openrouter, ollama=ollama, uyumlu=saglayicilar)
    talimatlar = TalimatDeposu(veri_dizini)
    skiller = skill_deposu or SkillDeposu(veri_dizini)
    projeler = WorkspaceDeposu(veri_dizini)
    koord.KOORD.bagla(veri_dizini / "koordinasyon.json")
    _adaptorler: dict[tuple[str, str], Any] = {}

    def izolasyon() -> Any:
        a = ayarlar.oku()
        k = (a.izolasyon, a.konteyner_imaj)
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

    skill_alani: ContextVar[CalismaAlani | None] = ContextVar("skill_alani", default=None)

    def proje_skill_kaynaklari() -> list[tuple[str, Path]]:
        alan = skill_alani.get() or sohbet.aktif_alan()
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
    hooklar.ek_kaynak = pluginler.hook_tanimlari
    composio = Composio(veri_dizini)

    def _mcp_ek() -> list[dict]:
        ek = list(pluginler.mcp_tanimlari())
        try:
            if (d := composio.mcp_tanimi()) is not None:
                ek.append(d)
        except Exception as e:  # noqa: BLE001
            logger.debug("Composio baglayicisi eklenmedi: {}", e)
        return ek

    mcp.ek_kaynak = _mcp_ek
    mcp.kokler = lambda: [str(k) for k in sohbet.aktif_alan().izinli_kokler]
    sohbet.uzantilar = uzantilar
    sohbet.tarayici = Tarayici(veri_dizini)
    sohbet.masaustu = Masaustu(
        lambda: ayarlar.oku().masaustu_izinli, veri_dizini / "ekran-goruntuleri"
    )
    sohbet.mcp = mcp
    sohbet.hafiza = hafiza

    def ajan_baglami(
        hedef: str,
        model_secimi: str | None = None,
        *,
        alan: CalismaAlani | None = None,
        mcp_sunuculari: set[str] | None = None,
    ) -> tuple[str, list, dict, str | None]:
        alan = alan or sohbet.aktif_alan()
        if sohbet.ajan_araclari(alan) is None:
            raise UygulamaHatasi("Ajan araclari hazir degil.")
        a = ayarlar.oku()
        sistem_m, araclar_, isleyiciler, skill_adi = sohbet.baglam_hazirla(
            a,
            hedef,
            [],
            model_secimi,
            ajan_gorevi=True,
            alan=alan,
            mcp_sunuculari=mcp_sunuculari,
        )
        if a.otomatik_ogrenme:
            araclar_ = [*araclar_, HAFIZA_ARACI]
            sistem_m += HAFIZA_TALIMATI

            def hafizaya_ekle(metin: str, dayanak: list | None = None) -> dict:
                try:
                    dayanak_ = [str(x)[:500] for x in (dayanak or [])][:4]
                    return hafiza.ekle(
                        metin, kaynak="ajan", guven="dusuk", kapsam=alan.id, dayanak=dayanak_
                    )
                except (UygulamaHatasi, ValueError) as e:
                    return {"hata": getattr(e, "mesaj", str(e))}

            isleyiciler = {**isleyiciler, "hafizaya_ekle": hafizaya_ekle}
        if a.hafiza_acik:
            araclar_ = [*araclar_, HAFIZA_YARGI_ARACI]

            def hafiza_yargila(id: str, yargi: str, duzeltme: str = "") -> dict:  # noqa: A002
                try:
                    k = hafiza.yargila(id, yargi, duzeltme)
                    return {"tamam": True, "revizyon": k["revizyon"]}
                except (UygulamaHatasi, Bulunamadi) as e:
                    return {"hata": e.mesaj}

            isleyiciler = {**isleyiciler, "hafiza_yargila": hafiza_yargila}

        def skill_kaydet(ad: str, aciklama: str, icerik: str, okunan_revizyon: int = 0) -> dict:
            try:
                istek = Istek(
                    arac="skill_kaydet",
                    yan_etki=YanEtki.yaz,
                    ozet=f"Skill kaydet: {ad}",
                    komut=icerik[:2000],
                )
                politika.uygula(istek, alan)
                return skiller.ajan_kaydet(ad, aciklama, icerik, okunan_revizyon)
            except OnayGerekli as e:
                return {"hata": e.mesaj, "karar": "onay_bekliyor", "onay": e.onay}
            except (UygulamaHatasi, YetkiYok) as e:
                return {"hata": getattr(e, "mesaj", str(e))}

        araclar_ = [*araclar_, SKILL_KAYDET_ARACI]
        isleyiciler = {**isleyiciler, "skill_kaydet": skill_kaydet}
        return sistem_m, araclar_, isleyiciler, skill_adi

    def model_yetenegi(model: str = "") -> ModelYetenegi:
        a = ayarlar.oku()
        model = model or (a.aktif_model if a.saglayici in ("ollama", "uyumlu") else "")
        if p := saglayici_ayir(model):
            sid, mid = p
            m = saglayicilar.model_bilgisi(model) or {}
            ml = mid.lower()
            goruntu = any(
                k in ml
                for k in (
                    "gpt-4o",
                    "gpt-4.1",
                    "gpt-5",
                    "claude-3",
                    "claude-4",
                    "gemini",
                    "vision",
                    "-vl",
                    "pixtral",
                )
            )
            return ModelYetenegi(
                model=model,
                saglayici="uyumlu",
                araclar=True,
                json_cikti=True,
                goruntu=goruntu,
                baglam=int(m.get("baglam") or 32768),
                dusunme=_reasoning_destekli(sid, mid),
                tokenizer="tahmin",
                not_="Yetenekler varsayılan; model araç desteklemiyorsa hata verir.",
            )
        if model.startswith("ollama:"):
            y = ollama.yetenekler.get(model.removeprefix("ollama:")) or {}
            hedef = ollama_baglam(a.baglam_token)
            return ModelYetenegi(
                model=model,
                saglayici="ollama",
                araclar=y.get("araclar", True),
                json_cikti=True,
                goruntu=y.get("goruntu", False),
                baglam=min(y["baglam"], hedef) if y.get("baglam") else hedef,
                dusunme=y.get("dusunme", False),
                tokenizer="tahmin",
            )
        if model and model not in MODELLER:
            openrouter.eksik_modeli_getir(model)
            return uzak_yetenek(model, openrouter.liste_yolu)
        if model:
            return yerel_yetenek(model, a.baglam_token)
        if a.saglayici == "openrouter" and a.or_model:
            openrouter.eksik_modeli_getir(a.or_model)
            return uzak_yetenek(a.or_model, openrouter.liste_yolu)
        return yerel_yetenek(a.model, a.baglam_token)

    async def _ollama_yetenek_hazirla(model: str = "", *, baslat: bool = True) -> None:
        a = ayarlar.oku()
        hedef = model or (a.aktif_model if a.saglayici == "ollama" else "")
        if hedef.startswith("ollama:"):
            await ollama.yetenek(hedef.removeprefix("ollama:"), baslat=baslat)

    def onay_durumu(onay_id: str) -> str:
        return next(
            (o["karar"] for o in politika.onaylar.gecmis(500) if o["id"] == onay_id), "bekliyor"
        )

    run_deposu = RunDeposu(veri_dizini)
    run_deposu.kurtar()

    def gorev_alani(proje_id: str = "") -> CalismaAlani:
        if proje_id:
            try:
                return projeler.getir(proje_id)
            except Bulunamadi:
                logger.warning("Gorevin projesi bulunamadi: {}", proje_id)
        return sohbet.aktif_alan()

    async def gorev_baglami(run: Run) -> tuple[str, list, dict]:
        secim = run.skill_adi
        ayar = ayarlar.oku()
        hedef_model = run.model if run.model_sabit or run.ajan_id else ayar.aktif_model
        await _ollama_yetenek_hazirla(hedef_model)
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
            except Exception as e:  # noqa: BLE001
                logger.debug("Gorev skill secimi basarisiz: {}", e)
        alan = projeler.getir(run.proje_id) if run.proje_id else sohbet.aktif_alan()
        degisiklik: dict = {}
        if run.calisma_koku:
            degisiklik.update(kokler=[run.calisma_koku], ek_klasorler=[])
        if run.profil_izni == "plan" and alan.mod is not Mod.sohbet:
            degisiklik["mod"] = Mod.planla
        elif run.profil_izni == "ask" and alan.mod is Mod.otomatik:
            degisiklik["mod"] = Mod.onayli
        alan = alan.model_copy(update=degisiklik)
        mcp_sunuculari = set(run.profil_mcp) if run.profil_mcp is not None else None
        if run.bagimsiz_worktree:
            mcp_sunuculari = (mcp_sunuculari or set()) & {s.ad for s in mcp.tum() if s.url}
        jeton = skill_alani.set(alan)
        try:
            sistem_m, araclar_, isleyiciler, skill_adi = await asyncio.to_thread(
                ajan_baglami, run.hedef, secim, alan=alan, mcp_sunuculari=mcp_sunuculari
            )
            run.skill_adi = skill_adi or ""
            if ayar.skiller_acik:
                for ad in run.profil_skilleri:
                    try:
                        skill = skiller.getir(ad, set(ayar.kapali_skiller))
                        if not skill.hata:
                            sistem_m += "\n\n" + skl.otomatik_metin(skill)
                    except Bulunamadi:
                        logger.debug("Alt ajan skill'i etkin degil: {}", ad)
            return sistem_m, araclar_, isleyiciler
        finally:
            skill_alani.reset(jeton)

    ajan = AgentRunner(
        run_deposu,
        lambda hedef: ajan_baglami(hedef)[:3],
        lambda model=None: yonetici.kullan(model or None),
        onay_durumu,
        yetenek=model_yetenegi,
        hooks=hooklar,
        hafiza=lambda proje_id="": (
            hafiza.sistem_metni(gorev_alani(proje_id).id) if ayarlar.oku().hafiza_acik else ""
        ),
    )
    ajan.gorev_baglami = gorev_baglami
    ajan.profil_yetenegi = model_yetenegi
    ajan.kok = lambda proje_id="": next(iter(gorev_alani(proje_id).kokler), "")
    ajan.paralel_model = lambda: ayarlar.oku().saglayici == "openrouter"
    ajan.uygulayici_model = lambda proje_id="": gorev_alani(proje_id).uygulayici_model
    ajan.cli_tam_yetki = lambda: ayarlar.oku().cli_tam_yetki

    def _ajan_model_denetle(istenen: str, proje_id: str) -> tuple[str, str | None]:
        a = ayarlar.oku()
        alan = gorev_alani(proje_id)
        hedef = istenen or a.aktif_model
        return model_sec(hedef, a, alan, gunluk_maliyet_usd(run_deposu, oturumlar))

    ajan.model_denetle = _ajan_model_denetle

    def _proje_modeli(rol: str) -> dict:
        alan = sohbet.aktif_alan()
        ozel = getattr(alan, f"{rol}_model")
        return {
            "model": ozel or ayarlar.oku().aktif_model,
            "model_sabit": bool(ozel),
            "model_rol": rol,
            "uygulayici_model": alan.uygulayici_model if rol == "koordinator" else "",
            "proje_id": alan.id if alan.id != VARSAYILAN_ALAN_ID else "",
        }

    ajan.dersler = DersDefteri(veri_dizini)

    async def _gorev_incele(run: Run) -> dict | None:
        if not ayarlar.oku().otomatik_inceleme:
            return None
        kok = run.calisma_koku or ajan.kok(run.proje_id)
        dosyalar = sorted({a.dosya for a in run.adimlar if a.dosya and a.arac in YAZAN_ARACLAR})
        if not kok or not dosyalar:
            return None

        def _diff() -> str:
            ortam = ortam_allowlist()
            kum.git_komut_sertlestir(ortam)
            res = subprocess.run(
                [
                    "git",
                    "-C",
                    kok,
                    "diff",
                    "--no-ext-diff",
                    "--no-textconv",
                    "HEAD",
                    "--",
                    *dosyalar,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=ortam,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return res.stdout if res.returncode == 0 else ""

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
    sohbet.ajan_olusturucu = ajan_deposu.olustur
    ajan_dinleyicileri: list = []

    def _ajan_araclari(run: Run) -> tuple[list, dict]:
        def ajana_mesaj(ajan: str, mesaj: str) -> dict:
            try:
                gonderen = ajan_deposu.getir(run.ajan_id)
                hedef = ajan_deposu.getir(ajan)
                if hedef.id == gonderen.id:
                    return {"hata": "Kendine mesaj atamazsin."}
                zincir = (gonderen.aktif_is.zincir if gonderen.aktif_is else 0) + 1
                ajan_deposu.kuyruga_ekle(
                    hedef.id,
                    KuyrukOgesi(
                        metin=f"[{gonderen.ad} ajanindan] {mesaj}",
                        kimden=f"ajan:{gonderen.id}",
                        zincir=zincir,
                        cevap_ajan=gonderen.id,
                    ),
                )
            except (UygulamaHatasi, ValueError) as e:
                return {"hata": getattr(e, "mesaj", str(e))}
            return {"gonderildi": hedef.ad, "not": "Cevap bitince sana yeni mesaj olarak gelir."}

        def ajan_notu(**kw: Any) -> dict:
            try:
                a = ajan_deposu.hafizaya_ekle(run.ajan_id, str(kw.get("not") or ""))
            except UygulamaHatasi as e:
                return {"hata": e.mesaj}
            return {"kaydedildi": True, "not_sayisi": len(a.hafiza)}

        return [AJANA_MESAJ_ARACI, AJAN_NOTU_ARACI], {
            "ajana_mesaj": ajana_mesaj,
            "ajan_notu": ajan_notu,
        }

    ajan.ajan_araclari = _ajan_araclari

    cli_isleri: dict[str, asyncio.Task] = {}
    cli_canli: dict[str, list[str]] = {}
    cc_dur = threading.Event()

    def _cc_esitle() -> dict:
        try:
            o = pluginler.claude_code_esitle(cc_dur)
            logger.info("Claude Code plugin esitleme: {}", o)
            return o
        except Exception as e:  # noqa: BLE001
            logger.warning("Claude Code plugin esitleme basarisiz: {}", e)
            return {"hata": str(e)}

    telegram = TelegramKanali(veri_dizini)
    _ana_loop: list[asyncio.AbstractEventLoop | None] = [None]
    _bildirilen_onaylar: set[str] = set()

    async def _onay_islem(onay_id: str, onayla: bool, kapsam: str = "tek") -> dict:
        sonuc = politika.onaylar.karar_ver(onay_id, onayla, kapsam).model_dump(mode="json")
        for r in run_deposu.liste():
            if r.durum is RunDurum.onay_bekliyor and any(a.onay_id == onay_id for a in r.adimlar):
                await ajan.devam(r.id)
        return sonuc

    def _telegram_onay_bildir(onay: Any) -> None:
        try:
            t = telegram.ayar()
            if not t.get("aktif") or not t.get("token") or not t.get("izinli"):
                return
            if onay.id in _bildirilen_onaylar:
                return
            if len(_bildirilen_onaylar) > 500:
                _bildirilen_onaylar.clear()
            _bildirilen_onaylar.add(onay.id)
            ozet = maskele((onay.ozet or "").strip())[:240]
            metin = (
                f"Onay bekleniyor ({onay.id})\n"
                f"Arac: {onay.arac} ({onay.yan_etki})\n"
                f"Islem: {ozet}\n"
                f"Onayla: /onayla {onay.id}\n"
                f"Reddet: /reddet {onay.id}"
            )
            try:
                asyncio.get_running_loop()
                asyncio.create_task(telegram.bildir_herkese(metin))
            except RuntimeError:
                if _ana_loop[0] is not None and not _ana_loop[0].is_closed():
                    asyncio.run_coroutine_threadsafe(telegram.bildir_herkese(metin), _ana_loop[0])
        except Exception as e:  # noqa: BLE001
            logger.warning("Telegram onay bildirimi planlanamadi: {}", maskele(str(e)))

    politika.onaylar.onay_bildir = _telegram_onay_bildir

    superajan_deposu = sa.SuperajanDeposu(veri_dizini)
    zamanlayici = Zamanlayici(veri_dizini)
    webhooklar = WebhookDeposu(veri_dizini)
    webhook_kilidi = asyncio.Lock()
    uzak_depo = uzak_mod.UzakDeposu(veri_dizini)
    uzak_sunucu = uzak_mod.UzakSunucu()
    akislar = AkisDeposu(veri_dizini)
    sablonlar = SablonDeposu(veri_dizini)
    uyanik = Uyanik()
    isitmalar: set[asyncio.Task] = set()
    agecidi = AgGecidi(agecidi_uygulamasi(yonetici, ayarlar, kapat))
    magaza = magaza or Magaza()
    indirici = Indirici(magaza, kayit, lambda: Path(ayarlar.oku().llm_dizin))
    testler = TestServisi(yonetici, ekler)
    editor_baglam: dict[str, Any] = {}
    sohbet.editor_baglam = lambda: dict(editor_baglam) if editor_baglam else {}

    def _aktif_kok() -> str:
        alan = sohbet.projeler.aktif() if sohbet.projeler else None
        return str(Path(alan.kokler[0])) if alan and alan.kokler else ""

    def _durum_ozet(is_: sa.IsEmri) -> tuple[str | None, str]:
        if not is_.runlar:
            return None, ""
        try:
            r = run_deposu.getir(is_.runlar[-1])
        except Exception:  # noqa: BLE001
            return "basarisiz", "Gorev kaydi bulunamadi."
        return str(r.durum.value), (r.sonuc.ozet or r.hata or "")

    def _is_ozet(is_: sa.IsEmri) -> dict:
        durum, ozet = _durum_ozet(is_)
        asama = sa.asama(is_, durum, ozet)
        bekleme = ""
        if asama == "sirada" and _aktif_kok() != is_.proje_kok:
            bekleme = "Projesi açık değil; proje açılınca başlar."
        soru: dict = {}
        if durum == "cevap_bekliyor":
            with contextlib.suppress(Exception):
                a = next(
                    x
                    for x in reversed(run_deposu.getir(is_.runlar[-1]).adimlar)
                    if x.arac == "soru_sor"
                )
                secenek = [str(s)[:120] for s in (a.argumanlar.get("secenekler") or [])][:4]
                soru = {"metin": str(a.argumanlar.get("soru", ""))[:600], "secenekler": secenek}
        return {
            **is_.model_dump(exclude={"gorev"}),
            "gorev": is_.gorev[:400],
            "asama": asama,
            "run": is_.runlar[-1] if is_.runlar else "",
            "run_durum": durum or "",
            "ozet": ozet[:600],
            "bekleme": bekleme,
            "soru": soru,
        }

    def _sohbet_is_ac(baslik: str, gorev: str) -> dict:
        kok = _aktif_kok()
        if not kok:
            raise UygulamaHatasi("Once bir proje ac.")
        if not wt.git_mi(Path(kok)):
            raise UygulamaHatasi("Proje bir git deposu degil; thread ayri dalda calisir.")
        is_ = superajan_deposu.olustur(
            baslik, gorev, kok, "sohbet", {"yazan": "model", "guc": "cikarim"}
        )
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
    sohbet.gunluk_maliyet = lambda: gunluk_maliyet_usd(run_deposu, oturumlar)

    async def _is_baslat(is_: sa.IsEmri) -> None:
        izole_kur = None
        if not is_.calisma_koku:
            proje = Path(is_.proje_kok)

            def izole_kur(run_id: str) -> tuple[str, str]:
                yol, dal = wt.olustur(proje, veri_dizini / "worktrees", run_id, "is")
                return str(yol), dal

        run = await ajan.baslat(
            sa.gorev_metni(is_, is_.bekleyen_mesaj),
            [],
            **_proje_modeli("uygulayici"),
            izole_kur=izole_kur,
            onceki=is_.runlar[-1] if is_.runlar else "",
            etkilesimli=True,
            calisma_koku=is_.calisma_koku,
        )
        is_ = superajan_deposu.getir(is_.id)
        is_.runlar = [*is_.runlar, run.id]
        is_.calisma_koku = is_.calisma_koku or run.calisma_koku
        is_.dal = is_.dal or run.dal
        is_.bekleyen_mesaj = ""
        is_.olay(f"Atama baslatildi ({run.id}).")
        superajan_deposu.guncelle(is_)

    def _gh_yokla() -> dict:
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
            if mevcut and mevcut.durum != "durduruldu":
                mevcut.bekleyen_mesaj = maskele(x["metin"])[:4000]
                mevcut.durum, mevcut.onay_bekliyor = "acik", a.mod == "gozle"
                if mevcut.calisma_koku and not Path(mevcut.calisma_koku).is_dir():
                    mevcut.calisma_koku, mevcut.dal = "", ""
                mevcut.olay(f"GitHub takip: @{x['login']}")
                superajan_deposu.guncelle(mevcut)
                takip += 1
            else:
                ilk_satir = x["metin"].splitlines()[0][:80] if x["metin"] else ""
                superajan_deposu.olustur(
                    x["baslik"] or ilk_satir or konu,
                    sa.github_gorev(a.depo, x),
                    a.proje_kok,
                    "github",
                    {"yazan": x["login"], "guc": "acik", "mod": a.mod},
                    [konu],
                    a.mod == "gozle",
                )
                acilan += 1
        superajan_deposu.github_yaz(
            a, [*g["gorulen"], *(x["anahtar"] for x in yeni)], {"c": e1, "i": e2}
        )
        return {"durum": "tamam", "acilan": acilan, "takip": takip}

    def _teslim(iid: str) -> dict:
        is_ = superajan_deposu.getir(iid)
        if is_.pr_url:
            return {"durum": "zaten", "pr_url": is_.pr_url}
        if not is_.calisma_koku or not Path(is_.calisma_koku).is_dir() or not is_.dal:
            raise UygulamaHatasi("Bu is emrinin teslim edilecek dali yok.")
        depo = superajan_deposu.github()["ayar"].depo
        kok = Path(is_.calisma_koku)
        wt._git(kok, "add", "-A")
        wt._git(
            kok,
            "-c",
            "user.name=Kairo",
            "-c",
            "user.email=ajan@yerel",
            "commit",
            "-m",
            f"Is emri: {is_.baslik}"[:200],
        )
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
            sa.gh(
                "issue",
                "comment",
                k.split("#")[-1],
                "--repo",
                k.split("#")[0],
                "--body",
                f"{sa.ISARET}\nKairo PR acti: {url}",
            )
        is_ = superajan_deposu.getir(iid)
        is_.pr_url = url
        is_.olay(f"Teslim: {url}")
        superajan_deposu.guncelle(is_)
        return {"durum": "acildi", "pr_url": url}

    def _pr_durumlari() -> None:
        for is_ in [x for x in superajan_deposu.liste() if x.durum == "acik" and x.pr_url]:
            kod, cikti = sa.gh("pr", "view", is_.pr_url, "--json", "state", "-q", ".state")
            if kod == 0 and cikti.strip() in ("MERGED", "CLOSED"):
                is_.durum = "bitti"
                is_.olay(f"PR {cikti.strip().lower()}.")
                superajan_deposu.guncelle(is_)

    gh_zaman = {"son": 0.0}

    async def _gh_tick() -> None:
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
                with contextlib.suppress(Exception):
                    if run_deposu.getir(is_.runlar[-1]).sonuc.dogrulandi:
                        await asyncio.to_thread(_teslim, is_.id)
        await asyncio.to_thread(_pr_durumlari)

    async def _superajan_tick() -> None:
        try:
            await _gh_tick()
        except Exception as e:  # noqa: BLE001
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
            except Exception as e:  # noqa: BLE001
                is_ = superajan_deposu.getir(is_.id)
                is_.durum = "durduruldu"
                is_.olay(f"Baslatilamadi: {e}")
                superajan_deposu.guncelle(is_)

    ajan.takim = TakimPanosu(veri_dizini)
    ajan.uzantilar = uzantilar

    def ajan_profilleri(run: Run) -> dict:
        profiller = pluginler.ajan_profilleri()
        alan = projeler.getir(run.proje_id) if run.proje_id else sohbet.aktif_alan()
        dizinler = [Path.home() / ".claude" / "agents"]
        if alan.talimat_okunur_mu():
            dizinler.extend(Path(kok) / ".claude" / "agents" for kok in alan.kokler)
        for dizin in dizinler:
            for dosya in sorted(dizin.glob("*.md")):
                try:
                    profil = ccp.ajan_profili(dosya)
                except (OSError, ValueError):
                    continue
                profiller[profil["ad"]] = profil
        return profiller

    ajan.ajan_profilleri = ajan_profilleri

    def alt_worktree_kur(run: Run, cocuk_id: str) -> tuple[str, str]:
        alan = projeler.getir(run.proje_id) if run.proje_id else sohbet.aktif_alan()
        if not alan.kokler or alan.id == VARSAYILAN_ALAN_ID:
            raise UygulamaHatasi("Alt ajan worktree'si icin Git projesi acin.")
        yol, dal = wt.olustur(Path(alan.kokler[0]), veri_dizini / "worktrees", cocuk_id, "alt-ajan")
        return str(yol), dal

    ajan.alt_worktree_kur = alt_worktree_kur

    BITMIS_DURUMLAR = {"basarili", "dogrulanmadi", "basarisiz", "iptal"}  # noqa: N806
    HEDEF_ISARETI = "HEDEF_TAMAM"  # noqa: N806

    def _run_durumu(run_id: str) -> str:
        try:
            return str(run_deposu.getir(run_id).durum.value)
        except Exception:  # noqa: BLE001
            return "basarisiz"

    def _rutin_hedefi(z: Any, onek: str) -> str:
        hedef = f"[{onek}: {z.ad}] {z.hedef}"
        if z.davranis == "bildir":
            hedef += (
                "\n\nYALNIZ BILDIR: dosya yazma, komut, gonderme gibi hicbir degisiklik "
                "yapma; yalniz incele ve kullanicinin bilmesi gerekenleri raporla."
            )
        if z.bitis_kosulu:
            hedef += (
                f"\n\nBITIS KOSULU: {z.bitis_kosulu}\nBu kosul artik saglaniyorsa "
                f"raporunun ilk satirina tam olarak {HEDEF_ISARETI} yaz."
            )
        return hedef

    async def _tetikle(t: Tetik) -> None:
        z = next((x for x in zamanlayici.liste() if x.id == t.zamanlama), None)
        alan = sohbet.projeler.aktif() if sohbet.projeler else None
        if (
            z is None
            or alan is None
            or not alan.kokler
            or Path(alan.kokler[0]) != Path(z.proje_kok)
        ):
            zamanlayici.baslatildi(t, "", "zamanlamanin projesi acik degil")
            return
        try:
            run = await ajan.baslat(
                _rutin_hedefi(z, "zamanlanmis"),
                [],
                Butce(max_adim=z.max_adim),
                model=ayarlar.oku().aktif_model,
            )
            zamanlayici.baslatildi(t, run.id)
        except Exception as e:  # noqa: BLE001
            zamanlayici.baslatildi(t, "", str(e))

    async def zamanlayici_tick(simdi: datetime | None = None) -> list[Tetik]:
        tetikler = await asyncio.to_thread(
            zamanlayici.tick, simdi or datetime.now(UTC), _run_durumu
        )
        for t in tetikler:
            await _tetikle(t)
        for z in zamanlayici.liste():
            if not z.bitis_kosulu or not z.aktif or not z.son_run:
                continue
            with contextlib.suppress(Exception):
                r = run_deposu.getir(z.son_run)
                if r.durum in BITMIS_RUN and r.sonuc.ozet.lstrip().startswith(HEDEF_ISARETI):
                    zamanlayici.guncelle(z.id, {"aktif": False})
                    if ayarlar.oku().bildirim_zamanlama:
                        await asyncio.to_thread(
                            mda.bildirim, URUN_ADI, f"Rutin hedefine ulasti ve durdu: {z.ad}"
                        )
        return tetikler

    def _isit_baglam() -> None:
        try:
            ajan_baglami("")
        except Exception as e:  # noqa: BLE001
            logger.debug("Baglam isitma atlandi: {}", e)

    app_tutucu: list[FastAPI] = []

    def _cc_izin(baglam: str) -> dict | None:
        if not app_tutucu:
            return None
        uyg = app_tutucu[0]
        adres = getattr(uyg.state, "izin_adresi", "")
        if not adres:
            return None
        return {"url": adres, "anahtar": uyg.state.cc_izin_anahtari, "baglam": baglam}

    ajan.cli_izin = _cc_izin
    sohbet.cli_izin = lambda b: _cc_izin(f"sohbet:{b}")

    async def _cli_baslat(a: Any, oge: Any) -> str:
        cli_canli[a.id] = []
        digerleri = [x for x in ajan_deposu.liste() if x.id != a.id]
        ek = ajan_deposu.sistem_metni(a, digerleri)
        is_id = f"cli:{uuid.uuid4().hex[:10]}"

        async def calis() -> Any:
            return await cli_ajan.calistir(
                a.saglayici,
                oge.metin,
                ajan_deposu.klasor(a),
                oturum=a.cli_oturum,
                tam_yetki=ayarlar.oku().tam_yetki,
                ek_sistem=ek,
                model=a.model,
                canli=cli_canli[a.id],
                izin=_cc_izin(f"ajan:{a.id}"),
            )

        cli_isleri[a.id] = asyncio.create_task(calis())
        return is_id

    def _cli_sonucu(a: Any) -> tuple[str, str] | None:
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
        for a in ajan_deposu.liste():
            if a.aktif_run and a.aktif_run.startswith("cli:"):
                bitti = _cli_sonucu(a)
                if bitti is None:
                    continue
                durum, ozet = bitti
            elif a.aktif_run and a.aktif_run != "baslatiliyor":
                try:
                    r = run_deposu.getir(a.aktif_run)
                except Exception:  # noqa: BLE001
                    r = None
                if r is not None and r.durum not in BITMIS_RUN:
                    continue
                durum = str(r.durum.value) if r else "basarisiz"
                ozet = ((r.sonuc.ozet or r.hata) if r else "Gorev kaydi bulunamadi.") or durum
            else:
                durum = ""
            if durum:
                a, is_ = ajan_deposu.bitti(a.id, a.aktif_run, durum, ozet)
                if is_ and is_.cevap_ajan:
                    try:
                        ajan_deposu.kuyruga_ekle(
                            is_.cevap_ajan,
                            KuyrukOgesi(
                                metin=f"[{a.ad} cevabi ({durum})] {ozet}",
                                kimden=f"ajan:{a.id}",
                                zincir=is_.zincir,
                            ),
                        )
                    except (UygulamaHatasi, Bulunamadi) as e:
                        logger.warning(f"Ajan cevabi iletilemedi: {e}")
                for dinle in ajan_dinleyicileri:
                    try:
                        await dinle(a, is_, durum, ozet)
                    except Exception as e:  # noqa: BLE001
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
                    oge.metin,
                    model=a.model or ayarlar.oku().aktif_model,
                    onceki=a.son_run,
                    ajan_id=a.id,
                    ek_sistem=ajan_deposu.sistem_metni(a, digerleri),
                    calisma_koku=str(ajan_deposu.klasor(a)),
                )
                ajan_deposu.basladi(a.id, run.id)
            except Exception as e:  # noqa: BLE001
                ajan_deposu.baslamadi(a.id, getattr(e, "mesaj", str(e)))

    async def _telegram_mesaj(chat: int, metin: str, _ad: str) -> str | None:
        t = telegram.ayar()
        parcalar = metin.strip().split()
        komut = parcalar[0].lower().split("@", 1)[0] if parcalar else ""
        if komut in ("/start", "/yardim", "/help"):
            liste = ", ".join(x.ad for x in ajan_deposu.liste()) or "yok"
            return (
                f"Kairo'ya bagli. Ajanlar: {liste}\nMesajin varsayilan ajana gider. "
                "Baska ajana: '/ajan Ad mesaj'. Durum: /durum\n"
                "Onaylar: /onaylar, /onayla <id>, /reddet <id>"
            )
        if komut == "/durum":
            return (
                "\n".join(
                    f"{x.avatar} {x.ad}: {x.ozet()['durum']}, {len(x.kuyruk)} sirada"
                    for x in ajan_deposu.liste()
                )
                or "Ajan yok."
            )
        if komut == "/onaylar":
            bekleyen = [o for o in politika.onaylar.gecmis(50) if o.get("karar") == "bekliyor"]
            if not bekleyen:
                return "Bekleyen onay yok."
            satirlar = [
                f"- {o['id']} | {o['arac']}: {maskele(str(o.get('ozet', '')).strip())[:100]}\n"
                f"  /onayla {o['id']}  /reddet {o['id']}"
                for o in bekleyen[:10]
            ]
            return "Bekleyen onaylar:\n" + "\n".join(satirlar)
        if komut in ("/onayla", "/reddet"):
            if len(parcalar) < 2:
                return f"Kullanim: {komut} <onay_id>"
            onay_id = parcalar[1].strip()
            onayla = komut == "/onayla"
            try:
                sonuc = await _onay_islem(onay_id, onayla, "tek")
            except (YetkiYok, UygulamaHatasi) as e:
                return getattr(e, "mesaj", str(e))
            durum_metni = "Onaylandi" if onayla else "Reddedildi"
            return f"{durum_metni}: {sonuc['id']} ({sonuc['arac']})"
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
        a = ajan_deposu.kuyruga_ekle(hedef, KuyrukOgesi(metin=metin, kimden=f"telegram:{chat}"))
        await _ajan_dagit()
        sira = len(ajan_deposu.getir(a.id).kuyruk)
        return f"{a.avatar} {a.ad} ise aldi" + (f" ({sira} is sirada)." if sira else ".")

    async def _telegram_cevap(a: Any, is_: Any, durum: str, ozet: str) -> None:
        if is_ and is_.kimden.startswith("telegram:"):
            chat = int(is_.kimden.split(":", 1)[1])
            await telegram.gonder(chat, f"{a.avatar} {a.ad} ({durum}):\n{ozet}")

    ajan_dinleyicileri.append(_telegram_cevap)

    async def _webhook_isle(wid: str) -> str:
        async with webhook_kilidi:
            w = webhooklar.getir(wid)
            if w.ajan:
                sira = webhooklar.siradaki(wid)
                if sira is None:
                    return "bos"
                w, olay = sira
                a = ajan_deposu.kuyruga_ekle(
                    w.ajan,
                    KuyrukOgesi(metin=hedef_olustur(w, olay["olay"]), kimden=f"webhook:{w.id}"),
                )
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
                hedef_olustur(w, olay["olay"]),
                [],
                Butce(max_adim=w.max_adim),
                model=ayarlar.oku().aktif_model,
            )
            w = webhooklar.getir(wid)
            w.son_run = run.id
            webhooklar.kaydet(w)
            return f"basladi:{run.id}"

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

    async def _zamanlayici_dongusu() -> None:
        while True:
            try:
                await zamanlayici_tick()
                for w in webhooklar.liste():
                    await _webhook_isle(w["id"])
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Zamanlayici: {e}")
            await asyncio.sleep(30)

    kisayol_tutucu: list[mda.GenelKisayol] = []

    @asynccontextmanager
    async def omur(_: FastAPI):
        komutlar.loop = asyncio.get_running_loop()
        _ana_loop[0] = komutlar.loop
        a = ayarlar.oku()
        if gecit and a.sunucu_acik:
            await agecidi.baslat(a.sunucu_port)
        zd = asyncio.create_task(_zamanlayici_dongusu()) if gecit else None
        ad_ = asyncio.create_task(_ajan_dongusu())
        if gecit:
            telegram.baslat(_telegram_mesaj)
            kisayol_tutucu[0].ayarla(a.hizli_kisayol)
            threading.Thread(target=_cc_esitle, name="cc-esitle", daemon=True).start()
            asyncio.get_running_loop().run_in_executor(None, _isit_baglam)
        if a.saglayici == "openrouter":
            asyncio.get_running_loop().run_in_executor(None, openrouter._tasima)
        yield
        cc_dur.set()
        if zd:
            zd.cancel()
        ad_.cancel()
        telegram.durdur()
        await uzak_sunucu.kapat()
        await ajan.kapat()
        mcp.kapat()
        uzantilar.kapat()
        kisayol_tutucu[0].kapat()
        for kz in sohbet.kod_zekasi.values():
            kz.kapat()
        if sohbet.tarayici.acik_mi():
            await asyncio.to_thread(sohbet.tarayici.kapat)
        await komutlar.hepsini_durdur()
        await agecidi.durdur()
        await yonetici.kapat()
        await magaza.kapat()
        await ollama.kapat()

    app = FastAPI(title=URUN_ADI, version=__version__, lifespan=omur)
    app_tutucu.append(app)
    app.state.one_getir = lambda: None
    kisayol = mda.GenelKisayol(lambda: app.state.one_getir())
    kisayol_tutucu.append(kisayol)

    oturum_anahtari = secrets.token_urlsafe(24)
    cc_izin_anahtari = secrets.token_urlsafe(32)
    skill_ice = SkillIceAktarici(veri_dizini, skiller)

    async def _ic_cagri(metod: str, yol: str, govde: Any) -> tuple[int, Any]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers={OTURUM_BASLIGI: oturum_anahtari},
            timeout=60,
        ) as c:
            res = await c.request(metod, yol, json=govde)
        try:
            return res.status_code, res.json()
        except ValueError:
            return res.status_code, {"hata": "Gecersiz cevap."}

    def alan_sohbetlerini_sil(alan_id: str) -> int:
        bagli = [o["id"] for o in oturumlar.liste() if o.get("alan", "") == alan_id]
        for oid in bagli:
            with contextlib.suppress(Bulunamadi):
                oturumlar.sil(oid)
        return len(bagli)

    # Testler ve dis bilesenlerle geriye donuk tam app.state sozlesmesi
    app.state.ajan_deposu = ajan_deposu
    app.state.superajan = superajan_deposu
    app.state.superajan_tick = _superajan_tick
    app.state.ajan_dagit = _ajan_dagit
    app.state.ajan_runner = ajan
    app.state.telegram = telegram
    app.state.telegram_mesaj = _telegram_mesaj
    app.state.politika = politika
    app.state.run_deposu = run_deposu
    app.state.guncelleme = guncelleme
    app.state.yonetici = yonetici
    app.state.sohbet = sohbet
    app.state.agecidi = agecidi
    app.state.oturum_anahtari = oturum_anahtari
    app.state.cc_izin_anahtari = cc_izin_anahtari
    app.state.editor_baglam = editor_baglam
    app.state.kullanici_komut_dizini = lambda: Path.home() / ".claude" / "commands"
    app.state.arac_paketleri = arac_paketleri
    app.state.skill_ice = skill_ice
    app.state.zamanlayici_tick = zamanlayici_tick
    app.state.uzak_depo = uzak_depo
    app.state.uzak_ic_cagri = _ic_cagri
    app.state.sablonlar = sablonlar

    @app.middleware("http")
    async def _loopback_koruma(istek: Request, sonraki):
        try:
            konak = urlsplit(f"//{istek.headers.get('host') or ''}").hostname
        except ValueError:
            konak = None
        if not yerel_host_mu(konak):
            return JSONResponse({"hata": "Yalniz bu bilgisayardan erisilir."}, status_code=403)
        kaynak = istek.headers.get("origin") or istek.headers.get("referer") or ""
        oauth_geri = istek.method == "GET" and istek.url.path == "/api/mcp/oauth/geri"
        if kaynak and not oauth_geri:
            try:
                kaynak_konak = urlsplit(kaynak).hostname
            except ValueError:
                kaynak_konak = None
            if not yerel_host_mu(kaynak_konak):
                return JSONResponse({"hata": "Dis kaynakli istek reddedildi."}, status_code=403)
        yol = istek.url.path
        korunan = (
            yol.startswith("/api")
            and yol != "/api/bilgi"
            and not yol.startswith("/api/webhook/")
            and yol != "/api/mcp/oauth/geri"
        )
        gelen = istek.headers.get(OTURUM_BASLIGI)
        if (
            yol == "/api/cc-izin"
            and istek.method == "POST"
            and hmac.compare_digest(gelen or "", cc_izin_anahtari)
        ):
            return await sonraki(istek)
        if korunan and gelen != oturum_anahtari:
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

    baglam = SimpleNamespace(
        app=app,
        veri_dizini=veri_dizini,
        gecit=gecit,
        kayit=kayit,
        ayarlar=ayarlar,
        oturumlar=oturumlar,
        ekler=ekler,
        guncelleme=guncelleme,
        openrouter=openrouter,
        ollama=ollama,
        saglayicilar=saglayicilar,
        yonetici=yonetici,
        talimatlar=talimatlar,
        skiller=skiller,
        skill_ice=skill_ice,
        projeler=projeler,
        politika=politika,
        checkpointler=checkpointler,
        komutlar=komutlar,
        sohbet=sohbet,
        pluginler=pluginler,
        hafiza=hafiza,
        hooklar=hooklar,
        mcp=mcp,
        uzantilar=uzantilar,
        composio=composio,
        run_deposu=run_deposu,
        ajan=ajan,
        ajan_deposu=ajan_deposu,
        cli_isleri=cli_isleri,
        cli_canli=cli_canli,
        telegram=telegram,
        telegram_mesaj=_telegram_mesaj,
        superajan_deposu=superajan_deposu,
        zamanlayici=zamanlayici,
        webhooklar=webhooklar,
        uzak_depo=uzak_depo,
        uzak_sunucu=uzak_sunucu,
        akislar=akislar,
        sablonlar=sablonlar,
        uyanik=uyanik,
        kisayol=kisayol,
        isitmalar=isitmalar,
        agecidi=agecidi,
        magaza=magaza,
        indirici=indirici,
        testler=testler,
        editor_baglam=editor_baglam,
        oturum_anahtari=oturum_anahtari,
        ajan_baglami=ajan_baglami,
        model_yetenegi=model_yetenegi,
        ollama_yetenek_hazirla=_ollama_yetenek_hazirla,
        proje_modeli=_proje_modeli,
        onay_islem=_onay_islem,
        alan_sohbetlerini_sil=alan_sohbetlerini_sil,
        cc_esitle=_cc_esitle,
        aktif_kok=_aktif_kok,
        durum_ozet=_durum_ozet,
        is_ozet=_is_ozet,
        teslim=_teslim,
        gh_yokla=_gh_yokla,
        superajan_tick=_superajan_tick,
        ajan_dagit=_ajan_dagit,
        rutin_hedefi=_rutin_hedefi,
        webhook_isle=_webhook_isle,
    )

    for router_mod in (
        ajan_ve_otomasyon,
        modeller,
        sohbet_hafiza,
        proje_ve_sistem,
        eklentiler,
    ):
        app.include_router(router_mod.router_olustur(baglam))

    web = web_dizini()

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(web_dizini() / "kairo.ico", media_type="image/x-icon")

    @app.get("/")
    async def ana_sayfa(istek: Request) -> Response:
        try:
            html = (web / "index.html").read_text(encoding="utf-8")
        except OSError:  # pragma: no cover
            return JSONResponse({"hata": "Arayuz dosyasi bulunamadi."}, status_code=500)
        anahtar = "uzak" if istek.headers.get("x-yas-uzak-cihaz") else oturum_anahtari
        etiket = f'<meta name="yas-oturum" content="{anahtar}">'
        html = html.replace("</head>", f"  {etiket}\n</head>", 1)
        return Response(
            html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"}
        )

    if web.exists():
        app.mount("/web", TazeStatik(directory=web), name="web")
    else:  # pragma: no cover
        logger.error("Arayuz klasoru yok: {}", web)
    return app


__all__ = [
    "ACIK_YOLLAR",
    "DIKTE_MAX_BAYT",
    "DIKTE_MAX_SN",
    "DIKTE_SESSIZ",
    "DIKTE_TALIMATI",
    "DIKTE_UZAK",
    "DIKTE_UZAK_SESSIZ",
    "HAFIZA_ARACI",
    "HAFIZA_TALIMATI",
    "HAFIZA_YARGI_ARACI",
    "OTURUM_BASLIGI",
    "OZET_ONAY",
    "OZET_TALIMATI",
    "PR_ALANLARI",
    "PR_URL",
    "UPLOAD_PARCA_BAYT",
    "AdIstegi",
    "AjanRunKaydi",
    "AltOturumIstegi",
    "AnahtarIstegi",
    "CcIzinIstegi",
    "DurdurIstegi",
    "EditorBaglamIstegi",
    "EntegreIstegi",
    "GeriAlIstegi",
    "GeriSarIstegi",
    "GirdiIstegi",
    "GizliProjeIstegi",
    "GorevIstegi",
    "GorevMesaji",
    "GuvenIstegi",
    "HafizaIstegi",
    "HunkIstegi",
    "IndirIstegi",
    "IsEmriIstegi",
    "KararIstegi",
    "KartKomutIstegi",
    "ModelIstegi",
    "ModellerIstegi",
    "ModIstegi",
    "OllamaIndirIstegi",
    "OnayIstegi",
    "OneriRedIstegi",
    "ProjeIstegi",
    "SaglayiciIstegi",
    "SkillDurumIstegi",
    "SkillIceAdIstegi",
    "SkillIceIstegi",
    "SkillIceKurIstegi",
    "SkillIstegi",
    "SonrakiOneriIstegi",
    "TalimatIstegi",
    "TazeStatik",
    "YolIstegi",
    "dogrulama_mesaji",
    "dogrula",
    "shutil",
    "sse",
    "uygulama_olustur",
]
