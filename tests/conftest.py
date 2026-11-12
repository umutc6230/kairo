"""Ortak test duzeni: gecici veri klasoru + llama-server'i taklit eden sahte sunucu."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "app" / "services"))  # skill testleri `import yerel_llm` kullanir

from app.api import uygulama_olustur  # noqa: E402
from app.services.testler import ORNEK_SATIRLAR  # noqa: E402
from app.services.yerel_llm import YerelLLM  # noqa: E402

ZAMANLAMA = {
    "predicted_per_second": 6.5,
    "prompt_per_second": 42.0,
    "predicted_n": 12,
    "prompt_n": 30,
}


def pytest_configure(config):
    config.addinivalue_line("markers", "canli: yerel llama-server acikken calisan kisa canli test")


class SahteSunucu:
    """llama-server'in kullandigimiz uclarini taklit eder; istekleri kaydeder."""

    def __init__(self) -> None:
        self.istekler: list[dict] = []
        self.saglik = True
        self.acik_modeller: list[str] = []  # bos: model adi dogrulanmaz
        self.hata: tuple[int, str] | None = None  # (kod, govde) -> chat istekleri hata doner
        self.dusunce = "Once soruyu anlamaliyim."

    def __call__(self, r: httpx.Request) -> httpx.Response:
        yol = r.url.path
        if yol == "/health":
            return httpx.Response(200 if self.saglik else 503, json={"status": "ok"})
        if yol == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": m} for m in self.acik_modeller]})
        if yol == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3]})
        govde = json.loads(r.content)
        self.istekler.append(govde)
        if yol == "/v1/messages/count_tokens":
            return httpx.Response(200, json={"input_tokens": 42})
        if yol == "/v1/messages":  # llama-server'in Anthropic ucu
            return self._anthropic(govde)
        if self.hata:
            return httpx.Response(self.hata[0], text=self.hata[1])
        icerik, cagrilar = self._cevap(govde)
        if govde.get("stream"):
            return httpx.Response(200, text=self._sse(icerik, cagrilar))
        mesaj: dict = {"role": "assistant", "content": icerik}
        if cagrilar:
            mesaj["tool_calls"] = cagrilar
        bitis = "tool_calls" if cagrilar else "stop"
        return httpx.Response(
            200,
            json={"choices": [{"message": mesaj, "finish_reason": bitis}], "timings": ZAMANLAMA},
        )

    def _anthropic(self, govde: dict) -> httpx.Response:
        if self.hata:
            return httpx.Response(self.hata[0], text=self.hata[1])
        if govde.get("stream"):
            olaylar = [
                ("message_start", {"type": "message_start"}),
                ("content_block_delta", {"type": "content_block_delta",
                                         "delta": {"type": "text_delta", "text": "selam"}}),
                ("message_stop", {"type": "message_stop"}),
            ]  # fmt: skip
            metin = "".join(f"event: {o}\ndata: {json.dumps(v)}\n\n" for o, v in olaylar)
            return httpx.Response(200, text=metin)
        return httpx.Response(200, json={
            "type": "message", "role": "assistant", "model": govde["model"],
            "content": [{"type": "text", "text": "selam"}], "stop_reason": "end_turn"})  # fmt: skip

    def _sse(self, icerik: str, cagrilar: list | None = None) -> str:
        parcalar = []
        if self.dusunce:
            parcalar.append({"choices": [{"delta": {"reasoning_content": self.dusunce}}]})
        for i, c in enumerate(cagrilar or []):  # arac cagrisi iki parcada akar
            yarim = len(c["function"]["arguments"]) // 2
            ilk = {"name": c["function"]["name"], "arguments": c["function"]["arguments"][:yarim]}
            parcalar.append({"choices": [{"delta": {"tool_calls": [
                {"index": i, "id": c["id"], "function": ilk}]}}]})  # fmt: skip
            kalan = {"arguments": c["function"]["arguments"][yarim:]}
            parcalar.append({"choices": [{"delta": {"tool_calls": [
                {"index": i, "function": kalan}]}}]})  # fmt: skip
        for kelime in icerik.split(" ") if icerik else []:
            parcalar.append({"choices": [{"delta": {"content": kelime + " "}}]})
        parcalar.append({"choices": [{"delta": {}, "finish_reason": "stop"}], "timings": ZAMANLAMA})
        return "".join(f"data: {json.dumps(p)}\n\n" for p in parcalar) + "data: [DONE]\n\n"

    @staticmethod
    def _metin(govde: dict) -> str:
        son = govde["messages"][-1]["content"]
        if isinstance(son, list):
            return " ".join(p.get("text", p.get("type", "")) for p in son)
        return son or ""

    def _cevap(self, govde: dict) -> tuple[str, list | None]:
        metin = self._metin(govde)
        kullanici = " ".join(
            m["content"]
            for m in govde["messages"]
            if m["role"] == "user" and isinstance(m["content"], str)
        ).lower()
        arac_sonuclari = [m for m in govde["messages"] if m["role"] == "tool"]
        if govde.get("tools") and "masaustu" in kullanici:
            if not arac_sonuclari:
                return "", [
                    {
                        "id": "m1",
                        "type": "function",
                        "function": {"name": "klasor_listele", "arguments": '{"yol": "masaustu"}'},
                    }
                ]
            liste = json.loads(arac_sonuclari[-1]["content"])
            return "Masaustunde: " + ", ".join(liste.get("ogeler", [])), None
        if govde.get("tools") and "dolar" in kullanici:
            if not arac_sonuclari:
                return "", [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "kur_getir", "arguments": '{"para_birimi": "USD"}'},
                    }
                ]
            return "1250 dolar 51.500 TL eder.", None
        if govde.get("response_format"):
            bicim = govde["response_format"].get("json_schema") or {}
            ozellik = bicim.get("schema", {}).get("properties", {})
            if "sehir" in ozellik:
                return json.dumps({"sehir": "Ankara", "plaka": 6}), None
            if "alanlar" in ozellik:
                return json.dumps({"alanlar": [{"ad": "Hakedis no", "deger": "7"}]}), None
            return json.dumps(
                {"hakedis_no": 7, "yuklenici": "Ornek Insaat", "tutar_tl": 1248500}
            ), None
        if "image_url" in metin:
            return "\n".join(ORNEK_SATIRLAR), None
        if "input_audio" in metin:
            return "The total amount is twelve.", None
        if "havuz" in metin.lower():
            return "Havuz 36/7 saatte dolar.", None
        if "maymuncuk" in metin.lower():
            return "1. Gerilim anahtarini tak. 2. Pimleri it. 3. Cevir.", None
        return "Merhaba, ben yerel modelim.", None


