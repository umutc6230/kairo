"""A1-A5 eksiklik giderme regresyon testleri."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from app.agent.runner import AgentRunner, Butce, RunDeposu
from app.agent.workspaces import CalismaAlani, Mod
from app.main import _baglanti_sil, _baglanti_yaz
from app.services.ayarlar import KullaniciAyarlari
from app.services.oturumlar import Mesaj, OturumDeposu
from app.services.saglayicilar import SaglayiciDeposu, SaglayiciHatasi, UyumluLLM
from app.services.yerel_llm import MODELLER
from app.services.yonlendirici import gunluk_maliyet_usd, model_sec, yerel_yedek_model


def test_baglanti_json_yaz_ve_sil(tmp_path: Path) -> None:
    yol = _baglanti_yaz(tmp_path, 51234, "gizli-oturum-123")
    assert yol.is_file()
    veri = json.loads(yol.read_text(encoding="utf-8"))
    assert veri["url"] == "http://127.0.0.1:51234"
    assert veri["port"] == 51234
    assert veri["oturum_anahtari"] == "gizli-oturum-123"
    _baglanti_sil(yol)
    assert not yol.exists()


@pytest.mark.asyncio
async def test_editor_baglam_sohbet_sistemine_girer_ve_silinir(
    tmp_path: Path, app, istemci
) -> None:
    await istemci.post(
        "/api/editor/baglam",
        json={
            "dosya": str(tmp_path / "ornek.py"),
            "satir_baslangic": 10,
            "satir_bitis": 20,
            "secim": "api_key=sk-or-v1-" + "a" * 30 + "\nprint('merhaba')",
            "proje_kok": str(tmp_path),
            "kaynak": "vscode",
        },
    )
    ayar = app.state.sohbet.yonetici.ayarlar.oku()
    sistem, _, _, _ = app.state.sohbet.baglam_hazirla(ayar, "bunu incele", [])
    assert "DIS VERI: EDITOR BAGLAMI (vscode" in sistem
    assert "ornek.py (L10-L20)" in sistem
    assert "sk-or-v1-" not in sistem

    await istemci.delete("/api/editor/baglam")
    sistem2, _, _, _ = app.state.sohbet.baglam_hazirla(ayar, "bunu incele", [])
    assert "DIS VERI: EDITOR BAGLAMI" not in sistem2


@pytest.mark.asyncio
async def test_kart_komut_bos_kok_ve_sohbet_modu_reddi(
    tmp_path: Path, app, istemci, monkeypatch
) -> None:
    monkeypatch.setattr(
        app.state.sohbet,
        "aktif_alan",
        lambda: CalismaAlani(id="test", kokler=[str(tmp_path)], mod=Mod.sohbet),
    )
    r1 = await istemci.post("/api/kart-komut", json={"komut": "echo 1", "onay": True})
    assert r1.status_code == 403

    monkeypatch.setattr(
        app.state.sohbet,
        "aktif_alan",
        lambda: CalismaAlani(id="test", kokler=[], mod=Mod.onayli),
    )
    r2 = await istemci.post("/api/kart-komut", json={"komut": "echo 1", "onay": True})
    assert r2.status_code == 403


def test_yonlendirici_ollama_yedek_ve_oturum_maliyeti(tmp_path: Path) -> None:
    ayar = KullaniciAyarlari(saglayici="ollama", ollama_model="qwen3:8b", gunluk_butce_usd=0.5)
    assert yerel_yedek_model(ayar) == "ollama:qwen3:8b"

    alan = CalismaAlani(id="p1", kokler=[str(tmp_path)], gizli_proje=True)
    secilen, uyari = model_sec("anthropic/claude-sonnet-4", ayar, alan, 0.0)
    assert secilen == "ollama:qwen3:8b" and "Gizli proje" in (uyari or "")

    oturumlar = OturumDeposu(tmp_path)
    o = oturumlar.olustur("p1")
    o.mesajlar.append(
        Mesaj(
            rol="asistan",
            metin="tamam",
            istatistik={"maliyet_usd": 0.65},
            zaman=datetime.now().isoformat(timespec="seconds"),
        )
    )
    oturumlar.kaydet(o)
    run_deposu = RunDeposu(tmp_path)
    assert gunluk_maliyet_usd(run_deposu, oturumlar) >= 0.65


def test_runner_gizli_proje_cli_ve_bulut_modelini_yerele_cevirir(tmp_path: Path) -> None:
    depo = RunDeposu(tmp_path)
    yerel = next(iter(MODELLER))
    kullanilan: list[str] = []

    class SahteLlm:
        def __init__(self, model: str):
            self.model = model
            self.son_kullanim: dict = {}

        async def __aenter__(self):
            kullanilan.append(self.model)
            return self

        async def __aexit__(self, *a):
            return None

        async def token_say(self, m: str) -> int:
            return max(1, len(m) // 4)

        async def sohbet(self, *_a, **_kw):
            return {"message": {"role": "assistant", "content": "bitti"}, "finish_reason": "stop"}

    runner = AgentRunner(
        depo,
        lambda _h: ("", [], {}),
        lambda m="": SahteLlm(m or yerel),
    )
    runner.model_denetle = lambda istenen, _pid: (
        yerel,
        f"Gizli proje kurali: {istenen} -> {yerel}",
    )

    async def _kos():
        r = await runner.baslat(
            "kontrol",
            model="cli:claude",
            model_sabit=True,
            butce=Butce(max_adim=2, max_ilerlemesiz=1),
        )
        t = runner._gorevler[r.id]
        await t
        return depo.getir(r.id)

    son = asyncio.run(_kos())
    assert kullanilan == [yerel]
    assert son.model == yerel
    assert any("Gizli proje kurali" in g for g in son.guncellemeler)


def test_saglayici_ssrf_loopback_ve_reasoning_effort(tmp_path: Path) -> None:
    depo = SaglayiciDeposu(tmp_path)
    with pytest.raises(SaglayiciHatasi):
        depo.kaydet("lmstudio", adres="https://evil.example/v1")
    with pytest.raises(SaglayiciHatasi):
        depo.kaydet("ozel", adres="http://169.254.169.254/latest/meta-data")

    depo.kaydet("lmstudio", adres="http://127.0.0.1:1234/v1")
    llm_o3 = UyumluLLM("OpenAI", "https://api.openai.com/v1", "k", "o3-mini", sid="openai")
    assert (
        llm_o3._govde([{"role": "user", "content": "hi"}], "derin", 100)["reasoning_effort"]
        == "high"
    )

    llm_groq = UyumluLLM(
        "Groq", "https://api.groq.com/openai/v1", "k", "llama-3.3-70b-versatile", sid="groq"
    )
    assert "reasoning_effort" not in llm_groq._govde(
        [{"role": "user", "content": "hi"}], "derin", 100
    )
