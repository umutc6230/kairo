"""A13 arayuz E2E: gercek sunucu + gercek tarayici (kurulu Chrome, Playwright).

1) Masaustu boyutu: arayuz yuklenir, JS hatasi yok, sohbetten /doctor ve /schedule calisir.
2) Telefon boyutu (A12 Tailscale ince istemci): uzak TLS sunucusunda eslesme sayfasi -> kod ->
   masaustu uygulamanin TAM arayuzu; kenar cubugu ust katman olarak acilip kapanir.
Ekran goruntuleri tmp klasorune yazilir (gorsel dogrulama icin).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import threading
from pathlib import Path

import pytest

from app.agent import tarayici as tr

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
pytestmark = pytest.mark.skipif(
    not tr.playwright_var() or not (CHROME.exists() or shutil.which("chrome")),
    reason="Playwright ya da Chrome yok",
)


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def sunucular(tmp_path):
    import uvicorn

    from app import uzak
    from app.api import uygulama_olustur

    veri = tmp_path / "veri"
    veri.mkdir()
    (veri / "ayarlar.json").write_text(json.dumps({
        "adres": "http://127.0.0.1:9", "otomatik_baslat": False, "sunucu_acik": False,
        "llm_dizin": str(tmp_path)}), encoding="utf-8")  # fmt: skip
    app = uygulama_olustur(veri, gecit=False)
    p1, p2 = _port(), _port()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    durum: dict = {}

    async def basla() -> None:
        s = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=p1, log_level="warning"))
        durum["ana"] = s
        asyncio.get_running_loop().create_task(s.serve())
        while not s.started:
            await asyncio.sleep(0.05)
        cert, key, parmak = uzak.sertifika(veri / "uzak-tls", ["127.0.0.1"])
        depo = app.state.uzak_depo
        uapp = uzak.uzak_uygulamasi(depo, app.state.uzak_ic_cagri, parmak)
        asgi = uzak.tam_erisim_asgi(depo, uapp, app, app.state.oturum_anahtari)
        durum["uzak"] = uzak.UzakSunucu()
        await durum["uzak"].ac(asgi, p2, cert, key, "127.0.0.1")

    asyncio.run_coroutine_threadsafe(basla(), loop).result(30)
    yield f"http://127.0.0.1:{p1}", f"https://127.0.0.1:{p2}", app

    async def dur() -> None:
        await durum["uzak"].kapat()
        durum["ana"].should_exit = True
        await asyncio.sleep(0.3)

    asyncio.run_coroutine_threadsafe(dur(), loop).result(15)
    loop.call_soon_threadsafe(loop.stop)


HAZIR = "document.querySelector('#sunucu-metni')?.textContent !== 'Kontrol ediliyor...'"


def _tarayici(p):
    return p.chromium.launch(executable_path=str(CHROME) if CHROME.exists() else None,
                             channel=None if CHROME.exists() else "chrome")  # fmt: skip


def test_masaustu_ve_telefon_arayuzu(sunucular, tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    yerel, uzak_adres, app = sunucular
    with sync_playwright() as p:
        b = _tarayici(p)
        # ---- masaustu ----
        s = b.new_page(viewport={"width": 1280, "height": 800})
        hatalar: list[str] = []
        s.on("pageerror", lambda e: hatalar.append(str(e)))
        s.goto(yerel + "/")
        s.wait_for_selector("#girdi", state="visible", timeout=15000)
        s.wait_for_function(HAZIR, timeout=30000)
        s.fill("#girdi", "/doctor")
        s.keyboard.press("Enter")
        s.wait_for_selector("text=Tanı", timeout=15000)
        assert s.locator("text=Python").count() > 0
        s.screenshot(path=str(tmp_path / "masaustu-doctor.png"))
        s.keyboard.press("Escape")
        s.locator("button:has-text('Kapat')").last.click(timeout=3000) if s.locator(
            "button:has-text('Kapat')").count() else None  # fmt: skip
        s.fill("#girdi", "/schedule")
        s.keyboard.press("Enter")
        s.wait_for_selector("text=Zamanlamalar", timeout=10000)
        assert not hatalar, hatalar

        # ---- telefon (Tailscale ince istemci) ----
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                            has_touch=True, ignore_https_errors=True)  # fmt: skip
        t = ctx.new_page()
        t_hata: list[str] = []
        t.on("pageerror", lambda e: t_hata.append(str(e)))
        t.goto(uzak_adres + "/")
        t.wait_for_selector("text=Cihazı eşleştir", timeout=15000)
        assert t.url.endswith("/uzak/")
        kod = app.state.uzak_depo.kod_olustur("tam")["kod"]
        t.fill("#kod", kod)
        t.fill("#ad", "e2e-telefon")
        t.click("#esles")
        t.wait_for_selector("#girdi", state="visible", timeout=15000)
        t.wait_for_function(HAZIR, timeout=30000)
        assert t.url.rstrip("/") == uzak_adres
        icerik = t.content()
        assert app.state.oturum_anahtari not in icerik  # yerel anahtar telefona gitmez
        tasan = t.evaluate("[...document.querySelectorAll('#ana *')].filter(e => e.offsetParent"
                           " && e.getBoundingClientRect().right > 391).slice(0, 6)"
                           ".map(e => e.tagName"
                           " + '#' + e.id + '.' + e.className + ' ' + Math.round("
                           "e.getBoundingClientRect().right))")  # fmt: skip
        assert not tasan, tasan
        # yatay tasma yok (icerik ekrandan disari kesilmez)
        assert t.evaluate("document.documentElement.scrollWidth") <= 390
        assert t.evaluate("Math.max(...[...document.querySelectorAll('#ana *')]"
                          ".filter(e => e.offsetParent).map(e => e.getBoundingClientRect().right))"
                          ) <= 391  # fmt: skip
        kenar = t.locator("#kenar")
        t.wait_for_timeout(400)  # gizlenme animasyonu
        assert not kenar.is_visible()  # telefonda kapali baslar
        t.screenshot(path=str(tmp_path / "telefon-kapali.png"))
        t.click("#btn-kenar")
        t.wait_for_timeout(400)
        assert kenar.bounding_box()["x"] >= 0
        t.screenshot(path=str(tmp_path / "telefon-kenar.png"))
        t.fill("#girdi", "/status")
        t.keyboard.press("Enter")
        t.wait_for_timeout(1500)
        t.screenshot(path=str(tmp_path / "telefon-status.png"))
        assert not t_hata, t_hata
        b.close()
    print("EKRAN:", tmp_path)
