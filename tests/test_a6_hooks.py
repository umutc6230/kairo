"""A6 hooks: deny, timeout, fail-closed/open, sir maskeleme, ajan entegrasyonu."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from test_a3_ajan import SahteModel, bitir, cagri, kur

from app.agent.hooks import HookDeposu
from app.agent.runner import AdimDurum, RunDurum

PY = f'"{sys.executable}"'


def _betik(tmp_path: Path, ad: str, kod: str) -> str:
    p = tmp_path / f"{ad}.py"
    p.write_text(kod, encoding="utf-8")
    return f'{PY} "{p}"'


def test_engel_timeout_ve_bilgi_hatasi(tmp_path) -> None:
    d = HookDeposu(tmp_path)
    reddet = _betik(tmp_path, "r", "import sys; sys.stderr.write('rm yasak'); sys.exit(2)")
    yavas = _betik(tmp_path, "y", "import time; time.sleep(5)")
    bozuk = _betik(tmp_path, "b", "import sys; sys.exit(1)")
    d.ekle({"ad": "bilgi-bozuk", "olay": "pre_tool", "tur": "bilgi", "komut": bozuk})
    assert d.tetikle("pre_tool", {}, arac="x").izin  # bilgi hook'u hatasi durdurmaz

    d.ekle({"ad": "yavas", "olay": "pre_tool", "tur": "guvenlik", "komut": yavas, "timeout": 1})
    s = d.tetikle("pre_tool", {}, arac="x")
    assert not s.izin and "zaman asimi" in s.neden  # guvenlik: fail-closed

    d2 = HookDeposu(tmp_path / "d2")
    d2.ekle({"ad": "rm", "olay": "pre_tool", "tur": "guvenlik", "komut": reddet,
             "arac": "komut_calistir"})  # fmt: skip
    assert d2.tetikle("pre_tool", {}, arac="proje_listele").izin  # arac filtresi
    s = d2.tetikle("pre_tool", {}, arac="komut_calistir")
    assert not s.izin and "rm yasak" in s.neden


def test_hook_girdisi_sir_maskelenir(tmp_path) -> None:
    cikti = tmp_path / "girdi.json"
    kaydet = _betik(tmp_path, "k", f"import sys; open({str(cikti)!r},'w').write(sys.stdin.read())")
    d = HookDeposu(tmp_path)
    d.ekle({"ad": "log", "olay": "post_tool", "komut": kaydet})
    d.tetikle("post_tool", {"sonuc": "api_key=sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789"})
    veri = json.loads(cikti.read_text(encoding="utf-8"))
    assert veri["surum"] == 1 and veri["olay"] == "post_tool"
    assert "abcdefghijklmnop" not in cikti.read_text(encoding="utf-8")


async def test_guvenlik_hooku_ajan_aracini_durdurur(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    hooks = HookDeposu(tmp_path / "h")
    hooks.ekle({"ad": "yazma-yasak", "olay": "pre_tool", "tur": "guvenlik",
                "arac": "proje_dosya_yaz",
                "komut": _betik(tmp_path, "r", "import sys; sys.exit(2)")})  # fmt: skip
    model = SahteModel([cagri("proje_dosya_yaz", yol="a.txt", icerik="x"),
                        cagri("gorevi_bitir", ozet="yazamadim", kanit_adimlari=[])])  # fmt: skip
    runner, *_ = kur(tmp_path, proje, model, hooks=hooks)
    run = await bitir(runner, (await runner.baslat("dosya yaz")).id)
    assert run.adimlar[0].durum is AdimDurum.reddedildi and "yazma-yasak" in run.adimlar[0].sonuc
    assert not (proje / "a.txt").exists() and run.durum is RunDurum.dogrulanmadi


async def test_hook_api(istemci) -> None:
    r = await istemci.post("/api/hooks", json={"ad": "t", "olay": "pre_tool", "komut": "exit 0"})
    h = r.json()
    assert r.status_code == 200 and h["tur"] == "bilgi"
    assert (await istemci.post(f"/api/hooks/{h['id']}/test")).json()["durum"] == "izin"
    bad = await istemci.post("/api/hooks", json={"ad": "t", "olay": "yok", "komut": "x"})
    assert bad.status_code == 422
    assert "pre_tool" in (await istemci.get("/api/hooks")).json()["olaylar"]
    assert (await istemci.delete(f"/api/hooks/{h['id']}")).status_code == 200


async def test_run_baslangic_ve_prompt_hooklari(tmp_path) -> None:
    import pytest

    from app.exceptions import UygulamaHatasi

    proje = tmp_path / "proje"
    proje.mkdir()
    iz = tmp_path / "olaylar.txt"
    yaz = _betik(
        tmp_path,
        "w",
        f"import sys,json; open({str(iz)!r},'a').write(json.load(sys.stdin)['olay']+'\\n')",
    )
    hooks = HookDeposu(tmp_path / "h")
    for olay in ("run_baslangic", "run_bitis"):
        hooks.ekle({"ad": olay, "olay": olay, "komut": yaz})
    model = SahteModel([cagri("gorevi_bitir", ozet="x", kanit_adimlari=[])])
    runner, *_ = kur(tmp_path, proje, model, hooks=hooks)
    await bitir(runner, (await runner.baslat("x")).id)
    assert iz.read_text(encoding="utf-8").split() == ["run_baslangic", "run_bitis"]

    hooks.ekle({"ad": "yasak", "olay": "run_baslangic", "tur": "guvenlik",
                "komut": _betik(tmp_path, "r", "import sys; sys.exit(2)")})  # fmt: skip
    with pytest.raises(UygulamaHatasi, match="yasak"):
        await runner.baslat("engellenecek")


async def test_slash_komut_dosyasi_ve_html(istemci) -> None:
    js = (await istemci.get("/web/komutlar.js")).text
    for k in ("/help", "/status", "/hooks", "/goal", "/clear", "/memory"):
        assert f'"{k}"' in js
    # 2026-11-12: "henuz yok" listesi kalkti; o komutlarin hepsi artik gercek is yapar
    for k in ("/compact", "/cost", "/todos", "/export", "/rewind", "/resume", "/init"):
        assert f'"{k}"' in js
    assert "HENUZ_YOK" not in js


def test_claude_plugin_hooku_yalniz_cikis_2_ile_engeller(tmp_path) -> None:
    """Bozuk kurulumlu plugin hook'u (cikis 127) sohbeti kilitlememeli; Claude Code gibi."""
    d = HookDeposu(tmp_path)
    bozuk = _betik(tmp_path, "k", "import sys; sys.exit(127)")
    engel = _betik(tmp_path, "e", "import sys; sys.stderr.write('dur'); sys.exit(2)")
    tanim = {"olay": "pre_tool", "tur": "guvenlik", "bicim": "claude", "kaynak": "plugin:x"}
    d.ek_kaynak = lambda: [{**tanim, "id": "p1", "ad": "bozuk", "komut": bozuk}]
    assert d.tetikle("pre_tool", {}, arac="x").izin
    d.ek_kaynak = lambda: [{**tanim, "id": "p2", "ad": "engel", "komut": engel}]
    s = d.tetikle("pre_tool", {}, arac="x")
    assert not s.izin and "dur" in s.neden


