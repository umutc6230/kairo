"""MCP OAuth: kesif, dinamik kayit, PKCE, kod -> token, yenileme ve API geri donusu."""
# ruff: noqa: E501

from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.agent import mcp_oauth
from app.agent.mcp import McpYoneticisi
from app.exceptions import UygulamaHatasi

KOK = "https://mcp.ornek.test"


def sahte_sunucu() -> tuple[httpx.MockTransport, dict]:
    durum: dict = {"meydan": "", "yenilendi": 0}

    def isle(r: httpx.Request) -> httpx.Response:
        u = r.url.path
        if u.startswith("/.well-known/oauth-protected-resource"):
            return httpx.Response(
                200, json={"resource": f"{KOK}/mcp", "authorization_servers": [KOK]}
            )
        if u == "/.well-known/oauth-authorization-server":
            return httpx.Response(200, json={
                "authorization_endpoint": f"{KOK}/yetki", "token_endpoint": f"{KOK}/token",
                "registration_endpoint": f"{KOK}/kayit"})  # fmt: skip
        if u == "/kayit":
            return httpx.Response(201, json={"client_id": "istemci-1"})
        if u == "/token":
            g = parse_qs(r.content.decode())
            if g["grant_type"] == ["authorization_code"]:
                # PKCE dogrulamasi: verifier'in SHA256'si challenge'a esit olmali
                v = (
                    base64.urlsafe_b64encode(
                        hashlib.sha256(g["code_verifier"][0].encode()).digest()
                    )
                    .rstrip(b"=")
                    .decode()
                )
                if g["code"] != ["KOD"] or v != durum["meydan"]:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(
                    200, json={"access_token": "A1", "refresh_token": "R1", "expires_in": 3600}
                )
            durum["yenilendi"] += 1
            return httpx.Response(200, json={"access_token": "A2", "expires_in": 3600})
        return httpx.Response(404)

    return httpx.MockTransport(isle), durum


def test_tam_akis_ve_yenileme() -> None:
    t, d = sahte_sunucu()
    with httpx.Client(transport=t) as c:
        adres, b = mcp_oauth.baslat(f"{KOK}/mcp", "http://127.0.0.1:9/geri", c)
        q = parse_qs(urlsplit(adres).query)
        assert q["client_id"] == ["istemci-1"] and q["code_challenge_method"] == ["S256"]
        d["meydan"] = q["code_challenge"][0]
        o = mcp_oauth.tamamla(b, "KOD", c)
        assert o["erisim"] == "A1" and o["yenileme"] == "R1"
        assert mcp_oauth.gerekirse_yenile(o, c) is None  # suresi dolmadi
        o["bitis"] = time.time()
        y = mcp_oauth.gerekirse_yenile(o, c)
        assert y["erisim"] == "A2" and y["yenileme"] == "R1" and d["yenilendi"] == 1
        with pytest.raises(UygulamaHatasi):
            mcp_oauth.tamamla(b, "YANLIS", c)


def test_guvensiz_adres_reddedilir() -> None:
    def isle(r: httpx.Request) -> httpx.Response:
        if "authorization-server" in r.url.path:
            return httpx.Response(
                200,
                json={"authorization_endpoint": "http://kotu.test/a", "token_endpoint": f"{KOK}/t"},
            )
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(isle)) as c, pytest.raises(UygulamaHatasi):
        mcp_oauth.kesif(f"{KOK}/mcp", c)


def test_token_disari_gitmez_ve_baslik_yazilir(tmp_path) -> None:
    m = McpYoneticisi(tmp_path)
    m.ekle({"ad": "uzak", "url": f"{KOK}/mcp"})
    m.oauth_kaydet("uzak", {"erisim": "GIZLI", "yenileme": "R", "bitis": time.time() + 999,
                            "client_id": "c", "token_endpoint": f"{KOK}/token"})  # fmt: skip
    s = m.liste()[0]
    assert s.basliklar["Authorization"] == "Bearer GIZLI"
    d = s.disari()
    assert "GIZLI" not in str(d) and d["oauth"]["bagli"] is True


async def test_api_geri_donus_gecersiz_state(istemci) -> None:
    r = await istemci.get(
        "/api/mcp/oauth/geri", params={"state": "yok", "code": "x"}, headers={"x-yas-oturum": ""}
    )
    assert r.status_code == 200 and "Gecersiz" in r.text
