"""Ajan dosya okuma araclari: satir numarali okuma, glob ve icerik arama (A2.1).

Tek yol cozme noktasi `KokKapsami`: hem sohbetin basit araclari hem ajanin zengin araclari
buradan gecer, boylece iki ayri kapsama mantigi olusmaz.

Okuma sonuclari DAIMA yapisaldir: `truncated`, `next_offset` / `sonraki_satir`, toplam uzunluk.
Serilestirmeden sonra kesme yapilmaz (A0.3).
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from app.agent import policy
from app.agent.checkpoints import icerik_hashi
from app.agent.yollar import guvenli_coz, ham_dogrula, kimlik, kimlik_dogrula
from app.exceptions import YetkiYok

MAX_SATIR = 400  # tek okumada en fazla satir
MAX_SATIR_KARAKTER = 2000  # tek satirdan alinan en fazla karakter
MAX_OKUMA_KARAKTER = 60000
MAX_DOSYA_BAYT = 5 * 1024 * 1024
MAX_SONUC = 200
MAX_ARAMA_SATIRI = 120
ATLANAN = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache"}
IKILI_UZANTILAR = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".exe", ".dll",
    ".gguf", ".bin", ".so", ".dylib", ".woff", ".woff2", ".ico", ".mp3", ".wav",
}  # fmt: skip
ESLESME_SATIRI = re.compile(r"^(.+?):(\d+):(.*)$")


class KokKapsami:
    """Yetkili kokler ve tek yol cozme noktasi. Kokler closure'da: model argumanla ezemez."""

    def __init__(self, kokler: Sequence[Path] | None = None) -> None:
        self.kokler = [Path(k) for k in (kokler or [])]

    def coz(self, ham: str | None, *, varsayilan: str = ".") -> Path:
        temiz = ham_dogrula(ham if (ham or "").strip() else varsayilan)
        p = Path(temiz).expanduser()
        if not p.is_absolute() and self.kokler:
            p = self.kokler[0] / temiz
        hedef = guvenli_coz(self.kokler, str(p))
        if policy.hassas_mi(hedef):
            raise YetkiYok(
                "Bu hedef gizli bilgi (anahtar, parola, oturum) icerebilecegi icin acilmaz."
            )
        return hedef

    def kok_of(self, p: Path) -> Path:
        from app.agent.yollar import icinde_mi

        return next(
            (k for k in self.kokler if icinde_mi(k, p)), self.kokler[0] if self.kokler else p
        )

    def goreli(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.kok_of(p)))
        except ValueError:
            return str(p)


# ----------------------------------------------------------------- gitignore


