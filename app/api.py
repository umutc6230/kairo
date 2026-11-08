"""FastAPI uygulamasi: arayuz dosyalari + /api uclari. Uzun isler SSE (text/event-stream) akitir."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, ValidationError

from app import URUN_ADI, URUN_SAHIBI, URUN_SAHIBI_GITHUB, URUN_SAHIBI_X, __version__
from app.config import web_dizini
from app.exceptions import UygulamaHatasi, YerelLLMHatasi
from app.services.araclar import ARACLAR, ORNEK_ISTEMLER
from app.services.ayarlar import AyarDeposu
from app.services.ekler import EkDeposu
from app.services.model_yonetici import LLMFabrikasi, ModelYonetici
from app.services.oturumlar import OturumDeposu
from app.services.sohbet import MesajIstegi, SohbetServisi
from app.services.testler import (
    ORNEK_SATIRLAR,
    AracIstegi,
    KarsilastirmaIstegi,
    OcrIstegi,
    PaketIstegi,
    TestServisi,
    ornek_belge,
)
from app.services.yerel_llm import DUSUNME_SECENEKLERI, YerelLLM


class AdIstegi(BaseModel):
    baslik: str


class ModelIstegi(BaseModel):
    model: str | None = None


class DurdurIstegi(BaseModel):
    harici: bool = False


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


def uygulama_olustur(veri_dizini: Path, fabrika: LLMFabrikasi = YerelLLM) -> FastAPI:
    ayarlar = AyarDeposu(veri_dizini)
    oturumlar = OturumDeposu(veri_dizini)
    ekler = EkDeposu(veri_dizini)
    yonetici = ModelYonetici(ayarlar, fabrika)
    sohbet = SohbetServisi(yonetici, oturumlar, ekler)
    testler = TestServisi(yonetici, ekler)

    @asynccontextmanager
    async def omur(_: FastAPI):
        yield
        await yonetici.kapat()  # yalniz bizim baslattigimiz model sunucusunu durdurur

    app = FastAPI(title=URUN_ADI, version=__version__, lifespan=omur)
    app.state.yonetici = yonetici

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
        return await yonetici.hazirla(istek.model)

    @app.post("/api/model/durdur")
    async def model_durdur(istek: DurdurIstegi) -> dict:
        return await yonetici.durdur(harici=istek.harici)

    # ---- ayarlar ----
    @app.get("/api/ayarlar")
    async def ayar_oku() -> dict:
        return ayarlar.oku().model_dump()

    @app.put("/api/ayarlar")
    async def ayar_yaz(degisiklik: dict) -> dict:
        return ayarlar.guncelle(degisiklik).model_dump()

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
