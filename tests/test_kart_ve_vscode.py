"""Kart koprusu `yenile` turu ve VS Code editor baglam API/eklenti testleri."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent


async def test_editor_baglam_api_ve_sir_maskeleme(istemci) -> None:
    bos = (await istemci.get("/api/editor/baglam")).json()
    assert bos == {"var": False}

    kayit = (
        await istemci.post(
            "/api/editor/baglam",
            json={
                "dosya": "C:/proj/app.py",
                "satir_baslangic": 10,
                "satir_bitis": 25,
                "secim": "API_KEY = 'sk-or-v1-1234567890abcdef1234567890abcdef'",
                "proje_kok": "C:/proj",
            },
        )
    ).json()
    assert kayit["var"] is True
    assert kayit["dosya"] == "C:/proj/app.py"
    assert kayit["satir_baslangic"] == 10 and kayit["satir_bitis"] == 25
    assert "1234567890abcdef" not in kayit["secim"]

    oku = (await istemci.get("/api/editor/baglam")).json()
    assert oku["var"] is True and oku["kaynak"] == "vscode"

    sil = (await istemci.delete("/api/editor/baglam")).json()
    assert sil == {"temizlendi": True}
    assert (await istemci.get("/api/editor/baglam")).json() == {"var": False}


def test_vscode_eklenti_manifest_ve_sozdizimi() -> None:
    klasor = KOK / "integrations" / "vscode"
    pkg = json.loads((klasor / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "kairo-bridge"
    komutlar = {c["command"] for c in pkg["contributes"]["commands"]}
    assert {"kairo.baglamGonder", "kairo.ac"} <= komutlar

    if shutil.which("node") is not None:
        r = subprocess.run(
            ["node", "--check", str(klasor / "extension.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0, r.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_kart_koprusu_yenile_turu_denetimi(tmp_path: Path) -> None:
    url = (KOK / "app" / "web" / "gorsel_kartlar.js").as_uri()
    betik = tmp_path / "t.mjs"
    betik.write_text(
        f"""globalThis.window = {{ addEventListener: () => {{}} }};
globalThis.document = {{ querySelector: () => null }};
const {{ kopruDenetle, KOPRU_TURLERI }} = await import({url!r});
if (!KOPRU_TURLERI.has("yenile")) throw new Error("yenile eksik");
if (kopruDenetle({{ tur: "yenile", istem: "Tabloyu filtrele" }}, true, 0, 5000) !== "") {{
  throw new Error("gecerli yenile reddedildi");
}}
if (kopruDenetle({{ tur: "yenile", istem: "   " }}, true, 0, 5000) !== "istem") {{
  throw new Error("bos istem kabul edildi");
}}
if (kopruDenetle({{ tur: "yenile", istem: "a".repeat(2001) }}, true, 0, 5000) !== "istem") {{
  throw new Error("cok uzun istem kabul edildi");
}}
if (kopruDenetle({{ tur: "yenile", istem: "yenile" }}, true, 4500, 5000) !== "oran") {{
  throw new Error("oran siniri calismadi");
}}
""",
        encoding="utf-8",
    )
    r = subprocess.run(["node", str(betik)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
