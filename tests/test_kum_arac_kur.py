"""--kum-arac-kur: arac klasorlerine yalniz RX, genis klasorlere asla."""

from __future__ import annotations

import os
from pathlib import Path

from app.agent import kum


def test_genis_klasorler_atlanir(tmp_path, monkeypatch):
    ev = Path.home().resolve()
    win = Path(os.environ.get("WINDIR", "C:/Windows")).resolve()
    arac = tmp_path / "araclar" / "bin"
    arac.mkdir(parents=True)
    yollar = {
        "python": str(arac / "python.exe"),
        "node": str(arac / "node.exe"),  # ayni klasor: tekrar etmez
        "npx": str(ev / "npx.cmd"),  # ev klasoru
        "npm": str(Path(ev.anchor) / "npm.cmd"),  # surucu koku
        "git": str(win / "System32" / "git.exe"),  # Windows alti
    }
    assert kum.arac_klasorleri(yollar.get) == [arac.resolve()]


def test_yalniz_rx_verilir(monkeypatch, tmp_path):
    hazir = tmp_path / "hazir"
    monkeypatch.setattr(kum, "arac_klasorleri", lambda: [tmp_path, hazir])
    monkeypatch.setattr(kum, "_sddl", lambda k: "D:(A;;FA;;;AC)" if k == hazir else "D:")
    cagrilar = []

    class R:
        returncode, stdout, stderr = 0, "", ""

    eklenen = []
    monkeypatch.setattr(kum, "_ace_ekle", lambda k, ace: eklenen.append((k, ace)))
    assert kum.arac_kur(lambda k, **_: cagrilar.append(k) or R()) == 0
    assert eklenen == [(Path(tmp_path.anchor), f"(A;;{kum._LISTELE:#x};;;AC)")]
    assert cagrilar == [["icacls", str(tmp_path), "/grant", "*S-1-15-2-1:(OI)(CI)(RX)"]]
