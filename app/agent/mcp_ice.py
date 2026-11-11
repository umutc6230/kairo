# ruff: noqa: E501 - dizin tablosu
"""Claude Code ve Claude Desktop'taki baglayicilari (MCP) bulup ice aktarma + hazir dizin.

Kaynaklar (hicbiri calistirilmaz, yalniz okunur):
- ~/.claude.json: mcpServers (kullanici) ve projects.*.mcpServers (proje)
- %APPDATA%/Claude/claude_desktop_config.json: mcpServers
- %APPDATA%/Claude/Claude Extensions/*/manifest.json: server.mcp_config (${__dirname},
  ${user_config.x} ayar dosyasindan ya da manifest varsayilanindan)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from app.services import cc_plugin as cc

AD_TEMIZ = re.compile(r"[^a-z0-9_-]+")

# Claude'un "Discover" listesine benzer hazir baglayicilar; {deger} kullanicidan istenir
DIZIN = [
    {"ad": "context7", "baslik": "Context7", "aciklama": "Kutuphanelerin guncel dokumantasyonu.",
     "url": "https://mcp.context7.com/mcp"},
    {"ad": "linear", "baslik": "Linear", "aciklama": "Issue ve proje takibi (hesabinla giris).",
     "url": "https://mcp.linear.app/mcp", "oauth": True},
    {"ad": "notion", "baslik": "Notion", "aciklama": "Sayfa ve veritabanlarin (hesabinla giris).",
     "url": "https://mcp.notion.com/mcp", "oauth": True},
    {"ad": "sentry", "baslik": "Sentry", "aciklama": "Hata kayitlari ve olaylar (hesabinla giris).",
     "url": "https://mcp.sentry.dev/mcp", "oauth": True},
    {"ad": "github", "baslik": "GitHub", "aciklama": "Issue, PR, depo arama ve yonetimi.",
     "url": "https://api.githubcopilot.com/mcp/", "baslik_iste": "GitHub token (ghp_...)"},
    {"ad": "playwright", "baslik": "Playwright", "aciklama": "Tarayici otomasyonu ve test.",
     "komut": "npx", "argumanlar": ["-y", "@playwright/mcp@latest"]},
    {"ad": "dosyalar", "baslik": "Filesystem", "aciklama": "Secilen klasorlerde dosya islemleri.",
     "komut": "npx", "argumanlar": ["-y", "@modelcontextprotocol/server-filesystem", "{klasor}"]},
    {"ad": "fetch", "baslik": "Fetch", "aciklama": "Web sayfalarini indirip metne cevirir.",
     "komut": "uvx", "argumanlar": ["mcp-server-fetch"]},
    {"ad": "hafiza-grafi", "baslik": "Memory", "aciklama": "Kalici bilgi grafigi hafizasi.",
     "komut": "npx", "argumanlar": ["-y", "@modelcontextprotocol/server-memory"]},
    {"ad": "dusunme", "baslik": "Sequential Thinking", "aciklama": "Adim adim problem cozme araci.",
     "komut": "npx", "argumanlar": ["-y", "@modelcontextprotocol/server-sequential-thinking"]},
    {"ad": "git", "baslik": "Git", "aciklama": "Yerel git deposunu okuma ve islemler.",
     "komut": "uvx", "argumanlar": ["mcp-server-git", "--repository", "{klasor}"]},
]  # fmt: skip


def _ad(ham: str) -> str:
    return AD_TEMIZ.sub("-", ham.lower()).strip("-_")[:32] or "mcp"


def _json(p: Path) -> dict:
    try:
        v = json.loads(p.read_text(encoding="utf-8-sig"))
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _uzanti(kok: Path, ayar_dizini: Path) -> tuple[str, dict] | None:
    m = _json(kok / "manifest.json")
    cfg = (m.get("server") or {}).get("mcp_config")
    if not isinstance(cfg, dict):
        return None
    kullanici = (_json(ayar_dizini / f"{kok.name}.json").get("userConfig")) or {}
    for k, v in (m.get("user_config") or {}).items():
        kullanici.setdefault(k, v.get("default") if isinstance(v, dict) else None)

    def ac(s: str) -> list[str]:
        s = s.replace("${__dirname}", str(kok))
        tam = re.fullmatch(r"\$\{user_config\.([\w-]+)\}", s)
        if tam:  # liste degerleri (or. izinli klasorler) ayri argumanlara acilir
            v = kullanici.get(tam.group(1))
            return (
                [str(x) for x in v]
                if isinstance(v, list)
                else ([str(v)] if v not in (None, "") else [])
            )
        return [re.sub(r"\$\{user_config\.([\w-]+)\}",
                       lambda x: str(kullanici.get(x.group(1)) or ""), s)]  # fmt: skip

    ham = {
        "command": cfg.get("command", ""),
        "args": [a for x in cfg.get("args") or [] for a in ac(str(x))],
        "env": {k: ac(str(v))[0] if ac(str(v)) else "" for k, v in (cfg.get("env") or {}).items()},
    }
    return str(m.get("display_name") or m.get("name") or kok.name), ham


def bul(ev: Path | None = None, appdata: Path | None = None) -> list[dict]:
    """[{anahtar, kaynak, ad, baslik, veri}] - veri McpSunucu alanlari (henuz eklenmedi)."""
    ev = ev or Path.home()
    appdata = appdata or Path(os.environ.get("APPDATA", ev / "AppData/Roaming"))
    out: list[dict] = []

    def ekle(kaynak: str, ad: str, ham: dict, kok: Path, baslik: str = "") -> None:
        d = cc.mcp_donustur(_ad(ad), ham, kok)
        if d:
            out.append({"anahtar": f"{kaynak}:{ad}", "kaynak": kaynak, "ad": d["ad"],
                        "baslik": baslik or ad, "veri": d})  # fmt: skip

    cj = _json(ev / ".claude.json")
    for ad, ham in (cj.get("mcpServers") or {}).items():
        ekle("Claude Code", ad, ham, ev)
    for proje, pv in (cj.get("projects") or {}).items():
        for ad, ham in ((pv or {}).get("mcpServers") or {}).items():
            ekle(f"Claude Code ({Path(proje).name})", ad, ham, Path(proje))
    cd = appdata / "Claude"
    for ad, ham in (_json(cd / "claude_desktop_config.json").get("mcpServers") or {}).items():
        ekle("Claude Desktop", ad, ham, cd)
    ext = cd / "Claude Extensions"
    if ext.is_dir():
        for kok in sorted(p for p in ext.iterdir() if p.is_dir() and ".backup" not in p.name):
            r = _uzanti(kok, cd / "Claude Extensions Settings")
            if r:
                ekle("Claude Desktop uzantisi", kok.name.split(".")[-1], r[1], kok, r[0])
    return out