def test_plugin_hook_komutu_git_bash_ve_duz_yol(tmp_path) -> None:
    from app.agent.terminal import windows_bash
    from app.services.cc_plugin import hook_komutu

    k = hook_komutu('bash "${CLAUDE_PLUGIN_ROOT}/h.sh"', tmp_path)
    assert tmp_path.as_posix() + "/h.sh" in k and "\\" not in k.split('" "')[-1]
    if windows_bash():
        assert k.startswith(f'"{windows_bash()}"')


def test_claude_async_hook_beklenmez(tmp_path) -> None:
    """{"async": true} ilk satiri: hook arka planda surer, sohbet beklemez (Claude Code gibi)."""
    import time

    yavas = _betik(tmp_path, "a", 'import json,time,sys; print(json.dumps({"async": True}), '
                   'flush=True); time.sleep(8)')  # fmt: skip
    d = HookDeposu(tmp_path)
    d.ek_kaynak = lambda: [{"id": "pa", "ad": "async", "olay": "pre_tool", "tur": "guvenlik",
                            "bicim": "claude", "kaynak": "plugin:x", "komut": yavas}]  # fmt: skip
    bas = time.monotonic()
    assert d.tetikle("pre_tool", {}, arac="x").izin
    assert time.monotonic() - bas < 5


async def test_claude_hooklari_brain_baglami_ve_kayit(tmp_path) -> None:
    """SessionStart baglami ek_sistem'e girer; Stop hook'u proje cwd'si + istek/cevap alir."""
    proje = tmp_path / "proje"
    proje.mkdir()
    iz = tmp_path / "stop.json"
    baslangic = _betik(tmp_path, "b", "import json; print(json.dumps({'hookSpecificOutput': "
                       "{'additionalContext': 'DURUM: siradaki madde X'}}))")  # fmt: skip
    bitis = _betik(
        tmp_path, "s", f"import sys; open({str(iz)!r},'wb').write(sys.stdin.buffer.read())"
    )
    hooks = HookDeposu(tmp_path / "h")
    hooks.ekle({"ad": "b", "olay": "run_baslangic", "bicim": "claude", "komut": baslangic})
    hooks.ekle({"ad": "s", "olay": "run_bitis", "bicim": "claude", "komut": bitis})
    model = SahteModel([cagri("gorevi_bitir", ozet="giris ekrani bitti", kanit_adimlari=[])])
    runner, *_ = kur(tmp_path, proje, model, hooks=hooks)
    runner.kok = lambda: str(proje)
    run = await bitir(runner, (await runner.baslat("giris ekranini yap")).id)
    assert "DURUM: siradaki madde X" in run.ek_sistem
    govde = json.loads(iz.read_bytes().decode("utf-8"))
    assert govde["hook_event_name"] == "Stop" and Path(govde["cwd"]) == proje
    assert govde["prompt"] == "giris ekranini yap"
    assert govde["last_assistant_message"] == "giris ekrani bitti"
