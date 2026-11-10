"""A10.1 LSP sozlesme testi: gercek stdio cerceveli test sunucusu; proje disi sonuc filtresi;
sunucu istegine cevap; cokme ve sunucusuz durumda kontrollu metin aramasi yedegi."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.agent.dosyalar import AjanDosyaAraclari, KokKapsami
from app.agent.lsp import KodZekasi

SUNUCU = Path(__file__).parent / "lsp_test_sunucusu.py"
KOD = (
    "class Hesap:\n    pass\n\n\ndef topla(a, b):\n    return a + b\n\n\n"
    "x = topla(1, 2)  # HATA\ny = topla(3, 4)\n"
)


@pytest.fixture
def ortam(tmp_path):
    (tmp_path / "a.py").write_text(KOD, encoding="utf-8")
    kapsam = KokKapsami([tmp_path])
    ara = AjanDosyaAraclari(kapsam)
    sunucular: dict[str, str] = {".py": f'"{sys.executable}" -I "{SUNUCU}"'}

    def arama(desen, dosya_deseni):
        return ara.icerik_ara(desen, "", dosya_deseni)

    z = KodZekasi(lambda: sunucular, kapsam, arama)
    yield z.isleyiciler(), sunucular, z
    z.kapat()


def test_tanim_referans_sembol_tani(ortam) -> None:
    isl, *_ = ortam
    t = isl["kod_tanim"](yol="a.py", satir=9, sutun=6)  # 'topla' kullanimi
    assert t["sonuclar"] == [{"dosya": "a.py", "satir": 5, "sutun": 5}]  # proje disi elendi
    r = isl["kod_referanslar"](yol="a.py", satir=5, sutun=6)["sonuclar"]
    assert [x["satir"] for x in r] == [5, 9, 10]
    s = isl["kod_semboller"](yol="a.py")["sonuclar"]
    assert [x["ad"] for x in s] == ["Hesap", "topla"]
    d = isl["kod_tanilar"](yol="a.py")["sonuclar"]
    assert d == [{"satir": 9, "mesaj": "HATA bulundu", "onem": 1}]
    assert "yedek" not in t


def test_sunucu_yoksa_metin_aramasi_yedegi(ortam) -> None:
    isl, sunucular, _ = ortam
    sunucular.clear()
    t = isl["kod_tanim"](yol="a.py", satir=9, sutun=6)
    assert t["yedek"] and "tanimli degil" in t["neden"]
    assert t["sonuclar"][0]["satir"] == 5 and "def topla" in t["sonuclar"][0]["metin"]


def test_coken_sunucuda_yedek_ve_yeniden_baslatma(ortam) -> None:
    isl, sunucular, _ = ortam
    sunucular[".py"] = f'"{sys.executable}" -I "{SUNUCU}" coz'
    t = isl["kod_referanslar"](yol="a.py", satir=5, sutun=6)
    assert t["yedek"] and "kullanilamadi" in t["neden"] and len(t["sonuclar"]) == 3
    sunucular[".py"] = f'"{sys.executable}" -I "{SUNUCU}"'
    assert "yedek" not in isl["kod_semboller"](yol="a.py")


def test_proje_disi_dosya_reddedilir(ortam, tmp_path) -> None:
    isl, *_ = ortam
    r = isl["kod_semboller"](yol=str(tmp_path.parent / "baska.py"))
    assert r.get("karar") == "ret" or "hata" in r
