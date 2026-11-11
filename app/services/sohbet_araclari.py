"""Sohbette modelin kullanabildigi araclar. HEPSI SALT OKUNUR: dosya yazma, silme, tasima yok.
Gizli bilgi icerebilecek yerler (ssh/bulut anahtarlari, .env, tarayici profilleri) okunmaz."""

from __future__ import annotations

import ctypes
import re
import sys
import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agent import policy
from app.agent.yollar import guvenli_coz, ham_dogrula, kimlik, kimlik_dogrula
from app.exceptions import YetkiYok
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


def takma_ad(temiz: str) -> Path | None:
    """`masaustu`, `belgeler/Notlar` gibi takma adi gercek yola cevirir; takma ad yoksa None."""
    anahtar = _TAKMA_AD.get(temiz.lower().rstrip("/\\"))
    if anahtar:
        return bilinen_klasor(anahtar)
    for takma, gercek in _TAKMA_AD.items():  # "masaustu/Projeler" gibi
        on_ek = takma + "/"
        if temiz.lower().replace("\\", "/").startswith(on_ek):
            return bilinen_klasor(gercek) / temiz[len(on_ek) :]
    return None


def yol_coz(yol: str | None) -> Path:
    temiz = (yol or "masaustu").strip().strip("\"'")
    if (hedef := takma_ad(temiz)) is not None:
        return hedef
    p = Path(temiz).expanduser()
    return p if p.is_absolute() else Path.home() / p


def gizli_mi(p: Path) -> bool:
    """Gizli hedef mi? Tek kaynak izin motorunda (`agent.policy.hassas_mi`)."""
    return policy.hassas_mi(p)


def varsayilan_kokler() -> list[Path]:
    """Proje acilmadiginda dosya araclarinin dokunabilecegi kisisel klasorler.

    Once tum ev dizini (ve mutlak her yol) erisilebiliyordu; A1 ile kapsam bu dort klasore
    indirildi. Proje acilinca kokler projenin kendisi olur.
    """
    return [bilinen_klasor(a) for a in ("masaustu", "belgeler", "indirilenler", "resimler")]


def _boyut(n: int) -> str:
    for birim in ("B", "KB", "MB", "GB"):
        if n < 1024 or birim == "GB":
            return f"{n:.0f} {birim}" if birim == "B" else f"{n:.1f} {birim}"
        n /= 1024
    return ""


class DosyaAraclari:
    """Salt okunur dosya araclari, YETKILI KOKLERE bagli.

    Kokler kurucuda kapatilir (closure): model arguman olarak kok listesini degistiremez.
    Her yol `agent.yollar.guvenli_coz` ile kanonik hale gelir ve kapsama kontrolunden gecer;
    junction/symlink, UNC, cihaz yolu ve alternatif veri akisi kacislari burada kapanir.
    """

    def __init__(self, kokler: Sequence[Path] | None = None) -> None:
        self.kokler = [Path(k) for k in (kokler if kokler is not None else varsayilan_kokler())]
        self.projeli = kokler is not None  # proje acik: varsayilan hedef proje koku

    def _coz(self, ham: str | None, *, varsayilan: str = "masaustu") -> Path:
        if not (ham or "").strip() and self.projeli and self.kokler:
            varsayilan = str(self.kokler[0])  # A13: bos klasor Masaustu'ne degil projeye gider
        temiz = ham_dogrula(ham or varsayilan)
        hedef = takma_ad(temiz)
        if hedef is None:
            p = Path(temiz).expanduser()
            # goreli ad: ev dizini yerine ILK YETKILI KOK altinda aranir
            hedef = p if p.is_absolute() else ((self.kokler[0] / temiz) if self.kokler else p)
        yetkili = guvenli_coz(self.kokler, str(hedef))
        if policy.hassas_mi(yetkili):
            raise YetkiYok(
                "Bu hedef gizli bilgi (anahtar, parola, oturum) icerebilecegi icin okunmaz."
            )
        return yetkili

    def klasor_listele(self, yol: str = "masaustu", gizlileri_goster: bool = False) -> dict:
        try:
            k = self._coz(yol)
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        return _klasor_listele(k, gizlileri_goster)

    def dosya_oku(self, yol: str, baslangic: int = 0) -> dict:
        try:
            p = self._coz(yol, varsayilan="")
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        return _dosya_oku(p, baslangic)

    def dosya_ara(self, aranan: str, klasor: str = "masaustu", derinlik: int = 3) -> dict:
        try:
            kok = self._coz(klasor)
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        return _dosya_ara(aranan, kok, derinlik)

    def isleyiciler(self) -> dict[str, Any]:
        """Arac adi -> baglanmis fonksiyon. Model yalniz sema alanlarini gonderebilir."""
        return {
            "klasor_listele": self.klasor_listele,
            "dosya_oku": self.dosya_oku,
            "dosya_ara": self.dosya_ara,
            "hesapla": demo.hesapla,
            "saat_kac": demo.saat_kac,
            "birim_cevir": demo.birim_cevir,
        }


