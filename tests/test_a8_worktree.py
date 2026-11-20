"""A8.3 izole worktree: gercek git deposu ile entegrasyon kurallari."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent import worktree as wt

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git yok")


def g(kok: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=kok, capture_output=True, text=True,
                          check=True).stdout.strip()  # fmt: skip


def _oku(p: Path) -> str:  # git autocrlf satir sonunu degistirebilir
    return p.read_bytes().decode().strip()


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    (r / "a.txt").write_bytes(b"bir\n")
    g(r, "init", "-q", "-b", "main")
    g(r, "config", "user.name", "t")
    g(r, "config", "user.email", "t@t")
    g(r, "add", ".")
    g(r, "commit", "-qm", "ilk")
    return r


def test_izole_degisiklik_testle_birlesir(repo, tmp_path) -> None:
    yol, dal = wt.olustur(repo, tmp_path / "wt", "abc123abc123")
    (yol / "a.txt").write_bytes(b"iki\n")
    assert (repo / "a.txt").read_bytes() == b"bir\n"  # ana agac etkilenmedi
    kotu = wt.entegre_et(repo, yol, dal, "ajan", f'"{sys.executable}" -c "raise SystemExit(1)"')
    assert kotu["durum"] == "test_basarisiz" and (repo / "a.txt").read_bytes() == b"bir\n"
    s = wt.entegre_et(repo, yol, dal, "ajan", f'"{sys.executable}" -c "print(1)"')
    assert s["durum"] == "birlestirildi" and _oku(repo / "a.txt") == "iki"
    assert not yol.exists() and dal not in g(repo, "branch")


def test_kullanici_degisikligi_korunur(repo, tmp_path) -> None:
    yol, dal = wt.olustur(repo, tmp_path / "wt", "def456def456")
    (yol / "a.txt").write_bytes(b"ajan\n")
    (repo / "a.txt").write_bytes(b"kullanici\n")  # commit edilmemis kullanici isi
    s = wt.entegre_et(repo, yol, dal, "ajan")
    assert s["durum"] == "kullanici_degisikligi_var"
    assert (repo / "a.txt").read_bytes() == b"kullanici\n"


def test_catisma_sessiz_cozulmez_ve_geri_alinir(repo, tmp_path) -> None:
    yol, dal = wt.olustur(repo, tmp_path / "wt", "aaa111aaa111")
    (yol / "a.txt").write_bytes(b"ajan\n")
    (repo / "a.txt").write_bytes(b"kullanici\n")
    g(repo, "commit", "-qam", "kullanici")  # ayni satir ana dalda degisti
    s = wt.entegre_et(repo, yol, dal, "ajan")
    assert s["durum"] == "catisma" and s["catisan"] == ["a.txt"]
    assert _oku(repo / "a.txt") == "kullanici"  # merge geri alindi
    assert not g(repo, "status", "--porcelain")  # yarim merge kalmadi
    assert yol.exists() and wt.at(repo, yol, dal)["durum"] == "atildi"


def test_git_olmayan_proje(tmp_path) -> None:
    with pytest.raises(Exception, match="git deposu"):
        wt.olustur(tmp_path, tmp_path / "wt", "bbb222bbb222")


async def test_api_izole_gorev(istemci, repo, tmp_path) -> None:
    await istemci.post("/api/projeler", json={"yol": str(repo), "guven": "guvenilir"})
    r = await istemci.post("/api/gorevler/" + "0" * 12 + "/entegre", json={})
    assert r.status_code == 404

@pytest.mark.parametrize("islem, sonuc", [("entegre", "birlestirildi"), ("at", "atildi")])
async def test_worktree_kapanisi_ve_ayni_sohbette_sonraki_gorev(
    app, istemci, repo, tmp_path, monkeypatch, islem, sonuc
) -> None:
    from app.agent.runner import Run, RunDurum, Sonuc

    proje = (await istemci.post("/api/projeler", json={"yol": str(repo)})).json()
    assert (await istemci.post(f"/api/projeler/{proje['id']}/etkin")).status_code == 200
    runner = app.state.ajan_runner
    run = Run(hedef="Ilk gorev", durum=RunDurum.basarili, sonuc=Sonuc(ozet="Ilk sonuc"))
    yol, dal = wt.olustur(repo, tmp_path / "wt", run.id)
    (yol / "a.txt").write_bytes(b"degisiklik\n")
    run.calisma_koku, run.dal = str(yol), dal
    runner.depo.kaydet(run)

    endpoint = f"/api/gorevler/{run.id}"
    assert (await istemci.get(endpoint)).json()["worktree_durumu"] == "acik"
    r = await istemci.post(f"{endpoint}/{islem}", json={})
    assert r.status_code == 200 and r.json()["durum"] == sonuc
    assert not yol.exists()
    assert (await istemci.get(endpoint)).json()["worktree_durumu"] == sonuc
    assert (await istemci.post(f"{endpoint}/{islem}", json={})).json()["durum"] == sonuc

    run.worktree_durumu = ""  # worktree kapandiginda durum alani olmayan eski kayit
    runner.depo.kaydet(run)
    assert (await istemci.get(endpoint)).json()["worktree_durumu"] == "kapali"

    async def model_kullanmadan_bitir(_run_id):
        pass

    monkeypatch.setattr(runner, "_dongu", model_kullanmadan_bitir)
    yeni = await istemci.post(
        "/api/gorevler", json={"hedef": "Ikinci mesaj", "onceki": run.id, "izole": True}
    )
    assert yeni.status_code == 200, yeni.text
    assert yeni.json()["onceki"] == run.id
    assert yeni.json()["worktree_durumu"] == "acik"

async def test_alt_ajan_bagimsiz_worktree_skill_ve_merge(app, istemci, repo, skill_klasoru) -> None:
    from app.agent.runner import Run, RunDurum

    skill = skill_klasoru / "alt-rapor"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: alt-rapor\ndescription: Rapor becerisi\n---\nBELIRGIN_RAPOR_TALIMATI",
        encoding="utf-8",
    )
    p = (await istemci.post("/api/projeler", json={"yol": str(repo)})).json()
    await istemci.post(f"/api/projeler/{p['id']}/etkin")
    runner = app.state.ajan_runner
    lider = Run(hedef="incele", proje_id=p["id"])
    alt = Run(
        hedef="rapor", proje_id=lider.proje_id, parent=lider.id,
        bagimsiz_worktree=True, profil_skilleri=["alt-rapor"], profil_mcp=[],
        durum=RunDurum.basarili,
    )
    alt.calisma_koku, alt.dal = runner.alt_worktree_kur(lider, alt.id)
    yol = Path(alt.calisma_koku)
    assert yol != repo and alt.dal.startswith("alt-ajan/")
    sistem, _, araclar = await runner.gorev_baglami(alt)
    assert "BELIRGIN_RAPOR_TALIMATI" in sistem
    assert not any(ad.startswith("mcp__") for ad in araclar)
    (yol / "a.txt").write_text("alt ajan")
    assert _oku(repo / "a.txt") == "bir"
    runner.depo.kaydet(alt)
    sonuc = await istemci.post(f"/api/gorevler/{alt.id}/entegre", json={})
    assert sonuc.status_code == 200 and sonuc.json()["durum"] == "birlestirildi"
    assert _oku(repo / "a.txt") == "alt ajan"
