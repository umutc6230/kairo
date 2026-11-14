"""gorsel_uret: OpenRouter /images istemcisi, gorsel model listesi ve sohbet araci isleyicisi."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.services.openrouter import OpenRouterDeposu, OpenRouterHatasi
from app.services.sohbet import SohbetServisi

PNG = b"\x89PNG\r\n\x1a\nsahte"


def depo(tmp_path, isleyici) -> OpenRouterDeposu:
    d = OpenRouterDeposu(tmp_path, transport=httpx.MockTransport(isleyici))
    d.anahtar_kaydet("sk-or-v1-" + "a" * 40)
    return d


def test_gorsel_uret_basarili_ve_hata(tmp_path):
    istekler = []

    def isleyici(r: httpx.Request) -> httpx.Response:
        istekler.append(json.loads(r.content))
        if istekler[-1]["model"] == "pahali":
            return httpx.Response(402, text="{}")
        veri = {"data": [{"b64_json": base64.b64encode(PNG).decode(), "media_type": "image/png"}],
                "usage": {"cost": 0.01}}  # fmt: skip
        return httpx.Response(200, json=veri)

    d = depo(tmp_path, isleyici)
    r = d.gorsel_uret("m/x:free", "a red fox")
    assert r == {"veri": PNG, "tur": "image/png", "maliyet_usd": 0.01}
    assert istekler[0] == {"model": "m/x:free", "prompt": "a red fox"}
    with pytest.raises(OpenRouterHatasi, match="bakiyesi"):
        d.gorsel_uret("pahali", "x")


def test_anahtarsiz_gorsel_uret(tmp_path):
    with pytest.raises(OpenRouterHatasi, match="anahtari yok"):
        OpenRouterDeposu(tmp_path).gorsel_uret("m", "x")


@pytest.mark.asyncio
async def test_gorsel_model_listesi(tmp_path):
    def isleyici(r: httpx.Request) -> httpx.Response:
        assert r.url.params.get("output_modalities") == "image"
        modeller = [{"id": "a/b:free", "name": "B"}, {"id": "c/d", "name": "D"}]  # fiyat yok
        return httpx.Response(200, json={"data": modeller})

    v = await depo(tmp_path, isleyici).modeller(cikti="image")
    assert {m["id"]: m["ucretsiz"] for m in v["modeller"]} == {"a/b:free": True, "c/d": False}
    assert (tmp_path / "openrouter-gorsel-modeller.json").exists()
    assert not (tmp_path / "openrouter-modeller.json").exists()  # metin listesi ayri kalir


def isleyici_kur(tmp_path, tur="image/png", onay_hatasi=None):
    hedef = tmp_path / "gorseller" / "logo.png"

    def uygula(istek, alan):
        if onay_hatasi:
            raise onay_hatasi
        assert istek.arac == "gorsel_uret" and str(istek.yan_etki) == "yaz"
        return SimpleNamespace(cozulmus_yol=str(hedef))

    or_ = SimpleNamespace(gorsel_uret=lambda m, i: {"veri": PNG, "tur": tur, "maliyet_usd": 0})
    oz = SimpleNamespace(politika=SimpleNamespace(uygula=uygula), openrouter=or_,
                         _gorsel_saglayici=lambda ayar: "openrouter")  # fmt: skip
    ayar = SimpleNamespace(gorsel_model="m/x:free")
    return SohbetServisi._gorsel_uret_isleyici(oz, SimpleNamespace(), ayar), hedef


def test_isleyici_yazar_ve_uzantiyi_duzeltir(tmp_path):
    yap, hedef = isleyici_kur(tmp_path)
    r = yap(istem="minimal owl logo", yol="gorseller/logo.png")
    assert r["yol"] == str(hedef) and hedef.read_bytes() == PNG
    yap, hedef = isleyici_kur(tmp_path, tur="image/svg+xml")
    r = yap(istem="vector owl")
    assert r["yol"].endswith("logo.svg")
    assert yap(istem="  ")["hata"]


def test_isleyici_onay_bekler(tmp_path):
    from app.exceptions import OnayGerekli

    yap, hedef = isleyici_kur(tmp_path, onay_hatasi=OnayGerekli("Onay gerekli", {"id": "o1"}))
    r = yap(istem="owl")
    assert r["karar"] == "onay_bekliyor" and not hedef.exists()


@pytest.mark.asyncio
async def test_codex_gorsel_klasorden_ve_yedekten(tmp_path, monkeypatch):
    from app.agent import cli_ajan

    async def kopyalayan(saglayici, mesaj, klasor):
        assert saglayici == "codex" and "kirmizi tilki" in mesaj
        (klasor / "gorsel.png").write_bytes(PNG)
        return cli_ajan.CliSonuc(durum="basarili", oturum="t1")

    r = await cli_ajan.codex_gorsel_uret("kirmizi tilki", calistirici=kopyalayan)
    assert r == {"veri": PNG, "tur": "image/png", "maliyet_usd": None}

    # Codex kopyalamadi: ~/.codex/generated_images/<thread>/ yedegi
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    uretilen = tmp_path / ".codex" / "generated_images" / "t2"
    uretilen.mkdir(parents=True)
    (uretilen / "exec-1.webp").write_bytes(b"RIFF")

    async def kopyalamayan(saglayici, mesaj, klasor):
        return cli_ajan.CliSonuc(durum="basarili", oturum="t2")

    r = await cli_ajan.codex_gorsel_uret("x", calistirici=kopyalamayan)
    assert r["tur"] == "image/webp" and r["veri"] == b"RIFF"

    async def basarisiz(saglayici, mesaj, klasor):
        return cli_ajan.CliSonuc(durum="basarisiz", ozet="limit doldu", oturum="yok")

    with pytest.raises(RuntimeError, match="limit doldu"):
        await cli_ajan.codex_gorsel_uret("x", calistirici=basarisiz)


def test_saglayici_secimi(monkeypatch):
    from app.agent import cli_ajan

    or_ = SimpleNamespace(anahtar=lambda: "sk-or-x")
    oz = SimpleNamespace(openrouter=or_)
    sec = lambda **kw: SohbetServisi._gorsel_saglayici(  # noqa: E731
        oz, SimpleNamespace(gorsel_model="m", **kw)
    )
    monkeypatch.setattr(cli_ajan, "codex_komutu", lambda: ["codex"])
    assert sec(gorsel_saglayici="otomatik") == "codex"
    assert sec(gorsel_saglayici="openrouter") == "openrouter"
    monkeypatch.setattr(cli_ajan, "codex_komutu", lambda: None)
    assert sec(gorsel_saglayici="otomatik") == "openrouter"
    assert sec(gorsel_saglayici="codex") == ""
