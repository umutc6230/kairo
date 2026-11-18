"""Model yetenek profili (A4.7) ve baglam butcesi dokumu (A4.1).

Yetenek, yerel modelde MODELLER + ayarlardan, OpenRouter'da diske alinmis model listesinden
okunur (ag istegi YAPILMAZ). Bilinmeyen uzak model temkinli varsayilir: araç yok, 8K.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.exceptions import UygulamaHatasi

PROFIL_SURUMU = 1
GUVENLIK_PAYI = 1.15  # tahmini sayimda %15 emniyet payi


class ModelYetenegi(BaseModel):
    model: str
    saglayici: Literal["yerel", "openrouter", "ollama"]
    araclar: bool
    json_cikti: bool
    goruntu: bool
    ses: bool = False
    baglam: int
    dusunme: bool
    tokenizer: Literal["sunucu", "tahmin"]
    profil_surumu: int = PROFIL_SURUMU
    not_: str = ""


def yerel_yetenek(anahtar: str, baglam_token: int) -> ModelYetenegi:
    from app.services.yerel_llm import MODELLER

    p = MODELLER.get(anahtar)
    return ModelYetenegi(
        model=anahtar,
        saglayici="yerel",
        araclar=True,  # llama-server --jinja: arac cagrisi
        json_cikti=True,
        goruntu=bool(p and p.mmproj),
        ses=bool(p and p.ses),
        baglam=baglam_token,
        dusunme=True,
        tokenizer="sunucu",
        not_="" if p else "Profil bulunamadi.",
    )


def uzak_yetenek(model_id: str, liste_yolu: Path) -> ModelYetenegi:
    try:
        liste = json.loads(liste_yolu.read_text(encoding="utf-8")).get("modeller") or []
    except (OSError, ValueError):
        liste = []
    m = next((x for x in liste if x.get("id") == model_id), None)
    if m is None:
        return ModelYetenegi(
            model=model_id,
            saglayici="openrouter",
            araclar=False,
            json_cikti=False,
            goruntu=False,
            baglam=8192,
            dusunme=False,
            tokenizer="tahmin",
            not_="Model listede yok; AI Ayarlari'nda listeyi yenileyin.",
        )
    return ModelYetenegi(
        model=model_id,
        saglayici="openrouter",
        araclar=bool(m.get("araclar")),
        json_cikti=bool(m.get("json")),
        goruntu=bool(m.get("goruntu")),
        baglam=int(m.get("baglam") or 8192),
        dusunme=bool(m.get("dusunme")),
        tokenizer="tahmin",
    )


def dogrula(y: ModelYetenegi, *, araclar_gerekli: bool = False, dusunme: str = "kapali") -> None:
    """Desteklenmeyen istegi SESSIZCE dusurmek yerine acik Turkce hata verir."""
    if araclar_gerekli and not y.araclar:
        raise UygulamaHatasi(
            f"'{y.model}' arac cagirmayi desteklemiyor; ajan gorevi icin arac destekli model secin."
        )
    if dusunme != "kapali" and not y.dusunme:
        raise UygulamaHatasi(
            f"'{y.model}' dusunme seviyesini desteklemiyor; dusunmeyi 'kapali' yapin."
        )


def tahmini_token(metin: str) -> int:
    """Tokenizer yoksa emniyet payli tahmin (Turkce metinde ~3 karakter/token)."""
    return int((len(metin) / 3 + 1) * GUVENLIK_PAYI)


def _js(x: object) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


def butce_dokumu(
    sistem: str, araclar: list[dict], mesajlar: list[dict], cevap: int, baglam: int
) -> dict:
    """Baglamin nereye harcandigi: sistem, arac tanimi, mesaj, kanit (arac sonuclari), cevap."""
    kanit = sum(tahmini_token(_js(m)) for m in mesajlar if m.get("role") == "tool")
    mesaj = sum(tahmini_token(_js(m)) for m in mesajlar if m.get("role") != "tool")
    d = {
        "sistem": tahmini_token(sistem),
        "araclar": tahmini_token(_js(araclar)),
        "mesajlar": mesaj,
        "kanit": kanit,
        "cevap": cevap,
    }
    toplam = sum(d.values())
    return d | {"toplam": toplam, "baglam": baglam, "dolu_yuzde": round(100 * toplam / baglam)}
