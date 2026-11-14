"""Kalici ajanin saglayicisi olarak Claude Code / Codex CLI'larini surer (openbot'un saglayici
modelinden uyarlandi). Kullanicinin KENDI aboneligi ve oturumu kullanilir; Kairo token gormez.

- Claude Code: `claude -p ... --output-format stream-json --verbose`; oturum `--resume <id>`.
- Codex: `codex exec --json -C <klasor>`; oturum `codex exec resume <id>`.
- Antigravity: `agy -p ... --output-format stream-json`; oturum `--conversation <id>`
  (argumanlar 2026-11-14 `agy --help` ve canli ciktiyla dogrulandi).
- Ortam: Kairo'nun izinli ortam listesi (ortam_allowlist). Bu, ust surecin (or. Claude Desktop)
  oturum degiskenlerini tasimaz; tasirsa ic ice CLI bos cikti verip cikiyordu (canli gozlem).
- Izin: Kairo'da tam yetki aciksa Claude `bypassPermissions` / Codex `danger-full-access`;
  degilse Claude `acceptEdits` (dosya duzenler, komut sormadan calistiramaz) / Codex
  `workspace-write` (yalniz calisma klasorune yazar).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.agent.dosyalar import ortam_allowlist

SAGLAYICILAR = {
    "kairo": "Kairo ajani", "claude": "Claude Code", "codex": "Codex", "antigravity": "Antigravity",
}  # fmt: skip
MAX_LOG = 200
ZAMAN_ASIMI = 3600


def _npm() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules"


def claude_yolu() -> str | None:
    aday = _npm() / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    if aday.is_file():
        return str(aday)
    for ad in ("claude.exe", "claude"):
        y = shutil.which(ad)
        if y and Path(y).stat().st_size > 0 and "system32" not in y.lower():
            return y
    return None


def codex_komutu() -> list[str] | None:
    js = _npm() / "@openai" / "codex" / "bin" / "codex.js"
    node = shutil.which("node")
    if js.is_file() and node:
        return [node, str(js)]
    y = shutil.which("codex.exe")
    return [y] if y else None


def agy_yolu() -> str | None:
    aday = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
    return str(aday) if aday.is_file() else shutil.which("agy")


def durum() -> dict:
    return {"claude": bool(claude_yolu()), "codex": bool(codex_komutu()),
            "antigravity": bool(agy_yolu())}  # fmt: skip


def komut_kur(
    saglayici: str, mesaj: str, klasor: Path, *, oturum: str = "", tam_yetki: bool = False,
    ek_sistem: str = "", model: str = "",
) -> list[str]:  # fmt: skip
    if saglayici == "claude":
        exe = claude_yolu()
        if not exe:
            raise RuntimeError("Claude Code CLI bulunamadi (npm i -g @anthropic-ai/claude-code).")
        k = [exe, "-p", mesaj, "--output-format", "stream-json", "--verbose",
             "--permission-mode", "bypassPermissions" if tam_yetki else "acceptEdits"]  # fmt: skip
        if ek_sistem:
            k += ["--append-system-prompt", ek_sistem]
        if oturum:
            k += ["--resume", oturum]
        if model:
            k += ["--model", model]
        return k
    if saglayici == "codex":
        taban = codex_komutu()
        if not taban:
            raise RuntimeError("Codex CLI bulunamadi (npm i -g @openai/codex).")
        istem = f"{ek_sistem}\n\n---\n{mesaj}" if ek_sistem and not oturum else mesaj
        k = [*taban, "exec", "--json", "--skip-git-repo-check", "-C", str(klasor),
             "-s", "danger-full-access" if tam_yetki else "workspace-write"]  # fmt: skip
        if model:
            k += ["-m", model]
        return [*k, "resume", oturum, istem] if oturum else [*k, istem]
    if saglayici == "antigravity":
        exe = agy_yolu()
        if not exe:
            raise RuntimeError("Antigravity CLI (agy) bulunamadi.")
        istem = f"{ek_sistem}\n\n---\n{mesaj}" if ek_sistem and not oturum else mesaj
        k = [exe, "-p", istem, "--output-format", "stream-json", "--add-dir", str(klasor)]
        k += ["--dangerously-skip-permissions"] if tam_yetki else ["--mode", "accept-edits"]
        if oturum:
            k += ["--conversation", oturum]
        if model:
            k += ["--model", model]
        return k
    raise RuntimeError(f"Bilinmeyen saglayici: {saglayici}")


@dataclass
class CliSonuc:
    durum: str = "basarisiz"  # basarili | basarisiz | iptal
    ozet: str = ""
    oturum: str = ""
    maliyet_usd: float = 0.0
    log: list[str] = field(default_factory=list)


def olay_isle(saglayici: str, e: dict, s: CliSonuc) -> None:
    """Tek JSON satirini sonuca isler (oturum, ilerleme logu, son metin, hata)."""
    t = e.get("type")
    if saglayici == "claude":
        if e.get("session_id"):
            s.oturum = e["session_id"]
        if t == "assistant":
            for c in (e.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    arg = json.dumps(c.get("input") or {}, ensure_ascii=False)[:160]
                    s.log.append(f"🔧 {c.get('name')} {arg}")
                elif c.get("type") == "text" and c.get("text", "").strip():
                    s.log.append(c["text"].strip()[:400])
        elif t == "result":
            s.ozet = str(e.get("result") or "").strip()
            s.maliyet_usd = float(e.get("total_cost_usd") or 0)
            s.durum = "basarisiz" if e.get("is_error") else "basarili"
        return
    if saglayici == "antigravity":
        olay = e.get("event")
        if e.get("conversation_id"):
            s.oturum = e["conversation_id"]
        if olay == "step_update":
            st = e.get("step_update") or {}
            if st.get("step_type") == "tool" and st.get("state") in ("DONE", "ERROR"):
                arg = json.dumps((st.get("tool_info") or {}).get("parameters") or {},
                                 ensure_ascii=False)[:160]  # fmt: skip
                isaret = "🔧" if st["state"] == "DONE" else "⚠"
                s.log.append(f"{isaret} {st.get('tool_name')} {arg}")
        elif olay == "result":
            res = e.get("result") or {}
            s.oturum = res.get("conversation_id") or s.oturum
            s.ozet = str(res.get("response") or "").strip()
            basarili = res.get("status") == "SUCCESS" and bool(s.ozet)  # ret notundan once
            reddedilen = [d.get("action") for d in res.get("denied_actions") or []]
            if reddedilen:  # headless onay soramaz; kullaniciya neden eksik kaldigini soyle
                s.ozet += (
                    f"\n\n(Izin verilmedigi icin yapilamayan: {', '.join(map(str, reddedilen))}."
                    " Tam yetki acilirsa calisir.)"
                )
            s.durum = "basarili" if basarili else "basarisiz"
        s.log = s.log[-MAX_LOG:]
        return
    # codex
    if t == "thread.started":
        s.oturum = e.get("thread_id", "")
    elif t == "item.completed":
        it = e.get("item") or {}
        tur = it.get("type") or it.get("item_type")
        if tur in ("agent_message", "assistant_message"):
            s.ozet = str(it.get("text") or "").strip()
            s.log.append(s.ozet[:400])
        elif tur == "command_execution":
            s.log.append(f"🔧 komut: {str(it.get('command'))[:160]} -> {it.get('exit_code')}")
        elif tur == "file_change":
            s.log.append(f"🔧 dosya: {json.dumps(it.get('changes'), ensure_ascii=False)[:160]}")
    elif t == "turn.completed":
        s.durum = "basarili"
    elif t in ("error", "turn.failed"):
        mesaj = e.get("message") or (e.get("error") or {}).get("message") or "hata"
        s.ozet, s.durum = f"Codex hatasi: {mesaj}", "basarisiz"
    s.log = s.log[-MAX_LOG:]


async def calistir(
    saglayici: str, mesaj: str, klasor: Path, *, oturum: str = "", tam_yetki: bool = False,
    ek_sistem: str = "", model: str = "", canli: list[str] | None = None,
) -> CliSonuc:  # fmt: skip
    """CLI'yi calistirir; ilerleme `canli` listesine akar. Iptal edilirse surec agaci oldurulur."""
    s = CliSonuc(log=canli if canli is not None else [])
    komut = komut_kur(saglayici, mesaj, klasor, oturum=oturum, tam_yetki=tam_yetki,
                      ek_sistem=ek_sistem, model=model)  # fmt: skip
    klasor.mkdir(parents=True, exist_ok=True)
    surec = await asyncio.create_subprocess_exec(
        *komut, cwd=str(klasor), env=ortam_allowlist(), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, limit=8 * 1024 * 1024,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )  # fmt: skip
    hata_metni: list[str] = []

    async def stderr_oku() -> None:
        assert surec.stderr is not None
        async for b in surec.stderr:
            hata_metni.append(b.decode("utf-8", "replace"))
            del hata_metni[:-40]

    eh = asyncio.create_task(stderr_oku())
    try:
        assert surec.stdout is not None
        async with asyncio.timeout(ZAMAN_ASIMI):
            async for b in surec.stdout:
                try:
                    olay_isle(saglayici, json.loads(b), s)
                except ValueError:
                    continue
            await surec.wait()
    except (asyncio.CancelledError, TimeoutError):
        _oldur(surec.pid)
        s.durum, s.ozet = "iptal", s.ozet or "Iptal edildi ya da zaman asimi."
        raise
    finally:
        eh.cancel()
    if surec.returncode and s.durum != "basarisiz" and not s.ozet:
        s.durum = "basarisiz"
    if s.durum == "basarisiz" and not s.ozet:
        s.ozet = ("CLI hata verdi: " + "".join(hata_metni)[-600:]).strip()
    return s


def _oldur(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)  # fmt: skip
    else:
        with contextlib.suppress(OSError):
            os.kill(pid, 9)
