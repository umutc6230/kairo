"""video_uret: OpenRouter /videos is akisi (gonder -> yokla -> indir) ve sohbet araci isleyicisi."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.agent.policy import Istek, YanEtki, eylem_turu
from app.services.openrouter import OpenRouterDeposu, OpenRouterHatasi
from app.services.sohbet import SohbetServisi

MP4 = b"\x00\x00\x00\x18ftypmp42sahte"


def depo(tmp_path, isleyici) -> OpenRouterDeposu:
    d = OpenRouterDeposu(tmp_path, transport=httpx.MockTransport(isleyici))
    d.anahtar_kaydet("sk-or-v1-" + "a" * 40)
    return d


def test_video_gonder_yokla_indir(tmp_path):
    yoklama, istekler = iter(["in_progress", "completed"]), []

    def isleyici(r: httpx.Request) -> httpx.Response:
        istekler.append((r.method, r.url.path))
        if r.method == "POST":
            assert json.loads(r.content) == {"model": "m/v", "prompt": "fox", "duration": 4}
            return httpx.Response(200, json={"id": "j1", "status": "pending",
                                             "polling_url": "/api/v1/videos/j1"})  # fmt: skip
        if r.url.path.endswith("/content"):
            assert r.url.params["index"] == "0" and r.headers["authorization"].startswith("Bearer")
            return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})
        return httpx.Response(200, json={"id": "j1", "status": next(yoklama),
                                         "polling_url": "/api/v1/videos/j1",
                                         "usage": {"cost": 0.4}})  # fmt: skip

    beklemeler = []
    r = depo(tmp_path, isleyici).video_uret("m/v", "fox", 4, bekle=beklemeler.append)
    assert r == {"veri": MP4, "tur": "video/mp4", "maliyet_usd": 0.4}
    yoklama_yolu = ("GET", "/api/v1/videos/j1")
    assert istekler == [("POST", "/api/v1/videos"), yoklama_yolu, yoklama_yolu,
                        ("GET", "/api/v1/videos/j1/content")]  # fmt: skip
    assert len(beklemeler) == 2


def test_video_basarisiz_ve_zaman_asimi(tmp_path):
    def basarisiz(r):
        return httpx.Response(200, json={"id": "j", "status": "failed", "error": "icerik reddi"})

    with pytest.raises(OpenRouterHatasi, match="icerik reddi"):
        depo(tmp_path, basarisiz).video_uret("m", "x", bekle=lambda s: None)

    def hep_bekliyor(r):
        return httpx.Response(200, json={"id": "j", "status": "pending"})

    with pytest.raises(OpenRouterHatasi, match="bitmedi"):
        depo(tmp_path, hep_bekliyor).video_uret("m", "x", bekle=lambda s: None, en_fazla=3)

    def bakiye_yok(r):
        return httpx.Response(402, text="{}")

    with pytest.raises(OpenRouterHatasi, match="bakiyesi"):
        depo(tmp_path, bakiye_yok).video_uret("m", "x")


@pytest.mark.asyncio
async def test_video_model_listesi_ayri_onbellek(tmp_path):
    def isleyici(r: httpx.Request) -> httpx.Response:
        assert r.url.params.get("output_modalities") == "video"
        return httpx.Response(200, json={"data": [{"id": "x-ai/grok-imagine-video"}]})

    v = await depo(tmp_path, isleyici).modeller(cikti="video")
    assert [m["id"] for m in v["modeller"]] == ["x-ai/grok-imagine-video"]
    assert (tmp_path / "openrouter-video-modeller.json").exists()
    with pytest.raises(OpenRouterHatasi):
        await depo(tmp_path, isleyici).modeller(cikti="ses")


def test_isleyici_ucretli_onay_ve_yazma(tmp_path):
    hedef = tmp_path / "videolar" / "tilki.mp4"
    istekler = []

    def uygula(istek, alan):
        istekler.append(istek)
        return SimpleNamespace(cozulmus_yol=str(hedef))

    or_ = SimpleNamespace(video_uret=lambda m, i, s: {"veri": MP4, "tur": "video/mp4",
                                                      "maliyet_usd": 0.4})  # fmt: skip
    oz = SimpleNamespace(politika=SimpleNamespace(uygula=uygula), openrouter=or_)
    yap = SohbetServisi._video_uret_isleyici(
        oz, SimpleNamespace(), SimpleNamespace(video_model="x-ai/grok-imagine-video")
    )
    r = yap(istem="a fox running in snow", sure_sn=60, yol="videolar/tilki.mp4")
    assert hedef.read_bytes() == MP4 and r["maliyet_usd"] == 0.4 and r["sure_sn"] == 10
    i = istekler[0]
    assert i.yan_etki is YanEtki.dis and i.yol == "videolar/tilki.mp4"
    assert eylem_turu(i) == "odeme"  # tam yetkide de sorulur
    assert yap(istem=" ")["hata"]


def test_odeme_turu_tam_yetkide_sorulur():
    i = Istek(arac="video_uret", yan_etki=YanEtki.dis, ozet="Ucretli odeme: m ile 5 sn video")
    assert eylem_turu(i) == "odeme"  # ASCII Turkce de yakalanir
    assert eylem_turu(Istek(arac="odeme_yap", yan_etki=YanEtki.dis)) == "odeme"
