"""A12 kabul (yerel kisim): iki test cihaziyla eslesme / revoke / reconnect (token dondurme),
yetkisiz run/onay/dosya erisimi reddi, rate limit, denetim kaydi ve GERCEK TLS uzerinden erisim."""

from __future__ import annotations

import json
import socket

import httpx
import pytest

from app import uzak


class Saat:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
async def ortam(app, tmp_path):
    saat = Saat()
    depo = uzak.UzakDeposu(tmp_path, saat=saat)
    uapp = uzak.uzak_uygulamasi(depo, app.state.uzak_ic_cagri, "AB:CD")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=uapp),
                                 base_url="https://telefon.lan") as c:  # fmt: skip
        yield c, depo, saat


async def _esles(c, depo, rol, ad):
    kod = depo.kod_olustur(rol)["kod"]
    r = await c.post("/uzak/esles", json={"kod": kod, "cihaz": ad})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["cihaz_id"], kod


async def test_iki_cihaz_esles_revoke_reconnect(ortam) -> None:
    c, depo, saat = ortam
    a, a_id, kod = await _esles(c, depo, "izleyici", "telefon")
    b, b_id, _ = await _esles(c, depo, "operator", "tablet")
    # kod tek kullanimlik
    assert (await c.post("/uzak/esles", json={"kod": kod, "cihaz": "x"})).status_code == 401
    assert (await c.get("/uzak/api/gorevler", headers=a)).status_code == 200
    assert (await c.get("/uzak/api/gorevler", headers=b)).status_code == 200
    # revoke A: A reddedilir, B etkilenmez
    depo.iptal(a_id)
    r = await c.get("/uzak/api/gorevler", headers=a)
    assert r.status_code == 401 and "iptal" in r.json()["hata"]
    assert (await c.get("/uzak/api/gorevler", headers=b)).status_code == 200
    # reconnect: B tokenini dondurur; eski token gecersiz, yenisi gecerli
    y = (await c.post("/uzak/yenile", headers=b)).json()
    assert (await c.get("/uzak/ben", headers=b)).status_code == 401
    b2 = {"Authorization": "Bearer " + y["token"]}
    assert (await c.get("/uzak/ben", headers=b2)).json()["rol"] == "operator"
    # token suresi dolar -> yeniden eslesme gerekir
    saat.t += uzak.TOKEN_OMRU + 1
    assert (await c.get("/uzak/api/gorevler", headers=b2)).status_code == 401
    # kayitlarda token/ozet yok
    assert all("token_ozet" not in x for x in depo.liste())
    assert y["token"] not in depo.denetim_yolu.read_text(encoding="utf-8")
    assert b_id in {x["cihaz"] for x in depo.denetim()}


async def test_kod_suresi_ve_yanlis_kod_siniri(ortam) -> None:
    c, depo, saat = ortam
    kod = depo.kod_olustur("izleyici")["kod"]
    saat.t += uzak.KOD_OMRU + 1
    assert (await c.post("/uzak/esles", json={"kod": kod})).status_code == 401
    durumlar = [(await c.post("/uzak/esles", json={"kod": "YANLIS00"})).status_code
                for _ in range(6)]  # fmt: skip
    assert durumlar[-1] == 429  # kaba kuvvet IP basina sinirli


async def test_rol_ve_beyaz_liste(ortam, app) -> None:
    c, depo, _ = ortam
    izl, *_ = await _esles(c, depo, "izleyici", "izleyici")
    op, *_ = await _esles(c, depo, "operator", "op")
    # izleyici iptal/mesaj yapamaz; operator onay veremez
    assert (await c.post("/uzak/api/gorevler/abc123/iptal", headers=izl)).status_code == 403
    assert (await c.post("/uzak/api/gorevler/abc123/mesaj", headers=izl,
                         json={"metin": "x"})).status_code == 403  # fmt: skip
    r = await c.post("/uzak/api/onaylar/abc", headers=op, json={"onayla": True})
    assert r.status_code == 403
    # beyaz liste disi: dosya, ayar, proje, mod, gorev baslatma, tekrar, yol gezinme
    for metod, yol in [("GET", "/uzak/api/dosya?yol=C:/Windows/win.ini"),
                       ("POST", "/uzak/api/ayarlar"), ("POST", "/uzak/api/projeler/ac"),
                       ("POST", "/uzak/api/gorevler"), ("POST", "/uzak/api/gorevler/abc/tekrar"),
                       ("GET", "/uzak/api/gorevler/..%2F..%2Fapi%2Fayarlar"),
                       ("GET", "/uzak/api/checkpointler")]:  # fmt: skip
        r = await c.request(metod, yol, headers=op, json={})
        assert r.status_code == 404, (yol, r.status_code)
    # tokensiz hicbir sey
    assert (await c.get("/uzak/api/gorevler")).status_code == 401
    # yerel API uzak uygulamada yok
    assert (await c.get("/api/gorevler", headers=op)).status_code == 404
    # izinli islem ic API'ye gider: olmayan run -> ic API'nin hatasi
    r = await c.get("/uzak/api/gorevler/yokboyle1", headers=izl)
    assert r.status_code in (404, 400)


async def test_yerel_api_kod_ve_cihaz_yonetimi(istemci) -> None:
    r = await istemci.post("/api/uzak/kod", json={"rol": "onaylayici"})
    assert r.status_code == 200 and len(r.json()["kod"]) == 8
    assert (await istemci.post("/api/uzak/kod", json={"rol": "admin"})).status_code >= 400
    d = (await istemci.get("/api/uzak")).json()
    assert d["acik"] is False and len(d["parmak_izi"]) == 39  # varsayilan KAPALI


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_gercek_tls_sunucu(app, tmp_path) -> None:
    cert, key, parmak = uzak.sertifika(tmp_path / "tls")
    depo = uzak.UzakDeposu(tmp_path)
    sunucu = uzak.UzakSunucu()
    port = _bos_port()
    sunucu.ac(uzak.uzak_uygulamasi(depo, app.state.uzak_ic_cagri, parmak), port, cert, key,
              host="127.0.0.1")  # fmt: skip
    try:
        assert sunucu.acik_mi()
        kod = depo.kod_olustur("izleyici")["kod"]
        async with httpx.AsyncClient(verify=str(cert), base_url=f"https://127.0.0.1:{port}") as c:
            r = await c.post("/uzak/esles", json={"kod": kod, "cihaz": "tls-test"})
            assert r.status_code == 200
            h = {"Authorization": "Bearer " + r.json()["token"]}
            r = await c.get("/uzak/ben", headers=h)
            assert r.json()["parmak_izi"] == parmak and r.headers["cache-control"] == "no-store"
            assert "Eşleştir" in (await c.get("/uzak/")).text
        with pytest.raises(httpx.ConnectError):  # duz HTTP / dogrulanmamis sertifika yok
            async with httpx.AsyncClient() as c:
                await c.get(f"https://127.0.0.1:{port}/uzak/ben")
    finally:
        sunucu.kapat()
    assert json.loads(depo.denetim_yolu.read_text(encoding="utf-8").splitlines()[0])["sonuc"] == 200
