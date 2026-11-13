"""Composio baglantisi (OpenBot'un uygulama araci katmani gibi).

Tek bir Composio API anahtariyla Gmail, Slack, Google Drive/Sheets/Docs, Jira, Notion gibi yuzlerce
uygulamaya OAuth ile baglanilir: kullanici "Baglan"a basar, tarayicida uygulamanin KENDI onay
sayfasi acilir, onaylayinca baglanti kurulur. Token Composio'da kalir; Kairo'ya ve modele gelmez.

Ajan tarafinda Composio "tool router" oturumunun MCP adresi normal bir uzak MCP baglayicisi olarak
eklenir (arama + calistirma + baglanti yonetimi araclari). Cagrilar Kairo'nun izin motorundan gecer.

API: https://backend.composio.dev/api/v3.1 (baslik: x-api-key).
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import httpx

from app.exceptions import UygulamaHatasi
from app.services.depo import json_oku, json_yaz

TABAN = "https://backend.composio.dev/api/v3.1"
MCP_AD = "composio"
ZAMAN = 30.0


def maskele(anahtar: str) -> str:
    return f"{anahtar[:4]}...{anahtar[-4:]}" if len(anahtar) > 10 else "****"


class Composio:
    def __init__(self, veri_dizini: Path, transport: Any = None) -> None:
        self.yol = veri_dizini / "composio.json"
        self.transport = transport

    # ---- kayit ----
    def _kayit(self) -> dict:
        return json_oku(self.yol, {}) or {}

    def _yaz(self, v: dict) -> None:
        json_yaz(self.yol, v)

    def anahtar(self) -> str:
        return str(self._kayit().get("anahtar", ""))

    def durum(self) -> dict:
        k = self._kayit()
        a = str(k.get("anahtar", ""))
        return {"bagli": bool(a), "anahtar": maskele(a) if a else "",
                "oturum": bool(k.get("session_id"))}  # fmt: skip

    # ---- HTTP ----
    def _istek(self, yontem: str, yol: str, **kw: Any) -> dict:
        a = self.anahtar()
        if not a:
            raise UygulamaHatasi("Composio API anahtari girilmemis (Eklentiler > Composio).")
        try:
            with httpx.Client(timeout=ZAMAN, transport=self.transport) as c:
                r = c.request(yontem, f"{TABAN}{yol}", headers={"x-api-key": a}, **kw)
        except httpx.HTTPError as e:
            raise UygulamaHatasi(f"Composio'ya ulasilamadi: {type(e).__name__}") from e
        try:
            veri = r.json() if r.content else {}
        except ValueError:
            veri = {}
        if r.status_code >= 400:
            hata = (veri.get("error") or {}) if isinstance(veri, dict) else {}
            if r.status_code in (401, 403):
                raise UygulamaHatasi("Composio API anahtari gecersiz ya da yetkisiz.")
            raise UygulamaHatasi(
                f"Composio hatasi ({r.status_code}): {hata.get('message', '')}"[:300]
            )
        return veri if isinstance(veri, dict) else {}

    # ---- anahtar / oturum ----
    def anahtar_kaydet(self, anahtar: str) -> dict:
        anahtar = anahtar.strip()
        if len(anahtar) < 10:
            raise UygulamaHatasi("Gecerli bir Composio API anahtari girin.")
        k = self._kayit()
        # kullanici kimligi: bu bilgisayardaki Kairo icin sabit, kisisel veri icermez
        k = {"anahtar": anahtar, "user_id": k.get("user_id") or f"kairo-{secrets.token_hex(6)}"}
        self._yaz(k)
        try:
            self.oturum(yenile=True)
        except UygulamaHatasi:
            self._yaz({"user_id": k["user_id"]})  # gecersiz anahtar saklanmaz
            raise
        return self.durum()

    def anahtar_sil(self) -> dict:
        k = self._kayit()
        self._yaz({"user_id": k.get("user_id", "")})
        return self.durum()

    def oturum(self, yenile: bool = False) -> dict:
        """Tool router oturumu: MCP adresi ajan baglayicisi olur; baglanti yonetimi acik."""
        k = self._kayit()
        if k.get("session_id") and k.get("mcp_url") and not yenile:
            return {"session_id": k["session_id"], "mcp_url": k["mcp_url"]}
        v = self._istek("POST", "/tool_router/session", json={
            "user_id": k.get("user_id") or f"kairo-{secrets.token_hex(6)}",
            "manage_connections": {"enable": True},
        })  # fmt: skip
        sid, url = v.get("session_id"), (v.get("mcp") or {}).get("url")
        if not sid or not url:
            raise UygulamaHatasi("Composio oturumu olusturulamadi (beklenmeyen cevap).")
        k.update({"session_id": sid, "mcp_url": url})
        self._yaz(k)
        return {"session_id": sid, "mcp_url": url}

    def mcp_tanimi(self) -> dict | None:
        """Ajanin kullanacagi uzak MCP baglayicisi (anahtar yalniz backend basliginda)."""
        if not self.anahtar():
            return None
        o = self.oturum()
        return {"ad": MCP_AD, "url": o["mcp_url"], "basliklar": {"x-api-key": self.anahtar()}}

    # ---- uygulamalar ----
    def uygulamalar(self, arama: str = "", bagli: bool | None = None, imlec: str = "") -> dict:
        o = self.oturum()
        p: dict[str, Any] = {"limit": 50}
        if arama:
            p["search"] = arama
        if bagli is not None:
            p["is_connected"] = str(bagli).lower()
        if imlec:
            p["cursor"] = imlec
        try:
            v = self._istek("GET", f"/tool_router/session/{o['session_id']}/toolkits", params=p)
        except UygulamaHatasi:  # oturum suresi dolmus olabilir: bir kez yenile
            o = self.oturum(yenile=True)
            v = self._istek("GET", f"/tool_router/session/{o['session_id']}/toolkits", params=p)
        ogeler = []
        for x in v.get("items", []):
            meta = x.get("meta") or {}
            ca = x.get("connected_account")
            ogeler.append({
                "slug": x.get("slug", ""), "ad": x.get("name", ""),
                "aciklama": (meta.get("description") or "")[:200], "logo": meta.get("logo", ""),
                "baglanti": (ca or {}).get("id", "") if isinstance(ca, dict) else "",
                "bagli": bool(ca) and (ca or {}).get("status", "ACTIVE") in ("ACTIVE", None),
                "kimliksiz": bool(x.get("is_no_auth")),
            })  # fmt: skip
        return {"uygulamalar": ogeler, "sonraki": v.get("next_cursor") or "",
                "toplam": v.get("total_items", len(ogeler))}  # fmt: skip

    def baglan(self, toolkit: str) -> dict:
        """OAuth baglanti linki: kullanici tarayicida uygulamanin onay sayfasinda onaylar."""
        if not toolkit or not toolkit.replace("_", "").replace("-", "").isalnum():
            raise UygulamaHatasi("Gecersiz uygulama adi.")
        o = self.oturum()
        v = self._istek("POST", f"/tool_router/session/{o['session_id']}/link",
                        json={"toolkit": toolkit})  # fmt: skip
        url = v.get("redirect_url", "")
        if not url.startswith("https://"):
            raise UygulamaHatasi("Composio baglanti adresi alinamadi.")
        return {"adres": url, "baglanti": v.get("connected_account_id", "")}

    def baglanti_kes(self, baglanti_id: str) -> dict:
        if not baglanti_id or not baglanti_id.replace("_", "").replace("-", "").isalnum():
            raise UygulamaHatasi("Gecersiz baglanti.")
        self._istek("DELETE", f"/connected_accounts/{baglanti_id}")
        return {"silindi": baglanti_id}
