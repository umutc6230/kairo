"""Sohbet: mesaj gecmisini ve ekleri model mesajina cevirir, cevabi olay olarak akitir.

Olaylar (dict, "tur" alani): durum, ilerleme, dusunce, parca, bitti, hata, kullanici_mesaji.
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from app.exceptions import SesDesteklenmiyor, UygulamaHatasi, YerelLLMHatasi
from app.services.ekler import Ek, EkDeposu
from app.services.model_yonetici import ModelYonetici
from app.services.oturumlar import EkOzet, Mesaj, OturumDeposu, baslik_uret
from app.services.yerel_llm import MODELLER, YerelLLM, resmi_kucult

GECMIS_KARAKTER = 16000  # gecmis mesajlar icin pay (~5k token); 8192 context'e sigsin
EK_METIN_KARAKTER = 12000


class MesajIstegi(BaseModel):
    metin: str = Field(default="", max_length=60000)
    ekler: list[str] = []
    dusunme: str | None = None


Olay = dict[str, Any]
_BITTI = object()


async def kuyruktan_akit(
    uretici: Callable[[Callable[[Olay], None]], Awaitable[Any]],
) -> AsyncIterator[Olay | tuple[str, Any]]:
    """`uretici(gonder)` gorevini calistirir; gonder() ile atilan olaylari aninda verir.
    Sonunda ("sonuc", deger) verir. Tuketici biterse (istemci koptu) gorev iptal edilir."""
    kuyruk: asyncio.Queue = asyncio.Queue()
    gorev = asyncio.create_task(uretici(kuyruk.put_nowait))
    gorev.add_done_callback(lambda _: kuyruk.put_nowait(_BITTI))
    try:
        while (olay := await kuyruk.get()) is not _BITTI:
            yield olay
        yield ("sonuc", gorev.result())
    finally:
        if not gorev.done():
            gorev.cancel()
            await asyncio.gather(gorev, return_exceptions=True)


async def ek_parcalari(
    llm: YerelLLM, depo: EkDeposu, ek: Ek, gonder: Callable[[Olay], None]
) -> list[dict]:
    """Bir eki, mesaj icerik parcalarina cevirir (gorsel, ses ya da metin)."""
    if ek.tur == "resim":
        veri, mime = resmi_kucult(depo.veri(ek), mime=ek.mime)
        return [{"type": "image_url", "image_url": {"url": YerelLLM.resim_data_url(veri, mime)}}]
    if ek.tur == "ses":
        profil = MODELLER.get(llm.model)
        if profil and not profil.ses:
            raise SesDesteklenmiyor()
        veri = base64.b64encode(depo.veri(ek)).decode()
        bicim = "mp3" if ek.uzanti == ".mp3" else "wav"
        return [{"type": "input_audio", "input_audio": {"data": veri, "format": bicim}}]
    if ek.tur == "pdf" and not ek.metin:
        gonder({"tur": "durum", "metin": f"PDF okunuyor: {ek.ad}"})

        def ilerleme(a: int, b: int) -> None:
            gonder({"tur": "ilerleme", "metin": f"{ek.ad}: sayfa {a}/{b}", "a": a, "b": b})

        sayfalar = await llm.ocr_pdf(depo.yol(ek), ilerleme=ilerleme, max_tokens=2048)
        metin = "\n\n".join(f"--- Sayfa {i} ---\n{s}" for i, s in enumerate(sayfalar, 1))
        ek = depo.metin_kaydet(ek, metin)
    etiket = "PDF" if ek.tur == "pdf" else "Dosya"
    kesik = ek.metin[:EK_METIN_KARAKTER]
    not_ = "\n[... metin kisaltildi]" if len(ek.metin) > EK_METIN_KARAKTER else ""
    return [{"type": "text", "text": f"[{etiket}: {ek.ad}]\n{kesik}{not_}"}]


def gecmis(mesajlar: list[Mesaj], sinir: int = GECMIS_KARAKTER) -> list[dict]:
    """Onceki mesajlari yalniz metin olarak (ekler adiyla) sondan basa sinira kadar alir."""
    sonuc: list[dict] = []
    toplam = 0
    for m in reversed(mesajlar):
        if m.hata and not m.metin:
            continue
        metin = m.metin
        if m.ekler:
            metin = " ".join(f"[Ek: {e.ad}]" for e in m.ekler) + ("\n" + metin if metin else "")
        if toplam + len(metin) > sinir:
            break
        toplam += len(metin)
        sonuc.append({"role": "user" if m.rol == "kullanici" else "assistant", "content": metin})
    return list(reversed(sonuc))


def istatistik(llm: YerelLLM, bas: float, ilk: float | None, yukleme: float | None) -> dict:
    z = llm.son_zamanlama or {}
    return {
        "model": llm.model,
        "dusunme": llm.dusunme,
        "sure_sn": round(time.perf_counter() - bas, 1),
        "ilk_token_sn": round(ilk - bas, 1) if ilk else None,
        "uretim_tok_sn": round(z.get("predicted_per_second") or 0, 1) or None,
        "prompt_tok_sn": round(z.get("prompt_per_second") or 0, 1) or None,
        "token": z.get("predicted_n"),
        "prompt_token": z.get("prompt_n"),
        "yukleme_sn": yukleme,
    }


async def cevap_akit(
    llm: YerelLLM,
    mesajlar: list[dict],
    gonder: Callable[[Olay], None],
    *,
    dusunme: str | None = None,
    max_tokens: int = 1024,
    sicaklik: float = 0.2,
    etiket: dict | None = None,
) -> dict:
    """Cevabi parca parca gonderir; sonunda {metin, dusunce, istatistik} dondurur."""
    etiket = etiket or {}
    bas, ilk = time.perf_counter(), None
    parcalar: list[str] = []
    dusunceler: list[str] = []

    def dusunce(d: str) -> None:
        dusunceler.append(d)
        gonder({"tur": "dusunce", "metin": d, **etiket})

    async for p in llm.akis(
        mesajlar, dusunme=dusunme, max_tokens=max_tokens, temperature=sicaklik, dusunce_cb=dusunce
    ):
        ilk = ilk or time.perf_counter()
        parcalar.append(p)
        gonder({"tur": "parca", "metin": p, **etiket})
    ist = istatistik(llm, bas, ilk, None)
    if dusunceler:  # dusunme suresi: ilk cevap parcasina kadar (cevap yoksa tum sure)
        ist["dusunce_sn"] = round((ilk or time.perf_counter()) - bas, 1)
    return {
        "metin": "".join(parcalar).strip(),
        "dusunce": "".join(dusunceler).strip(),
        "istatistik": ist,
    }


class SohbetServisi:
    def __init__(self, yonetici: ModelYonetici, oturumlar: OturumDeposu, ekler: EkDeposu) -> None:
        self.yonetici = yonetici
        self.oturumlar = oturumlar
        self.ekler = ekler

    async def mesaj_gonder(self, oturum_id: str, istek: MesajIstegi) -> AsyncIterator[Olay]:
        if not istek.metin.strip() and not istek.ekler:
            raise UygulamaHatasi("Bos mesaj gonderilemez.")
        oturum = self.oturumlar.getir(oturum_id)
        ekler = [self.ekler.getir(i) for i in istek.ekler]
        onceki = list(oturum.mesajlar)
        kullanici = Mesaj(
            rol="kullanici",
            metin=istek.metin,
            ekler=[EkOzet(id=e.id, ad=e.ad, tur=e.tur) for e in ekler],
        )
        oturum.mesajlar.append(kullanici)
        if len(oturum.mesajlar) == 1:
            oturum.baslik = baslik_uret(istek.metin or ekler[0].ad)
        self.oturumlar.kaydet(oturum)
        yield {"tur": "kullanici_mesaji", "mesaj": kullanici.model_dump(), "baslik": oturum.baslik}

        ayar = self.yonetici.ayarlar.oku()
        asistan = Mesaj(rol="asistan", model=ayar.model)
        yarim: list[str] = []
        yarim_dusunce: list[str] = []

        async def uret(gonder: Callable[[Olay], None]) -> dict:
            if self.yonetici.mesgul:
                gonder({"tur": "durum", "metin": "Onceki islemin bitmesi bekleniyor..."})
            gonder({"tur": "durum", "metin": f"Model hazirlaniyor: {ayar.model}"})
            async with self.yonetici.kullan(ayar.model) as llm:
                yukleme = self.yonetici.yukleme_sn
                parcalar: list[dict] = []
                for ek in ekler:
                    parcalar += await ek_parcalari(llm, self.ekler, ek, gonder)
                icerik: Any = istek.metin
                if parcalar:
                    icerik = [{"type": "text", "text": istek.metin}] if istek.metin else []
                    icerik += parcalar
                mesajlar = (
                    [{"role": "system", "content": ayar.sistem_istemi}]
                    if ayar.sistem_istemi
                    else []
                )
                mesajlar += gecmis(onceki) + [{"role": "user", "content": icerik}]
                gonder({"tur": "durum", "metin": "Yanitlaniyor..."})
                sonuc = await cevap_akit(
                    llm,
                    mesajlar,
                    gonder,
                    dusunme=istek.dusunme,
                    max_tokens=ayar.max_tokens,
                    sicaklik=ayar.sicaklik,
                )
                sonuc["istatistik"]["yukleme_sn"] = yukleme
                return sonuc

        try:
            async for olay in kuyruktan_akit(uret):
                if isinstance(olay, tuple):
                    sonuc = olay[1]
                    asistan.metin = sonuc["metin"]
                    asistan.dusunce = sonuc["dusunce"]
                    asistan.istatistik = sonuc["istatistik"]
                    continue
                if olay["tur"] == "parca":
                    yarim.append(olay["metin"])
                elif olay["tur"] == "dusunce":
                    yarim_dusunce.append(olay["metin"])
                yield olay
        except (YerelLLMHatasi, UygulamaHatasi) as e:
            asistan.metin, asistan.hata = "".join(yarim), str(e)
            asistan.dusunce = "".join(yarim_dusunce)
            yield {"tur": "hata", "mesaj": str(e)}
        except (asyncio.CancelledError, GeneratorExit):  # kullanici durdurdu / pencere kapandi
            asistan.metin, asistan.hata = "".join(yarim), "Durduruldu."
            asistan.dusunce = "".join(yarim_dusunce)
            self._kaydet(oturum_id, asistan)
            raise
        self._kaydet(oturum_id, asistan)
        yield {"tur": "bitti", "mesaj": asistan.model_dump()}

    def _kaydet(self, oturum_id: str, asistan: Mesaj) -> None:
        oturum = self.oturumlar.getir(oturum_id)
        oturum.mesajlar.append(asistan)
        self.oturumlar.kaydet(oturum)
