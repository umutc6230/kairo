"""Ihtiyaca gore arac yukleme (arac_bul): MCP semalari ertelenir, bulunan ayni listeye eklenir."""

from __future__ import annotations

import json

import httpx
from conftest import SahteSunucu
from test_a3_ajan import proje  # noqa: F401 - fixture

from app.agent.arac_bul import ARAC_BUL, ertele
from app.services.sohbet import cevap_akit
from app.services.yerel_llm import YerelLLM


def _sema(ad: str, aciklama: str = "", boy: int = 0) -> dict:
    return {
        "type": "function",
        "function": {"name": ad, "description": aciklama + " " + "x" * boy, "parameters": {}},
    }


def _kur() -> tuple[list[dict], dict]:
    araclar = [_sema("proje_dosya_oku", "dosya okur")]
    araclar += [_sema(f"mcp__github__arac{i}", "github issue", 600) for i in range(30)]
    araclar += [_sema("mcp__windows-mcp__Process", "List running processes", 600)]
    isleyiciler = {"mcp__windows-mcp__Process": lambda **_: {"surecler": ["steam.exe"]}}
    return araclar, isleyiciler


def _adlar(araclar: list[dict]) -> list[str]:
    return [a["function"]["name"] for a in araclar]


def test_esik_altinda_dokunulmaz() -> None:
    araclar = [_sema("proje_dosya_oku"), _sema("mcp__fetch__fetch", "url getir")]
    ertele(araclar, {}, set())
    assert _adlar(araclar) == ["proje_dosya_oku", "mcp__fetch__fetch"]


def test_ertelenir_bulunan_ayni_listeye_eklenir() -> None:
    araclar, isl = _kur()
    ertele(araclar, isl, set())
    assert _adlar(araclar) == ["proje_dosya_oku", ARAC_BUL]
    aciklama = araclar[-1]["function"]["description"]
    assert "github (30)" in aciklama and "windows-mcp (1)" in aciklama

    sonuc = isl[ARAC_BUL](sorgu="running process")
    assert [x["arac"] for x in sonuc["yuklendi"]] == ["mcp__windows-mcp__Process"]
    assert "mcp__windows-mcp__Process" in _adlar(araclar)  # cevap_akit bu listeyi yollar
    assert _adlar(isl[ARAC_BUL].yuklenen) == ["mcp__windows-mcp__Process"]  # runner icin
    assert isl[ARAC_BUL](sorgu="process")["yuklendi"] == []  # ikinci kez yuklenmez

    secili = isl[ARAC_BUL](sorgu="select:mcp__github__arac3,mcp__github__arac7")
    assert {x["arac"] for x in secili["yuklendi"]} == {"mcp__github__arac3", "mcp__github__arac7"}
    assert "Sunucular: github" in isl[ARAC_BUL](sorgu="zzzz")["not"]


def test_gecmiste_cagrilan_yuklu_kalir() -> None:
    araclar, isl = _kur()
    ertele(araclar, isl, {"mcp__windows-mcp__Process"})
    assert _adlar(araclar) == ["proje_dosya_oku", "mcp__windows-mcp__Process", ARAC_BUL]


class _AraYukleCagir(SahteSunucu):
    """Model once arac_bul ile arar, sonra yuklenen araci gercek adiyla cagirir."""

    def _cevap(self, govde: dict) -> tuple[str, list | None]:
        sonuclar = [m for m in govde["messages"] if m["role"] == "tool"]
        if not sonuclar:
            arg = json.dumps({"sorgu": "process"})
            return "", [{"id": "b1", "type": "function",
                         "function": {"name": ARAC_BUL, "arguments": arg}}]  # fmt: skip
        if len(sonuclar) == 1:
            cagri = {"name": "mcp__windows-mcp__Process", "arguments": "{}"}
            return "", [{"id": "p1", "type": "function", "function": cagri}]
        icerik = sonuclar[-1]["content"]  # MCP sonucu dis kaynak zarfinda gelir
        return ("Calisan: steam.exe" if "steam.exe" in icerik else "sonuc yok"), None


async def test_cevap_akit_yuklenen_araci_sonraki_turda_yollar() -> None:
    sunucu = _AraYukleCagir()
    sunucu.dusunce = ""
    llm = YerelLLM(transport=httpx.MockTransport(sunucu))
    araclar, isl = _kur()
    ertele(araclar, isl, set())
    sonuc = await cevap_akit(
        llm, [{"role": "user", "content": "calisan uygulamalar"}], lambda o: None,
        araclar=araclar, isleyiciler=isl, max_tur=0,
    )  # fmt: skip
    gonderilen = [[t["function"]["name"] for t in i.get("tools") or []] for i in sunucu.istekler]
    assert "mcp__windows-mcp__Process" not in gonderilen[0]  # ilk istekte ertelenmis
    assert len(json.dumps(sunucu.istekler[0]["tools"])) < 3000  # 31 MCP semasi gitmedi
    assert "mcp__windows-mcp__Process" in gonderilen[1]  # bulunduktan sonra yuklu
    assert sonuc["metin"] == "Calisan: steam.exe"


async def test_ajan_gorevi_bulunan_araci_sonraki_turda_alir(tmp_path, proje) -> None:  # noqa: F811
    """Runner semalari kopyalayarak kurar: bulunan araclar bul.yuklenen ile her turda eklenmeli."""
    from test_a3_ajan import SahteModel, bitir, cagri, kur

    gorulen: list[list[str]] = []

    class Model(SahteModel):
        async def sohbet(self, mesajlar, **kw):
            gorulen.append([t["function"]["name"] for t in kw.get("tools") or []])
            return await super().sohbet(mesajlar, **kw)

    model = Model([cagri(ARAC_BUL, sorgu="process"), cagri("mcp__windows-mcp__Process")])
    runner, _, _, _ = kur(tmp_path, proje, model)
    asil = runner.araclar

    def baglam(hedef: str):
        sistem, semalar, isl = asil(hedef)
        mcp, mcp_isl = _kur()
        semalar, isl = [*semalar, *mcp[1:]], {**isl, **mcp_isl}
        ertele(semalar, isl, set())
        return sistem, semalar, isl

    runner.araclar = baglam
    run = await bitir(runner, (await runner.baslat("calisan uygulamalari bul")).id)

    assert ARAC_BUL in gorulen[0] and "mcp__windows-mcp__Process" not in gorulen[0]
    assert "mcp__windows-mcp__Process" in gorulen[1]
    assert any(
        a.arac == "mcp__windows-mcp__Process" and "steam.exe" in a.sonuc for a in run.adimlar
    )
