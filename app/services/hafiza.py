"""Kalici hafiza (A4.4): kaynak, tarih, kapsam, guven ve gecerlilik bilgili kisa notlar.

- Sir SAKLANMAZ: maskeleme metni degistiriyorsa kayit reddedilir.
- Kapsam: "genel" ya da proje (calisma alani) kimligi; ilgili() ikisini birlikte verir.
- Sohbet temizleme (clear) hafizayi SILMEZ; hafiza yalniz buradan silinir.
- Otomatik ogrenme (ajanin kendi not eklemesi) ayardan acilir; varsayilan KAPALI.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.policy import maskele
from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

MAX_KAYIT = 300
MAX_SISTEM_KAYDI = 6  # Ogrenen sistem C: ilgiye gore en iyi 6
MAX_SISTEM_KARAKTER = 800
MAX_DAYANAK = 4
_KELIME = re.compile(r"[a-z0-9çğıöşü_]{3,}")
YARGILAR = ("yararli", "eski", "yanlis")


class Hafiza(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    metin: str = Field(min_length=1, max_length=1000)
    kaynak: Literal["kullanici", "ajan"] = "kullanici"
    kapsam: str = "genel"
    guven: Literal["yuksek", "orta", "dusuk"] = "orta"
    tarih: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    gecerlilik: str | None = None  # YYYY-MM-DD; sonrasinda kullanilmaz
    aktif: bool = True
    # Kanit (WrongStack SAGE fikri): "dosya_yolu::icerdigi metin". Dosya artik metni icermiyorsa
    # not ESKI sayilir ve sisteme girmez (kod degisti, bilgi bayatladi).
    dayanak: list[str] = Field(default=[], max_length=MAX_DAYANAK)
    yararli: int = 0
    eski: int = 0
    yanlis: int = 0
    revizyon: int = 1

    def dayanak_tutuyor_mu(self) -> bool:
        for d in self.dayanak:
            yol, _, parca = d.partition("::")
            try:
                if parca and parca not in Path(yol).read_text(encoding="utf-8", errors="ignore"):
                    return False
            except OSError:
                return False
        return True

    def puan(self, kelimeler: set[str]) -> float:
        ortak = len(kelimeler & set(_KELIME.findall(self.metin.lower())))
        return ortak * 2 + self.yararli - 2 * self.yanlis - self.eski + (self.guven == "yuksek")

    def gecerli_mi(self, bugun: date | None = None) -> bool:
        if not self.aktif:
            return False
        if self.gecerlilik:
            try:
                return (bugun or date.today()) <= date.fromisoformat(self.gecerlilik)
            except ValueError:
                return False
        return True


def _sir_yok(metin: str) -> str:
    metin = metin.strip()
    if maskele(metin) != metin:
        raise UygulamaHatasi("Bu not gizli bilgi (anahtar, parola, token) iceriyor; kaydedilmez.")
    return metin


class HafizaDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "hafiza.json"

    def _liste(self) -> list[Hafiza]:
        sonuc = []
        for h in json_oku(self.yol, []) or []:
            try:
                sonuc.append(Hafiza(**h))
            except ValueError:
                continue
        return sonuc

    def _yaz(self, kayitlar: list[Hafiza]) -> None:
        json_yaz(self.yol, [k.model_dump() for k in kayitlar])

    def liste(self, kapsam: str | None = None) -> list[dict]:
        return [k.model_dump() for k in self._liste() if kapsam is None or k.kapsam == kapsam]

    def ekle(self, metin: str, **alanlar) -> dict:
        kayitlar = self._liste()
        if len(kayitlar) >= MAX_KAYIT:
            raise UygulamaHatasi(f"Hafiza dolu ({MAX_KAYIT} kayit); eskileri silin.")
        k = Hafiza(metin=_sir_yok(metin), **alanlar)
        if any(x.metin == k.metin and x.kapsam == k.kapsam for x in kayitlar):
            raise UygulamaHatasi("Bu not zaten kayitli.")
        self._yaz([*kayitlar, k])
        return k.model_dump()

    def guncelle(self, kayit_id: str, degisiklik: dict) -> dict:
        kayitlar = self._liste()
        for i, k in enumerate(kayitlar):
            if k.id == kayit_id:
                izinli = {"metin", "guven", "gecerlilik", "aktif", "kapsam"}
                yeni = k.model_dump() | {a: v for a, v in degisiklik.items() if a in izinli}
                if "metin" in degisiklik:
                    yeni["metin"] = _sir_yok(str(degisiklik["metin"]))
                kayitlar[i] = Hafiza(**yeni)
                self._yaz(kayitlar)
                return kayitlar[i].model_dump()
        raise Bulunamadi("Hafiza kaydi bulunamadi.")

    def ice_aktar(self, metin: str, kaynak_adi: str = "") -> dict:
        """Baska asistanin (Claude, ChatGPT, Grok...) hafiza metnini satir satir not yapar.
        Madde isaretleri temizlenir; gizli bilgi iceren ve zaten kayitli satirlar atlanir."""
        eklenen, atlanan, gizli, dolu = 0, 0, 0, False
        for satir in str(metin or "").splitlines():
            satir = re.sub(r"^\s*(?:[-*•·]|\d+[.)])\s*", "", satir).strip()
            if len(satir) < 3 or satir.startswith("#"):
                continue
            try:
                self.ekle(satir[:1000], kaynak="kullanici", guven="orta")
                eklenen += 1
            except UygulamaHatasi as e:
                if "gizli" in e.mesaj:
                    gizli += 1
                elif "dolu" in e.mesaj:
                    dolu = True
                    break
                else:
                    atlanan += 1
        return {"eklenen": eklenen, "atlanan": atlanan, "gizli": gizli, "dolu": dolu,
                "kaynak": kaynak_adi[:40]}  # fmt: skip

    def sil(self, kayit_id: str) -> dict:
        kayitlar = self._liste()
        kalan = [k for k in kayitlar if k.id != kayit_id]
        if len(kalan) == len(kayitlar):
            raise Bulunamadi("Hafiza kaydi bulunamadi.")
        self._yaz(kalan)
        return {"silindi": kayit_id}

    def disa_aktar(self) -> dict:
        return {
            "surum": 1,
            "tarih": datetime.now().isoformat(timespec="seconds"),
            "kayitlar": self.liste(),
        }

    def ilgili(self, kapsam: str, sorgu: str = "") -> list[Hafiza]:
        """Gecerli, yanlis sayilmamis, dayanagi tutan notlar; sorguya ilgiye gore siralanir."""
        kelimeler = set(_KELIME.findall(sorgu.lower()))
        uygun = [
            k
            for k in self._liste()
            if k.kapsam in ("genel", kapsam) and k.gecerli_mi() and k.yanlis < 2
            and k.dayanak_tutuyor_mu()
        ]  # fmt: skip
        # esit puanda yeni kayit once (eski davranis: son kayitlar)
        return sorted(reversed(uygun), key=lambda k: k.puan(kelimeler), reverse=True)

    def yargila(self, kayit_id: str, yargi: str, duzeltme: str = "") -> dict:
        """Ajan/kullanici notu degerlendirir; duzeltme metni yeni revizyon olur."""
        if yargi not in YARGILAR:
            raise UygulamaHatasi(f"Yargi su degerlerden biri olmali: {', '.join(YARGILAR)}")
        kayitlar = self._liste()
        for i, k in enumerate(kayitlar):
            if k.id == kayit_id:
                yeni = k.model_dump()
                yeni[yargi] += 1
                if duzeltme.strip():
                    yeni |= {"metin": _sir_yok(duzeltme), "revizyon": k.revizyon + 1,
                             "yanlis": 0, "eski": 0}  # fmt: skip
                kayitlar[i] = Hafiza(**yeni)
                self._yaz(kayitlar)
                return kayitlar[i].model_dump()
        raise Bulunamadi("Hafiza kaydi bulunamadi.")

    def sistem_metni(self, kapsam: str, sorgu: str = "") -> str:
        satirlar = [
            "HAFIZA (onceki oturumlardan notlar; dogrulanmamis olabilir, kanit yerine gecmez. "
            "Bir not yanlis ya da eskiyse hafiza_yargila ile bildir):"
        ]
        boy = len(satirlar[0])
        for k in self.ilgili(kapsam, sorgu)[:MAX_SISTEM_KAYDI]:
            satir = f"- [{k.id}, {k.guven}, {k.tarih[:10]}] {k.metin}"
            if boy + len(satir) > MAX_SISTEM_KARAKTER:
                break
            satirlar.append(satir)
            boy += len(satir)
        return "\n".join(satirlar) if len(satirlar) > 1 else ""
