"""Ollama saglayicisi ve model magazasi (Hugging Face magazasinin Ollama karsiligi).

- Model id'si `ollama:<ad>` olarak saklanir; istekler Ollama'nin OpenAI uyumlu /v1 ucuna gider.
- Kairo'nun kendi Ollama uyumlu sunucusu 11434'te durdugu icin Kairo, gerektiginde `ollama serve`
  surecini ayri portta (varsayilan 11435) baslatir; modeller Ollama'nin kendi klasorundedir.
- Arama ollama.com'dan (resmi arama API'si yok; HTMX parca sayfasi ayristirilir).
"""

from __future__ import annotations

import asyncio
import html
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.services.yerel_llm import ModelCevapHatasi, YerelLLM

ONEK = "ollama:"
VARSAYILAN_ADRES = "http://127.0.0.1:11435"
SITE = "https://ollama.com"
GIZLI = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
EFOR = {"kapali": "none", "dengeli": "low", "derin": "high"}


class OllamaHatasi(ModelCevapHatasi):
    def __init__(self, mesaj: str, gecici: bool = False) -> None:
        super().__init__(mesaj)
        self.gecici = gecici


OLLAMA_MIN_BAGLAM = 32768  # ajan talimati + arac tanimlari ~18K; 16K'da gorev hic baslamiyordu


def ollama_baglam(ayar_baglam: int) -> int:
    """Ollama baglami: ayardaki deger, en az OLLAMA_MIN_BAGLAM (llama.cpp ayari 16K olabilir)."""
    return max(ayar_baglam, OLLAMA_MIN_BAGLAM)


def ollama_mi(model: str) -> bool:
    return model.startswith(ONEK)


def ad(model: str) -> str:
    return model.removeprefix(ONEK)


def _gb(bayt: Any) -> float:
    return round((bayt or 0) / 1024**3, 1)


def _boyut_gb(metin: str) -> float | None:
    m = re.search(r"([\d.]+)\s*(GB|MB|KB|TB)", metin, re.I)
    if not m:
        return None
    carpan = {"KB": 1 / 1024**2, "MB": 1 / 1024, "GB": 1, "TB": 1024}[m.group(2).upper()]
    return round(float(m.group(1)) * carpan, 1)


def _parametre_milyar(etiket: str) -> float | None:
    m = re.fullmatch(r"(?:e)?([\d.]+)([bm])", etiket.strip().lower())
    if not m:
        return None
    return float(m.group(1)) / (1000 if m.group(2) == "m" else 1)


