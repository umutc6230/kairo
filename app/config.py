"""Calisma ortami ayarlari (.env / ortam degiskeni, YAS_ oneki). Kullanici ayarlari degil:
onlar services/ayarlar.py'de, veri klasorundeki ayarlar.json'da."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJE_KOKU = Path(__file__).resolve().parent.parent


class OrtamAyarlari(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YAS_", env_file=".env", extra="ignore")

    veri_dizini: Path | None = None  # bos: kurulu exe -> %LOCALAPPDATA%, gelistirme -> ./data
    port: int = 0  # 0: bos port secilir
    gunluk_seviyesi: str = "INFO"


def veri_dizini(ortam: OrtamAyarlari | None = None) -> Path:
    """Sohbetler, ekler ve ayarlarin tutuldugu klasor (yoksa olusturulur)."""
    ortam = ortam or OrtamAyarlari()
    if ortam.veri_dizini:
        dizin = Path(ortam.veri_dizini)
    elif getattr(sys, "frozen", False):  # kurulu exe: Program Files'a yazilamaz
        dizin = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "YerelAIStudio"
    else:
        dizin = PROJE_KOKU / "data"
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin


def web_dizini() -> Path:
    """Arayuz dosyalari (PyInstaller paketinde _MEIPASS altinda)."""
    kok = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return kok / "app" / "web"
