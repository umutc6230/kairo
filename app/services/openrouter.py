"""OpenRouter saglayicisi: uzak modeller ayni OpenAI uyumlu akistan kullanilir.

API anahtari yalniz backend'de (<veri>/openrouter.json) durur; arayuze maskeli gider.
Model listesi GET /api/v1/models'ten cekilir, 24 saat diskte tutulur (atomik yazim).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.services.depo import json_oku, json_yaz
from app.services.yerel_llm import ModelCevapHatasi, YerelLLM

OR_ADRES = "https://openrouter.ai/api/v1"
ONBELLEK_SN = 24 * 3600
OR_BASLIK = {
    "HTTP-Referer": "https://github.com/umutc6230/kairo",
    "X-Title": "Kairo",
}


class OpenRouterHatasi(ModelCevapHatasi):
    def __init__(self, mesaj: str, gecici: bool = False) -> None:
        super().__init__(mesaj)
        self.gecici = gecici  # 429/5xx: ajan dongusu sinirli bekleyip yeniden dener


def maskele(anahtar: str) -> str:
    return f"{anahtar[:6]}...{anahtar[-4:]}" if len(anahtar) > 12 else "****"


# Dusunmeyi kapatmaya izin vermeyen modeller (OpenRouter 400 "Reasoning is mandatory");
# ilk hatada ogrenilir, istek en dusuk eforla yeniden gonderilir.
ZORUNLU_DUSUNME: set[str] = set()
EFOR = {"dengeli": "low", "derin": "high"}


class _DusunmeDuzelten(httpx.AsyncBaseTransport):
    """400 "reasoning is mandatory" gelirse istegi en dusuk eforla bir kez yeniden atar."""

    def __init__(self, ic: httpx.AsyncBaseTransport) -> None:
        self.ic = ic

    async def handle_async_request(self, istek: httpx.Request) -> httpx.Response:
        cevap = await self.ic.handle_async_request(istek)
        if cevap.status_code != 400 or not istek.url.path.endswith("/chat/completions"):
            return cevap
        govde = await cevap.aread()
        if b"easoning is mandatory" not in govde:
            return httpx.Response(400, headers=cevap.headers, content=govde, request=istek)
        import json as _json

        veri = _json.loads(istek.content or b"{}")
        if veri.get("model"):
            ZORUNLU_DUSUNME.add(veri["model"])
        veri["reasoning"] = {"effort": "low"}
        yeni = httpx.Request(
            istek.method, istek.url,
            headers={k: v for k, v in istek.headers.items() if k.lower() != "content-length"},
            content=_json.dumps(veri).encode(), extensions=istek.extensions,
        )  # fmt: skip
        return await self.ic.handle_async_request(yeni)

    async def aclose(self) -> None:
        await self.ic.aclose()


class OpenRouterLLM(YerelLLM):
    """Sunucu sureci yok; hazirla/durdur bos, govdede llama.cpp'ye ozel alanlar yok."""

    def __init__(self, anahtar: str, model: str, *, transport: Any = None, adres: str = OR_ADRES):
        super().__init__(adres=adres, model=model, transport=transport, cokunce_kapat=False)
        if not anahtar:
            raise OpenRouterHatasi("OpenRouter API anahtari girilmemis (AI Ayarlari).")
        self._istemci.headers.update({"Authorization": f"Bearer {anahtar}", **OR_BASLIK})
        self._istemci._transport = _DusunmeDuzelten(self._istemci._transport)  # noqa: SLF001 - kucuk sarmalayici

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
        # Effort gercekten gonderilir: dengeli=low, derin=high. Kapali: dusunmeyi kapatmaya
        # izin vermeyen modelde (ZORUNLU_DUSUNME) en dusuk efor; digerlerinde kapat.
        if seviye == "kapali":
            govde["reasoning"] = (
                {"effort": "low"} if self.model in ZORUNLU_DUSUNME else {"enabled": False}
            )
        else:
            govde["reasoning"] = {"effort": EFOR.get(str(seviye), "medium")}
        govde["usage"] = {"include": True}  # cevapta maliyet (usage.cost)
        return govde

    @staticmethod
    def _hata_firlat(durum: int, govde: str) -> None:
        mesaj = {
            401: "OpenRouter API anahtari gecersiz.",
            402: "OpenRouter bakiyesi yetersiz; ucretsiz bir model secin ya da bakiye ekleyin.",
            404: "Secili OpenRouter modeli bulunamadi ya da bu istegi desteklemiyor.",
            429: "OpenRouter istek siniri asildi; biraz bekleyip tekrar deneyin.",
        }.get(durum)
        raise OpenRouterHatasi(
            mesaj or f"OpenRouter hata dondu ({durum}): {govde[:300]}",
            gecici=durum == 429 or durum >= 500,
        )


