"""A8.6 dinamik is akislari: graf dogrulama, bagimlilik, kosul, tekrar, onayda durma/devam."""

from __future__ import annotations

import pytest

from app.agent.akis import Akis, AkisDeposu, calistir
from app.exceptions import UygulamaHatasi


def akis(*adimlar) -> Akis:
    return Akis(ad="t", adimlar=list(adimlar))


def test_dongu_bilinmeyen_ve_eksik_alan() -> None:
    with pytest.raises(ValueError, match="dongu"):
        akis({"id": "a", "tur": "komut", "komut": "x", "bagimli": ["b"]},
             {"id": "b", "tur": "komut", "komut": "y", "bagimli": ["a"]})  # fmt: skip
    with pytest.raises(ValueError, match="bilinmeyen"):
        akis({"id": "a", "tur": "komut", "komut": "x", "bagimli": ["yok"]})
    with pytest.raises(ValueError, match="hedef zorunlu"):
        akis({"id": "a", "tur": "ajan"})
    with pytest.raises(ValueError):
        akis({"id": "a", "tur": "python", "komut": "eval('1')"})  # kod tipi yok


async def test_bagimlilik_kosul_tekrar(tmp_path) -> None:
    calisan: list[str] = []
    sayac = {"test": 0}

    def komut(k: str) -> dict:
        calisan.append(k)
        if k == "test":
            sayac["test"] += 1
            return {"cikis_kodu": 0 if sayac["test"] == 2 else 1, "cikti": "x"}  # 2. denemede gecer
        return {"cikis_kodu": 1 if k == "kotu" else 0, "cikti": k}

    async def ajan(hedef: str):
        calisan.append(f"ajan:{hedef}")
        return "basarili", "tamam", "r1"

    a = akis(
        {"id": "duzelt", "tur": "ajan", "hedef": "duzelt"},
        {"id": "test", "tur": "komut", "komut": "test", "bagimli": ["duzelt"], "tekrar": 2},
        {"id": "kotu", "tur": "komut", "komut": "kotu"},
        {"id": "sonra", "tur": "komut", "komut": "sonra", "bagimli": ["kotu"]},
        {"id": "rapor", "tur": "komut", "komut": "rapor",
         "kosul": {"adim": "test", "durum": "basarili"}},
        {"id": "alarm", "tur": "komut", "komut": "alarm",
         "kosul": {"adim": "test", "durum": "basarisiz"}},
    )  # fmt: skip
    s = await calistir(a, AkisDeposu(tmp_path), ajan, komut)
    d = {x.id: x for x in s.adimlar}
    assert calisan.index("ajan:duzelt") < calisan.index("test")
    assert d["test"].durum == "basarili" and d["test"].deneme == 2
    assert d["kotu"].durum == "basarisiz" and d["sonra"].durum == "atlandi"
    assert d["rapor"].durum == "basarili" and d["alarm"].durum == "atlandi"
    assert "sonra" not in calisan and "alarm" not in calisan
    assert s.durum == "basarisiz"


async def test_onayda_durur_devamda_tamamlanan_tekrar_calismaz(tmp_path) -> None:
    calisan: list[str] = []
    onayli = {"deger": False}

    def komut(k: str) -> dict:
        if k == "yaz" and not onayli["deger"]:
            return {"karar": "onay_bekliyor"}
        calisan.append(k)
        return {"cikis_kodu": 0}

    async def ajan(h):
        return "basarili", "", ""

    depo = AkisDeposu(tmp_path)
    a = akis({"id": "once", "tur": "komut", "komut": "once"},
             {"id": "yaz", "tur": "komut", "komut": "yaz", "bagimli": ["once"]})  # fmt: skip
    s = await calistir(a, depo, ajan, komut)
    assert s.durum == "onay_bekliyor" and calisan == ["once"]
    onayli["deger"] = True
    s = depo.getir(s.id)
    s.adimlar[1].durum = "bekliyor"
    s = await calistir(s, depo, ajan, komut)
    assert s.durum == "basarili" and calisan == ["once", "yaz"]  # 'once' yinelenmedi


async def test_api_proje_yok_ve_gecersiz(istemci) -> None:
    r = await istemci.post(
        "/api/akislar", json={"ad": "x", "adimlar": [{"id": "a", "tur": "ajan"}]}
    )
    assert r.status_code >= 400 and "hedef zorunlu" in r.json()["hata"]
    r = await istemci.post("/api/akislar", json={"ad": "x", "adimlar": [
        {"id": "a", "tur": "komut", "komut": "echo 1"}]})  # fmt: skip
    assert r.status_code >= 400 and "proje" in r.json()["hata"]
    assert (await istemci.get("/api/akislar/" + "0" * 12)).status_code == 404


def test_dogrula_veri_turkce_hata() -> None:
    from app.agent.akis import dogrula_veri

    with pytest.raises(UygulamaHatasi, match="Akis gecersiz"):
        dogrula_veri({"ad": "x", "adimlar": []})
