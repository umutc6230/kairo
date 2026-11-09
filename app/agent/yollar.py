"""Windows'ta guvenli yol cozumu ve kapsama kontrolu (A1.5).

`Path(x).is_absolute()` + ad eslestirmesi YETERSIZ. Bu modul su kacislari kapatir:
- junction / symlink: hedef kok disinda olabilir -> `os.path.realpath` ile gerceklestir
- cihaz yolu (`\\\\?\\`, `\\\\.\\`) ve UNC (`\\\\sunucu\\pay`) -> varsayilan reddedilir
- alternatif veri akisi (`dosya.txt:gizli`) -> ad bazli kontrolleri atlatir, reddedilir
- ayrilmis ad (`CON`, `NUL`, `COM1`) -> aygita yazar/okur, reddedilir
- sonda nokta/bosluk (`dosya.txt.`) -> Windows sessizce kirpar, ad kontrolu atlanir
- harf buyuklugu -> karsilastirma `os.path.normcase` ile

TOCTOU: kontrol ile kullanim arasinda dosya degistirilebilir. `kimlik` + `kimlik_dogrula` bunu
acmak ICIN kullanilir; tam garanti degil, bu nedenle yazma araclari ayrica beklenen hash ister.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path

from app.exceptions import YetkiYok

AYRILMIS_ADLAR = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
CIHAZ_ONEKLERI = ("\\\\.\\", "\\\\?\\")
SURUCU = re.compile(r"^[A-Za-z]:$")
MAX_YOL_UZUNLUK = 4096


def ham_dogrula(ham: str) -> str:
    """Yol METNI uzerinde yapisal kontrol (dosya sistemine dokunmadan). Temiz metni dondurur."""
    s = (ham or "").strip().strip("\"'")
    if not s:
        raise YetkiYok("Bos yol verildi.")
    if "\x00" in s:
        raise YetkiYok("Yolda gecersiz karakter var.")
    if len(s) > MAX_YOL_UZUNLUK:
        raise YetkiYok("Yol cok uzun.")
    d = s.replace("/", "\\")
    if d.startswith(CIHAZ_ONEKLERI):
        raise YetkiYok("Cihaz yolu (\\\\?\\, \\\\.\\) kullanilamaz.")
    if d.startswith("\\\\"):
        raise YetkiYok("Ag yolu (UNC) varsayilan olarak kullanilamaz.")
    for i, parca in enumerate(d.split("\\")):
        if not parca:
            continue
        if i == 0 and SURUCU.match(parca):
            continue
        if parca in (".", ".."):
            continue  # gezinme bileseni; kapsama zaten kanonik yolda dogrulanir
        if ":" in parca:
            raise YetkiYok(f"Alternatif veri akisi kullanilamaz: {parca}")
        if parca != parca.rstrip(" ."):
            raise YetkiYok(f"Sonunda nokta/bosluk olan ad kullanilamaz: {parca!r}")
        if parca.split(".")[0].strip().lower() in AYRILMIS_ADLAR:
            raise YetkiYok(f"Ayrilmis Windows adi kullanilamaz: {parca}")
    return s


def kanonik(yol: str | Path) -> Path:
    """Symlink/junction cozulmus mutlak yol. Dosya yoksa da calisir (ust klasor uzerinden)."""
    try:
        return Path(os.path.realpath(str(Path(yol).expanduser()), strict=False))
    except (OSError, ValueError) as e:
        raise YetkiYok(f"Yol cozulemedi: {yol}") from e


def _esit_bicim(p: Path) -> str:
    s = os.path.normcase(str(p))
    kirpik = s.rstrip("\\/")
    return kirpik or s  # "C:\\" gibi kok yollar bos kalmasin


def icinde_mi(kok: str | Path, hedef: str | Path) -> bool:
    """`hedef` kanonik olarak `kok`un icinde (ya da kendisi) mi? Harf buyuklugune duyarsiz."""
    k = _esit_bicim(kanonik(kok))
    h = _esit_bicim(kanonik(hedef))
    return h == k or h.startswith(k + os.sep)


def guvenli_coz(kokler: Sequence[str | Path], ham: str) -> Path:
    """Yolu dogrular, gerceklestirir ve verilen koklerden birinin icinde oldugunu garanti eder.

    Kok listesi BOS ise hicbir yola izin verilmez: calisma alani secilmeden dosya erisimi yok.
    """
    temiz = ham_dogrula(ham)
    hedef = kanonik(temiz)
    if not kokler:
        raise YetkiYok("Once bir proje (calisma alani) acin; kok dizin olmadan dosya okunmaz.")
    if not any(icinde_mi(k, hedef) for k in kokler):
        raise YetkiYok(f"Bu yol yetkili klasorlerin disinda: {hedef}")
    return hedef


def kimlik(yol: Path) -> tuple[int, int] | None:
    """Dosyanin kimligi (aygit, inode). Kontrol sonrasi yer degistirmeyi yakalamak icin."""
    try:
        st = yol.stat()
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


def kimlik_dogrula(yol: Path, beklenen: tuple[int, int] | None) -> None:
    """Kontrol anindaki dosya ile kullanilan dosya ayni mi (TOCTOU penceresini daraltir)."""
    if beklenen is None:
        return
    if kimlik(yol) != beklenen:
        raise YetkiYok("Dosya kontrol edildikten sonra degisti; islem iptal edildi.")
