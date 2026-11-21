"""Mini arayuz kartindan Kairo'ya kopru: /api/kart-komut ve gorsel_kartlar.js denetimi."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).parent.parent / "app" / "web"


async def _proje(istemci, tmp_path: Path, mod: str = "onayli") -> dict:
    p = tmp_path / "proje"
    p.mkdir()
    alan = (await istemci.post("/api/projeler", json={"yol": str(p), "ad": "P"})).json()
    await istemci.put(f"/api/projeler/{alan['id']}/mod", json={"mod": mod})
    return alan


async def test_onaysiz_komut_calismaz(istemci, tmp_path) -> None:
    await _proje(istemci, tmp_path)
    isaret = tmp_path / "proje" / "x.txt"
    r = await istemci.post("/api/kart-komut", json={"komut": "echo hi > x.txt"})
    assert r.status_code == 403
    assert not isaret.exists()


async def test_onayli_komut_cikti_doner(istemci, tmp_path) -> None:
    await _proje(istemci, tmp_path)
    r = await istemci.post("/api/kart-komut", json={"komut": "echo kopru-ok", "onay": True})
    assert r.status_code == 200, r.text
    assert "kopru-ok" in r.json()["cikti"]


async def test_planla_modunda_ret(istemci, tmp_path) -> None:
    await _proje(istemci, tmp_path, mod="planla")
    r = await istemci.post("/api/kart-komut", json={"komut": "echo a", "onay": True})
    assert r.status_code == 403


async def test_oturum_anahtarsiz_ret(yetkisiz_istemci) -> None:
    r = await yetkisiz_istemci.post("/api/kart-komut", json={"komut": "echo a", "onay": True})
    assert r.status_code == 403


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_kopru_denetimi(tmp_path) -> None:
    betik = tmp_path / "t.mjs"
    url = (WEB / "gorsel_kartlar.js").as_uri()
    # tarayici modullerini node'da yuklemek yerine saf fonksiyonu kaynaktan cikar
    kaynak = (WEB / "gorsel_kartlar.js").read_text(encoding="utf-8")
    bas = kaynak.index("export const KOPRU_TURLERI")
    son = kaynak.index("function kopruYanit")
    betik.write_text(
        kaynak[bas:son]
        + """
const s = [
  kopruDenetle({tur:"komut", komut:"echo"}, false, 0, 10000),
  kopruDenetle({tur:"dosya_sil", komut:"x"}, true, 0, 10000),
  kopruDenetle({tur:"komut", komut:""}, true, 0, 10000),
  kopruDenetle({tur:"komut", komut:"echo"}, true, 9000, 10000),
  kopruDenetle({tur:"komut", komut:"echo"}, true, 0, 10000),
];
console.log(JSON.stringify(s));
""",
        encoding="utf-8",
    )
    assert url
    r = subprocess.run(["node", str(betik)], capture_output=True, check=False, text=True)
    assert r.returncode == 0, r.stderr[:400]
    assert json.loads(r.stdout) == ["kaynak", "tur", "komut", "oran", ""]


def test_kopru_guvenlik_yapisi() -> None:
    js = (WEB / "gorsel_kartlar.js").read_text(encoding="utf-8")
    assert 'setAttribute("sandbox", "allow-scripts")' in js
    assert "allow-same-origin" not in js.split("function sandboxIframe")[1].split("export")[0]
    assert "connect-src" not in js
    assert "if (!kaynak) return;" in js  # yabanci kaynak yok sayilir
