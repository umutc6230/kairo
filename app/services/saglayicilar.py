"""OpenAI uyumlu bulut/yerel saglayicilar (OpenAI, Anthropic, Gemini, DeepSeek, Groq, ...).

Tek istemci (YerelLLM'in OpenAI uyumlu akisi) hepsini karsilar; model kimligi
`<saglayici>:<model_id>` (or. `groq:llama-3.3-70b-versatile`). Anahtarlar DPAPI ile sifreli
`<veri>/saglayici-anahtarlari.json`'da durur, arayuze yalniz maskeli gider.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from loguru import logger

from app.services import dpapi
from app.services.depo import json_oku, json_yaz
from app.services.openrouter import ONBELLEK_SN, maskele
from app.services.yerel_llm import ModelCevapHatasi, YerelLLM

# id: (ad, base_url, anahtar_gerekli, ortam degiskeni)
KAYIT: dict[str, tuple[str, str, bool, str]] = {
    "openai": ("OpenAI", "https://api.openai.com/v1", True, "OPENAI_API_KEY"),
    "anthropic": ("Anthropic", "https://api.anthropic.com/v1", True, "ANTHROPIC_API_KEY"),
    "gemini": (
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        True,
        "GEMINI_API_KEY",
    ),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1", True, "DEEPSEEK_API_KEY"),
    "groq": ("Groq", "https://api.groq.com/openai/v1", True, "GROQ_API_KEY"),
    "mistral": ("Mistral", "https://api.mistral.ai/v1", True, "MISTRAL_API_KEY"),
    "xai": ("xAI (Grok)", "https://api.x.ai/v1", True, "XAI_API_KEY"),
    "cerebras": ("Cerebras", "https://api.cerebras.ai/v1", True, "CEREBRAS_API_KEY"),
    "together": ("Together AI", "https://api.together.xyz/v1", True, "TOGETHER_API_KEY"),
    "lmstudio": ("LM Studio (yerel)", "http://127.0.0.1:1234/v1", False, ""),
    "ozel": ("Özel (OpenAI uyumlu)", "", False, ""),
}


class SaglayiciHatasi(ModelCevapHatasi):
    def __init__(self, mesaj: str, gecici: bool = False) -> None:
        super().__init__(mesaj)
        self.gecici = gecici


def ayir(model: str) -> tuple[str, str] | None:
    """`groq:llama-3` -> ("groq", "llama-3"); kayitli saglayici degilse None."""
    sid, _, mid = model.partition(":")
    return (sid, mid) if sid in KAYIT and mid else None


def hata_mesaji(ad: str, durum: int, govde: str) -> SaglayiciHatasi:
    mesaj = {
        401: f"{ad} API anahtarı geçersiz.",
        402: f"{ad} bakiyesi yetersiz.",
        403: f"{ad} bu anahtara bu modeli/isteği izin vermiyor.",
        404: f"Seçili {ad} modeli bulunamadı ya da bu isteği desteklemiyor.",
        429: f"{ad} istek sınırı aşıldı; biraz bekleyip tekrar deneyin.",
    }.get(durum)
    return SaglayiciHatasi(
        mesaj or f"{ad} hata döndü ({durum}): {govde[:300]}",
        gecici=durum == 429 or durum >= 500,
    )


class UyumluLLM(YerelLLM):
    """Sunucu sureci yok; govdeye yalniz standart OpenAI alanlari gider."""

    def __init__(self, ad: str, adres: str, anahtar: str, model: str, *, transport: Any = None):
        super().__init__(adres=adres, model=model, transport=transport, cokunce_kapat=False)
        self.ad = ad
        if anahtar:
            self._istemci.headers["Authorization"] = f"Bearer {anahtar}"

    async def saglikli(self) -> bool:
        return True

    async def _acik_modeller(self) -> list[str]:
        return [self.model]

    async def hazirla(self, otomatik_baslat: bool = True, bekle_sn: float = 180.0) -> None:
        return None

    async def _sureci_durdur(self) -> None:
        return None

    async def token_say(self, metin: str) -> int:
        return max(1, len(metin) // 4)  # shortcut: kaba tahmin, uzak tokenizer yok

    def _govde(self, mesajlar: list[dict], seviye: Any, max_tokens: int, **ek: Any) -> dict:
        govde = super()._govde(mesajlar, seviye, max_tokens, **ek)
        govde.pop("chat_template_kwargs", None)
        govde.pop("thinking_budget_tokens", None)
        # shortcut: dusunme seviyesi gonderilmez (reasoning_effort'u reddeden saglayici/modeller
        # var); modelin varsayilani kullanilir. Model basina destek bilgisi gelince ac.
        return govde

    def _hata_firlat(self, durum: int, govde: str) -> None:  # type: ignore[override]
        raise hata_mesaji(self.ad, durum, govde)


def _ozel_adres_dogrula(adres: str) -> str:
    adres = adres.strip().rstrip("/")
    u = urlsplit(adres)
    if u.scheme not in ("http", "https") or not u.netloc or u.username or u.password:
        raise SaglayiciHatasi("Base URL http(s)://alan/... biçiminde olmalı.")
    return adres


class SaglayiciDeposu:
    def __init__(self, veri_dizini: Path, transport: Any = None) -> None:
        self.veri_dizini = veri_dizini
        self.yol = veri_dizini / "saglayici-anahtarlari.json"
        self.transport = transport

    def _sid(self, sid: str) -> tuple[str, str, bool, str]:
        if sid not in KAYIT:
            raise SaglayiciHatasi(f"Bilinmeyen sağlayıcı: {sid}")
        return KAYIT[sid]

    def _kayit(self) -> dict:
        return json_oku(self.yol, {}) or {}

    def adres(self, sid: str) -> str:
        _, adres, _, _ = self._sid(sid)
        return (self._kayit().get(sid) or {}).get("adres") or adres

    def anahtar(self, sid: str) -> tuple[str, str]:
        """(anahtar, kaynak): kaynak 'kayitli' | 'ortam' | ''."""
        _, _, _, ortam = self._sid(sid)
        sifreli = (self._kayit().get(sid) or {}).get("sifreli")
        if sifreli:
            try:
                return dpapi.coz(sifreli), "kayitli"
            except (OSError, ValueError):
                logger.warning("{} anahtari cozulemedi (baska bilgisayar/kullanici)", sid)
        deger = os.environ.get(ortam, "").strip().strip("\"'") if ortam else ""
        return (deger, "ortam") if deger else ("", "")

    def durum(self) -> list[dict]:
        sonuc = []
        for sid, (ad, _, gerekli, ortam) in KAYIT.items():
            a, kaynak = self.anahtar(sid)
            sonuc.append({
                "id": sid, "ad": ad, "adres": self.adres(sid), "anahtar_gerekli": gerekli,
                "anahtar": {"var": bool(a), "maskeli": maskele(a) if a else "", "kaynak": kaynak},
                "ortam": ortam,
            })  # fmt: skip
        return sonuc

    def kaydet(self, sid: str, anahtar: str = "", adres: str = "") -> list[dict]:
        _, _, _, _ = self._sid(sid)
        anahtar = anahtar.strip()
        if anahtar and (len(anahtar) < 8 or any(c.isspace() for c in anahtar)):
            raise SaglayiciHatasi("Geçersiz anahtar biçimi.")
        d = self._kayit()
        g = dict(d.get(sid) or {})
        if anahtar:
            g["sifreli"] = dpapi.sifrele(anahtar)
        if adres or sid == "ozel":
            if sid not in ("ozel", "lmstudio"):
                raise SaglayiciHatasi("Bu sağlayıcının adresi değiştirilemez.")
            g["adres"] = _ozel_adres_dogrula(adres)
        d[sid] = g
        json_yaz(self.yol, d)
        return self.durum()

    def sil(self, sid: str) -> list[dict]:
        self._sid(sid)
        d = self._kayit()
        d.pop(sid, None)
        json_yaz(self.yol, d)
        (self.veri_dizini / f"modeller-{sid}.json").unlink(missing_ok=True)
        return self.durum()

    def _hazir(self, sid: str) -> tuple[str, str, str]:
        ad, _, gerekli, _ = self._sid(sid)
        adres = self.adres(sid)
        if not adres:
            raise SaglayiciHatasi(f"{ad} için base URL girilmemiş (AI Ayarları).")
        a, _ = self.anahtar(sid)
        if gerekli and not a:
            raise SaglayiciHatasi(f"{ad} API anahtarı girilmemiş (AI Ayarları).")
        return ad, adres, a

    async def modeller(self, sid: str, yenile: bool = False) -> dict:
        yol = self.veri_dizini / f"modeller-{sid}.json"
        onb = json_oku(yol, None)
        if onb and not yenile and time.time() - onb.get("zaman", 0) < ONBELLEK_SN:
            return onb | {"uyari": ""}
        ad, adres, a = self._hazir(sid)
        basliklar = {"Authorization": f"Bearer {a}"} if a else {}
        try:
            async with httpx.AsyncClient(timeout=20.0, transport=self.transport) as c:
                r = await c.get(f"{adres}/models", headers=basliklar)
            if r.status_code >= 400:
                raise hata_mesaji(ad, r.status_code, r.text)
            ham = r.json().get("data") or []
            liste = sorted(
                (
                    {
                        "id": m["id"],
                        "ad": m.get("display_name") or m.get("name") or m["id"],
                        "baglam": m.get("context_window") or m.get("context_length") or 0,
                    }  # fmt: skip
                    for m in ham
                    if isinstance(m, dict) and m.get("id")
                ),
                key=lambda m: m["id"],
            )
        except (httpx.HTTPError, ValueError, AttributeError, TypeError) as e:
            if onb:
                return onb | {"uyari": f"Liste güncellenemedi, eski liste ({type(e).__name__})."}
            raise SaglayiciHatasi(f"{ad} model listesi alınamadı ({type(e).__name__}).") from e
        veri = {"zaman": time.time(), "modeller": liste}
        json_yaz(yol, veri)
        return veri | {"uyari": ""}

    def model_bilgisi(self, model: str) -> dict | None:
        p = ayir(model)
        if p is None:
            return None
        onb = json_oku(self.veri_dizini / f"modeller-{p[0]}.json", None) or {}
        return next((m for m in onb.get("modeller", []) if m.get("id") == p[1]), None)

    def istemci(self, model: str) -> UyumluLLM:
        p = ayir(model)
        if p is None:
            raise SaglayiciHatasi(f"Model kimliği <sağlayıcı>:<model> olmalı: {model}")
        ad, adres, a = self._hazir(p[0])
        return UyumluLLM(ad, adres, a, p[1], transport=self.transport)

    async def test(self, model: str) -> dict:
        """Uygulamanin gercek bicimiyle (arac tanimli) kisa istek."""
        llm = self.istemci(model)
        arac = {"type": "function", "function": {
            "name": "saat", "description": "Simdiki saati verir",
            "parameters": {"type": "object", "properties": {}}}}  # fmt: skip
        bas = time.perf_counter()
        try:
            govde = llm._govde(
                [{"role": "user", "content": "Sadece 'tamam' yaz."}], "kapali", 32, tools=[arac]
            )
            r = await llm._istemci.post(f"{llm.adres}/chat/completions", json=govde, timeout=60.0)
            if r.status_code >= 400:
                llm._hata_firlat(r.status_code, r.text)
            j = r.json()
        except httpx.HTTPError as e:
            raise SaglayiciHatasi(f"{llm.ad} sunucusuna ulaşılamadı ({type(e).__name__}).") from e
        finally:
            await llm.kapat()
        secim = (j.get("choices") or [{}])[0]
        mesaj = secim.get("message") or {}
        kullanim = j.get("usage") or {}
        return {
            "tamam": True,
            "sure_sn": round(time.perf_counter() - bas, 2),
            "cevap": (mesaj.get("content") or "").strip()[:200],
            "arac_cagrisi": bool(mesaj.get("tool_calls")),
            "token": kullanim.get("total_tokens"),
            "finish_reason": secim.get("finish_reason"),
        }
