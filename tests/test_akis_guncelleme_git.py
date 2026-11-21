"""Parametreli is akisi sablonlari, surum kontrolu ve kum disi git sertlestirmesi testleri."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app.agent import kum
from app.agent.akis import SablonDeposu, sablon_uygula
from app.agent.dosyalar import KokKapsami
from app.agent.git_araclari import GitAraclari
from app.exceptions import UygulamaHatasi
from app.services.guncelleme import GuncellemeDenetleyici, surum_demeti


def test_sablon_deposu_ve_uygula(tmp_path: Path) -> None:
    depo = SablonDeposu(tmp_path)
    idler = {s["id"] for s in depo.liste()}
    assert {"pr-incele-test", "hata-avcisi", "surum-hazirla"} <= idler

    with pytest.raises(UygulamaHatasi, match="Eksik sablon parametresi"):
        sablon_uygula(depo.getir("hata-avcisi"), {})

    akis = sablon_uygula(depo.getir("hata-avcisi"), {"hata": "KeyError x"})
    assert "KeyError x" in akis.adimlar[0].hedef
    assert akis.adimlar[1].komut == "pytest -q"

    kayit = depo.kaydet(
        {
            "id": "ozel-kontrol",
            "ad": "Ozel kontrol",
            "parametreler": ["hedef_dosya"],
            "adimlar": [{"id": "a1", "tur": "ajan", "hedef": "Incele {{hedef_dosya}}"}],
        }
    )
    assert kayit.yerlesik is False
    depo2 = SablonDeposu(tmp_path)
    assert depo2.getir("ozel-kontrol").ad == "Ozel kontrol"

    with pytest.raises(UygulamaHatasi, match="Yerlesik"):
        depo2.sil("pr-incele-test")

    depo2.sil("ozel-kontrol")
    assert all(s["id"] != "ozel-kontrol" for s in depo2.liste())


async def test_api_akis_sablonlari(app, istemci, tmp_path: Path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    p = (await istemci.post("/api/projeler", json={"yol": str(proje)})).json()["id"]
    await istemci.post(f"/api/projeler/{p}/etkin")

    liste = (await istemci.get("/api/akis-sablonlari")).json()["sablonlar"]
    assert any(s["id"] == "pr-incele-test" for s in liste)

    r_kayit = await istemci.post(
        "/api/akis-sablonlari",
        json={
            "id": "hizli-echo",
            "ad": "Hizli echo",
            "parametreler": ["mesaj"],
            "adimlar": [{"id": "yaz", "tur": "komut", "komut": "echo {{mesaj}}"}],
        },
    )
    assert r_kayit.status_code == 200 and r_kayit.json()["id"] == "hizli-echo"

    r_calistir = await istemci.post(
        "/api/akis-sablonlari/hizli-echo/calistir",
        json={"parametreler": {"mesaj": "selam"}},
    )
    assert r_calistir.status_code == 200
    assert r_calistir.json()["adimlar"][0]["komut"] == "echo selam"

    assert (await istemci.delete("/api/akis-sablonlari/pr-incele-test")).status_code >= 400
    assert (await istemci.delete("/api/akis-sablonlari/hizli-echo")).status_code == 200


async def test_guncelleme_denetleyici_ve_api(app, istemci, tmp_path: Path) -> None:
    assert surum_demeti("v0.2.1") > surum_demeti("0.1.0")
    assert surum_demeti("0.1.0") == surum_demeti("v0.1.0")

    cagri_sayisi = [0]
    durum_kodu = [200]
    yanit_govde: list[dict] = [
        {
            "tag_name": "v9.9.9",
            "html_url": "https://github.com/umutc6230/kairo/releases/tag/v9.9.9",
            "body": "Yeni ozellikler",
            "published_at": "2026-11-21T12:00:00Z",
        }
    ]

    def sahte_gh(_r: httpx.Request) -> httpx.Response:
        cagri_sayisi[0] += 1
        if durum_kodu[0] >= 400:
            return httpx.Response(durum_kodu[0], json={"message": "hata"})
        return httpx.Response(200, json=yanit_govde[0])

    d = GuncellemeDenetleyici(tmp_path, transport=httpx.MockTransport(sahte_gh))

    # Ag kapaliyken istek atmaz
    kapali = await d.kontrol(ag_acik=False)
    assert kapali["yeni_var"] is False and "Ag erisimi kapali" in kapali["not"]
    assert cagri_sayisi[0] == 0

    # Ilk kontrol yeni surumu bulur ve onbellege yazar
    s1 = await d.kontrol(ag_acik=True)
    assert s1["yeni_var"] is True and s1["son"] == "9.9.9" and cagri_sayisi[0] == 1

    # 24 saat icinde zorla=False onbellekten gelir
    s2 = await d.kontrol(zorla=False, ag_acik=True)
    assert s2["yeni_var"] is True and s2.get("onbellekten") is True and cagri_sayisi[0] == 1

    # Ag hatasinda cokmez, eski onbellek + uyari doner
    durum_kodu[0] = 500
    s_hata = await d.kontrol(zorla=True, ag_acik=True)
    assert s_hata["son"] == "9.9.9" and "basarisiz" in s_hata["uyari"]

    # 404 henuz release yok
    d404 = GuncellemeDenetleyici(
        tmp_path / "yeni", transport=httpx.MockTransport(lambda _: httpx.Response(404, json={}))
    )
    s404 = await d404.kontrol(ag_acik=True)
    assert s404["yeni_var"] is False and "yayinlanmis surum yok" in s404["not"]

    # API ucundan test
    app.state.guncelleme.transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "tag_name": "v2.0.0",
                "html_url": "https://github.com/umutc6230/kairo/releases/tag/v2.0.0",
                "body": "API testi",
            },
        )
    )
    api_r = await istemci.get("/api/guncelleme?zorla=true")
    assert api_r.status_code == 200 and api_r.json()["yeni_var"] is True
    assert api_r.json()["son"] == "2.0.0"


def test_kum_disi_git_sertlestirme(tmp_path: Path) -> None:
    ortam: dict = {}
    kum.git_komut_sertlestir(ortam)
    kum.git_komut_sertlestir(ortam)  # tekrar eklemez
    anahtarlar = {ortam[f"GIT_CONFIG_KEY_{i}"] for i in range(int(ortam["GIT_CONFIG_COUNT"]))}
    assert {
        "core.hooksPath",
        "core.fsmonitor",
        "core.pager",
        "core.sshCommand",
        "protocol.file.allow",
    } <= anahtarlar
    assert ortam["GIT_TERMINAL_PROMPT"] == "0"

    if shutil.which("git") is None:
        pytest.skip("git yok")

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    dosya = repo / "dosya.txt"
    dosya.write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "dosya.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "ilk"], check=True)
    dosya.write_text("v2\n", encoding="utf-8")

    iz = tmp_path / "calisti.txt"
    betik = tmp_path / "kotu.py"
    betik.write_text(f"open({str(iz)!r}, 'w').write('kacis')\n", encoding="utf-8")
    komut = f'"{sys.executable}" "{betik}"'
    subprocess.run(["git", "-C", str(repo), "config", "diff.external", komut], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", str(tmp_path)], check=True)

    git_arac = GitAraclari(KokKapsami([repo]))
    durum = git_arac.git_durum()
    diff = git_arac.git_diff()
    assert durum["repo"] is True and durum["degisen_sayisi"] == 1
    assert "+v2" in diff["diff"]
    assert not iz.exists()
