"""Ders defteri: ajanin gorevler arasi hatalardan ogrenmesi (OGRENEN-SISTEM-PLANI.md madde A).

Hata, izin reddi ve basarisiz gorev bitisi <veri>/dersler.json'a yazilir (model cagrisi yok).
Ayni hata (degisken kisimlari atilmis imza) tekrar gorulunce sayac artar; ayni aracin sonraki
basarili cagrisi "ise yarayan" cozum olarak kaydedilir. Yeni gorevde hedefe en ilgili dersler
kisa bir not olarak sisteme, tekrar eden hatada da ders arac sonucuna eklenir.
"""

from __future__ import annotations

import hashlib
import re
import threading
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.agent.policy import maskele
from app.services.depo import json_oku, json_yaz

MAX_DERS = 300
SISTEM_SINIRI = 600  # yeni gorevde sisteme eklenen ders notu (karakter)
_KELIME = re.compile(r"[a-z0-9çğıöşü_]{3,}")


def simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


def imza(arac: str, hata: str) -> str:
    """Degisken kisimlar (yol, sayi, tirnak ici) atilir: ayni hata farkli dosyada da eslesir."""
    h = hata.lower()
    # Windows yolunda bosluk olur (Portable Programlar): surucu harfinden tirnak/satir sonuna kadar
    h = re.sub(r"[a-z]:[\\/][^'\"<>|\r\n]*|/[\w.\-/]{3,}", "<yol>", h)
    h = re.sub(r"'[^']*'|\"[^\"]*\"", "<x>", h)
    h = re.sub(r"\d+", "<n>", h)
    h = re.sub(r"\s+", " ", h).strip()[:160]
    return hashlib.sha1(f"{arac}|{h}".encode()).hexdigest()[:16]


def _kelimeler(metin: str) -> set[str]:
    return set(_KELIME.findall(metin.lower()))


class Ders(BaseModel):
    imza: str
    arac: str
    hata: str
    sayi: int = 1
    hedefler: list[str] = []  # gorulen gorev hedefleri (ilgililik icin, en fazla 3)
    cozum: str = ""
    ilk: str = ""
    son: str = ""

    def metin(self) -> str:
        cozum = (
            f" Ise yarayan: {self.cozum}"
            if self.cozum
            else " Cozumu kayitli degil; farkli yol dene."
        )
        return f"- {self.arac}: {self.hata[:160]} ({self.sayi} kez).{cozum}"


class DersDefteri:
    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "dersler.json"
        self._kilit = threading.Lock()

    def liste(self) -> list[Ders]:
        return [Ders(**d) for d in (json_oku(self.yol, {}) or {}).get("dersler", [])]

    def _yaz(self, dersler: list[Ders]) -> None:
        # en cok tekrar eden + en yeni kalir
        dersler = sorted(dersler, key=lambda d: (d.sayi, d.son), reverse=True)[:MAX_DERS]
        json_yaz(self.yol, {"dersler": [d.model_dump() for d in dersler]})

    def hata(self, arac: str, hata: str, hedef: str = "") -> Ders:
        """Hatayi yazar; donen dersin sayi > 1 ise bu hata daha once gorulmus demektir."""
        hata = maskele(str(hata))[:300]
        anahtar = imza(arac, hata)
        with self._kilit:
            dersler = self.liste()
            d = next((x for x in dersler if x.imza == anahtar), None)
            if d is None:
                d = Ders(imza=anahtar, arac=arac, hata=hata, ilk=simdi())
                dersler.append(d)
            else:
                d.sayi += 1
                d.hata = hata
            hedef = maskele(hedef.strip())[:200]
            if hedef and hedef not in d.hedefler:
                d.hedefler = [*d.hedefler, hedef][-3:]
            d.son = simdi()
            self._yaz(dersler)
            return d

    def cozuldu(self, anahtar: str, cozum: str) -> None:
        with self._kilit:
            dersler = self.liste()
            d = next((x for x in dersler if x.imza == anahtar), None)
            if d is None:
                return
            d.cozum = maskele(cozum)[:200]
            self._yaz(dersler)

    def ilgili(self, hedef: str, k: int = 5) -> str:
        """Hedefle kelime ortakligi olan (ya da cok tekrar eden) en fazla k ders; bos olabilir."""
        aranan = _kelimeler(hedef)
        puanli = []
        for d in self.liste():
            ortak = len(aranan & _kelimeler(" ".join([d.arac, d.hata, *d.hedefler])))
            if ortak or d.sayi >= 3:
                puanli.append((ortak * 2 + min(d.sayi, 5), d))
        puanli.sort(key=lambda x: x[0], reverse=True)
        satirlar, uzunluk = [], 0
        for _, d in puanli[:k]:
            s = d.metin()
            if uzunluk + len(s) > SISTEM_SINIRI:
                break
            satirlar.append(s)
            uzunluk += len(s)
        if not satirlar:
            return ""
        return "ONCEKI GOREVLERDEN DERSLER (ayni hatayi tekrarlama):\n" + "\n".join(satirlar)
