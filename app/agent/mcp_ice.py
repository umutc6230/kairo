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
    {"ad": "context7", "baslik": "Context7", "aciklama": "Kütüphanelerin güncel dokümantasyonu.",
     "url": "https://mcp.context7.com/mcp"},
    # OpenBot web arastirma saglayicilari: anahtarsiz ucretsiz kullanim (saglayici sinirli)
    {"ad": "exa", "baslik": "Exa Search", "aciklama": "Web araması ve sayfa okuma (ücretsiz, kaynaklı).",
     "url": "https://mcp.exa.ai/mcp"},
    {"ad": "parallel", "baslik": "Parallel Search", "aciklama": "Derin web araması ve sayfa okuma (hesabınla giriş).",
     "url": "https://search-mcp.parallel.ai/mcp", "oauth": True},
    # Claude Desktop "Popular" listesindeki resmi uzak sunucular (2026-11-13 canli dogrulandi:
    # 401 + WWW-Authenticate = tarayicida hesabınla giriş)
    {"ad": "atlassian", "baslik": "Atlassian", "aciklama": "Jira, Confluence, Bitbucket (hesabınla giriş).",
     "url": "https://mcp.atlassian.com/v1/mcp", "oauth": True},
    {"ad": "canva", "baslik": "Canva", "aciklama": "Tasarım oluştur ve düzenle (hesabınla giriş).",
     "url": "https://mcp.canva.com/mcp", "oauth": True},
    {"ad": "figma", "baslik": "Figma", "aciklama": "Tasarım bağlamından kod ve diyagram (hesabınla giriş).",
     "url": "https://mcp.figma.com/mcp", "oauth": True},
    {"ad": "supabase", "baslik": "Supabase", "aciklama": "Veritabanı, kimlik ve depolama (hesabınla giriş).",
     "url": "https://mcp.supabase.com/mcp", "oauth": True},
    {"ad": "asana", "baslik": "Asana", "aciklama": "Görev ve proje yönetimi (hesabınla giriş).",
     "url": "https://mcp.asana.com/v2/mcp", "oauth": True},
    {"ad": "vercel", "baslik": "Vercel", "aciklama": "Dağıtım ve projeler (hesabınla giriş).",
     "url": "https://mcp.vercel.com", "oauth": True},
    {"ad": "stripe", "baslik": "Stripe", "aciklama": "Ödeme verileri (hesabınla giriş).",
     "url": "https://mcp.stripe.com", "oauth": True},
    {"ad": "box", "baslik": "Box", "aciklama": "Dosya ve içerikler (hesabınla giriş).",
     "url": "https://mcp.box.com", "oauth": True},
    {"ad": "zapier", "baslik": "Zapier", "aciklama": "Binlerce uygulamada otomasyon (hesabınla giriş).",
     "url": "https://mcp.zapier.com/api/mcp/mcp", "oauth": True},
    {"ad": "huggingface", "baslik": "Hugging Face", "aciklama": "Model, veri seti ve Space arama.",
     "url": "https://huggingface.co/mcp"},
    {"ad": "cloudflare-docs", "baslik": "Cloudflare Docs", "aciklama": "Cloudflare dokümantasyonu.",
     "url": "https://docs.mcp.cloudflare.com/mcp"},
    {"ad": "linear", "baslik": "Linear", "aciklama": "Issue ve proje takibi (hesabınla giriş).",
     "url": "https://mcp.linear.app/mcp", "oauth": True},
    {"ad": "notion", "baslik": "Notion", "aciklama": "Sayfa ve veritabanların (hesabınla giriş).",
     "url": "https://mcp.notion.com/mcp", "oauth": True},
    {"ad": "sentry", "baslik": "Sentry", "aciklama": "Hata kayıtları ve olaylar (hesabınla giriş).",
     "url": "https://mcp.sentry.dev/mcp", "oauth": True},
    # 2026-11-13 canli yoklandi: 401 + oauth-authorization-server'da registration_endpoint (DCR)
    {"ad": "netlify", "baslik": "Netlify", "aciklama": "Site dağıtımı ve projeler (hesabınla giriş).",
     "url": "https://netlify-mcp.netlify.app/mcp", "oauth": True},
    {"ad": "cloudflare", "baslik": "Cloudflare", "aciklama": "Workers, KV, R2, D1 (hesabınla giriş).",
     "url": "https://bindings.mcp.cloudflare.com/mcp", "oauth": True},
    {"ad": "neon", "baslik": "Neon", "aciklama": "Serverless Postgres veritabanları (hesabınla giriş).",
     "url": "https://mcp.neon.tech/mcp", "oauth": True},
    {"ad": "prisma", "baslik": "Prisma", "aciklama": "Prisma Postgres veritabanları (hesabınla giriş).",
     "url": "https://mcp.prisma.io/mcp", "oauth": True},
    {"ad": "railway", "baslik": "Railway", "aciklama": "Uygulama dağıtımı ve servisler (hesabınla giriş).",
     "url": "https://mcp.railway.com/mcp", "oauth": True},
    {"ad": "gitlab", "baslik": "GitLab", "aciklama": "Depo, issue ve merge request (hesabınla giriş).",
     "url": "https://gitlab.com/api/v4/mcp", "oauth": True},
    {"ad": "posthog", "baslik": "PostHog", "aciklama": "Ürün analitiği ve özellik bayrakları (hesabınla giriş).",
     "url": "https://mcp.posthog.com/mcp", "oauth": True},
    {"ad": "monday", "baslik": "monday.com", "aciklama": "İş panoları ve görevler (hesabınla giriş).",
     "url": "https://mcp.monday.com/mcp", "oauth": True},
    {"ad": "clickup", "baslik": "ClickUp", "aciklama": "Görev ve doküman yönetimi (hesabınla giriş).",
     "url": "https://mcp.clickup.com/mcp", "oauth": True},
    {"ad": "airtable", "baslik": "Airtable", "aciklama": "Tablo ve kayıtlar (hesabınla giriş).",
     "url": "https://mcp.airtable.com/mcp", "oauth": True},
    {"ad": "miro", "baslik": "Miro", "aciklama": "Beyaz tahta ve diyagramlar (hesabınla giriş).",
     "url": "https://mcp.miro.com/", "oauth": True},
    {"ad": "webflow", "baslik": "Webflow", "aciklama": "Site ve CMS içerikleri (hesabınla giriş).",
     "url": "https://mcp.webflow.com/mcp", "oauth": True},
    {"ad": "wix", "baslik": "Wix", "aciklama": "Site, mağaza ve içerik (hesabınla giriş).",
     "url": "https://mcp.wix.com/mcp", "oauth": True},
    {"ad": "sanity", "baslik": "Sanity", "aciklama": "İçerik yönetimi (hesabınla giriş).",
     "url": "https://mcp.sanity.io", "oauth": True},
    {"ad": "cloudinary", "baslik": "Cloudinary", "aciklama": "Görsel ve video varlıkları (hesabınla giriş).",
     "url": "https://asset-management.mcp.cloudinary.com/sse", "oauth": True},
    {"ad": "intercom", "baslik": "Intercom", "aciklama": "Müşteri konuşmaları (hesabınla giriş).",
     "url": "https://mcp.intercom.com/mcp", "oauth": True},
    {"ad": "attio", "baslik": "Attio", "aciklama": "CRM kayıtları (hesabınla giriş).",
     "url": "https://mcp.attio.com/mcp", "oauth": True},
    {"ad": "close", "baslik": "Close", "aciklama": "Satış CRM'i (hesabınla giriş).",
     "url": "https://mcp.close.com/mcp", "oauth": True},
    {"ad": "paypal", "baslik": "PayPal", "aciklama": "Fatura ve işlemler (hesabınla giriş).",
     "url": "https://mcp.paypal.com/mcp", "oauth": True},
    {"ad": "square", "baslik": "Square", "aciklama": "Satış, ödeme ve envanter (hesabınla giriş).",
     "url": "https://mcp.squareup.com/mcp", "oauth": True},
    {"ad": "plaid", "baslik": "Plaid", "aciklama": "Plaid geliştirici paneli (hesabınla giriş).",
     "url": "https://api.dashboard.plaid.com/mcp", "oauth": True},
    {"ad": "jam", "baslik": "Jam", "aciklama": "Hata kayıtları ve ekran videoları (hesabınla giriş).",
     "url": "https://mcp.jam.dev/mcp", "oauth": True},
    {"ad": "fireflies", "baslik": "Fireflies", "aciklama": "Toplantı kayıtları ve özetler (hesabınla giriş).",
     "url": "https://api.fireflies.ai/mcp", "oauth": True},
    {"ad": "granola", "baslik": "Granola", "aciklama": "Toplantı notları (hesabınla giriş).",
     "url": "https://mcp.granola.ai/mcp", "oauth": True},
    {"ad": "deepwiki", "baslik": "DeepWiki", "aciklama": "Açık GitHub depolarının dokümantasyonu (anahtarsız).",
     "url": "https://mcp.deepwiki.com/mcp"},
    {"ad": "github", "baslik": "GitHub", "aciklama": "Issue, PR, depo arama ve yönetimi.",
     "url": "https://api.githubcopilot.com/mcp/", "baslik_iste": "GitHub token (ghp_...)"},
    {"ad": "playwright", "baslik": "Playwright", "aciklama": "Tarayıcı otomasyonu ve test.",
     "komut": "npx", "argumanlar": ["-y", "@playwright/mcp@latest"]},
    {"ad": "dosyalar", "baslik": "Filesystem", "aciklama": "Seçilen klasörlerde dosya işlemleri.",
     "komut": "npx", "argumanlar": ["-y", "@modelcontextprotocol/server-filesystem", "{klasor}"]},
    {"ad": "fetch", "baslik": "Fetch", "aciklama": "Web sayfalarını indirip metne çevirir.",
     "komut": "uvx", "argumanlar": ["mcp-server-fetch"]},
    {"ad": "hafiza-grafi", "baslik": "Memory", "aciklama": "Kalıcı bilgi grafiği hafızası.",
     "komut": "npx", "argumanlar": ["-y", "@modelcontextprotocol/server-memory"]},
    {"ad": "dusunme", "baslik": "Sequential Thinking", "aciklama": "Adım adım problem çözme aracı.",
     "komut": "npx", "argumanlar": ["-y", "@modelcontextprotocol/server-sequential-thinking"]},
    {"ad": "git", "baslik": "Git", "aciklama": "Yerel git deposunu okuma ve işlemler.",
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
        if isinstance(v, dict) and v.get("required") and kullanici.get(k) in (None, "", []):
            # Zorunlu ayar (or. filesystem'in izinli klasorleri) Claude Desktop'ta secilmemis:
            # bos aktarilan sunucu her istegi reddediyordu ("path outside allowed directories").
            return None

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
