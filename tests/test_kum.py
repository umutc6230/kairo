"""Docker'siz Windows kum havuzu (AppContainer): gercek surecle, yalniz Windows'ta."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.agent import kum
from app.agent.izolasyon import KumAdaptoru, adaptor_olustur

pytestmark = pytest.mark.skipif(not kum.destekli(), reason="AppContainer yalniz Windows 8+")


def _kos(kok: Path, komut: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(kum.argv(kok, kok, komut), capture_output=True, timeout=60)  # noqa: S603


@pytest.fixture
def kok(tmp_path: Path) -> Path:
    k = tmp_path / "proje"
    k.mkdir()
    return k


def test_adaptor_secimi_ve_durum() -> None:
    a = adaptor_olustur("kum", "")
    assert isinstance(a, KumAdaptoru)
    assert a.izole and a.durum()["kullanilabilir"]


def test_proje_icine_yazar(kok: Path) -> None:
    r = _kos(kok, "echo merhaba> ic.txt")
    assert r.returncode == 0
    assert (kok / "ic.txt").read_text().strip() == "merhaba"


def test_proje_disina_yazamaz(kok: Path) -> None:
    r = _kos(kok, "echo x> ..\\kacis.txt")
    assert r.returncode != 0
    assert not (kok.parent / "kacis.txt").exists()


def test_kullanici_profilini_okuyamaz(kok: Path) -> None:
    gizli = Path.home() / ".kairo-kum-test-gizli.txt"
    gizli.write_text("sir")
    try:
        r = _kos(kok, f'type "{gizli}"')
        assert r.returncode != 0
        assert b"sir" not in r.stdout
    finally:
        gizli.unlink()


def test_ag_kapali(kok: Path) -> None:
    curl = Path(r"C:\Windows\System32\curl.exe")
    if not curl.exists():
        pytest.skip("curl yok")
    r = _kos(kok, "curl -s -m 5 https://example.com -o nul")
    assert r.returncode != 0


def test_cikis_kodu_ve_cikti_gecer(kok: Path) -> None:
    r = _kos(kok, "echo boru && exit /b 7")
    assert r.returncode == 7
    assert b"boru" in r.stdout


def test_frozen_argv_exe_kendisi(monkeypatch: pytest.MonkeyPatch, kok: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert kum.argv(kok, kok, "x")[:2] == [sys.executable, "--kum"]
