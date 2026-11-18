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


def test_numarali_dosya_kopyalarinda_yon():
    # canli: ajan her denemede _unpack1.py ... _unpack43.py yazdi; ilerleme sayaci yakalamadi
    run = Run(hedef="x")
    adimlar = []
    for i in range(1, 6):
        adimlar += [_a(2 * i, "proje_dosya_yaz", yol=f"C:\cikti\_unpack{i}.py", icerik="x"),
                    _a(2 * i + 1, "komut", komut=f"python _unpack{i}.py")]  # fmt: skip
    run.adimlar = adimlar
    yon = AgentRunner._izleyici(run)
    assert "_unpack#.py" in yon and "TEK dosyayi" in yon
    # yeni kopya yoksa ayni not tekrar gelmez (canli: eski 51 kopya yuzunden her 6 adimda geldi)
    run.adimlar += [_a(100 + i, "komut", komut=f"x{i}") for i in range(IZLE_ARALIK)]
    assert "_unpack#" not in AgentRunner._izleyici(run)
    farkli = Run(hedef="x")  # farkli adli dosyalar kopya sayilmaz
    farkli.adimlar = [_a(i, "proje_dosya_yaz", yol=f"{ad}.py") for i, ad in enumerate("abcdef")]
    assert AgentRunner._izleyici(farkli) == ""
