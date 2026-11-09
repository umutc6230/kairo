"""OpenRouter saglayicisi: anahtar, model listesi onbellegi, test, sohbetin uzak modele gitmesi.
Ag cagrilari MockTransport ile; gercek anahtar/istek yok."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from conftest import olaylar

from app.api import uygulama_olustur
from app.services.ayarlar import AyarDeposu
from app.services.openrouter import OpenRouterDeposu, OpenRouterHatasi, maskele

ANAHTAR = "sk-or-v1-" + "a" * 40
MODELLER = {
    "data": [
        {
            "id": "ucuz/model:free",
            "name": "Ucuz",
            "context_length": 32768,
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["tools", "reasoning"],
            "architecture": {"input_modalities": ["text", "image"]},
        },
        {
            "id": "pahali/model",
            "name": "Pahali",
            "context_length": 200000,
            "pricing": {"prompt": "0.000003", "completion": "0.000015"},
            "supported_parameters": ["structured_outputs"],
        },
    ]
}


class SahteOR:
    def __init__(self) -> None:
        self.istekler: list[httpx.Request] = []
        self.liste_hatasi = False

    def __call__(self, r: httpx.Request) -> httpx.Response:
        self.istekler.append(r)
        if r.url.path.endswith("/models"):
            return httpx.Response(500) if self.liste_hatasi else httpx.Response(200, json=MODELLER)
        if r.headers.get("authorization") != f"Bearer {ANAHTAR}":
            return httpx.Response(401, json={"error": {"message": "no auth"}})
        govde = json.loads(r.content)
        if govde.get("stream"):
            satirlar = [
                ": OPENROUTER PROCESSING",
                'data: {"choices":[{"delta":{"reasoning":"dusun"}}]}',
                'data: {"choices":[{"delta":{"content":"Merhaba"}}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ]
            return httpx.Response(200, text="\n\n".join(satirlar) + "\n\n")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "tamam"}, "finish_reason": "stop"}],
                "usage": {"cost": 0.00001},
            },
        )


@pytest.fixture
def sahte() -> SahteOR:
    return SahteOR()


@pytest.fixture
def depo(tmp_path: Path, sahte: SahteOR) -> OpenRouterDeposu:
    return OpenRouterDeposu(tmp_path, transport=httpx.MockTransport(sahte))


def test_anahtar_kaydet_maskele_sil(depo: OpenRouterDeposu) -> None:
    assert depo.anahtar_durumu() == {"var": False, "maskeli": ""}
    with pytest.raises(OpenRouterHatasi):
        depo.anahtar_kaydet("yanlis-anahtar")
    d = depo.anahtar_kaydet(f"  {ANAHTAR} ")
    assert d["var"] and ANAHTAR not in d["maskeli"] and d["maskeli"] == maskele(ANAHTAR)
    assert depo.anahtar() == ANAHTAR
    assert depo.anahtar_sil()["var"] is False


async def test_model_listesi_sadelesir_ve_onbellege_alinir(depo, sahte) -> None:
    v = await depo.modeller()
    ucuz, pahali = sorted(v["modeller"], key=lambda m: m["id"], reverse=True)
    assert ucuz["ucretsiz"] and ucuz["araclar"] and ucuz["goruntu"] and ucuz["baglam"] == 32768
    assert not pahali["ucretsiz"] and pahali["json"] and pahali["giris_1m"] == 3.0
    await depo.modeller()  # taze onbellek: ag cagrisi yok
    assert len(sahte.istekler) == 1
    await depo.modeller(yenile=True)
    assert len(sahte.istekler) == 2


async def test_ag_hatasinda_eski_liste_uyariyla_doner(depo, sahte) -> None:
    await depo.modeller()
    eski = json.loads(depo.liste_yolu.read_text(encoding="utf-8"))
    eski["zaman"] = time.time() - 2 * 24 * 3600  # bayat
    depo.liste_yolu.write_text(json.dumps(eski), encoding="utf-8")
    sahte.liste_hatasi = True
    v = await depo.modeller()
    assert v["uyari"] and len(v["modeller"]) == 2


async def test_onbellek_yokken_ag_hatasi_turkce(depo, sahte) -> None:
    sahte.liste_hatasi = True
    with pytest.raises(OpenRouterHatasi, match="alinamadi"):
        await depo.modeller()


async def test_test_istegi_arac_ve_maliyet(depo, sahte) -> None:
    depo.anahtar_kaydet(ANAHTAR)
    s = await depo.test("ucuz/model:free")
    assert s["tamam"] and s["cevap"] == "tamam" and s["maliyet_usd"] == 0.00001
    govde = json.loads(sahte.istekler[-1].content)
    assert govde["tools"] and govde["usage"] == {"include": True}
    assert "chat_template_kwargs" not in govde and govde["reasoning"] == {"enabled": False}


async def test_anahtarsiz_ve_gecersiz_anahtar(depo, sahte) -> None:
    with pytest.raises(OpenRouterHatasi, match="girilmemis"):
        await depo.test("x/y")
    depo.anahtar_kaydet("sk-or-v1-" + "b" * 40)
    with pytest.raises(OpenRouterHatasi, match="gecersiz"):
        await depo.test("x/y")


@pytest.fixture
async def or_istemci(veri: Path, sahte: SahteOR):
    app = uygulama_olustur(veri, or_transport=httpx.MockTransport(sahte))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"X-YAS-Oturum": app.state.oturum_anahtari},
    ) as c:
        yield c


async def test_api_anahtar_hic_acik_gitmez(or_istemci) -> None:
    r = await or_istemci.put("/api/openrouter/anahtar", json={"anahtar": ANAHTAR})
    assert r.status_code == 200 and ANAHTAR not in r.text
    assert ANAHTAR not in (await or_istemci.get("/api/openrouter/anahtar")).text
    assert ANAHTAR not in (await or_istemci.get("/api/ayarlar")).text
    assert (await or_istemci.delete("/api/openrouter/anahtar")).json()["var"] is False


async def test_sohbet_openrouter_modeline_gider(or_istemci, veri: Path, sahte) -> None:
    await or_istemci.put("/api/openrouter/anahtar", json={"anahtar": ANAHTAR})
    AyarDeposu(veri).guncelle(
        {"saglayici": "openrouter", "or_model": "ucuz/model:free", "sohbet_araclari": False}
    )
    o = (await or_istemci.post("/api/oturumlar")).json()["id"]
    r = await or_istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "selam"})
    tum = olaylar(r.text)
    assert not [x for x in tum if x["tur"] == "hata"], tum
    metin = "".join(x.get("metin", "") for x in tum if x["tur"] == "parca")
    assert "Merhaba" in metin
    sohbet = [i for i in sahte.istekler if i.url.path.endswith("/chat/completions")]
    assert sohbet and json.loads(sohbet[-1].content)["model"] == "ucuz/model:free"
    assert str(sohbet[-1].url).startswith("https://openrouter.ai/api/v1/")


def test_ayar_aktif_model() -> None:
    from app.services.ayarlar import KullaniciAyarlari

    a = KullaniciAyarlari(saglayici="openrouter", or_model="x/y")
    assert a.aktif_model == "x/y"
    assert KullaniciAyarlari(saglayici="openrouter").aktif_model == a.model  # secim yoksa yerel
