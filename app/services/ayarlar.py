"""Kullanici ayarlari (AI Ayarlari ekrani): secili model, dusunme seviyesi, model klasoru..."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.config import varsayilan_llm_dizini
from app.services.depo import json_oku, json_yaz
from app.services.yerel_llm import (
    DUSUNME_SEVIYELERI,
    MODELLER,
    VARSAYILAN_ADRES,
    VARSAYILAN_MODEL,
)


class KullaniciAyarlari(BaseModel):
    model: str = VARSAYILAN_MODEL
    dusunme: str = "kapali"
    llm_dizin: str = Field(default_factory=lambda: str(varsayilan_llm_dizini()))
    adres: str = VARSAYILAN_ADRES
    otomatik_baslat: bool = True
    sistem_istemi: str = Field(default="", max_length=4000)
    sicaklik: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=16, le=8192)

    @field_validator("model")
    @classmethod
    def _model(cls, v: str) -> str:
        if v not in MODELLER:
            raise ValueError(f"Bilinmeyen model: {v}")
        return v

    @field_validator("dusunme")
    @classmethod
    def _dusunme(cls, v: str) -> str:
        if v not in DUSUNME_SEVIYELERI:
            raise ValueError(f"Gecersiz dusunme seviyesi: {v}")
        return v

    @field_validator("adres")
    @classmethod
    def _adres(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://127.0.0.1", "http://localhost")):
            raise ValueError("Adres yalniz bu bilgisayar olabilir (http://127.0.0.1:...)")
        return v if v.endswith("/v1") else f"{v}/v1"


class AyarDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "ayarlar.json"

    def oku(self) -> KullaniciAyarlari:
        ham = json_oku(self.yol, {}) or {}
        try:
            return KullaniciAyarlari(**ham)
        except ValueError:  # eski/bozuk ayar: varsayilana don, gecerli alanlari koru
            gecerli = {}
            for anahtar, deger in ham.items():
                try:
                    KullaniciAyarlari(**{anahtar: deger})
                    gecerli[anahtar] = deger
                except (ValueError, TypeError):
                    continue
            return KullaniciAyarlari(**gecerli)

    def yaz(self, ayarlar: KullaniciAyarlari) -> KullaniciAyarlari:
        json_yaz(self.yol, ayarlar.model_dump())
        return ayarlar

    def guncelle(self, degisiklik: dict) -> KullaniciAyarlari:
        yeni = KullaniciAyarlari(**(self.oku().model_dump() | degisiklik))
        return self.yaz(yeni)