def klasor_listele(yol: str = "masaustu", gizlileri_goster: bool = False) -> dict:
    """Varsayilan kisisel kokler ile (proje acilmadiginda ve testlerde)."""
    return DosyaAraclari().klasor_listele(yol, gizlileri_goster)


def _klasor_listele(k: Path, gizlileri_goster: bool = False) -> dict:
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
    return DosyaAraclari().dosya_oku(yol, baslangic)


def _dosya_oku(p: Path, baslangic: int = 0) -> dict:
    if not p.is_file():
        return {"hata": f"Dosya bulunamadi: {p}"}
    if p.stat().st_size > MAX_DOSYA_BAYT:
        return {"hata": "Dosya 5 MB'dan buyuk; okunmadi."}
    kimlik_once = kimlik(p)  # kontrol-kullanim arasinda dosya degistiyse okumayi iptal et
    veri = p.read_bytes()
    try:
        kimlik_dogrula(p, kimlik_once)
    except YetkiYok as e:
        return {"hata": str(e), "karar": "ret"}
    if b"\x00" in veri[:4096]:
        return {"hata": "Bu bir metin dosyasi degil (ikili dosya); icerigi okunamaz."}
    metin = veri.decode("utf-8", errors="replace")
    baslangic = min(max(0, int(baslangic)), len(metin))
    bitis = min(baslangic + MAX_OKUMA_KARAKTER, len(metin))
    parca = metin[baslangic:bitis]
    kesildi = bitis < len(metin)
    sonuc: dict[str, Any] = {
        "dosya": str(p),
        "karakter": len(metin),  # geriye donuk uyumluluk
        "toplam_karakter": len(metin),
        "toplam_satir": metin.count("\n") + 1,
        "satir_baslangic": metin.count("\n", 0, baslangic) + 1,
        "satir_bitis": metin.count("\n", 0, bitis) + 1,
        "baslangic": baslangic,
        "bitis": bitis,
        "truncated": kesildi,
        "next_offset": bitis if kesildi else None,
        "icerik": parca,
    }
    if kesildi:
        sonuc["devam"] = f"Devami icin baslangic={bitis} ile tekrar oku."
    return sonuc


def dosya_ara(aranan: str, klasor: str = "masaustu", derinlik: int = 3) -> dict:
    return DosyaAraclari().dosya_ara(aranan, klasor, derinlik)


def _dosya_ara(aranan: str, kok: Path, derinlik: int = 3) -> dict:
    if not kok.is_dir():
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
    "Dosya araclarin SALT OKUNUR: klasor_listele, dosya_oku, dosya_ara (masaustu icin "
    "yol='masaustu'). Dosya yazma, silme, tasima aracin YOK; istenirse acikca soyle. "
    "Hesap icin hesapla, saat icin saat_kac. Araci metinle anlatma ('cagiracagim' deme), "
    "dogrudan cagir."
)  # Her istekte giden sabit onek: kisa tutulur (dahili GPU'da girdi isleme 14-26 tok/sn)


def sonuc_ozeti(ad: str, sonuc: Any) -> str:
    """Arayuzde gosterilecek kisa ozet."""
    if not isinstance(sonuc, dict):
        return str(sonuc)[:80]
    if "hata" in sonuc:
        return f"hata: {sonuc['hata']}"
    if ad == "klasor_listele" and "klasor_sayisi" in sonuc:
        return f"{sonuc['klasor_sayisi']} klasor, {sonuc['dosya_sayisi']} dosya"
    if ad == "dosya_oku" and "karakter" in sonuc:
        kesik = " (kesildi)" if sonuc.get("truncated") else ""
        return f"{sonuc['karakter']} karakter okundu{kesik}"
    if ad == "dosya_ara" and "sayi" in sonuc:
        return f"{sonuc['sayi']} sonuc"
    return ", ".join(f"{k}: {v}" for k, v in list(sonuc.items())[:3])[:100]