def _metin(parca: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", parca)).strip()


# shortcut: ollama.com HTML'i ayristirilir; site degisirse arama bos doner (yuklu modeller,
# indirme ve silme yerel API ile calismaya devam eder). Resmi arama API'si cikarsa ona gecin.
def arama_ayristir(sayfa: str) -> tuple[list[dict], bool]:
    sonuclar = []
    for li in re.findall(r"<li\b.*?</li>", sayfa, re.S):
        m = re.search(r'href="/library/([^"]+)"', li)
        if not m:
            continue
        rozetler = re.findall(r'<span\s+class="[^"]*rounded-md[^"]*">([^<]+)</span>', li)
        yetenekler = [
            r
            for r in rozetler
            if r in ("vision", "tools", "thinking", "embedding", "cloud", "audio")
        ]
        boyutlar = [r for r in rozetler if _parametre_milyar(r) is not None]
        indirme = re.search(r'title="([\d,]+) downloads"', li)
        etiket = re.search(r"([\d,]+)\s+tags?<", li)
        guncel = re.search(r'title="Updated ([^"]+)"', li)
        aciklama = re.search(r"<p[^>]*>(.*?)</p>", li, re.S)
        sonuclar.append({
            "ad": m.group(1),
            "aciklama": _metin(aciklama.group(1)) if aciklama else "",
            "yetenekler": yetenekler,
            "boyutlar": boyutlar,
            "indirme": int(indirme.group(1).replace(",", "")) if indirme else 0,
            "etiket_sayisi": int(etiket.group(1).replace(",", "")) if etiket else 0,
            "guncelleme": guncel.group(1) if guncel else "",
        })  # fmt: skip
    return sonuclar, 'hx-get="/search?page=' in sayfa


def etiket_ayristir(sayfa: str, model_ad: str) -> list[dict]:
    """/library/<ad>/tags: her etiket icin boyut, baglam, girdi turu, guncelleme."""
    sonuc, gorulen = [], set()
    desen = rf'<a href="/library/{re.escape(model_ad)}:([^"]+)" class="md:hidden[^"]*">(.*?)</a>'
    for etiket, govde in re.findall(desen, sayfa, re.S):
        if etiket in gorulen:
            continue
        gorulen.add(etiket)
        metin = " ".join(_metin(govde).split())
        kuyruk = re.search(r"\b[0-9a-f]{12}\b(.*)", metin)  # ozet hash'inden sonrasi
        kuyruk = kuyruk.group(1) if kuyruk else metin
        baglam = re.search(r"([\d.]+[KM]?)\s+context", kuyruk)
        girdi = re.search(r"([A-Za-z][A-Za-z, ]*?)\s+input", kuyruk)
        guncel = re.search(r"(\d+\s+\w+\s+ago|yesterday|today)", kuyruk)
        sonuc.append({
            "etiket": etiket,
            "tam_ad": f"{model_ad}:{etiket}",
            "boyut_gb": _boyut_gb(kuyruk),
            "baglam": baglam.group(1) if baglam else "",
            "girdi": girdi.group(1).strip() if girdi else "",
            "guncelleme": guncel.group(1) if guncel else "",
            "mlx": "MLX" in metin.split(kuyruk)[0] if kuyruk in metin else False,
        })  # fmt: skip
    return sonuc


class OllamaLLM(YerelLLM):
    """Sunucu sureci Ollama'da; govdede llama.cpp alanlari yok, dusunme reasoning_effort ile."""

    def __init__(self, kok: str, model: str, dusunur: bool, *, transport: Any = None) -> None:
        super().__init__(adres=f"{kok}/v1", model=model, transport=transport, cokunce_kapat=False)
        self.dusunur = dusunur

    async def saglikli(self) -> bool:
        return True

    async def _acik_modeller(self) -> list[str]:
        return [self.model]

    async def hazirla(self, otomatik_baslat: bool = True, bekle_sn: float = 180.0) -> None:
        return None

    async def _sureci_durdur(self) -> None:
        return None

    async def token_say(self, metin: str) -> int:
        return max(1, len(metin) // 4)  # shortcut: kaba tahmin, Ollama tokenize ucu yok

    def _govde(self, mesajlar: list[dict], seviye: Any, max_tokens: int, **ek: Any) -> dict:
        govde = super()._govde(mesajlar, seviye, max_tokens, **ek)
        govde.pop("chat_template_kwargs", None)
        govde.pop("thinking_budget_tokens", None)
        if self.dusunur:  # dusunmeyen modele gonderilirse Ollama 400 doner
            govde["reasoning_effort"] = EFOR.get(str(seviye), "medium")
        return govde

    @staticmethod
    def _hata_firlat(durum: int, govde: str) -> None:
        mesaj = {
            404: "Model Ollama'da yok; Modeller > Ollama bölümünden indir.",
            500: f"Ollama hata döndü: {govde[:300]}",
        }.get(durum)
        raise OllamaHatasi(
            mesaj or f"Ollama hata döndü ({durum}): {govde[:300]}", gecici=durum >= 502
        )


class Indirme:
    def __init__(self, model_ad: str) -> None:
        self.id = uuid.uuid4().hex[:8]
        self.ad = model_ad
        self.durum = "bekliyor"  # bekliyor | iniyor | bitti | hata | iptal
        self.asama = ""
        self.inen = 0
        self.toplam = 0
        self.hiz = 0.0
        self.hata = ""
        self.gorev: asyncio.Task | None = None

    def ozet(self) -> dict:
        yuzde = round(self.inen * 100 / self.toplam, 1) if self.toplam else 0
        kalan = (self.toplam - self.inen) / self.hiz if self.hiz and self.toplam else None
        return {"id": self.id, "ad": self.ad, "durum": self.durum, "asama": self.asama,
                "inen": self.inen, "toplam": self.toplam, "yuzde": yuzde, "hiz": self.hiz,
                "kalan_sn": round(kalan) if kalan else None, "hata": self.hata}  # fmt: skip


class Ollama:
    def __init__(
        self,
        adres: Callable[[], str],
        baglam: Callable[[], int],
        transport: Any = None,
        site_transport: Any = None,
    ) -> None:
        self.adres = adres
        self.baglam = baglam
        self.transport = transport
        self._site = httpx.AsyncClient(
            timeout=20.0, transport=site_transport, follow_redirects=True,
            headers={"HX-Request": "true", "User-Agent": "Kairo"},
        )  # fmt: skip
        self._surec: subprocess.Popen | None = None
        self.indirmeler: dict[str, Indirme] = {}
        self.yetenekler: dict[str, dict] = {}  # ad -> {araclar, goruntu, dusunme, baglam}

    def _istemci(self, sure: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.adres(), timeout=sure, transport=self.transport)

    @staticmethod
    def exe() -> str | None:
        aday = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        return shutil.which("ollama") or (str(aday) if aday.exists() else None)

    async def surum(self) -> str | None:
        """Calisan gercek Ollama'nin surumu; Kairo'nun kendi gecidi (yanitta 'kairo') sayilmaz."""
        try:
            async with self._istemci(3.0) as c:
                j = (await c.get("/api/version")).json()
        except (httpx.HTTPError, ValueError):
            return None
        return None if "kairo" in j else j.get("version")

    async def baslat(self) -> dict:
        if s := await self.surum():
            return {"calisiyor": True, "surum": s}
        exe = self.exe()
        if not exe:
            raise OllamaHatasi("Ollama kurulu değil. https://ollama.com/download adresinden kur.")
        url = httpx.URL(self.adres())
        if url.host not in ("127.0.0.1", "localhost"):
            raise OllamaHatasi(f"{self.adres()} adresindeki Ollama'ya ulaşılamıyor.")
        ortam = os.environ | {
            "OLLAMA_HOST": f"{url.host}:{url.port}",
            "OLLAMA_CONTEXT_LENGTH": str(self.baglam()),  # varsayilan 4K ajan talimatina yetmez
        }
        self._surec = subprocess.Popen(
            [exe, "serve"], env=ortam, creationflags=GIZLI,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        logger.info("Ollama baslatildi: {} ({})", self.adres(), exe)
        for _ in range(40):
            await asyncio.sleep(0.5)
            if s := await self.surum():
                return {"calisiyor": True, "surum": s, "baslatildi": True}
        raise OllamaHatasi("Ollama başlatıldı ama yanıt vermiyor.")

    def durdur(self) -> None:
        if self._surec and self._surec.poll() is None:
            self._surec.terminate()
        self._surec = None

    async def durum(self) -> dict:
        s = await self.surum()
        return {"calisiyor": bool(s), "surum": s, "kurulu": bool(self.exe()), "adres": self.adres()}

    async def _iste(self, metod: str, yol: str, **kw: Any) -> Any:
        await self.baslat()
        try:
            async with self._istemci(kw.pop("sure", 30.0)) as c:
                r = await c.request(metod, yol, **kw)
        except httpx.HTTPError as e:
            raise OllamaHatasi(f"Ollama'ya ulaşılamadı: {e}") from e
        if r.status_code >= 400:
            hata = (
                r.json().get("error", r.text)
                if r.headers.get("content-type", "").startswith("application/json")
                else r.text
            )
            raise OllamaHatasi(f"Ollama: {hata[:300]}")
        return r.json() if r.content else {}

    async def yuklu(self) -> list[dict]:
        tags = await self._iste("GET", "/api/tags")
        ps = await self._iste("GET", "/api/ps")
        acik = {m.get("name") for m in ps.get("models", [])}
        return [{
            "ad": m["name"],
            "anahtar": ONEK + m["name"],
            "boyut_gb": _gb(m.get("size")),
            "aile": (m.get("details") or {}).get("family", ""),
            "parametre": (m.get("details") or {}).get("parameter_size", ""),
            "niceleme": (m.get("details") or {}).get("quantization_level", ""),
            "degisim": m.get("modified_at", "")[:10],
            "acik": m["name"] in acik,
            "yetenek": self.yetenekler.get(m["name"]),
        } for m in tags.get("models", [])]  # fmt: skip

    async def detay(self, model_ad: str) -> dict:
        j = await self._iste("POST", "/api/show", json={"model": model_ad})
        bilgi = j.get("model_info") or {}
        baglam = next((v for k, v in bilgi.items() if k.endswith(".context_length")), None)
        yet = j.get("capabilities") or []
        self.yetenekler[model_ad] = {
            "araclar": "tools" in yet, "goruntu": "vision" in yet,
            "dusunme": "thinking" in yet, "baglam": int(baglam or 8192),
        }  # fmt: skip
        return {
            "ad": model_ad,
            "yetenekler": yet,
            "baglam": baglam,
            "ayrintilar": j.get("details") or {},
            "parametreler": j.get("parameters", ""),
            "lisans": (j.get("license") or "")[:2000],
            "degisim": j.get("modified_at", ""),
        }

    async def yetenek(self, model_ad: str) -> dict:
        if model_ad not in self.yetenekler:
            try:
                await self.detay(model_ad)
            except OllamaHatasi:
                return {"araclar": True, "goruntu": False, "dusunme": False, "baglam": 8192}
        return self.yetenekler[model_ad]

    async def sil(self, model_ad: str) -> dict:
        await self._iste("DELETE", "/api/delete", json={"model": model_ad})
        self.yetenekler.pop(model_ad, None)
        return {"silindi": model_ad}

    async def indir(self, model_ad: str) -> Indirme:
        model_ad = model_ad.strip()
        if not re.fullmatch(r"[\w./:-]{1,200}", model_ad):
            raise OllamaHatasi("Geçersiz model adı.")
        if any(
            i.ad == model_ad and i.durum in ("bekliyor", "iniyor") for i in self.indirmeler.values()
        ):
            raise OllamaHatasi("Bu model zaten iniyor.")
        await self.baslat()
        i = Indirme(model_ad)
        self.indirmeler[i.id] = i
        i.gorev = asyncio.create_task(self._indir(i))
        return i

    async def _indir(self, i: Indirme) -> None:
        import json

        i.durum = "iniyor"
        son_t, son_b = time.monotonic(), 0
        katman: dict[str, tuple[int, int]] = {}
        try:
            async with (
                self._istemci(None) as c,
                c.stream("POST", "/api/pull", json={"model": i.ad, "stream": True}) as r,
            ):
                async for satir in r.aiter_lines():
                    if not satir.strip():
                        continue
                    o = json.loads(satir)
                    if o.get("error"):
                        raise OllamaHatasi(o["error"])
                    i.asama = o.get("status", "")
                    if o.get("total"):  # her katman (digest) ayri bildirilir; toplam = katmanlar
                        katman[o.get("digest", "")] = (o["total"], o.get("completed", 0))
                        i.toplam = sum(t for t, _ in katman.values())
                        i.inen = sum(c for _, c in katman.values())
                        simdi = time.monotonic()
                        if simdi - son_t >= 1:
                            i.hiz = max(0.0, (i.inen - son_b) / (simdi - son_t))
                            son_t, son_b = simdi, i.inen
            i.durum, i.inen = "bitti", i.toplam
        except asyncio.CancelledError:
            i.durum = "iptal"
        except (OllamaHatasi, httpx.HTTPError, ValueError) as e:
            i.durum, i.hata = "hata", str(e)[:300]

    def iptal(self, indirme_id: str) -> None:
        i = self.indirmeler.get(indirme_id)
        if i and i.gorev and not i.gorev.done():
            i.gorev.cancel()

    async def ara(
        self, sorgu: str = "", sayfa: int = 1, sira: str = "popular", yetenek: str = ""
    ) -> dict:
        p = {
            "q": sorgu,
            "page": max(1, sayfa),
            "o": sira if sira in ("popular", "newest") else "popular",
        }
        if yetenek in ("tools", "vision", "thinking", "embedding"):
            p["c"] = yetenek
        try:
            r = await self._site.get(f"{SITE}/search", params=p)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaHatasi(f"ollama.com'a ulaşılamadı: {e}") from e
        sonuclar, daha = arama_ayristir(r.text)
        return {"sonuclar": sonuclar, "daha": daha}

    async def etiketler(self, model_ad: str) -> list[dict]:
        if not re.fullmatch(r"[\w./-]{1,100}", model_ad):
            raise OllamaHatasi("Geçersiz model adı.")
        try:
            r = await self._site.get(f"{SITE}/library/{model_ad}/tags", headers={"HX-Request": ""})
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaHatasi(f"ollama.com'a ulaşılamadı: {e}") from e
        return etiket_ayristir(r.text, model_ad)

    async def istemci(self, model_id: str) -> OllamaLLM:
        await self.baslat()
        yet = await self.yetenek(ad(model_id))
        return OllamaLLM(self.adres(), ad(model_id), yet["dusunme"], transport=self.transport)

    async def kapat(self) -> None:
        await self._site.aclose()
        self.durdur()
