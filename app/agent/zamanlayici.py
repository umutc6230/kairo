"""Kalici zamanlayici (A11.1-2, A11.5). YALNIZ UYGULAMA ACIKKEN calisir; kapaliyken calistigi
iddia edilmez. Acilista kacirilan tetikleme kurala gore atlanir ya da BIR KEZ calisir.

- Saat dilimi zamanlamada saklanir (varsayilan kullanici ayari). Gunluk saat DST'de: yok olan saat
  (ileri alma) gecis sonrasi ilk ana kayar; iki kez yasanan saat (geri alma) BIR KEZ calisir.
- Idempotency: her tetiklemenin anahtari <zamanlama>@<planlanan UTC>; ayni anahtar iki kez
  calismaz (restart dahil).
- Overlap: onceki calisma surerken yeni tetikleme ATLANIR ve kaydedilir.
- Retry: basarisiz calisma en fazla `tekrar` kez yeniden baslatilir.
- Gozetimsiz onay YOK: onay isteyen adim 'onay_bekliyor'da kalir (runner davranisi).
Mantik saatten bagimsizdir: tick(simdi) sahte saatle test edilir.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from app.exceptions import Bulunamadi
from app.services.depo import json_oku, json_yaz

KACIRMA_TOLERANS = timedelta(minutes=2)  # bu kadar gec kalan tetikleme "zamaninda" sayilir
MAX_GECMIS = 500
BITMIS = {"basarili", "dogrulanmadi", "basarisiz", "iptal"}


class Zamanlama(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ad: str = Field(min_length=1, max_length=80)
    hedef: str = Field(min_length=1, max_length=4000)
    proje_kok: str = Field(min_length=1)
    tur: Literal["aralik", "gunluk", "bir_kez"]  # bir_kez: OpenBot "Now, once"
    aralik_dk: int = Field(default=60, ge=5, le=7 * 24 * 60)
    saat: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    gunler: list[int] = Field(default=[0, 1, 2, 3, 4, 5, 6])  # 0 = Pazartesi
    saat_dilimi: str = "Europe/Istanbul"
    kacirilan: Literal["atla", "bir_kez"] = "atla"
    tekrar: int = Field(default=0, ge=0, le=2)
    max_adim: int = Field(default=30, ge=1, le=200)
    aktif: bool = True
    baslangic: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    son_plan: str = ""  # islenmis son planlanan tetikleme (UTC ISO)
    # OpenBot rutin cumlesi: Ne / Ne zaman / Ne yapar (yap | bildir) / Ne zamana kadar
    davranis: Literal["yap", "bildir"] = "yap"  # bildir: degisiklik yapmaz, yalniz raporlar
    bitis_kosulu: str = Field(default="", max_length=500)  # dolu: hedef; saglaninca durur
    tamamlandi: str = ""  # hedefe ulasildigi an (UTC ISO)

    @field_validator("saat_dilimi")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"Bilinmeyen saat dilimi: {v}") from e
        return v

    @model_validator(mode="after")
    def _gunler(self) -> Zamanlama:
        if not self.gunler or any(g not in range(7) for g in self.gunler):
            raise ValueError("gunler 0 (Pazartesi) - 6 (Pazar) arasinda olmali.")
        return self


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(UTC)


def sonraki(z: Zamanlama, sonra: datetime) -> datetime:
    """`sonra`dan (UTC) kesin sonraki planlanan tetikleme (UTC)."""
    if z.tur == "bir_kez":  # yalniz baslangic aninda; sonrasi yok
        bas = _utc(z.baslangic)
        return bas if sonra < bas else bas + timedelta(days=365 * 100)
    if z.tur == "aralik":
        bas = _utc(z.baslangic)
        adim = timedelta(minutes=z.aralik_dk)
        if sonra < bas:
            return bas
        return bas + adim * ((sonra - bas) // adim + 1)
    tz = ZoneInfo(z.saat_dilimi)
    s, d = (int(x) for x in z.saat.split(":"))
    gun = sonra.astimezone(tz).date()
    for i in range(8):
        g = gun + timedelta(days=i)
        if g.weekday() not in z.gunler:
            continue
        # fold=0: iki kez yasanan saatte ilki; yok olan saat UTC'ye cevrilince ileri kayar
        aday = datetime(g.year, g.month, g.day, s, d, tzinfo=tz).astimezone(UTC)
        if aday > sonra:
            return aday
    raise ValueError("Sonraki tetikleme bulunamadi.")


class Tetik(BaseModel):
    anahtar: str
    zamanlama: str
    plan: str
    deneme: int = 1
    run_id: str = ""
    durum: str = (
        "bekliyor"  # bekliyor | calisiyor | atlandi_overlap | atlandi_kacirildi | <run durumu>
    )
    zaman: str = ""


class Zamanlayici:
    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "zamanlamalar.json"

    def _oku(self) -> dict:
        ham = json_oku(self.yol, {}) or {}
        return {"zamanlamalar": ham.get("zamanlamalar", []), "gecmis": ham.get("gecmis", [])}

    def _yaz(self, v: dict) -> None:
        v["gecmis"] = v["gecmis"][-MAX_GECMIS:]
        json_yaz(self.yol, v)

    def liste(self) -> list[Zamanlama]:
        return [Zamanlama(**z) for z in self._oku()["zamanlamalar"]]

    def gecmis(self, zamanlama_id: str | None = None) -> list[dict]:
        g = self._oku()["gecmis"]
        return [t for t in g if zamanlama_id is None or t["zamanlama"] == zamanlama_id]

    def ekle(self, veri: dict, simdi: datetime | None = None) -> Zamanlama:
        z = Zamanlama(**veri)
        z.baslangic = (simdi or datetime.now(UTC)).isoformat()
        z.son_plan = z.baslangic  # olusturma oncesi tetiklemeler "kacirilmis" sayilmaz
        if z.tur == "bir_kez":  # "simdi, bir kez": ilk tick'te calisir
            z.son_plan = (_utc(z.baslangic) - timedelta(seconds=1)).isoformat()
        v = self._oku()
        v["zamanlamalar"].append(z.model_dump())
        self._yaz(v)
        return z

    def guncelle(self, zid: str, degisiklik: dict) -> Zamanlama:
        v = self._oku()
        for i, z in enumerate(v["zamanlamalar"]):
            if z["id"] == zid:
                yeni = Zamanlama(**(z | {k: x for k, x in degisiklik.items() if k not in ("id",)}))
                v["zamanlamalar"][i] = yeni.model_dump()
                self._yaz(v)
                return yeni
        raise Bulunamadi("Zamanlama bulunamadi.")

    def sil(self, zid: str) -> None:
        v = self._oku()
        kalan = [z for z in v["zamanlamalar"] if z["id"] != zid]
        if len(kalan) == len(v["zamanlamalar"]):
            raise Bulunamadi("Zamanlama bulunamadi.")
        v["zamanlamalar"] = kalan
        self._yaz(v)

    def tick(self, simdi: datetime, run_durumu: Callable[[str], str]) -> list[Tetik]:
        """Calistirilacak tetiklemeleri doner (cagiran run baslatip `baslatildi` ile yazar)."""
        v = self._oku()
        gecmis = [Tetik(**t) for t in v["gecmis"]]
        anahtarlar = {t.anahtar for t in gecmis}
        for t in gecmis:  # durumlari tazele
            if t.run_id and t.durum not in BITMIS:
                t.durum = run_durumu(t.run_id)
        baslat: list[Tetik] = []
        for zi, ham in enumerate(v["zamanlamalar"]):
            z = Zamanlama(**ham)
            if not z.aktif:
                continue
            kendi = [t for t in gecmis if t.zamanlama == z.id]
            suren = any(t.run_id and t.durum not in BITMIS for t in kendi)
            # retry: son calisma basarisizsa ve hak varsa ayni anahtarla yeniden
            son = kendi[-1] if kendi else None
            if son and son.durum == "basarisiz" and son.deneme <= z.tekrar and not suren:
                yeniden = Tetik(**{**son.model_dump(), "deneme": son.deneme + 1, "run_id": "",
                                   "durum": "bekliyor", "zaman": simdi.isoformat()})  # fmt: skip
                gecmis.append(yeniden)
                baslat.append(yeniden)
                continue
            vadesi: list[datetime] = []
            p = sonraki(z, _utc(z.son_plan or z.baslangic))
            while p <= simdi and len(vadesi) < 1000:
                vadesi.append(p)
                p = sonraki(z, p)
            if not vadesi:
                continue
            z.son_plan = vadesi[-1].isoformat()
            v["zamanlamalar"][zi] = z.model_dump()
            for kacan in vadesi[:-1]:  # birden fazla kacirildi: yalniz sonuncusu aday
                k = f"{z.id}@{kacan.isoformat()}"
                if k not in anahtarlar:
                    gecmis.append(Tetik(anahtar=k, zamanlama=z.id, plan=kacan.isoformat(),
                                        durum="atlandi_kacirildi",
                                        zaman=simdi.isoformat()))  # fmt: skip
            plan = vadesi[-1]
            anahtar = f"{z.id}@{plan.isoformat()}"
            if anahtar in anahtarlar:
                continue  # idempotent: ayni tetikleme iki kez calismaz
            t = Tetik(
                anahtar=anahtar, zamanlama=z.id, plan=plan.isoformat(), zaman=simdi.isoformat()
            )
            if simdi - plan > KACIRMA_TOLERANS and z.kacirilan == "atla":
                t.durum = "atlandi_kacirildi"
            elif suren:
                t.durum = "atlandi_overlap"
            else:
                baslat.append(t)
            if z.tur == "bir_kez":  # tek seferlik rutin calistiktan sonra kapanir
                z.aktif = False
                v["zamanlamalar"][zi] = z.model_dump()
            gecmis.append(t)
        v["gecmis"] = [t.model_dump() for t in gecmis]
        self._yaz(v)
        return baslat

    def hedefe_ulasti(self, zid: str, simdi: datetime) -> None:
        """Bitis kosulu saglandi: rutin durur (OpenBot goal 'until')."""
        v = self._oku()
        for z in v["zamanlamalar"]:
            if z["id"] == zid:
                z["aktif"], z["tamamlandi"] = False, simdi.isoformat()
        self._yaz(v)

    def baslatildi(self, t: Tetik, run_id: str, hata: str = "") -> None:
        v = self._oku()
        for x in reversed(v["gecmis"]):
            if x["anahtar"] == t.anahtar and x["deneme"] == t.deneme:
                x["run_id"], x["durum"] = run_id, ("calisiyor" if run_id else f"hata: {hata[:200]}")
                break
        self._yaz(v)
