"""Kalici hafiza (A4.4): kaynak, tarih, kapsam, guven ve gecerlilik bilgili kisa notlar.

- Sir SAKLANMAZ: maskeleme metni degistiriyorsa kayit reddedilir.
- Kapsam: "genel" ya da proje (calisma alani) kimligi; ilgili() ikisini birlikte verir.
- Sohbet temizleme (clear) hafizayi SILMEZ; hafiza yalniz buradan silinir.
- Otomatik ogrenme (ajanin kendi not eklemesi) ayardan acilir; varsayilan KAPALI.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.policy import maskele
from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

MAX_KAYIT = 300
MAX_SISTEM_KAYDI = 20


class Hafiza(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    metin: str = Field(min_length=1, max_length=1000)
    kaynak: Literal["kullanici", "ajan"] = "kullanici"
    kapsam: str = "genel"
    guven: Literal["yuksek", "orta", "dusuk"] = "orta"
    tarih: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    gecerlilik: str | None = None  # YYYY-MM-DD; sonrasinda kullanilmaz
    aktif: bool = True

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

    def ilgili(self, kapsam: str) -> list[Hafiza]:
        return [k for k in self._liste() if k.kapsam in ("genel", kapsam) and k.gecerli_mi()]

    def sistem_metni(self, kapsam: str) -> str:
        kayitlar = self.ilgili(kapsam)[-MAX_SISTEM_KAYDI:]
        if not kayitlar:
            return ""
        satirlar = [
            "HAFIZA (onceki oturumlardan notlar; dogrulanmamis olabilir, kanit yerine gecmez):"
        ]
        satirlar += [f"- [{k.guven}, {k.kaynak}, {k.tarih[:10]}] {k.metin}" for k in kayitlar]
        return "\n".join(satirlar)
