"""Akilli maliyet ve gizlilik yonlendiricisi: gizli projede veya gunluk butce asiminda
bulut model isteklerini yerel modele yonlendirir.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.services.yerel_llm import MODELLER

if TYPE_CHECKING:
    from app.agent.workspaces import CalismaAlani
    from app.services.ayarlar import KullaniciAyarlari


def bulut_model_mi(model: str) -> bool:
    """Verilen model kimligi yerel (GGUF, Ollama, LM Studio) degilse True."""
    m = (model or "").strip()
    if not m:
        return False
    if m in MODELLER:
        return False
    return not m.startswith(("ollama:", "lmstudio:"))


def gunluk_maliyet_usd(run_deposu: Any, oturum_deposu: Any = None) -> float:
    """Bugun baslatilan gorevlerin ve sohbet mesajlarinin toplam maliyeti (USD)."""
    bugun = datetime.now().date().isoformat()
    toplam = 0.0
    for r in run_deposu.liste():
        if str(getattr(r, "olusturma", "")).startswith(bugun):
            kullanim = getattr(r, "kullanim", None)
            if kullanim is not None:
                toplam += float(getattr(kullanim, "maliyet_usd", 0.0) or 0.0)
    if oturum_deposu is not None:
        for o in oturum_deposu.liste():
            if not str(o.get("guncelleme", "")).startswith(bugun):
                continue
            try:
                ot = oturum_deposu.getir(o["id"])
            except Exception:  # noqa: BLE001 - silinmis/bozuk oturum toplami bozmasin
                continue
            for m in getattr(ot, "mesajlar", []):
                if getattr(m, "rol", "") == "asistan" and str(getattr(m, "zaman", "")).startswith(
                    bugun
                ):
                    toplam += float(
                        (getattr(m, "istatistik", None) or {}).get("maliyet_usd") or 0.0
                    )
    return round(toplam, 6)


def yerel_yedek_model(ayar: KullaniciAyarlari) -> str:
    """Gizli proje veya butce asiminda kullanilacak yerel model (GGUF, Ollama veya LM Studio)."""
    sag = getattr(ayar, "saglayici", "yerel")
    ollama_m = str(getattr(ayar, "ollama_model", "") or "").strip()
    uyumlu_m = str(getattr(ayar, "uyumlu_model", "") or "").strip()
    if sag == "ollama" and ollama_m:
        return f"ollama:{ollama_m}"
    if sag == "uyumlu" and uyumlu_m.startswith("lmstudio:"):
        return uyumlu_m
    if not getattr(ayar, "model", "") and ollama_m:
        return f"ollama:{ollama_m}"
    return ayar.model


def model_sec(
    istenen_model: str,
    ayar: KullaniciAyarlari,
    alan: CalismaAlani | None,
    bugun_usd: float = 0.0,
) -> tuple[str, str | None]:
    """Gizlilik ve gunluk butce kurallarina gore etkin modeli ve varsa uyariyi doner."""
    yerel = yerel_yedek_model(ayar)
    if alan is not None and getattr(alan, "gizli_proje", False) and bulut_model_mi(istenen_model):
        return (
            yerel,
            f"Gizli proje kurali: bulut modeli ({istenen_model}) yerine "
            f"yerel model ({yerel}) kullaniliyor.",
        )
    if (
        ayar.gunluk_butce_usd > 0
        and bugun_usd >= ayar.gunluk_butce_usd
        and bulut_model_mi(istenen_model)
    ):
        return (
            yerel,
            f"Gunluk butce siniri (${ayar.gunluk_butce_usd:.2f}, harcanan ${bugun_usd:.2f}) "
            f"asildi: yerel model ({yerel}) kullaniliyor.",
        )
    return istenen_model, None


def maliyet_analitigi(run_deposu: Any, ayar: KullaniciAyarlari) -> dict[str, Any]:
    """Bugun, 7 gun, 30 gun harcamalari, model/proje dokumu ve onbellek/yerel tasarrufu."""
    bugun = datetime.now().date()
    bugun_str = bugun.isoformat()
    sinir_7 = (bugun - timedelta(days=6)).isoformat()
    sinir_30 = (bugun - timedelta(days=29)).isoformat()

    seri_map: dict[str, dict[str, Any]] = {}
    for i in range(6, -1, -1):
        t = (bugun - timedelta(days=i)).isoformat()
        seri_map[t] = {"tarih": t, "maliyet_usd": 0.0, "gorev": 0}

    bugun_usd = 0.0
    son_7_gun_usd = 0.0
    son_30_gun_usd = 0.0
    toplam_usd = 0.0
    onbellek_token = 0
    toplam_token = 0
    yerel_gorev = 0
    bulut_gorev = 0

    model_map: dict[str, dict[str, Any]] = {}
    proje_map: dict[str, dict[str, Any]] = {}

    for r in run_deposu.liste():
        tarih = str(getattr(r, "olusturma", ""))[:10]
        k = getattr(r, "kullanim", None)
        maliyet = float(getattr(k, "maliyet_usd", 0.0) or 0.0)
        token = int(getattr(k, "token", 0) or 0)
        onbellek = int(getattr(k, "onbellek_token", 0) or 0)
        cagri = int(getattr(k, "model_cagrisi", 0) or 0)

        toplam_usd += maliyet
        if tarih == bugun_str:
            bugun_usd += maliyet
        if tarih >= sinir_7:
            son_7_gun_usd += maliyet
        if tarih >= sinir_30:
            son_30_gun_usd += maliyet
        if tarih in seri_map:
            seri_map[tarih]["maliyet_usd"] = round(seri_map[tarih]["maliyet_usd"] + maliyet, 6)
            seri_map[tarih]["gorev"] += 1

        onbellek_token += onbellek
        toplam_token += token

        ana_model = str(getattr(r, "son_model", "") or getattr(r, "model", "") or "").strip()
        if bulut_model_mi(ana_model) or (not ana_model and maliyet > 0):
            bulut_gorev += 1
        else:
            yerel_gorev += 1

        dokum = getattr(k, "model_dokumu", None) or {}
        if isinstance(dokum, dict) and dokum:
            tek_model = len(dokum) == 1
            for m_ad, d in dokum.items():
                ad = str(m_ad or ana_model or "?")
                kayit = model_map.setdefault(
                    ad,
                    {
                        "model": ad,
                        "cagri": 0,
                        "token": 0,
                        "onbellek_token": 0,
                        "maliyet_usd": 0.0,
                        "yerel": not bulut_model_mi(ad),
                    },
                )
                kayit["cagri"] += int((d or {}).get("cagri", 0) or 0)
                kayit["token"] += int((d or {}).get("token", 0) or 0)
                if tek_model:
                    kayit["onbellek_token"] += onbellek
                kayit["maliyet_usd"] = round(
                    kayit["maliyet_usd"] + float((d or {}).get("maliyet_usd", 0.0) or 0.0), 6
                )
        elif ana_model or token or maliyet or cagri:
            ad = ana_model or "?"
            kayit = model_map.setdefault(
                ad,
                {
                    "model": ad,
                    "cagri": 0,
                    "token": 0,
                    "onbellek_token": 0,
                    "maliyet_usd": 0.0,
                    "yerel": not bulut_model_mi(ad),
                },
            )
            kayit["cagri"] += cagri
            kayit["token"] += token
            kayit["onbellek_token"] += onbellek
            kayit["maliyet_usd"] = round(kayit["maliyet_usd"] + maliyet, 6)

        proje_id = str(getattr(r, "proje_id", "") or "(Projesiz)")
        pk = proje_map.setdefault(
            proje_id, {"proje_id": proje_id, "gorev": 0, "maliyet_usd": 0.0, "token": 0}
        )
        pk["gorev"] += 1
        pk["maliyet_usd"] = round(pk["maliyet_usd"] + maliyet, 6)
        pk["token"] += token

    gunluk_butce = float(getattr(ayar, "gunluk_butce_usd", 0.0) or 0.0)
    butce_yuzde = (
        min(100.0, round((bugun_usd / gunluk_butce) * 100, 1)) if gunluk_butce > 0 else None
    )
    toplam_gorev = yerel_gorev + bulut_gorev

    modeller_liste = sorted(
        model_map.values(), key=lambda x: (-x["maliyet_usd"], -x["token"], x["model"])
    )
    projeler_liste = sorted(
        proje_map.values(), key=lambda x: (-x["maliyet_usd"], -x["token"], x["proje_id"])
    )

    return {
        "bugun_usd": round(bugun_usd, 6),
        "son_7_gun_usd": round(son_7_gun_usd, 6),
        "son_30_gun_usd": round(son_30_gun_usd, 6),
        "toplam_usd": round(toplam_usd, 6),
        "gunluk_butce_usd": gunluk_butce,
        "butce_yuzde": butce_yuzde,
        "butce_asildi": bool(gunluk_butce > 0 and bugun_usd >= gunluk_butce),
        "gunluk_seri": list(seri_map.values()),
        "modeller": modeller_liste,
        "projeler": projeler_liste,
        "tasarruf": {
            "onbellek_token": onbellek_token,
            "toplam_token": toplam_token,
            "onbellek_orani": round((onbellek_token / toplam_token) * 100, 1)
            if toplam_token > 0
            else 0.0,
            "yerel_gorev": yerel_gorev,
            "bulut_gorev": bulut_gorev,
            "yerel_orani": round((yerel_gorev / toplam_gorev) * 100, 1)
            if toplam_gorev > 0
            else 0.0,
        },
    }
