"""Yerel sunucu (Ollama + OpenAI uyumlu). Istekler GridMind'in Ollama istemcisinin gonderdigi
bicimde (crates/ai/src/ollama.rs: localize) kurulur."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from conftest import SahteSunucu

from app.main import bos_port
from app.services import agecidi as ag
from app.services.ayarlar import AyarDeposu
from app.services.model_yonetici import ModelYonetici
from app.services.yerel_llm import YerelLLM, YerelLLMHatasi

PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 20).decode()


@pytest.fixture
def gecit(veri, llm_dizin, sunucu: SahteSunucu):
    ayarlar = AyarDeposu(veri)
    ayarlar.guncelle({"llm_dizin": str(llm_dizin)})
    yonetici = ModelYonetici(
        ayarlar, lambda **kw: YerelLLM(transport=httpx.MockTransport(sunucu), **kw)
    )
    kapatildi = []
    uyg = ag.agecidi_uygulamasi(yonetici, ayarlar, kapat=lambda: kapatildi.append(1))
    uyg.state.kapatildi = kapatildi
    uyg.state.yonetici = yonetici
    return uyg


@pytest.fixture
async def gi(gecit):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gecit), base_url="http://127.0.0.1:11434"
    ) as c:
        yield c


def gridmind_govdesi(**ek) -> dict:
    """GridMind ollama::localize ciktisinin aynisi."""
    return {
        "model": "gemma4-e4b-heretic:latest",
        "messages": [
            {"role": "system", "content": "Sen GridMind asistanisin."},
            {"role": "user", "content": "Bu tabloya bak", "images": [PNG_B64]},
        ],
        "stream": False,
        "options": {"num_ctx": 8192, "num_predict": 300, "temperature": 0.1},
        **ek,
    }


async def test_kok_surum_etiketler_ve_show(gi):
    assert (await gi.get("/")).text.startswith("Ollama is running")
    v = (await gi.get("/api/version")).json()
    assert v["version"] == ag.OLLAMA_SURUMU and "kairo" in v
    adlar = [m["name"] for m in (await gi.get("/api/tags")).json()["models"]]
    assert adlar == [
        "deepseek-heretic:latest",
        "gemma4-12b-heretic:latest",
        "gemma4-e4b-heretic:latest",
    ]
    s = (await gi.post("/api/show", json={"model": "gemma4-e4b-heretic:latest"})).json()
    assert {"completion", "tools", "vision", "audio"} <= set(s["capabilities"])
    s = (await gi.post("/api/show", json={"name": "deepseek-heretic"})).json()
    assert "audio" not in s["capabilities"] and "vision" in s["capabilities"]
    r = await gi.post("/api/show", json={"model": "yok:latest"})
    assert r.status_code == 404 and "not found" in r.json()["error"]


async def test_gridmind_sohbet_istegi_cevrilir(gi, sunucu):
    sema = {"type": "object", "properties": {"x": {"type": "number"}}}
    r = await gi.post("/api/chat", json=gridmind_govdesi(format=sema))
    istek = sunucu.istekler[-1]
    assert istek["model"] == "gemma4-e4b-heretic" and istek["max_tokens"] == 300
    assert istek["temperature"] == 0.1 and istek["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    parca = istek["messages"][1]["content"]
    assert parca[0] == {"type": "text", "text": "Bu tabloya bak"}
    assert parca[1]["image_url"]["url"] == f"data:image/png;base64,{PNG_B64}"
    assert istek["response_format"]["json_schema"]["schema"] == sema
    c = r.json()
    assert (
        c["done"] is True
        and c["done_reason"] == "stop"
        and c["model"] == "gemma4-e4b-heretic:latest"
    )
    assert (
        c["message"]["role"] == "assistant"
        and c["eval_count"] == 12
        and c["prompt_eval_count"] == 30
    )
    await gi.post("/api/chat", json=gridmind_govdesi(format="json", think=True))
    assert sunucu.istekler[-1]["response_format"] == {"type": "json_object"}
    assert sunucu.istekler[-1]["chat_template_kwargs"] == {"enable_thinking": True}


async def test_arac_cagrisi_ollama_bicimine_doner_ve_geri_cevrilir(gi, sunucu):
    araclar = [
        {"type": "function", "function": {"name": "kur_getir", "parameters": {"type": "object"}}}
    ]
    govde = {
        "model": "deepseek-heretic",
        "messages": [{"role": "user", "content": "100 dolar kac TL?"}],
        "tools": araclar,
        "stream": False,
    }
    m = (await gi.post("/api/chat", json=govde)).json()["message"]
    assert m["tool_calls"] == [
        {"function": {"name": "kur_getir", "arguments": {"para_birimi": "USD"}}}
    ]
    # GridMind arac sonucunu kimliksiz gonderir: tool_call_id eslenmeli
    govde["messages"] += [
        {"role": "assistant", "content": "", "tool_calls": m["tool_calls"]},
        {"role": "tool", "content": '{"tl": 41.2}', "tool_name": "kur_getir"},
    ]
    son = (await gi.post("/api/chat", json=govde)).json()["message"]
    assert "51.500" in son["content"]
    giden = sunucu.istekler[-1]["messages"]
    assert giden[1]["tool_calls"][0]["function"]["arguments"] == '{"para_birimi": "USD"}'
    assert giden[2]["tool_call_id"] == giden[1]["tool_calls"][0]["id"]


async def test_chat_akisli_ndjson(gi, sunucu):
    r = await gi.post("/api/chat", json={**gridmind_govdesi(), "stream": True, "think": True})
    satirlar = [json.loads(s) for s in r.text.splitlines() if s]
    assert satirlar[-1]["done"] is True and all(not s["done"] for s in satirlar[:-1])
    assert satirlar[0]["message"]["thinking"] == sunucu.dusunce
    metin = "".join(s["message"]["content"] for s in satirlar[:-1])
    assert "HAKEDİŞ" in metin  # sahte sunucu resimli istege OCR metni doner
    assert r.headers["content-type"].startswith("application/x-ndjson")


async def test_chat_akista_arac_cagrisi_sonda(gi):
    govde = {
        "model": "deepseek-heretic",
        "messages": [{"role": "user", "content": "masaustu"}],
        "tools": [{"type": "function", "function": {"name": "klasor_listele"}}],
    }
    satirlar = [
        json.loads(s) for s in (await gi.post("/api/chat", json=govde)).text.splitlines() if s
    ]
    son = satirlar[-1]
    assert son["done"] and son["message"]["tool_calls"][0]["function"] == {
        "name": "klasor_listele",
        "arguments": {"yol": "masaustu"},
    }


async def test_generate_akissiz_ve_akisli(gi, sunucu):
    govde = {
        "model": "deepseek-heretic",
        "prompt": "Merhaba",
        "system": "Kisa yaz",
        "stream": False,
    }
    r = (await gi.post("/api/generate", json=govde)).json()
    assert r["response"] == "Merhaba, ben yerel modelim." and r["done"]
    assert sunucu.istekler[-1]["messages"][0] == {"role": "system", "content": "Kisa yaz"}
    akis = await gi.post("/api/generate", json={"model": "deepseek-heretic", "prompt": "Merhaba"})
    satirlar = [json.loads(s) for s in akis.text.splitlines() if s]
    assert "".join(s.get("response", "") for s in satirlar).startswith("Merhaba, ben")


async def test_openai_uclari(gi, sunucu):
    v = (await gi.get("/v1/models")).json()
    assert [m["id"] for m in v["data"]][0] == "deepseek-heretic" and "vision" in v["data"][0][
        "yetenekler"
    ]
    r = await gi.post(
        "/v1/chat/completions",
        json={"model": "gemma4-12b-heretic", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.json()["choices"][0]["message"]["content"] == "Merhaba, ben yerel modelim."
    assert sunucu.istekler[-1]["chat_template_kwargs"] == {"enable_thinking": False}
    govde = {
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    r = await gi.post("/v1/chat/completions", json=govde)
    assert r.text.rstrip().endswith("data: [DONE]") and '"content"' in r.text
    assert sunucu.istekler[-1]["model"] == "deepseek-heretic"  # model verilmedi: secili model
    assert sunucu.istekler[-1]["chat_template_kwargs"] == {"enable_thinking": True}
    r = await gi.post("/v1/chat/completions", json={"model": "yok", "messages": []})
    assert r.status_code == 404


async def test_hata_durumlari_ve_diger_uclar(gi, sunucu, gecit):
    assert (await gi.post("/api/chat", json={"model": "yok"})).status_code == 404
    assert (await gi.post("/api/pull", json={"model": "x"})).status_code == 400
    assert (await gi.get("/api/ps")).json() == {"models": []}
    await gi.post("/api/chat", json=gridmind_govdesi())
    assert (await gi.get("/api/ps")).json()["models"][0]["name"] == "gemma4-e4b-heretic:latest"
    sunucu.hata = (500, "boom")
    r = await gi.post("/api/chat", json=gridmind_govdesi())
    assert r.status_code == 503 and "500" in r.json()["error"]
    akis = await gi.post("/api/chat", json={**gridmind_govdesi(), "stream": True})
    assert "error" in json.loads(akis.text.splitlines()[-1])
    r = await gi.post("/v1/chat/completions", json={"model": "deepseek-heretic", "messages": []})
    assert r.status_code == 503
    r = await gi.post(
        "/v1/chat/completions", json={"model": "deepseek-heretic", "messages": [], "stream": True}
    )
    assert '"error"' in r.text and r.text.rstrip().endswith("[DONE]")
    assert (await gi.post("/api/yerel/kapat")).json() == {"kapat": True}
    assert gecit.state.istatistik["istek"] >= 5


def test_yardimcilar():
    assert ag.model_coz("deepseek-heretic:latest", "x") == "deepseek-heretic"
    assert ag.model_coz("", "secili") == "secili" and ag.model_coz("yok:latest", "x") is None
    assert ag._mime("/9j/abc") == "image/jpeg" and ag._mime("UklGRxyz") == "image/webp"
    assert ag._mime("R0lGODlh") == "image/gif" and ag._mime("iVBOR") == "image/png"
    assert ag._cagrilari_ollama([{"function": {"name": "a", "arguments": "bozuk{"}}]) == [
        {"function": {"name": "a", "arguments": {"_ham": "bozuk{"}}}
    ]
    assert ag._sse_satirlari('data: {"a":1}\n\ndata: [DONE]\ndata: {bozuk\n') == [{"a": 1}]


async def test_gercek_port_acma_cakisma_ve_kapatma(gecit):
    port = bos_port()
    g1 = ag.AgGecidi(gecit)
    assert await g1.baslat(port) and g1.acik
    async with httpx.AsyncClient() as c:
        v = (await c.get(f"http://127.0.0.1:{port}/api/version")).json()
    assert "kairo" in v
    d = g1.durum()
    assert d["ollama_adres"] == f"http://127.0.0.1:{port}" and d["openai_adres"].endswith("/v1")
    g2 = ag.AgGecidi(gecit)
    assert await g2.baslat(port) is False and "baska bir Kairo" in g2.hata
    await g1.durdur()
    assert not g1.acik and ag.port_bos(port)
    assert await ag.portu_kim_kullaniyor(port) == "baska bir program"


async def test_ayarlardan_sunucu_ac_kapat(istemci, app):
    port = bos_port()
    await istemci.put("/api/ayarlar", json={"sunucu_acik": False})
    r = await istemci.put("/api/ayarlar", json={"sunucu_acik": True, "sunucu_port": port})
    assert r.json()["sunucu_port"] == port
    d = (await istemci.get("/api/sunucu")).json()
    assert d["acik"] and d["port"] == port and d["ayar_acik"]
    assert (await istemci.post("/api/sunucu/yeniden")).json()["acik"]
    await istemci.put("/api/ayarlar", json={"sunucu_acik": False})
    assert not (await istemci.get("/api/sunucu")).json()["acik"]
    r = await istemci.put("/api/ayarlar", json={"sunucu_port": 80})
    assert r.status_code == 422


async def test_anthropic_uclari_claude_code_icin(gi, sunucu, gecit, monkeypatch):
    govde = {
        "model": "gemma4-e4b-heretic",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "selam"}],
    }
    r = (await gi.post("/v1/messages", json=govde)).json()
    assert r["content"][0]["text"] == "selam" and r["model"] == "gemma4-e4b-heretic"
    assert sunucu.istekler[-1]["chat_template_kwargs"] == {"enable_thinking": False}
    # Claude Code arka plan isleri 'claude-haiku-...' ister: acik model kullanilir (degisim yok)
    ek = {"model": "claude-haiku-4-5", "thinking": {"type": "enabled", "budget_tokens": 50}}
    await gi.post("/v1/messages", json={**govde, **ek})
    assert sunucu.istekler[-1]["model"] == "gemma4-e4b-heretic"
    assert "chat_template_kwargs" not in sunucu.istekler[-1]
    # Claude Code her istekte 'adaptive' ister: yerel modelde dusunme kapali kalir,
    # her istekte degisebilen billing satiri onbellegi bozmasin diye atilir
    claude_code = {
        "thinking": {"type": "adaptive"},
        "system": [
            {"type": "text", "text": "x-anthropic-billing-header: cc_version=2.1; cch=ab12;"},
            {"type": "text", "text": "You are Claude Code."},
        ],
    }
    await gi.post("/v1/messages", json={**govde, **claude_code})
    giden = sunucu.istekler[-1]
    assert "thinking" not in giden and giden["chat_template_kwargs"] == {"enable_thinking": False}
    assert giden["system"] == [{"type": "text", "text": "You are Claude Code."}]
    await gi.post("/v1/messages", json={**govde, "system": "x-anthropic-billing-header: a\nSen."})
    assert sunucu.istekler[-1]["system"] == "Sen."
    akis = await gi.post("/v1/messages", json={**govde, "stream": True})
    assert "event: message_start" in akis.text and "selam" in akis.text
    assert akis.headers["content-type"].startswith("text/event-stream")
    say = (await gi.post("/v1/messages/count_tokens", json=govde)).json()
    assert say == {"input_tokens": 42}
    r = await gi.post("/v1/messages", json={**govde, "model": "bilinmeyen-model"})
    assert r.status_code == 404 and r.json()["error"]["type"] == "not_found_error"
    m = (await gi.get("/v1/models")).json()["data"][0]
    assert m["type"] == "model" and m["display_name"]
    sunucu.hata = (500, "boom")
    assert (await gi.post("/v1/messages", json=govde)).status_code == 500
    akis = await gi.post("/v1/messages", json={**govde, "stream": True})
    assert "boom" in akis.text  # llama-server hatasi aynen gecer
    sunucu.hata = None

    async def acilamaz(model):
        raise YerelLLMHatasi("Model acilamadi")

    monkeypatch.setattr(gecit.state.yonetici, "_hazirla", acilamaz)
    r = await gi.post("/v1/messages", json={**govde, "model": "deepseek-heretic"})
    assert r.status_code == 503 and r.json()["type"] == "error"
    akis = await gi.post(
        "/v1/messages", json={**govde, "model": "deepseek-heretic", "stream": True}
    )
    assert akis.text.startswith("event: error")


async def test_agecidi_guvenlik_ve_kenar_durumlari(gi, gecit) -> None:
    # Host DNS rebinding / dis Origin engeli
    assert (await gi.get("/api/tags", headers={"host": "evil.test"})).status_code == 403
    assert (
        await gi.post("/api/chat", json={}, headers={"origin": "https://evil.test"})
    ).status_code == 403
    # DELETE /api/delete desteklenmiyor (400)
    assert (await gi.delete("/api/delete")).status_code == 400
    # thinking: null AttributeError vermemeli
    r = await gi.post(
        "/v1/messages",
        json={
            "model": "gemma4-e4b-heretic",
            "max_tokens": 50,
            "thinking": None,
            "messages": [{"role": "user", "content": "selam"}],
        },
    )
    assert r.status_code == 200
