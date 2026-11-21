"""OpenRouter saglayicisi: uzak modeller ayni OpenAI uyumlu akistan kullanilir.

API anahtari yalniz backend'de (<veri>/openrouter.json) durur; arayuze maskeli gider.
Model listesi GET /api/v1/models'ten cekilir, 24 saat diskte tutulur (atomik yazim).
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from loguru import logger

from app.services import dpapi
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
            basliklar = {
                k: v
                for k, v in cevap.headers.items()
                if k.lower() not in ("content-encoding", "content-length")
            }
            return httpx.Response(400, headers=basliklar, content=govde, request=istek)
        await cevap.aclose()
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


# Anthropic ve Gemini onbellegi acik isaret ister (cache_control); OpenAI/DeepSeek/Grok
# kendiliginden onbellekler. Ajan her turda ayni sistem + gecmisi yeniden gonderdigi icin
# isaret olmadan cagri basina ~100K token tam fiyatla odenir.
ONBELLEK_ISARETLI = ("anthropic/", "google/gemini")


def onbellek_isaretle(mesajlar: list[dict]) -> list[dict]:
    """Sistem mesaji ve son mesaj onbellek kirilma noktasi olur (en fazla 4 izinli)."""
    sonuc = [dict(m) for m in mesajlar]
    hedefler = [i for i, m in enumerate(sonuc) if m.get("role") == "system"][:1]
    if sonuc and sonuc[-1].get("role") in ("user", "tool"):
        hedefler.append(len(sonuc) - 1)
    for i in hedefler:
        icerik = sonuc[i].get("content")
        if isinstance(icerik, str) and icerik:
            sonuc[i]["content"] = [
                {"type": "text", "text": icerik, "cache_control": {"type": "ephemeral"}}
            ]
        elif isinstance(icerik, list) and icerik:
            icerik = [dict(p) if isinstance(p, dict) else p for p in icerik]
            for j in range(len(icerik) - 1, -1, -1):
                if isinstance(icerik[j], dict) and icerik[j].get("type") == "text":
                    icerik[j]["cache_control"] = {"type": "ephemeral"}
                    break
            sonuc[i]["content"] = icerik
    return sonuc


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
        if '"input_audio"' in json.dumps(govde["messages"]):  # kullanici sesi: veri toplanmasin
            govde["provider"] = {"data_collection": "deny"}
        if self.model.startswith(ONBELLEK_ISARETLI):
            govde["messages"] = onbellek_isaretle(govde["messages"])
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
        "ses": "audio" in girdiler,
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
        self.veri_dizini = veri_dizini
        self.transport = transport
        self.adres = adres

    # ---- anahtar ----
    def anahtar(self) -> str:
        # CI (A11.4): kisa omurlu sir ortamdan okunur, diske YAZILMAZ; alt sureclere gecmez
        # (ortam_allowlist). Kayitli anahtar varsa o oncelikli.
        d = json_oku(self.anahtar_yolu, {}) or {}
        kayitli = ""
        if d.get("sifreli"):
            try:
                kayitli = dpapi.coz(d["sifreli"])
            except (OSError, ValueError):  # baska kullanici/makine: anahtar yeniden girilmeli
                logger.warning("OpenRouter anahtari cozulemedi")
        elif d.get("anahtar"):  # eski duz metin kayit: sifreliye tasi
            kayitli = d["anahtar"]
            json_yaz(self.anahtar_yolu, {"sifreli": dpapi.sifrele(kayitli)})
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
        json_yaz(self.anahtar_yolu, {"sifreli": dpapi.sifrele(anahtar)})
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

    def model_bilgisi(self, model_id: str) -> dict | None:
        """Onbellekteki sadelestirilmis model kaydi (yoksa None)."""
        onb = json_oku(self.liste_yolu, None) or {}
        return next((m for m in onb.get("modeller", []) if m.get("id") == model_id), None)

    async def modeller(self, yenile: bool = False, cikti: str = "") -> dict:
        """cikti: "image" | "video" -> o ciktiyi URETEN modeller (/models varsayilan olarak yalniz
        metin cikislilari verir); her biri ayri onbellekte."""
        if cikti not in ("", "image", "video"):
            raise OpenRouterHatasi("cikti image ya da video olmali.")
        ek = {"image": "gorsel-", "video": "video-"}.get(cikti, "")
        yol = self.veri_dizini / f"openrouter-{ek}modeller.json" if ek else self.liste_yolu
        onb = json_oku(yol, None)
        taze = onb and time.time() - onb.get("zaman", 0) < ONBELLEK_SN
        if taze and not yenile:
            return {"modeller": onb["modeller"], "zaman": onb["zaman"], "uyari": ""}
        try:
            async with httpx.AsyncClient(timeout=20.0, transport=self.transport) as c:
                r = await c.get(
                    f"{self.adres}/models",
                    params={"output_modalities": cikti} if cikti else None,
                )
                r.raise_for_status()
                ham = r.json()["data"]
            liste = sorted((_sadelestir(m) for m in ham if m.get("id")), key=lambda m: m["ad"])
            if cikti:  # gorsel/video fiyati token disinda; yalniz :free kesin ucretsiz
                for m in liste:
                    m["ucretsiz"] = m["id"].endswith(":free")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            if onb:
                return {
                    "modeller": onb["modeller"],
                    "zaman": onb["zaman"],
                    "uyari": f"Liste guncellenemedi, eski liste gosteriliyor ({type(e).__name__}).",
                }
            raise OpenRouterHatasi(f"OpenRouter model listesi alinamadi: {e}") from e
        veri = {"zaman": time.time(), "modeller": liste}
        json_yaz(yol, veri)
        return veri | {"uyari": ""}

    def gorsel_uret(self, model: str, istem: str) -> dict:
        """POST /images {model, prompt} -> {veri: bytes, tur: media_type, maliyet_usd}.
        Senkron: arac isleyicileri is parcaciginda calisir."""
        import base64

        a = self.anahtar()
        if not a:
            raise OpenRouterHatasi("OpenRouter anahtari yok; AI Ayarlari'ndan ekleyin.")
        try:
            with httpx.Client(timeout=180.0, transport=self.transport) as c:
                r = c.post(f"{self.adres}/images", headers={"Authorization": f"Bearer {a}"},
                           json={"model": model, "prompt": istem})  # fmt: skip
        except httpx.HTTPError as e:
            raise OpenRouterHatasi(f"Gorsel uretilemedi ({type(e).__name__}).", gecici=True) from e
        if r.status_code >= 400:
            OpenRouterLLM._hata_firlat(r.status_code, r.text)
        try:
            g = r.json()["data"][0]
            veri = base64.b64decode(g["b64_json"])
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise OpenRouterHatasi("Gorsel modeli beklenmeyen cevap dondurdu.") from e
        maliyet = (r.json().get("usage") or {}).get("cost")
        return {"veri": veri, "tur": g.get("media_type") or "image/png", "maliyet_usd": maliyet}

    def video_uret(self, model: str, istem: str, sure_sn: int = 5, *, bekle=time.sleep,
                   aralik: float = 10.0, en_fazla: int = 90) -> dict:  # fmt: skip
        """POST /videos -> polling_url yoklanir -> GET /videos/{id}/content. UCRETLI.
        Doner: {veri: bytes, tur: "video/mp4", maliyet_usd}. Senkron (arac is parcacigi)."""
        a = self.anahtar()
        if not a:
            raise OpenRouterHatasi("OpenRouter anahtari yok; AI Ayarlari'ndan ekleyin.")
        bas = {"Authorization": f"Bearer {a}"}
        kok = self.adres.split("/api/")[0]  # polling_url goreli gelir: /api/v1/videos/<id>
        try:
            with httpx.Client(timeout=120.0, transport=self.transport) as c:
                r = c.post(f"{self.adres}/videos", headers=bas,
                           json={"model": model, "prompt": istem, "duration": sure_sn})  # fmt: skip
                if r.status_code >= 400:
                    OpenRouterLLM._hata_firlat(r.status_code, r.text)
                is_ = r.json()
                for _ in range(en_fazla):
                    durum = is_.get("status")
                    if durum == "completed":
                        break
                    if durum in ("failed", "cancelled", "expired"):
                        raise OpenRouterHatasi(
                            f"Video uretilemedi ({durum}): {is_.get('error') or ''}"
                        )
                    bekle(aralik)
                    yol = is_.get("polling_url") or f"/api/v1/videos/{is_['id']}"
                    if yol.startswith(("http://", "https://")):
                        uy, uk = urlsplit(yol), urlsplit(kok)
                        if (
                            uy.scheme != uk.scheme
                            or uy.netloc.lower() != uk.netloc.lower()
                            or uy.username
                            or uy.password
                        ):
                            raise OpenRouterHatasi("Gecersiz video yoklama adresi.")
                        hedef = yol
                    else:
                        if not yol.startswith("/") or yol.startswith("//"):
                            raise OpenRouterHatasi("Gecersiz video yoklama adresi.")
                        hedef = kok + yol
                    r = c.get(hedef, headers=bas)
                    if r.status_code >= 400:
                        OpenRouterLLM._hata_firlat(r.status_code, r.text)
                    is_ = r.json()
                else:
                    raise OpenRouterHatasi(f"Video {int(en_fazla * aralik)} sn icinde bitmedi.")
                v = c.get(
                    f"{self.adres}/videos/{is_['id']}/content", params={"index": 0}, headers=bas
                )
                if v.status_code >= 400:
                    OpenRouterLLM._hata_firlat(v.status_code, v.text)
        except httpx.HTTPError as e:
            raise OpenRouterHatasi(f"Video uretilemedi ({type(e).__name__}).", gecici=True) from e
        except (KeyError, TypeError, ValueError) as e:
            raise OpenRouterHatasi("Video modeli beklenmeyen cevap dondurdu.") from e
        tur = v.headers.get("content-type", "video/mp4").split(";")[0]
        maliyet = (is_.get("usage") or {}).get("cost")
        return {"veri": v.content, "tur": tur if tur.startswith("video/") else "video/mp4",
                "maliyet_usd": maliyet}  # fmt: skip

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
