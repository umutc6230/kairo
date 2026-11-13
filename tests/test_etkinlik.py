"""Etkinlik (denetim) ucu ve onay kurallari ucu."""


async def test_etkinlik_ve_onay_kurallari_uclari(istemci) -> None:
    r = await istemci.get("/api/etkinlik?adet=10")
    assert r.status_code == 200 and isinstance(r.json()["etkinlik"], list)
    r = await istemci.get("/api/onay-kurallari")
    assert r.status_code == 200 and r.json()["kurallar"] == []
