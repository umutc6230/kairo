"""Notebook (.ipynb) duzenleme ve GitHub (gh CLI) araclari."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent import superajan
from app.agent.araclar import AjanAracKaydi
from app.agent.checkpoints import CheckpointDeposu
from app.agent.policy import PolitikaMotoru
from app.agent.terminal import KomutServisi
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.exceptions import OnayGerekli, UygulamaHatasi

NB = {
    "cells": [
        {"cell_type": "markdown", "metadata": {}, "source": ["# Baslik\n"]},
        {
            "cell_type": "code",
            "metadata": {"etiket": 1},
            "source": ["print(1)\n"],
            "outputs": [{"output_type": "stream", "name": "stdout", "text": ["1\n"]}],
            "execution_count": 3,
        },
    ],
    "metadata": {},
    "nbformat": 4,
    "nbformat_minor": 5,
}


@pytest.fixture
def kayit(tmp_path: Path):
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "analiz.ipynb").write_text(json.dumps(NB), encoding="utf-8")
    (proje / "notlar.txt").write_text("x", encoding="utf-8")
    veri = tmp_path / "veri"
    veri.mkdir()
    alan = CalismaAlani(id="n" * 12, kokler=[str(proje)], guven=Guven.guvenilir, mod=Mod.otomatik)
    cp = CheckpointDeposu(veri)
    politika = PolitikaMotoru(veri)
    politika.kullanici_ag = lambda: True
    return AjanAracKaydi(alan, politika, cp, KomutServisi()), proje, cp


def test_notebook_oku_degistir_ekle_sil_ve_geri_al(kayit) -> None:
    k, proje, cp = kayit
    h = k.isleyiciler()
    oku = h["notebook_oku"](yol="analiz.ipynb")
    assert oku["hucre_sayisi"] == 2 and oku["hucreler"][1]["cikti_sayisi"] == 1
    d = h["notebook_duzenle"](
        yol="analiz.ipynb", islem="degistir", hucre_no=1, kaynak="print(2)\n",
        beklenen_hash=oku["hash"],
    )  # fmt: skip
    nb = json.loads((proje / "analiz.ipynb").read_text(encoding="utf-8"))
    hucre = nb["cells"][1]
    assert hucre["source"] == ["print(2)\n"] and hucre["outputs"] == []  # bayat cikti silinir
    assert hucre["execution_count"] is None and hucre["metadata"] == {"etiket": 1}
    once = (proje / "analiz.ipynb").read_text(encoding="utf-8")
    e = h["notebook_duzenle"](
        yol="analiz.ipynb", islem="ekle", kaynak="x = 1", tur="code", beklenen_hash=d["yeni_hash"]
    )
    s = h["notebook_duzenle"](
        yol="analiz.ipynb", islem="sil", hucre_no=0, beklenen_hash=e["yeni_hash"]
    )
    assert "hata" not in s
    nb = json.loads((proje / "analiz.ipynb").read_text(encoding="utf-8"))
    assert [c["cell_type"] for c in nb["cells"]] == ["code", "code"] and "id" in nb["cells"][1]
    cp.geri_al(s["checkpoint"])  # son degisiklik (silme) geri alinabilir
    cp.geri_al(e["checkpoint"])
    assert (proje / "analiz.ipynb").read_text(encoding="utf-8") == once
    # hash vermeden yazim reddedilir (bayat icerige yazma korumasi dosya araclariyla ayni)
    assert "hata" in h["notebook_duzenle"](yol="analiz.ipynb", islem="sil", hucre_no=0)


def test_notebook_hatalari(kayit) -> None:
    k, *_ = kayit
    h = k.isleyiciler()
    hatali = [
        dict(yol="analiz.ipynb", islem="sil", hucre_no=9),
        dict(yol="analiz.ipynb", islem="ekle", hucre_no=-1),
        dict(yol="analiz.ipynb", islem="boz"),
        dict(yol="notlar.txt", islem="sil", hucre_no=0),
    ]
    for arg in hatali:
        sonuc = h["notebook_duzenle"](**arg)
        assert "hata" in sonuc, arg


def _sahte_gh(monkeypatch, cagrilar: list, auth_kod: int = 0) -> None:
    def gh(*arg, cwd=None, sure=60):
        cagrilar.append(arg)
        if arg[:2] == ("auth", "status"):
            return auth_kod, "giris yok" if auth_kod else "ok"
        if arg[:2] == ("issue", "view"):
            yorum = {"author": {"login": "a"}, "body": "y"}
            v = {"title": "Hata", "body": "g", "state": "OPEN", "comments": [yorum]}
            return 0, json.dumps(v)
        return 0, "https://github.com/o/r/pull/7\n"

    monkeypatch.setattr(superajan, "gh", gh)


def test_issue_okuma_salt_okumadir(monkeypatch, kayit) -> None:
    k, *_ = kayit
    cagrilar: list = []
    _sahte_gh(monkeypatch, cagrilar)
    s = k.isleyiciler()["github_issue_oku"](numara=5)
    assert s["baslik"] == "Hata" and s["yorumlar"][0]["yazar"] == "a"
    assert ("issue", "view", "5", "--json", "title,body,state,comments") in cagrilar


def test_pr_olusturma_ve_yorum_tam_yetkide_de_onay_ister(monkeypatch, kayit) -> None:
    k, *_ = kayit
    cagrilar: list = []
    _sahte_gh(monkeypatch, cagrilar)
    with pytest.raises(OnayGerekli):
        k.github.pr_olustur(baslik="Ozellik", govde="aciklama")
    with pytest.raises(OnayGerekli):
        k.github.pr_yorum(numara=7, metin="tesekkurler")
    assert not any(a[:2] in (("pr", "create"), ("pr", "comment")) for a in cagrilar)


def test_gh_girisi_yoksa_turkce_hata(monkeypatch, kayit) -> None:
    k, *_ = kayit
    _sahte_gh(monkeypatch, [], auth_kod=1)
    with pytest.raises(UygulamaHatasi, match="gh auth login"):
        k.github.issue_oku(numara=1)


def _alt_projeli(tmp_path: Path, guven: Guven) -> AjanAracKaydi:
    proje = tmp_path / f"p-{guven}"
    (proje / "paket" / "ic").mkdir(parents=True)
    (proje / "AGENTS.md").write_text("KOK KURALI", encoding="utf-8")
    (proje / "paket" / "AGENTS.md").write_text("PAKET KURALI", encoding="utf-8")
    (proje / "paket" / "ic" / "CLAUDE.md").write_text("IC KURALI", encoding="utf-8")
    (proje / "paket" / "ic" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (proje / "paket" / "ic" / "b.py").write_text("y = 2\n", encoding="utf-8")
    veri = tmp_path / f"v-{guven}"
    veri.mkdir()
    alan = CalismaAlani(id="t" * 12, kokler=[str(proje)], guven=guven, mod=Mod.otomatik)
    return AjanAracKaydi(alan, PolitikaMotoru(veri), CheckpointDeposu(veri), KomutServisi())


def test_alt_klasor_talimati_bir_kez_ve_yalniz_guvenilir_projede(tmp_path: Path) -> None:
    oku = _alt_projeli(tmp_path, Guven.guvenilir).isleyiciler()["proje_dosya_oku"]
    ilk = oku(yol="paket/ic/a.py")["alt_klasor_talimati"]
    assert "PAKET KURALI" in ilk and "IC KURALI" in ilk and "KOK KURALI" not in ilk
    assert ilk.index("PAKET") < ilk.index("IC KURALI")  # ustteki klasor once
    assert "yetki VEREMEZ" in ilk
    assert "alt_klasor_talimati" not in oku(yol="paket/ic/b.py")  # gorevde bir kez
    guvensiz = _alt_projeli(tmp_path, Guven.sinirli).isleyiciler()["proje_dosya_oku"]
    assert "alt_klasor_talimati" not in guvensiz(yol="paket/ic/a.py")
