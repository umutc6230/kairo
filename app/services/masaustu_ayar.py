# ruff: noqa: E501 - PowerShell betik satirlari
"""Claude Desktop 'Desktop app' ayarlarinin karsiliklari (Windows).

- Baslangicta ac: Baslangic klasorune kisayol (registry YAZILMAZ; kapatinca silinir).
- Bildirim: Windows toast (ek paket yok, PowerShell WinRT ile).
- Hizli acma kisayolu: RegisterHotKey ile genel kisayol; basilinca pencere one gelir.
- Depolama: veri klasorunun alt klasor boyutlari.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app import URUN_ADI

KISAYOL = (
    Path(os.environ.get("APPDATA", ""))
    / "Microsoft/Windows/Start Menu/Programs/Startup"
    / f"{URUN_ADI}.lnk"
)
GIZLI = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _ps(betik: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - sabit betik, kullanici girdisi tirnaklanir
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", betik],
        capture_output=True, text=True, timeout=timeout, creationflags=GIZLI,
    )  # fmt: skip


def _q(s: str) -> str:
    """PowerShell tek tirnakli metin."""
    return "'" + str(s).replace("'", "''") + "'"


def baslatici() -> tuple[str, str, str]:
    """(exe, argumanlar, calisma klasoru): paketli exe ya da pythonw -m app."""
    if getattr(sys, "frozen", False):
        return sys.executable, "", str(Path(sys.executable).parent)
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    return str(pyw if pyw.is_file() else py), "-m app", str(Path(__file__).resolve().parents[2])


def baslangic_durumu() -> bool:
    return KISAYOL.is_file()


def baslangic_ayarla(acik: bool) -> bool:
    if sys.platform != "win32":
        return False
    if not acik:
        KISAYOL.unlink(missing_ok=True)
        return False
    exe, arg, cwd = baslatici()
    ikon = Path(__file__).resolve().parents[1] / "web" / "kairo.ico"
    r = _ps(
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({_q(KISAYOL)});"
        f"$s.TargetPath={_q(exe)};$s.Arguments={_q(arg)};$s.WorkingDirectory={_q(cwd)};"
        f"$s.IconLocation={_q(ikon)};$s.Save()"
    )
    if r.returncode != 0:
        logger.warning("Baslangic kisayolu yazilamadi: {}", r.stderr[-300:])
    return KISAYOL.is_file()


def bildirim(baslik: str, metin: str) -> bool:
    """Windows toast. Basarisizsa False (arayuz kendi bildirimini gosterir)."""
    if sys.platform != "win32":
        return False
    xml = (
        "<toast><visual><binding template='ToastGeneric'>"
        f"<text>{_xml(baslik)}</text><text>{_xml(metin)}</text></binding></visual></toast>"
    )
    betik = (
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null;"
        f"$x=New-Object Windows.Data.Xml.Dom.XmlDocument;$x.LoadXml({_q(xml)});"
        # PowerShell'in kayitli AppUserModelID'si: ek kayit gerekmeden toast gosterir
        "$id='{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    try:
        return _ps(betik).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _xml(s: str) -> str:
    return (str(s)[:300].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("'", "&apos;"))  # fmt: skip


def depolama(veri_dizini: Path) -> list[dict]:
    out = []
    for d in sorted(p for p in veri_dizini.iterdir() if p.is_dir()):
        try:
            boyut = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        except OSError:
            boyut = 0
        out.append({"ad": d.name, "bayt": boyut})
    return sorted(out, key=lambda x: -x["bayt"])


# ---- genel kisayol (RegisterHotKey) ----
MOD = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "win": 0x8}
TUS = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B}
WM_HOTKEY, WM_QUIT, MOD_NOREPEAT = 0x0312, 0x0012, 0x4000


def kisayol_coz(metin: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+Space' -> (modlar, sanal tus). En az bir mod ve tek tus sart."""
    parca = [p.strip().lower() for p in metin.split("+") if p.strip()]
    if len(parca) < 2:
        return None
    mod = 0
    for p in parca[:-1]:
        if p not in MOD:
            return None
        mod |= MOD[p]
    son = parca[-1]
    vk = TUS.get(son) or (ord(son.upper()) if len(son) == 1 and son.isalnum() else 0)
    if not vk and son.startswith("f") and son[1:].isdigit() and 1 <= int(son[1:]) <= 12:
        vk = 0x6F + int(son[1:])
    return (mod, vk) if vk else None


class GenelKisayol:
    def __init__(self, geri: Callable[[], None]) -> None:
        self.geri = geri
        self._tid = 0
        self.hata = ""

    def ayarla(self, metin: str) -> bool:
        self.kapat()
        self.hata = ""
        if sys.platform != "win32" or not metin:
            return False
        c = kisayol_coz(metin)
        if c is None:
            self.hata = f"Gecersiz kisayol: {metin}"
            return False
        hazir = threading.Event()
        threading.Thread(target=self._dongu, args=(c, hazir), daemon=True).start()
        hazir.wait(2)
        return not self.hata

    def _dongu(self, c: tuple[int, int], hazir: threading.Event) -> None:
        from ctypes import wintypes

        u = ctypes.windll.user32
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        if not u.RegisterHotKey(None, 1, c[0] | MOD_NOREPEAT, c[1]):
            self.hata = "Kısayol başka bir uygulamada kullanılıyor."
            self._tid = 0
            hazir.set()
            return
        hazir.set()
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    self.geri()
                except Exception as e:  # noqa: BLE001
                    logger.debug("Kisayol geri cagrisi: {}", e)
        u.UnregisterHotKey(None, 1)

    def kapat(self) -> None:
        if self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._tid = 0
