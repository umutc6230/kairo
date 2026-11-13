"""OpenRouter seciliyken yerel (llama.cpp) model hicbir yoldan kullanilmaz."""

import pytest

from app.exceptions import UygulamaHatasi
from app.services.ayarlar import AyarDeposu
from app.services.model_yonetici import ModelYonetici
from app.services.yerel_llm import MODELLER


def _yonetici(tmp_path, **ayar):
    a = AyarDeposu(tmp_path)
    a.guncelle(ayar)
    acilan = []
    return ModelYonetici(a, lambda **kw: acilan.append(kw)), acilan


async def test_openrouter_modelsiz_yerele_dusmez(tmp_path):
    y, acilan = _yonetici(tmp_path, saglayici="openrouter", or_model="")
    with pytest.raises(UygulamaHatasi, match="OpenRouter modeli seç"):
        async with y.kullan():
            pass
    assert not acilan


async def test_openrouter_iken_acik_yerel_istek_reddedilir(tmp_path):
    y, acilan = _yonetici(tmp_path, saglayici="openrouter", or_model="x/y")
    with pytest.raises(UygulamaHatasi, match="yerel modeller kullanılmaz"):
        async with y.kullan(next(iter(MODELLER))):
            pass
    assert not acilan
