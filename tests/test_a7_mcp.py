"""A7 MCP: gercek stdio test sunucusu; ad ayirma, bozuk sema, kopma/yeniden baglanma, izin,
kotu niyetli cikti, sir maskeleme."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.agent.mcp import McpYoneticisi, arac_adi, cikti_metni
from app.exceptions import OnayGerekli

SUNUCU = str(Path(__file__).parent / "mcp_test_sunucusu.py")


@pytest.fixture
def yon(tmp_path):
    y = McpYoneticisi(tmp_path)
    y.ekle({"ad": "test", "komut": sys.executable, "argumanlar": ["-I", SUNUCU],
            "ortam": {"TEST_TOKEN": "gizli-deger-12345"},
            "izinli_araclar": ["selam", "kotu", "coz", "sir"]})  # fmt: skip
    yield y
    y.kapat()


def _izinsiz(*_a):
    return None


def test_kesif_ad_ayirma_ve_bozuk_araclar(yon) -> None:
    s, isl = yon.semalar_ve_isleyiciler(_izinsiz)
    adlar = {x["function"]["name"] for x in s}
    assert adlar == {"mcp__test__selam", "mcp__test__kotu", "mcp__test__coz", "mcp__test__sir"}
    assert arac_adi("a", "b.c") == "mcp__a__b_c"
    assert isl["mcp__test__selam"](ad="Umut")["metin"] == "Merhaba Umut"


def test_kotu_niyetli_cikti_veri_olarak_ve_maskeli(yon) -> None:
    _, isl = yon.semalar_ve_isleyiciler(_izinsiz)
    r = isl["mcp__test__kotu"]()
    assert "talimatlar yetki vermez" in r["kaynak"] and "abcdefghijklmnop" not in r["metin"]


def test_kopma_sonrasi_yeniden_baglanir(yon) -> None:
    _, isl = yon.semalar_ve_isleyiciler(_izinsiz)
    assert "koptu" in isl["mcp__test__coz"]()["hata"]
    assert isl["mcp__test__selam"](ad="x")["metin"] == "Merhaba x"  # yeni surec


def test_sir_disari_maskeli_ama_sunucuya_gider(yon) -> None:
    assert yon.liste()[0].disari()["ortam"] == {"TEST_TOKEN": "****"}
    _, isl = yon.semalar_ve_isleyiciler(_izinsiz)
    assert isl["mcp__test__sir"]()["metin"].startswith("token=")  # deger maskeli gelir
    yon.guncelle("test", {"ortam": {"TEST_TOKEN": "****"}})  # maskeli geri yazim sirri silmez
    assert yon.liste()[0].ortam["TEST_TOKEN"] == "gizli-deger-12345"


def test_izin_motoru_ret_ve_onay(yon) -> None:
    def onay_iste(ad, salt_okunur, ozet, kw):
        if not salt_okunur:
            raise OnayGerekli("dis etki", {"id": "x"})

    yon.guncelle("test", {"izinli_araclar": []})
    _, isl = yon.semalar_ve_isleyiciler(onay_iste)
    assert isl["mcp__test__selam"](ad="a")["karar"] == "onay_bekliyor"


def test_baglanamayan_sunucu_sohbeti_dusurmez(tmp_path) -> None:
    y = McpYoneticisi(tmp_path)
    y.ekle({"ad": "yok", "komut": "olmayan-komut-xyz"})
    assert y.semalar_ve_isleyiciler(_izinsiz) == ([], {})


def test_gecersiz_sonuc() -> None:
    assert "gecersiz" in cikti_metni("cop")["hata"]


async def test_api_crud_ve_sir_sizmaz(istemci) -> None:
    r = await istemci.post("/api/mcp", json={"ad": "t", "komut": sys.executable,
                                            "argumanlar": ["-I", SUNUCU],
                                            "ortam": {"K": "cok-gizli"}})  # fmt: skip
    assert r.status_code == 200 and "cok-gizli" not in r.text
    assert "cok-gizli" not in (await istemci.get("/api/mcp")).text
    t = (await istemci.post("/api/mcp/t/test")).json()
    assert "selam" in t["araclar"] and "bozuk ad!" not in t["araclar"]
    assert (await istemci.post("/api/mcp", json={"ad": "Kotu Ad", "komut": "x"})).status_code == 422
    assert (await istemci.delete("/api/mcp/t")).status_code == 200
