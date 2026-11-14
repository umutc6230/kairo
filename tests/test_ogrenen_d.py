"""Ogrenen sistem D: gorev sonu otomatik inceleme; ciddi bulgu ders defterine girer."""

from __future__ import annotations

from app.agent.dersler import DersDefteri
from app.agent.runner import Adim, AdimDurum, AgentRunner, Run, RunDeposu, RunDurum


def _runner(tmp_path, inceleyici):
    r = AgentRunner.__new__(AgentRunner)
    r.depo, r.dersler, r.inceleyici, r._incelemeler = (
        RunDeposu(tmp_path),
        DersDefteri(tmp_path),
        inceleyici,
        set(),
    )
    return r


async def test_yazan_gorev_incelenir_ve_ders_olur(tmp_path):
    async def incele(run):
        return {"ozet": "1 sorun", "bulgular": [
            {"onem": "yuksek", "baslik": "Bos liste", "neden": "IndexError olur"},
            {"onem": "dusuk", "baslik": "Ad", "neden": "stil"}]}  # fmt: skip

    r = _runner(tmp_path, incele)
    run = Run(hedef="hesap makinesi", durum=RunDurum.basarili)
    run.adimlar = [Adim(no=1, arac="proje_dosya_yaz", durum=AdimDurum.tamam, dosya="a.py")]
    r.depo.kaydet(run)
    assert r._incelenmeli(run)
    await r._incele(run.id)
    assert r.depo.getir(run.id).inceleme["ozet"] == "1 sorun"
    dersler = r.dersler.liste()
    assert len(dersler) == 1 and "Bos liste" in dersler[0].hata and dersler[0].arac == "inceleme"


def test_okuyan_ya_da_basarisiz_gorev_incelenmez(tmp_path):
    r = _runner(tmp_path, lambda run: None)
    run = Run(hedef="x", durum=RunDurum.basarili)
    run.adimlar = [Adim(no=1, arac="proje_dosya_oku", durum=AdimDurum.tamam)]
    assert not r._incelenmeli(run)
    run.adimlar = [Adim(no=1, arac="proje_dosya_yaz", durum=AdimDurum.tamam)]
    run.durum = RunDurum.basarisiz
    assert not r._incelenmeli(run)
    r.inceleyici = None
    run.durum = RunDurum.basarili
    assert not r._incelenmeli(run)


async def test_inceleme_hatasi_gorevi_bozmaz(tmp_path):
    async def bozuk(run):
        raise RuntimeError("model yok")

    r = _runner(tmp_path, bozuk)
    run = Run(hedef="x", durum=RunDurum.basarili)
    r.depo.kaydet(run)
    await r._incele(run.id)
    assert r.depo.getir(run.id).inceleme == {}
