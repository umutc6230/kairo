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
    return subprocess.run(  # noqa: S603
        kum.argv(kok, kok, komut), capture_output=True, timeout=60, cwd=kok
    )


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


def test_ev_ve_surucu_koku_reddedilir(tmp_path: Path) -> None:
    for genis in (Path.home(), Path(Path.home().anchor)):
        with pytest.raises(OSError, match="cok genis"):
            kum.kok_dogrula(genis)
    assert kum.kok_dogrula(tmp_path) == tmp_path.resolve()


def test_her_projeye_ayri_kap(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert kum.kap_adi(a) != kum.kap_adi(b)
    assert len(kum.kap_adi(a)) <= 64  # AppContainer adi siniri


def test_bir_projenin_kabi_digerine_yazamaz(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert _kos(b, "echo b> b.txt").returncode == 0  # b'nin kabina b'de izin verildi
    r = _kos(a, f'echo x> "{b / "a-dan.txt"}"')
    assert r.returncode != 0
    assert not (b / "a-dan.txt").exists()


def test_projedeki_sahte_app_paketi_yardimciyi_ele_geciremez(kok: Path) -> None:
    kacis = kok.parent / "ele-gecirildi.txt"
    sahte = kok / "app" / "agent"
    sahte.mkdir(parents=True)
    (kok / "app" / "__init__.py").write_text("")
    (sahte / "__init__.py").write_text("")
    (sahte / "kum.py").write_text(f"open({str(kacis)!r}, 'w').write('x')\ndef main(a): return 0\n")
    _kos(kok, "echo tamam")
    assert not kacis.exists()


def test_git_klasorune_yazamaz_silemez_ama_projeye_yazar(kok: Path) -> None:
    (kok / ".git" / "hooks").mkdir(parents=True)
    (kok / ".git" / "config").write_text("[core]\n")
    r = _kos(kok, r"echo kotu> .git\hooks\pre-commit")
    assert r.returncode != 0
    assert not (kok / ".git" / "hooks" / "pre-commit").exists()
    _kos(kok, r"echo x>> .git\config")
    assert (kok / ".git" / "config").read_text() == "[core]\n"
    _kos(kok, "rmdir /s /q .git")
    assert (kok / ".git" / "config").exists()
    assert _kos(kok, "echo ok> normal.txt").returncode == 0


def test_git_sertlestir_repo_hookunu_ezer(tmp_path: Path) -> None:
    import os

    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git yok")
    r = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "config", "core.hooksPath", "kotu-hooks"], check=True)
    ortam = dict(os.environ)
    kum.git_sertlestir(ortam)
    cik = subprocess.run(
        ["git", "-C", str(r), "config", "core.hooksPath"], capture_output=True, text=True, env=ortam
    )
    assert cik.stdout.strip() == "NUL"


def test_git_baglanti_ise_reddedilir(kok: Path, tmp_path: Path) -> None:
    hedef = tmp_path / "baska"
    hedef.mkdir()
    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(kok / ".git"), str(hedef)], capture_output=True
    )
    if r.returncode != 0:
        pytest.skip("junction olusturulamadi")
    with pytest.raises(OSError, match="reparse"):
        kum.git_kilitle(kok, "S-1-15-2-1")


def test_git_sertlestir_tekrar_eklemez() -> None:
    o: dict = {}
    kum.git_sertlestir(o)
    kum.git_sertlestir(o)
    assert o["GIT_CONFIG_COUNT"] == "2"


def test_sertlestirme_komut_ortamina_gecer(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agent.dosyalar import ortam_allowlist

    for k in [k for k in __import__("os").environ if k.startswith("GIT_CONFIG_")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "0")
    import os

    kum.git_sertlestir(os.environ)
    o = ortam_allowlist()
    assert o["GIT_CONFIG_COUNT"] == "2" and o["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert "GIT_CONFIG_GLOBAL" not in o  # yalniz COUNT/KEY/VALUE gecer
