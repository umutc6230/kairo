"""Onbellekte olmayan OpenRouter modeli: liste bir kez yenilenir, model aracsiz sanilmaz."""

from __future__ import annotations

import httpx

from app.agent.yetenek import uzak_yetenek
from app.services import openrouter as orm
from app.services.openrouter import OpenRouterDeposu

HAM = {"data": [{"id": "deepseek/v4", "name": "DeepSeek V4", "context_length": 128000,
                 "supported_parameters": ["tools", "response_format"],
                 "pricing": {"prompt": "0", "completion": "0"}}]}  # fmt: skip


def test_eksik_model_bir_kez_getirilir(tmp_path, monkeypatch):
    istekler = []

    def isle(r):
        istekler.append(str(r.url))
        return httpx.Response(200, json=HAM)

    gercek = httpx.Client
    monkeypatch.setattr(
        orm.httpx, "Client", lambda **k: gercek(transport=httpx.MockTransport(isle), **k)
    )
    d = OpenRouterDeposu(tmp_path)
    assert uzak_yetenek("deepseek/v4", d.liste_yolu).araclar is False  # onbellek yok
    d.eksik_modeli_getir("deepseek/v4")
    y = uzak_yetenek("deepseek/v4", d.liste_yolu)
    assert y.araclar is True and y.baglam == 128000
    d.eksik_modeli_getir("deepseek/v4")  # artik listede: aga cikilmaz
    d.eksik_modeli_getir("yok/model")  # 5 dk icinde tekrar aga cikilmaz (kota/yavaslik)
    assert len(istekler) == 1
