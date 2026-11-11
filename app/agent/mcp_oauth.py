# ruff: noqa: E501 - OAuth parametre sozlukleri
"""Uzak MCP sunuculari icin OAuth 2.1 girisi (MCP yetkilendirme spesifikasyonu).

Akis: korunan kaynak meta verisi -> yetkilendirme sunucusu meta verisi -> dinamik istemci kaydi
(RFC 7591) -> PKCE (S256) ile tarayicida giris -> yerel geri donus adresinde kod -> token.
Tokenlar yalniz bu bilgisayarda (mcp.json) saklanir; suresi dolunca refresh_token ile yenilenir.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from app.exceptions import UygulamaHatasi

ZAMAN = 20


def _kok(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.netloc}"


def _https(url: str) -> str:
    u = urlsplit(url or "")
    yerel = u.hostname in ("127.0.0.1", "localhost", "::1")
    if u.scheme != "https" and not (u.scheme == "http" and yerel):
        raise UygulamaHatasi(f"Guvensiz OAuth adresi reddedildi: {url[:120]}")
    return url


def _json(c: httpx.Client, url: str) -> dict | None:
    try:
        r = c.get(url, headers={"Accept": "application/json"})
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def kesif(sunucu_url: str, c: httpx.Client) -> dict:
    """Yetkilendirme sunucusunun uclari (authorization, token, registration)."""
    kok, yol = _kok(sunucu_url), urlsplit(sunucu_url).path.rstrip("/")
    kaynak = (
        _json(c, f"{kok}/.well-known/oauth-protected-resource{yol}")
        or _json(c, f"{kok}/.well-known/oauth-protected-resource")
        or {}
    )
    as_url = ((kaynak.get("authorization_servers") or [kok])[0]).rstrip("/")
    meta = None
    for ek in ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"):
        meta = _json(c, f"{as_url}{ek}") or _json(c, f"{_kok(as_url)}{ek}{urlsplit(as_url).path}")
        if meta:
            break
    if not meta or not meta.get("authorization_endpoint") or not meta.get("token_endpoint"):
        raise UygulamaHatasi("Bu sunucu OAuth girisi sunmuyor (meta veri bulunamadi).")
    return {
        "authorization_endpoint": _https(meta["authorization_endpoint"]),
        "token_endpoint": _https(meta["token_endpoint"]),
        "registration_endpoint": meta.get("registration_endpoint") or "",
        "kaynak": kaynak.get("resource") or sunucu_url,
        "kapsam": " ".join(kaynak.get("scopes_supported") or []),
    }


def baslat(sunucu_url: str, geri: str, c: httpx.Client, client_id: str = "") -> tuple[str, dict]:
    """(tarayicida acilacak adres, bekleyen durum)."""
    m = kesif(sunucu_url, c)
    if not client_id:
        if not m["registration_endpoint"]:
            raise UygulamaHatasi("Sunucu otomatik istemci kaydi desteklemiyor; client_id gerekli.")
        r = c.post(_https(m["registration_endpoint"]), json={
            "client_name": "Kairo", "redirect_uris": [geri], "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        })  # fmt: skip
        if r.status_code not in (200, 201):
            raise UygulamaHatasi(f"Istemci kaydi basarisiz: HTTP {r.status_code}")
        client_id = r.json().get("client_id", "")
    dogrulayici = secrets.token_urlsafe(48)
    meydan = base64.urlsafe_b64encode(hashlib.sha256(dogrulayici.encode()).digest()).rstrip(b"=")
    durum = secrets.token_urlsafe(24)
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": geri, "state": durum,
         "code_challenge": meydan.decode(), "code_challenge_method": "S256", "resource": m["kaynak"]}  # fmt: skip
    if m["kapsam"]:
        q["scope"] = m["kapsam"]
    sep = "&" if "?" in m["authorization_endpoint"] else "?"
    return f"{m['authorization_endpoint']}{sep}{urlencode(q)}", {
        "durum": durum, "dogrulayici": dogrulayici, "client_id": client_id, "geri": geri,
        "token_endpoint": m["token_endpoint"], "kaynak": m["kaynak"], "zaman": time.time(),
    }  # fmt: skip


def _token(c: httpx.Client, uc: str, govde: dict) -> dict:
    r = c.post(uc, data=govde, headers={"Accept": "application/json"})
    if r.status_code != 200:
        raise UygulamaHatasi(f"Token alinamadi: HTTP {r.status_code} {r.text[:150]}")
    t = r.json()
    if not t.get("access_token"):
        raise UygulamaHatasi("Token yanitinda access_token yok.")
    return t


def tamamla(b: dict, kod: str, c: httpx.Client) -> dict:
    """Kodu tokene cevirir; McpSunucu.oauth alanina yazilacak sozluk doner."""
    t = _token(c, b["token_endpoint"], {
        "grant_type": "authorization_code", "code": kod, "redirect_uri": b["geri"],
        "client_id": b["client_id"], "code_verifier": b["dogrulayici"], "resource": b["kaynak"],
    })  # fmt: skip
    return _kayit(t, b["client_id"], b["token_endpoint"], b["kaynak"])


def _kayit(t: dict, client_id: str, uc: str, kaynak: str, eski_yenileme: str = "") -> dict:
    return {
        "erisim": t["access_token"], "yenileme": t.get("refresh_token") or eski_yenileme,
        "bitis": time.time() + int(t.get("expires_in") or 3600), "client_id": client_id,
        "token_endpoint": uc, "kaynak": kaynak,
    }  # fmt: skip


def gerekirse_yenile(oauth: dict, c: httpx.Client) -> dict | None:
    """Suresi 60 sn icinde dolacaksa yeniler; yeni kayit ya da None (gerek yok/yapilamaz)."""
    if not oauth or oauth.get("bitis", 0) - time.time() > 60 or not oauth.get("yenileme"):
        return None
    t = _token(c, oauth["token_endpoint"], {
        "grant_type": "refresh_token", "refresh_token": oauth["yenileme"],
        "client_id": oauth["client_id"], "resource": oauth.get("kaynak", ""),
    })  # fmt: skip
    return _kayit(t, oauth["client_id"], oauth["token_endpoint"], oauth.get("kaynak", ""),
                  oauth["yenileme"])  # fmt: skip


def ozet(oauth: dict[str, Any]) -> dict:
    return {"bagli": bool(oauth.get("erisim")), "bitis": oauth.get("bitis", 0)} if oauth else {}
