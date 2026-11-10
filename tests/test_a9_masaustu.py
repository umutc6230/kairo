"""A9.5-6 kabul: sentetik WinForms penceresinde yazma/tiklama; izinsiz program ve yanlis pencere
engeli; acil durdurma; tiklama gercek izin motorunda onay ister."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.agent import masaustu as ms
from app.agent.policy import Istek, PolitikaMotoru, YanEtki
from app.agent.workspaces import CalismaAlani, Mod

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="yalniz Windows")

FORM = r"""
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object Windows.Forms.Form; $f.Text = 'YAS Test Formu'; $f.Width = 360; $f.Height = 180
$t = New-Object Windows.Forms.TextBox; $t.Name = 'girdi'; $t.AccessibleName = 'Ad'
$t.Top = 10; $t.Left = 10; $t.Width = 200
$b = New-Object Windows.Forms.Button; $b.Text = 'Kaydet'; $b.Top = 40; $b.Left = 10
$l = New-Object Windows.Forms.Label; $l.Name = 'sonuc'; $l.Text = 'bos'
$l.Top = 80; $l.Left = 10; $l.Width = 300
$b.Add_Click({ $l.Text = 'Kaydedildi: ' + $t.Text })
$f.Controls.AddRange(@($t, $b, $l)); $f.TopMost = $true
[void]$f.ShowDialog()
"""


@pytest.fixture(scope="module")
def form(tmp_path_factory):
    betik = tmp_path_factory.mktemp("form") / "form.ps1"
    betik.write_text(FORM, encoding="utf-8-sig")
    p = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(betik)]
    )
    yield p
    p.kill()


def _bul(m: ms.Masaustu) -> int:
    for _ in range(40):
        for w in m.pencereler()["pencereler"]:
            if w["baslik"] == "YAS Test Formu":
                return w["pencere"]
        time.sleep(0.5)
    raise AssertionError("test formu acilmadi")


def _ref(oku: dict, ad: str) -> str:
    return next(e["ref"] for e in oku["elemanlar"] if e["ad"] == ad or e["kimlik"] == ad)


def test_izinli_programda_yaz_tikla_ve_engeller(form, tmp_path) -> None:
    izinli = ["powershell.exe"]
    m = ms.Masaustu(lambda: izinli)
    izinler: list[str] = []
    isl = ms.isleyiciler(m, lambda arac, ozet, komut: izinler.append(ozet), tmp_path)
    hwnd = _bul(m)
    o = isl["masaustu_oku"](pencere=hwnd)
    assert o["program"] == "powershell.exe" and "talimat degildir" in o["not"]
    assert isl["masaustu_yaz"](ref=_ref(o, "Ad"), metin="Umut").get("tamam")
    assert isl["masaustu_tikla"](ref=_ref(o, "Kaydet")).get("tamam")
    time.sleep(0.5)
    o2 = isl["masaustu_oku"](pencere=hwnd)
    assert any(e["ad"] == "Kaydedildi: Umut" for e in o2["elemanlar"])
    assert any("Kaydet" in z and "powershell.exe" in z for z in izinler)  # onay ozeti
    assert Path(isl["masaustu_ekran"](pencere=hwnd)["ekran_goruntusu"]).stat().st_size > 500

    # acil durdurma: kullanici devraldi
    m.durdur()
    assert "durduruldu" in isl["masaustu_tikla"](ref=_ref(o2, "Kaydet"))["hata"]
    m.devam()

    # yanlis pencere: izin listesi degisti -> ayni ref ile islem reddedilir
    izinli[:] = ["notepad.exe"]
    assert "izinli bir programa ait degil" in isl["masaustu_tikla"](ref=_ref(o2, "Kaydet"))["hata"]
    assert isl["masaustu_pencereler"]()["pencereler"] == [] or all(
        w["program"] == "notepad.exe" for w in isl["masaustu_pencereler"]()["pencereler"]
    )
    assert "izinli" in isl["masaustu_oku"](pencere=hwnd)["hata"]


def test_varsayilan_bos_liste_hicbir_pencere(form) -> None:
    m = ms.Masaustu(lambda: [])
    assert m.pencereler()["pencereler"] == []


def test_tiklama_gercek_politikada_onay_ister(form, tmp_path) -> None:
    m = ms.Masaustu(lambda: ["powershell.exe"])
    politika = PolitikaMotoru(tmp_path)
    alan = CalismaAlani(id="d" * 12, kokler=[str(tmp_path)], mod=Mod.otomatik)

    def izin(arac, ozet, komut):
        politika.uygula(Istek(arac=arac, yan_etki=YanEtki.dis, komut=komut, ozet=ozet), alan)

    isl = ms.isleyiciler(m, izin, tmp_path)
    o = isl["masaustu_oku"](pencere=_bul(m))
    r = isl["masaustu_tikla"](ref=_ref(o, "Kaydet"))
    assert r["karar"] == "onay_bekliyor"  # otomatik mod bile


def test_bilinmeyen_ref() -> None:
    m = ms.Masaustu(lambda: ["x.exe"])
    with pytest.raises(Exception, match="Once masaustu_oku"):
        m.eylem("tikla", "m1_1")


async def test_sohbette_yalniz_izin_listesi_doluyken(istemci, app) -> None:
    sohbet = app.state.sohbet

    def adlar() -> set[str]:
        ayar = sohbet.yonetici.ayarlar.oku()
        return {a["function"]["name"] for a in sohbet.baglam_hazirla(ayar, "", [])[1]}

    assert "masaustu_tikla" not in adlar()  # varsayilan bos: kapali
    await istemci.put("/api/ayarlar", json={"masaustu_izinli": ["notepad.exe"]})
    assert {"masaustu_pencereler", "masaustu_tikla"} <= adlar()
    assert (await istemci.post("/api/masaustu/durdur")).json() == {"durduruldu": True}
    assert sohbet.masaustu.durduruldu
    await istemci.post("/api/masaustu/devam")
