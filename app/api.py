"""FastAPI uygulamasi: arayuz dosyalari + /api uclari. Uzun isler SSE (text/event-stream) akitir."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from app import URUN_ADI, URUN_SAHIBI, URUN_SAHIBI_GITHUB, URUN_SAHIBI_X, __version__
from app.config import web_dizini
from app.exceptions import UygulamaHatasi, YerelLLMHatasi
from app.services import sistem
from app.services.agecidi import AgGecidi, agecidi_uygulamasi
from app.services.araclar import ARACLAR, ORNEK_ISTEMLER
from app.services.ayarlar import AyarDeposu
from app.services.ekler import EkDeposu
from app.services.model_magaza import Indirici, Magaza, ModelKaydi, uyumluluk
from app.services.model_yonetici import LLMFabrikasi, ModelYonetici
from app.services.oturumlar import OturumDeposu
from app.services.skiller import SkillDeposu
from app.services.sohbet import MesajIstegi, SohbetServisi
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


class AdIstegi(BaseModel):
    baslik: str


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
) -> FastAPI:
    kayit = ModelKaydi(veri_dizini)
    kayit.yukle()  # magazadan indirilen modeller MODELLER'e (ayar dogrulamasindan once)
    ayarlar = AyarDeposu(veri_dizini)
    oturumlar = OturumDeposu(veri_dizini)
    ekler = EkDeposu(veri_dizini)
    yonetici = ModelYonetici(ayarlar, fabrika)
    talimatlar = TalimatDeposu(veri_dizini)
    skiller = skill_deposu or SkillDeposu(veri_dizini)
    sohbet = SohbetServisi(yonetici, oturumlar, ekler, talimatlar, skiller)
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
        await agecidi.durdur()
        await yonetici.kapat()  # yalniz bizim baslattigimiz model sunucusunu durdurur
        await magaza.kapat()

    app = FastAPI(title=URUN_ADI, version=__version__, lifespan=omur)
    app.state.yonetici = yonetici
    app.state.agecidi = agecidi

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
        veri = await dosya.read()
        return ekler.kaydet(dosya.filename or "dosya", veri).model_dump(exclude={"metin"})

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
        return skiller.olustur(istek.ad, istek.aciklama, istek.icerik).ozet()

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

    # ---- arayuz ----
    web = web_dizini()

    @app.get("/")
    async def ana_sayfa() -> Response:
        return FileResponse(web / "index.html", headers={"Cache-Control": "no-store"})

    if web.exists():
        app.mount("/web", StaticFiles(directory=web), name="web")
    else:  # pragma: no cover - paket hatasi
        logger.error("Arayuz klasoru yok: {}", web)
    return app
