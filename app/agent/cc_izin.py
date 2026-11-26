"""CLI izin koprusu: headless `claude -p`, `codex exec` ve `agy -p` izin soramaz; PreToolUse
hook'u her arac cagrisini Kairo'nun izin motoruna sorar. izin -> allow, ret -> deny, sor ->
Kairo'da onay karti cikar, kullanici karar verene kadar hook bekler.

- Hook komutu Kairo'nun kendisidir (`--cc-izin`); adres ve oturum anahtari ortamdan gelir
  (komut satirinda gorunmez).
- Kairo'ya ulasilamazsa ya da cevap bozuksa DENY (fail-closed).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

from app.agent.policy import Istek, YanEtki

URL_ORTAM, ANAHTAR_ORTAM, BAGLAM_ORTAM = "KAIRO_IZIN_URL", "KAIRO_IZIN_ANAHTAR", "KAIRO_IZIN_BAGLAM"
BEKLEME_SN = 300  # kullanicinin karar suresi (onay gecerliligi kadar); hook zaman asimi da bu

_OKU = {
    "Read", "Glob", "Grep", "LS", "NotebookRead", "TodoWrite", "Task", "Agent", "TaskOutput",
    "ExitPlanMode", "ToolSearch", "Skill", "ListMcpResourcesTool", "ReadMcpResourceTool",
    "read_file", "view_file", "grep_search", "find_by_name", "list_dir", "list_resources",
    "read_resource",
}  # fmt: skip
_YAZ = {
    "Edit", "Write", "MultiEdit", "NotebookEdit",
    "write_file", "edit_file", "apply_patch", "replace_file_content", "multi_replace_file_content",
}  # fmt: skip
_KOMUT = {
    "Bash", "PowerShell", "BashOutput", "KillShell", "KillBash",
    "run_command", "shell", "exec_command", "container.exec", "local_shell",
}  # fmt: skip


def istek_cevir(arac: str, girdi: dict) -> Istek:
    """CLI arac cagrisini Kairo izin istegine cevirir. Bilinmeyen arac dis etki sayilir."""
    ozet = f"CLI {arac}: {json.dumps(girdi, ensure_ascii=False)[:200]}"
    a = f"cc:{arac}"
    yol = (
        girdi.get("file_path")
        or girdi.get("notebook_path")
        or girdi.get("path")
        or girdi.get("Path")
        or girdi.get("TargetFile")
    )
    if arac in _YAZ:
        return Istek(arac=a, yan_etki=YanEtki.yaz, yol=yol, ozet=ozet)
    if arac in _OKU:
        return Istek(arac=a, yan_etki=YanEtki.oku, yol=yol, ozet=ozet)
    if arac in _KOMUT:
        komut = str(
            girdi.get("command")
            or girdi.get("CommandLine")
            or (
                " ".join(map(str, girdi["cmd"]))
                if isinstance(girdi.get("cmd"), list)
                else girdi.get("cmd")
            )
            or girdi.get("bash_id")
            or girdi.get("shell_id")
            or ""
        )
        return Istek(arac=a, yan_etki=YanEtki.komut, komut=komut, ozet=ozet)
    if arac in ("WebFetch", "read_url_content"):
        hedef_url = str(girdi.get("url") or girdi.get("Url") or "")
        host = urlsplit(hedef_url).hostname or ""
        return Istek(arac=a, yan_etki=YanEtki.ag, host=host, ozet=ozet)
    if arac in ("WebSearch", "search_web"):
        return Istek(arac=a, yan_etki=YanEtki.ag, host="web-arama", ozet=ozet)
    return Istek(arac=a, yan_etki=YanEtki.dis, ozet=ozet)  # mcp__*, bilinmeyen


def hook_cikti(izin: bool, neden: str) -> dict:
    karar = "allow" if izin else "deny"
    return {
        "decision": karar,
        "reason": neden,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": karar,
            "permissionDecisionReason": neden,
        },
    }


def hook_argv() -> list[str]:
    """Hook sureci: derlenmiste exe'nin kendisi, gelistirmede python (kum.argv ile ayni ilke)."""
    # ileri egik cizgi: hook bash'te de cmd'de de calisir (bash ters boluyu kacis sayar)
    exe = Path(sys.executable).as_posix()
    if getattr(sys, "frozen", False):
        return [exe, "--cc-izin"]
    depo = Path(__file__).resolve().parents[2].as_posix()
    kod = (
        f"import sys; sys.path.insert(0, {depo!r}); "
        "from app.agent.cc_izin import main; sys.exit(main())"
    )
    return [exe, "-P", "-c", kod]


def ayar_json() -> str:
    """`claude --settings` ve `agy --settings` icin PreToolUse hook tanimi (tum araclar)."""
    komut = " ".join(f'"{p}"' for p in hook_argv())
    hook = {"type": "command", "command": komut, "timeout": BEKLEME_SN + 30}
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [hook]}]}})


def codex_home_hazirla(hedef: Path, kaynak: Path | None = None) -> Path:
    """Codex CLI `--settings` almaz; gecici CODEX_HOME icine kimlik dosyalarini ve
    Kairo PreToolUse hook'unu yazar."""
    kaynak = kaynak or (Path.home() / ".codex")
    hedef.mkdir(parents=True, exist_ok=True)
    for ad in ("auth.json", "config.toml", "version.json", "models_cache.json"):
        k = kaynak / ad
        if k.is_file():
            shutil.copy2(k, hedef / ad)
    mevcut: dict = {}
    if (kaynak / "hooks.json").is_file():
        try:
            mevcut = json.loads((kaynak / "hooks.json").read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            mevcut = {}
    hooks = dict(mevcut.get("hooks") or {})
    komut = " ".join(f'"{p}"' for p in hook_argv())
    kairo_hook = {
        "matcher": "*",
        "hooks": [{"type": "command", "command": komut, "timeout": BEKLEME_SN + 30}],
    }
    hooks["PreToolUse"] = [*list(hooks.get("PreToolUse") or []), kairo_hook]
    (hedef / "hooks.json").write_text(
        json.dumps({"hooks": hooks}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return hedef


def main() -> int:
    """Hook girisi: stdin'de Claude Code olayi, stdout'a karar. Her hatada deny."""
    import httpx

    try:
        olay = json.loads(sys.stdin.read() or "{}")
        cevap = httpx.post(
            os.environ[URL_ORTAM],
            json={"arac": olay.get("tool_name", ""), "girdi": olay.get("tool_input") or {},
                  "klasor": olay.get("cwd", ""), "baglam": os.environ.get(BAGLAM_ORTAM, "")},
            headers={"x-yas-oturum": os.environ[ANAHTAR_ORTAM]},
            timeout=BEKLEME_SN + 15,
        )  # fmt: skip
        veri = cevap.json()
        cikti = hook_cikti(bool(veri.get("izin")), str(veri.get("neden") or ""))
    except Exception as e:  # noqa: BLE001 - fail-closed
        cikti = hook_cikti(False, f"Kairo izin motoruna ulasilamadi: {type(e).__name__}")
    sys.stdout.write(json.dumps(cikti, ensure_ascii=False))
    return 0
