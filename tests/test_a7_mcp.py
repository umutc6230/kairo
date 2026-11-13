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
    assert adlar == {"mcp__test__selam", "mcp__test__kotu", "mcp__test__coz", "mcp__test__sir",
                     "mcp__test__kokler"}  # fmt: skip
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


# ------------------------------------------------------------ streamable HTTP (sahte uzak sunucu)
import json as _json  # noqa: E402

import httpx  # noqa: E402


class SahteUzak:
    def __init__(self, token: str = "tok-1", sse: bool = False) -> None:
        self.token, self.sse, self.oturumlar, self.istekler = token, sse, {"s1"}, []

    def __call__(self, r: httpx.Request) -> httpx.Response:
        m = _json.loads(r.content)
        self.istekler.append((m.get("method"), r.headers.get("mcp-session-id")))
        if r.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401)
        if (
            m.get("method") != "initialize"
            and r.headers.get("mcp-session-id") not in self.oturumlar
        ):
            return httpx.Response(404)
        if "id" not in m:
            return httpx.Response(202)
        sonuc = {
            "initialize": {"protocolVersion": "2025-06-18", "capabilities": {"resources": {}}},
            "tools/list": {"tools": [{"name": "ara", "inputSchema": {"type": "object"}}]},
            "tools/call": {"content": [{"type": "text", "text": "uzak sonuc"}]},
            "resources/list": {"resources": [{"uri": "file:///rapor.md"}]},
        }[m["method"]]
        govde = {"jsonrpc": "2.0", "id": m["id"], "result": sonuc}
        h = {"mcp-session-id": "s1"} if m["method"] == "initialize" else {}
        if self.sse:
            return httpx.Response(200, text=f"event: message\ndata: {_json.dumps(govde)}\n\n",
                                  headers={**h, "content-type": "text/event-stream"})  # fmt: skip
        return httpx.Response(200, json=govde, headers=h)


def _uzak(tmp_path, sahte, token="tok-1"):
    y = McpYoneticisi(tmp_path, transport=httpx.MockTransport(sahte))
    y.ekle({"ad": "uzak", "url": "https://mcp.ornek.invalid/mcp",
            "basliklar": {"Authorization": f"Bearer {token}"},
            "izinli_araclar": ["ara"]})  # fmt: skip
    return y


@pytest.mark.parametrize("sse", [False, True])
def test_http_json_ve_sse_oturum_resources(tmp_path, sse) -> None:
    sahte = SahteUzak(sse=sse)
    y = _uzak(tmp_path, sahte)
    t = y.test("uzak")
    assert t == {"ad": "uzak", "araclar": ["ara"], "kaynaklar": ["file:///rapor.md"], "uzak": True,
                 "tembel": False}  # fmt: skip
    assert ("tools/list", "s1") in sahte.istekler  # oturum kimligi tasindi


def test_http_uzak_arac_izinli_olsa_da_onay_ister(tmp_path) -> None:
    y = _uzak(tmp_path, SahteUzak())

    def onay(ad, salt_okunur, ozet, kw):
        if not salt_okunur:
            raise OnayGerekli("veri disari gidecek", {"id": "x"})

    _, isl = y.semalar_ve_isleyiciler(onay)
    assert isl["mcp__uzak__ara"]()["karar"] == "onay_bekliyor"  # izinli listesi uzakta gecmez
    _, isl = y.semalar_ve_isleyiciler(_izinsiz)
    assert isl["mcp__uzak__ara"]()["metin"] == "uzak sonuc"


def test_http_401_token_yenileme_ve_oturum_dusmesi(tmp_path) -> None:
    sahte = SahteUzak(token="yeni")
    y = _uzak(tmp_path, sahte, token="eski")
    with pytest.raises(Exception, match="401"):
        y.test("uzak")
    y.guncelle("uzak", {"basliklar": {"Authorization": "Bearer yeni"}})  # kullanici yeniledi
    assert y.test("uzak")["araclar"] == ["ara"]
    y.guncelle("uzak", {"basliklar": {"Authorization": "****"}})  # maskeli geri yazim korur
    assert y.liste()[0].basliklar["Authorization"] == "Bearer yeni"
    _, isl = y.semalar_ve_isleyiciler(_izinsiz)
    sahte.oturumlar.clear()  # sunucu oturumu dusurdu
    assert "sona erdi" in isl["mcp__uzak__ara"]()["hata"]
    sahte.oturumlar.add("s1")
    assert isl["mcp__uzak__ara"]()["metin"] == "uzak sonuc"  # yeniden initialize


def test_http_adres_dogrulama() -> None:
    from app.agent.mcp import McpSunucu

    for kotu in ("http://uzak.ornek/mcp", "https://u:p@ornek/mcp", "ftp://x"):
        with pytest.raises(ValueError):
            McpSunucu(ad="x", url=kotu)
    with pytest.raises(ValueError):
        McpSunucu(ad="x", url="https://a/mcp", komut="python")
    assert McpSunucu(ad="x", url="http://127.0.0.1:9000/mcp").disari()["uzak"]


def test_mcp_roots_aktif_proje_klasoru_ve_degisiklik(tmp_path) -> None:
    """filesystem gibi sunucular izinli klasoru MCP roots'tan alir; klasorsuz aktarilan sunucu
    her dosyayi reddediyordu. Proje degisince roots/list_changed ile yeniden sorulur."""
    import json

    a, b = tmp_path / "proje-a", tmp_path / "proje-b"
    a.mkdir()
    b.mkdir()
    y = McpYoneticisi(tmp_path)
    aktif = [str(a), str(tmp_path / "yok")]  # olmayan klasor roots'a girmez
    y.kokler = lambda: aktif
    y.ekle({"ad": "fs", "komut": sys.executable, "argumanlar": ["-I", SUNUCU],
            "izinli_araclar": ["kokler"]})  # fmt: skip
    try:
        _, isl = y.semalar_ve_isleyiciler(_izinsiz)
        ilk = json.loads(isl["mcp__fs__kokler"]()["metin"])
        assert [k["uri"] for k in ilk] == [a.resolve().as_uri()]
        aktif[:] = [str(b)]
        sonra = json.loads(isl["mcp__fs__kokler"]()["metin"])
        assert [k["uri"] for k in sonra] == [b.resolve().as_uri()]
    finally:
        y.kapat()
