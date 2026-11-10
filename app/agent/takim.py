"""Takim panosu (A8.2): lider (ust gorev) + alt ajanlar icin ortak gorev listesi ve mesaj kutusu.

- Gorevlerin bagimliligi var; bagimliligi bitmemis gorev alinamaz.
- Alma (claim) sureli kiralamadir (lease). Sahibi panoyu her kullandiginda kiralama yenilenir
  (heartbeat). Suresi dolan (coken/yetim ajan) gorev yeniden "acik" olur.
- Bir gorevi yalniz sahibi tamamlayabilir.
- Mesajlar kimlikli; ayni mesaj_id ikinci kez gelirse yok sayilir (tekrar teslim).
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.services.depo import json_oku, json_yaz

KIRA_SN = 600


class TakimGorevi(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    baslik: str
    bagimli: list[str] = []
    durum: str = "acik"  # acik | alindi | tamam
    sahip: str = ""
    kira_bitis: float = 0
    sonuc: str = ""


class Pano(BaseModel):
    gorevler: list[TakimGorevi] = []
    mesajlar: list[dict] = []


class TakimPanosu:
    def __init__(self, veri_dizini: Path, saat=time.time) -> None:
        self.dizin = veri_dizini / "takim"
        self.dizin.mkdir(parents=True, exist_ok=True)
        self.saat = saat

    def _yol(self, kok: str) -> Path:
        return self.dizin / f"{kok}.json"

    def _oku(self, kok: str) -> Pano:
        return Pano(**(json_oku(self._yol(kok), {}) or {}))

    def _yaz(self, kok: str, p: Pano) -> None:
        json_yaz(self._yol(kok), p.model_dump())

    def _bakim(self, p: Pano, ajan: str) -> None:
        simdi = self.saat()
        for g in p.gorevler:
            if g.durum == "alindi" and g.sahip == ajan:
                g.kira_bitis = simdi + KIRA_SN  # heartbeat
            elif g.durum == "alindi" and g.kira_bitis < simdi:
                g.durum, g.sahip = "acik", ""  # yetim: geri acilir

    def isleyiciler(self, kok: str, ajan: str) -> dict[str, Any]:
        def gorev_ekle(baslik: str, bagimli: list[str] | None = None) -> dict:
            p = self._oku(kok)
            ids = {g.id for g in p.gorevler}
            eksik = [b for b in bagimli or [] if b not in ids]
            if eksik:
                return {"hata": f"Bilinmeyen bagimlilik: {', '.join(eksik)}"}
            g = TakimGorevi(baslik=str(baslik)[:300], bagimli=list(bagimli or []))
            p.gorevler.append(g)
            self._yaz(kok, p)
            return {"id": g.id}

        def gorev_listesi() -> dict:
            p = self._oku(kok)
            self._bakim(p, ajan)
            self._yaz(kok, p)
            return {"gorevler": [g.model_dump(exclude={"kira_bitis"}) for g in p.gorevler]}

        def gorev_al(id: str) -> dict:  # noqa: A002 - arac argumani
            p = self._oku(kok)
            self._bakim(p, ajan)
            g = next((x for x in p.gorevler if x.id == id), None)
            if g is None:
                return {"hata": "Gorev yok."}
            if g.durum != "acik":
                return {"hata": f"Gorev {g.durum} (sahip: {g.sahip or '-'})."}
            bitmemis = [
                b for b in g.bagimli if next(x for x in p.gorevler if x.id == b).durum != "tamam"
            ]
            if bitmemis:
                return {"hata": f"Once bagimliliklar bitmeli: {', '.join(bitmemis)}"}
            g.durum, g.sahip, g.kira_bitis = "alindi", ajan, self.saat() + KIRA_SN
            self._yaz(kok, p)
            return {"alindi": g.id}

        def gorev_tamamla(id: str, sonuc: str = "") -> dict:  # noqa: A002
            p = self._oku(kok)
            self._bakim(p, ajan)
            g = next((x for x in p.gorevler if x.id == id), None)
            if g is None or g.sahip != ajan or g.durum != "alindi":
                return {"hata": "Yalniz kendi aldigin gorevi tamamlayabilirsin."}
            g.durum, g.sonuc = "tamam", str(sonuc)[:1000]
            self._yaz(kok, p)
            return {"tamam": g.id}

        def mesaj_gonder(alici: str, metin: str, mesaj_id: str = "") -> dict:
            p = self._oku(kok)
            mid = mesaj_id or uuid.uuid4().hex[:10]
            if any(m["id"] == mid for m in p.mesajlar):
                return {"tekrar": mid}  # ayni mesaj ikinci kez teslim edilmez
            p.mesajlar.append({"id": mid, "kimden": ajan, "kime": alici, "metin": str(metin)[:2000],
                               "okundu": False})  # fmt: skip
            self._yaz(kok, p)
            return {"gonderildi": mid}

        def mesajlari_oku() -> dict:
            p = self._oku(kok)
            self._bakim(p, ajan)
            gelen = [m for m in p.mesajlar if m["kime"] in (ajan, "hepsi") and not m["okundu"]]
            for m in gelen:
                m["okundu"] = True
            self._yaz(kok, p)
            return {"mesajlar": [{k: m[k] for k in ("id", "kimden", "metin")} for m in gelen]}

        return {
            "takim_gorev_ekle": gorev_ekle,
            "takim_gorev_listesi": gorev_listesi,
            "takim_gorev_al": gorev_al,
            "takim_gorev_tamamla": gorev_tamamla,
            "takim_mesaj_gonder": mesaj_gonder,
            "takim_mesajlari_oku": mesajlari_oku,
        }

    def pano(self, kok: str) -> dict:
        return self._oku(kok).model_dump()


def _f(ad: str, aciklama: str, ozellikler: dict, zorunlu: list[str]) -> dict:
    parametreler = {"type": "object", "properties": ozellikler, "required": zorunlu}
    fonk = {"name": ad, "description": aciklama, "parameters": parametreler}
    return {"type": "function", "function": fonk}


S, LS = {"type": "string"}, {"type": "array", "items": {"type": "string"}}
SEMALAR = [
    _f("takim_gorev_ekle", "Takim gorev listesine is ekler (bagimli: once bitmesi gerekenler).",
       {"baslik": S, "bagimli": LS}, ["baslik"]),
    _f("takim_gorev_listesi", "Takimin gorevlerini ve durumlarini listeler.", {}, []),
    _f("takim_gorev_al", "Acik bir gorevi uzerine alir (sureli; panoyu kullandikca yenilenir).",
       {"id": S}, ["id"]),
    _f("takim_gorev_tamamla", "Aldigin gorevi sonucuyla tamamlar.", {"id": S, "sonuc": S}, ["id"]),
    _f("takim_mesaj_gonder", "Takimdan birine (ajan kimligi ya da 'hepsi') mesaj gonderir.",
       {"alici": S, "metin": S, "mesaj_id": S}, ["alici", "metin"]),
    _f("takim_mesajlari_oku", "Sana gelen okunmamis mesajlari doner.", {}, []),
]  # fmt: skip
