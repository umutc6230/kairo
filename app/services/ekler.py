"""Sohbete/OCR testine eklenen dosyalar: data/ekler/<id>.<uzanti> + <id>.json (bilgi)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from pydantic import BaseModel

from app.exceptions import Bulunamadi, GecersizEk
from app.services.depo import json_oku, json_yaz

MAX_BOYUT = 50 * 1024 * 1024
TURLER = {
    "resim": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"},
    "pdf": {".pdf"},
    "ses": {".wav", ".mp3"},
    "metin": {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".xml", ".log", ".ini"},
}
MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
}


class Ek(BaseModel):
    id: str
    ad: str
    tur: str
    uzanti: str
    boyut: int
    mime: str
    metin: str = ""  # PDF/metin ekinden cikarilan yazi (bir kez hesaplanir, saklanir)


def tur_bul(ad: str) -> tuple[str, str]:
    uzanti = Path(ad).suffix.lower()
    for tur, uzantilar in TURLER.items():
        if uzanti in uzantilar:
            return tur, uzanti
    raise GecersizEk(
        f"Desteklenmeyen dosya: {Path(ad).name}. Resim (png, jpg, webp), PDF, ses (wav, mp3) "
        "ya da metin dosyasi ekleyin."
    )


class EkDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.dizin = veri_dizini / "ekler"
        self.dizin.mkdir(parents=True, exist_ok=True)

    def _kontrol(self, ek_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{12}", ek_id):
            raise Bulunamadi("Ek bulunamadi.")

    def kaydet(self, ad: str, veri: bytes) -> Ek:
        tur, uzanti = tur_bul(ad)
        if not veri:
            raise GecersizEk("Dosya bos.")
        if len(veri) > MAX_BOYUT:
            raise GecersizEk("Dosya 50 MB'dan buyuk.")
        ek = Ek(
            id=uuid.uuid4().hex[:12],
            ad=Path(ad).name[:120],
            tur=tur,
            uzanti=uzanti,
            boyut=len(veri),
            mime=MIME.get(uzanti, "text/plain"),
        )
        if tur == "metin":
            ek.metin = veri.decode("utf-8", errors="replace")
        (self.dizin / f"{ek.id}{uzanti}").write_bytes(veri)
        json_yaz(self.dizin / f"{ek.id}.json", ek.model_dump())
        return ek

    def getir(self, ek_id: str) -> Ek:
        self._kontrol(ek_id)
        ham = json_oku(self.dizin / f"{ek_id}.json")
        if ham is None:
            raise Bulunamadi("Ek bulunamadi.")
        return Ek(**ham)

    def yol(self, ek: Ek) -> Path:
        return self.dizin / f"{ek.id}{ek.uzanti}"

    def veri(self, ek: Ek) -> bytes:
        return self.yol(ek).read_bytes()

    def metin_kaydet(self, ek: Ek, metin: str) -> Ek:
        ek.metin = metin
        json_yaz(self.dizin / f"{ek.id}.json", ek.model_dump())
        return ek