def _sadelestir(m: dict) -> dict:
    fiyat = m.get("pricing") or {}
    giris = float(fiyat.get("prompt") or 0)
    cikis = float(fiyat.get("completion") or 0)
    params = m.get("supported_parameters") or []
    girdiler = (m.get("architecture") or {}).get("input_modalities") or []
    return {
        "id": m["id"],
        "ad": m.get("name") or m["id"],
        "baglam": m.get("context_length") or 0,
        "giris_1m": round(giris * 1e6, 4),  # USD / 1M token
        "cikis_1m": round(cikis * 1e6, 4),
        "ucretsiz": m["id"].endswith(":free") or (giris == 0 and cikis == 0),
        "araclar": "tools" in params,
        "json": "structured_outputs" in params or "response_format" in params,
        "goruntu": "image" in girdiler,
        "dusunme": "reasoning" in params,
    }


_HAVUZ_KILIDI = threading.Lock()


class _KapanmayanTasima(httpx.AsyncBaseTransport):
    """Paylasilan baglanti havuzu: her mesajin istemcisi kapaninca havuz KAPANMAZ. Her mesajda
    yeni istemci + TLS el sikismasi ~1.5 sn ekliyordu (canli olcum)."""

    def __init__(self) -> None:
        self.ic = httpx.AsyncHTTPTransport(
            retries=1, limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=120)
        )

    async def handle_async_request(self, istek: httpx.Request) -> httpx.Response:
        return await self.ic.handle_async_request(istek)

    async def aclose(self) -> None:
        return None  # havuz uygulama boyunca yasar


