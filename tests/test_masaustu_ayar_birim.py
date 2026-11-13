"""masaustu_ayar.py: baslangic kisayolu ve toast (sahte PowerShell), genel kisayol GERCEK
RegisterHotKey ile (Windows). Kullanicinin Baslangic klasorune dokunulmaz (KISAYOL tmp'ye)."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from app.services import masaustu_ayar as m

windows = pytest.mark.skipif(sys.platform != "win32", reason="yalniz Windows")


@pytest.fixture
def ps(monkeypatch):
    cagrilar: list[str] = []
    sonuc = SimpleNamespace(returncode=0, stderr="")

    def sahte(betik: str, timeout: int = 20):
        cagrilar.append(betik)
        return sonuc

    monkeypatch.setattr(m, "_ps", sahte)
    return SimpleNamespace(cagrilar=cagrilar, sonuc=sonuc)


def test_q_ve_xml_kacis() -> None:
    assert m._q("a'b") == "'a''b'"
    assert m._xml("<b>&'x'") == "&lt;b&gt;&amp;&apos;x&apos;"
    assert len(m._xml("x" * 500)) == 300


def test_baslatici_paketli_ve_kaynak(monkeypatch, tmp_path) -> None:
    exe, arg, cwd = m.baslatici()
    assert arg == "-m app" and exe.lower().endswith((".exe", "python", "pythonw"))
    monkeypatch.setattr(m.sys, "frozen", True, raising=False)
    monkeypatch.setattr(m.sys, "executable", str(tmp_path / "Kairo.exe"))
    assert m.baslatici() == (str(tmp_path / "Kairo.exe"), "", str(tmp_path))


def test_baslangic_kisayolu_yaz_ve_sil(monkeypatch, tmp_path, ps) -> None:
    lnk = tmp_path / "Kairo.lnk"
    monkeypatch.setattr(m, "KISAYOL", lnk)
    monkeypatch.setattr(m.sys, "platform", "win32")

    def yaz(betik: str, timeout: int = 20):
        ps.cagrilar.append(betik)
        lnk.write_bytes(b"lnk")
        return ps.sonuc

    monkeypatch.setattr(m, "_ps", yaz)
    assert m.baslangic_ayarla(True) is True and m.baslangic_durumu() is True
    assert "CreateShortcut(" in ps.cagrilar[0] and "kairo.ico" in ps.cagrilar[0]
    assert m.baslangic_ayarla(False) is False and not lnk.exists()


def test_baslangic_kisayolu_yazilamazsa_false(monkeypatch, tmp_path, ps) -> None:
    monkeypatch.setattr(m, "KISAYOL", tmp_path / "yok.lnk")
    monkeypatch.setattr(m.sys, "platform", "win32")
    ps.sonuc.returncode, ps.sonuc.stderr = 1, "erisim reddedildi"
    assert m.baslangic_ayarla(True) is False


def test_windows_disinda_kapali(monkeypatch) -> None:
    monkeypatch.setattr(m.sys, "platform", "linux")
    assert m.baslangic_ayarla(True) is False
    assert m.bildirim("a", "b") is False
    k = m.GenelKisayol(lambda: None)
    assert k.ayarla("Ctrl+Alt+K") is False and k.hata == ""


def test_bildirim_betigi_kacirir(monkeypatch, ps) -> None:
    monkeypatch.setattr(m.sys, "platform", "win32")
    assert m.bildirim("Baslik <x>", "it's") is True
    assert "Baslik &lt;x&gt;" in ps.cagrilar[0] and "it&apos;s" in ps.cagrilar[0]
    ps.sonuc.returncode = 1
    assert m.bildirim("a", "b") is False


def test_bildirim_powershell_yoksa_false(monkeypatch) -> None:
    monkeypatch.setattr(m.sys, "platform", "win32")

    def yok(*a, **k):
        raise OSError("powershell yok")

    monkeypatch.setattr(m, "_ps", yok)
    assert m.bildirim("a", "b") is False


def test_gecersiz_kisayol_hata_verir() -> None:
    k = m.GenelKisayol(lambda: None)
    assert k.ayarla("") is False
    if sys.platform == "win32":
        assert k.ayarla("Ctrl+Hyper+K") is False
        assert "Gecersiz" in k.hata


@windows
def test_gercek_genel_kisayol_tetiklenir_ve_cakisma_bildirilir() -> None:
    basildi = threading.Event()
    k = m.GenelKisayol(basildi.set)
    assert k.ayarla("Ctrl+Alt+Shift+F11") is True, k.hata
    tid = k._tid
    assert tid
    ikinci = m.GenelKisayol(lambda: None)
    assert ikinci.ayarla("Ctrl+Alt+Shift+F11") is False  # ayni kisayol zaten kayitli
    assert "kullanılıyor" in ikinci.hata
    u = ctypes.windll.user32
    u.PostThreadMessageW.argtypes = [ctypes.c_ulong, ctypes.c_uint, ctypes.c_size_t,
                                     ctypes.c_ssize_t]  # fmt: skip
    u.PostThreadMessageW(tid, m.WM_HOTKEY, 1, 0)  # tusa basilmis gibi
    assert basildi.wait(3)
    k.kapat()
    assert k._tid == 0
    # dongu bitti ve kayit kalkti: ayni kisayol yeniden alinabilir
    ucuncu = m.GenelKisayol(lambda: None)
    for _ in range(40):
        if ucuncu.ayarla("Ctrl+Alt+Shift+F11"):
            break
        time.sleep(0.05)
    assert ucuncu.hata == ""
    ucuncu.kapat()


@windows
def test_geri_cagri_hatasi_donguyu_dusurmez() -> None:
    sayac: list[int] = []

    def patlar() -> None:
        sayac.append(1)
        raise RuntimeError("x")

    k = m.GenelKisayol(patlar)
    assert k.ayarla("Ctrl+Alt+Shift+F10") is True, k.hata
    u = ctypes.windll.user32
    for _ in range(2):
        u.PostThreadMessageW(k._tid, m.WM_HOTKEY, 1, 0)
    for _ in range(40):
        if len(sayac) == 2:
            break
        time.sleep(0.05)
    assert len(sayac) == 2
    k.kapat()
