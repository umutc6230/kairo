"""Telegram kanali: telefondan kalici bir ajana mesaj; ajan bitince cevap Telegram'a doner.

openbot'un mesajlasma kanallarindan (Telegram/Slack/Discord/WhatsApp) uyarlandi; yalniz Telegram,
resmi Bot API ile (getUpdates uzun yoklama: sunucu/port acmak gerekmez).

GUVENLIK: Ajan tam yetkiyle bilgisayarda is yapabilir. Bu yuzden YALNIZ izin listesindeki sohbet
kimlikleri (chat id) kabul edilir; digerlerine yalniz kendi kimliklerini soyleyen bir cevap gider.
Bot token'i yalniz <veri>/telegram.json'da durur; arayuze maskeli gider, modele hic gitmez.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.agent.policy import maskele as sir_maskele
from app.services import dpapi
from app.services.depo import json_oku, json_yaz

API = "https://api.telegram.org"
MAX_MESAJ = 4000  # Telegram siniri 4096


def maskele(token: str) -> str:
    return f"{token[:6]}...{token[-4:]}" if len(token) > 12 else ("****" if token else "")


class TelegramKanali:
    def __init__(self, veri_dizini: Path, transport: Any = None) -> None:
        self.yol = veri_dizini / "telegram.json"
        self.transport = transport
        self.son_hata = ""
        self.bot_adi = ""
        self._gorev: asyncio.Task | None = None

    # ---- ayar ----
    def ayar(self) -> dict:
        a = json_oku(self.yol, {}) or {}
        if sif := a.get("token_sifreli"):
            try:
                a["token"] = dpapi.coz(str(sif))
            except (OSError, ValueError):
                a["token"] = ""
        elif duz := a.get("token"):  # eski duz kaydi ilk okumada DPAPI ile sifrele
            a_disk = dict(a)
            a_disk["token_sifreli"] = dpapi.sifrele(str(duz))
            a_disk.pop("token", None)
            json_yaz(self.yol, a_disk)
        return a

    def _yaz(self, a: dict) -> None:
        disk = dict(a)
        if tok := disk.pop("token", ""):
            disk["token_sifreli"] = dpapi.sifrele(str(tok))
        json_yaz(self.yol, disk)

    def kaydet(self, veri: dict) -> dict:
        a = self.ayar()
        if "token" in veri and veri["token"]:
            a["token"] = str(veri["token"]).strip()
            self.bot_adi = ""
        if veri.get("token_sil"):
            a.pop("token", None)
            a.pop("token_sifreli", None)
            self.bot_adi = ""
        if "izinli" in veri:
            a["izinli"] = sorted({int(x) for x in veri["izinli"] if str(x).lstrip("-").isdigit()})
        if "ajan" in veri:
            a["ajan"] = str(veri["ajan"] or "")
        if "aktif" in veri:
            a["aktif"] = bool(veri["aktif"])
        self._yaz(a)
        return self.durum()

    def durum(self) -> dict:
        a = self.ayar()
        return {
            "token_var": bool(a.get("token")), "token": maskele(a.get("token", "")),
            "izinli": a.get("izinli", []), "ajan": a.get("ajan", ""),
            "aktif": bool(a.get("aktif")),
            "calisiyor": bool(self._gorev and not self._gorev.done()),
            "bot": self.bot_adi, "son_hata": self.son_hata,
            "bekleyen_kimlikler": a.get("bekleyen", [])[-5:],
        }  # fmt: skip

    # ---- Bot API ----
    async def _cagir(self, c: httpx.AsyncClient, yontem: str, **veri: Any) -> Any:
        token = self.ayar().get("token", "")
        r = await c.post(f"{API}/bot{token}/{yontem}", json=veri)
        j = r.json()
        if not j.get("ok"):
            raise RuntimeError(j.get("description") or f"HTTP {r.status_code}")
        return j["result"]

    async def gonder(self, chat_id: int, metin: str) -> None:
        if not self.ayar().get("token"):
            return
        async with httpx.AsyncClient(timeout=20, transport=self.transport) as c:
            for i in range(0, max(1, len(metin)), MAX_MESAJ):  # uzun cevap parcali
                await self._cagir(c, "sendMessage", chat_id=chat_id, text=metin[i : i + MAX_MESAJ])

    async def bildir_herkese(self, metin: str) -> None:
        """Telegram aktifse izinli tum sohbetlere bildirim gonderir; hatalari yutar."""
        a = self.ayar()
        if not a.get("aktif") or not a.get("token"):
            return
        for chat_id in a.get("izinli", []):
            try:
                await self.gonder(int(chat_id), metin)
            except Exception as e:  # noqa: BLE001
                logger.warning("Telegram bildirim hatasi ({}): {}", chat_id, sir_maskele(str(e)))

    # ---- dongu ----
    def baslat(self, mesaj_isle) -> None:
        """mesaj_isle(chat_id, metin, kimden_adi) -> str | None (hemen verilecek cevap)."""
        if self._gorev and not self._gorev.done():
            return
        self._gorev = asyncio.create_task(self._dongu(mesaj_isle))

    def durdur(self) -> None:
        if self._gorev:
            self._gorev.cancel()

    async def _dongu(self, mesaj_isle) -> None:
        ofset = int(self.ayar().get("ofset", 0))
        async with httpx.AsyncClient(timeout=40, transport=self.transport) as c:
            while True:
                a = self.ayar()
                if not a.get("aktif") or not a.get("token"):
                    await asyncio.sleep(3)
                    continue
                try:
                    if not self.bot_adi:
                        self.bot_adi = (await self._cagir(c, "getMe")).get("username", "")
                    guncellemeler = await self._cagir(
                        c, "getUpdates", offset=ofset, timeout=25, allowed_updates=["message"]
                    )
                    self.son_hata = ""
                except Exception as e:  # noqa: BLE001 - ag/token hatasi: bekle, tekrar dene
                    self.son_hata = re.sub(r"/bot[^/\s]+/", "/bot***/", sir_maskele(str(e)))[:200]
                    await asyncio.sleep(10)
                    continue
                for g in guncellemeler:
                    ofset = max(ofset, g["update_id"] + 1)
                    m = g.get("message") or {}
                    metin = (m.get("text") or "").strip()
                    chat = (m.get("chat") or {}).get("id")
                    if not metin or chat is None:
                        continue
                    await self._isle(c, int(chat), metin, m, mesaj_isle)
                a = self.ayar()
                a["ofset"] = ofset
                self._yaz(a)

    async def _isle(self, c, chat: int, metin: str, m: dict, mesaj_isle) -> None:
        a = self.ayar()
        if chat not in a.get("izinli", []):
            bekleyen = [x for x in a.get("bekleyen", []) if x != chat] + [chat]
            a["bekleyen"] = bekleyen[-10:]
            self._yaz(a)
            await self._cagir(c, "sendMessage", chat_id=chat, text=(
                f"Bu sohbet Kairo'da izinli degil. Sohbet kimligin: {chat}\n"
                "Kairo > Ajanlar > Telegram bolumunde izin listesine ekle."))  # fmt: skip
            logger.warning(f"Telegram: izinsiz sohbet {chat}")
            return
        ad = (m.get("from") or {}).get("first_name", "")
        try:
            cevap = await mesaj_isle(chat, metin, ad)
        except Exception as e:  # noqa: BLE001
            cevap = f"Hata: {getattr(e, 'mesaj', str(e))}"
        if cevap:
            await self._cagir(c, "sendMessage", chat_id=chat, text=cevap[:MAX_MESAJ])
