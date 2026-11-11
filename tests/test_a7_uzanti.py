"""A7.6 uzantilar: gercek ayri surec; komut, panel, olay, arac, yetki siniri, cokme, izolasyon."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.exceptions import OnayGerekli, UygulamaHatasi
from app.services.uzantilar import UzantiYoneticisi

ANA = r"""
import json, os, sys, time, pathlib
for satir in sys.stdin:
    m = json.loads(satir)
    t, v = m["tur"], m["veri"]
    if t == "komut":
        if v["arg"] == "coz":
            sys.exit(1)
        if v["arg"] == "bekle":
            time.sleep(60)
        sir = str(os.environ.get("GIZLI_TEST", "yok"))
        sonuc = {"metin": "Selam " + v["arg"] + " | sir=" + sir}
    elif t == "panel":
        sonuc = {"html": "<h1>Panel</h1><script>parent.x=1</script>"}
    elif t == "olay":
        pathlib.Path("olaylar.txt").open("a").write(v["olay"] + "\n")
        sonuc = {}
    elif t == "arac":
        sonuc = {"toplam": sum(v["argumanlar"].get("sayilar", []))}
    print(json.dumps({"id": m["id"], "sonuc": sonuc}), flush=True)
"""


def uzanti(kok: Path, yetenekler=("komut", "panel", "olay", "arac"), ad="ornek") -> Path:
    p = kok / f"kaynak-{ad}"
    p.mkdir(parents=True)
    (p / "ana.py").write_text(ANA, encoding="utf-8")
    (p / "uzanti.json").write_text(json.dumps({
        "name": ad, "version": "1.0.0", "description": "test", "yetenekler": list(yetenekler),
        "komutlar": ["selam"], "olaylar": ["run_bitis"],
        "araclar": [{"ad": "topla", "aciklama": "sayilari toplar"}],
    }), encoding="utf-8")  # fmt: skip
    return p


@pytest.fixture
def yon(tmp_path, monkeypatch):
    monkeypatch.setenv("GIZLI_TEST", "cok-gizli")  # uzantiya GITMEMELI
    y = UzantiYoneticisi(tmp_path / "veri")
    k = y.karantinaya_al(str(uzanti(tmp_path)))
    assert k["rapor"]["dosya_sayisi"] == 2
    assert y.liste() == []  # karantina kurulum degil
    y.kur(k["karantina"])
    yield y
    y.kapat()


def test_komut_ayri_surecte_ve_sir_gitmez(yon) -> None:
    r = yon.komut("selam", "Umut")
    assert r["metin"] == "Selam Umut | sir=yok" and r["uzanti"] == "ornek"
    assert yon.komut_listesi() == [{"komut": "selam", "uzanti": "ornek"}]
    with pytest.raises(Exception, match="acik uzanti yok"):
        yon.komut("olmayan", "")


def test_panel_ve_olay(yon, tmp_path) -> None:
    assert "<h1>Panel</h1>" in yon.panel("ornek")["html"]
    yon.olay("run_bitis", {"run": "x"})
    yon.olay("run_baslangic", {})  # ilan edilmedi: gonderilmez
    olaylar = (tmp_path / "veri" / "uzantilar" / "ornek" / "olaylar.txt").read_text()
    assert olaylar.split() == ["run_bitis"]


def test_arac_her_zaman_onay_ister(yon) -> None:
    def onay(ad, kw):
        raise OnayGerekli("dis kod", {"id": "o"})

    s, isl = yon.arac_semalari_ve_isleyiciler(onay)
    assert s[0]["function"]["name"] == "uzanti__ornek__topla"
    assert isl["uzanti__ornek__topla"](sayilar=[1, 2])["karar"] == "onay_bekliyor"
    _, isl = yon.arac_semalari_ve_isleyiciler(lambda ad, kw: None)
    assert '"toplam": 3' in isl["uzanti__ornek__topla"](sayilar=[1, 2])["sonuc"]


def test_cokme_ve_zaman_asimi_sonra_yeniden_baslar(yon, monkeypatch) -> None:
    with pytest.raises(UygulamaHatasi):
        yon.komut("selam", "coz")
    assert yon.komut("selam", "a")["metin"].startswith("Selam a")
    import app.services.uzantilar as u

    monkeypatch.setattr(u, "ZAMAN_ASIMI", 1)
    with pytest.raises(UygulamaHatasi, match="cevap vermedi"):
        yon.komut("selam", "bekle")
    assert yon.komut("selam", "b")["metin"].startswith("Selam b")


def test_ilan_edilmeyen_yetenek_ve_kapatinca_durur(tmp_path) -> None:
    y = UzantiYoneticisi(tmp_path / "veri")
    y.kur(y.karantinaya_al(str(uzanti(tmp_path, ("komut",))))["karantina"])
    with pytest.raises(UygulamaHatasi, match="ilan etmedi"):
        y.panel("ornek")
    assert y.arac_semalari_ve_isleyiciler(lambda *a: None) == ([], {})
    y.komut("selam", "x")
    s = y._surecler["ornek"].p
    y.ac_kapat("ornek", False)
    assert s.poll() is not None  # surec durdu
    with pytest.raises(Exception, match="acik uzanti yok"):
        y.komut("selam", "x")
    y.kaldir("ornek")
    assert y.liste() == []


def test_bozuk_manifest(tmp_path) -> None:
    p = uzanti(tmp_path)
    (p / "uzanti.json").write_text('{"name": "X", "version": "1"}', encoding="utf-8")
    with pytest.raises(UygulamaHatasi, match="gecersiz"):
        UzantiYoneticisi(tmp_path / "v").karantinaya_al(str(p))


async def test_api_uzanti(istemci, tmp_path) -> None:
    k = (await istemci.post("/api/uzantilar/karantina", json={"yol": str(uzanti(tmp_path))})).json()
    assert (
        await istemci.post("/api/uzantilar/kur", json={"ad": k["karantina"]})
    ).status_code == 200
    r = (await istemci.post("/api/uzantilar/komut", json={"komut": "selam", "arg": "API"})).json()
    assert r["metin"].startswith("Selam API")
    p = (await istemci.get("/api/uzantilar/ornek/panel")).json()
    assert "connect-src 'none'" in p["csp"]
    assert (await istemci.post("/api/uzantilar/kur", json={"ad": "../x"})).status_code == 404
