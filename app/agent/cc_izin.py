"""Claude Code izin koprusu: headless `claude -p` izin soramaz; PreToolUse hook'u her arac
cagrisini Kairo'nun izin motoruna sorar. izin -> allow, ret -> deny, sor -> Kairo'da onay karti
cikar, kullanici karar verene kadar hook bekler.

- Hook komutu Kairo'nun kendisidir (`--cc-izin`); adres ve oturum anahtari ortamdan gelir
  (komut satirinda gorunmez).
- Kairo'ya ulasilamazsa ya da cevap bozuksa DENY (fail-closed).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from app.agent.policy import Istek, YanEtki

URL_ORTAM, ANAHTAR_ORTAM, BAGLAM_ORTAM = "KAIRO_IZIN_URL", "KAIRO_IZIN_ANAHTAR", "KAIRO_IZIN_BAGLAM"
BEKLEME_SN = 300  # kullanicinin karar suresi (onay gecerliligi kadar); hook zaman asimi da bu

_OKU = {"Read", "Glob", "Grep", "LS", "NotebookRead", "TodoWrite", "Task", "Agent", "TaskOutput",
        "ExitPlanMode", "ToolSearch", "Skill", "ListMcpResourcesTool",
        "ReadMcpResourceTool"}  # fmt: skip
_YAZ = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_KOMUT = {"Bash", "PowerShell", "BashOutput", "KillShell", "KillBash"}


def istek_cevir(arac: str, girdi: dict) -> Istek:
    """Claude Code arac cagrisini Kairo izin istegine cevirir. Bilinmeyen arac dis etki sayilir."""
    ozet = f"Claude Code {arac}: {json.dumps(girdi, ensure_ascii=False)[:200]}"
    a = f"cc:{arac}"
    yol = girdi.get("file_path") or girdi.get("notebook_path") or girdi.get("path")
    if arac in _YAZ:
        return Istek(arac=a, yan_etki=YanEtki.yaz, yol=yol, ozet=ozet)
    if arac in _OKU:
        return Istek(arac=a, yan_etki=YanEtki.oku, yol=yol, ozet=ozet)
    if arac in _KOMUT:
        komut = str(girdi.get("command") or girdi.get("bash_id") or girdi.get("shell_id") or "")
        return Istek(arac=a, yan_etki=YanEtki.komut, komut=komut, ozet=ozet)
    if arac == "WebFetch":
        host = urlsplit(str(girdi.get("url") or "")).hostname or ""
        return Istek(arac=a, yan_etki=YanEtki.ag, host=host, ozet=ozet)
    if arac == "WebSearch":
        return Istek(arac=a, yan_etki=YanEtki.ag, host="web-arama", ozet=ozet)
    return Istek(arac=a, yan_etki=YanEtki.dis, ozet=ozet)  # mcp__*, bilinmeyen


def hook_cikti(izin: bool, neden: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if izin else "deny",
            "permissionDecisionReason": neden,
        }
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
    """`claude --settings` icin PreToolUse hook tanimi (tum araclar)."""
    komut = " ".join(f'"{p}"' for p in hook_argv())
    hook = {"type": "command", "command": komut, "timeout": BEKLEME_SN + 30}
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [hook]}]}})


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
