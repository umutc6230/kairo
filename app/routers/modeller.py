"""Genel bilgi, ayarlar, saglayicilar, OpenRouter, model magazasi, Ollama ve model testleri."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app import URUN_ADI, URUN_SAHIBI, URUN_SAHIBI_GITHUB, URUN_SAHIBI_X, __version__
from app.agent.policy import maskele
from app.exceptions import UygulamaHatasi
from app.routers import (
    AnahtarIstegi,
    DurdurIstegi,
    EditorBaglamIstegi,
    IndirIstegi,
    ModelIstegi,
    OllamaIndirIstegi,
    SaglayiciIstegi,
    sse,
)
from app.services import masaustu_ayar as mda
from app.services import sistem
from app.services.araclar import ARACLAR, ORNEK_ISTEMLER
from app.services.model_magaza import uyumluluk
from app.services.testler import AracIstegi, KarsilastirmaIstegi, OcrIstegi, PaketIstegi
from app.services.yerel_llm import DUSUNME_SECENEKLERI, MODELLER


def router_olustur(b: Any) -> APIRouter:
    r = APIRouter()

    @r.get("/api/bilgi")
    async def bilgi() -> dict:
        return {
            "urun": URUN_ADI,
            "surum": __version__,
            "urun_sahibi": URUN_SAHIBI,
            "x": URUN_SAHIBI_X,
            "github": URUN_SAHIBI_GITHUB,
            "dusunme_secenekleri": DUSUNME_SECENEKLERI,
            "veri_dizini": str(b.veri_dizini),
        }

    @r.get("/api/durum")
    async def durum() -> dict:
        return await b.yonetici.bilgi()

    @r.get("/api/guncelleme")
    async def surum_guncelleme(zorla: bool = False) -> dict:
        return await b.guncelleme.kontrol(zorla=zorla, ag_acik=b.politika.ag_acik())

    @r.post("/api/editor/baglam")
    async def editor_baglam_kaydet(istek: EditorBaglamIstegi) -> dict:
        b.editor_baglam.clear()
        b.editor_baglam.update(
            {
                "var": True,
                "dosya": istek.dosya.strip(),
                "satir_baslangic": istek.satir_baslangic,
                "satir_bitis": max(istek.satir_baslangic, istek.satir_bitis),
                "secim": maskele(istek.secim),
                "proje_kok": istek.proje_kok.strip(),
                "kaynak": istek.kaynak.strip() or "vscode",
                "guncelleme": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return dict(b.editor_baglam)

    @r.get("/api/editor/baglam")
    async def editor_baglam_oku() -> dict:
        if not b.editor_baglam:
            return {"var": False}
        return dict(b.editor_baglam)

    @r.delete("/api/editor/baglam")
    async def editor_baglam_sil() -> dict:
        b.editor_baglam.clear()
        return {"temizlendi": True}

    @r.post("/api/model/hazirla")
    async def model_hazirla(istek: ModelIstegi) -> dict:
        sonuc = await b.yonetici.hazirla(istek.model)
        b.isitmalar.add(gorev := asyncio.create_task(b.sohbet.isit()))
        gorev.add_done_callback(b.isitmalar.discard)
        return sonuc

    @r.post("/api/model/durdur")
    async def model_durdur(istek: DurdurIstegi) -> dict:
        return await b.yonetici.durdur(harici=istek.harici)

    @r.get("/api/model/yetenek")
    async def model_yetenek() -> dict:
        await b.ollama_yetenek_hazirla(baslat=False)
        return b.model_yetenegi().model_dump()

    # ---- OpenAI uyumlu saglayicilar ----
    @r.get("/api/saglayicilar")
    async def saglayici_liste() -> list[dict]:
        return b.saglayicilar.durum()

    @r.put("/api/saglayicilar/{sid}")
    async def saglayici_kaydet(sid: str, istek: SaglayiciIstegi) -> list[dict]:
        return b.saglayicilar.kaydet(sid, istek.anahtar, istek.adres)

    @r.delete("/api/saglayicilar/{sid}")
    async def saglayici_sil(sid: str) -> list[dict]:
        return b.saglayicilar.sil(sid)

    @r.get("/api/saglayicilar/{sid}/modeller")
    async def saglayici_modeller(sid: str, yenile: bool = False) -> dict:
        return await b.saglayicilar.modeller(sid, yenile)

    @r.post("/api/saglayicilar/test")
    async def saglayici_test(istek: ModelIstegi) -> dict:
        return await b.saglayicilar.test(istek.model or b.ayarlar.oku().uyumlu_model)

    # ---- OpenRouter ----
    @r.get("/api/openrouter/anahtar")
    async def or_anahtar() -> dict:
        return b.openrouter.anahtar_durumu()

    @r.put("/api/openrouter/anahtar")
    async def or_anahtar_kaydet(istek: AnahtarIstegi) -> dict:
        return b.openrouter.anahtar_kaydet(istek.anahtar)

    @r.delete("/api/openrouter/anahtar")
    async def or_anahtar_sil() -> dict:
        return b.openrouter.anahtar_sil()

    @r.get("/api/openrouter/limit")
    async def or_limit() -> dict:
        return await b.openrouter.limit()

    @r.get("/api/openrouter/modeller")
    async def or_modeller(yenile: bool = False, cikti: str = "") -> dict:
        return await b.openrouter.modeller(yenile, cikti)

    @r.post("/api/openrouter/test")
    async def or_test(istek: ModelIstegi) -> dict:
        return await b.openrouter.test(istek.model or b.ayarlar.oku().or_model)

    # ---- Ayarlar ve yerel sunucu ----
    @r.get("/api/ayarlar")
    async def ayar_oku() -> dict:
        return b.ayarlar.oku().model_dump()

    @r.put("/api/ayarlar")
    async def ayar_yaz(degisiklik: dict) -> dict:
        once = b.ayarlar.oku()
        yeni = b.ayarlar.guncelle(degisiklik)
        if "baslangicta_ac" in degisiklik:
            await asyncio.to_thread(mda.baslangic_ayarla, yeni.baslangicta_ac)
        if (
            b.gecit
            and once.hizli_kisayol != yeni.hizli_kisayol
            and not b.kisayol.ayarla(yeni.hizli_kisayol)
            and yeni.hizli_kisayol
        ):
            raise UygulamaHatasi(b.kisayol.hata or "Kisayol kaydedilemedi.")
        if (once.sunucu_acik, once.sunucu_port) != (yeni.sunucu_acik, yeni.sunucu_port):
            if yeni.sunucu_acik:
                await b.agecidi.baslat(yeni.sunucu_port)
            else:
                await b.agecidi.durdur()
        if once.baglam_token != yeni.baglam_token or once.ollama_adres != yeni.ollama_adres:
            b.ollama.durdur()
        return yeni.model_dump()

    @r.get("/api/sunucu")
    async def sunucu_durumu() -> dict:
        a = b.ayarlar.oku()
        return {**b.agecidi.durum(), "ayar_acik": a.sunucu_acik, "ayar_port": a.sunucu_port}

    @r.post("/api/sunucu/yeniden")
    async def sunucu_yeniden() -> dict:
        a = b.ayarlar.oku()
        await b.agecidi.baslat(a.sunucu_port)
        return b.agecidi.durum()

    @r.post("/api/ayarlar/test")
    async def ayar_test(istek: ModelIstegi) -> dict:
        bas = time.perf_counter()
        async with b.yonetici.kullan(istek.model) as llm:
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
            "yukleme_sn": b.yonetici.yukleme_sn,
            "maliyet": "0 (yerel)",
            "uretim_tok_sn": round((llm.son_zamanlama or {}).get("predicted_per_second") or 0, 1),
        }

    # ---- Model magazasi (Hugging Face) ----
    def _sistem_bilgisi() -> dict:
        bel = sistem.bellek()
        return {
            "toplam_ram_gb": bel.get("toplam_gb"),
            "bos_ram_gb": bel.get("bos_gb"),
            "disk_bos_gb": b.indirici.disk_bos_gb(),
            "model_klasoru": str(b.indirici.model_klasoru),
        }

    @r.get("/api/magaza/ara")
    async def magaza_ara(q: str = "", imlec: str = "") -> dict:
        s = _sistem_bilgisi()
        bellek = {"toplam_gb": s["toplam_ram_gb"], "bos_gb": s["bos_ram_gb"]}
        yuklu = {p.dosya for p in MODELLER.values()}
        adaylar, sonraki = await b.magaza.ara(q, imlec=imlec[:500])
        sonuclar = [
            a
            | {
                "uyumluluk": uyumluluk(a["tahmini_gb"], bellek, s["disk_bos_gb"]),
                "yuklu": a["model_dosyasi"] in yuklu,
            }
            for a in adaylar
        ]
        return {"sistem": s, "sonuclar": sonuclar, "sonraki": sonraki}

    @r.get("/api/magaza/yuklu")
    async def magaza_yuklu() -> dict:
        klasor = b.indirici.model_klasoru / "models"
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
                    "yerlesik": p.anahtar in b.kayit.yerlesik,
                    "repo": b.kayit.kaynak(p.anahtar),
                    "acik": b.yonetici.yuklenen_model == p.anahtar,
                }
            )
        return {"sistem": _sistem_bilgisi(), "modeller": liste}

    @r.delete("/api/magaza/yuklu/{anahtar}")
    async def magaza_sil(anahtar: str) -> dict:
        if b.yonetici.yuklenen_model == anahtar:
            await b.yonetici.durdur()
        return b.indirici.sil(anahtar)

    @r.post("/api/magaza/indir")
    async def magaza_indir(istek: IndirIstegi) -> dict:
        return (await b.indirici.baslat(istek.repo)).ozet()

    @r.get("/api/magaza/indirmeler")
    async def magaza_indirmeler() -> list[dict]:
        return [i.ozet() for i in b.indirici.indirmeler.values()]

    @r.post("/api/magaza/indirmeler/{indirme_id}/iptal")
    async def magaza_iptal(indirme_id: str) -> dict:
        b.indirici.iptal(indirme_id)
        return {"iptal": indirme_id}

    # ---- Ollama ----
    @r.get("/api/ollama/durum")
    async def ollama_durum() -> dict:
        return await b.ollama.durum()

    @r.post("/api/ollama/baslat")
    async def ollama_baslat() -> dict:
        return await b.ollama.baslat()

    @r.get("/api/ollama/yuklu")
    async def ollama_yuklu() -> dict:
        return {"sistem": _sistem_bilgisi(), "modeller": await b.ollama.yuklu()}

    @r.get("/api/ollama/detay")
    async def ollama_detay(ad: str) -> dict:
        return await b.ollama.detay(ad[:200])

    @r.delete("/api/ollama/yuklu")
    async def ollama_sil(ad: str) -> dict:
        a = b.ayarlar.oku()
        sonuc = await b.ollama.sil(ad[:200])
        if a.ollama_model == ad:
            b.ayarlar.guncelle({"ollama_model": ""})
        return sonuc

    @r.get("/api/ollama/ara")
    async def ollama_ara(
        q: str = "", sayfa: int = 1, sira: str = "popular", yetenek: str = ""
    ) -> dict:
        v = await b.ollama.ara(q[:100], sayfa, sira, yetenek)
        return v | {"sistem": _sistem_bilgisi()}

    @r.get("/api/ollama/etiketler")
    async def ollama_etiketler(ad: str) -> dict:
        s = _sistem_bilgisi()
        bellek = {"toplam_gb": s["toplam_ram_gb"], "bos_gb": s["bos_ram_gb"]}
        yuklu = {m["ad"] for m in await b.ollama.yuklu()} if await b.ollama.surum() else set()
        return {
            "etiketler": [
                e
                | {
                    "uyumluluk": uyumluluk(e["boyut_gb"], bellek, s["disk_bos_gb"]),
                    "yuklu": e["tam_ad"] in yuklu or (e["etiket"] == "latest" and ad in yuklu),
                }
                for e in await b.ollama.etiketler(ad[:100])
            ]
        }

    @r.post("/api/ollama/indir")
    async def ollama_indir(istek: OllamaIndirIstegi) -> dict:
        return (await b.ollama.indir(istek.ad)).ozet()

    @r.get("/api/ollama/indirmeler")
    async def ollama_indirmeler() -> list[dict]:
        return [i.ozet() for i in b.ollama.indirmeler.values()]

    @r.post("/api/ollama/indirmeler/{indirme_id}/iptal")
    async def ollama_iptal(indirme_id: str) -> dict:
        b.ollama.iptal(indirme_id)
        return {"iptal": indirme_id}

    # ---- Testler ----
    @r.post("/api/karsilastir")
    async def karsilastir(istek: KarsilastirmaIstegi) -> StreamingResponse:
        return sse(b.testler.karsilastir(istek))

    @r.post("/api/ocr")
    async def ocr(istek: OcrIstegi) -> StreamingResponse:
        b.ekler.getir(istek.ek_id)
        return sse(b.testler.ocr(istek))

    @r.get("/api/araclar")
    async def araclar() -> dict:
        return {"araclar": ARACLAR, "ornekler": ORNEK_ISTEMLER}

    @r.post("/api/arac-testi")
    async def arac_testi(istek: AracIstegi) -> StreamingResponse:
        return sse(b.testler.arac(istek))

    @r.post("/api/test-paketi")
    async def test_paketi(istek: PaketIstegi) -> StreamingResponse:
        return sse(b.testler.paket(istek))

    @r.get("/api/doctor")
    async def doktor_tani() -> dict:
        from app.doktor import tani

        a = b.ayarlar.oku()
        sonuc = await asyncio.to_thread(
            tani, b.veri_dizini, Path(a.llm_dizin), b.openrouter.anahtar_durumu()["var"]
        )
        return {"kontroller": sonuc}

    return r
