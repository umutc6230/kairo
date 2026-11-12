# ruff: noqa: E501 - Win32 yapi tanimlari
"""Windows sistem tepsisi simgesi (ek paket yok; Shell_NotifyIcon + ctypes).

Sol tik: pencereyi one getir. Sag tik: Ac / Cik menusu. Ayri bir is parcaciginda kendi
mesaj dongusuyle calisir; kapat() simgeyi kaldirir.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

from loguru import logger

WM_APP_TEPSI = 0x8001
WM_LBUTTONUP, WM_RBUTTONUP, WM_CLOSE, WM_DESTROY = 0x0202, 0x0205, 0x0010, 0x0002
NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x100, 0x2
HWND_MESSAGE = -3
LR_LOADFROMFILE, IMAGE_ICON = 0x10, 1

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON),
    ]  # fmt: skip


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]  # fmt: skip


class Tepsi:
    def __init__(
        self, ipucu: str, ikon: Path, goster: Callable[[], None], cik: Callable[[], None]
    ) -> None:
        self.ipucu, self.ikon, self.goster, self.cik = ipucu, ikon, goster, cik
        self._hwnd = None
        self._proc = None  # GC'den korunur

    def baslat(self) -> bool:
        if sys.platform != "win32":
            return False
        hazir = threading.Event()
        threading.Thread(target=self._dongu, args=(hazir,), daemon=True).start()
        hazir.wait(3)
        return self._hwnd is not None

    def _dongu(self, hazir: threading.Event) -> None:
        u, s, k = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
        u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.DefWindowProcW.restype = LRESULT
        u.CreateWindowExW.restype = wintypes.HWND
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                      wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]  # fmt: skip
        u.LoadImageW.restype = wintypes.HANDLE
        u.CreatePopupMenu.restype = wintypes.HMENU
        u.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, wintypes.HWND, wintypes.LPVOID]  # fmt: skip
        u.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        # Tipsiz cagri 64-bit tutamaci c_int'e kesiyordu: RegisterClassW erisim ihlali veriyordu
        k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k.GetModuleHandleW.restype = wintypes.HMODULE
        u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u.RegisterClassW.restype = wintypes.ATOM
        u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                                 ctypes.c_int, wintypes.UINT]  # fmt: skip
        u.DestroyWindow.argtypes = [wintypes.HWND]
        s.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        s.Shell_NotifyIconW.restype = wintypes.BOOL

        def proc(hwnd, msg, wp, lp):  # noqa: ANN001, ANN202 - Win32 geri cagrisi
            if msg == WM_APP_TEPSI:
                if lp == WM_LBUTTONUP:
                    self._guvenli(self.goster)
                elif lp == WM_RBUTTONUP:
                    self._menu(hwnd)
                return 0
            if msg == WM_DESTROY:
                u.PostQuitMessage(0)
                return 0
            return u.DefWindowProcW(hwnd, msg, wp, lp)

        self._proc = WNDPROC(proc)
        hinst = k.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName="KairoTepsi")
        u.RegisterClassW(ctypes.byref(wc))
        hwnd = u.CreateWindowExW(
            0, "KairoTepsi", "Kairo", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None
        )
        if not hwnd:
            hazir.set()
            return
        nid = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=hwnd, uID=1,
                              uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP, uCallbackMessage=WM_APP_TEPSI)  # fmt: skip
        nid.hIcon = u.LoadImageW(None, str(self.ikon), IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
        nid.szTip = self.ipucu[:127]
        if not s.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            logger.warning("Tepsi simgesi eklenemedi.")
            u.DestroyWindow(hwnd)
            hazir.set()
            return
        self._hwnd = hwnd
        hazir.set()
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))
        s.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def _menu(self, hwnd) -> None:  # noqa: ANN001
        u = ctypes.windll.user32
        m = u.CreatePopupMenu()
        u.AppendMenuW(m, 0, 1, "Kairo'yu aç")
        u.AppendMenuW(m, 0x800, 0, None)  # ayrac
        u.AppendMenuW(m, 0, 2, "Çık")
        pt = wintypes.POINT()
        u.GetCursorPos(ctypes.byref(pt))
        u.SetForegroundWindow(hwnd)  # menu disina tiklayinca kapansin
        sec = u.TrackPopupMenu(m, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None)
        u.DestroyMenu(m)
        if sec == 1:
            self._guvenli(self.goster)
        elif sec == 2:
            self._guvenli(self.cik)

    @staticmethod
    def _guvenli(f: Callable[[], None]) -> None:
        try:
            f()
        except Exception as e:  # noqa: BLE001
            logger.debug("Tepsi eylemi: {}", e)

    def kapat(self) -> None:
        if self._hwnd:
            u = ctypes.windll.user32
            u.PostMessageW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            u.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            self._hwnd = None
