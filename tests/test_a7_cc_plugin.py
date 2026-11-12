"""Claude Code plugin formati: manifest, komut, ajan, hook (claude bicimi), MCP, marketplace."""
# ruff: noqa: E501

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.agent.hooks import HookDeposu
from app.services import cc_plugin as cc
from app.services.pluginler import PluginDeposu


def cc_plugin(kok: Path) -> Path:
    p = kok / "ornek"
    (p / ".claude-plugin").mkdir(parents=True)
    (p / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "Ornek Plugin", "version": "v2.1", "author": {"name": "x"}}), "utf-8"
    )
    (p / "commands" / "git").mkdir(parents=True)
    (p / "commands" / "selam.md").write_text(
        "---\ndescription: Selamla\nargument-hint: <ad>\n---\nMerhaba $1, tum: $ARGUMENTS "
        "kok=${CLAUDE_PLUGIN_ROOT}",
        "utf-8",
    )
    (p / "commands" / "git" / "durum.md").write_text("git durum", "utf-8")
    (p / "agents").mkdir()
    (p / "agents" / "inceleyici.md").write_text(
        "---\nname: inceleyici\ndescription: Kod inceler\ntools: Read, Grep, Bash\n---\nSen bir "
        "inceleyicisin.",
        "utf-8",
    )
    (p / "skills" / "rapor").mkdir(parents=True)
    (p / "skills" / "rapor" / "SKILL.md").write_text("---\nname: rapor\n---\nx", "utf-8")
    betik = p / "engel.py"
    betik.write_text(
        "import json,sys\nd=json.load(sys.stdin)\n"
        "sys.exit(2 if 'rm' in d['tool_input'].get('komut','') else 0)\n",
        "utf-8",
    )
    (p / "hooks").mkdir()
    (p / "hooks" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f'"{sys.executable}" "${{CLAUDE_PLUGIN_ROOT}}/engel.py"',
                                }
                            ],
                        }
                    ],
                    "Notification": [{"hooks": [{"type": "command", "command": "x"}]}],
                    "SessionEnd": [{"hooks": [{"type": "command", "command": "x"}]}],
                }
            }
        ),  # fmt: skip
        "utf-8",
    )
    (p / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "yerel": {"command": "node", "args": ["${CLAUDE_PLUGIN_ROOT}/s.js"]},
                    "uzak": {
                        "type": "http",
                        "url": "https://x.test/mcp",
                        "headers": {"A": "${YOK_DEGISKEN:-vars}"},
                    },
                }
            }
        ),  # fmt: skip
        "utf-8",
    )
    return p


def test_bilesenler_ve_donusumler(tmp_path) -> None:
    p = cc_plugin(tmp_path)
    b = cc.bilesenler(p)
    assert {k["ad"] for k in b["komutlar"]} == {"selam", "git:durum"}
    ajan = b["ajanlar"][0]
    assert ajan["araclar"] == ["proje_dosya_oku", "proje_ara", "komut_calistir"]
    assert b["hooks"][0]["olay"] == "pre_tool" and b["hooks"][0]["eslesen"] == "Bash"
    assert "hook olayi SessionEnd" in b["desteklenmeyen"]  # karsiligi olmayan olay raporlanir
    assert "hook olayi Notification" not in b["desteklenmeyen"]  # 2026-11-12: bildirim
    assert {h["olay"] for h in b["hooks"]} == {"pre_tool", "bildirim"}
    selam = next(k for k in b["komutlar"] if k["ad"] == "selam")
    assert cc.komut_genislet(selam["govde"], "Umut Celik", p) == (
        f"Merhaba Umut, tum: Umut Celik kok={p}"
    )
    assert cc.mcp_donustur("y", b["mcp"]["yerel"], p)["argumanlar"] == [f"{p}/s.js"]
    assert cc.mcp_donustur("u", b["mcp"]["uzak"], p)["basliklar"] == {"A": "vars"}
    assert (
        cc.surum_normalize("v2.1") == "2.1.0" and cc.ad_normalize("Ornek Plugin") == "ornek-plugin"
    )


