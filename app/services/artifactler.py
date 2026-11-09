"""Artifact'ler (A5.5): ajanin/sohbetin urettigi rapor, HTML, SVG, tablo gibi ciktilar.

Guvenlik:
- Yalniz beyaz listedeki turler; boyut siniri; kimlik siki bicim (yol kacisi yok).
- HTML/SVG onizlemesi arayuzde `<iframe sandbox="allow-scripts" srcdoc>` + kisitli CSP ile
  yapilir: opak origin, ust pencereye/uygulama API'sine/oturum anahtarina erisim yok, ag yok.
  Bu modul icerigi SUNMAZ (acik/oturumsuz uc yok); icerik oturumlu API ile alinir.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

TURLER = ("html", "md", "txt", "svg", "json", "csv")
MAX_BAYT = 2 * 1024 * 1024
MAX_ADET = 200
KIMLIK = re.compile(r"[0-9a-f]{12}")

# Onizleme CSP'si (arayuz srcdoc'un EN BASINA koyar). connect-src 'none': fetch/XHR/WebSocket yok.
ONIZLEME_CSP = (
    "default-src 'none'; img-src data: blob:; media-src data: blob:; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; font-src data:; connect-src 'none'; form-action 'none'; "
    "base-uri 'none'"
)


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ad: str = Field(min_length=1, max_length=120)
    tur: Literal["html", "md", "txt", "svg", "json", "csv"]
    boyut: int = 0
    kaynak: str = "ajan"  # ajan | sohbet | kullanici
    gorev_id: str = ""
    tarih: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ArtifactDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.dizin = veri_dizini / "artifacts"
        self.dizin.mkdir(parents=True, exist_ok=True)
        self.kayit = self.dizin / "kayit.json"

    def _liste(self) -> list[Artifact]:
        sonuc = []
        for h in json_oku(self.kayit, []) or []:
            try:
                sonuc.append(Artifact(**h))
            except ValueError:
                continue
        return sonuc

    def _yol(self, a: Artifact) -> Path:
        return self.dizin / f"{a.id}.{a.tur}"

    def liste(self) -> list[dict]:
        return [a.model_dump() for a in self._liste()]

    def olustur(
        self, ad: str, tur: str, icerik: str, kaynak: str = "ajan", gorev_id: str = ""
    ) -> dict:
        if tur not in TURLER:
            raise UygulamaHatasi(
                f"Desteklenmeyen artifact turu: {tur}. Turler: {', '.join(TURLER)}"
            )
        veri = icerik.encode("utf-8")
        if len(veri) > MAX_BAYT:
            raise UygulamaHatasi(f"Artifact {MAX_BAYT // (1024 * 1024)} MB'dan buyuk olamaz.")
        temiz_ad = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", ad).strip() or "artifact"
        a = Artifact(ad=temiz_ad[:120], tur=tur, boyut=len(veri), kaynak=kaynak, gorev_id=gorev_id)
        kayitlar = self._liste()
        if len(kayitlar) >= MAX_ADET:  # en eskiyi dusur
            eski = kayitlar.pop(0)
            self._yol(eski).unlink(missing_ok=True)
        tmp = self._yol(a).with_suffix(".tmp")
        tmp.write_bytes(veri)
        tmp.replace(self._yol(a))
        json_yaz(self.kayit, [x.model_dump() for x in [*kayitlar, a]])
        return a.model_dump()

    def getir(self, artifact_id: str) -> tuple[dict, str]:
        if not KIMLIK.fullmatch(artifact_id or ""):
            raise Bulunamadi("Artifact bulunamadi.")
        a = next((x for x in self._liste() if x.id == artifact_id), None)
        if a is None or not self._yol(a).is_file():
            raise Bulunamadi("Artifact bulunamadi.")
        return a.model_dump(), self._yol(a).read_text(encoding="utf-8", errors="replace")

    def sil(self, artifact_id: str) -> dict:
        meta, _ = self.getir(artifact_id)
        kalan = [x for x in self._liste() if x.id != artifact_id]
        self._yol(Artifact(**meta)).unlink(missing_ok=True)
        json_yaz(self.kayit, [x.model_dump() for x in kalan])
        return {"silindi": artifact_id}


ARTIFACT_ARACI = {
    "type": "function",
    "function": {
        "name": "artifact_olustur",
        "description": "Kullaniciya gosterilecek bir CIKTI uretir (rapor, HTML sayfa, SVG cizim, "
        "tablo). Proje dosyalarina yazmaz. tur: html | md | txt | svg | json | csv.",
        "parameters": {
            "type": "object",
            "properties": {
                "ad": {"type": "string"},
                "tur": {"type": "string", "enum": list(TURLER)},
                "icerik": {"type": "string"},
            },
            "required": ["ad", "tur", "icerik"],
        },
    },
}
