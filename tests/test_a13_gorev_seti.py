"""A13 gorev setinin kendisinin dogrulanmasi: her gorevde gizli kontrol
- baslangic fixture'inda KALMALI (gorev gercekten bir is istiyor),
- referans cozumle GECMELI (gorev cozulebilir, kontrol dogru),
- korunan (gorunur test) dosyasi degistirilirse KALMALI (test degistirerek basari yok)."""

from __future__ import annotations

import shutil

import pytest

from app.degerlendir import _yaz, gizli_kontrol, gorevleri_yukle, kur

SURUM, GOREVLER = gorevleri_yukle()


def _gerekli(g: dict) -> str | None:
    if g["dil"] == "csharp" and not shutil.which("dotnet"):
        return "dotnet yok"
    if g["dil"] in ("typescript", "javascript") and not shutil.which("node"):
        return "node yok"
    return None


def test_dagilim() -> None:
    from collections import Counter

    c = Counter(g["kategori"] for g in GOREVLER)
    assert dict(c) == {"hata": 6, "ozellik": 5, "test": 4, "kesif": 4, "uzun": 4,
                       "toparlanma": 4, "entegrasyon": 3}  # fmt: skip
    assert {g["dil"] for g in GOREVLER} >= {"python", "typescript", "csharp"}


@pytest.mark.parametrize("g", GOREVLER, ids=[g["id"] for g in GOREVLER])
def test_gorev_basta_kalir_cozumle_gecer(g, tmp_path) -> None:
    if neden := _gerekli(g):
        pytest.skip(neden)
    proje = tmp_path / "p"
    korunan = kur(g, proje)
    bas = gizli_kontrol(g, proje, korunan)
    assert not bas["basari"], "gorev baslangicta zaten geciyor"
    korunan = kur(g, proje)
    _yaz(proje, g["cozum"])
    son = gizli_kontrol(g, proje, korunan)
    assert son["basari"], son["neden"]


def test_korunan_test_degistirilirse_kalir(tmp_path) -> None:
    g = next(x for x in GOREVLER if x["id"] == "hata-py-median")
    korunan = kur(g, tmp_path / "p")
    _yaz(tmp_path / "p", g["cozum"])
    _yaz(tmp_path / "p", {"tests/test_stats.py": "def test_x():\n    pass\n"})
    r = gizli_kontrol(g, tmp_path / "p", korunan)
    assert not r["basari"] and "korunan" in r["neden"]
