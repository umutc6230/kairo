"""Ajan sir kasasi: kullanicinin verdigi API anahtarlari DPAPI ile sifreli `data/sirlar.json`'da.

Model degeri hic gormez: sohbete yalniz adi gider (`$GITHUB_TOKEN`), komut sureclerine ortam
degiskeni olarak eklenir, araclardan modele donen metinde deger `***AD***` ile maskelenir.
Kasa tum oturumlarda gecerlidir.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from app.exceptions import UygulamaHatasi
from app.services import dpapi
from app.services.depo import json_oku, json_yaz

AD = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
EN_KISA = 8  # daha kisa degerler maskelenirse siradan metni bozar; zaten anahtar degildir

# Yapistirilan anahtarin turune gore varsayilan ortam degiskeni adi (ilk eslesen)
ONEK_ADLARI = (
    ("sk-or-", "OPENROUTER_API_KEY"),
    ("sk-ant-", "ANTHROPIC_API_KEY"),
    ("sk-", "OPENAI_API_KEY"),
    ("github_pat_", "GITHUB_TOKEN"),
    ("gh", "GITHUB_TOKEN"),
    ("xox", "SLACK_TOKEN"),
    ("AKIA", "AWS_ACCESS_KEY_ID"),
    ("AIza", "GOOGLE_API_KEY"),
    ("ck_", "COMPOSIO_API_KEY"),
)


def varsayilan_ad(deger: str) -> str:
    for onek, ad in ONEK_ADLARI:
        if deger.startswith(onek):
            return ad
    return "TELEGRAM_BOT_TOKEN" if re.fullmatch(r"\d{8,10}:[\w-]{35}", deger) else "API_KEY"


class SirKasasi:
    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "sirlar.json"
        self._kilit = threading.Lock()
        self._acik: dict[str, str] | None = None  # cozulmus onbellek (her komutta DPAPI cagirma)

    def _oku(self) -> dict[str, str]:
        if self._acik is None:
            acik = {}
            for ad, sifreli in (json_oku(self.yol, {}) or {}).items():
                try:
                    acik[ad] = dpapi.coz(sifreli)
                except (OSError, ValueError):
                    continue  # baska kullanici/PC'de sifrelenmis: cozulemez, atla
            self._acik = acik
        return self._acik

    def _yaz(self, acik: dict[str, str]) -> None:
        json_yaz(self.yol, {ad: dpapi.sifrele(d) for ad, d in acik.items()})
        self._acik = dict(acik)

    def ekle(self, deger: str, ad: str = "") -> str:
        deger = deger.strip()
        if len(deger) < EN_KISA or any(c.isspace() for c in deger):
            raise UygulamaHatasi("Gecersiz anahtar.")
        with self._kilit:
            acik = dict(self._oku())
            for mevcut, d in acik.items():
                if d == deger:
                    return mevcut  # ayni anahtar ikinci kez yapistirildi
            ad = (ad or varsayilan_ad(deger)).upper()
            if not AD.fullmatch(ad):
                raise UygulamaHatasi("Sir adi BUYUK_HARF_VE_ALT_CIZGI olmali.")
            taban, n = ad, 2
            while ad in acik:  # ayni turden ikinci anahtar: GITHUB_TOKEN_2
                ad, n = f"{taban}_{n}", n + 1
            acik[ad] = deger
            self._yaz(acik)
            return ad

    def sil(self, ad: str) -> None:
        with self._kilit:
            acik = dict(self._oku())
            if acik.pop(ad, None) is None:
                raise UygulamaHatasi("Sir bulunamadi.")
            self._yaz(acik)

    def adlar(self) -> list[str]:
        return sorted(self._oku())

    def ortam(self) -> dict[str, str]:
        return dict(self._oku())

    def maskele(self, metin: str) -> str:
        for ad, d in self._oku().items():
            if len(d) >= EN_KISA and d in metin:
                metin = metin.replace(d, f"***{ad}***")
        return metin


KASA: SirKasasi | None = None  # api acilisinda kurulur; testte/CLI'da yoksa kasa bos sayilir


def ortam() -> dict[str, str]:
    return KASA.ortam() if KASA else {}


def maskele(metin: str) -> str:
    return KASA.maskele(metin) if KASA else metin


def talimat() -> str:
    """Sistem istemine: hangi sirlar var ve nasil kullanilir (degerler ASLA)."""
    adlar = KASA.adlar() if KASA else []
    if not adlar:
        return ""
    return (
        "\n\n## Sir kasasi\nKullanicinin kayitli anahtarlari komut_calistir sureclerinde ortam "
        f"degiskeni olarak hazir: {', '.join(adlar)}. Komutta $AD (bash) ya da $env:AD "
        "(PowerShell) ile kullan. Degeri yazdirma, dosyaya (.env dahil) yazma, URL'e koyma; "
        "ciktida ***AD*** gorursen bu maskeli degerdir."
    )
