"""Ollama saglayicisi ve magazasi: ayristirma, istek govdesi, yonlendirme, indirme/silme (mock)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.services import ollama as ol
from app.services.ayarlar import KullaniciAyarlari

ARAMA = """
<li class="x"><a href="/library/qwen3.8" class="group">
  <h2 title="qwen3.8"><span>qwen3.8</span></h2>
  <span class="flex-none" title="Updated November 8, 2026">1w</span>
  <span  class="inline-flex rounded-md bg-indigo-50">vision</span>
  <span  class="inline-flex rounded-md bg-indigo-50">tools</span>
  <p class="mt-1">Kodlama &amp; ajan isleri.</p>
  <span class="tabular-nums" title="6,826,360 downloads"><span>6.8M</span></span>
  <span class="inline-flex"><svg></svg><span >13 tags</span></span>
  <span  class="inline-flex rounded-md bg-[#ddf4ff]">27b</span>
</a></li>
<li><a href="/library/bulut-model" class="group"><h2>bulut-model</h2>
  <span  class="inline-flex rounded-md bg-indigo-50">cloud</span><p>Bulut.</p></a></li>
<div hx-get="/search?page=2&q=qwen"></div>
"""

ETIKET = """
<a href="/library/lfm3:1.7b" class="md:hidden flex flex-col group">
  <span class="group-hover:underline">lfm3:1.7b</span>
  <span class="font-mono">abcdef012345</span> • 1.1GB • 256K context window •
  <span class="hidden sm:inline">Text input • 2 weeks ago</span>
  <div class="flex sm:hidden">Text input • 2 weeks ago</div></a>
<a href="/library/lfm3:1.7b-mlx" class="md:hidden flex"><span>lfm3:1.7b-mlx</span> MLX
  <span class="font-mono">0123456789ab</span> • 3.5GB • 128K context window •
  Text, Image input • 3 weeks ago</a>
