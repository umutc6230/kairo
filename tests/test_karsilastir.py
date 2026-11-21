import json
from pathlib import Path

import pytest

from degerlendirme.karsilastir import KAT, esdegerlik_sonucu, rapor


def _ozet(genel=90, basari=100.0, kategori_basari=100.0):
    return {
        "kosu": genel,
        "basari_yuzde": basari,
        "kategori": {kategori: {"kosu": 1, "basari_yuzde": kategori_basari} for kategori in KAT},
    }


@pytest.mark.parametrize(
    ("yerel_basari", "cc_basari", "beklenen"),
    [
        (100.0, 100.0, True),
        (95.0, 100.0, True),
        (100.0, 95.0, True),
        (94.9, 100.0, False),
        (100.0, 94.9, False),
    ],
)
def test_esdegerlik_genel_fark_sinirini_iki_yonlu_uygular(yerel_basari, cc_basari, beklenen):
    yerel = _ozet(basari=yerel_basari)
    cc = _ozet(basari=cc_basari)

    sonuc, eksik, gerileyen = esdegerlik_sonucu(yerel, cc)

    assert sonuc is beklenen
    assert eksik == []
    assert gerileyen == []


def test_esdegerlik_tum_kategorileri_kritik_sayar():
    yerel, cc = _ozet(), _ozet()
    yerel["kategori"]["hata"]["basari_yuzde"] = 99.9

    sonuc, eksik, gerileyen = esdegerlik_sonucu(yerel, cc)

    assert sonuc is False
    assert eksik == []
    assert gerileyen == ["Hata duzeltme"]


def test_esdegerlik_eksik_kapsamda_belirsizdir_ve_gerileme_atfetmez():
    yerel, cc = _ozet(), _ozet()
    cc["kategori"]["test"] = {"kosu": 0, "basari_yuzde": 0.0}

    sonuc, eksik, gerileyen = esdegerlik_sonucu(yerel, cc)

    assert sonuc is None
    assert eksik == ["Test/build"]
    assert gerileyen == []


@pytest.mark.parametrize(
    ("yerel_kosu", "cc_kosu", "beklenen"),
    [(0, 90, ["genel"]), (90, 0, ["genel"])],
)
def test_esdegerlik_genel_olcum_yokken_belirsizdir(yerel_kosu, cc_kosu, beklenen):
    sonuc, eksik, gerileyen = esdegerlik_sonucu(_ozet(genel=yerel_kosu), _ozet(genel=cc_kosu))

    assert sonuc is None
    assert eksik == beklenen
    assert gerileyen == []


@pytest.mark.parametrize("eksik_taraf", ["yerel", "cc"])
def test_esdegerlik_her_iki_taraftaki_kategori_eksiginde_belirsizdir(eksik_taraf):
    yerel, cc = _ozet(), _ozet()
    hedef = yerel if eksik_taraf == "yerel" else cc
    hedef["kategori"]["test"] = {"kosu": 0, "basari_yuzde": 0.0}

    sonuc, eksik, gerileyen = esdegerlik_sonucu(yerel, cc)

    assert sonuc is None
    assert eksik == ["Test/build"]
    assert gerileyen == []


def test_tarihsel_girdiler_esdegerlik_raporu_uret() -> None:
    kok = Path(__file__).resolve().parents[1]
    yerel = json.loads(
        (
            kok
            / "degerlendirme/rapor-2026-11-18/kairo-x3-96f8a2a"
            / "rapor-20261118T180926Z.json"
        ).read_text(encoding="utf-8")
    )
    cc = json.loads(
        (
            kok / "degerlendirme/rapor-2026-11-18/cc" / "rapor-claude-code-20261118T131600Z.json"
        ).read_text(encoding="utf-8")
    )

    cikti = rapor([yerel], cc)

    assert "Genel fark **+0.0 puan**" in cikti
    assert "**SAGLANDI**" in cikti
    assert "BELIRSIZ" not in cikti
    assert (
        "Bu esik yalnizca bu benchmarkin raporlama kapisidir; "
        "genel urun esdegerligi iddiasi degildir."
    ) in cikti
