"""Sistem tepsisi (app/services/tepsi.py). Windows'ta GERCEK Shell_NotifyIcon ile: simge eklenir,
gizli pencereye tik iletisi gonderilir, kapatinca mesaj dongusu biter. Engelleyen acilir menu
(TrackPopupMenu) sahte user32 ile ayrica denenir."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path

import pytest

from app.services import tepsi as t

IKON = Path(__file__).resolve().parents[1] / "app" / "web" / "kairo.ico"
windows = pytest.mark.skipif(sys.platform != "win32", reason="yalniz Windows")


def test_windows_disinda_baslamaz(monkeypatch) -> None:
    monkeypatch.setattr(t.sys, "platform", "linux")
    assert t.Tepsi("x", IKON, lambda: None, lambda: None).baslat() is False


def test_guvenli_hata_yutar() -> None:
    def patlar() -> None:
        raise RuntimeError("x")

    t.Tepsi._guvenli(patlar)  # istisna disari cikmaz


@windows
def test_gercek_tepsi_tik_iletileri_ve_kapatma(monkeypatch) -> None:
    gosterildi = threading.Event()
    menuler: list = []
    tp = t.Tepsi("Kairo test", IKON, gosterildi.set, lambda: None)
    monkeypatch.setattr(tp, "_menu", lambda hwnd: menuler.append(hwnd))
    assert tp.baslat() is True
    hwnd = tp._hwnd
    u = ctypes.windll.user32
    u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    u.SendMessageW(hwnd, t.WM_APP_TEPSI, 0, t.WM_LBUTTONUP)
    assert gosterildi.wait(3)
    u.SendMessageW(hwnd, t.WM_APP_TEPSI, 0, t.WM_RBUTTONUP)
    assert menuler == [hwnd]
    assert u.SendMessageW(hwnd, 0x0400, 0, 0) == 0  # diger ileti DefWindowProc'a gider
    tp.kapat()
    assert tp._hwnd is None
    tp.kapat()  # ikinci kez zararsiz
    u.IsWindow.argtypes = [ctypes.c_void_p]
    for _ in range(60):  # WM_CLOSE -> WM_DESTROY -> dongu biter, simge kaldirilir
        if not u.IsWindow(hwnd):
            break
        time.sleep(0.05)
    assert not u.IsWindow(hwnd)


class SahteUser32:
    def __init__(self, secim: int) -> None:
        self.secim = secim
        self.eklenen: list = []

    def CreatePopupMenu(self):  # noqa: N802 - Win32 adi
        return 7

    def AppendMenuW(self, m, bayrak, kimlik, metin):  # noqa: N802
        self.eklenen.append(metin)

    def GetCursorPos(self, p):  # noqa: N802
        return 1

    def SetForegroundWindow(self, h):  # noqa: N802
        return 1

    def TrackPopupMenu(self, *a):  # noqa: N802
        return self.secim

    def DestroyMenu(self, m):  # noqa: N802
        return 1


@pytest.mark.parametrize(("secim", "beklenen"), [(1, ["goster"]), (2, ["cik"]), (0, [])])
def test_menu_secimi(monkeypatch, secim, beklenen) -> None:
    olay: list[str] = []
    user = SahteUser32(secim)
    monkeypatch.setattr(t.ctypes, "windll", type("W", (), {"user32": user})(), raising=False)
    t.Tepsi("x", IKON, lambda: olay.append("goster"), lambda: olay.append("cik"))._menu(1)
    assert olay == beklenen
    assert user.eklenen == ["Kairo'yu aç", None, "Çık"]
