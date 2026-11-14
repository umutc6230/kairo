"""Mods karsiligi: arac_cagrisi kancasi, istem yeniden yazma, UI yuzeyleri, dosya degisince
yeniden yukleme ve "Kairo mod yazsin" (yalniz karantina). Gercek ayri surec."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from app.services.sohbet import uzanti_kancali
from app.services.uzantilar import UzantiYoneticisi

ANA = r"""
import json, sys
SURUM = "v1"
for satir in sys.stdin:
    m = json.loads(satir)
    t, v = m["tur"], m["veri"]
    sonuc = {}
    if t == "olay" and v["olay"] == "arac_cagrisi":
        a = v["veri"]
        if a["arac"] == "komut_calistir" and "rm -rf" in a["argumanlar"].get("komut", ""):
            sonuc = {"karar": "engelle", "neden": "tehlikeli komut"}
        elif a["arac"] == "saat_kac":
            sonuc = {"cevap": "uzanti saati 12:00"}
        elif a["arac"] == "web_ara":
            sonuc = {"argumanlar": {"sorgu": a["argumanlar"]["sorgu"] + " site:docs.python.org"}}
    elif t == "olay" and v["olay"] == "istem":
        sonuc = {"metin": v["veri"]["metin"] + " (kisa cevap ver)"}
    elif t == "ui":
        sonuc = {"durum": "mod " + SURUM, "bildirim": "merhaba",
                 "bant": {"md": "**Not**", "dugmeler": [{"metin": "Tamam", "komut": "tamam"}]}}
    print(json.dumps({"id": m["id"], "sonuc": sonuc}), flush=True)
"""

MANIFEST = {
    "name": "kanca", "version": "1.0.0", "description": "Mods testi",
    "yetenekler": ["olay", "ui"], "olaylar": ["arac_cagrisi", "istem", "tur_bitis"],
}  # fmt: skip


@pytest.fixture
def yon(tmp_path):
    y = UzantiYoneticisi(tmp_path / "veri")
    k = y.taslak_yaz(MANIFEST, ANA)  # "Kairo mod yazsin": yalniz karantinaya
    assert y.liste() == [] and k["karantina"] == "kanca"
    y.kur("kanca")
    yield y
    y.kapat()


def test_arac_kancasi_engelle_cevapla_arguman_degistir(yon) -> None:
    calisan: list = []

    def gercek(ad):
        return lambda **kw: calisan.append((ad, kw)) or {"tamam": True}

    isl = uzanti_kancali(yon, {a: gercek(a) for a in ("komut_calistir", "saat_kac", "web_ara")})
    r = isl["komut_calistir"](komut="rm -rf /")
    assert r["karar"] == "ret" and "tehlikeli" in r["hata"]
    assert isl["saat_kac"]()["sonuc"] == "uzanti saati 12:00"
    assert isl["web_ara"](sorgu="asyncio") == {"tamam": True}
    assert isl["komut_calistir"](komut="pytest -q") == {"tamam": True}
    assert calisan == [("web_ara", {"sorgu": "asyncio site:docs.python.org"}),
                       ("komut_calistir", {"komut": "pytest -q"})]  # fmt: skip


def test_istem_ve_ui_yuzeyleri(yon) -> None:
    assert yon.dinleyen_var("istem") and not yon.dinleyen_var("run_bitis")
    assert yon.istem_kancasi("README yaz") == "README yaz (kisa cevap ver)"
    ui = yon.ui()
    assert ui[0]["durum"] == "mod v1" and ui[0]["bildirim"] == "merhaba"
    assert ui[0]["bant"]["dugmeler"] == [{"metin": "Tamam", "komut": "tamam"}]
    assert yon.ui()[0]["bildirim"] == ""  # ayni bildirim tekrar toast olmaz


def test_dosya_degisince_yeniden_yuklenir(yon) -> None:
    assert yon.ui()[0]["durum"] == "mod v1"
    ana = yon.kok / "kanca" / "ana.py"
    ana.write_text(ANA.replace('"v1"', '"v2"'), encoding="utf-8")
    ileri = time.time() + 5  # mtime cozunurlugu: degisim kesin gorulsun
    os.utime(ana, (ileri, ileri))
    assert yon.ui()[0]["durum"] == "mod v2"


def test_taslak_gecersiz_manifest_reddedilir(tmp_path) -> None:
    y = UzantiYoneticisi(tmp_path / "v")
    with pytest.raises(ValueError):
        y.taslak_yaz({"name": "Kotu Ad", "version": "1", "description": "x"}, "print(1)")
    assert not any(p.name.startswith("taslak-") for p in y.karantina.iterdir())


def test_coken_kanca_cagriyi_engellemez(tmp_path) -> None:
    y = UzantiYoneticisi(tmp_path / "v")
    y.taslak_yaz(MANIFEST, "import sys\nsys.exit(1)\n")
    y.kur("kanca")
    try:
        isl = uzanti_kancali(y, {"x": lambda **kw: {"ok": kw}})
        assert isl["x"](a=1) == {"ok": {"a": 1}}
        assert y.istem_kancasi("selam") == "selam"
    finally:
        y.kapat()


def test_git_karantina_yalniz_https(tmp_path) -> None:
    y = UzantiYoneticisi(tmp_path / "v")
    for kotu in ("file:///C:/x", "git@github.com:a/b", "https://x.com/a;rm"):
        with pytest.raises(Exception, match="https"):
            y.git_karantina(kotu)
    assert json.loads(json.dumps(MANIFEST))["name"] == "kanca" and Path(y.karantina).is_dir()
