"""Superajan D3-D5: /kairo tetikleri, gozle modu, takip, teslim engeli, ETag ayrisimi."""

from __future__ import annotations

import pytest

from app.agent import superajan as sa
from app.agent.runner import TESLIM_KOMUTU


def _yorum(i, login, govde, no=7):
    return {"id": i, "user": {"login": login}, "body": govde,
            "issue_url": f"https://api.github.com/repos/u/r/issues/{no}",
            "html_url": f"https://github.com/u/r/issues/{no}#c{i}"}  # fmt: skip


def test_hitap_ve_adaylar():
    assert sa.hitap_metni("  \n/kairo  testleri ekle\nayrinti") == "testleri ekle\nayrinti"
    assert sa.hitap_metni("lutfen /kairo yap") is None
    yorumlar = [
        _yorum(1, "umut", "/kairo README duzelt"),
        _yorum(2, "yabanci", "/kairo hepsini sil"),  # izinli degil
        _yorum(3, "dependabot[bot]", "/kairo x"),  # bot
        _yorum(4, "umut", f"{sa.ISARET}\n/kairo kendi yorumu"),  # Kairo'nun kendisi
        _yorum(5, "umut", "normal yorum"),
    ]
    konular = [{"number": 9, "title": "Giris hatasi", "user": {"login": "Umut"},
                "body": "/kairo giris ekranini duzelt", "html_url": "u"}]  # fmt: skip
    a = sa.adaylar(yorumlar, konular, {"umut"}, gorulen={"c9"})
    assert [(x["anahtar"], x["no"], x["metin"]) for x in a] == [
        ("c1", 7, "README duzelt"), ("i9", 9, "giris ekranini duzelt")]  # fmt: skip
    assert sa.adaylar(yorumlar, [], {"umut"}, gorulen={"c1"}) == []
    g = sa.github_gorev("u/r", a[0])
    assert "DIS ISTEK VERISI" in g and "README duzelt" in g and "u/r#7" in g


def test_onay_bekliyor_asamasi():
    is_ = sa.IsEmri(baslik="x", gorev="y", proje_kok=".", onay_bekliyor=True)
    assert sa.asama(is_, None) == "onay_bekliyor" and "onay_bekliyor" in sa.INSAN_BEKLIYOR


def test_ayar_dogrulama():
    a = sa.GithubAyar(depo="u/r", izinli=[" @Umut ", ""]).dogrula()
    assert a.izinli == ["umut"]
    with pytest.raises(Exception, match="sahip/ad"):
        sa.GithubAyar(depo="kotu depo; rm").dogrula()


def test_gh_liste_etag_ve_304(monkeypatch):
    cikti = 'HTTP/2.0 200 OK\r\nEtag: W/"abc"\r\n\r\n[{"id": 1}]'
    monkeypatch.setattr(sa, "gh", lambda *a, **k: (0, cikti))
    assert sa.gh_liste("repos/u/r/issues") == (200, 'W/"abc"', [{"id": 1}])
    monkeypatch.setattr(sa, "gh", lambda *a, **k: (1, "HTTP/2.0 304 Not Modified\r\n\r\n"))
    assert sa.gh_liste("repos/u/r/issues", 'W/"abc"') == (304, 'W/"abc"', [])


def test_teslim_komutu_engeli():
    for k in ("git push origin is/x", "gh pr create", "GH issue comment 3", "gh api repos"):
        assert TESLIM_KOMUTU.search(k), k
    for k in ("git status", "git commit -m x", "pytest -q", "echo gh"):
        assert not TESLIM_KOMUTU.search(k), k


