"""Ogrenen sistem C: kanitli hafiza (dayanak), yargilar, revizyon, ilgiye gore secim."""

from __future__ import annotations

import pytest

from app.exceptions import UygulamaHatasi
from app.services.hafiza import MAX_SISTEM_KARAKTER, HafizaDeposu


def test_dayanak_bozulunca_not_eskir(tmp_path):
    f = tmp_path / "ayar.py"
    f.write_text("PORT = 8765\n", encoding="utf-8")
    h = HafizaDeposu(tmp_path)
    h.ekle("Uzak erisim portu 8765", kapsam="p", dayanak=[f"{f}::PORT = 8765"])
    assert "8765" in h.sistem_metni("p")
    f.write_text("PORT = 9000\n", encoding="utf-8")
    assert h.sistem_metni("p") == ""  # kod degisti: bayat not sisteme girmez


def test_yargi_ve_revizyon(tmp_path):
    h = HafizaDeposu(tmp_path)
    k = h.ekle("Testler unittest ile", kapsam="p")
    h.yargila(k["id"], "yanlis")
    assert "unittest" in h.sistem_metni("p")  # tek yanlis yargisi yetmez
    h.yargila(k["id"], "yanlis")
    assert h.sistem_metni("p") == ""
    y = h.yargila(k["id"], "yanlis", duzeltme="Testler pytest -q ile")
    assert y["revizyon"] == 2 and y["yanlis"] == 0 and "pytest" in h.sistem_metni("p")
    with pytest.raises(UygulamaHatasi):
        h.yargila(k["id"], "harika")


def test_ilgiye_gore_en_iyi_alti_ve_sinir(tmp_path):
    h = HafizaDeposu(tmp_path)
    for i in range(10):
        h.ekle(f"Genel bilgi numara {i} " + "x" * 60, kapsam="p")
    h.ekle("Veritabani postgres 16 kullaniyor", kapsam="p")
    metin = h.sistem_metni("p", "postgres baglantisi neden kopuyor")
    assert metin.splitlines()[1].endswith("Veritabani postgres 16 kullaniyor")
    assert len(metin) <= MAX_SISTEM_KARAKTER + 200 and len(metin.splitlines()) <= 7
