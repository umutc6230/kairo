"""Ihtiyaca gore arac yukleme (Claude Code 'deferred tools' gibi).

Bagli MCP sunuculari onlarca arac getirir (olcum 2026-11-15: 128 arac, ~34.5K token); hepsi her
mesajda modele gidince baglam doluyor, gecmise yer kalmiyordu. Esik asilinca MCP semalari listeden
cikarilir, yerine tek `arac_bul` gider. Model aradigi araci bulunca sema AYNI listeye eklenir:
cevap_akit her turda ayni listeyi yolladigi icin arac bir sonraki turda gercek adiyla cagrilir.
Isleyiciler (izin katmani dahil) hep kayitli kalir; yalniz sema ertelenir.
"""

from __future__ import annotations

import json
import re
from typing import Any

ARAC_BUL = "arac_bul"
ESIK_TOKEN = 4000  # MCP semalari toplami bunu asmazsa (1-2 kucuk sunucu) dogrudan verilir
KARAKTER_PER_TOKEN = 3.3


def _ad(sema: dict) -> str:
    return str(sema.get("function", {}).get("name", ""))


def _ertelenir(ad: str) -> bool:
    return ad.startswith("mcp__")


def _sunucu(ad: str) -> str:
    return ad.split("__")[1] if ad.count("__") >= 2 else ad


def ara(adaylar: list[dict], sorgu: str, limit: int) -> list[dict]:
    """'select:a,b' tam ad; aksi halde ad/aciklamada kelime puani (ad 3, sunucu 2, aciklama 1)."""
    if sorgu.strip().lower().startswith("select:"):
        istenen = {x.strip() for x in sorgu.split(":", 1)[1].split(",") if x.strip()}
        return [s for s in adaylar if _ad(s) in istenen]
    kelimeler = [k for k in re.split(r"[^a-z0-9]+", sorgu.lower()) if len(k) > 1]
    puanli = []
    for sira, s in enumerate(adaylar):
        ad = _ad(s).lower()
        aciklama = str(s.get("function", {}).get("description") or "").lower()
        puan = sum(3 * (k in ad) + 2 * (k in _sunucu(ad)) + (k in aciklama) for k in kelimeler)
        if puan:
            puanli.append((-puan, sira, s))
    return [s for _, _, s in sorted(puanli, key=lambda x: x[:2])[:limit]]


def ertele(araclar: list[dict], isleyiciler: dict[str, Any], onceki_adlar: set[str]) -> None:
    """`araclar` listesini YERINDE degistirir. Gecmiste cagrilmis araclar yuklu kalir (model
    onlari gecmiste gordu; semasiz cagri saglayicida reddedilir)."""
    ertelenen = [s for s in araclar if _ertelenir(_ad(s))]
    toplam = sum(len(json.dumps(s, ensure_ascii=False)) for s in ertelenen) / KARAKTER_PER_TOKEN
    if toplam <= ESIK_TOKEN:
        return
    bekleyen = [s for s in ertelenen if _ad(s) not in onceki_adlar]
    beklenen_adlar = {_ad(s) for s in bekleyen}
    araclar[:] = [s for s in araclar if _ad(s) not in beklenen_adlar]
    yuklenen: list[dict] = []

    def bul(sorgu: str, limit: int = 5) -> dict:
        limit = max(1, min(int(limit or 5), 15))
        bulunan = ara(bekleyen, str(sorgu), limit)
        for s in bulunan:
            bekleyen.remove(s)
            araclar.append(s)  # sohbet: cevap_akit bu listeyi her turda yollar
            yuklenen.append(s)  # ajan gorevi: runner semalarina ekler
        if not bulunan:
            sunucular = ", ".join(sorted({_sunucu(_ad(s)) for s in bekleyen}))
            not_ = f"Eslesen arac yok; baska (Ingilizce) kelime dene. Sunucular: {sunucular}"
            return {"yuklendi": [], "not": not_}
        return {
            "yuklendi": [
                {"arac": _ad(s), "aciklama": str(s["function"].get("description") or "")[:200]}
                for s in bulunan
            ],
            "not": "Bu araclar artik yuklu; bir sonraki adimda gercek adlariyla dogrudan cagir.",
        }

    bul.yuklenen = yuklenen  # type: ignore[attr-defined]
    bul.bekleyen = bekleyen  # type: ignore[attr-defined]
    sayac: dict[str, int] = {}
    for s in bekleyen:
        sayac[_sunucu(_ad(s))] = sayac.get(_sunucu(_ad(s)), 0) + 1
    liste = ", ".join(f"{k} ({v})" for k, v in sorted(sayac.items()))
    araclar.append(
        {
            "type": "function",
            "function": {
                "name": ARAC_BUL,
                "description": "Baglayici (MCP) araclari baglami doldurmasin diye yuklu gelmez. "
                "Bir dis sistem (masaustu, tarayici, GitHub, dosya sistemi vb.) gerekiyorsa once "
                "bununla ara; bulunan araclar yuklenir ve sonra gercek adlariyla cagrilir. "
                "Tam ad biliniyorsa sorgu 'select:mcp__sunucu__arac'. "
                f"Yuklu olmayan sunucular (arac sayisi): {liste}",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sorgu": {"type": "string", "description": "Ingilizce anahtar kelimeler"},
                        "limit": {"type": "integer", "description": "En fazla kac arac (1-15)"},
                    },
                    "required": ["sorgu"],
                },
            },
        }
    )
    isleyiciler[ARAC_BUL] = bul
