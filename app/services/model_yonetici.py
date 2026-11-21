"""Tek bir yerel model sunucusunu yonetir. Ayni anda tek model acik olabilir (port 8080, RAM);
model degistirme ile sohbet cakismasin diye tum model islemleri tek kilitten gecer."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from loguru import logger

from app.exceptions import FarkliModelAcik, UygulamaHatasi, YerelLLMHatasi
from app.services import sistem
from app.services.ayarlar import AyarDeposu
from app.services.yerel_llm import MODELLER, YerelLLM

LLMFabrikasi = Callable[..., YerelLLM]


class ModelYonetici:
    def __init__(
        self,
        ayarlar: AyarDeposu,
        fabrika: LLMFabrikasi = YerelLLM,
        uzak: Any = None,
        ollama: Any = None,
    ) -> None:
        self.ayarlar = ayarlar
        self.ollama = ollama  # Ollama: 'ollama:<ad>' model id'leri buradan
        self.uzak = uzak  # OpenRouterDeposu: yerel listede olmayan model id'leri buradan
        self._fabrika = fabrika
        self._llm: YerelLLM | None = None
        self._anahtar: tuple[str, str] | None = None  # (adres, dizin): degisirse yeni istemci
        self._kilit = asyncio.Lock()
        self.durum = "bilinmiyor"  # kapali | yukleniyor | hazir | hata
        self.son_hata = ""
        self.yuklenen_model = ""
        self.yukleme_sn: float | None = None

    @property
    def mesgul(self) -> bool:
        return self._kilit.locked()

    async def _istemci(self) -> YerelLLM:
        a = self.ayarlar.oku()
        anahtar = (a.adres, a.llm_dizin)
        if self._llm is None or anahtar != self._anahtar:
            if self._llm is not None:
                await self._llm.kapat()
            self._llm = self._fabrika(adres=a.adres, dizin=Path(a.llm_dizin), baglam=a.baglam_token)
            self._anahtar = anahtar
        self._llm.dusunme = a.dusunme
        return self._llm

    async def _hazirla(self, model: str) -> YerelLLM:
        if model not in MODELLER and self.uzak is not None:
            return self.uzak.istemci(model)  # OpenRouter: surec/RAM yok, yerel durum degismez
        llm = await self._istemci()
        llm.model = model
        baglam = self.ayarlar.oku().baglam_token
        if llm.baglam != baglam:  # bagalam degisti: kendi sunucumuz yeni -c ile acilsin
            llm.baglam = baglam
            if llm._surec and llm._surec.poll() is None:
                await llm._sureci_durdur()
                await llm._kapanana_kadar_bekle()
        if await llm.saglikli() and model in (await llm._acik_modeller() or [model]):
            self.durum, self.yuklenen_model = "hazir", model
            self.yukleme_sn = 0  # zaten acikti: bu istek icin yukleme yok
            return llm
        self.durum, self.son_hata = "yukleniyor", ""
        bas = time.perf_counter()
        try:
            await llm.hazirla(otomatik_baslat=self.ayarlar.oku().otomatik_baslat, bekle_sn=300)
        except YerelLLMHatasi as e:
            self.durum, self.son_hata = "hata", str(e)
            raise
        self.yukleme_sn = round(time.perf_counter() - bas, 1)
        self.durum, self.yuklenen_model = "hazir", model
        logger.info("Model hazir: {} ({} sn)", model, self.yukleme_sn)
        return llm

    @asynccontextmanager
    async def kullan(self, model: str | None = None) -> AsyncIterator[YerelLLM]:
        """Modeli hazirlar ve is bitene kadar kilitli tutar (bu sirada model degistirilemez)."""
        a = self.ayarlar.oku()
        model = model or a.aktif_model
        if model.startswith("ollama:") and self.ollama is not None:
            llm = await self.ollama.istemci(model)
            llm.dusunme = a.dusunme
            try:
                yield llm
            finally:
                await llm.kapat()
            return
        if model in MODELLER and (
            a.saglayici == "openrouter" or (a.saglayici == "ollama" and a.ollama_model)
        ):
            # Saglayici OpenRouter/Ollama: yerel (llama.cpp) model hicbir yoldan acilmaz
            if a.saglayici == "openrouter":
                hata = (
                    "OpenRouter seçili; yerel modeller kullanılmaz. AI Ayarları'ndan bir "
                    "OpenRouter modeli seç ya da sağlayıcıyı Yerel yap."
                    if not a.or_model
                    else "OpenRouter seçili; yerel modeller kullanılmaz. Yerel model için "
                    "sağlayıcıyı Yerel yap."
                )
            else:
                hata = (
                    "Ollama seçili; yerel modeller kullanılmaz. Yerel model için "
                    "sağlayıcıyı Yerel yap."
                )
            raise UygulamaHatasi(hata)
        if model not in MODELLER and self.uzak is not None:  # uzak: yerel kilide gerek yok
            llm = self.uzak.istemci(model)
            llm.dusunme = a.dusunme
            try:
                yield llm
            finally:
                await llm.kapat()
            return
        async with self._kilit:
            yield await self._hazirla(model)

    async def hazirla(self, model: str | None = None) -> dict:
        async with self.kullan(model):
            return {"model": self.yuklenen_model, "yukleme_sn": self.yukleme_sn}

    async def durdur(self, harici: bool = False) -> dict:
        """Kendi sunucumuzu durdurur; harici=True ise kullanicinin bat ile actigini da.
        Kilidi BEKLEMEZ: model yuklenirken ya da cevap yazilirken de hemen durdurur (yukleme
        surec kapandigini gorup hata verir, akis baglanti hatasiyla biter)."""
        if self._llm is not None:
            await self._llm._sureci_durdur()
        kapatildi = sistem.llama_server_durdur() if harici else False
        self.durum, self.yuklenen_model = "kapali", ""
        return {"harici_kapatildi": kapatildi}

    async def bilgi(self) -> dict:
        a = self.ayarlar.oku()
        # is surerken istemciyi yenileme (adres/klasor degismis olsa bile kullanilan istemci kalir)
        llm = self._llm if (self.mesgul and self._llm) else await self._istemci()
        acik = await llm.saglikli()
        acik_modeller = await llm._acik_modeller() if acik else []
        bizim = bool(llm._surec and llm._surec.poll() is None)
        if not self.mesgul:
            if acik:
                self.durum = "hazir"
                self.yuklenen_model = acik_modeller[0] if acik_modeller else self.yuklenen_model
            elif self.durum != "hata":
                self.durum = "kapali"
        dizin = Path(a.llm_dizin)
        dosyalar = sistem.model_dosyalari(dizin)
        return {
            "durum": self.durum,
            "son_hata": self.son_hata,
            "mesgul": self.mesgul,
            "sunucu_acik": acik,
            "acik_modeller": acik_modeller,
            "bizim_sunucu": bizim,
            "yuklenen_model": self.yuklenen_model,
            "yukleme_sn": self.yukleme_sn,
            "secili_model": a.model,
            "dusunme": a.dusunme,
            "baglam_token": a.baglam_token,
            "bellek": sistem.bellek(),
            "motor_var": sistem.motor_var(dizin),
            "modeller": [
                {
                    "anahtar": p.anahtar,
                    "ad": p.ad,
                    "aciklama": p.aciklama,
                    "ram_gb": p.ram_gb,
                    "ses": p.ses,
                    **dosyalar[p.anahtar],
                }
                for p in MODELLER.values()
            ],
        }

    async def kapat(self) -> None:
        if self._llm is not None:
            await self._llm.kapat()
            self._llm = None


__all__ = ["FarkliModelAcik", "ModelYonetici"]
