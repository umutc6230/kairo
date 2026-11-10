"""A11 kabul: sahte saatle aralik/gunluk, DST, ayni tetiklemenin tekrari, restart, overlap,
kacirilan tetikleme ve basarisiz gorev retry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agent.zamanlayici import Zamanlayici, sonraki

T0 = datetime(2026, 3, 20, 8, 0, tzinfo=UTC)


def _z(tmp_path, **ek):
    zl = Zamanlayici(tmp_path)
    veri = {"ad": "test", "hedef": "testleri calistir", "proje_kok": str(tmp_path), "tur": "aralik",
            "aralik_dk": 60} | ek  # fmt: skip
    return zl, zl.ekle(veri, simdi=T0)


def calistir(zl, simdi, durumlar):
    tetikler = zl.tick(simdi, lambda rid: durumlar.get(rid, "calisiyor"))
    for i, t in enumerate(tetikler):
        rid = f"r{simdi.timestamp():.0f}-{i}-{t.deneme}"
        durumlar[rid] = "calisiyor"
        zl.baslatildi(t, rid)
    return tetikler


def test_aralik_ve_idempotent_restart(tmp_path) -> None:
    zl, z = _z(tmp_path)
    d: dict = {}
    assert calistir(zl, T0 + timedelta(minutes=30), d) == []
    assert len(calistir(zl, T0 + timedelta(minutes=60), d)) == 1
    for rid in d:
        d[rid] = "basarili"
    # ayni an tekrar + uygulama restart (yeni nesne, ayni dosya): ikinci calisma YOK
    assert calistir(Zamanlayici(tmp_path), T0 + timedelta(minutes=60, seconds=30), d) == []
    assert len(calistir(zl, T0 + timedelta(minutes=120), d)) == 1


def test_overlap_atlanir(tmp_path) -> None:
    zl, z = _z(tmp_path)
    d: dict = {}
    calistir(zl, T0 + timedelta(minutes=60), d)  # r1 "calisiyor" kalir
    assert calistir(zl, T0 + timedelta(minutes=120), d) == []
    assert zl.gecmis(z.id)[-1]["durum"] == "atlandi_overlap"


def test_onay_bekleyen_gozetimsiz_onaylanmaz_ve_overlap_sayilir(tmp_path) -> None:
    zl, z = _z(tmp_path)
    d: dict = {}
    calistir(zl, T0 + timedelta(minutes=60), d)
    for rid in d:
        d[rid] = "onay_bekliyor"
    assert calistir(zl, T0 + timedelta(minutes=120), d) == []
    durumlar = [t["durum"] for t in zl.gecmis(z.id)]
    assert durumlar == ["onay_bekliyor", "atlandi_overlap"]


@pytest.mark.parametrize("kural,beklenen", [("atla", 0), ("bir_kez", 1)])
def test_kapaliyken_kacirilan(tmp_path, kural, beklenen) -> None:
    zl, z = _z(tmp_path, kacirilan=kural)
    d: dict = {}
    # uygulama 5 saat kapali kaldi: 5 tetikleme kacirildi, en fazla BIR calisma
    tetik = calistir(zl, T0 + timedelta(hours=5, minutes=20), d)
    assert len(tetik) == beklenen
    g = zl.gecmis(z.id)
    assert sum(t["durum"] == "atlandi_kacirildi" for t in g) == 5 - beklenen


def test_basarisiz_retry_sinirli(tmp_path) -> None:
    zl, z = _z(tmp_path, tekrar=1)
    d: dict = {}
    calistir(zl, T0 + timedelta(minutes=60), d)
    for rid in d:
        d[rid] = "basarisiz"
    yeniden = calistir(zl, T0 + timedelta(minutes=61), d)
    assert len(yeniden) == 1 and yeniden[0].deneme == 2
    for rid in d:
        d[rid] = "basarisiz"
    assert calistir(zl, T0 + timedelta(minutes=62), d) == []  # hak bitti


def test_gunluk_dst_ileri_ve_geri(tmp_path) -> None:
    zl = Zamanlayici(tmp_path)
    z = zl.ekle({"ad": "dst", "hedef": "x", "proje_kok": str(tmp_path), "tur": "gunluk",
                 "saat": "02:30", "saat_dilimi": "Europe/Berlin"}, simdi=T0)  # fmt: skip
    # 29 Mart 2026: 02:00 -> 03:00 (02:30 yok) -> 03:30 CEST = 01:30 UTC
    s = sonraki(z, datetime(2026, 3, 28, 23, 0, tzinfo=UTC))
    assert s == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    # 25 Ekim 2026: 02:30 iki kez yasanir -> yalniz ilki (CEST, 00:30 UTC), ikincisi atlanir
    s = sonraki(z, datetime(2026, 10, 24, 23, 0, tzinfo=UTC))
    assert s == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert sonraki(z, s) == datetime(2026, 10, 26, 1, 30, tzinfo=UTC)  # ertesi gun CET


def test_gecersiz_saat_dilimi_ve_gun(tmp_path) -> None:
    zl = Zamanlayici(tmp_path)
    temel = {"ad": "x", "hedef": "x", "proje_kok": "x", "tur": "gunluk"}
    with pytest.raises(ValueError, match="saat dilimi"):
        zl.ekle(temel | {"saat_dilimi": "Mars/Olympus"})
    with pytest.raises(ValueError, match="gunler"):
        zl.ekle(temel | {"gunler": [7]})


async def test_api_zamanlama_proje_acik_degilse_calistirmaz(app, istemci, tmp_path) -> None:
    r = await istemci.post(
        "/api/zamanlamalar",
        json={
            "ad": "gece",
            "hedef": "x",
            "proje_kok": str(tmp_path),
            "tur": "aralik",
            "aralik_dk": 5,
        },
    )
    assert r.status_code == 200, r.text
    z = r.json()
    assert z["saat_dilimi"] == "Europe/Istanbul"  # kullanici ayarindan
    tick = app.state.zamanlayici_tick
    gelecek = datetime.fromisoformat(z["baslangic"]) + timedelta(minutes=5, seconds=10)
    assert len(await tick(gelecek)) == 1
    g = (await istemci.get("/api/zamanlamalar")).json()
    assert g["gecmis"][-1]["durum"].startswith("hata: zamanlamanin projesi acik degil")
    assert "acikken" in g["not"]
    bad = await istemci.post(
        "/api/zamanlamalar",
        json={"ad": "x", "hedef": "x", "proje_kok": "x", "tur": "gunluk", "saat": "25:00"},
    )
    assert bad.status_code >= 400
    assert (await istemci.delete(f"/api/zamanlamalar/{z['id']}")).status_code == 200
