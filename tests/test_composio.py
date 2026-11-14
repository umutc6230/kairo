"""Composio: anahtar, oturum, uygulama listesi, OAuth linki, MCP tanimi (sahte sunucu)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.exceptions import UygulamaHatasi
from app.services.composio import Composio


def _sahte(istekler: list):
    def isle(r: httpx.Request) -> httpx.Response:
        istekler.append((r.method, r.url.path, r.headers.get("x-api-key"), r.content))
        if r.headers.get("x-api-key") != "ak_gecerli_anahtar":
            return httpx.Response(401, json={"error": {"message": "yetkisiz"}})
        if r.url.path.endswith("/tool_router/session"):
            return httpx.Response(
                201,
                json={
                    "session_id": "trs_1",
                    "mcp": {
                        "type": "http",
                        "url": "https://backend.composio.dev/tool_router/trs_1/mcp",
                    },
                },
            )
        if r.url.path.endswith("/toolkits"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "name": "Gmail",
                            "slug": "gmail",
                            "enabled": True,
                            "is_no_auth": False,
                            "composio_managed_auth_schemes": ["OAUTH2"],
                            "meta": {"logo": "https://x/gmail.png", "description": "E-posta"},
                            "connected_account": {"id": "ca_1", "status": "ACTIVE"},
                        },
                        {
                            "name": "Slack",
                            "slug": "slack",
                            "enabled": True,
                            "is_no_auth": False,
                            "composio_managed_auth_schemes": ["OAUTH2"],
                            "meta": {"logo": "https://x/slack.png", "description": "Mesaj"},
                            "connected_account": None,
                        },
                    ],
                    "next_cursor": None,
                    "total_pages": 1,
                    "current_page": 1,
                    "total_items": 2,
                },
            )
        if r.url.path.endswith("/link"):
            return httpx.Response(
                201,
                json={
                    "link_token": "lt",
                    "connected_account_id": "ca_2",
                    "redirect_url": "https://connect.composio.dev/x",
                },
            )
        if r.method == "DELETE":
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": {"message": "yok"}})

    return httpx.MockTransport(isle)


def test_gecersiz_anahtar_saklanmaz(tmp_path):
    c = Composio(tmp_path, transport=_sahte([]))
    with pytest.raises(UygulamaHatasi, match="gecersiz"):
        c.anahtar_kaydet("ck_yanlis_anahtar_123")
    assert not c.durum()["bagli"]


def test_oturum_uygulamalar_baglan_ve_mcp(tmp_path):
    istekler: list = []
    c = Composio(tmp_path, transport=_sahte(istekler))
    d = c.anahtar_kaydet("ak_gecerli_anahtar")
    assert d["bagli"] and d["anahtar"].startswith("ak_g") and "gecerli" not in d["anahtar"]
    govde = json.loads(istekler[0][3])
    assert govde["user_id"].startswith("kairo-") and govde["manage_connections"]["enable"]

    u = c.uygulamalar(arama="mail")["uygulamalar"]
    assert u[0]["slug"] == "gmail" and u[0]["bagli"] and u[0]["baglanti"] == "ca_1"
    assert not u[1]["bagli"]

    b = c.baglan("slack")
    assert b["adres"].startswith("https://connect.composio.dev")
    with pytest.raises(UygulamaHatasi):
        c.baglan("../etc")

    m = c.mcp_tanimi()
    assert m["url"].endswith("/mcp") and m["basliklar"]["x-api-key"] == "ak_gecerli_anahtar"
    assert c.baglanti_kes("ca_1")["silindi"] == "ca_1"
    c.anahtar_sil()
    assert c.mcp_tanimi() is None


def _connect_sahte(istekler: list):
    """Composio Connect MCP (ck_ anahtar, x-consumer-api-key, SSE cevap)."""

    def isle(r: httpx.Request) -> httpx.Response:
        g = json.loads(r.content)
        istekler.append((str(r.url), r.headers.get("x-consumer-api-key"), g["method"]))
        if r.headers.get("x-consumer-api-key") != "ck_kisisel_anahtar":
            return httpx.Response(401, json={"error": {"message": "Invalid API key"}})
        if g["method"] == "initialize":
            sonuc = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}
        else:
            metin = json.dumps({"data": {"redirect_url": "https://connect.composio.dev/link/ln_1"}})
            sonuc = {"content": [{"type": "text", "text": metin}], "isError": False}
        sse = (
            f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': sonuc})}\n\n"
        )
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    return httpx.MockTransport(isle)


def test_connect_anahtari_mcpye_gider_rest_kullanilmaz(tmp_path):
    istekler: list = []
    c = Composio(tmp_path, transport=_connect_sahte(istekler))
    with pytest.raises(UygulamaHatasi, match="gecersiz"):
        c.anahtar_kaydet("ck_yanlis_anahtar_000")
    assert c.anahtar() == ""  # gecersiz saklanmaz
    d = c.anahtar_kaydet("ck_kisisel_anahtar")
    assert d["bagli"] and d["tur"] == "connect"
    assert all(u.startswith("https://connect.composio.dev/mcp") for u, *_ in istekler)  # REST yok
    t = c.mcp_tanimi()
    assert t["url"] == "https://connect.composio.dev/mcp"
    assert t["basliklar"] == {"x-consumer-api-key": "ck_kisisel_anahtar"}
    assert c.uygulamalar()["connect"] is True
    assert c.baglan("gmail")["adres"] == "https://connect.composio.dev/link/ln_1"
    assert istekler[-1][2] == "tools/call"
    with pytest.raises(UygulamaHatasi, match="For You"):
        c.baglanti_kes("ca_1")