@pytest.fixture
def sunucu() -> SahteSunucu:
    return SahteSunucu()


@pytest.fixture
def veri(tmp_path: Path) -> Path:
    d = tmp_path / "veri"
    d.mkdir()
    return d


@pytest.fixture
def llm_dizin(tmp_path: Path) -> Path:
    """Sahte model klasoru: llama.cpp + tum model dosyalari (bos)."""
    from app.services.yerel_llm import MODELLER

    d = tmp_path / "llm"
    (d / "llama.cpp").mkdir(parents=True)
    (d / "models").mkdir()
    (d / "llama.cpp" / "llama-server.exe").write_bytes(b"")
    for p in MODELLER.values():
        (d / "models" / p.dosya).write_bytes(b"")
        (d / "models" / p.mmproj).write_bytes(b"")
    return d


@pytest.fixture
def skill_klasoru(tmp_path: Path, monkeypatch) -> Path:
    """Testler kullanicinin gercek ~/.claude skill'lerini ve CLAUDE.md'sini okumasin."""
    from app.services import talimatlar

    d = tmp_path / "claude_skills"
    d.mkdir()
    monkeypatch.setattr(talimatlar, "claude_md_yolu", lambda: tmp_path / "CLAUDE.md")
    return d


@pytest.fixture
def app(veri: Path, sunucu: SahteSunucu, llm_dizin: Path, skill_klasoru: Path):
    from app.services.skiller import SkillDeposu

    def fabrika(**kw) -> YerelLLM:
        return YerelLLM(transport=httpx.MockTransport(sunucu), **kw)

    depo = SkillDeposu(veri, [("claude", skill_klasoru), ("uygulama", veri / "skills")])
    uyg = uygulama_olustur(veri, fabrika, depo)
    # testler kullanicinin gercek ~/.claude/commands komutlarini okumasin
    uyg.state.kullanici_komut_dizini = lambda: skill_klasoru.parent / "claude_commands"
    from app.services.ayarlar import AyarDeposu

    AyarDeposu(veri).guncelle({"llm_dizin": str(llm_dizin)})
    return uyg


@pytest.fixture
async def istemci(app):
    """Gercek arayuz gibi: loopback Host + oturum anahtari basligi (A1.9)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"X-YAS-Oturum": app.state.oturum_anahtari},
    ) as c:
        yield c


@pytest.fixture
async def yetkisiz_istemci(app):
    """Oturum anahtari OLMAYAN istemci: yerel baska bir surec/sayfa gibi davranir."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as c:
        yield c


def olaylar(metin: str) -> list[dict]:
    return [json.loads(s[6:]) for s in metin.split("\n\n") if s.startswith("data: ")]


class IzoleSahte:
    """Politika testleri icin 'izole' adaptor: komut yine yerelde calisir (izolasyon iddiasi
    yalniz karar mantigini test etmek icindir)."""

    ad = "sahte"
    izole = True

    def durum(self) -> dict:
        return {"ad": self.ad, "izole": True, "kullanilabilir": True, "not": "test"}

    def sar(self, komut, cwd, kok):
        return None
