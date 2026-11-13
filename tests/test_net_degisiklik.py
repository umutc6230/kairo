from app.agent.runner import Adim, AdimDurum, net_degisiklikler


def _a(no, arac, yol):
    return Adim(no=no, arac=arac, argumanlar={"yol": yol}, durum=AdimDurum.tamam)


def test_gecici_dosya_yaz_sil_degisiklik_sayilmaz():
    adimlar = [
        _a(8, "proje_dosya_yaz", r"C:\Users\u\Desktop\_saglik.ps1"),
        Adim(no=9, arac="komut_calistir", durum=AdimDurum.tamam, cikis_kodu=0),
        _a(10, "proje_dosya_sil", "c:/users/u/desktop/_saglik.ps1"),
    ]
    assert net_degisiklikler(adimlar) == []


def test_kalici_degisiklik_sayilir():
    adimlar = [_a(1, "proje_dosya_yaz", "a.py"), _a(2, "proje_dosya_sil", "b.py")]
    assert [x.no for x in net_degisiklikler(adimlar)] == [1, 2]