class GitIgnore:
    """Kucuk .gitignore eslestirici (rg yoksa yedek yol icin).

    Tam git semantigi DEGILDIR: `**`, negatif desen ve dizin kuralinin temel hali desteklenir.
    Eksik eslesme guvenlik sorunu degildir; yalniz gurultu filtresidir.
    """

    def __init__(self, kok: Path) -> None:
        self.kok = kok
        self.desenler: list[tuple[str, bool, bool]] = []  # (desen, negatif, yalniz_dizin)
        try:
            satirlar = (
                (kok / ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines()
            )
        except OSError:
            satirlar = []
        for ham in satirlar:
            s = ham.strip()
            if not s or s.startswith("#"):
                continue
            negatif = s.startswith("!")
            s = s[1:] if negatif else s
            yalniz_dizin = s.endswith("/")
            self.desenler.append((s.strip("/"), negatif, yalniz_dizin))

    def yok_sayilir(self, p: Path) -> bool:
        try:
            goreli = p.relative_to(self.kok).as_posix()
        except ValueError:
            return False
        sonuc = False
        for desen, negatif, yalniz_dizin in self.desenler:
            if yalniz_dizin and not p.is_dir():
                continue
            if self._eslesir(goreli, desen):
                sonuc = not negatif
        return sonuc

    @staticmethod
    def _eslesir(goreli: str, desen: str) -> bool:
        if fnmatch.fnmatch(goreli, desen) or fnmatch.fnmatch(Path(goreli).name, desen):
            return True
        return any(fnmatch.fnmatch(parca, desen) for parca in goreli.split("/"))


def ikili_mi(p: Path, ilk: bytes) -> bool:
    return p.suffix.lower() in IKILI_UZANTILAR or b"\x00" in ilk[:4096]


def _coz_metin(veri: bytes) -> tuple[str, str]:
    """(metin, kodlama). UTF-8 BOM ve cp1254 (Turkce Windows) denenir."""
    if veri.startswith(b"\xef\xbb\xbf"):
        return veri[3:].decode("utf-8", errors="replace"), "utf-8-bom"
    try:
        return veri.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return veri.decode("cp1254"), "cp1254"
    except (UnicodeDecodeError, LookupError):
        return veri.decode("utf-8", errors="replace"), "utf-8-hatali"


class AjanDosyaAraclari:
    """A2.1 okuma araclari. Hepsi salt okunur; yazma `agent.yazma` modulunde."""

    def __init__(self, kapsam: KokKapsami) -> None:
        self.kapsam = kapsam

    # ---- okuma ----
    def dosya_oku(self, yol: str, baslangic_satir: int = 1, satir_sayisi: int = MAX_SATIR) -> dict:
        try:
            p = self.kapsam.coz(yol)
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        if not p.is_file():
            return {"hata": f"Dosya bulunamadi: {p}"}
        boyut = p.stat().st_size
        if boyut > MAX_DOSYA_BAYT:
            return {"hata": f"Dosya {MAX_DOSYA_BAYT // (1024 * 1024)} MB'dan buyuk; okunmadi."}
        kimlik_once = kimlik(p)
        veri = p.read_bytes()
        try:
            kimlik_dogrula(p, kimlik_once)
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        if ikili_mi(p, veri):
            return {"hata": "Bu bir metin dosyasi degil (ikili); icerigi okunamaz."}
        metin, kodlama = _coz_metin(veri)
        satirlar = metin.splitlines()
        toplam = len(satirlar)
        bas = max(1, int(baslangic_satir))
        adet = max(1, min(int(satir_sayisi), MAX_SATIR))
        dilim = satirlar[bas - 1 : bas - 1 + adet]
        numarali = "\n".join(
            f"{bas + i:>6}\t{s[:MAX_SATIR_KARAKTER]}" for i, s in enumerate(dilim)
        )[:MAX_OKUMA_KARAKTER]
        son = bas + len(dilim) - 1
        kesildi = son < toplam
        return {
            "dosya": str(p),
            "goreli": self.kapsam.goreli(p),
            "kodlama": kodlama,
            "satir_sonu": "CRLF" if b"\r\n" in veri else "LF",
            "toplam_satir": toplam,
            "satir_baslangic": bas,
            "satir_bitis": son,
            "truncated": kesildi,
            "sonraki_satir": son + 1 if kesildi else None,
            "icerik": numarali,
            # yazma/yama/silme araclari bunu `beklenen_hash` olarak ister (bayat yazimi onler)
            "hash": icerik_hashi(veri),
        }

    def klasor_listele(self, yol: str = "", derinlik: int = 1) -> dict:
        try:
            k = self.kapsam.coz(yol, varsayilan=".")
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        if not k.is_dir():
            return {"hata": f"Klasor bulunamadi: {k}"}
        yoksay = GitIgnore(self.kapsam.kok_of(k))
        ogeler: list[str] = []
        for p in self._gez(k, max(1, min(int(derinlik), 4)), yoksay):
            if len(ogeler) >= MAX_SONUC:
                break
            ogeler.append(("[klasor] " if p.is_dir() else "") + str(p.relative_to(k)))
        return {
            "klasor": str(k),
            "sayi": len(ogeler),
            "truncated": len(ogeler) >= MAX_SONUC,
            "ogeler": ogeler,
        }

    def glob_bul(self, desen: str, klasor: str = "") -> dict:
        try:
            kok = self.kapsam.coz(klasor, varsayilan=".")
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        if not desen or len(desen) > 200:
            return {"hata": "Gecersiz desen."}
        yoksay = GitIgnore(self.kapsam.kok_of(kok))
        bulunan: list[str] = []
        try:
            for p in kok.glob(desen):
                if len(bulunan) >= MAX_SONUC:
                    break
                if yoksay.yok_sayilir(p):
                    continue
                # dist/build gibi klasorler desen ACIKCA icermiyorsa atlanir
                if any(x in ATLANAN and x not in desen for x in p.relative_to(kok).parts):
                    continue
                if policy.hassas_mi(p):
                    continue
                bulunan.append(str(p.relative_to(kok)))
        except (OSError, ValueError) as e:
            return {"hata": f"Glob hatasi: {e}"}
        return {
            "klasor": str(kok),
            "desen": desen,
            "sayi": len(bulunan),
            "truncated": len(bulunan) >= MAX_SONUC,
            "bulunan": sorted(bulunan),
        }

    def icerik_ara(self, desen: str, klasor: str = "", dosya_deseni: str = "") -> dict:
        """Icerik aramasi: once ripgrep (gitignore'a uyar), yoksa kontrollu Python yedegi."""
        try:
            kok = self.kapsam.coz(klasor, varsayilan=".")
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        if not desen:
            return {"hata": "Aranacak desen bos."}
        rg = shutil.which("rg")
        if rg:
            sonuc = self._rg(rg, desen, kok, dosya_deseni)
            if sonuc is not None:
                return sonuc
        return self._python_ara(desen, kok, dosya_deseni)

    # ---- yardimcilar ----
    def _gez(self, kok: Path, derinlik: int, yoksay: GitIgnore) -> Iterable[Path]:
        yigin: list[tuple[Path, int]] = [(kok, 1)]
        while yigin:
            d, seviye = yigin.pop(0)
            try:
                ogeler = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except OSError:
                continue
            for p in ogeler:
                if policy.hassas_mi(p) or yoksay.yok_sayilir(p):
                    continue
                if p.name in ATLANAN:
                    if p.is_dir() and p.name != ".git":  # gorunur ama icine inilmez (dist/build)
                        yield p
                    continue
                yield p
                if p.is_dir() and seviye < derinlik:
                    yigin.append((p, seviye + 1))

    def _rg(self, rg: str, desen: str, kok: Path, dosya_deseni: str) -> dict | None:
        komut = [rg, "--line-number", "--no-heading", "--color", "never", "--max-count", "20"]
        if dosya_deseni:
            komut += ["--glob", dosya_deseni]
        komut += ["--", desen, str(kok)]
        try:
            ch = subprocess.run(  # noqa: S603 - sabit komut, kullanici girdisi argumandir
                komut,
                capture_output=True,
                text=True,
                timeout=20,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if ch.returncode not in (0, 1):  # 1 = eslesme yok
            return None
        return self._satirlari_topla(ch.stdout.splitlines(), kok, desen, "ripgrep")

    def _python_ara(self, desen: str, kok: Path, dosya_deseni: str) -> dict:
        try:
            kalip = re.compile(desen)
        except re.error as e:
            return {"hata": f"Gecersiz desen: {e}"}
        satirlar: list[str] = []
        yoksay = GitIgnore(self.kapsam.kok_of(kok))
        for p in self._gez(kok, 6, yoksay):
            if len(satirlar) >= MAX_ARAMA_SATIRI:
                break
            if p.is_dir() or (dosya_deseni and not fnmatch.fnmatch(p.name, dosya_deseni)):
                continue
            try:
                if p.stat().st_size > MAX_DOSYA_BAYT:
                    continue
                veri = p.read_bytes()
            except OSError:
                continue
            if ikili_mi(p, veri):
                continue
            metin, _ = _coz_metin(veri)
            for no, satir in enumerate(metin.splitlines(), 1):
                if kalip.search(satir):
                    satirlar.append(f"{p}:{no}:{satir}")
                    if len(satirlar) >= MAX_ARAMA_SATIRI:
                        break
        return self._satirlari_topla(satirlar, kok, desen, "python")

    def _satirlari_topla(self, ham: list[str], kok: Path, desen: str, motor: str) -> dict:
        sonuc: list[dict[str, Any]] = []
        for satir in ham[:MAX_ARAMA_SATIRI]:
            # `C:\yol\a.py:12:metin` -> surucu harfindeki iki nokta yanlis bolmesin
            m = ESLESME_SATIRI.match(satir)
            if not m:
                continue
            dosya, no, metin = m.group(1), m.group(2), m.group(3)
            try:
                goreli = str(Path(dosya).relative_to(kok))
            except ValueError:
                goreli = dosya
            sonuc.append({"dosya": goreli, "satir": int(no) if no.isdigit() else 0,
                          "metin": metin.strip()[:300]})  # fmt: skip
        return {
            "klasor": str(kok),
            "desen": desen,
            "motor": motor,
            "sayi": len(sonuc),
            "truncated": len(ham) > MAX_ARAMA_SATIRI,
            "eslesmeler": sonuc,
        }


def ortam_allowlist() -> dict[str, str]:
    """Komut surecine verilecek ortam degiskenleri (A1.7). Sir tasiyanlar DISARIDA kalir."""
    izinli = (
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATHEXT", "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE", "OS", "HOMEDRIVE", "HOMEPATH", "USERPROFILE", "APPDATA",
        "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMDATA", "PYTHONIOENCODING", "LANG", "LC_ALL", "HOME",
    )  # fmt: skip
    ortam = {k: v for k, v in os.environ.items() if k.upper() in izinli}
    ortam.setdefault("PYTHONIOENCODING", "utf-8")
    ortam["PYTHONDONTWRITEBYTECODE"] = "1"
    return ortam
