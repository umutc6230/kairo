# ruff: noqa: E501 - bicim tablosu ve sozluk satirlari okunurluk icin uzun
"""Claude Code plugin formati uyumlulugu.

Desteklenen bilesenler (Claude Code ile ayni dizin yapisi):
- `.claude-plugin/plugin.json` (yoksa kokte `plugin.json`): name, version?, description?, author,
  commands (str|list), skills (str|list), agents (str|list), hooks (yol|nesne), mcpServers (yol|nesne)
- `skills/<ad>/SKILL.md`       -> skill
- `commands/*.md`              -> slash komut (frontmatter: description, argument-hint; $ARGUMENTS, $1..)
- `agents/*.md`                -> alt ajan profili (frontmatter: name, description, tools)
- `hooks/hooks.json`           -> hook (PreToolUse, PostToolUse, SessionStart, Stop, UserPromptSubmit,
                                  PreCompact; yalniz "type": "command"); ${CLAUDE_PLUGIN_ROOT}
- `.mcp.json`                  -> MCP sunucusu (stdio command/args/env ya da http url/headers)
- `.claude-plugin/marketplace.json` -> plugin katalogu (yerel yol ya da git kaynak)

Desteklenmeyen (rapora yazilir, sessizce yutulmaz): `type: prompt` hook, komut icindeki `!`bash``
on-calistirmasi, LSP sunuculari, output-styles.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

# Claude Code arac adi -> bu uygulamanin araclari (hook matcher ve ajan profili 'tools' icin)
ARAC_ESLESME = {
    "Read": ["proje_dosya_oku"],
    "Grep": ["proje_ara"],
    "Glob": ["proje_glob"],
    "LS": ["proje_listele"],
    "Edit": ["proje_dosya_yama"],
    "MultiEdit": ["proje_dosya_yama"],
    "Write": ["proje_dosya_yaz"],
    "Bash": ["komut_calistir"],
    "WebFetch": ["web_getir"],
    "WebSearch": ["web_ara"],
}
TERS_ESLESME = {b: a for a, bs in ARAC_ESLESME.items() for b in bs}
OLAY_ESLESME = {
    "PreToolUse": "pre_tool",
    "PostToolUse": "post_tool",
    "SessionStart": "run_baslangic",
    "Stop": "run_bitis",
    "UserPromptSubmit": "prompt",
    "PreCompact": "compact",
    "SubagentStop": "alt_ajan_bitis",
    "Notification": "bildirim",
}


def _json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _fm(metin: str) -> tuple[dict, str]:
    if not metin.startswith("---"):
        return {}, metin
    son = metin.find("\n---", 3)
    if son < 0:
        return {}, metin
    try:
        m = yaml.safe_load(metin[3:son]) or {}
    except yaml.YAMLError:
        m = {}
    return (m if isinstance(m, dict) else {}), metin[son + 4 :].lstrip("\n")


def ham_manifest(kok: Path) -> dict | None:
    for p in (kok / ".claude-plugin" / "plugin.json", kok / "plugin.json"):
        if p.is_file():
            v = _json(p)
            return v if isinstance(v, dict) else None
    return None


def ad_normalize(ad: str) -> str:
    a = re.sub(r"[^a-z0-9_-]+", "-", str(ad).lower()).strip("-_")
    return a[:48] or "plugin"


def surum_normalize(s: Any) -> str:
    m = re.match(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(s or ""))
    return ".".join(x or "0" for x in m.groups()) if m else "0.0.0"


def _yollar(kok: Path, deger: Any, varsayilan: str) -> list[Path]:
    liste = deger if isinstance(deger, list) else [deger] if isinstance(deger, str) else []
    yollar = [kok / str(x) for x in liste] or [kok / varsayilan]
    k = kok.resolve()
    # plugin koku disina cikan yol kabul edilmez
    return [p for p in yollar if p.resolve().is_relative_to(k)]


def ajan_profili(dosya: Path) -> dict:
    fm, govde = _fm(dosya.read_text(encoding="utf-8", errors="replace"))

    def adlar(alan: str) -> list[str] | None:
        if alan not in fm:
            return None
        deger = fm[alan]
        if isinstance(deger, str):
            deger = deger.split(",")
        if not isinstance(deger, list):
            return []
        return [s.strip() for s in deger if isinstance(s, str) and s.strip()]

    def araclar(alan: str) -> list[str] | None:
        adlar_ = adlar(alan)
        if adlar_ is None:
            return None
        return [b for a in adlar_ for b in ARAC_ESLESME.get(a, [a])]

    return {
        "ad": str(fm.get("name") or dosya.stem),
        "aciklama": str(fm.get("description", ""))[:500],
        "araclar": araclar("tools"),
        "yasak_araclar": araclar("disallowedTools") or [],
        "model": str(fm.get("model") or ""),
        "effort": str(fm.get("effort") or ""),
        "izin": str(fm.get("permissionMode") or ""),
        "isolation": str(fm.get("isolation") or ""),
        "skills": adlar("skills") or [],
        "mcp": adlar("mcpServers"),
        "govde": govde,
    }


def bilesenler(kok: Path) -> dict:
    """Plugin klasorundeki tum Claude Code bilesenlerini cikarir (hicbir sey calistirmaz)."""
    m = ham_manifest(kok) or {}
    sonuc: dict = {"skills": [], "komutlar": [], "ajanlar": [], "hooks": [], "mcp": {},
                   "desteklenmeyen": []}  # fmt: skip
    for d in _yollar(kok, m.get("skills"), "skills"):
        if d.is_dir():
            sonuc["skills"].append(d)
    for d in _yollar(kok, m.get("commands"), "commands"):
        for f in sorted(d.rglob("*.md")) if d.is_dir() else ([d] if d.suffix == ".md" else []):
            fm, govde = _fm(f.read_text(encoding="utf-8", errors="replace"))
            ad = (
                f.relative_to(d).with_suffix("").as_posix().replace("/", ":")
                if d.is_dir()
                else f.stem
            )
            if "!`" in govde:
                sonuc["desteklenmeyen"].append(f"komut {ad}: '!`...`' kabuk on-calistirmasi")
            sonuc["komutlar"].append({
                "ad": ad, "aciklama": str(fm.get("description", ""))[:300],
                "ipucu": str(fm.get("argument-hint", ""))[:200], "govde": govde,
            })  # fmt: skip
    for d in _yollar(kok, m.get("agents"), "agents"):
        for f in sorted(d.glob("*.md")) if d.is_dir() else []:
            sonuc["ajanlar"].append(ajan_profili(f))
    hooks = m.get("hooks")
    if isinstance(hooks, str | list) or hooks is None:
        for p in _yollar(kok, hooks, "hooks/hooks.json"):
            if p.is_file():
                hooks = _json(p)
                break
        else:
            hooks = {}
    for olay, gruplar in ((hooks or {}).get("hooks", hooks) or {}).items():
        if olay not in OLAY_ESLESME:
            sonuc["desteklenmeyen"].append(f"hook olayi {olay}")
            continue
        for g in gruplar if isinstance(gruplar, list) else []:
            for h in g.get("hooks", []) if isinstance(g, dict) else []:
                if not isinstance(h, dict) or h.get("type") != "command" or not h.get("command"):
                    sonuc["desteklenmeyen"].append(f"hook {olay}: type={h.get('type')}")
                    continue
                sonuc["hooks"].append({
                    "olay": OLAY_ESLESME[olay], "eslesen": str(g.get("matcher") or ""),
                    "komut": str(h["command"]), "timeout": int(h.get("timeout") or 60),
                })  # fmt: skip
    mcp = m.get("mcpServers")
    if isinstance(mcp, str) or mcp is None:
        p = (_yollar(kok, mcp, ".mcp.json") or [None])[0]
        mcp = _json(p) if p and p.is_file() else {}
    if isinstance(mcp, dict):
        sonuc["mcp"] = mcp.get("mcpServers", mcp)
    return sonuc


def komut_dosyalari(dizin: Path) -> list[dict]:
    """Claude Code ozel slash komutlari: <dizin>/**/*.md (kullanici ~/.claude/commands ve proje
    .claude/commands). Alt klasor ad alani olur (a/b.md -> a:b). Hicbir sey calistirmaz; dizin
    disina cikan (sembolik link) dosya atlanir."""
    if not dizin.is_dir():
        return []
    kok = dizin.resolve()
    sonuc = []
    for f in sorted(dizin.rglob("*.md"))[:200]:
        try:
            if not f.resolve().is_relative_to(kok) or f.stat().st_size > 200_000:
                continue
            fm, govde = _fm(f.read_text(encoding="utf-8-sig", errors="replace"))
        except OSError:
            continue
        sonuc.append({
            "ad": f.relative_to(dizin).with_suffix("").as_posix().replace("/", ":"),
            "aciklama": str(fm.get("description", ""))[:300],
            "ipucu": str(fm.get("argument-hint", ""))[:200], "govde": govde,
        })  # fmt: skip
    return sonuc


def degisken_ac(metin: str, kok: Path) -> str:
    """${CLAUDE_PLUGIN_ROOT}, ${VAR} ve ${VAR:-varsayilan} (Claude Code ile ayni)."""

    def yerine(m: re.Match) -> str:
        ad, vars_ = m.group(1), m.group(3)
        if ad == "CLAUDE_PLUGIN_ROOT":
            return str(kok)
        return os.environ.get(ad) or (vars_ if vars_ is not None else "")

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}", yerine, metin)


def hook_komutu(komut: str, kok: Path) -> str:
    """Claude Code hook komutunu Windows'ta calisir hale getirir: ${CLAUDE_PLUGIN_ROOT} '/' ile
    acilir; bastaki 'bash' Git Bash'e yonlendirilir (PATH'teki System32 altindaki bash.exe WSL'dir,
    Windows yollarini goremez: 'No such file', cikis 127)."""
    metin = degisken_ac(komut.replace("${CLAUDE_PLUGIN_ROOT}", kok.as_posix()), kok)
    from app.agent.terminal import windows_bash

    gb = windows_bash()
    if gb and re.match(r"^\s*bash(\s|$)", metin):
        metin = re.sub(r"^\s*bash", lambda _: f'"{gb}"', metin, count=1)
    return metin


def komut_genislet(govde: str, arg: str, kok: Path) -> str:
    parcalar = arg.split()
    metin = govde.replace("$ARGUMENTS", arg)
    for i in range(9, 0, -1):
        metin = metin.replace(f"${i}", parcalar[i - 1] if len(parcalar) >= i else "")
    return degisken_ac(metin, kok)


def eksik_degiskenler(metin: str) -> list[str]:
    """Varsayilani olmayan ve bu bilgisayarda tanimli olmayan ${DEGISKEN}'ler."""
    return [m.group(1) for m in re.finditer(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", metin)
            if m.group(1) != "CLAUDE_PLUGIN_ROOT" and not os.environ.get(m.group(1))]  # fmt: skip


def mcp_donustur(ad: str, ham: dict, kok: Path) -> dict | None:
    """Claude Code .mcp.json girdisi -> McpSunucu alanlari."""
    if not isinstance(ham, dict):
        return None
    if ham.get("type") in ("http", "sse") or ham.get("url"):
        basliklar, eksik = {}, []
        for k, v in (ham.get("headers") or {}).items():
            # "Bearer ${TOKEN}" TOKEN yokken "Bearer " olup HTTP katmaninda LocalProtocolError
            # veriyordu; eksik degiskenli baslik gonderilmez, sunucu "kimlik eksik" diye gorunur
            if yok := eksik_degiskenler(str(v)):
                eksik += yok
                continue
            if (deger := degisken_ac(str(v), kok).strip()) and deger.lower() not in (
                "bearer",
                "token",
            ):
                basliklar[k] = deger
        return {"ad": ad, "url": degisken_ac(str(ham.get("url", "")), kok),
                "basliklar": basliklar, "eksik_degiskenler": sorted(set(eksik))}  # fmt: skip
    if ham.get("command"):
        return {"ad": ad, "komut": degisken_ac(str(ham["command"]), kok),
                "argumanlar": [degisken_ac(str(a), kok) for a in ham.get("args") or []],
                "ortam": {k: degisken_ac(str(v), kok) for k, v in (ham.get("env") or {}).items()}}  # fmt: skip
    return None


def marketplace_oku(kok: Path) -> dict:
    p = kok / ".claude-plugin" / "marketplace.json"
    if not p.is_file():
        p = kok / "marketplace.json"
    if not p.is_file():
        raise ValueError("marketplace.json bulunamadi.")
    v = _json(p)
    pluginler = []
    for x in v.get("plugins") or []:
        if not isinstance(x, dict) or not x.get("name"):
            continue
        src = x.get("source")
        if isinstance(src, str):
            kaynak = {"tur": "yol", "yol": str((kok / src).resolve())}
        elif isinstance(src, dict) and src.get("source") in ("github", "git", "url"):
            url = src.get("url") or f"https://github.com/{src.get('repo', '')}.git"
            kaynak = {"tur": "git", "url": url, "ref": src.get("ref") or src.get("sha") or ""}
        else:
            continue
        pluginler.append({"name": x["name"], "description": str(x.get("description", ""))[:300],
                          "version": str(x.get("version", "")), "kaynak": kaynak})  # fmt: skip
    return {"ad": v.get("name", kok.name), "pluginler": pluginler}


def claude_code_kurulu() -> list[dict]:
    """Bu bilgisayardaki Claude Code'un kurulu plugin'leri (~/.claude/plugins/installed_plugins.json)."""
    p = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        v = _json(p)
    except (OSError, ValueError):
        return []
    out = []
    for anahtar, kurulumlar in (v.get("plugins") or {}).items():
        for k in kurulumlar if isinstance(kurulumlar, list) else []:
            yol = Path(k.get("installPath", ""))
            if not yol.is_dir():
                continue  # Claude Code listesinde kalmis, diskten silinmis kayit
            icerik = [p for p in yol.iterdir() if p.name not in (".in_use", ".orphaned_at")]
            out.append({"ad": anahtar, "yol": str(yol), "surum": k.get("version", ""),
                        "bos": not icerik})  # fmt: skip
            break
    return out
