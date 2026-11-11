"""Claude Desktop ayar karsiliklari: kisayol ayrisma, baglayici ice aktarma, ayar alanlari."""
# ruff: noqa: E501

from __future__ import annotations

import json

from app.agent import mcp_ice
from app.services import masaustu_ayar as mda
from app.services.ayarlar import AyarDeposu


def test_kisayol_coz() -> None:
    assert mda.kisayol_coz("Ctrl+Alt+Space") == (0x2 | 0x1, 0x20)
    assert mda.kisayol_coz("ctrl+shift+K") == (0x2 | 0x4, ord("K"))
    assert mda.kisayol_coz("Alt+F4") == (0x1, 0x73)
    for kotu in ("Space", "Ctrl+", "Hyper+X", "Ctrl+Alt+Uzun"):
        assert mda.kisayol_coz(kotu) is None


def test_depolama(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.bin").write_bytes(b"1" * 100)
    (tmp_path / "b").mkdir()
    assert mda.depolama(tmp_path)[0] == {"ad": "a", "bayt": 100}


def test_ayar_alanlari(tmp_path) -> None:
    d = AyarDeposu(tmp_path)
    a = d.guncelle(
        {"tema": "acik", "cikti_stili": "kisa", "branch_oneki": "kairo", "arsiv_gun": 30}
    )
    assert (a.tema, a.cikti_stili, a.arsiv_gun) == ("acik", "kisa", 30)
    for kotu in ({"tema": "mor"}, {"branch_oneki": "bos luk"}, {"arsiv_gun": 999}):
        try:
            d.guncelle(kotu)
            raise AssertionError(kotu)
        except ValueError:
            pass


def test_baglayici_bul(tmp_path) -> None:
    ev, ad = tmp_path / "ev", tmp_path / "appdata"
    ev.mkdir()
    (ev / ".claude.json").write_text(json.dumps({
        "mcpServers": {"Rea Ajan": {"command": "node", "args": ["x.mjs"]}},
        "projects": {"C:/p/proje": {"mcpServers": {"uzak": {"type": "http", "url": "https://a.test/mcp"}}}},
    }), "utf-8")  # fmt: skip
    cd = ad / "Claude"
    (cd / "Claude Extensions" / "ant.dir.x.dosya").mkdir(parents=True)
    (cd / "Claude Extensions" / "ant.dir.x.dosya" / "manifest.json").write_text(json.dumps({
        "display_name": "Dosyalar",
        "server": {"mcp_config": {"command": "node", "args": ["${__dirname}/i.js", "${user_config.dirs}"]}},
        "user_config": {"dirs": {"default": ["C:/a", "C:/b"]}},
    }), "utf-8")  # fmt: skip
    (cd / "claude_desktop_config.json").write_text(json.dumps({"mcpServers": {}}), "utf-8")
    b = {x["ad"]: x for x in mcp_ice.bul(ev, ad)}
    assert b["rea-ajan"]["veri"]["komut"] == "node"
    assert b["uzak"]["veri"]["url"] == "https://a.test/mcp"
    arg = b["dosya"]["veri"]["argumanlar"]
    assert arg[0].endswith("i.js") and arg[1:] == ["C:/a", "C:/b"]  # liste ayri argumanlara


async def test_api_ice_aktar(istemci, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcp_ice, "bul", lambda: [{"anahtar": "k:a", "kaynak": "k", "ad": "aaa",
                        "baslik": "a", "veri": {"ad": "aaa", "komut": "node", "argumanlar": []}}])  # fmt: skip
    r = (await istemci.get("/api/mcp/ice-aktar")).json()
    assert r["bulunan"][0]["var"] is False and r["dizin"]
    r = (await istemci.post("/api/mcp/ice-aktar", json={"anahtarlar": ["k:a"]})).json()
    assert r["eklenen"] == ["aaa"]
    assert (await istemci.get("/api/mcp/ice-aktar")).json()["bulunan"][0]["var"] is True
