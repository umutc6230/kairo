"""Tam yetki modu, web aramasi izni, masaustu '*' ve OpenRouter zorunlu dusunme."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.agent.policy import Istek, Karar, PolitikaMotoru, YanEtki
from app.agent.workspaces import CalismaAlani, Guven, Mod


def _motor(tmp_path: Path, tam: bool, ag: bool = True) -> PolitikaMotoru:
    m = PolitikaMotoru(tmp_path)
    m.tam_yetki = lambda: tam
    m.kullanici_ag = lambda: ag
    return m


def _alan(tmp_path: Path, mod: Mod = Mod.onayli, guven: Guven = Guven.sinirli) -> CalismaAlani:
    return CalismaAlani(id="a" * 12, kokler=[str(tmp_path)], mod=mod, guven=guven)


@pytest.mark.parametrize("etki", [YanEtki.yaz, YanEtki.komut, YanEtki.dis, YanEtki.git])
def test_tam_yetki_sormadan_izin(tmp_path: Path, etki: YanEtki) -> None:
    alan = _alan(tmp_path)
    ist = Istek(arac="x", yan_etki=etki, komut="npm test")
    assert _motor(tmp_path, False).degerlendir(ist, alan).karar is Karar.sor
    assert _motor(tmp_path, True).degerlendir(ist, alan).karar is Karar.izin


@pytest.mark.parametrize(
    "komut", ["rm -rf /", "format D:", "git push --force origin main", "shutdown /s /t 0"]
)
def test_tam_yetkide_tehlikeli_komut_sorar(tmp_path: Path, komut: str) -> None:
    ist = Istek(arac="terminal", yan_etki=YanEtki.komut, komut=komut)
    assert _motor(tmp_path, True).degerlendir(ist, _alan(tmp_path)).karar is Karar.sor


def test_tam_yetki_planla_ve_hassas_dosyayi_asmaz(tmp_path: Path) -> None:
    m = _motor(tmp_path, True)
    ist = Istek(arac="yaz", yan_etki=YanEtki.yaz, yol=str(tmp_path / "a.txt"))
    assert m.degerlendir(ist, _alan(tmp_path, Mod.planla)).karar is Karar.ret
    env = Istek(arac="oku", yan_etki=YanEtki.oku, yol=str(tmp_path / ".env"))
    assert m.degerlendir(env, _alan(tmp_path)).karar is Karar.ret


def test_web_aramasi_onaysiz_diger_siteler_sorar(tmp_path: Path) -> None:
    m, alan = _motor(tmp_path, False), _alan(tmp_path)
    ara = Istek(arac="web_getir", yan_etki=YanEtki.ag, host="html.duckduckgo.com")
    site = Istek(arac="web_getir", yan_etki=YanEtki.ag, host="example.com")
    assert m.degerlendir(ara, alan).karar is Karar.izin
    assert m.degerlendir(site, alan).karar is Karar.sor
    assert _motor(tmp_path, True).degerlendir(site, alan).karar is Karar.izin
    assert _motor(tmp_path, True, ag=False).degerlendir(site, alan).karar is Karar.ret


def test_masaustu_yildiz_tum_programlar_guvenlik_haric(monkeypatch) -> None:
    from app.agent import masaustu as ms

    m = ms.Masaustu(lambda: ["*"])
    e = type("E", (), {"CurrentProcessId": 1})()
    monkeypatch.setattr(ms, "_exe_adi", lambda pid: "chrome.exe")
    assert m._izinli_mi(e) == "chrome.exe"
    monkeypatch.setattr(ms, "_exe_adi", lambda pid: "consent.exe")
    assert m._izinli_mi(e) == ""


def test_openrouter_zorunlu_dusunme_yeniden_dener() -> None:
    from app.services.openrouter import ZORUNLU_DUSUNME, OpenRouterLLM

    gelen = []

    def h(r: httpx.Request) -> httpx.Response:
        v = json.loads(r.content)
        gelen.append(v.get("reasoning"))
        if v["reasoning"] == {"enabled": False}:
            return httpx.Response(400, json={"error": {"message": "Reasoning is mandatory"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    llm = OpenRouterLLM("sk-or-xxxxxxxxxxxx", "test/zorunlu", transport=httpx.MockTransport(h))
    sonuc = asyncio.run(llm.sohbet([{"role": "user", "content": "a"}]))
    assert sonuc["message"]["content"] == "ok"
    assert gelen == [{"enabled": False}, {"effort": "low"}]
    assert "test/zorunlu" in ZORUNLU_DUSUNME
