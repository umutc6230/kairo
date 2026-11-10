"""/doctor (A10.7): kurulum tanisi. Sir DEGERLERI gosterilmez; yalniz var/yok ve surum."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _surum(komut: list[str]) -> str:
    yol = shutil.which(komut[0])
    if not yol:
        return ""
    try:
        r = subprocess.run([yol, *komut[1:]], capture_output=True, text=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return "calismiyor"
    return (r.stdout or r.stderr).strip().splitlines()[0][:80] if (r.stdout or r.stderr) else "var"


def tani(veri_dizini: Path, llm_dizin: Path, openrouter_anahtar_var: bool) -> list[dict]:
    def k(ad: str, durum: str, ayrinti: str = "", oneri: str = "") -> dict:
        return {"ad": ad, "durum": durum, "ayrinti": ayrinti, "oneri": oneri}

    sonuc = [k("Python", "tamam", sys.version.split()[0])]
    yazilabilir = os.access(veri_dizini, os.W_OK)
    sonuc.append(k("Veri klasoru", "tamam" if yazilabilir else "hata", str(veri_dizini),
                   "" if yazilabilir else "Klasore yazma izni verin."))  # fmt: skip
    bos = shutil.disk_usage(veri_dizini).free / 1024**3
    sonuc.append(k("Bos disk", "tamam" if bos > 5 else "uyari", f"{bos:.1f} GB",
                   "" if bos > 5 else "Model ve checkpoint icin en az 5 GB onerilir."))  # fmt: skip
    motor = (llm_dizin / "llama.cpp" / "llama-server.exe").exists()
    sonuc.append(k("llama.cpp", "tamam" if motor else "hata", str(llm_dizin),
                   "" if motor else "Ayarlar > Model klasoru'nu duzeltin."))  # fmt: skip
    modeller = sorted(p.name for p in (llm_dizin / "models").glob("*.gguf")) if motor else []
    sonuc.append(k("Yerel modeller", "tamam" if modeller else "uyari", f"{len(modeller)} dosya",
                   "" if modeller else "Model magazasindan bir model indirin."))  # fmt: skip
    for ad, komut, oneri in [
        ("git", ["git", "--version"], "Diff/review/ayri dal icin git kurun."),
        ("ripgrep (rg)", ["rg", "--version"], "Hizli arama icin rg kurun (yoksa yavas yedek)."),
        ("Node.js", ["node", "--version"], "Yalniz bazi MCP sunuculari icin gerekir."),
    ]:
        s = _surum(komut)
        sonuc.append(k(ad, "tamam" if s and s != "calismiyor" else "uyari", s or "yok",
                       "" if s else oneri))  # fmt: skip
    try:
        import playwright  # noqa: F401

        pw = True
    except ImportError:
        pw = False
    sonuc.append(k("Playwright", "tamam" if pw else "uyari", "var" if pw else "yok",
                   "" if pw else "Tarayici kontrolu icin: pip install playwright"))  # fmt: skip
    sonuc.append(k("OpenRouter anahtari", "tamam" if openrouter_anahtar_var else "bilgi",
                   "kayitli" if openrouter_anahtar_var else "yok (istege bagli)"))  # fmt: skip
    return sonuc
