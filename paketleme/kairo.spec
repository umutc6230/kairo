# PyInstaller spec: tek klasor (onedir), konsolsuz pencere uygulamasi.
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

KOK = Path(SPECPATH).parent

a = Analysis(
    [str(KOK / "paketleme" / "giris.py")],
    pathex=[str(KOK)],
    datas=[(str(KOK / "app" / "web"), "app/web"), (str(KOK / "app" / "skills"), "app/skills")] + collect_data_files("webview"),
    hiddenimports=collect_submodules("uvicorn") + ["webview.platforms.edgechromium", "clr"],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kairo",
    console=False,
    icon=str(KOK / "paketleme" / "ikon.ico"),
    version=str(KOK / "paketleme" / "surum.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Kairo")
