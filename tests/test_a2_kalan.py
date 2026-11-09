"""A2 kalanlari: terminale girdi, git dal/commit (her zaman onay), hunk bazli geri alma."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent.araclar import AjanAracKaydi
from app.agent.checkpoints import CakismaHatasi, CheckpointDeposu, dosya_hashi
from app.agent.policy import PolitikaMotoru
from app.agent.terminal import KomutServisi
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.exceptions import UygulamaHatasi

GIT = shutil.which("git")


def _git(kok: Path, *a: str) -> str:
    return subprocess.run(
        ["git", *a], cwd=kok, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def proje(tmp_path: Path) -> Path:
    p = tmp_path / "proje"
    p.mkdir()
    (p / "a.txt").write_bytes(b"bir\niki\nuc\ndort\nbes\n")  # LF: Windows'ta write_text CRLF yazar
    (p / "b.txt").write_text("b\n", encoding="utf-8")
    return p


@pytest.fixture
def kayit(tmp_path: Path, proje: Path):
    veri = tmp_path / "veri"
    veri.mkdir()
    alan = CalismaAlani(id="e" * 12, kokler=[str(proje)], guven=Guven.guvenilir, mod=Mod.otomatik)
    politika = PolitikaMotoru(veri)
    return AjanAracKaydi(alan, politika, CheckpointDeposu(veri), KomutServisi()), politika


# ------------------------------------------------------------- stdin (A2.4)


async def test_arka_plan_isine_girdi_gonderilir(proje: Path) -> None:
    s = KomutServisi()
    kod = "import sys; print('ad?', flush=True); print('selam ' + sys.stdin.readline().strip())"
    is_ = await s.baslat(f'"{sys.executable}" -c "{kod}"', proje, timeout=30, arka_plan=True)
    sonuc = await s.girdi_gonder(is_.durum.id, "umut")
    assert sonuc["gonderildi"] == 4
    await asyncio.wait_for(s.bekle(is_), 20)
    ozet = s.ozet(is_)
    assert ozet["cikis_kodu"] == 0 and "selam umut" in ozet["cikti"]
    with pytest.raises(UygulamaHatasi, match="calismiyor"):
        await s.girdi_gonder(is_.durum.id, "tekrar")


async def test_on_plan_isi_stdin_beklemez(proje: Path) -> None:
    """On planda stdin kapali: girdi bekleyen komut asili kalmaz, hemen biter."""
    s = KomutServisi()
    kod = "import sys; print(repr(sys.stdin.readline()))"
    is_ = await s.baslat(f'"{sys.executable}" -c "{kod}"', proje, timeout=10)
    await s.bekle(is_)
    assert s.ozet(is_)["durum"] == "bitti" and "''" in s.ozet(is_)["cikti"]


async def test_girdi_siniri(proje: Path) -> None:
    s = KomutServisi()
    bekle = "ping -n 30 127.0.0.1 > nul" if sys.platform == "win32" else "sleep 30"
    is_ = await s.baslat(bekle, proje, timeout=60, arka_plan=True)
    try:
        with pytest.raises(UygulamaHatasi, match="en fazla"):
            await s.girdi_gonder(is_.durum.id, "x" * 10001)
    finally:
        await s.durdur(is_.durum.id)


# ------------------------------------------------------------- git (A2.6)


def test_git_araclari_otomatik_modda_da_onay_ister(kayit, proje: Path) -> None:
    k, _ = kayit
    adlar = {s["function"]["name"] for s in k.semalar()}
    assert {"git_dal", "git_commit", "komut_girdi"} <= adlar
    sonuc = k.isleyiciler()["git_dal"](ad="deneme", yeni=True)
    assert sonuc["karar"] == "onay_bekliyor"


def test_planla_modunda_git_sunulmaz(tmp_path: Path, proje: Path) -> None:
    veri = tmp_path / "v2"
    veri.mkdir()
    alan = CalismaAlani(id="f" * 12, kokler=[str(proje)], mod=Mod.planla)
    k = AjanAracKaydi(alan, PolitikaMotoru(veri), CheckpointDeposu(veri), KomutServisi())
    assert "git_commit" not in {s["function"]["name"] for s in k.semalar()}


@pytest.mark.skipif(GIT is None, reason="git yok")
def test_dal_ve_yalniz_secili_dosya_commit(kayit, proje: Path) -> None:
    k, politika = kayit
    _git(proje, "init", "-q", "-b", "main")
    _git(proje, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(proje, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ilk")
    _git(proje, "config", "user.name", "t")
    _git(proje, "config", "user.email", "t@t")

    # gecersiz dal adi onaya bile gelmez
    assert "Gecersiz" in k.git_dal("-x")["hata"]
    assert "Gecersiz" in k.git_dal("a..b", yeni=True)["hata"]

    s = k.git_dal("ozellik", yeni=True)
    politika.onaylar.karar_ver(s["onay"]["id"], True)
    assert k.git_dal("ozellik", yeni=True)["dal"] == "ozellik"
    assert _git(proje, "branch", "--show-current") == "ozellik"

    # kullanicinin kendi degisikligi (b.txt) commit'e KARISMAMALI
    (proje / "a.txt").write_text("ajan\n", encoding="utf-8")
    (proje / "b.txt").write_text("kullanici\n", encoding="utf-8")
    (proje / "yeni.txt").write_text("y\n", encoding="utf-8")
    s = k.git_commit("ajan degisikligi", ["a.txt", "yeni.txt"])
    assert s["karar"] == "onay_bekliyor"

    # baska dosya listesiyle gelen istek ayni onayi KULLANAMAZ (islem hash'i)
    assert k.git_commit("ajan degisikligi", ["a.txt", "b.txt"])["karar"] == "onay_bekliyor"

    politika.onaylar.karar_ver(s["onay"]["id"], True)
    c = k.git_commit("ajan degisikligi", ["a.txt", "yeni.txt"])
    assert c["commit"] and set(c["dosyalar"]) == {
        str(proje / "a.txt"),
        str(proje / "yeni.txt"),
    }
    assert set(_git(proje, "show", "--name-only", "--format=", "HEAD").split()) == {
        "a.txt",
        "yeni.txt",
    }
    assert "b.txt" in _git(proje, "status", "--porcelain")  # kullanicinin degisikligi duruyor


def test_commit_dogrulamalari(kayit, tmp_path: Path) -> None:
    k, _ = kayit
    assert "bos olamaz" in k.git_commit("  ", ["a.txt"])["hata"]
    assert "tek tek" in k.git_commit("m", [])["hata"]
    disari = tmp_path / "disari.txt"
    disari.write_text("x", encoding="utf-8")
    assert k.git_commit("m", [str(disari)])["karar"] == "ret"


# ------------------------------------------------------------- hunk (A2.7)


def _degistir(k: AjanAracKaydi, proje: Path) -> str:
    h = dosya_hashi(proje / "a.txt")
    yeni = "BIR\niki\nuc\ndort\nBES\nalti\n"
    return k.yazma.dosya_yaz("a.txt", yeni, beklenen_hash=h)["checkpoint"]


def test_hunklar_ve_secili_blok_geri_alma(kayit, proje: Path) -> None:
    k, _ = kayit
    cp_id = _degistir(k, proje)
    cp: CheckpointDeposu = k.yazma.checkpointler
    yol = str(proje / "a.txt")
    bloklar = cp.hunklar(cp_id, yol)["hunklar"]
    assert len(bloklar) == 2 and bloklar[0]["eski"] == "bir\n" and bloklar[0]["yeni"] == "BIR\n"

    s = cp.hunk_geri_al(cp_id, yol, [1])  # yalniz sondaki blok
    assert s["kalan"] == 1
    assert (proje / "a.txt").read_text(encoding="utf-8") == "BIR\niki\nuc\ndort\nbes\n"

    # kalan blok da geri alinabilir; sonra tam geri alma da tutarli calisir
    assert len(cp.hunklar(cp_id, yol)["hunklar"]) == 1
    assert cp.geri_al(cp_id)["tamam"]
    assert (proje / "a.txt").read_text(encoding="utf-8") == "bir\niki\nuc\ndort\nbes\n"


def test_hunk_crlf_korunur(kayit, proje: Path) -> None:
    k, _ = kayit
    (proje / "a.txt").write_bytes(b"bir\r\niki\r\nuc\r\n")
    h = dosya_hashi(proje / "a.txt")
    cp_id = k.yazma.dosya_yaz("a.txt", "BIR\r\niki\r\nUC\r\n", beklenen_hash=h)["checkpoint"]
    cp = k.yazma.checkpointler
    cp.hunk_geri_al(cp_id, str(proje / "a.txt"), [0])
    assert (proje / "a.txt").read_bytes() == b"bir\r\niki\r\nUC\r\n"


def test_hunk_cakismada_dokunmaz_ve_gecersiz_numara(kayit, proje: Path) -> None:
    k, _ = kayit
    cp_id = _degistir(k, proje)
    cp = k.yazma.checkpointler
    yol = str(proje / "a.txt")
    with pytest.raises(UygulamaHatasi, match="Gecersiz blok"):
        cp.hunk_geri_al(cp_id, yol, [5])
    (proje / "a.txt").write_text("kullanici yazdi\n", encoding="utf-8")
    with pytest.raises(CakismaHatasi):
        cp.hunk_geri_al(cp_id, yol, [0])
    assert (proje / "a.txt").read_text(encoding="utf-8") == "kullanici yazdi\n"


def test_hunk_yalniz_degistirilen_dosyada(kayit, proje: Path) -> None:
    k, _ = kayit
    cp_id = k.yazma.dosya_yaz("yepyeni.txt", "x\n")["checkpoint"]
    with pytest.raises(UygulamaHatasi, match="yalniz degistirilen"):
        k.yazma.checkpointler.hunklar(cp_id, str(proje / "yepyeni.txt"))
