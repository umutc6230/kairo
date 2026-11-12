"""Masaustu kontrolunde ajanin hedefini ekranda gosterir (openbot'un "agent cursor" ve pencere
vurgusundan uyarlandi): hedef pencere MAVI cerceve, tiklanacak/yazilacak eleman TURUNCU cerceve.

Ek paket yok: ctypes ile katmanli (yari saydam), tiklamayi gecirgen (WS_EX_TRANSPARENT), her
zaman ustte, odak almayan pencereler; cerceve sekli SetWindowRgn ile (ic kisim delik). Pencereler
kendi is parcaciginda acilir ve sure dolunca kapanir; ajanin eylemini BLOKLAMAZ (yalniz kisa
bir gorunme bekleyisi olur). Windows disinda hicbir sey yapmaz.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
import threading
import time
from ctypes import wintypes

MAVI = 0x00E0A040  # BGR: (64,160,224)
TURUNCU = 0x00306CE0  # BGR: (224,108,48)
KALINLIK = 4

_hazir = False
_kilit = threading.Lock()


def _api():
    u32, g32, k32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
    H = ctypes.c_void_p  # noqa: N806 - 64-bit tutamaclar (int'e kesilmesin; tepsi.py dersi)
    u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                    wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, H, H, H, H]  # fmt: skip
    u32.CreateWindowExW.restype = H
    u32.DefWindowProcW.argtypes = [H, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.DefWindowProcW.restype = ctypes.c_ssize_t
    u32.SetLayeredWindowAttributes.argtypes = [H, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
    u32.SetWindowRgn.argtypes = [H, H, wintypes.BOOL]
    u32.ShowWindow.argtypes = [H, ctypes.c_int]
    u32.DestroyWindow.argtypes = [H]
    u32.PeekMessageW.argtypes = [ctypes.c_void_p, H, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    u32.TranslateMessage.argtypes = [ctypes.c_void_p]
    u32.DispatchMessageW.argtypes = [ctypes.c_void_p]
    g32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
    g32.CreateRectRgn.restype = H
    g32.CombineRgn.argtypes = [H, H, H, ctypes.c_int]
    g32.CreateSolidBrush.argtypes = [wintypes.DWORD]
    g32.CreateSolidBrush.restype = H
    g32.DeleteObject.argtypes = [H]
    k32.GetModuleHandleW.restype = H
    return u32, g32, k32


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)  # fmt: skip


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", ctypes.c_void_p),
                ("hIcon", ctypes.c_void_p), ("hCursor", ctypes.c_void_p),
                ("hbrBackground", ctypes.c_void_p), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]  # fmt: skip


_siniflar: dict[int, str] = {}
_proc_ref = None


def _sinif(renk: int) -> str:
    """Renk basina bir pencere sinifi (arka plan fircasi = cerceve rengi)."""
    global _proc_ref
    if renk in _siniflar:
        return _siniflar[renk]
    u32, g32, k32 = _api()
    if _proc_ref is None:
        _proc_ref = WNDPROC(lambda h, m, w, l: u32.DefWindowProcW(h, m, w, l))  # noqa: E741
    ad = f"KairoVurgu{renk:06x}"
    wc = WNDCLASSW()
    wc.lpfnWndProc = _proc_ref
    wc.hInstance = k32.GetModuleHandleW(None)
    wc.hbrBackground = g32.CreateSolidBrush(renk)
    wc.lpszClassName = ad
    u32.RegisterClassW(ctypes.byref(wc))
    _siniflar[renk] = ad
    return ad


def _goster(kutular: list[tuple[tuple[int, int, int, int], int]], sure: float) -> None:
    u32, g32, k32 = _api()
    # UI Automation dikdortgenleri FIZIKSEL pikseldir; bu is parcacigi DPI'dan habersiz olursa
    # %125 olceklemede cerceve kayiyordu (canli). Per-monitor v2 baglami: koordinatlar fiziksel.
    with contextlib.suppress(Exception):
        u32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    ex = (
        0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000
    )  # LAYERED|TRANSPARENT|TOPMOST|TOOLWINDOW|NOACTIVATE
    hwndler = []
    for (sol, ust, sag, alt), renk in kutular:
        g, y = max(sag - sol, 2 * KALINLIK + 2), max(alt - ust, 2 * KALINLIK + 2)
        h = u32.CreateWindowExW(ex, _sinif(renk), "", 0x80000000, sol, ust, g, y,
                                None, None, k32.GetModuleHandleW(None), None)  # fmt: skip
        if not h:
            continue
        u32.SetLayeredWindowAttributes(h, 0, 220, 0x2)  # LWA_ALPHA
        dis = g32.CreateRectRgn(0, 0, g, y)
        ic = g32.CreateRectRgn(KALINLIK, KALINLIK, g - KALINLIK, y - KALINLIK)
        g32.CombineRgn(dis, dis, ic, 4)  # RGN_DIFF: yalniz cerceve
        g32.DeleteObject(ic)
        u32.SetWindowRgn(h, dis, True)  # bolge pencereye gecer; silinmez
        u32.ShowWindow(h, 4)  # SW_SHOWNOACTIVATE
        hwndler.append(h)
    msg = wintypes.MSG()
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis:
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.02)
    for h in hwndler:
        u32.DestroyWindow(h)


def vurgula(pencere=None, eleman=None, sure: float = 1.6, bekle: float = 0.45) -> bool:
    """pencere/eleman: (sol, ust, sag, alt) ekran koordinatlari. Gosterir, `bekle` sn bekler
    (kullanici neye tiklanacagini gorsun), sonra doner; cerceveler `sure` dolunca kapanir."""
    if sys.platform != "win32":
        return False
    kutular = []
    if pencere and pencere[2] > pencere[0] and pencere[3] > pencere[1]:
        kutular.append((tuple(pencere), MAVI))
    if eleman and eleman[2] > eleman[0] and eleman[3] > eleman[1]:
        p = 3  # eleman cercevesi biraz disaridan
        kutular.append(((eleman[0] - p, eleman[1] - p, eleman[2] + p, eleman[3] + p), TURUNCU))
    if not kutular:
        return False

    def is_() -> None:
        with _kilit, contextlib.suppress(Exception):  # vurgu yardimcidir; eylemi asla bozmaz
            _goster(kutular, sure)

    threading.Thread(target=is_, daemon=True).start()
    time.sleep(max(0.0, bekle))
    return True


def dikdortgen(eleman) -> tuple[int, int, int, int] | None:
    """UIA elemaninin ekran dikdortgeni (gorunmuyorsa None)."""
    try:
        r = eleman.CurrentBoundingRectangle
    except Exception:  # noqa: BLE001
        return None
    if r.right <= r.left or r.bottom <= r.top:
        return None
    return (r.left, r.top, r.right, r.bottom)
