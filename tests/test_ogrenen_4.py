"""Ogrenen sistem 4: izleyici hata yogunlugu ve dolasmada aralikli yon notu verir."""

from __future__ import annotations

from app.agent.runner import IZLE_ARALIK, Adim, AdimDurum, AgentRunner, Run


def _a(no, arac="komut", durum=AdimDurum.tamam, **arg):
    return Adim(no=no, arac=arac, argumanlar=arg or {"n": no}, durum=durum)


def test_hata_yogunlugunda_yon_ve_aralik():
    run = Run(hedef="x")
    run.adimlar = [_a(i, durum=AdimDurum.hata if i % 4 else AdimDurum.tamam) for i in range(8)]
    yon = AgentRunner._izleyici(run)
    assert "basarisiz" in yon and "FARKLI" in yon
    assert AgentRunner._izleyici(run) == ""  # ayni pencerede tekrar not yok
    run.adimlar += [_a(100 + i, durum=AdimDurum.hata) for i in range(IZLE_ARALIK)]
    assert "basarisiz" in AgentRunner._izleyici(run)


def test_dolasma_ve_saglikli_gorev():
    run = Run(hedef="x")
    run.adimlar = [_a(i, "oku", yol=f"{i % 3}.py") for i in range(12)]
    assert "donup duruyorsun" in AgentRunner._izleyici(run)
    saglikli = Run(hedef="x")
    saglikli.adimlar = [_a(i, "oku", yol=f"{i}.py") for i in range(20)]
    assert AgentRunner._izleyici(saglikli) == ""
    az = Run(hedef="x")
    az.adimlar = [_a(i, durum=AdimDurum.hata) for i in range(4)]
    assert AgentRunner._izleyici(az) == ""