"""


def test_arama_ayristirilir() -> None:
    sonuc, daha = ol.arama_ayristir(ARAMA)
    assert daha is True
    q = sonuc[0]
    assert q["ad"] == "qwen3.8" and q["yetenekler"] == ["vision", "tools"]
    assert q["boyutlar"] == ["27b"] and q["indirme"] == 6826360 and q["etiket_sayisi"] == 13
    assert q["aciklama"] == "Kodlama & ajan isleri." and q["guncelleme"] == "November 8, 2026"
    assert sonuc[1]["yetenekler"] == ["cloud"] and sonuc[1]["boyutlar"] == []


def test_etiketler_ayristirilir_mobil_tekrar_tek_sayilir() -> None:
    e = ol.etiket_ayristir(ETIKET, "lfm3")
    assert [x["etiket"] for x in e] == ["1.7b", "1.7b-mlx"]
    assert e[0] | {} == e[0] and e[0]["boyut_gb"] == 1.1 and e[0]["baglam"] == "256K"
    assert e[0]["girdi"] == "Text" and e[0]["guncelleme"] == "2 weeks ago" and not e[0]["mlx"]
    assert e[1]["mlx"] and e[1]["girdi"] == "Text, Image" and e[1]["boyut_gb"] == 3.5


def test_aktif_model_ollama_onekli() -> None:
    a = KullaniciAyarlari(saglayici="ollama", ollama_model="qwen3:8b")
    assert a.aktif_model == "ollama:qwen3:8b"
    assert KullaniciAyarlari(saglayici="ollama").aktif_model == a.model  # secim yoksa yerel


def test_govde_llama_alanlari_yok_dusunme_efor() -> None:
    llm = ol.OllamaLLM("http://x", "m", dusunur=True)
    g = llm._govde([{"role": "user", "content": "a"}], "derin", 64)
    assert "chat_template_kwargs" not in g and "thinking_budget_tokens" not in g
    assert g["reasoning_effort"] == "high" and llm.adres == "http://x/v1"
    g = ol.OllamaLLM("http://x", "m", dusunur=False)._govde([], "derin", 64)
    assert "reasoning_effort" not in g  # dusunmeyen modele gonderilirse Ollama 400 doner


def _sahte_ollama(kayit: list) -> httpx.MockTransport:
    def isle(istek: httpx.Request) -> httpx.Response:
        kayit.append((istek.method, istek.url.path, istek.content))
        yol = istek.url.path
        if yol == "/api/version":
            return httpx.Response(200, json={"version": "0.40.0"})
        if yol == "/api/tags":
            return httpx.Response(200, json={"models": [{
                "name": "lfm3:1.7b", "size": 1_073_741_824, "modified_at": "2026-11-18T09:00",
                "details": {"family": "lfm3", "parameter_size": "1.7B", "quantization_level": "Q4"},
            }]})  # fmt: skip
        if yol == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "lfm3:1.7b"}]})
        if yol == "/api/show":
            return httpx.Response(200, json={
                "capabilities": ["completion", "tools", "thinking"],
                "model_info": {"lfm3.context_length": 262144}, "details": {},
            })  # fmt: skip
        if yol == "/api/delete":
            return httpx.Response(200)
        if yol == "/api/pull":
            satirlar = [
                {"status": "pulling", "digest": "a", "total": 100, "completed": 50},
                {"status": "pulling", "digest": "a", "total": 100, "completed": 100},
                {"status": "pulling", "digest": "b", "total": 20, "completed": 20},
                {"status": "success"},
            ]
            return httpx.Response(200, content="\n".join(json.dumps(s) for s in satirlar))
        if yol == "/v1/chat/completions":
            return httpx.Response(200, json={"choices": [
                {"message": {"role": "assistant", "content": "tamam"}, "finish_reason": "stop"}
            ]})  # fmt: skip
        return httpx.Response(404, json={"error": "yok"})

    return httpx.MockTransport(isle)


@pytest.fixture
def servis():
    kayit: list = []
    return ol.Ollama(
        lambda: "http://127.0.0.1:11435", lambda: 16384, transport=_sahte_ollama(kayit)
    ), kayit


async def test_yuklu_detay_yetenek_ve_sil(servis) -> None:
    o, kayit = servis
    y = await o.yuklu()
    assert y[0]["anahtar"] == "ollama:lfm3:1.7b" and y[0]["acik"] and y[0]["boyut_gb"] == 1.0
    d = await o.detay("lfm3:1.7b")
    assert d["baglam"] == 262144
    assert o.yetenekler["lfm3:1.7b"] == {
        "araclar": True,
        "goruntu": False,
        "dusunme": True,
        "baglam": 262144,
    }
    await o.sil("lfm3:1.7b")
    assert ("DELETE", "/api/delete", b'{"model":"lfm3:1.7b"}') in kayit
    assert "lfm3:1.7b" not in o.yetenekler


async def test_indirme_ilerlemesi_ve_gecersiz_ad(servis) -> None:
    o, _ = servis
    with pytest.raises(ol.OllamaHatasi):
        await o.indir("kotu ad; rm")
    i = await o.indir("lfm3:1.7b")
    await i.gorev
    assert i.durum == "bitti" and i.toplam == 120 and i.ozet()["yuzde"] == 100  # katmanlar toplanir


async def test_kairo_gecidi_gercek_ollama_sayilmaz() -> None:
    t = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"version": "0.12.0", "kairo": "0.1"})
    )
    o = ol.Ollama(lambda: "http://127.0.0.1:11434", lambda: 8192, transport=t)
    assert await o.surum() is None


async def test_model_yonetici_ollama_modelini_yonlendirir(tmp_path, servis) -> None:
    from app.services.ayarlar import AyarDeposu
    from app.services.model_yonetici import ModelYonetici

    o, kayit = servis
    yon = ModelYonetici(AyarDeposu(tmp_path), ollama=o)
    async with yon.kullan("ollama:lfm3:1.7b") as llm:
        assert isinstance(llm, ol.OllamaLLM) and llm.model == "lfm3:1.7b" and llm.dusunur
        cevap = await llm.sohbet([{"role": "user", "content": "x"}], max_tokens=16)
    assert cevap["message"]["content"] == "tamam"
    govde = json.loads(next(c for m, y, c in kayit if y == "/v1/chat/completions"))
    assert govde["model"] == "lfm3:1.7b"


async def test_sonraki_oneri_ucu(istemci, app) -> None:
    from contextlib import asynccontextmanager

    gelen = []

    class Sahte:
        async def json_cikti(self, istem, *_a, **_k):
            gelen.append(istem)
            return {"oneri": "  main'e birlestir ve DURUM.md guncelle. "}

    @asynccontextmanager
    async def kullan(*_a, **_k):
        yield Sahte()

    app.state.yonetici.kullan = kullan
    bos = await istemci.post("/api/sonraki-oneri", json={"kullanici": "x", "asistan": " "})
    assert bos.json() == {"oneri": ""} and not gelen  # asistan cevabi yoksa model cagrilmaz
    r = await istemci.post(
        "/api/sonraki-oneri",
        json={"kullanici": "derle", "asistan": "Teslim edildi; main birlesmedi."},
    )
    assert r.json() == {"oneri": "main'e birlestir ve DURUM.md guncelle"}
    assert "main birlesmedi" in gelen[0]

    @asynccontextmanager
    async def bozuk(*_a, **_k):
        raise RuntimeError("model kapali")
        yield

    app.state.yonetici.kullan = bozuk
    assert (await istemci.post("/api/sonraki-oneri", json={"asistan": "a"})).json() == {"oneri": ""}


async def test_sonraki_oneri_etiket_ve_tekrar_temizlenir(istemci, app) -> None:
    from contextlib import asynccontextmanager

    cevaplar = iter(["BIR SONRAKI mesaji: Testleri calistir", "'derle ve teslim et"])

    class Sahte:
        async def json_cikti(self, *_a, **_k):
            return {"oneri": next(cevaplar)}

    @asynccontextmanager
    async def kullan(*_a, **_k):
        yield Sahte()

    app.state.yonetici.kullan = kullan
    govde = {"kullanici": "Derle ve teslim et", "asistan": "Teslim edildi."}
    assert (await istemci.post("/api/sonraki-oneri", json=govde)).json()[
        "oneri"
    ] == "Testleri calistir"
    assert (await istemci.post("/api/sonraki-oneri", json=govde)).json()["oneri"] == ""


def test_ollama_baglami_ajan_talimatina_yeter() -> None:
    # canli: 16K bagamda talimat 12K + arac 5.7K sigmadi, gorev 0 adimda basarisiz oldu
    assert ol.ollama_baglam(16384) == 32768 and ol.ollama_baglam(65536) == 65536