class OpenRouterDeposu:
    """Anahtar + secim disinda kalan OpenRouter verisi (anahtar, model listesi onbellegi)."""

    def __init__(self, veri_dizini: Path, transport: Any = None, adres: str = OR_ADRES) -> None:
        self.anahtar_yolu = veri_dizini / "openrouter.json"
        self.liste_yolu = veri_dizini / "openrouter-modeller.json"
        self.transport = transport
        self.adres = adres

    # ---- anahtar ----
    def anahtar(self) -> str:
        # CI (A11.4): kisa omurlu sir ortamdan okunur, diske YAZILMAZ; alt sureclere gecmez
        # (ortam_allowlist). Kayitli anahtar varsa o oncelikli.
        kayitli = (json_oku(self.anahtar_yolu, {}) or {}).get("anahtar", "")
        # Windows setx/.env ile tirnakli kaydedilmis olabilir: "sk-or-..."
        return kayitli or os.environ.get("YAS_OPENROUTER_ANAHTARI", "").strip().strip("\"'")

    def anahtar_kaydet(self, anahtar: str) -> dict:
        anahtar = anahtar.strip()
        if (
            not anahtar.startswith("sk-or-")
            or len(anahtar) < 20
            or any(c.isspace() for c in anahtar)
        ):
            raise OpenRouterHatasi("Gecersiz anahtar bicimi (sk-or-... ile baslamali).")
        json_yaz(self.anahtar_yolu, {"anahtar": anahtar})
        return self.anahtar_durumu()

    def anahtar_sil(self) -> dict:
        self.anahtar_yolu.unlink(missing_ok=True)
        return self.anahtar_durumu()

    def anahtar_durumu(self) -> dict:
        a = self.anahtar()
        return {"var": bool(a), "maskeli": maskele(a) if a else ""}

    # ---- kalan limit (durum cubugu) ----
    async def limit(self) -> dict:
        """Anahtarin kalan limiti (/key) ve hesap bakiyesi (/credits). 60 sn bellekte tutulur.
        Doner: {var, kalan, limit, kullanim, bakiye, ucretsiz, uyari}; tutarlar USD."""
        onb = getattr(self, "_limit_onb", None)
        if onb and time.time() - onb[0] < 60:
            return onb[1]
        a = self.anahtar()
        if not a:
            return {"var": False}
        basliklar = {"Authorization": f"Bearer {a}"}
        sonuc: dict = {"var": True, "uyari": ""}
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self.transport) as c:
                r = await c.get(f"{self.adres}/key", headers=basliklar)
                r.raise_for_status()
                d = r.json().get("data") or {}
                sonuc |= {
                    "limit": d.get("limit"),  # None: limitsiz anahtar
                    "kalan": d.get("limit_remaining"),
                    "kullanim": d.get("usage"),
                    "ucretsiz": bool(d.get("is_free_tier")),
                }
                r = await c.get(f"{self.adres}/credits", headers=basliklar)
                if r.status_code == 200:
                    k = r.json().get("data") or {}
                    if isinstance(k.get("total_credits"), (int, float)):
                        sonuc["bakiye"] = round(k["total_credits"] - (k.get("total_usage") or 0), 4)
        except (httpx.HTTPError, ValueError, AttributeError) as e:
            if onb:  # ag hatasi: eski deger + uyari
                return onb[1] | {"uyari": f"Limit guncellenemedi ({type(e).__name__})."}
            return {"var": True, "uyari": f"Limit okunamadi ({type(e).__name__})."}
        self._limit_onb = (time.time(), sonuc)
        return sonuc

    # ---- model listesi ----
    def eksik_modeli_getir(self, model_id: str) -> None:
        """Secili model onbellekte yoksa listeyi bir kez (5 dk'da en fazla) senkron yeniler.
        Onbelleksiz kurulumda (CLI, yeni veri klasoru) yetenek denetimi modeli 'aracsiz'
        sanip ajan gorevini reddediyordu."""
        onb = json_oku(self.liste_yolu, None) or {}
        if any(m.get("id") == model_id for m in onb.get("modeller", [])):
            return
        if self.transport is not None or time.time() - getattr(self, "_son_eksik_deneme", 0) < 300:
            return  # testlerde (sahte tasima) gercek aga cikilmaz
        self._son_eksik_deneme = time.time()
        try:
            with httpx.Client(timeout=20.0) as c:
                r = c.get(f"{self.adres}/models")
                r.raise_for_status()
                ham = r.json()["data"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            logger.warning("OpenRouter model listesi alinamadi: {}", e)
            return
        liste = sorted((_sadelestir(m) for m in ham if m.get("id")), key=lambda m: m["ad"])
        json_yaz(self.liste_yolu, {"zaman": time.time(), "modeller": liste})

    async def modeller(self, yenile: bool = False) -> dict:
        onb = json_oku(self.liste_yolu, None)
        taze = onb and time.time() - onb.get("zaman", 0) < ONBELLEK_SN
        if taze and not yenile:
            return {"modeller": onb["modeller"], "zaman": onb["zaman"], "uyari": ""}
        try:
            async with httpx.AsyncClient(timeout=20.0, transport=self.transport) as c:
                r = await c.get(f"{self.adres}/models")
                r.raise_for_status()
                ham = r.json()["data"]
            liste = sorted((_sadelestir(m) for m in ham if m.get("id")), key=lambda m: m["ad"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            if onb:
                return {
                    "modeller": onb["modeller"],
                    "zaman": onb["zaman"],
                    "uyari": f"Liste guncellenemedi, eski liste gosteriliyor ({type(e).__name__}).",
                }
            raise OpenRouterHatasi(f"OpenRouter model listesi alinamadi: {e}") from e
        veri = {"zaman": time.time(), "modeller": liste}
        json_yaz(self.liste_yolu, veri)
        return veri | {"uyari": ""}

    def _tasima(self) -> Any:
        if self.transport is not None:  # testler: sahte tasima
            return self.transport
        with _HAVUZ_KILIDI:  # acilista arka plan is parcacigi da kurabilir
            if getattr(self, "_havuz", None) is None:
                self._havuz = _KapanmayanTasima()
        return self._havuz

    def istemci(self, model: str) -> OpenRouterLLM:
        return OpenRouterLLM(self.anahtar(), model, transport=self._tasima(), adres=self.adres)

    async def test(self, model: str) -> dict:
        """Uygulamanin kullandigi bicimde (arac tanimli) kisa istek; sure ve maliyet dondurur."""
        llm = self.istemci(model)
        arac = {
            "type": "function",
            "function": {
                "name": "saat",
                "description": "Simdiki saati verir",
                "parameters": {"type": "object", "properties": {}},
            },
        }
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
            raise OpenRouterHatasi(f"OpenRouter'a ulasilamadi: {e}") from e
        finally:
            await llm.kapat()
        mesaj = (j.get("choices") or [{}])[0].get("message") or {}
        return {
            "tamam": True,
            "sure_sn": round(time.perf_counter() - bas, 2),
            "cevap": (mesaj.get("content") or "").strip()[:200],
            "arac_cagrisi": bool(mesaj.get("tool_calls")),
            "maliyet_usd": (j.get("usage") or {}).get("cost", 0),
        }
