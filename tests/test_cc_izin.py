"""Claude Code izin koprusu: arac eslemesi, CLI bayraklari, /api/cc-izin karar akisi."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.agent import cc_izin, cli_ajan
from app.agent.policy import YanEtki


def test_istek_cevir_yan_etkiler():
    assert cc_izin.istek_cevir("Read", {"file_path": "C:/a.py"}).yan_etki is YanEtki.oku
    assert cc_izin.istek_cevir("Edit", {"file_path": "C:/a.py"}).yol == "C:/a.py"
    b = cc_izin.istek_cevir("Bash", {"command": "npm test"})
    assert (b.yan_etki, b.komut, b.arac) == (YanEtki.komut, "npm test", "cc:Bash")
    assert cc_izin.istek_cevir("WebFetch", {"url": "https://x.com/a"}).host == "x.com"
    assert cc_izin.istek_cevir("mcp__slack__send", {}).yan_etki is YanEtki.dis


def test_hook_ayari_ve_cikti():
    ayar = json.loads(cc_izin.ayar_json())
    hook = ayar["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "*" and "cc_izin" in hook["hooks"][0]["command"]
    assert cc_izin.hook_cikti(False, "x")["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_komut_kur_kopru_yalniz_tam_yetki_kapaliyken(monkeypatch):
    monkeypatch.setattr(cli_ajan, "claude_yolu", lambda: "claude")
    k = cli_ajan.komut_kur("claude", "m", Path("."), izin_koprusu=True)
    assert "--settings" in k
    k = cli_ajan.komut_kur("claude", "m", Path("."), izin_koprusu=True, tam_yetki=True)
    assert "--settings" not in k


def test_main_ulasilamazsa_deny(monkeypatch, capsys):
    import io

    monkeypatch.setenv(cc_izin.URL_ORTAM, "http://127.0.0.1:9/api/cc-izin")
    monkeypatch.setenv(cc_izin.ANAHTAR_ORTAM, "x")
    monkeypatch.setattr("sys.stdin", io.StringIO('{"tool_name": "Bash", "tool_input": {}}'))
    cc_izin.main()
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


async def test_api_okuma_izin_komut_onay(istemci, app, tmp_path):
    govde = {"arac": "Read", "girdi": {"file_path": str(tmp_path / "a.py")},
             "klasor": str(tmp_path)}  # fmt: skip
    r = (await istemci.post("/api/cc-izin", json=govde)).json()
    assert r["izin"] is True

    komut = {"arac": "Bash", "girdi": {"command": "echo hi"}, "klasor": str(tmp_path),
             "baglam": "t1"}  # fmt: skip
    gorev = asyncio.create_task(istemci.post("/api/cc-izin", json=komut))
    for _ in range(50):  # onay karti olusana kadar
        await asyncio.sleep(0.05)
        bekleyen = [o for o in app.state.politika.onaylar.gecmis() if o["karar"] == "bekliyor"]
        if bekleyen:
            break
    assert bekleyen and bekleyen[0]["arac"] == "cc:Bash"
    await istemci.post(f"/api/onaylar/{bekleyen[0]['id']}", json={"onayla": True})
    assert (await gorev).json()["izin"] is True


async def test_cc_jetonu_yalniz_izin_ucunda_gecer(yetkisiz_istemci, app):
    h = {"X-YAS-Oturum": app.state.cc_izin_anahtari}
    r = await yetkisiz_istemci.post("/api/cc-izin", json={"arac": "Read"}, headers=h)
    assert r.status_code == 200
    r = await yetkisiz_istemci.post("/api/onaylar/x", json={"onayla": True}, headers=h)
    assert r.status_code == 403
    assert (await yetkisiz_istemci.get("/api/onaylar", headers=h)).status_code == 403
