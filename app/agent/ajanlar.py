"""Kalici ajanlar: her ajanin kendi adi, avatari, talimati, calisma klasoru, modeli, hafizasi ve
FIFO is kuyrugu vardir. Ajanlar birbirine mesaj atabilir; cevap gonderenin kuyruguna doner.

Tasarim openbot'tan uyarlandi (nightly-labs/openbot, PolyForm Noncommercial 1.0.0,
Copyright 2026 Synthetify Labs): kalici ajan + kuyruk + ajanlar arasi mesaj. Kod birebir
kopyalanmadi (TypeScript/Electron); kisisel, ticari olmayan kullanim.

- Kuyruk sirasi korunur (FIFO); ajan mesgulken gelen mesaj bekler. Duraklatilan ajan isi almaz.
- Her mesaj ajanin ONCEKI isinin ozetiyle baslar (kalici konusma; ham gecmis degil).
- Ajanlar arasi mesajda zincir derinligi sinirlidir (sonsuz ping-pong olmaz).
- Calisma klasoru ajan basinadir; izinler yine ayni izin motorundan gecer.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

MAX_AJAN = 50
MAX_KUYRUK = 50
MAX_GECMIS = 200  # konusma kaydinda tutulan mesaj sayisi
MAX_ZINCIR = 3  # ajan -> ajan -> ajan ... en fazla bu derinlik
AD_DESENI = re.compile(r"^[\w .\-]{1,40}$", re.UNICODE)


def simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


class KuyrukOgesi(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    metin: str = Field(min_length=1, max_length=20000)
    kimden: str = "kullanici"  # kullanici | ajan:<id> | telegram:<chat> | webhook:<id> | rutin
    zincir: int = 0  # ajanlar arasi mesaj derinligi
    cevap_ajan: str = ""  # bu is bitince sonucu bu ajanin kuyruguna gonder
    zaman: str = Field(default_factory=simdi)


class KonusmaMesaji(BaseModel):
    rol: str  # gelen | cevap | bilgi
    metin: str
    kimden: str = ""
    run: str = ""
    durum: str = ""
    zaman: str = Field(default_factory=simdi)


class Ajan(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ad: str = Field(min_length=1, max_length=40)
    avatar: str = Field(default="🤖", max_length=8)
    aciklama: str = Field(default="", max_length=300)
    talimat: str = Field(default="", max_length=20000)
    klasor: str = ""  # bos: <veri>/ajanlar/<id>/calisma
    model: str = ""  # bos: uygulamanin aktif modeli
    saglayici: str = "kairo"  # kairo | claude (Claude Code CLI) | codex (Codex CLI)
    cli_oturum: str = ""  # CLI saglayicisinda konusma surekliligi (--resume)
    hafiza: list[str] = Field(default_factory=list)  # ajanin kendine yazdigi kalici notlar
    duraklatildi: bool = False
    kuyruk: list[KuyrukOgesi] = Field(default_factory=list)
    aktif_run: str = ""
    aktif_is: KuyrukOgesi | None = None
    son_run: str = ""  # konusma surekliligi: sonraki is bunun ozetiyle baslar
    konusma: list[KonusmaMesaji] = Field(default_factory=list)
    olusturma: str = Field(default_factory=simdi)
    guncelleme: str = Field(default_factory=simdi)

    def ozet(self) -> dict:
        d = self.model_dump(exclude={"konusma", "kuyruk", "aktif_is"})
        d["kuyruk_sayisi"] = len(self.kuyruk)
        d["durum"] = (
            "duraklatildi" if self.duraklatildi else "calisiyor" if self.aktif_run else "bosta"
        )
        return d


class AjanDeposu:
    """<veri>/ajanlar.json. Tek surecte, tek kilitle (API ve dagitim dongusu ayni surecte)."""

    def __init__(self, veri_dizini: Path) -> None:
        self.veri = veri_dizini
        self.yol = veri_dizini / "ajanlar.json"
        self._kilit = threading.RLock()

    # ---- temel ----
    def _oku(self) -> list[Ajan]:
        return [Ajan(**a) for a in (json_oku(self.yol, {}) or {}).get("ajanlar", [])]

    def _yaz(self, liste: list[Ajan]) -> None:
        json_yaz(self.yol, {"ajanlar": [a.model_dump() for a in liste]})

    def liste(self) -> list[Ajan]:
        with self._kilit:
            return self._oku()

    def getir(self, ajan_id: str) -> Ajan:
        for a in self.liste():
            if a.id == ajan_id or a.ad.lower() == ajan_id.strip().lower():
                return a
        raise Bulunamadi(f"Ajan bulunamadi: {ajan_id}")

    def _guncelle(self, ajan_id: str, fonk) -> Ajan:
        with self._kilit:
            liste = self._oku()
            for i, a in enumerate(liste):
                if a.id == ajan_id:
                    fonk(a)
                    a.guncelleme = simdi()
                    liste[i] = a
                    self._yaz(liste)
                    return a
            raise Bulunamadi(f"Ajan bulunamadi: {ajan_id}")

    def klasor(self, a: Ajan) -> Path:
        p = Path(a.klasor) if a.klasor else self.veri / "ajanlar" / a.id / "calisma"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ---- olustur / duzenle / sil ----
    def olustur(self, veri: dict) -> Ajan:
        izinli = {"ad", "avatar", "aciklama", "talimat", "klasor", "model", "saglayici"}
        if veri.get("saglayici", "kairo") not in ("kairo", "claude", "codex"):
            raise UygulamaHatasi("Saglayici kairo, claude ya da codex olmali.")
        a = Ajan(**{k: v for k, v in veri.items() if k in izinli})
        if not AD_DESENI.match(a.ad):
            raise UygulamaHatasi("Ajan adi harf, rakam, bosluk, nokta ve tire icerebilir (<=40).")
        with self._kilit:
            liste = self._oku()
            if len(liste) >= MAX_AJAN:
                raise UygulamaHatasi(f"En fazla {MAX_AJAN} ajan olusturulabilir.")
            if any(x.ad.lower() == a.ad.lower() for x in liste):
                raise UygulamaHatasi(f"Bu adda ajan var: {a.ad}")
            if a.klasor and not Path(a.klasor).is_absolute():
                raise UygulamaHatasi("Klasor tam yol olmali (or. C:\\Users\\...\\proje).")
            liste.append(a)
            self._yaz(liste)
        self.klasor(a)
        return a

    def duzenle(self, ajan_id: str, veri: dict) -> Ajan:
        izinli = {"ad", "avatar", "aciklama", "talimat", "klasor", "model", "duraklatildi",
                  "saglayici", "cli_oturum"}  # fmt: skip
        if veri.get("saglayici", "kairo") not in ("kairo", "claude", "codex"):
            raise UygulamaHatasi("Saglayici kairo, claude ya da codex olmali.")

        def f(a: Ajan) -> None:
            for k, v in veri.items():
                if k in izinli:
                    setattr(a, k, v)
            if not AD_DESENI.match(a.ad):
                raise UygulamaHatasi("Gecersiz ajan adi.")

        return self._guncelle(ajan_id, f)

    def sil(self, ajan_id: str) -> None:
        with self._kilit:
            liste = self._oku()
            kalan = [a for a in liste if a.id != ajan_id]
            if len(kalan) == len(liste):
                raise Bulunamadi(f"Ajan bulunamadi: {ajan_id}")
            self._yaz(kalan)  # calisma klasoru SILINMEZ (kullanicinin dosyalari olabilir)

    # ---- kuyruk ----
    def kuyruga_ekle(self, ajan_id: str, oge: KuyrukOgesi) -> Ajan:
        if oge.zincir > MAX_ZINCIR:
            raise UygulamaHatasi(f"Ajanlar arasi mesaj zinciri {MAX_ZINCIR} derinligi asti.")

        def f(a: Ajan) -> None:
            if len(a.kuyruk) >= MAX_KUYRUK:
                raise UygulamaHatasi(f"{a.ad} kuyrugu dolu ({MAX_KUYRUK}).")
            a.kuyruk.append(oge)
            a.konusma.append(KonusmaMesaji(rol="gelen", metin=oge.metin, kimden=oge.kimden))
            a.konusma = a.konusma[-MAX_GECMIS:]

        return self._guncelle(self.getir(ajan_id).id, f)

    def kuyruktan_sil(self, ajan_id: str, oge_id: str) -> Ajan:
        def f(a: Ajan) -> None:
            a.kuyruk = [k for k in a.kuyruk if k.id != oge_id]

        return self._guncelle(ajan_id, f)

    def al(self, ajan_id: str) -> tuple[Ajan, KuyrukOgesi] | None:
        """Bosta ve duraklatilmamis ajanin ilk isini kuyruktan alir (aktif_run='baslatiliyor')."""
        with self._kilit:
            a = self.getir(ajan_id)
            if a.duraklatildi or a.aktif_run or not a.kuyruk:
                return None
            oge = a.kuyruk[0]

            def f(x: Ajan) -> None:
                x.kuyruk = x.kuyruk[1:]
                x.aktif_is, x.aktif_run = oge, "baslatiliyor"

            return self._guncelle(a.id, f), oge

    def basladi(self, ajan_id: str, run_id: str) -> Ajan:
        def f(x: Ajan) -> None:
            x.aktif_run = run_id
            x.konusma.append(KonusmaMesaji(rol="bilgi", metin="Ise basladi.", run=run_id))

        return self._guncelle(ajan_id, f)

    def baslamadi(self, ajan_id: str, hata: str) -> Ajan:
        def f(x: Ajan) -> None:
            x.aktif_run, x.aktif_is = "", None
            x.konusma.append(KonusmaMesaji(rol="bilgi", metin=f"Is baslatilamadi: {hata}"))

        return self._guncelle(ajan_id, f)

    def bitti(
        self, ajan_id: str, run_id: str, durum: str, ozet: str
    ) -> tuple[Ajan, KuyrukOgesi | None]:
        is_: list[KuyrukOgesi | None] = [None]

        def f(a: Ajan) -> None:
            is_[0] = a.aktif_is
            a.aktif_run, a.aktif_is, a.son_run = "", None, run_id
            a.konusma.append(
                KonusmaMesaji(rol="cevap", metin=ozet or durum, run=run_id, durum=durum)
            )
            a.konusma = a.konusma[-MAX_GECMIS:]

        return self._guncelle(ajan_id, f), is_[0]

    def hafizaya_ekle(self, ajan_id: str, not_: str) -> Ajan:
        not_ = not_.strip()[:500]
        if not not_:
            raise UygulamaHatasi("Bos not eklenmez.")

        def f(a: Ajan) -> None:
            if not_ not in a.hafiza:
                a.hafiza = (a.hafiza + [not_])[-50:]

        return self._guncelle(ajan_id, f)

    # ---- modele giden kimlik ----
    def sistem_metni(self, a: Ajan, digerleri: list[Ajan]) -> str:
        parcalar = [
            f"KIMLIGIN: Sen '{a.ad}' adli kalici bir ajansin. {a.aciklama}".strip(),
            f"CALISMA KLASORUN: {self.klasor(a)}\n"
            "Dosyalari YALNIZ bu klasorde olustur ve degistir; "
            "kullanici mesajinda acikca baska bir yol vermedikce (genel proje kurallari dahil) "
            "disina dosya yazma, yeni proje klasoru acma.",
        ]
        if a.talimat.strip():
            parcalar.append(f"TALIMATLARIN (kullanici yazdi):\n{a.talimat.strip()}")
        if a.hafiza:
            notlar = "\n".join(f"- {n}" for n in a.hafiza[-20:])
            parcalar.append(f"KALICI NOTLARIN (ajan_notu ile eklenir):\n{notlar}")
        if digerleri:
            liste = "; ".join(f"{x.ad}: {x.aciklama or 'aciklama yok'}" for x in digerleri[:20])
            parcalar.append(
                "DIGER AJANLAR (ajana_mesaj ile is verebilirsin; cevabi sonra sana gelir): " + liste
            )
        return "\n\n".join(parcalar)


def bekle_ve_tekrarla(fonk, deneme: int = 3, aralik: float = 0.05):
    """Dosya kilidi yarisinda kisa tekrar (Windows'ta json_yaz nadiren PermissionError verir)."""
    for i in range(deneme):
        try:
            return fonk()
        except PermissionError:
            if i == deneme - 1:
                raise
            time.sleep(aralik)
    return None


AJANA_MESAJ_ARACI = {
    "type": "function",
    "function": {
        "name": "ajana_mesaj",
        "description": "Baska bir kalici ajana is ya da soru gonderir (kendi klasoru ve "
        "talimatlariyla calisir). Cevabi bitince SANA yeni bir mesaj olarak gelir; beklemene "
        "gerek yok. Isi net ve kendi basina anlasilir yaz.",
        "parameters": {
            "type": "object",
            "properties": {
                "ajan": {"type": "string", "description": "Hedef ajanin adi"},
                "mesaj": {"type": "string"},
            },
            "required": ["ajan", "mesaj"],
        },
    },
}

AJAN_NOTU_ARACI = {
    "type": "function",
    "function": {
        "name": "ajan_notu",
        "description": "Kendi kalici hafizana kisa bir not ekler (sonraki islerinde gorursun). "
        "Yalniz ileride ise yarayacak kalici bilgi yaz; gizli bilgi (parola, anahtar) yazma.",
        "parameters": {
            "type": "object",
            "properties": {"not": {"type": "string"}},
            "required": ["not"],
        },
    },
}
