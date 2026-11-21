"""Dinamik is akislari (A8.6): tipli adimlar + bagimlilik + kosul + sinirli tekrar.

Adim turleri:
- "ajan": AgentRunner gorevi (ayri baglam). Bitene kadar beklenir.
- "komut": proje kokunde kabuk komutu; AjanAracKaydi uzerinden IZIN MOTORUNDAN gecer.
Kod CALISTIRILMAZ (eval yok): akis yalniz bu iki tipten olusan veridir.
Kosul: {"adim": id, "durum": "basarili"|"basarisiz"} saglanmazsa adim "atlandi" olur.
Onay bekleyen komut akisi durdurur; kullanici onaylayip "devam" deyince kaldigi yerden surer.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

MAX_ADIM = 30
BITMIS = {"basarili", "basarisiz", "atlandi"}


class Kosul(BaseModel):
    adim: str
    durum: Literal["basarili", "basarisiz"]


class AkisAdimi(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    tur: Literal["ajan", "komut"]
    hedef: str = Field(default="", max_length=4000)  # ajan
    komut: str = Field(default="", max_length=2000)  # komut
    bagimli: list[str] = []
    kosul: Kosul | None = None
    tekrar: int = Field(default=0, ge=0, le=3)
    durum: str = "bekliyor"  # bekliyor|calisiyor|onay_bekliyor|basarili|basarisiz|atlandi
    deneme: int = 0
    sonuc: str = ""
    run_id: str = ""

    @model_validator(mode="after")
    def _alan(self) -> AkisAdimi:
        if self.tur == "ajan" and not self.hedef.strip():
            raise ValueError(f"'{self.id}': ajan adiminda hedef zorunlu.")
        if self.tur == "komut" and not self.komut.strip():
            raise ValueError(f"'{self.id}': komut adiminda komut zorunlu.")
        return self


class Akis(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ad: str = Field(min_length=1, max_length=120)
    adimlar: list[AkisAdimi] = Field(min_length=1, max_length=MAX_ADIM)
    durum: str = "bekliyor"  # bekliyor|calisiyor|onay_bekliyor|basarili|basarisiz
    olusturma: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @model_validator(mode="after")
    def _graf(self) -> Akis:
        ids = [a.id for a in self.adimlar]
        if len(set(ids)) != len(ids):
            raise ValueError("Adim kimlikleri benzersiz olmali.")
        for a in self.adimlar:
            for b in [*a.bagimli, *([a.kosul.adim] if a.kosul else [])]:
                if b not in ids:
                    raise ValueError(f"'{a.id}' bilinmeyen adima bagli: {b}")
        sira(self.adimlar)  # dongu varsa hata
        return self


def sira(adimlar: list[AkisAdimi]) -> list[AkisAdimi]:
    """Topolojik sira; dongude ValueError."""
    harita = {a.id: a for a in adimlar}
    sonuc: list[AkisAdimi] = []
    durum: dict[str, int] = {}

    def gez(i: str) -> None:
        if durum.get(i) == 2:
            return
        if durum.get(i) == 1:
            raise ValueError("Akista dongu var (bagimliliklar birbirini bekliyor).")
        durum[i] = 1
        a = harita[i]
        for b in [*a.bagimli, *([a.kosul.adim] if a.kosul else [])]:
            gez(b)
        durum[i] = 2
        sonuc.append(a)

    for a in adimlar:
        gez(a.id)
    return sonuc


AjanCalistir = Callable[[str], Awaitable[tuple[str, str, str]]]  # hedef -> (durum, ozet, run_id)
KomutCalistir = Callable[[str], dict]  # komut -> komut_calistir sonucu


class AkisDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.dizin = veri_dizini / "akislar"
        self.dizin.mkdir(parents=True, exist_ok=True)

    def _yol(self, i: str) -> Path:
        if not (len(i) == 12 and i.isalnum()):
            raise Bulunamadi("Akis bulunamadi.")
        return self.dizin / f"{i}.json"

    def kaydet(self, a: Akis) -> Akis:
        json_yaz(self._yol(a.id), a.model_dump())
        return a

    def getir(self, i: str) -> Akis:
        ham = json_oku(self._yol(i), None)
        if ham is None:
            raise Bulunamadi("Akis bulunamadi.")
        return Akis(**ham)

    def liste(self) -> list[dict]:
        out = []
        for p in sorted(self.dizin.glob("*.json"), reverse=True):
            try:
                out.append(Akis(**json_oku(p, {})).model_dump())
            except (ValueError, TypeError):
                continue
        return out[:50]


async def calistir(akis: Akis, depo: AkisDeposu, ajan: AjanCalistir, komut: KomutCalistir) -> Akis:
    akis.durum = "calisiyor"
    depo.kaydet(akis)
    sonuc = {a.id: a for a in akis.adimlar}
    for a in sira(akis.adimlar):
        if a.durum in BITMIS:
            continue  # devamda tamamlananlar tekrar calismaz (yan etki yinelenmez)
        onkosul = [sonuc[b] for b in a.bagimli]
        if any(b.durum in ("basarisiz", "atlandi") for b in onkosul):
            a.durum, a.sonuc = "atlandi", "Bagimli adim basarisiz/atlandi."
            depo.kaydet(akis)
            continue
        if a.kosul and sonuc[a.kosul.adim].durum != a.kosul.durum:
            a.durum, a.sonuc = "atlandi", f"Kosul saglanmadi ({a.kosul.adim} != {a.kosul.durum})."
            depo.kaydet(akis)
            continue
        while True:
            a.deneme += 1
            a.durum = "calisiyor"
            depo.kaydet(akis)
            if a.tur == "ajan":
                durum, ozet, run_id = await ajan(a.hedef)
                a.run_id = run_id
                basarili = durum == "basarili"
                a.sonuc = ozet[:1000]
            else:
                r = await asyncio.to_thread(komut, a.komut)
                if r.get("karar") == "onay_bekliyor":
                    a.durum, a.deneme = "onay_bekliyor", a.deneme - 1
                    a.sonuc = "Komut onay bekliyor; onaylayip akisi devam ettirin."
                    akis.durum = "onay_bekliyor"
                    depo.kaydet(akis)
                    return akis
                basarili = r.get("cikis_kodu") == 0
                a.sonuc = str(r.get("cikti") or r.get("hata") or "")[-1000:]
            if basarili:
                a.durum = "basarili"
                break
            if a.deneme > a.tekrar:
                a.durum = "basarisiz"
                break
        depo.kaydet(akis)
    akis.durum = "basarisiz" if any(x.durum == "basarisiz" for x in akis.adimlar) else "basarili"
    depo.kaydet(akis)
    return akis


def dogrula_veri(veri: dict) -> Akis:
    try:
        return Akis(**veri)
    except ValueError as e:
        raise UygulamaHatasi(f"Akis gecersiz: {str(e)[:400]}") from e


_PARAM_RE = re.compile(r"\{\{([a-zA-Z0-9_-]{1,40})\}\}")


class AkisSablonu(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    ad: str = Field(min_length=1, max_length=120)
    aciklama: str = Field(default="", max_length=400)
    parametreler: list[str] = []
    varsayilanlar: dict[str, str] = {}
    adimlar: list[AkisAdimi] = Field(min_length=1, max_length=MAX_ADIM)
    yerlesik: bool = False

    @model_validator(mode="after")
    def _sablon_graf(self) -> AkisSablonu:
        ids = [a.id for a in self.adimlar]
        if len(set(ids)) != len(ids):
            raise ValueError("Adim kimlikleri benzersiz olmali.")
        for a in self.adimlar:
            for b in [*a.bagimli, *([a.kosul.adim] if a.kosul else [])]:
                if b not in ids:
                    raise ValueError(f"'{a.id}' bilinmeyen adima bagli: {b}")
        sira(self.adimlar)
        return self


YERLESIK_SABLONLAR: list[AkisSablonu] = [
    AkisSablonu(
        id="pr-incele-test",
        ad="PR incele ve test et",
        aciklama="Degisiklikleri inceler, testleri calistirir ve ozet rapor hazirlar.",
        parametreler=["test_komutu"],
        varsayilanlar={"test_komutu": "pytest -q"},
        adimlar=[
            AkisAdimi(
                id="incele",
                tur="ajan",
                hedef=(
                    "Calisma agacindaki git diff degisikliklerini incele, "
                    "olasi hata ve regresyon risklerini listele."
                ),
            ),
            AkisAdimi(id="test", tur="komut", komut="{{test_komutu}}", bagimli=["incele"]),
            AkisAdimi(
                id="ozet",
                tur="ajan",
                hedef="Inceleme bulgularini ve '{{test_komutu}}' sonucunu tek ozette topla.",
                bagimli=["test"],
            ),
        ],
        yerlesik=True,
    ),
    AkisSablonu(
        id="hata-avcisi",
        ad="Hata avcisi ve duzeltme",
        aciklama="Belirtilen hatayi yeniden uretip kok nedenini bulur, duzeltir ve test eder.",
        parametreler=["hata", "test_komutu"],
        varsayilanlar={"test_komutu": "pytest -q"},
        adimlar=[
            AkisAdimi(
                id="duzelt",
                tur="ajan",
                hedef="Su hatayi kok nedeninden duzelt: {{hata}}",
            ),
            AkisAdimi(
                id="dogrula",
                tur="komut",
                komut="{{test_komutu}}",
                bagimli=["duzelt"],
                tekrar=1,
            ),
        ],
        yerlesik=True,
    ),
    AkisSablonu(
        id="surum-hazirla",
        ad="Surum hazirligi",
        aciklama="Testleri kosar, CHANGELOG ve surum notlarini hazirlar.",
        parametreler=["surum", "test_komutu"],
        varsayilanlar={"test_komutu": "pytest -q"},
        adimlar=[
            AkisAdimi(id="test", tur="komut", komut="{{test_komutu}}"),
            AkisAdimi(
                id="notlar",
                tur="ajan",
                hedef=(
                    "Surum {{surum}} icin degisiklikleri ve surum notlarini kontrol edip guncelle."
                ),
                bagimli=["test"],
            ),
        ],
        yerlesik=True,
    ),
]


def sablon_uygula(sablon: AkisSablonu, degerler: dict[str, str] | None = None) -> Akis:
    """Sablon adimlarindaki `{{param}}` yer tutucularini doldurarak taze Akis uretir."""
    girdi = {str(k): str(v) for k, v in (degerler or {}).items() if v is not None}
    harita: dict[str, str] = {k: str(v) for k, v in sablon.varsayilanlar.items() if str(v).strip()}
    for k, v in girdi.items():
        if v.strip():
            harita[k] = v.strip()

    gereken = list(dict.fromkeys(sablon.parametreler))
    for a in sablon.adimlar:
        for alan in (a.hedef, a.komut):
            for p in _PARAM_RE.findall(alan):
                if p not in gereken:
                    gereken.append(p)
    for p in gereken:
        if not harita.get(p, "").strip():
            raise UygulamaHatasi(f"Eksik sablon parametresi: {p}")

    def yerine(m: re.Match[str]) -> str:
        return harita[m.group(1)]

    yeni_adimlar = [
        AkisAdimi(
            id=a.id,
            tur=a.tur,
            hedef=_PARAM_RE.sub(yerine, a.hedef) if a.hedef else "",
            komut=_PARAM_RE.sub(yerine, a.komut) if a.komut else "",
            bagimli=list(a.bagimli),
            kosul=a.kosul,
            tekrar=a.tekrar,
        )
        for a in sablon.adimlar
    ]
    return Akis(ad=sablon.ad, adimlar=yeni_adimlar)


class SablonDeposu:
    """Kullanici tanimli parametreli is akisi sablonlari (`akis-sablonlari.json`) + yerlesikler."""

    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "akis-sablonlari.json"

    def _kullanici(self) -> list[AkisSablonu]:
        ham = json_oku(self.yol, []) or []
        sonuc: list[AkisSablonu] = []
        for h in ham:
            try:
                sonuc.append(AkisSablonu(**{**h, "yerlesik": False}))
            except (ValueError, TypeError):
                continue
        return sonuc

    def _yaz(self, sablonlar: list[AkisSablonu]) -> None:
        json_yaz(self.yol, [s.model_dump() for s in sablonlar])

    def liste(self) -> list[dict]:
        kullanici = self._kullanici()
        kullanici_idler = {s.id for s in kullanici}
        yerlesik = [s for s in YERLESIK_SABLONLAR if s.id not in kullanici_idler]
        return [s.model_dump() for s in [*kullanici, *yerlesik]]

    def getir(self, sid: str) -> AkisSablonu:
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", sid or ""):
            raise Bulunamadi("Sablon bulunamadi.")
        for s in self._kullanici():
            if s.id == sid:
                return s
        for s in YERLESIK_SABLONLAR:
            if s.id == sid:
                return s
        raise Bulunamadi("Sablon bulunamadi.")

    def kaydet(self, veri: dict) -> AkisSablonu:
        try:
            sablon = AkisSablonu(**{**veri, "yerlesik": False})
        except ValueError as e:
            raise UygulamaHatasi(f"Sablon gecersiz: {str(e)[:400]}") from e
        mevcut = [s for s in self._kullanici() if s.id != sablon.id]
        mevcut.insert(0, sablon)
        self._yaz(mevcut[:50])
        return sablon

    def sil(self, sid: str) -> None:
        mevcut = self._kullanici()
        kalan = [s for s in mevcut if s.id != sid]
        if len(kalan) != len(mevcut):
            self._yaz(kalan)
            return
        if any(s.id == sid for s in YERLESIK_SABLONLAR):
            raise UygulamaHatasi("Yerlesik sablon silinemez.")
        raise Bulunamadi("Sablon bulunamadi.")
