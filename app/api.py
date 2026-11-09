"""FastAPI uygulamasi: arayuz dosyalari + /api uclari. Uzun isler SSE (text/event-stream) akitir."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from app import URUN_ADI, URUN_SAHIBI, URUN_SAHIBI_GITHUB, URUN_SAHIBI_X, __version__
from app.agent import review as rv
from app.agent.checkpoints import CheckpointDeposu
from app.agent.izolasyon import adaptor_olustur
from app.agent.policy import PolitikaMotoru, yerel_host_mu
from app.agent.runner import AgentRunner, Butce, RunDeposu, RunDurum, olay_akisi
from app.agent.terminal import KomutServisi
from app.agent.workspaces import Guven, Mod, WorkspaceDeposu
from app.agent.yetenek import ModelYetenegi, dogrula, uzak_yetenek, yerel_yetenek
from app.config import web_dizini
from app.exceptions import GecersizEk, OnayGerekli, UygulamaHatasi, YerelLLMHatasi
from app.services import ekler as ekler_modulu
from app.services import sistem
from app.services import skiller as skl
from app.services.agecidi import AgGecidi, agecidi_uygulamasi
from app.services.araclar import ARACLAR, ORNEK_ISTEMLER
from app.services.artifactler import ARTIFACT_ARACI, ONIZLEME_CSP, ArtifactDeposu
from app.services.ayarlar import AyarDeposu
from app.services.ekler import EkDeposu
from app.services.hafiza import HafizaDeposu
from app.services.model_magaza import Indirici, Magaza, ModelKaydi, uyumluluk
from app.services.model_yonetici import LLMFabrikasi, ModelYonetici
from app.services.openrouter import OpenRouterDeposu
from app.services.oturumlar import OturumDeposu
from app.services.skiller import SkillDeposu
from app.services.sohbet import VARSAYILAN_ALAN_ID, MesajIstegi, SohbetServisi
from app.services.talimatlar import TalimatDeposu
from app.services.testler import (
    ORNEK_SATIRLAR,
    AracIstegi,
    KarsilastirmaIstegi,
    OcrIstegi,
    PaketIstegi,
    TestServisi,
    ornek_belge,
)
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


class OnayIstegi(BaseModel):
    onayla: bool


class GorevIstegi(BaseModel):
    hedef: str = Field(min_length=1, max_length=8000)
    kabul: list[str] = Field(default=[], max_length=20)
    butce: Butce = Field(default_factory=Butce)


class GorevMesaji(BaseModel):
    metin: str = Field(min_length=1, max_length=4000)


HAFIZA_ARACI = {
    "type": "function",
    "function": {
        "name": "hafizaya_ekle",
        "description": "Sonraki oturumlarda isine yarayacak KALICI bir proje bilgisini kaydeder "
        "(or. 'testler pytest -q ile calisir'). Sir, gecici durum ya da tahmin yazma.",
        "parameters": {
            "type": "object",
            "properties": {"metin": {"type": "string"}},
            "required": ["metin"],
        },
    },
}


class HafizaIstegi(BaseModel):
    metin: str = Field(min_length=1, max_length=1000)
    kapsam: str = Field(default="genel", max_length=40)
    guven: str = "orta"
    gecerlilik: str | None = None


class KararIstegi(BaseModel):
    adim: int
    karar: str


DIKTE_MAX_SN = 30  # Gemma 4 ses girisi ~30 sn
DIKTE_UZAK = "Dikte yalniz yerel Gemma 4 modeliyle calisir; ses buluta gonderilmez."
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


class AnahtarIstegi(BaseModel):
    anahtar: str = Field(max_length=300)


class ModelIstegi(BaseModel):
    model: str | None = None


class DurdurIstegi(BaseModel):
    harici: bool = False


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
) -> FastAPI:
    kayit = ModelKaydi(veri_dizini)
    kayit.yukle()  # magazadan indirilen modeller MODELLER'e (ayar dogrulamasindan once)
    ayarlar = AyarDeposu(veri_dizini)
    oturumlar = OturumDeposu(veri_dizini)
    ekler = EkDeposu(veri_dizini)
    openrouter = OpenRouterDeposu(veri_dizini, transport=or_transport)
    yonetici = ModelYonetici(ayarlar, fabrika, uzak=openrouter)
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

    skiller.proje_kaynaklari = proje_skill_kaynaklari
    hafiza = HafizaDeposu(veri_dizini)
    artifactler = ArtifactDeposu(veri_dizini)
    sohbet.hafiza = hafiza

    def ajan_baglami(hedef: str) -> tuple[str, list, dict]:
        alan = sohbet.aktif_alan()
        if sohbet.ajan_araclari(alan) is None:
            raise UygulamaHatasi("Ajan gorevi icin once bir proje acin.")
        a = ayarlar.oku()
        sistem, araclar_, isleyiciler, _ = sohbet.baglam_hazirla(a, hedef, [])
        if a.otomatik_ogrenme:  # kullanici actiysa ajan kalici not ekleyebilir (dusuk guven)
            araclar_ = [*araclar_, HAFIZA_ARACI]

            def hafizaya_ekle(metin: str) -> dict:
                try:
                    return hafiza.ekle(metin, kaynak="ajan", guven="dusuk", kapsam=alan.id)
                except UygulamaHatasi as e:
                    return {"hata": e.mesaj}

            isleyiciler = {**isleyiciler, "hafizaya_ekle": hafizaya_ekle}

        def artifact_olustur(ad: str, tur: str, icerik: str) -> dict:
            try:
                a = artifactler.olustur(ad, tur, icerik, kaynak="ajan")
            except UygulamaHatasi as e:
                return {"hata": e.mesaj}
            return {"artifact": a["id"], "ad": a["ad"], "tur": a["tur"], "boyut": a["boyut"]}

        araclar_ = [*araclar_, ARTIFACT_ARACI]
        isleyiciler = {**isleyiciler, "artifact_olustur": artifact_olustur}
        return sistem, araclar_, isleyiciler

    def model_yetenegi() -> ModelYetenegi:
        a = ayarlar.oku()
        if a.saglayici == "openrouter" and a.or_model:
            return uzak_yetenek(a.or_model, openrouter.liste_yolu)
        return yerel_yetenek(a.model, a.baglam_token)

    def onay_durumu(onay_id: str) -> str:
        return next(
            (o["karar"] for o in politika.onaylar.gecmis(500) if o["id"] == onay_id), "bekliyor"
        )

    run_deposu = RunDeposu(veri_dizini)
    run_deposu.kurtar()  # onceki oturumda yarim kalanlar: belirsiz yan etki kullaniciya sorulur
    ajan = AgentRunner(
        run_deposu,
        ajan_baglami,
        lambda: yonetici.kullan(),
        onay_durumu,
        yetenek=model_yetenegi,
        hafiza=lambda: (
            hafiza.sistem_metni(sohbet.aktif_alan().id) if ayarlar.oku().hafiza_acik else ""
        ),
    )
    isitmalar: set[asyncio.Task] = set()
    agecidi = AgGecidi(agecidi_uygulamasi(yonetici, ayarlar, kapat))
    magaza = magaza or Magaza()
    indirici = Indirici(magaza, kayit, lambda: Path(ayarlar.oku().llm_dizin))
    testler = TestServisi(yonetici, ekler)

    @asynccontextmanager
    async def omur(_: FastAPI):
        a = ayarlar.oku()
        if a.sunucu_acik:
            await agecidi.baslat(a.sunucu_port)
        yield
        await ajan.kapat()  # calisan gorevler guvenli sinirda duraklatilir
        await komutlar.hepsini_durdur()  # yetim test/dev-server surecleri kalmasin
        await agecidi.durdur()
        await yonetici.kapat()  # yalniz bizim baslattigimiz model sunucusunu durdurur
        await magaza.kapat()

    app = FastAPI(title=URUN_ADI, version=__version__, lifespan=omur)
    app.state.yonetici = yonetici
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
        if kaynak:
            try:
                kaynak_konak = urlsplit(kaynak).hostname
            except ValueError:
                kaynak_konak = None
            if not yerel_host_mu(kaynak_konak):
                return JSONResponse({"hata": "Dis kaynakli istek reddedildi."}, status_code=403)
        yol = istek.url.path
        korunan = yol.startswith("/api") and not yol.startswith("/api/bilgi")
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

    @app.get("/api/openrouter/modeller")
    async def or_modeller(yenile: bool = False) -> dict:
        return await openrouter.modeller(yenile)

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
    @app.get("/api/oturumlar")
    async def oturum_liste(q: str = "") -> list[dict]:
        return oturumlar.liste(q)

    @app.post("/api/oturumlar")
    async def oturum_yeni() -> dict:
        return oturumlar.olustur().model_dump()

    @app.get("/api/oturumlar/{oturum_id}")
    async def oturum_getir(oturum_id: str) -> dict:
        return oturumlar.getir(oturum_id).model_dump()

    # ---- oturum catal / temizle / disa aktar (A4.5); temizle hafizaya dokunmaz ----
    @app.post("/api/oturumlar/{oturum_id}/catal")
    async def oturum_catal(oturum_id: str) -> dict:
        return oturumlar.catal(oturum_id).model_dump()

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

    # ---- hafiza (A4.4) ----
    @app.get("/api/hafiza")
    async def hafiza_listesi(kapsam: str | None = None) -> dict:
        return {"kayitlar": hafiza.liste(kapsam)}

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

    @app.post("/api/review")
    async def review_yap(staged: bool = False) -> dict:
        alan, kayit = _proje_git()
        d = await asyncio.to_thread(kayit.git.git_diff, "", staged)
        if d.get("hata"):
            raise UygulamaHatasi(d["hata"])
        diff = d.get("diff") or ""
        if not diff.strip():
            return {"ozet": "Incelenecek degisiklik yok (git diff bos).", "bulgular": [],
                    "dosyalar": [], "diff_kesildi": False}  # fmt: skip
        kural = rv.review_md_oku(alan.izinli_kokler) if alan.talimat_okunur_mu() else ""
        async with yonetici.kullan() as llm:
            try:
                cevap = await llm.json_cikti(
                    rv.istem(diff, kural), rv.SEMA, ad="review", max_tokens=3000,
                    dusunme="kapali",
                )  # fmt: skip
            except YerelLLMHatasi as e:
                raise UygulamaHatasi(f"Review yapilamadi: {e}") from e
        sonuc = rv.sonuclandir(cevap if isinstance(cevap, dict) else {}, diff)
        sonuc["review_md"] = bool(kural)
        return sonuc

    # ---- artifact'ler (A5.5): icerik yalniz oturumlu API ile; onizleme sandbox iframe ----
    @app.get("/api/artifactler")
    async def artifact_listesi() -> dict:
        return {"artifactler": artifactler.liste()}

    @app.get("/api/artifactler/{artifact_id}")
    async def artifact_getir(artifact_id: str) -> dict:
        meta, icerik = artifactler.getir(artifact_id)
        return {**meta, "icerik": icerik, "csp": ONIZLEME_CSP}

    @app.delete("/api/artifactler/{artifact_id}")
    async def artifact_sil(artifact_id: str) -> dict:
        return artifactler.sil(artifact_id)

    # ---- model yetenegi (A4.7) ----
    @app.get("/api/model/yetenek")
    async def model_yetenek() -> dict:
        return model_yetenegi().model_dump()

    @app.patch("/api/oturumlar/{oturum_id}")
    async def oturum_adlandir(oturum_id: str, istek: AdIstegi) -> dict:
        return oturumlar.yeniden_adlandir(oturum_id, istek.baslik).model_dump()

    @app.delete("/api/oturumlar/{oturum_id}")
    async def oturum_sil(oturum_id: str) -> dict:
        oturumlar.sil(oturum_id)
        return {"silindi": oturum_id}

    @app.post("/api/oturumlar/{oturum_id}/mesaj")
    async def mesaj(oturum_id: str, istek: MesajIstegi) -> StreamingResponse:
        oturumlar.getir(oturum_id)  # yoksa 404 (akis baslamadan)
        return sse(sohbet.mesaj_gonder(oturum_id, istek))

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
    async def magaza_ara(q: str = "heretic", gorsel: bool = True) -> dict:
        s = _sistem_bilgisi()
        bellek = {"toplam_gb": s["toplam_ram_gb"], "bos_gb": s["bos_ram_gb"]}
        yuklu = {p.dosya for p in MODELLER.values()}
        sonuclar = []
        for a in await magaza.ara(q or "heretic"):
            if gorsel and not a["gorsel"]:
                continue
            a = {**a, "uyumluluk": uyumluluk(a["tahmini_gb"], bellek, s["disk_bos_gb"])}
            a["yuklu"] = a["model_dosyasi"] in yuklu
            sonuclar.append(a)
        return {"sistem": s, "sonuclar": sonuclar}

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

    # ---- talimatlar ve skill'ler ----
    @app.get("/api/talimatlar")
    async def talimat_oku() -> dict:
        a = ayarlar.oku()
        kaynaklar = talimatlar.kaynaklar(claude=True, uygulama=False)
        return {
            "claude": [{**k, "metin": k["metin"][:4000]} for k in kaynaklar],
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

    @app.post("/api/projeler")
    async def proje_ac(istek: ProjeIstegi) -> dict:
        return projeler.ac(istek.yol, istek.ad, istek.guven).model_dump(mode="json")

    @app.post("/api/projeler/kapat")
    async def proje_kapat() -> dict:
        projeler.kapat()
        return {"aktif": None, "etkin": sohbet.aktif_alan().model_dump(mode="json")}

    @app.delete("/api/projeler/{alan_id}")
    async def proje_sil(alan_id: str) -> dict:
        projeler.sil(alan_id)
        return {"silindi": alan_id}

    @app.put("/api/projeler/{alan_id}/mod")
    async def proje_mod(alan_id: str, istek: ModIstegi) -> dict:
        return projeler.mod_ayarla(alan_id, istek.mod).model_dump(mode="json")

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

    @app.post("/api/onaylar/{onay_id}")
    async def onay_karar(onay_id: str, istek: OnayIstegi) -> dict:
        sonuc = politika.onaylar.karar_ver(onay_id, istek.onayla).model_dump(mode="json")
        for r in run_deposu.liste():  # bu onayi bekleyen ajan gorevi kaldigi yerden surer
            if r.durum is RunDurum.onay_bekliyor and any(a.onay_id == onay_id for a in r.adimlar):
                await ajan.devam(r.id)
        return sonuc

    # ---- ajan gorevleri (A3) ----
    @app.post("/api/gorevler")
    async def gorev_baslat(istek: GorevIstegi) -> dict:
        ajan_baglami(istek.hedef)  # proje yoksa hemen Turkce hata
        dogrula(model_yetenegi(), araclar_gerekli=True, dusunme=ayarlar.oku().dusunme)
        run = await ajan.baslat(
            istek.hedef, istek.kabul, istek.butce, model=ayarlar.oku().aktif_model
        )
        return run.ozet()

    @app.get("/api/gorevler")
    async def gorev_listesi() -> dict:
        return {"gorevler": [r.ozet() for r in run_deposu.liste()[:50]]}

    @app.get("/api/gorevler/{run_id}")
    async def gorev_getir(run_id: str) -> dict:
        return run_deposu.getir(run_id).ozet()

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

    @app.post("/api/komutlar/{is_id}/durdur")
    async def komut_durdur_ucu(is_id: str) -> dict:
        return await komutlar.durdur(is_id)

    # ---- arayuz ----
    web = web_dizini()

    @app.get("/")
    async def ana_sayfa() -> Response:
        """index.html'e oturum anahtarini gomer: baska origin bu sayfayi OKUYAMAZ (A1.9)."""
        try:
            html = (web / "index.html").read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - paket hatasi
            return JSONResponse({"hata": "Arayuz dosyasi bulunamadi."}, status_code=500)
        etiket = f'<meta name="yas-oturum" content="{oturum_anahtari}">'
        html = html.replace("</head>", f"  {etiket}\n</head>", 1)
        return Response(
            html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"}
        )

    if web.exists():
        app.mount("/web", TazeStatik(directory=web), name="web")
    else:  # pragma: no cover - paket hatasi
        logger.error("Arayuz klasoru yok: {}", web)
    return app
