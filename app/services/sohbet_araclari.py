"""Sohbette modelin kullanabildigi araclar. HEPSI SALT OKUNUR: dosya yazma, silme, tasima yok.
Gizli bilgi icerebilecek yerler (ssh/bulut anahtarlari, .env, tarayici profilleri) okunmaz."""

from __future__ import annotations

import ctypes
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services import araclar as demo

MAX_OGE = 150
MAX_OKUMA_KARAKTER = 6000
MAX_DOSYA_BAYT = 5 * 1024 * 1024
ATLANAN_KLASORLER = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "AppData",
    "$Recycle.Bin",
}
GIZLI_KLASORLER = {".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store"}
GIZLI_AD = re.compile(
    r"^\.env|\.pem$|\.key$|\.pfx$|\.p12$|^id_(rsa|ed25519|ecdsa|dsa)|credential|password|parola|"
    r"^login data$|^cookies$|^web data$|\.kdbx$",
    re.I,
)
TARAYICI_PROFILI = re.compile(r"(Chrome|Edge|Firefox|Opera|Brave)[\\/].*(User Data|Profiles)", re.I)

_BILINEN = {  # Windows Known Folder GUID'leri (OneDrive'a tasinmis masaustu dahil dogru yol)
    "masaustu": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "belgeler": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "indirilenler": "374DE290-123F-4565-9164-39C4925E467B",
    "resimler": "33E28130-4E1E-4676-835A-98395C3BC3BB",
}
_TAKMA_AD = {
    "masaustu": "masaustu", "masaüstü": "masaustu", "desktop": "masaustu",
    "belgeler": "belgeler", "documents": "belgeler", "belgelerim": "belgeler",
    "indirilenler": "indirilenler", "downloads": "indirilenler", "indirmeler": "indirilenler",
    "resimler": "resimler", "pictures": "resimler",
}  # fmt: skip


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def bilinen_klasor(ad: str) -> Path:
    """masaustu/belgeler/indirilenler/resimler'in gercek yolu (Windows API; yoksa ev/Ad)."""
    yedek = {
        "masaustu": "Desktop",
        "belgeler": "Documents",
        "indirilenler": "Downloads",
        "resimler": "Pictures",
    }
    if sys.platform == "win32":
        try:
            u = uuid.UUID(_BILINEN[ad])
            g = _GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
            yol = ctypes.c_wchar_p()
            if (
                ctypes.windll.shell32.SHGetKnownFolderPath(
                    ctypes.byref(g), 0, None, ctypes.byref(yol)
                )
                == 0
            ):
                sonuc = Path(yol.value)
                ctypes.windll.ole32.CoTaskMemFree(yol)
                return sonuc
        except (OSError, AttributeError, ValueError):
            pass
    return Path.home() / yedek[ad]


def yol_coz(yol: str | None) -> Path:
    temiz = (yol or "masaustu").strip().strip("\"'")
    anahtar = _TAKMA_AD.get(temiz.lower().rstrip("/\\"))
    if anahtar:
        return bilinen_klasor(anahtar)
    for takma, gercek in _TAKMA_AD.items():  # "masaustu/Projeler" gibi
        on_ek = takma + "/"
        if temiz.lower().replace("\\", "/").startswith(on_ek):
            return bilinen_klasor(gercek) / temiz[len(on_ek) :]
    p = Path(temiz).expanduser()
    return p if p.is_absolute() else Path.home() / p


def gizli_mi(p: Path) -> bool:
    parcalar = {x.lower() for x in p.parts}
    if parcalar & {k.lower() for k in GIZLI_KLASORLER}:
        return True
    return bool(GIZLI_AD.search(p.name) or TARAYICI_PROFILI.search(str(p)))


def _boyut(n: int) -> str:
    for birim in ("B", "KB", "MB", "GB"):
        if n < 1024 or birim == "GB":
            return f"{n:.0f} {birim}" if birim == "B" else f"{n:.1f} {birim}"
        n /= 1024
    return ""


def klasor_listele(yol: str = "masaustu", gizlileri_goster: bool = False) -> dict:
    k = yol_coz(yol)
    if gizli_mi(k):
        return {"hata": "Bu klasor gizli bilgi icerebilecegi icin listelenmez."}
    if not k.is_dir():
        return {"hata": f"Klasor bulunamadi: {k}"}
    klasorler, dosyalar = [], []
    try:
        ogeler = sorted(k.iterdir(), key=lambda x: x.name.lower())
    except PermissionError:
        return {"hata": f"Bu klasore erisim izni yok: {k}"}
    for o in ogeler:
        if not gizlileri_goster and (o.name.startswith(".") or o.name.lower() == "desktop.ini"):
            continue
        try:
            if o.is_dir():
                klasorler.append(f"[klasor] {o.name}")
            else:
                st = o.stat()
                tarih = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
                dosyalar.append(f"{o.name} ({_boyut(st.st_size)}, {tarih})")
        except OSError:
            continue
    hepsi = klasorler + dosyalar
    return {
        "klasor": str(k),
        "klasor_sayisi": len(klasorler),
        "dosya_sayisi": len(dosyalar),
        "ogeler": hepsi[:MAX_OGE],
        **({"not": f"Ilk {MAX_OGE} oge gosterildi."} if len(hepsi) > MAX_OGE else {}),
    }


