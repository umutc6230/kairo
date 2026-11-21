"""OpenAI uyumlu saglayicilar: anahtar saklama, model listesi, yonlendirme, hata siniflama.
Ag cagrilari MockTransport ile; gercek anahtar/istek yok."""

import asyncio
import json

import httpx
import pytest

from app.services.ayarlar import AyarDeposu
from app.services.model_yonetici import ModelYonetici
from app.services.saglayicilar import SaglayiciDeposu, SaglayiciHatasi, UyumluLLM, ayir

ANAHTAR = "gsk_gizli1234567890abcd"


def _depo(tmp_path, istekler=None, durum=200):
    def sahte(istek: httpx.Request) -> httpx.Response:
        if istekler is not None:
            istekler.append(istek)
        if istek.url.path.endswith("/models"):
            return httpx.Response(
                durum, json={"data": [{"id": "llama-3", "context_window": 131072}]}
            )
        govde = json.loads(istek.content)
        assert "reasoning" not in govde and "chat_template_kwargs" not in govde
        return httpx.Response(durum, json={
            "choices": [{"message": {"content": "tamam"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 12}})  # fmt: skip

    return SaglayiciDeposu(tmp_path, transport=httpx.MockTransport(sahte))


def test_ayir():
    assert ayir("groq:llama-3") == ("groq", "llama-3")
    assert ayir("meta/llama:free") is None  # OpenRouter kimligi
    assert ayir("groq:") is None


def test_anahtar_sifreli_saklanir_ve_maskeli_doner(tmp_path):
    d = _depo(tmp_path)
    durum = {s["id"]: s for s in d.kaydet("groq", ANAHTAR)}
    assert durum["groq"]["anahtar"] == {
        "var": True,
        "maskeli": "gsk_gi...abcd",
        "kaynak": "kayitli",
    }
    assert ANAHTAR not in (tmp_path / "saglayici-anahtarlari.json").read_text(encoding="utf-8")
    assert ANAHTAR not in json.dumps(d.durum())
    assert d.anahtar("groq") == (ANAHTAR, "kayitli")
    d.sil("groq")
    assert d.anahtar("groq") == ("", "")


def test_ortam_degiskeni_tirnak_soyulur(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", f'"{ANAHTAR}"')
    assert _depo(tmp_path).anahtar("groq") == (ANAHTAR, "ortam")


def test_gecersiz_girdiler(tmp_path):
    d = _depo(tmp_path)
    with pytest.raises(SaglayiciHatasi):
        d.kaydet("yok", ANAHTAR)
    with pytest.raises(SaglayiciHatasi):
        d.kaydet("groq", "a b")
    with pytest.raises(SaglayiciHatasi):
        d.kaydet("groq", ANAHTAR, adres="http://baska")  # sabit adresli saglayici
    with pytest.raises(SaglayiciHatasi):
        d.kaydet("ozel", adres="file:///c:/x")
    d.kaydet("ozel", adres="http://127.0.0.1:8000/v1/")
    assert d.adres("ozel") == "http://127.0.0.1:8000/v1"


async def test_modeller_ve_onbellek(tmp_path):
    istekler = []
    d = _depo(tmp_path, istekler)
    d.kaydet("groq", ANAHTAR)
    v = await d.modeller("groq")
    assert v["modeller"] == [{"id": "llama-3", "ad": "llama-3", "baglam": 131072}]
    assert istekler[0].headers["authorization"] == f"Bearer {ANAHTAR}"
    await d.modeller("groq")
    assert len(istekler) == 1  # 24 saat taze
    assert d.model_bilgisi("groq:llama-3")["baglam"] == 131072


async def test_anahtarsiz_istemci_reddedilir(tmp_path):
    with pytest.raises(SaglayiciHatasi, match="anahtarı girilmemiş"):
        _depo(tmp_path).istemci("openai:gpt-x")


async def test_test_istegi_ve_hata_siniflama(tmp_path):
    d = _depo(tmp_path)
    d.kaydet("groq", ANAHTAR)
    t = await d.test("groq:llama-3")
    assert t["cevap"] == "tamam" and t["token"] == 12
    kotu = _depo(tmp_path, durum=401)
    with pytest.raises(SaglayiciHatasi, match="Groq API anahtarı geçersiz"):
        await kotu.test("groq:llama-3")


def test_hata_429_gecici():
    llm = UyumluLLM("Groq", "https://x/v1", "", "m")
    with pytest.raises(SaglayiciHatasi) as e:
        llm._hata_firlat(429, "")
    assert e.value.gecici


async def test_model_yonetici_uyumlu_yonlendirir(tmp_path):
    a = AyarDeposu(tmp_path)
    a.guncelle({"saglayici": "uyumlu", "uyumlu_model": "groq:llama-3"})
    d = _depo(tmp_path)
    d.kaydet("groq", ANAHTAR)
    y = ModelYonetici(a, lambda **kw: pytest.fail("yerel acilmamali"), uyumlu=d)
    assert a.oku().aktif_model == "groq:llama-3"
    async with y.kullan() as llm:
        assert isinstance(llm, UyumluLLM) and llm.model == "llama-3"


def test_nvidia_nim_model_listesi_ve_sohbet(tmp_path):
    istekler: list = []
    d = _depo(tmp_path, istekler)
    d.kaydet("nvidia", "nvapi-gizli1234567890abcd")
    veri = asyncio.run(d.modeller("nvidia"))
    assert veri["modeller"][0]["id"] == "llama-3"
    assert str(istekler[0].url) == "https://integrate.api.nvidia.com/v1/models"
    assert istekler[0].headers["authorization"] == "Bearer nvapi-gizli1234567890abcd"
    assert d.istemci("nvidia:meta/llama-3.1-8b-instruct").model == "meta/llama-3.1-8b-instruct"
