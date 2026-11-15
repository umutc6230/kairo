"""Calisma ortami ayarlari (.env / ortam degiskeni, YAS_ oneki). Kullanici ayarlari degil:
onlar services/ayarlar.py'de, veri klasorundeki ayarlar.json'da.

Portable: derlenmis exe her seyi kendi klasorundeki data/ altina yazar (AppData, registry yok)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJE_KOKU = Path(__file__).resolve().parent.parent


class OrtamAyarlari(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YAS_", env_file=".env", extra="ignore")

    veri_dizini: Path | None = None  # bos: <uygulama klasoru>/data
    port: int = 0  # 0: bos port secilir
    gunluk_seviyesi: str = "INFO"


def uygulama_klasoru() -> Path:
    """Derlenmis exe'nin klasoru (portable kok) ya da gelistirmede proje koku."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJE_KOKU


def veri_dizini(ortam: OrtamAyarlari | None = None) -> Path:
    """Sohbetler, ekler ve ayarlarin tutuldugu klasor (yoksa olusturulur)."""
    ortam = ortam or OrtamAyarlari()
    dizin = Path(ortam.veri_dizini) if ortam.veri_dizini else uygulama_klasoru() / "data"
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin


def _motor_var(dizin: Path) -> bool:
    return (dizin / "llama.cpp" / "llama-server.exe").exists()


def varsayilan_llm_dizini() -> Path:
    """Model klasoru icin makineye ozel mutlak yol yazmadan aday sirasi:
    YEREL_LLM_DIZIN ortam degiskeni -> uygulama klasorunun yanindaki/icindeki llm ->
    kullanici klasoru/Projects/llm. Hicbiri yoksa sonuncusu (Ayarlar'dan degistirilir)."""
    if os.environ.get("YEREL_LLM_DIZIN"):
        return Path(os.environ["YEREL_LLM_DIZIN"])
    kok = uygulama_klasoru()
    adaylar = [kok / "llm", kok.parent / "llm", Path.home() / "Projects" / "llm"]
    return next((d for d in adaylar if _motor_var(d)), adaylar[-1])


def yerlesik_skill_dizini() -> Path:
    """Uygulamayla gelen skill'ler (PyInstaller paketinde _MEIPASS altinda; salt okunur)."""
    kok = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return kok / "app" / "skills"


def web_dizini() -> Path:
    """Arayuz dosyalari (PyInstaller paketinde _MEIPASS altinda)."""
    kok = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return kok / "app" / "web"
