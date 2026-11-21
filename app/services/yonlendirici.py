"""Akilli maliyet ve gizlilik yonlendiricisi: gizli projede veya gunluk butce asiminda
bulut model isteklerini yerel modele yonlendirir.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

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


def gunluk_maliyet_usd(run_deposu) -> float:
    """Bugun baslatilan gorevlerin toplam maliyeti (USD)."""
    bugun = datetime.now().date().isoformat()
    toplam = 0.0
    for r in run_deposu.liste():
        if str(getattr(r, "olusturma", "")).startswith(bugun):
            kullanim = getattr(r, "kullanim", None)
            if kullanim is not None:
                toplam += float(getattr(kullanim, "maliyet_usd", 0.0) or 0.0)
    return round(toplam, 6)


def model_sec(
    istenen_model: str,
    ayar: KullaniciAyarlari,
    alan: CalismaAlani | None,
    bugun_usd: float = 0.0,
) -> tuple[str, str | None]:
    """Gizlilik ve gunluk butce kurallarina gore etkin modeli ve varsa uyariyi doner."""
    if alan is not None and getattr(alan, "gizli_proje", False) and bulut_model_mi(istenen_model):
        return (
            ayar.model,
            f"Gizli proje kurali: bulut modeli ({istenen_model}) yerine "
            f"yerel model ({ayar.model}) kullaniliyor.",
        )
    if (
        ayar.gunluk_butce_usd > 0
        and bugun_usd >= ayar.gunluk_butce_usd
        and bulut_model_mi(istenen_model)
    ):
        return (
            ayar.model,
            f"Gunluk butce siniri (${ayar.gunluk_butce_usd:.2f}, harcanan ${bugun_usd:.2f}) "
            f"asildi: yerel model ({ayar.model}) kullaniliyor.",
        )
    return istenen_model, None
