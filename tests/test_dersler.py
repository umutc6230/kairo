"""Ders defteri: gorevler arasi hatalardan ogrenme (birim + gercek runner uzerinden)."""

from __future__ import annotations

import json

from test_a3_ajan import SahteModel, bitir, cagri, kur
from test_a3_ajan import proje as proje  # noqa: F401 - pytest fixture

from app.agent.dersler import SISTEM_SINIRI, DersDefteri, imza


def test_imza_degisken_kisimlari_atar():
    a = imza("dosya_oku", r"Bulunamadi: C:\proje\a.py satir 12")
    b = imza("dosya_oku", r"Bulunamadi: C:\baska\b.py satir 99")
    assert a == b and a != imza("komut", r"Bulunamadi: C:\proje\a.py satir 12")


def test_tekrar_sayilir_cozum_kaydedilir_ve_ilgili_secilir(tmp_path):
    d = DersDefteri(tmp_path)
    ilk = d.hata("read_media_file", r"Access denied: C:\x\a.png", "uygulamayi ac ve test et")
    assert ilk.sayi == 1
    ikinci = d.hata("read_media_file", r"Access denied: C:\y\b.png", "ekran goruntusunu oku")
    assert ikinci.sayi == 2 and ikinci.imza == ilk.imza
    d.cozuldu(ilk.imza, "proje klasoru icindeki yolu kullan")
    d.hata("baska_arac", "alakasiz hata", "veritabani yedegi")
    metin = d.ilgili("uygulamayi test et")
    assert "read_media_file" in metin and "proje klasoru icindeki" in metin
    assert "baska_arac" not in metin and len(metin) < SISTEM_SINIRI + 80
    assert d.ilgili("hicbir kelime eslesmez") == ""


def test_sirlar_maskelenir(tmp_path):
    d = DersDefteri(tmp_path).hata("x", "api_key=sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789")
    assert "abcdefghijklmnop" not in d.hata


async def test_runner_hatayi_yazar_cozumu_kaydeder_sonraki_gorevde_kullanir(tmp_path, proje):  # noqa: F811
    gorulen: list[str] = []

    def bitir_kanitla(no):
        return cagri("gorevi_bitir", ozet="okundu", kanit_adimlari=[no])

    model = SahteModel([
        cagri("proje_dosya_oku", yol="src/yok.py"),  # hata
        cagri("proje_dosya_oku", yol="src/hesap.py"),  # ayni arac basarili -> cozum
        bitir_kanitla(2),
    ])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)
    runner.dersler = defter = DersDefteri(tmp_path / "veri")
    run = await bitir(runner, (await runner.baslat("hesap dosyasini oku")).id)
    dersler = defter.liste()
    assert len(dersler) == 1 and dersler[0].arac == "proje_dosya_oku"
    assert "hesap.py" in dersler[0].cozum  # sonraki basarili cagri cozum oldu
    assert run.bekleyen_dersler == {}

    # ikinci gorev: ilgili ders sisteme girer; ayni hata tekrar olursa arac sonucunda ders var
    def kaydet(mesajlar):
        gorulen.append(json.dumps(mesajlar, ensure_ascii=False))
        return cagri("proje_dosya_oku", yol="src/yine_yok.py")

    model2 = SahteModel([kaydet, lambda m: gorulen.append(json.dumps(m, ensure_ascii=False))
                         or bitir_kanitla(1)])  # fmt: skip
    runner2, *_ = kur(tmp_path, proje, model2)
    runner2.dersler = defter
    run2 = await runner2.baslat("hesap dosyasini tekrar oku")
    assert "ONCEKI GOREVLERDEN DERSLER" in run2.ek_sistem and "hesap.py" in run2.ek_sistem
    await bitir(runner2, run2.id)
    assert "onceki_ders" in gorulen[-1]  # tekrar eden hata modele dersle dondu
    assert defter.liste()[0].sayi == 2
