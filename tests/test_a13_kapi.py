"""A13 deterministik kalite kapisi: iptal suresi + yonetilen surec temizligi, ag kapaliyken yerel
calisma, kapsam esigi. Donanim/istisnalar DURUM.md'ye yazilir."""

from __future__ import annotations

import asyncio
import socket
import sys
import time

import psutil
import pytest
from test_a3_ajan import SahteModel, bitir, cagri, kur, proje  # noqa: F401 - fixture

from app.agent.runner import RunDurum

# cocuk + torun surec: ikisi de pid yazar ve 60 sn uyur (yonetilen surec agaci)
AGAC = """import os, pathlib, subprocess, sys, time
t = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
pathlib.Path("pidler.txt").write_text(f"{os.getpid()} {t.pid}")
time.sleep(60)
"""


async def test_iptal_arac_calisirken_1sn_durum_5sn_surec_agaci(tmp_path, proje) -> None:  # noqa: F811
    (proje / "agac.py").write_text(AGAC, encoding="utf-8")
    komut = f'"{sys.executable}" agac.py'
    model = SahteModel([cagri("komut_calistir", komut=komut, timeout=120)])
    runner, *_ = kur(tmp_path, proje, model)
    run = await runner.baslat("uzun komut")
    pid_dosyasi = proje / "pidler.txt"
    for _ in range(200):
        if pid_dosyasi.exists() and pid_dosyasi.read_text().strip():
            break
        await asyncio.sleep(0.05)
    assert pid_dosyasi.exists(), runner.depo.getir(run.id).adimlar
    pidler = [int(x) for x in pid_dosyasi.read_text().split()]
    assert all(psutil.pid_exists(p) for p in pidler)

    bas = time.monotonic()
    run = await runner.iptal(run.id)
    gecen = time.monotonic() - bas
    assert run.durum is RunDurum.iptal
    assert gecen < 1.0, f"iptal durumu {gecen:.2f} sn surdu"
    bitis = time.monotonic() + 5
    while time.monotonic() < bitis and any(psutil.pid_exists(p) for p in pidler):
        await asyncio.sleep(0.1)
    canli = [p for p in pidler if psutil.pid_exists(p)]
    assert not canli, f"5 sn sonra hala yasayan surecler: {canli}"


async def test_ag_kapaliyken_yerel_ajan_calisir(tmp_path, proje, monkeypatch) -> None:  # noqa: F811
    gercek = socket.socket.connect

    def yalniz_loopback(self, adres):
        host = adres[0] if isinstance(adres, tuple) else str(adres)
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise OSError("ag kapali (test)")
        return gercek(self, adres)

    monkeypatch.setattr(socket.socket, "connect", yalniz_loopback)
    model = SahteModel([
        cagri("proje_dosya_oku", yol="src/hesap.py"),
        cagri("gorevi_bitir", ozet="okundu", kanit_adimlari=[1]),
    ])  # fmt: skip
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("dosyayi oku")).id)
    assert run.durum in (RunDurum.basarili, RunDurum.dogrulanmadi), run.hata


def test_web_ara_ag_kapaliyken_anlasilir_hata(monkeypatch) -> None:
    from app.agent import web

    def kapali(*_a, **_k):
        raise OSError("ag kapali (test)")

    monkeypatch.setattr(socket, "getaddrinfo", kapali)
    r = web.web_ara("python", lambda *_a, **_k: None)
    metin = str(r)
    assert "hata" in r, r
    assert "Traceback" not in metin


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object")
def test_komut_sahibi_kaydi() -> None:
    from app.agent import terminal

    assert terminal.AKTIF_RUN.get() == ""
