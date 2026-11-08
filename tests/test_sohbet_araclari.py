"""Sohbet araclari: salt okunur dosya araclari, gizli dosya korumasi, yol cozumleme."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.services import sohbet_araclari as sa


@pytest.fixture
def masa(tmp_path, monkeypatch) -> Path:
    m = tmp_path / "Masaustu"
    (m / "Alt" / "Derin").mkdir(parents=True)
    (m / "rapor.txt").write_text("a" * (sa.MAX_OKUMA_KARAKTER + 10), encoding="utf-8")
    (m / "Alt" / "rapor_eski.md").write_text("eski", encoding="utf-8")
    (m / ".gizli").write_text("x", encoding="utf-8")
    (m / "desktop.ini").write_text("x", encoding="utf-8")
    (m / "resim.png").write_bytes(b"\x89PNG\x00\x00binary")
    (m / ".env").write_text("SIR=1", encoding="utf-8")
    monkeypatch.setattr(sa, "bilinen_klasor", lambda ad: m)
    return m


def test_klasor_listele(masa):
    s = sa.klasor_listele("masaüstü")
    assert s["klasor"] == str(masa) and s["klasor_sayisi"] == 1 and s["dosya_sayisi"] == 2
    assert s["ogeler"][0] == "[klasor] Alt" and any(
        o.startswith("rapor.txt (") for o in s["ogeler"]
    )
    assert sa.klasor_listele("masaustu", gizlileri_goster=True)["dosya_sayisi"] == 5
    assert sa.sonuc_ozeti("klasor_listele", s) == "1 klasor, 2 dosya"
    assert "bulunamadi" in sa.klasor_listele(str(masa / "yok"))["hata"]
    assert "gizli" in sa.klasor_listele(str(masa / ".ssh"))["hata"]


def test_klasor_listele_cok_oge(masa, monkeypatch):
    monkeypatch.setattr(sa, "MAX_OGE", 2)
    s = sa.klasor_listele("masaustu")
    assert len(s["ogeler"]) == 2 and "Ilk 2" in s["not"]


def test_dosya_oku_ve_korumalar(masa):
    s = sa.dosya_oku("masaustu/rapor.txt")
    assert len(s["icerik"]) == sa.MAX_OKUMA_KARAKTER and "baslangic=" in s["devam"]
    assert (
        sa.dosya_oku(str(masa / "rapor.txt"), baslangic=sa.MAX_OKUMA_KARAKTER)["icerik"] == "a" * 10
    )
    assert "metin dosyasi degil" in sa.dosya_oku(str(masa / "resim.png"))["hata"]
    assert "gizli bilgi" in sa.dosya_oku(str(masa / ".env"))["hata"]
    assert "bulunamadi" in sa.dosya_oku(str(masa / "yok.txt"))["hata"]
    assert sa.sonuc_ozeti("dosya_oku", sa.dosya_oku(str(masa / "Alt" / "rapor_eski.md"))) == (
        "4 karakter okundu"
    )


def test_dosya_oku_buyuk_dosya(masa, monkeypatch):
    monkeypatch.setattr(sa, "MAX_DOSYA_BAYT", 3)
    assert "5 MB" in sa.dosya_oku(str(masa / "rapor.txt"))["hata"]


def test_dosya_ara(masa):
    s = sa.dosya_ara("RAPOR")
    assert sorted(s["bulunan"]) == [
        "Alt\\rapor_eski.md" if sys.platform == "win32" else "Alt/rapor_eski.md",
        "rapor.txt",
    ]
    assert sa.dosya_ara("derin")["bulunan"] == ["[klasor] " + str(Path("Alt") / "Derin")]
    assert sa.dosya_ara("rapor", derinlik=1)["sayi"] == 1
    assert "erisilemez" in sa.dosya_ara("x", klasor=str(masa / "yok"))["hata"]
    assert sa.sonuc_ozeti("dosya_ara", s) == "2 sonuc"


@pytest.mark.parametrize(
    "yol",
    [
        "C:/Users/a/.ssh/id_rsa",
        "C:/Users/a/proje/.env.local",
        "C:/x/sunucu.pem",
        "C:/x/AppData/Local/Google/Chrome/User Data/Default/Login Data",
        "C:/x/parolalarim.kdbx",
        "C:/x/aws_credentials.txt",
    ],
)
def test_gizli_dosyalar_okunmaz(yol):
    assert sa.gizli_mi(Path(yol))


def test_normal_dosya_gizli_degil():
    assert not sa.gizli_mi(Path("C:/Users/a/Desktop/rapor.txt"))


def test_yol_coz(monkeypatch, tmp_path):
    monkeypatch.setattr(sa, "bilinen_klasor", lambda ad: tmp_path / ad)
    assert sa.yol_coz("Desktop") == tmp_path / "masaustu"
    assert sa.yol_coz(None) == tmp_path / "masaustu"
    assert sa.yol_coz("indirilenler") == tmp_path / "indirilenler"
    assert sa.yol_coz("masaustu/Projeler") == tmp_path / "masaustu" / "Projeler"
    assert sa.yol_coz("belgeler\\Notlar") == tmp_path / "belgeler" / "Notlar"
    assert sa.yol_coz("C:/Temp") == Path("C:/Temp")
    assert sa.yol_coz("goreli/x") == Path.home() / "goreli/x"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Known Folder")
def test_bilinen_klasor_gercek_masaustu():
    assert sa.bilinen_klasor("masaustu").exists()


def test_bilinen_klasor_yedek(monkeypatch):
    monkeypatch.setattr(sa.sys, "platform", "linux")
    assert sa.bilinen_klasor("belgeler") == Path.home() / "Documents"


def test_arac_listesi_ve_ozet():
    adlar = [a["function"]["name"] for a in sa.ARACLAR]
    assert adlar == [
        "klasor_listele",
        "dosya_oku",
        "dosya_ara",
        "hesapla",
        "saat_kac",
        "birim_cevir",
    ]
    assert set(adlar) == set(sa.ISLEYICILER)
    assert sa.sonuc_ozeti("x", {"hata": "bozuk"}) == "hata: bozuk"
    assert sa.sonuc_ozeti("hesapla", {"ifade": "1+1", "sonuc": 2}) == "ifade: 1+1, sonuc: 2"
    assert sa.sonuc_ozeti("x", "duz") == "duz"