async def test_yoklama_gozle_takip_ve_yeniden_acma(istemci, app, tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.dogrula", lambda *a, **k: None)
    proje = tmp_path / "p"
    proje.mkdir()
    await istemci.post("/api/projeler", json={"yol": str(proje), "guven": "guvenilir"})
    await istemci.post("/api/superajan/git-baslat", json={})
    ayar = {"aktif": True, "depo": "u/r", "proje_kok": str(proje), "izinli": ["umut"],
            "mod": "gozle"}  # fmt: skip
    assert (await istemci.put("/api/superajan/github", json=ayar)).json()["izinli"] == ["umut"]
    akis = {"yorumlar": [_yorum(1, "umut", "/kairo README yaz")]}
    monkeypatch.setattr(sa, "gh_liste", lambda yol, etag="": (
        200, "e", akis["yorumlar"] if "comments" in yol else []))  # fmt: skip
    assert (await istemci.post("/api/superajan/yokla")).json()["acilan"] == 1
    isler = (await istemci.get("/api/superajan")).json()["isler"]
    assert isler[0]["asama"] == "onay_bekliyor" and isler[0]["konular"] == ["u/r#7"]
    assert (await istemci.post("/api/superajan/yokla")).json()["acilan"] == 0  # gorulen
    # D5: ayni konuya yeni /kairo yorumu -> yeni is emri degil, takip
    depo = app.state.superajan
    is_ = depo.getir(isler[0]["id"])
    is_.durum = "bitti"
    depo.guncelle(is_)
    akis["yorumlar"] = [_yorum(2, "umut", "/kairo testleri de ekle")]
    s = (await istemci.post("/api/superajan/yokla")).json()
    assert (s.get("acilan"), s.get("takip")) == (0, 1), s
    is_ = depo.getir(isler[0]["id"])
    assert is_.durum == "acik" and is_.bekleyen_mesaj == "testleri de ekle" and is_.onay_bekliyor
    r = (await istemci.post(f"/api/superajan/isler/{is_.id}/baslat")).json()
    assert r["asama"] != "onay_bekliyor"


async def test_teslim_push_pr_ve_yorum(istemci, app, tmp_path, monkeypatch):
    import subprocess

    from app.agent import worktree as wt

    uzak = tmp_path / "uzak.git"
    subprocess.run(["git", "init", "-q", "--bare", str(uzak)], check=True)
    proje = tmp_path / "p"
    proje.mkdir()
    (proje / "a.txt").write_text("1\n", encoding="utf-8")
    wt.git_baslat(proje)
    subprocess.run(["git", "-C", str(proje), "remote", "add", "origin", str(uzak)], check=True)
    yol, dal = wt.olustur(proje, tmp_path / "wt", "abc123", "is")
    (yol / "a.txt").write_text("2\n", encoding="utf-8")
    depo = app.state.superajan
    is_ = depo.olustur("README", "x", str(proje), "github", konular=["u/r#7"])
    is_.calisma_koku, is_.dal = str(yol), dal
    depo.guncelle(is_)
    cagrilar = []

    def sahte_gh(*arg, **_):
        cagrilar.append(arg)
        return (0, "https://github.com/u/r/pull/5\n") if arg[:2] == ("pr", "create") else (0, "")

    monkeypatch.setattr(sa, "gh", sahte_gh)
    r = (await istemci.post(f"/api/superajan/isler/{is_.id}/teslim")).json()
    assert r["pr_url"] == "https://github.com/u/r/pull/5" and r["is"]["pr_url"] == r["pr_url"]
    dallar = subprocess.run(["git", "-C", str(uzak), "branch"], capture_output=True, text=True)
    assert dal in dallar.stdout  # gercekten push edildi
    yorum = next(a for a in cagrilar if a[:2] == ("issue", "comment"))
    assert yorum[2] == "7" and sa.ISARET in yorum[-1]
    pr = next(a for a in cagrilar if a[:2] == ("pr", "create"))
    assert sa.ISARET in pr[pr.index("--body") + 1]
    tekrar = (await istemci.post(f"/api/superajan/isler/{is_.id}/teslim")).json()
    assert tekrar["durum"] == "zaten"


async def test_thread_sorusu_ozette_secenekli(istemci, app, tmp_path) -> None:
    from app.agent.runner import Adim, AdimDurum, Run, RunDurum

    proje = tmp_path / "s"
    proje.mkdir()
    depo, runlar = app.state.superajan, app.state.ajan_runner.depo
    run = Run(hedef="x", durum=RunDurum.cevap_bekliyor)
    arg = {"soru": "Hangi veritabani?", "secenekler": ["SQLite", "Postgres"]}
    run.adimlar = [Adim(no=1, arac="soru_sor", durum=AdimDurum.cevap_bekliyor, argumanlar=arg)]
    runlar.kaydet(run)
    is_ = depo.olustur("DB", "x", str(proje))
    is_.runlar = [run.id]
    depo.guncelle(is_)
    x = next(i for i in (await istemci.get("/api/superajan")).json()["isler"] if i["id"] == is_.id)
    assert x["asama"] == "insan_bekliyor"
    assert x["soru"] == {"metin": "Hangi veritabani?", "secenekler": ["SQLite", "Postgres"]}
