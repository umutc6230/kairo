"""Windows DPAPI (CurrentUser) ile sir sifreleme. Windows disinda dogrudan base64 (shortcut:
koruma yok, Linux/mac destegi gerekirse keyring'e gec)."""

from __future__ import annotations

import base64
import sys


def _blob(veri: bytes):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    tampon = ctypes.create_string_buffer(veri, len(veri))
    return BLOB(len(veri), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char))), BLOB, tampon


def _cagir(fonk_adi: str, veri: bytes) -> bytes:
    import ctypes

    giris, BLOB, _tampon = _blob(veri)
    cikis = BLOB()
    fonk = getattr(ctypes.windll.crypt32, fonk_adi)
    if not fonk(ctypes.byref(giris), None, None, None, None, 0, ctypes.byref(cikis)):
        raise OSError(f"{fonk_adi} basarisiz")
    try:
        return ctypes.string_at(cikis.pbData, cikis.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(cikis.pbData)


def sifrele(metin: str) -> str:
    veri = metin.encode()
    if sys.platform == "win32":
        veri = _cagir("CryptProtectData", veri)
    return base64.b64encode(veri).decode()


def coz(kodlu: str) -> str:
    veri = base64.b64decode(kodlu)
    if sys.platform == "win32":
        veri = _cagir("CryptUnprotectData", veri)
    return veri.decode()
