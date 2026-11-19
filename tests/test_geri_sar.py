"""Claude Code rewind karsiligi: konusmayi secilen kullanici mesajina geri sarma."""

from __future__ import annotations

from app.services.oturumlar import Mesaj, OturumDeposu


async def test_mesajdan_ve_ajan_turundan_geri_sarma(veri, istemci) -> None:
    depo = OturumDeposu(veri)
    o = depo.olustur()
    o.mesajlar = [
        Mesaj(rol="kullanici", metin="ilk"), Mesaj(rol="asistan", metin="cevap 1"),
        Mesaj(rol="kullanici", metin="ikinci"), Mesaj(rol="asistan", metin="cevap 2"),
    ]  # fmt: skip
    o.ajan_runlari = [{"run": "r1", "metin": "gorev 1"}, {"run": "r2", "metin": "gorev 2"}]
    depo.kaydet(o)
    hedef = o.mesajlar[2].id

    r = await istemci.post(f"/api/oturumlar/{o.id}/geri-sar", json={"mesaj_id": hedef})
    assert r.status_code == 200 and r.json()["metin"] == "ikinci"
    assert [m.metin for m in depo.getir(o.id).mesajlar] == ["ilk", "cevap 1"]

    r = await istemci.post(f"/api/oturumlar/{o.id}/geri-sar", json={"run": "r2"})
    assert r.json()["metin"] == "gorev 2"
    assert depo.getir(o.id).ajan_runlari == [{"run": "r1", "metin": "gorev 1"}]

    asistan = depo.getir(o.id).mesajlar[1].id  # yalniz kullanici mesajindan geri sarilir
    for govde in ({"mesaj_id": asistan}, {"mesaj_id": "yok"}, {"run": "yok"}, {}):
        r = await istemci.post(f"/api/oturumlar/{o.id}/geri-sar", json=govde)
        assert r.status_code >= 400, govde


async def test_mesajdan_dallanma_ve_sabitleme(veri, istemci) -> None:
    depo = OturumDeposu(veri)
    o = depo.olustur()
    o.mesajlar = [
        Mesaj(rol="kullanici", metin="a"),
        Mesaj(rol="asistan", metin="b"),
        Mesaj(rol="kullanici", metin="c"),
    ]
    depo.kaydet(o)

    r = await istemci.post(f"/api/oturumlar/{o.id}/catal", json={"mesaj_id": o.mesajlar[1].id})
    assert r.status_code == 200 and [m["metin"] for m in r.json()["mesajlar"]] == ["a", "b"]
    assert len(depo.getir(o.id).mesajlar) == 3  # asil degismez
    r = await istemci.post(f"/api/oturumlar/{o.id}/catal")  # govdesiz: tum gecmis
    assert len(r.json()["mesajlar"]) == 3

    yol = f"/api/oturumlar/{o.id}/mesajlar/{o.mesajlar[1].id}/sabitle"
    assert (await istemci.post(yol)).json()["sabit"] is True
    assert depo.getir(o.id).mesajlar[1].sabit is True
    assert (await istemci.post(yol)).json()["sabit"] is False
    assert (await istemci.post(f"/api/oturumlar/{o.id}/mesajlar/yok/sabitle")).status_code == 404
