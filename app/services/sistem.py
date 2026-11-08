"""Bilgisayar bilgisi: bos RAM, model dosyalari, disaridan acilmis llama-server'i durdurma."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

from app.services.yerel_llm import MODELLER


def bellek() -> dict:
    """Bos ve toplam fiziksel bellek (GB). Windows disinda bilinmez (None)."""
    if sys.platform != "win32":
        return {"bos_gb": None, "toplam_gb": None}

    class _Durum(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    durum = _Durum()
    durum.dwLength = ctypes.sizeof(_Durum)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(durum))
    gb = 1024**3
    return {
        "bos_gb": round(durum.ullAvailPhys / gb, 1),
        "toplam_gb": round(durum.ullTotalPhys / gb, 1),
        "sanal_bos_gb": round(durum.ullAvailPageFile / gb, 1),
    }


def model_dosyalari(dizin: Path) -> dict[str, dict]:
    sonuc = {}
    for anahtar, profil in MODELLER.items():
        sonuc[anahtar] = {
            "dosya_var": (dizin / "models" / profil.dosya).exists(),
            "mmproj_var": (dizin / "models" / profil.mmproj).exists(),
        }
    return sonuc


def motor_var(dizin: Path) -> bool:
    return (dizin / "llama.cpp" / "llama-server.exe").exists()


def llama_server_durdur() -> bool:
    """Kullanicinin acikca istegiyle, disaridan (bat ile) acilmis llama-server'i kapatir."""
    if sys.platform != "win32":
        return False
    sonuc = subprocess.run(
        ["taskkill", "/IM", "llama-server.exe", "/F"],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return sonuc.returncode == 0
