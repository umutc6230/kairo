"""Superajan (is emirleri, D1): asama tablosu, git hazirlama, API akisi ve eszamanlilik."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.agent import superajan as sa
from app.agent import worktree as wt
from app.agent.runner import Run, RunDurum, Sonuc


def _is(**kw) -> sa.IsEmri:
    return sa.IsEmri(baslik="x", gorev="y", proje_kok=".", **kw)


@pytest.mark.parametrize(("is_kw", "durum", "ozet", "beklenen"), [
    ({}, None, "", "sirada"),
    ({"runlar": ["r"]}, "calisiyor", "", "calisiyor"),
    ({"runlar": ["r"]}, "onay_bekliyor", "", "insan_bekliyor"),
    ({"runlar": ["r"]}, "cevap_bekliyor", "", "insan_bekliyor"),
    ({"runlar": ["r"]}, "basarili", "bitti", "inceleme"),
    ({"runlar": ["r"]}, "basarili", "IS_YOK\nyapilacak yok", "yapilacak_yok"),
    ({"runlar": ["r"]}, "dogrulanmadi", "", "taslak"),
    ({"runlar": ["r"]}, "basarisiz", "", "basarisiz"),
    ({"runlar": ["r"]}, "iptal", "", "basarisiz"),
    ({"runlar": ["r"], "bekleyen_mesaj": "devam"}, "basarili", "", "sirada"),
    ({"runlar": ["r"], "durum": "durduruldu"}, "calisiyor", "", "durduruldu"),
    ({"runlar": ["r"], "durum": "bitti"}, "basarili", "", "bitti"),
])  # fmt: skip
def test_asama_tablosu(is_kw, durum, ozet, beklenen):
    assert sa.asama(_is(**is_kw), durum, ozet) == beklenen


def test_gorev_metni_veri_zarfi_ve_kurallar():
    m = sa.gorev_metni(_is(), takip="testleri de ekle")
    assert "<gorev>" in m and "<takip>" in m and "git push" in m and sa.IS_YOK in m


def test_git_baslat_bos_klasoru_hazirlar(tmp_path):
    (tmp_path / "a.txt").write_text("merhaba", encoding="utf-8")
    assert not wt.git_mi(tmp_path)
    assert wt.git_baslat(tmp_path) == {"durum": "olusturuldu"}
    assert wt.git_mi(tmp_path)
    assert wt.git_baslat(tmp_path) == {"durum": "zaten_git"}
    dosyalar = subprocess.run(["git", "ls-files"], cwd=tmp_path, capture_output=True, text=True)
    assert "a.txt" in dosyalar.stdout


async def test_api_akisi_git_yok_olustur_eszamanlilik_durdur_at(istemci, app, tmp_path,
                                                                monkeypatch):  # fmt: skip
    monkeypatch.setattr("app.api.dogrula", lambda *a, **k: None)
    proje = tmp_path / "uygulama"
    proje.mkdir()
    (proje / "main.py").write_text("print(1)\n", encoding="utf-8")
    await istemci.post("/api/projeler", json={"yol": str(proje), "guven": "guvenilir"})
    r = await istemci.post("/api/superajan/isler", json={"gorev": "hesap makinesi yap"})
    assert r.status_code >= 400 and "GIT_YOK" in r.text  # once kullanici onayi
    assert (await istemci.post("/api/superajan/git-baslat", json={})).json()[
        "durum"
    ] == "olusturuldu"

    baslatilan: list[str] = []
    runner, depo = app.state.ajan_runner, app.state.ajan_runner.depo

    async def sahte_baslat(hedef, kabul, butce=None, izole_kur=None, **_):
        run = Run(hedef=hedef, durum=RunDurum.calisiyor)
        if izole_kur:
            run.calisma_koku, run.dal = izole_kur(run.id)
        depo.kaydet(run)
        baslatilan.append(run.id)
        return run

    monkeypatch.setattr(runner, "baslat", sahte_baslat)
    idler = []
    for i in range(3):
        o = (await istemci.post("/api/superajan/isler", json={"gorev": f"is {i}"})).json()
        idler.append(o["id"])
    liste = {x["id"]: x for x in (await istemci.get("/api/superajan")).json()["isler"]}
    assert [liste[i]["asama"] for i in idler] == ["calisiyor", "calisiyor", "sirada"]  # en fazla 2
    assert (
        liste[idler[0]]["dal"].startswith("is/") and Path(liste[idler[0]]["calisma_koku"]).is_dir()
    )

    # ilk is bitti (inceleme) -> sira bosaldi, ucuncusu baslar
    r0 = depo.getir(baslatilan[0])
    r0.durum, r0.sonuc = RunDurum.basarili, Sonuc(ozet="tamam", dogrulandi=True)
    depo.kaydet(r0)
    await app.state.superajan_tick()
    liste = {x["id"]: x for x in (await istemci.get("/api/superajan")).json()["isler"]}
    assert liste[idler[0]]["asama"] == "inceleme" and liste[idler[2]]["asama"] == "calisiyor"
    assert (await istemci.get("/api/superajan")).json()["insan_bekliyor"] == 1

    # durdur kalicidir; at ise worktree'yi siler, ana agaca dokunmaz
    d = (await istemci.post(f"/api/superajan/isler/{idler[1]}/durdur")).json()
    assert d["asama"] == "durduruldu"
    yol = Path(liste[idler[0]]["calisma_koku"])
    a = (await istemci.post(f"/api/superajan/isler/{idler[0]}/at")).json()
    assert a["asama"] == "bitti" and not yol.exists() and (proje / "main.py").exists()
    assert (await istemci.delete(f"/api/superajan/isler/{idler[0]}")).json() == {
        "silindi": idler[0]
    }


async def test_sohbet_thread_araclari(istemci, app, tmp_path):
    from app.services.sohbet_araclari import is_emri_isleyicileri

    ac, listele = app.state.sohbet.is_emirleri
    isl = is_emri_isleyicileri(ac, listele)
    assert (
        "Once bir proje ac"
        in isl["is_emri_baslat"](isler=[{"baslik": "a", "gorev": "b"}])["hatalar"][0]
    )
    proje = tmp_path / "p"
    proje.mkdir()
    await istemci.post("/api/projeler", json={"yol": str(proje), "guven": "guvenilir"})
    await istemci.post("/api/superajan/git-baslat", json={})
    r = isl["is_emri_baslat"](isler=[{"baslik": "Bir", "gorev": "x"}, {"baslik": "", "gorev": "y"}])
    assert [t["baslik"] for t in r["threadler"]] == ["Bir", "y"]
    assert all(t["asama"] == "sirada" for t in r["threadler"])
    assert isl["is_emri_baslat"]()["hata"]
    durum = isl["is_emirleri_durum"]()["threadler"]
    assert {t["baslik"] for t in durum} == {"Bir", "y"}
