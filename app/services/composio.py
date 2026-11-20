"""Composio baglantisi (OpenBot'un uygulama araci katmani gibi).

Tek bir Composio API anahtariyla Gmail, Slack, Google Drive/Sheets/Docs, Jira, Notion gibi yuzlerce
uygulamaya OAuth ile baglanilir: kullanici "Baglan"a basar, tarayicida uygulamanin KENDI onay
sayfasi acilir, onaylayinca baglanti kurulur. Token Composio'da kalir; Kairo'ya ve modele gelmez.

Ajan tarafinda Composio "tool router" oturumunun MCP adresi normal bir uzak MCP baglayicisi olarak
eklenir (arama + calistirma + baglanti yonetimi araclari). Cagrilar Kairo'nun izin motorundan gecer.

API: https://backend.composio.dev/api/v3.1 (baslik: x-api-key).

Iki anahtar turu var ve birbirinin yerine GECMEZ:
- Proje anahtari (Composio Platform, genelde ak_...): yukaridaki REST API + tool router oturumu.
- Kisisel Connect anahtari (Composio For You, ck_...): https://connect.composio.dev/mcp adresine
  x-consumer-api-key basligiyla dogrudan MCP. Uygulama baglantilari Composio'nun kendi MCP araci
  (COMPOSIO_MANAGE_CONNECTIONS) ile yapilir. Eskiden ck_ REST'e gidip "gecersiz" sayiliyordu.
"""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any

import httpx

from app.exceptions import UygulamaHatasi
from app.services import dpapi
from app.services.depo import json_oku, json_yaz

TABAN = "https://backend.composio.dev/api/v3.1"
CONNECT_MCP = "https://connect.composio.dev/mcp"
MCP_AD = "composio"
ZAMAN = 30.0


def connect_mi(anahtar: str) -> bool:
    """Kisisel Connect (For You) anahtari: MCP'ye x-consumer-api-key ile gider."""
    return anahtar.startswith("ck_")


def maskele(anahtar: str) -> str:
    return f"{anahtar[:4]}...{anahtar[-4:]}" if len(anahtar) > 10 else "****"


