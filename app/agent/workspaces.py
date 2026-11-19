"""Calisma alani (proje): kok yollar, guven durumu, proje bazli ayar ve talimat kapsami (A1.1-A1.2).

Bir `CalismaAlani` ajanin dokunabilecegi dis siniri tanimlar. Kok listesi bos olan bir alanda
hicbir dosya okunamaz; ek klasor acikca yetkilendirilir. Guven durumu talimat kapsamini belirler:
GUVENILMEYEN bir repodaki `AGENTS.md`/`CLAUDE.md` sisteme eklenmez, cunku repo metni kendi
yetkisini yukseltemez (A1.2).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.agent.yollar import ham_dogrula, icinde_mi, kanonik
from app.exceptions import Bulunamadi, UygulamaHatasi, YetkiYok
from app.services.depo import json_oku, json_yaz

MAX_KOK = 8
MAX_SON_PROJE = 12
PROJE_TALIMAT_ADLARI = ("KAIRO.md", "AGENTS.md", "CLAUDE.md", ".yas/AGENTS.md")


class Guven(StrEnum):
    guvenilir = "guvenilir"  # proje talimatlari okunur, politika kapsaminda arac kullanilir
    sinirli = "sinirli"  # proje talimatlari okunmaz; yalniz salt okunur araclar
    guvenilmeyen = "guvenilmeyen"  # yalniz acikca secilen dosyalar; talimat yok


class Mod(StrEnum):
    sohbet = "sohbet"  # dosya/komut araci yok
    planla = "planla"  # SALT OKUNUR: hicbir yan etki uygulanmaz
    onayli = "onayli"  # yan etkili her adim kullanici onayi ister
    otomatik = "otomatik"  # politika kapsaminda otomatik; sinirsiz yetki DEGIL


def simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CalismaAlani(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ad: str = "Proje"
    kokler: list[str] = []  # kanonik mutlak yollar
    guven: Guven = Guven.sinirli
    mod: Mod = Mod.sohbet
    ek_klasorler: list[str] = []  # kok disinda ACIKCA yetkilendirilen klasorler
    repo: str = ""
    dal: str = ""
    # Claude "Coordinator / Threads" gibi iki model; bos: uygulamanin aktif modeli
    koordinator_model: str = Field(default="", max_length=200)  # proje sohbeti: plan, arastirma
    uygulayici_model: str = Field(default="", max_length=200)  # thread + alt ajan: uygulama
    olusturma: str = Field(default_factory=simdi)
    guncelleme: str = Field(default_factory=simdi)

    @field_validator("ad")
    @classmethod
    def _ad(cls, v: str) -> str:
        return (v or "").strip()[:80] or "Proje"

    @property
    def izinli_kokler(self) -> list[Path]:
        """Dosya araclarinin dokunabilecegi tum kokler (proje kokleri + ek klasorler)."""
        return [Path(k) for k in (*self.kokler, *self.ek_klasorler)]

    def salt_okunur_mu(self) -> bool:
        return self.mod in (Mod.sohbet, Mod.planla) or self.guven is Guven.guvenilmeyen

    def talimat_okunur_mu(self) -> bool:
        """Proje icindeki talimat dosyalari sistem mesajina eklenebilir mi (A1.2)."""
        return self.guven is Guven.guvenilir

    def alt_talimatlar(self, dosya: Path) -> list[Path]:
        """Claude Code ic ice CLAUDE.md: dosyanin klasorunden proje kokune kadar (kok HARIC,
        o sistem mesajinda) talimat dosyalari; en ust klasordeki once. Yalniz guvenilir projede."""
        if not self.talimat_okunur_mu():
            return []
        bulunan: list[Path] = []
        for kok in self.kokler:
            k = Path(kok)
            try:
                if not icinde_mi(kok, dosya):
                    continue
            except YetkiYok:
                continue
            d = dosya.parent
            while d != k and k in d.parents:
                for ad in PROJE_TALIMAT_ADLARI:
                    p = d / ad
                    try:
                        if p.is_file() and icinde_mi(kok, p):
                            bulunan.append(kanonik(p))
                    except YetkiYok:
                        continue
                d = d.parent
        return list(reversed(list(dict.fromkeys(bulunan))))

    def proje_talimatlari(self) -> list[Path]:
        """Guvenilir projede bulunan talimat dosyalari. Guvenilmeyen/sinirli projede BOS."""
        if not self.talimat_okunur_mu():
            return []
        bulunan: list[Path] = []
        for kok in self.kokler:
            for ad in PROJE_TALIMAT_ADLARI:
                p = Path(kok) / ad
                try:  # kok disina link eden talimat dosyasi okunmaz
                    if p.is_file() and icinde_mi(kok, p):
                        bulunan.append(kanonik(p))
                except YetkiYok:
                    continue
        return list(dict.fromkeys(bulunan))


class WorkspaceDeposu:
    """Projeler ve son kullanilanlar: data/projeler.json. Aktif proje tek olur."""

    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "projeler.json"

    def _ham(self) -> dict:
        ham = json_oku(self.yol, {}) or {}
        return {"alanlar": ham.get("alanlar", []), "aktif": ham.get("aktif") or ""}

    def _yaz(self, veri: dict) -> None:
        json_yaz(self.yol, veri)

    def liste(self) -> list[CalismaAlani]:
        alanlar = []
        for h in self._ham()["alanlar"]:
            try:
                alanlar.append(CalismaAlani(**h))
            except ValueError:  # bozuk kayit tum listeyi dusurmesin
                continue
        return sorted(alanlar, key=lambda a: a.guncelleme, reverse=True)[:MAX_SON_PROJE]

    def getir(self, alan_id: str) -> CalismaAlani:
        if not re.fullmatch(r"[0-9a-f]{6,32}", alan_id or ""):
            raise Bulunamadi("Proje bulunamadi.")
        for a in self.liste():
            if a.id == alan_id:
                return a
        raise Bulunamadi("Proje bulunamadi.")

    def aktif(self) -> CalismaAlani | None:
        aktif_id = self._ham()["aktif"]
        if not aktif_id:
            return None
        try:
            return self.getir(aktif_id)
        except Bulunamadi:
            return None

    def ac(
        self,
        yol: str,
        ad: str = "",
        guven: Guven = Guven.sinirli,
        modeller: tuple[str, str] = ("", ""),
    ) -> CalismaAlani:
        """Klasoru proje olarak acar (ayni kok varsa onu gunceller) ve aktif yapar."""
        kok = kanonik(ham_dogrula(yol))
        if not kok.is_dir():
            raise UygulamaHatasi(f"Klasor bulunamadi: {kok}")
        veri = self._ham()
        for h in veri["alanlar"]:
            if (
                h.get("kokler")
                and icinde_mi(h["kokler"][0], kok)
                and icinde_mi(kok, h["kokler"][0])
            ):
                alan = CalismaAlani(**h)
                alan.guven = guven
                alan.guncelleme = simdi()
                return self.kaydet(alan, aktif=True)
        alan = CalismaAlani(
            ad=ad or kok.name, kokler=[str(kok)], guven=guven,
            koordinator_model=modeller[0], uygulayici_model=modeller[1],
        )  # fmt: skip
        return self.kaydet(alan, aktif=True)

    def kaydet(self, alan: CalismaAlani, *, aktif: bool = False) -> CalismaAlani:
        alan.guncelleme = simdi()
        veri = self._ham()
        veri["alanlar"] = [h for h in veri["alanlar"] if h.get("id") != alan.id]
        veri["alanlar"].insert(0, alan.model_dump(mode="json"))
        veri["alanlar"] = veri["alanlar"][:MAX_SON_PROJE]
        if aktif:
            veri["aktif"] = alan.id
        self._yaz(veri)
        return alan

    def etkinlestir(self, alan_id: str) -> CalismaAlani:
        """Kayitli projeyi ayarlarina (guven, mod) dokunmadan aktif yapar; sohbet secilince."""
        alan = self.getir(alan_id)
        veri = self._ham()
        veri["aktif"] = alan.id
        self._yaz(veri)
        return alan

    def kapat(self) -> None:
        veri = self._ham()
        veri["aktif"] = ""
        self._yaz(veri)

    def sil(self, alan_id: str) -> None:
        alan = self.getir(alan_id)
        veri = self._ham()
        veri["alanlar"] = [h for h in veri["alanlar"] if h.get("id") != alan.id]
        if veri["aktif"] == alan.id:
            veri["aktif"] = ""
        self._yaz(veri)

    def kok_ekle(self, alan_id: str, yol: str) -> CalismaAlani:
        """Cok koklu workspace: ikinci bir proje kokunu ACIKCA yetkilendirir."""
        alan = self.getir(alan_id)
        kok = kanonik(ham_dogrula(yol))
        if not kok.is_dir():
            raise UygulamaHatasi(f"Klasor bulunamadi: {kok}")
        if len(alan.kokler) >= MAX_KOK:
            raise UygulamaHatasi(f"En fazla {MAX_KOK} kok eklenebilir.")
        if str(kok) not in alan.kokler:
            alan.kokler.append(str(kok))
        return self.kaydet(alan)

    def klasor_yetkilendir(self, alan_id: str, yol: str) -> CalismaAlani:
        """Kok disinda tek bir klasore acik yetki (kullanici karari)."""
        alan = self.getir(alan_id)
        kok = kanonik(ham_dogrula(yol))
        if not kok.is_dir():
            raise UygulamaHatasi(f"Klasor bulunamadi: {kok}")
        if len(alan.ek_klasorler) >= MAX_KOK:
            raise UygulamaHatasi(f"En fazla {MAX_KOK} ek klasor yetkilendirilebilir.")
        if str(kok) not in alan.ek_klasorler:
            alan.ek_klasorler.append(str(kok))
        return self.kaydet(alan)

    def mod_ayarla(self, alan_id: str, mod: Mod) -> CalismaAlani:
        alan = self.getir(alan_id)
        alan.mod = mod
        return self.kaydet(alan)

    def modeller_ayarla(self, alan_id: str, koordinator: str, uygulayici: str) -> CalismaAlani:
        alan = self.getir(alan_id)
        alan.koordinator_model, alan.uygulayici_model = koordinator.strip(), uygulayici.strip()
        return self.kaydet(alan)

    def guven_ayarla(self, alan_id: str, guven: Guven) -> CalismaAlani:
        alan = self.getir(alan_id)
        alan.guven = guven
        return self.kaydet(alan)
