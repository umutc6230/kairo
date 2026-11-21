"""A5 kalan: GERCEK Kairo penceresinde (pywebview + WebView2) uctan uca test.

Uygulama `python -m app` ile izole veri klasoruyle acilir; WebView2'ye uzaktan hata ayiklama
portu verilir (WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS) ve Playwright o pencereye CDP ile baglanir.
Kontroller: arayuz JS hatasiz acilir, pywebview koprusu ana sayfada var, sandbox iframe'lere
(uzanti paneli onizlemesi) SIZMAZ, menu tekrar tekrar acilir, kapat dugmesi sureci bitirir.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.agent import tarayici as tr

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not tr.playwright_var(), reason="Windows + Playwright gerekli"
)
webview = pytest.importorskip("webview")

KOK = Path(__file__).resolve().parents[1]
HAZIR = "document.documentElement.dataset.hazir === '1'"
# Sandbox iframe icinden ust pencereye neyi gorebildigini bildirir.
SIZINTI_BETIGI = """
async (sandbox) => {
  const f = document.createElement('iframe');
  f.setAttribute('sandbox', sandbox);
  // WebView2 iframe'lere de chrome.webview verir; kopru cagrisini dogrudan dener (buyut).
  f.srcdoc = `<script>try { chrome.webview.postMessage(['buyut', '[]', 'sizinti']); } catch (e) {}
  parent.postMessage({e2e: 1,
    pywebview: typeof window.pywebview, webview: typeof (window.chrome && window.chrome.webview),
    ust: (() => { try { return typeof parent.pywebview; } catch (e) { return 'engel'; } })()
  }, '*');<\\/script>`;
  const sonuc = new Promise((coz) => {
    const dinle = (e) => { if (e.data && e.data.e2e) { removeEventListener('message', dinle);
      coz(e.data); } };
    addEventListener('message', dinle);
    setTimeout(() => coz({zaman_asimi: 1}), 5000);
  });
  document.body.append(f);
  const r = await sonuc;
  f.remove();
  return r;
}
"""


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _bekle(kosul, sure: float, adim: float = 0.25):
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if (r := kosul()) is not None:
            return r
        time.sleep(adim)
    return None


@pytest.fixture
def pencere(tmp_path):
    veri = tmp_path / "veri"
    veri.mkdir()
    (veri / "ayarlar.json").write_text(json.dumps({
        "adres": "http://127.0.0.1:9", "otomatik_baslat": False, "sunucu_acik": False,
        "llm_dizin": str(tmp_path), "sistem_tepsisi": False}), encoding="utf-8")  # fmt: skip
    port, cdp = _port(), _port()
    ortam = {**os.environ, "YAS_VERI_DIZINI": str(veri), "YAS_PORT": str(port),
             "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={cdp}"}  # fmt: skip
    surec = subprocess.Popen([sys.executable, "-m", "app"], cwd=KOK, env=ortam,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)  # fmt: skip
    yield surec, f"http://127.0.0.1:{port}/", f"http://127.0.0.1:{cdp}"
    if surec.poll() is None:
        surec.kill()
        surec.wait(10)


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") == "true",
    reason="CI runner'inda etkilesimli masaustu yok, WebView2 debug portu acilmiyor",
)
def test_gercek_pencere_uctan_uca(pencere, tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    surec, adres, cdp = pencere

    def cdp_hazir():
        if surec.poll() is not None:
            pytest.fail(f"Kairo acilmadan kapandi: {surec.stderr.read().decode(errors='replace')}")
        try:
            with socket.create_connection(("127.0.0.1", int(cdp.rsplit(":", 1)[1])), 0.5):
                return True
        except OSError:
            return None

    assert _bekle(cdp_hazir, 60), "WebView2 hata ayiklama portu acilmadi"
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(cdp)
        sayfa = _bekle(lambda: next((s for c in b.contexts for s in c.pages
                                     if s.url.startswith(adres)), None), 30)  # fmt: skip
        assert sayfa, "Kairo sayfasi bulunamadi"
        hatalar: list[str] = []
        sayfa.on("pageerror", lambda e: hatalar.append(str(e)))
        sayfa.reload()  # hatalari bastan yakalamak icin
        sayfa.wait_for_function(HAZIR, timeout=30000)
        sayfa.wait_for_function("window.pywebview && window.pywebview.api", timeout=15000)

        # 1) kopru ana sayfada: baslik cubugu ve diyalog cagrilari
        api = sayfa.evaluate("Object.keys(window.pywebview.api).sort()")
        assert {"buyut", "dosya_kaydet", "kapat", "klasor_sec", "kucult"} <= set(api), api
        assert not any(a.startswith("_") for a in api), api  # ozel alanlar disari acilmaz

        # 2) kopru sandbox iframe'lere sizmaz (uzanti paneli: allow-scripts; tarayici paneli de
        #    allow-same-origin'li oldugu icin ayrica)
        for sandbox in ("allow-scripts", "allow-scripts allow-forms allow-popups"):
            r = sayfa.evaluate(SIZINTI_BETIGI, sandbox)
            assert (r.get("pywebview"), r.get("ust")) == ("undefined", "engel"), (sandbox, r)
        # iframe'in chrome.webview.postMessage ile buyut cagrisi Python'a ULASMAMALI: ulasirsa
        # pencere durumu cevrilir ve asagidaki ilk buyut() False doner (bkz. adim 5).
        time.sleep(1.5)

        # 3) menu her tiklamada acilir/kapanir (bir kez acilip kalma hatasi)
        for _ in range(3):
            sayfa.click("#btn-daha")
            sayfa.wait_for_selector(".menu", state="visible", timeout=3000)
            sayfa.click("#btn-daha")
            sayfa.wait_for_selector(".menu", state="detached", timeout=3000)

        # 4) sohbet ekrani gercek pencerede calisir
        sayfa.fill("#girdi", "/doctor")
        sayfa.keyboard.press("Enter")
        sayfa.wait_for_selector("text=Tanı", timeout=15000)
        sayfa.screenshot(path=str(tmp_path / "webview2.png"))
        assert not hatalar, hatalar

        # 5) buyut iki kez: calisma alanina sigar, sonra eski boyuta doner (iframe sizintisi yoksa)
        assert sayfa.evaluate("window.pywebview.api.buyut()") is True
        assert sayfa.evaluate("window.pywebview.api.buyut()") is False

        # 6) kapat dugmesi (tepsi kapali): pencere ve arka uc sureci biter
        with contextlib.suppress(Exception):  # pencere kapanirken yanit gelmeyebilir
            sayfa.evaluate("window.pywebview.api.kapat()")
        b.close()
    assert _bekle(lambda: surec.poll(), 30) is not None, "Kairo kapanmadi"