class Composio:
    def __init__(self, veri_dizini: Path, transport: Any = None) -> None:
        self.yol = veri_dizini / "composio.json"
        self.transport = transport

    # ---- kayit ----
    def _kayit(self) -> dict:
        """Anahtar diskte DPAPI ile sifreli; eski duz kayit ilk okumada sifrelenir."""
        k = dict(json_oku(self.yol, {}) or {})
        if k.get("anahtar"):  # eski surum: duz metin
            self._yaz(k)
            return k
        if k.get("anahtar_sifreli"):
            try:
                k["anahtar"] = dpapi.coz(k.pop("anahtar_sifreli"))
            except (OSError, ValueError):
                k.pop("anahtar_sifreli", None)  # baska kullanici/PC: cozulemez, bagli degil say
        return k

    def _yaz(self, v: dict) -> None:
        v = dict(v)
        if v.get("anahtar"):
            v["anahtar_sifreli"] = dpapi.sifrele(v.pop("anahtar"))
        json_yaz(self.yol, v)

    def anahtar(self) -> str:
        return str(self._kayit().get("anahtar", ""))

    def durum(self) -> dict:
        k = self._kayit()
        a = str(k.get("anahtar", ""))
        return {"bagli": bool(a), "anahtar": maskele(a) if a else "",
                "tur": ("connect" if connect_mi(a) else "platform") if a else "",
                "oturum": bool(k.get("session_id")) or (bool(a) and connect_mi(a))}  # fmt: skip

    # ---- Connect (ck_) MCP ----
    def _connect(self, metod: str, params: dict) -> dict:
        """Connect MCP'ye tek JSON-RPC istegi (sunucu durumsuz; cevap JSON ya da SSE)."""
        govde = {"jsonrpc": "2.0", "id": 1, "method": metod, "params": params}
        basliklar = {"x-consumer-api-key": self.anahtar(),
                     "Accept": "application/json, text/event-stream"}  # fmt: skip
        try:
            with httpx.Client(timeout=ZAMAN, transport=self.transport) as c:
                r = c.post(CONNECT_MCP, json=govde, headers=basliklar)
        except httpx.HTTPError as e:
            raise UygulamaHatasi(f"Composio'ya ulasilamadi: {type(e).__name__}") from e
        if r.status_code in (401, 403):
            raise UygulamaHatasi("Composio Connect anahtari gecersiz ya da yetkisiz.")
        if r.status_code >= 400:
            raise UygulamaHatasi(f"Composio hatasi ({r.status_code}).")
        metin = r.text
        if "data:" in metin:  # SSE: son data satiri cevaptir
            veriler = [x[5:].strip() for x in metin.splitlines() if x.startswith("data:")]
            metin = veriler[-1] if veriler else "{}"
        try:
            v = json.loads(metin or "{}")
        except ValueError as e:
            raise UygulamaHatasi("Composio beklenmeyen cevap verdi.") from e
        if isinstance(v, dict) and v.get("error"):
            raise UygulamaHatasi(f"Composio hatasi: {str(v['error'].get('message', ''))[:200]}")
        return (v.get("result") or {}) if isinstance(v, dict) else {}

    def _connect_dogrula(self) -> None:
        sonuc = self._connect("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "kairo", "version": "0.1"},
        })  # fmt: skip
        if "capabilities" not in sonuc:
            raise UygulamaHatasi("Composio Connect anahtari dogrulanamadi.")

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
            if connect_mi(anahtar):
                self._connect_dogrula()
            else:
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
        a = self.anahtar()
        if not a:
            return None
        if connect_mi(a):
            return {"ad": MCP_AD, "url": CONNECT_MCP, "basliklar": {"x-consumer-api-key": a}}
        o = self.oturum()
        return {"ad": MCP_AD, "url": o["mcp_url"], "basliklar": {"x-api-key": self.anahtar()}}

    # ---- uygulamalar ----
    def uygulamalar(self, arama: str = "", bagli: bool | None = None, imlec: str = "") -> dict:
        if connect_mi(self.anahtar()):
            # Connect'te uygulama katalogu REST'te yok; arayuz populer listeyi gosterir, "Baglan"
            # Composio'nun baglanti aracini cagirir, ajan da sohbette ihtiyac oldukca baglar.
            return {"uygulamalar": [], "sonraki": "", "toplam": 0, "connect": True}
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
        if connect_mi(self.anahtar()):
            return self._connect_baglan(toolkit)
        o = self.oturum()
        v = self._istek("POST", f"/tool_router/session/{o['session_id']}/link",
                        json={"toolkit": toolkit})  # fmt: skip
        url = v.get("redirect_url", "")
        if not url.startswith("https://"):
            raise UygulamaHatasi("Composio baglanti adresi alinamadi.")
        return {"adres": url, "baglanti": v.get("connected_account_id", "")}

    def _connect_baglan(self, toolkit: str) -> dict:
        sonuc = self._connect("tools/call", {"name": "COMPOSIO_MANAGE_CONNECTIONS", "arguments": {
            "toolkits": [{"name": toolkit, "action": "add"}]}})  # fmt: skip
        metin = " ".join(str(c.get("text", "")) for c in sonuc.get("content") or [])
        adres = re.search(r"https://[^\s\"'\<>]+", metin)
        if sonuc.get("isError") or not adres:
            raise UygulamaHatasi(f"Composio baglanti adresi alinamadi: {metin[:200]}")
        return {"adres": adres.group(0), "baglanti": ""}

    def baglanti_kes(self, baglanti_id: str) -> dict:
        if connect_mi(self.anahtar()):
            raise UygulamaHatasi(
                "Connect anahtariyla baglanti dashboard.composio.dev > For You'dan kaldirilir."
            )
        if not baglanti_id or not baglanti_id.replace("_", "").replace("-", "").isalnum():
            raise UygulamaHatasi("Gecersiz baglanti.")
        self._istek("DELETE", f"/connected_accounts/{baglanti_id}")
        return {"silindi": baglanti_id}