def test_kurulum_komut_ajan_hook_mcp(tmp_path) -> None:
    d = PluginDeposu(tmp_path / "veri")
    k = d.karantinaya_al(str(cc_plugin(tmp_path)))
    assert k["bilesenler"]["komut"] and k["bilesenler"]["skill"] == 1
    d.kur(k["karantina"])
    assert {x["komut"] for x in d.komutlar()} == {"ornek-plugin:selam", "ornek-plugin:git:durum"}
    assert d.komut_genislet("selam", "Ali")["istem"].startswith("Merhaba Ali")
    assert "ornek-plugin:inceleyici" in d.ajan_profilleri()
    # hook ve MCP komut calistirir: kullanici acana kadar kapali
    assert d.hook_tanimlari() == [] and d.mcp_tanimlari() == []
    d.bilesen_ac("ornek-plugin", "hooks", True)
    d.bilesen_ac("ornek-plugin", "mcp", True)
    assert len(d.mcp_tanimlari()) == 2

    h = HookDeposu(tmp_path / "veri")
    h.ek_kaynak = d.hook_tanimlari
    engel = h.tetikle("pre_tool", {"arac": "komut_calistir", "argumanlar": {"komut": "rm -rf x"}},
                      arac="komut_calistir")  # fmt: skip
    assert not engel.izin
    assert h.tetikle("pre_tool", {"arac": "komut_calistir", "argumanlar": {"komut": "ls"}},
                     arac="komut_calistir").izin  # fmt: skip
    # matcher Bash: baska araca uygulanmaz
    assert h.tetikle("pre_tool", {"arac": "proje_dosya_oku"}, arac="proje_dosya_oku").calisan == []


def test_manifestsiz_ve_marketplace(tmp_path) -> None:
    ham = tmp_path / "lsp" / "1.0.0"
    ham.mkdir(parents=True)
    (ham / "README.md").write_text("x", "utf-8")
    d = PluginDeposu(tmp_path / "veri")
    assert d.karantinaya_al(str(ham))["manifest"]["name"] == "lsp"
    (tmp_path / "bos").mkdir()
    try:
        d.karantinaya_al(str(tmp_path / "bos"))
        raise AssertionError("bos klasor kabul edilmemeli")
    except Exception as e:  # noqa: BLE001
        assert "bos" in str(e)

    pazar = tmp_path / "pazar"
    (pazar / ".claude-plugin").mkdir(parents=True)
    cc_plugin(pazar)
    (pazar / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"name": "pz", "plugins": [
        {"name": "ornek", "source": "./ornek"},
        {"name": "uzak", "source": {"source": "github", "repo": "a/b"}},
    ]}), "utf-8")  # fmt: skip
    m = cc.marketplace_oku(pazar)
    assert m["pluginler"][1]["kaynak"] == {"tur": "git", "url": "https://github.com/a/b.git",
                                           "ref": ""}  # fmt: skip
    assert d.marketplace_karantina(str(pazar), "ornek")["manifest"]["name"] == "ornek-plugin"


def test_claude_code_esitle(tmp_path, monkeypatch) -> None:
    kaynak = cc_plugin(tmp_path / "cc")
    giris = {"ad": "ornek@pazar", "yol": str(kaynak), "surum": "2.1", "bos": False}
    monkeypatch.setattr(cc, "claude_code_kurulu", lambda: [giris])
    d = PluginDeposu(tmp_path / "veri")
    assert d.claude_code_esitle()["kuruldu"] == ["ornek-plugin"]
    assert d.hook_tanimlari() == []  # kod calistiran kisimlar kapali gelir
    assert d.claude_code_esitle()["atlandi"] == 1  # ayni yol: tekrar kurulmaz
    d.kaldir("ornek-plugin")
    assert d.claude_code_esitle()["kuruldu"] == []  # kullanicinin kaldirdigi geri gelmez


async def test_model_ile_skill_secimi(tmp_path) -> None:
    from app.services.skiller import SkillDeposu, model_ile_sec, secim_coz

    for ad, ac in (("x-control", "X Twitter bookmark yonetir"), ("pdf", "PDF dosyasi okur")):
        (tmp_path / ad).mkdir()
        (tmp_path / ad / "SKILL.md").write_text(
            f"---\nname: {ad}\ndescription: {ac}\n---\nx", "utf-8"
        )
    sk = SkillDeposu(tmp_path, [("claude", tmp_path)]).kesfet()

    class Llm:
        def __init__(self, cevap: str) -> None:
            self.cevap, self.istem = cevap, ""

        async def metin(self, istem: str, **_: object) -> str:
            self.istem = istem
            return self.cevap

    llm = Llm("1")
    s = await model_ile_sec(llm, sk, "twitter bookmark cek", "twitter bookmark cek")
    assert s and s.ad == "x-control" and "x-control" in llm.istem
    assert await model_ile_sec(Llm("0"), sk, "bookmark", "bookmark") is None
    assert (
        await model_ile_sec(Llm("1"), sk, "merhaba", "merhaba") is None
    )  # aday yok: model cagrilmaz
    assert secim_coz("Cevap: 9", sk) is None and secim_coz("", sk) is None
