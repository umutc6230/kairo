"""Sohbet ici mini arayuz (arayuz_goster) ve dev sunucu onizlemesi (onizleme_baslat)."""

from __future__ import annotations

import re
import socket
from pathlib import Path

from app.services import onizleme_araclari as oniz

WEB = Path(__file__).resolve().parents[1] / "app" / "web"


def _dinleyen() -> tuple[socket.socket, int]:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    return s, s.getsockname()[1]


def _bos_port() -> int:
    s, p = _dinleyen()
    s.close()
    return p


def test_arayuz_goster_denetim() -> None:
    assert "hata" in oniz.arayuz_goster("x", "  ")
    assert "hata" in oniz.arayuz_goster("x", "a" * (oniz.MAX_ARAYUZ_BAYT + 1))
    r = oniz.arayuz_goster("Monitor", "<b>ok</b>")
    assert r == {"gosterildi": True, "baslik": "Monitor", "boyut": 9}


def test_onizleme_port_zaten_acik() -> None:
    s, port = _dinleyen()
    try:
        f = oniz.onizleme_isleyici(None, None)
        r = f(port=port, yol="app")
        assert r["url"] == f"http://localhost:{port}/app" and r["is_id"] == ""
        # komut verildi ama port baska surecte: yanlis sunucu gosterilmez
        assert "baska bir surecte" in f(port=port, komut="npm run dev")["hata"]
    finally:
        s.close()


def test_onizleme_gecersiz_ve_komutsuz() -> None:
    f = oniz.onizleme_isleyici(None, None)
    assert "hata" in f(port=0)
    assert "hata" in f(port="abc")
    assert "komut" in f(port=_bos_port())["hata"]
    assert "kapali" in f(port=_bos_port(), komut="npm run dev")["hata"]


def test_onizleme_sunucu_acilinca_url_doner() -> None:
    acilan: list[socket.socket] = []
    cagri: dict = {}
    try:
        # port komut cagrilinca acilir: once bos port sec, sonra ayni porta dinleyici kur
        port = _bos_port()

        def calistir_ayni_port(**kw) -> dict:
            cagri.update(kw)
            s = socket.socket()
            s.bind(("127.0.0.1", port))
            s.listen()
            acilan.append(s)
            return {"id": "is1", "durum": "calisiyor"}

        f = oniz.onizleme_isleyici(calistir_ayni_port, lambda is_id: {"durum": "calisiyor"})
        r = f(port=port, komut="npm run dev")
        assert r["url"] == f"http://localhost:{port}/" and r["is_id"] == "is1"
        assert cagri["arka_plan"] is True and cagri["timeout"] == oniz.ONIZLEME_TIMEOUT_SN
    finally:
        for s in acilan:
            s.close()


def test_onizleme_sunucu_erken_kapanirsa_cikti_doner() -> None:
    f = oniz.onizleme_isleyici(
        lambda **kw: {"id": "is2"},
        lambda is_id: {"durum": "bitti", "cikti": "Error: port in use"},
        bekleme_sn=2,
    )
    r = f(port=_bos_port(), komut="npm run dev")
    assert "kapandi" in r["hata"] and "port in use" in r["cikti"]


def test_onizleme_komut_reddi_aynen_doner() -> None:
    f = oniz.onizleme_isleyici(lambda **kw: {"hata": "Kullanici reddetti"}, None)
    assert f(port=_bos_port(), komut="x") == {"hata": "Kullanici reddetti"}


def test_desenler() -> None:
    assert re.search(oniz.ARAYUZ_DESENI, "bana bir sistem monitörü paneli yap")
    assert re.search(oniz.ONIZLEME_DESENI, "uygulamayı çalıştır ve önizle")
    assert not re.search(oniz.ARAYUZ_DESENI, "selam nasilsin")


def test_kartlar_sandbox_guvenligi() -> None:
    js = (WEB / "gorsel_kartlar.js").read_text(encoding="utf-8")
    # model HTML'i: yalniz allow-scripts, ag yok; allow-same-origin yalniz localhost onizlemesinde
    assert 'f.setAttribute("sandbox", "allow-scripts")' in js
    assert "default-src 'none'" in js and "connect-src" not in js.split("const CSP")[1][:200]
    assert "localhost|127\\.0\\.0\\.1" in js
