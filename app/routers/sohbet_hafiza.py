"""Sohbet oturumlari, mesaj akisi, ekler, ses dikte ve kalici hafiza uclari."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from loguru import logger

from app.exceptions import GecersizEk, UygulamaHatasi, YerelLLMHatasi
from app.routers import (
    DIKTE_MAX_BAYT,
    DIKTE_MAX_SN,
    DIKTE_SESSIZ,
    DIKTE_TALIMATI,
    DIKTE_UZAK,
    DIKTE_UZAK_SESSIZ,
    OZET_ONAY,
    OZET_TALIMATI,
    UPLOAD_PARCA_BAYT,
    AdIstegi,
    AjanRunKaydi,
    AltOturumIstegi,
    GeriSarIstegi,
    HafizaIstegi,
    OneriRedIstegi,
    SonrakiOneriIstegi,
    sse,
)
from app.services import ekler as ekler_modulu
from app.services.oturumlar import Mesaj
from app.services.sohbet import VARSAYILAN_ALAN_ID, MesajIstegi, tahmini_token
from app.services.testler import ORNEK_SATIRLAR, ornek_belge
from app.services.yerel_llm import MODELLER


def router_olustur(b: Any) -> APIRouter:
    r = APIRouter()
    akistaki: set[str] = set()

    @r.get("/api/oturumlar")
    async def oturum_liste(q: str = "") -> list[dict]:
        return [{**o, "akista": o["id"] in akistaki} for o in b.oturumlar.liste(q)]

    @r.post("/api/oturumlar")
    async def oturum_yeni() -> dict:
        return b.oturumlar.olustur(b.sohbet.aktif_alan().id).model_dump()

    @r.get("/api/oturumlar/{oturum_id}/baglam")
    async def oturum_baglam(oturum_id: str) -> dict:
        o = b.oturumlar.getir(oturum_id)
        mesaj_tok = sum(tahmini_token(m.metin) + tahmini_token(m.dusunce) for m in o.mesajlar)
        ayar = b.ayarlar.oku()
        try:
            _, araclar, _, _ = await asyncio.to_thread(
                b.sohbet.baglam_hazirla, ayar, "", o.mesajlar
            )
            p = getattr(b.sohbet, "son_parcalar", {})
        except Exception as e:  # noqa: BLE001
            logger.debug("Baglam dokumu hesaplanamadi: {}", e)
            araclar, p = [], {}
        tok = lambda x: tahmini_token(x) if x else 0  # noqa: E731
        jtok = lambda x: tok(x and json.dumps(x, ensure_ascii=False))  # noqa: E731
        mcp = [a for a in araclar if str(a.get("function", {}).get("name", "")).startswith("mcp")]
        yerlesik = [a for a in araclar if a not in mcp]
        kalemler = [
            {"ad": "Mesajlar", "tur": "mesaj", "token": mesaj_tok},
            {"ad": "Sistem talimatı", "tur": "sistem", "token": tok(p.get("sistem"))},
            {"ad": "KAIRO.md ve talimatlar", "tur": "talimat", "token": tok(p.get("talimat"))},
            {"ad": "Proje talimatı", "tur": "proje", "token": tok(p.get("proje"))},
            {"ad": "Hafıza", "tur": "hafiza", "token": tok(p.get("hafiza"))},
            {"ad": "Skill'ler", "tur": "skill", "token": tok(p.get("skill"))},
            {"ad": "Araçlar", "tur": "arac", "token": jtok(yerlesik), "sayi": len(yerlesik)},
            {"ad": "MCP araçları", "tur": "mcp", "token": jtok(mcp), "sayi": len(mcp)},
        ]
        kalemler = [k for k in kalemler if k["token"] or k["tur"] == "mesaj"]
        boyut = b.model_yetenegi(b.sohbet.aktif_alan().koordinator_model).baglam or 1
        kullanilan = sum(k["token"] for k in kalemler)
        for k in kalemler:
            k["yuzde"] = round(k["token"] * 100 / boyut, 1)
        return {
            "kullanilan": kullanilan,
            "boyut": boyut,
            "kalemler": kalemler,
            "bos": max(0, boyut - kullanilan),
            "yuzde": min(100, round(kullanilan * 100 / boyut)),
        }

    @r.get("/api/oturumlar/{oturum_id}")
    async def oturum_getir(oturum_id: str) -> dict:
        return b.oturumlar.getir(oturum_id).model_dump()

    @r.post("/api/oturumlar/{oturum_id}/geri-sar")
    async def oturum_geri_sar(oturum_id: str, istek: GeriSarIstegi) -> dict:
        o, metin = b.oturumlar.geri_sar(oturum_id, istek.mesaj_id, istek.run)
        return {"oturum": o.model_dump(), "metin": metin}

    @r.post("/api/oturumlar/{oturum_id}/catal")
    async def oturum_catal(oturum_id: str, istek: GeriSarIstegi | None = None) -> dict:
        return b.oturumlar.catal(oturum_id, istek.mesaj_id if istek else "").model_dump()

    @r.post("/api/oturumlar/{oturum_id}/mesajlar/{mesaj_id}/sabitle")
    async def mesaj_sabitle(oturum_id: str, mesaj_id: str) -> dict:
        return b.oturumlar.sabitle(oturum_id, mesaj_id).model_dump()

    @r.post("/api/oturumlar/{oturum_id}/alt")
    async def oturum_alt(oturum_id: str, istek: AltOturumIstegi) -> dict:
        return b.oturumlar.alt_olustur(oturum_id, istek.baslik, istek.kaynak).model_dump()

    @r.post("/api/sonraki-oneri")
    async def sonraki_oneri(istek: SonrakiOneriIstegi) -> dict:
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
            async with asyncio.timeout(45), b.yonetici.kullan() as llm:
                v = await llm.json_cikti(
                    istem,
                    {
                        "type": "object",
                        "properties": {"oneri": {"type": "string"}},
                        "required": ["oneri"],
                    },
                    ad="sonraki_oneri",
                    max_tokens=80,
                    dusunme="kapali",
                )
        except Exception as e:  # noqa: BLE001
            logger.debug("Sonraki oneri alinamadi: {}", e)
            return {"oneri": ""}
        oneri = " ".join(str(v.get("oneri") or "").split()).strip(" .\"'")
        oneri = re.sub(r"^[^:]{0,40}(sonraki|kullanici|mesaj)[^:]{0,20}:\s*", "", oneri, flags=re.I)
        oneri = oneri.strip(" .\"'")
        if oneri.casefold() == " ".join(istek.kullanici.split()).strip(" .\"'").casefold():
            oneri = ""
        return {"oneri": oneri[:100]}

    @r.post("/api/oturumlar/{oturum_id}/oneri-reddet")
    async def oturum_oneri_reddet(oturum_id: str, istek: OneriRedIstegi) -> dict:
        o = b.oturumlar.oneri_reddet(oturum_id, istek.kaynak, istek.karar)
        return {"oneri_kararlari": o.oneri_kararlari}

    @r.post("/api/oturumlar/{oturum_id}/temizle")
    async def oturum_temizle(oturum_id: str) -> dict:
        return b.oturumlar.temizle(oturum_id).model_dump()

    @r.get("/api/oturumlar/{oturum_id}/disa-aktar")
    async def oturum_disa_aktar(oturum_id: str, bicim: str = "json") -> Response:
        if bicim == "md":
            return Response(
                b.oturumlar.disa_aktar_md(oturum_id),
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="sohbet-{oturum_id}.md"'},
            )
        return JSONResponse(
            b.oturumlar.getir(oturum_id).model_dump(),
            headers={"Content-Disposition": f'attachment; filename="sohbet-{oturum_id}.json"'},
        )

    @r.post("/api/oturumlar/{oturum_id}/ozetle")
    async def oturum_ozetle(oturum_id: str) -> dict:
        o = b.oturumlar.getir(oturum_id)
        son_kullanici = max(
            (i for i, m in enumerate(o.mesajlar) if m.rol == "kullanici"), default=0
        )
        eski = o.mesajlar[:son_kullanici]
        if len(eski) < 2:
            raise UygulamaHatasi("Ozetlenecek kadar eski mesaj yok.")
        dokum = "\n\n".join(f"{m.rol.upper()}: {m.metin[:4000]}" for m in eski if m.metin)
        try:
            async with b.yonetici.kullan() as llm:
                ozet = await llm.metin(
                    dokum[-48000:], sistem=OZET_TALIMATI, max_tokens=1200, dusunme="kapali"
                )
        except YerelLLMHatasi as e:
            raise UygulamaHatasi(f"Ozet uretilemedi: {e}") from e
        ozet = (ozet or "").strip()
        if not ozet:
            raise UygulamaHatasi("Model ozet uretmedi; sohbet degismedi.")
        guncel = b.oturumlar.getir(oturum_id)
        guncel.mesajlar = [
            Mesaj(rol="kullanici", metin=f"[Önceki konuşmanın özeti]\n\n{ozet}"),
            Mesaj(rol="asistan", metin=OZET_ONAY),
            *guncel.mesajlar[son_kullanici:],
        ]
        b.oturumlar.kaydet(guncel)
        return {"ozetlenen": len(eski), "kalan": len(guncel.mesajlar), "ozet": ozet}

    @r.delete("/api/oturumlar/grup/{grup}")
    async def proje_disi_sohbetleri_sil(grup: Literal["projesiz", "kisisel"]) -> dict:
        alan_id = VARSAYILAN_ALAN_ID if grup == "kisisel" else ""
        return {"silinen_sohbet": b.alan_sohbetlerini_sil(alan_id)}

    @r.patch("/api/oturumlar/{oturum_id}")
    async def oturum_adlandir(oturum_id: str, istek: AdIstegi) -> dict:
        return b.oturumlar.yeniden_adlandir(oturum_id, istek.baslik).model_dump()

    @r.post("/api/oturumlar/{oturum_id}/ajan-run")
    async def oturum_ajan_run(oturum_id: str, istek: AjanRunKaydi) -> dict:
        o = b.oturumlar.ajan_run_ekle(oturum_id, istek.run, istek.metin)
        return {"ajan_runlari": o.ajan_runlari}

    @r.delete("/api/oturumlar/{oturum_id}")
    async def oturum_sil(oturum_id: str) -> dict:
        b.oturumlar.sil(oturum_id)
        return {"silindi": oturum_id}

    @r.post("/api/oturumlar/{oturum_id}/mesaj")
    async def mesaj(oturum_id: str, istek: MesajIstegi) -> StreamingResponse:
        b.oturumlar.getir(oturum_id)

        async def izlenen() -> AsyncIterator[dict]:
            akistaki.add(oturum_id)
            try:
                async for olay in b.sohbet.mesaj_gonder(oturum_id, istek):
                    yield olay
            finally:
                akistaki.discard(oturum_id)

        return sse(izlenen())

    # ---- Ekler ve dikte ----
    @r.post("/api/ekler")
    async def ek_yukle(dosya: UploadFile) -> dict:
        ad = dosya.filename or "dosya"
        ekler_modulu.tur_bul(ad)
        parcalar: list[bytes] = []
        toplam = 0
        while parca := await dosya.read(UPLOAD_PARCA_BAYT):
            toplam += len(parca)
            if toplam > ekler_modulu.MAX_BOYUT:
                mb = ekler_modulu.MAX_BOYUT / (1024 * 1024)
                raise GecersizEk(f"Dosya {mb:.0f} MB sinirindan buyuk; yukleme durduruldu.")
            parcalar.append(parca)
        return b.ekler.kaydet(ad, b"".join(parcalar)).model_dump(exclude={"metin"})

    def dikte_durumu() -> dict:
        a = b.ayarlar.oku()
        if a.dikte_bulut and b.openrouter.anahtar():
            m = a.dikte_model or a.or_model
            if m:
                b.openrouter.eksik_modeli_getir(m)
            if not (b.openrouter.model_bilgisi(m) or {}).get("ses"):
                return {"kullanilabilir": False, "model": m, "neden": DIKTE_UZAK_SESSIZ}
            return {
                "kullanilabilir": True,
                "model": m,
                "neden": "",
                "max_sn": DIKTE_MAX_SN,
                "bulut": True,
            }
        if a.saglayici == "openrouter" and a.or_model:
            return {"kullanilabilir": False, "model": a.or_model, "neden": DIKTE_UZAK}
        if a.saglayici == "ollama":
            return {"kullanilabilir": False, "model": a.aktif_model, "neden": DIKTE_SESSIZ}
        p = MODELLER.get(a.model)
        if p is None or not p.ses:
            return {"kullanilabilir": False, "model": a.model, "neden": DIKTE_SESSIZ}
        return {"kullanilabilir": True, "model": a.model, "neden": "", "max_sn": DIKTE_MAX_SN}

    @r.get("/api/dikte/durum")
    async def dikte_durum() -> dict:
        return dikte_durumu()

    @r.post("/api/dikte")
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
        async with b.yonetici.kullan(d["model"]) as llm:
            metin = await llm.ses(
                veri, DIKTE_TALIMATI, bicim="wav", dusunme="kapali", max_tokens=512
            )
        return {"metin": metin.strip(), "sure_sn": round(time.perf_counter() - bas, 1)}

    @r.post("/api/ekler/ornek-belge")
    async def ek_ornek() -> dict:
        ek = b.ekler.kaydet("ornek-hakedis.png", ornek_belge())
        return {**ek.model_dump(exclude={"metin"}), "beklenen": "\n".join(ORNEK_SATIRLAR)}

    @r.get("/api/ekler/{ek_id}")
    async def ek_getir(ek_id: str) -> FileResponse:
        ek = b.ekler.getir(ek_id)
        return FileResponse(b.ekler.yol(ek), media_type=ek.mime, filename=ek.ad)

    # ---- Hafiza ----
    @r.get("/api/hafiza")
    async def hafiza_listesi(kapsam: str | None = None) -> dict:
        return {"kayitlar": b.hafiza.liste(kapsam)}

    @r.post("/api/hafiza/ice-aktar")
    async def hafiza_ice_aktar(veri: dict) -> dict:
        metin = str(veri.get("metin") or "")[:100_000]
        return b.hafiza.ice_aktar(metin, str(veri.get("kaynak") or ""))

    @r.post("/api/hafiza")
    async def hafiza_ekle(istek: HafizaIstegi) -> dict:
        return b.hafiza.ekle(istek.metin, **istek.model_dump(exclude={"metin"}))

    @r.patch("/api/hafiza/{kayit_id}")
    async def hafiza_guncelle(kayit_id: str, degisiklik: dict) -> dict:
        return b.hafiza.guncelle(kayit_id, degisiklik)

    @r.delete("/api/hafiza/{kayit_id}")
    async def hafiza_sil(kayit_id: str) -> dict:
        return b.hafiza.sil(kayit_id)

    @r.get("/api/hafiza-disa-aktar")
    async def hafiza_disa_aktar() -> JSONResponse:
        return JSONResponse(
            b.hafiza.disa_aktar(),
            headers={"Content-Disposition": 'attachment; filename="hafiza.json"'},
        )

    return r