def dosya_oku(yol: str, baslangic: int = 0) -> dict:
    p = yol_coz(yol)
    if gizli_mi(p):
        return {
            "hata": "Bu dosya gizli bilgi (anahtar, parola, oturum) icerebilecegi icin okunmaz."
        }
    if not p.is_file():
        return {"hata": f"Dosya bulunamadi: {p}"}
    if p.stat().st_size > MAX_DOSYA_BAYT:
        return {"hata": "Dosya 5 MB'dan buyuk; okunmadi."}
    veri = p.read_bytes()
    if b"\x00" in veri[:4096]:
        return {"hata": "Bu bir metin dosyasi degil (ikili dosya); icerigi okunamaz."}
    metin = veri.decode("utf-8", errors="replace")
    baslangic = max(0, int(baslangic))
    parca = metin[baslangic : baslangic + MAX_OKUMA_KARAKTER]
    sonuc: dict[str, Any] = {"dosya": str(p), "karakter": len(metin), "icerik": parca}
    if baslangic + MAX_OKUMA_KARAKTER < len(metin):
        sonuc["devam"] = f"Devami icin baslangic={baslangic + MAX_OKUMA_KARAKTER} ile tekrar oku."
    return sonuc


def dosya_ara(aranan: str, klasor: str = "masaustu", derinlik: int = 3) -> dict:
    kok = yol_coz(klasor)
    if gizli_mi(kok) or not kok.is_dir():
        return {"hata": f"Aranacak klasor yok ya da erisilemez: {kok}"}
    aranan_k = aranan.strip().lower()
    bulunan: list[str] = []
    derinlik = max(1, min(int(derinlik), 6))

    def gez(d: Path, seviye: int) -> None:
        if seviye > derinlik or len(bulunan) >= MAX_OGE:
            return
        try:
            ogeler = list(d.iterdir())
        except (PermissionError, OSError):
            return
        for o in ogeler:
            if len(bulunan) >= MAX_OGE:
                return
            if o.name in ATLANAN_KLASORLER or gizli_mi(o):
                continue
            if aranan_k in o.name.lower():
                bulunan.append(f"{'[klasor] ' if o.is_dir() else ''}{o.relative_to(kok)}")
            if o.is_dir():
                gez(o, seviye + 1)

    gez(kok, 1)
    return {"klasor": str(kok), "aranan": aranan, "bulunan": bulunan, "sayi": len(bulunan)}


def _fonk(ad: str, aciklama: str, ozellikler: dict, zorunlu: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": ad,
            "description": aciklama,
            "parameters": {"type": "object", "properties": ozellikler, "required": zorunlu},
        },
    }


ARACLAR: list[dict] = [
    _fonk(
        "klasor_listele",
        "Bu bilgisayardaki bir klasorun dosya ve klasorlerini listeler. Masaustu icin "
        "yol='masaustu'; 'belgeler', 'indirilenler', 'resimler' ya da tam yol da olur.",
        {"yol": {"type": "string", "description": "masaustu, belgeler ya da C:\\... gibi yol"}},
        ["yol"],
    ),
    _fonk(
        "dosya_oku",
        "Bir metin dosyasinin icerigini okur (txt, md, csv, json, kod...). En fazla 6000 karakter.",
        {
            "yol": {"type": "string", "description": "Tam yol ya da masaustu/dosya.txt"},
            "baslangic": {"type": "integer", "description": "Kacinci karakterden (devami icin)"},
        },
        ["yol"],
    ),
    _fonk(
        "dosya_ara",
        "Bir klasorde adinda verilen metin gecen dosya/klasorleri arar (alt klasorler dahil).",
        {
            "aranan": {"type": "string"},
            "klasor": {"type": "string", "description": "Varsayilan masaustu"},
        },
        ["aranan"],
    ),
    *[a for a in demo.ARACLAR if a["function"]["name"] in ("hesapla", "saat_kac", "birim_cevir")],
]
ISLEYICILER: dict[str, Any] = {
    "klasor_listele": klasor_listele,
    "dosya_oku": dosya_oku,
    "dosya_ara": dosya_ara,
    "hesapla": demo.hesapla,
    "saat_kac": demo.saat_kac,
    "birim_cevir": demo.birim_cevir,
}
SISTEM_NOTU = (
    "Bu bilgisayardaki dosya ve klasorlere salt okunur araclarla erisebilirsin: klasor_listele, "
    "dosya_oku, dosya_ara. Kullanici dosya, klasor ya da masaustu hakkinda sorarsa 'yapamam' deme, "
    "uygun araci cagir (masaustu icin yol='masaustu'). Hesap icin hesapla, saat icin saat_kac. "
    "Dosya silme, yazma ya da tasima aracin yok; istenirse bunu acikca soyle."
)


def sonuc_ozeti(ad: str, sonuc: Any) -> str:
    """Arayuzde gosterilecek kisa ozet."""
    if not isinstance(sonuc, dict):
        return str(sonuc)[:80]
    if "hata" in sonuc:
        return f"hata: {sonuc['hata']}"
    if ad == "klasor_listele":
        return f"{sonuc['klasor_sayisi']} klasor, {sonuc['dosya_sayisi']} dosya"
    if ad == "dosya_oku":
        return f"{sonuc['karakter']} karakter okundu"
    if ad == "dosya_ara":
        return f"{sonuc['sayi']} sonuc"
    return ", ".join(f"{k}: {v}" for k, v in list(sonuc.items())[:3])[:100]
