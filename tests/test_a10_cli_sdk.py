"""A10.3-4 kabul: ayni fixture gorevi CLI (gercek alt surec) ve SDK ile; onayda bekleme yok."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

KOK = Path(__file__).parent.parent
SAHTE = Path(__file__).parent / "sahte_model_sunucusu.py"


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def ortam(tmp_path):
    port = _port()
    pytest_komutu = f'"{sys.executable}" -m pytest -q tests'
    model = subprocess.Popen([sys.executable, "-I", str(SAHTE), str(port), pytest_komutu])
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    veri = tmp_path / "veri"
    veri.mkdir()
    (veri / "ayarlar.json").write_text(json.dumps({
        "adres": f"http://127.0.0.1:{port}", "otomatik_baslat": False, "model": "deepseek-heretic",
        "sunucu_acik": False, "llm_dizin": str(tmp_path)}), encoding="utf-8")  # fmt: skip
    proje = tmp_path / "proje"
    (proje / "src").mkdir(parents=True)
    (proje / "tests").mkdir()
    (proje / "src" / "hesap.py").write_bytes(b"def topla(a, b):\n    return a - b  # hatali\n")
    (proje / "tests" / "test_hesap.py").write_bytes(
        b"import sys\nsys.path.insert(0, 'src')\nfrom hesap import topla\n\n"
        b"def test_topla():\n    assert topla(2, 3) == 5\n"
    )
    yield veri, proje
    model.kill()


def cli(veri: Path, *a: str) -> tuple[int, list[dict]]:
    env = {**os.environ, "YAS_VERI_DIZINI": str(veri)}
    r = subprocess.run([sys.executable, "-m", "app", "agent", "--json", *a], cwd=KOK, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=180)  # fmt: skip
    olaylar = [json.loads(s) for s in r.stdout.splitlines() if s.startswith("{")]
    assert olaylar, r.stderr[-2000:]
    return r.returncode, olaylar


def test_cli_onayda_durur_devam_eder_ve_biter(ortam) -> None:
    veri, proje = ortam
    kod, o = cli(veri, "topla fonksiyonunu duzelt", "--proje", str(proje), "--guven", "guvenilir",
                 "--mod", "onayli", "--kabul", "pytest gecsin")  # fmt: skip
    son = o[-1]
    assert kod == 3 and son["durum"] == "onay_bekliyor"  # sonsuza kadar beklemedi
    assert son["bekleyen_onaylar"][0]["arac"] == "proje_dosya_yama"
    assert b"a - b" in (proje / "src" / "hesap.py").read_bytes()  # onaysiz yazilmadi

    run = son["run_id"]
    kod, o = cli(veri, "--onayla", son["bekleyen_onaylar"][0]["onay_id"], "--devam", run)
    assert kod == 3 and o[-1]["bekleyen_onaylar"][0]["arac"] == "komut_calistir"
    kod, o = cli(veri, "--onayla", o[-1]["bekleyen_onaylar"][0]["onay_id"], "--devam", run)
    assert kod == 0 and o[-1]["durum"] == "basarili" and o[-1]["kanit"]
    assert b"a + b" in (proje / "src" / "hesap.py").read_bytes()
    assert any(x["tur"] == "run" for x in o)  # JSON olay akisi
    kayit = json.loads((veri / "runs" / f"{run}.json").read_text(encoding="utf-8"))
    aciklamali = {a["arac"]: a["aciklama"] for a in kayit["adimlar"] if a.get("aciklama")}
    assert aciklamali["proje_dosya_yama"] == "proje_dosya_yama adimini calistiriyorum."


def test_cli_hatali_kullanim(ortam) -> None:
    veri, _ = ortam
    env = {**os.environ, "YAS_VERI_DIZINI": str(veri)}
    r = subprocess.run([sys.executable, "-m", "app", "agent"], cwd=KOK, env=env,
                       capture_output=True, text=True, timeout=120)  # fmt: skip
    assert r.returncode == 4 and "--proje" in r.stderr


def test_sdk_ayni_motor_ayni_sonuc(ortam, monkeypatch) -> None:
    """SDK ayri motor kurmaz: CLI'nin actigi ayni uygulama/API; kimliksiz istek reddedilir."""
    from app import cli
    from app.sdk import Studio, StudioHatasi

    veri, proje = ortam
    monkeypatch.setenv("YAS_VERI_DIZINI", str(veri))
    sunucu, adres, anahtar = cli._sunucu_baslat()
    try:
        with Studio(adres, "yanlis-anahtar") as kotu, pytest.raises(StudioHatasi, match="anahtari"):
            kotu.durum("0" * 12)
        with Studio(adres, "yanlis-anahtar") as kotu:
            assert kotu.bilgi()["urun"]  # yalniz urun bilgisi anahtarsiz acik
        with Studio(adres, anahtar) as s:
            s.proje_ac(str(proje), guven="guvenilir", mod="onayli")
            run = s.gorev("topla fonksiyonunu duzelt")["id"]
            for _ in range(3):
                r = list(s.izle(run, aralik=0.3))[-1]
                if r["durum"] != "onay_bekliyor":
                    break
                bekleyen = next(a for a in r["adimlar"] if a["durum"] == "onay_bekliyor")
                s.onay(bekleyen["onay_id"], True)
                s.islem(run, "devam")
            assert r["durum"] == "basarili" and r["sonuc"]["dogrulandi"]  # CLI ile ayni sonuc
    finally:
        sunucu.should_exit = True


async def test_doctor_sir_gostermez(istemci) -> None:
    await istemci.put("/api/openrouter/anahtar", json={"anahtar": "sk-or-v1-" + "z" * 40})
    r = await istemci.get("/api/doctor")
    adlar = {c["ad"]: c for c in r.json()["kontroller"]}
    assert {"Python", "llama.cpp", "git", "Playwright", "OpenRouter anahtari"} <= set(adlar)
    assert adlar["OpenRouter anahtari"]["ayrinti"] == "kayitli" and "zzzz" not in r.text
