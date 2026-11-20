"""A5.6 a11y yapisi + A5.7 yerel ses dikte."""

from __future__ import annotations

import io
import shutil
import struct
import subprocess
import wave
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

WEB = Path(__file__).parent.parent / "app" / "web"


def wav(sn: float = 0.5) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * sn))
    return b.getvalue()


async def test_dikte_durumu_sahte_destek_gostermez(istemci) -> None:
    await istemci.put("/api/ayarlar", json={"model": "deepseek-heretic"})
    d = (await istemci.get("/api/dikte/durum")).json()
    assert d["kullanilabilir"] is False and "sesi anlamiyor" in d["neden"]
    r = await istemci.post("/api/dikte", files={"ses": ("a.wav", wav(), "audio/wav")})
    assert r.status_code >= 400 and "sesi anlamiyor" in r.json()["hata"]

    await istemci.put("/api/ayarlar", json={"saglayici": "openrouter", "or_model": "x/y:free"})
    d = (await istemci.get("/api/dikte/durum")).json()
    assert d["kullanilabilir"] is False and "buluta gonderilmez" in d["neden"]


async def test_dikte_yerel_gemma_ile_yaziya_doker(istemci, app) -> None:
    await istemci.put("/api/ayarlar", json={"model": "gemma4-e4b-heretic", "saglayici": "yerel"})
    assert (await istemci.get("/api/dikte/durum")).json()["kullanilabilir"] is True
    gelen: list = []

    class Sahte:
        async def ses(self, veri, talimat, **kw):
            gelen.append((veri[:4], kw.get("bicim"), kw.get("dusunme")))
            return "  merhaba dunya  "

    @asynccontextmanager
    async def kullan(*_a, **_k):
        yield Sahte()

    app.state.yonetici.kullan = kullan
    r = await istemci.post("/api/dikte", files={"ses": ("a.wav", wav(), "audio/wav")})
    assert r.json()["metin"] == "merhaba dunya"
    assert gelen == [(b"RIFF", "wav", "kapali")]
    # WAV olmayan ve cok uzun kayit reddedilir (modele gitmez)
    r = await istemci.post(
        "/api/dikte", files={"ses": ("a.webm", b"\x1aE\xdf\xa3" * 100, "audio/webm")}
    )
    assert r.status_code >= 400 and "WAV" in r.json()["hata"]
    r = await istemci.post("/api/dikte", files={"ses": ("a.wav", wav(31), "audio/wav")})
    assert r.status_code >= 400 and "30 saniye" in r.json()["hata"]
    assert len(gelen) == 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_tarayici_wav_kodlayici_gecerli_wav_uretir(tmp_path) -> None:
    """dikte.js'deki wavKodla: Python wave modulunun okuyabildigi gecerli WAV."""
    betik = tmp_path / "t.mjs"
    url = (WEB / "dikte.js").as_uri()
    cikti = tmp_path / "o.wav"
    betik.write_text(
        f"""globalThis.document = {{ querySelector: () => null }};
const {{ wavKodla }} = await import({url!r});
const p = new Float32Array(1600).map((_, i) => Math.sin(i / 10));
const b = wavKodla([p, p.slice(0, 400)], 16000);
const fs = await import("node:fs");
fs.writeFileSync({str(cikti)!r}, Buffer.from(await b.arrayBuffer()));
""",
        encoding="utf-8",
    )
    r = subprocess.run(["node", str(betik)], capture_output=True, check=False)
    assert r.returncode == 0, r.stderr.decode(errors="replace")[:400]
    with wave.open(str(cikti), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        assert w.getnframes() == 2000
        ilk = struct.unpack("<h", w.readframes(1))[0]
        assert ilk == 0


def test_html_erisilebilirlik_yapisi() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="mesajlar" role="log"' in html
    assert 'id="girdi"' in html and 'aria-label="Mesaj"' in html
    assert 'id="btn-dikte"' in html and 'aria-pressed="false"' in html
    assert 'role="status"' in html  # dikte gostergesi ekran okuyucuya bildirilir
    ortak = (WEB / "ortak.js").read_text(encoding="utf-8")
    assert 'role="dialog" aria-modal="true" aria-labelledby' in ortak
    assert "onceki.focus" in ortak  # kapaninca odak geri doner
    css = (WEB / "app.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css and ":focus-visible" in css
    dikte = (WEB / "dikte.js").read_text(encoding="utf-8")
    assert "SpeechRecognition" not in dikte  # bulut konusma tanima kullanilmaz


async def test_dikte_bulut_izinle_ve_ses_destekli_modelle(istemci, app) -> None:
    from app.services.depo import json_yaz

    await istemci.put("/api/ayarlar", json={"saglayici": "openrouter", "or_model": "g/ses"})
    d = (await istemci.get("/api/dikte/durum")).json()
    assert d["kullanilabilir"] is False and "buluta gonderilmez" in d["neden"]  # varsayilan kapali

    uzak = app.state.yonetici.uzak
    uzak.anahtar_kaydet("sk-or-v1-" + "a" * 32)
    await istemci.put("/api/ayarlar", json={"dikte_bulut": True, "dikte_model": "g/ses"})
    d = (await istemci.get("/api/dikte/durum")).json()
    assert d["kullanilabilir"] is False and "sesi anlamiyor" in d["neden"]  # model bilinmiyor

    json_yaz(uzak.liste_yolu, {"zaman": 0, "modeller": [{"id": "g/ses", "ses": True}]})
    d = (await istemci.get("/api/dikte/durum")).json()
    assert d["kullanilabilir"] is True and d["bulut"] is True and d["model"] == "g/ses"

    # ayri dikte modeli: sohbet saglayicisi yerel olsa da mikrofon calisir
    await istemci.put("/api/ayarlar", json={"saglayici": "yerel"})
    d = (await istemci.get("/api/dikte/durum")).json()
    assert d["kullanilabilir"] is True and d["model"] == "g/ses"


def test_openrouter_ses_isteginde_veri_toplama_kapali() -> None:
    from app.services.openrouter import OpenRouterLLM, _sadelestir

    llm = OpenRouterLLM("k", "g/ses")
    ses = [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "x"}}]}]
    assert llm._govde(ses, "kapali", 9)["provider"] == {"data_collection": "deny"}
    assert "provider" not in llm._govde([{"role": "user", "content": "selam"}], "kapali", 9)
    m = {"id": "a/b", "architecture": {"input_modalities": ["text", "audio"]}}
    assert _sadelestir(m)["ses"] is True
