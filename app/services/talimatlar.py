"""Kalici talimatlar (Claude Code'daki CLAUDE.md mantigi).

Kaynaklar (sirayla, hepsi her sohbetin sistem mesajina eklenir):
1. Claude Code genel talimati: ~/.claude/CLAUDE.md ve icindeki `@yol` importlari (orn. brain
   BRAIN-POLICY.md). Claude Code'daki gibi: satir basindaki `@~/...` ya da `@yol` dosyayi icine
   alir; kod blogu icindekiler alinmaz; en fazla 4 seviye, dongu korumali.
2. Uygulama talimati: <veri>/AGENTS.md (uygulama icinden duzenlenir).
"""

from __future__ import annotations

import re
from pathlib import Path

IMPORT = re.compile(r"^\s*@(\S+)\s*$")
MAX_DERINLIK = 4
MAX_KAYNAK_KARAKTER = 16000


def claude_md_yolu() -> Path:
    return Path.home() / ".claude" / "CLAUDE.md"


def _yol(ham: str, taban: Path) -> Path:
    p = Path(ham.replace("~", str(Path.home()), 1) if ham.startswith("~") else ham)
    return p if p.is_absolute() else (taban / p)


def importlari_coz(yol: Path, ziyaret: set[Path] | None = None, derinlik: int = 0) -> list[dict]:
    """Dosyayi ve importladigi dosyalari sirayla dondurur: [{yol, metin}]. Import satirlari
    metinden cikarilir (yerine dosyanin kendisi ayri kaynak olarak gelir)."""
    ziyaret = ziyaret if ziyaret is not None else set()
    try:
        gercek = yol.resolve()
    except OSError:
        return []
    if gercek in ziyaret or derinlik > MAX_DERINLIK or not yol.is_file():
        return []
    ziyaret.add(gercek)
    satirlar, alinanlar = [], []
    kod_blogu = False
    for satir in yol.read_text(encoding="utf-8", errors="replace").splitlines():
        if satir.strip().startswith("```"):
            kod_blogu = not kod_blogu
        m = None if kod_blogu else IMPORT.match(satir)
        if m:
            alinanlar += importlari_coz(_yol(m.group(1), yol.parent), ziyaret, derinlik + 1)
        else:
            satirlar.append(satir)
    metin = "\n".join(satirlar).strip()
    return ([{"yol": str(yol), "metin": metin}] if metin else []) + alinanlar


def tahmini_token(metin: str) -> int:
    return int(len(metin) / 3.3) + 4


class TalimatDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.uygulama_yolu = veri_dizini / "AGENTS.md"

    def uygulama_oku(self) -> str:
        try:
            return self.uygulama_yolu.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def uygulama_yaz(self, metin: str) -> str:
        self.uygulama_yolu.write_text(
            metin.strip() + ("\n" if metin.strip() else ""), encoding="utf-8"
        )
        return self.uygulama_oku()

    def kaynaklar(self, *, claude: bool = True, uygulama: bool = True) -> list[dict]:
        """Etkin talimat kaynaklari: [{tur, yol, metin, token, kisaltildi}]."""
        sonuc: list[dict] = []
        if claude:
            for k in importlari_coz(claude_md_yolu()):
                sonuc.append({"tur": "claude", **k})
        if uygulama and (metin := self.uygulama_oku().strip()):
            sonuc.append({"tur": "uygulama", "yol": str(self.uygulama_yolu), "metin": metin})
        for k in sonuc:
            k["kisaltildi"] = len(k["metin"]) > MAX_KAYNAK_KARAKTER
            k["metin"] = k["metin"][:MAX_KAYNAK_KARAKTER]
            k["token"] = tahmini_token(k["metin"])
        return sonuc

    def sistem_metni(self, *, claude: bool = True, uygulama: bool = True) -> str:
        parcalar = [
            f'<talimat kaynak="{Path(k["yol"]).name}">\n{k["metin"]}\n</talimat>'
            for k in self.kaynaklar(claude=claude, uygulama=uygulama)
        ]
        if not parcalar:
            return ""
        return "Asagidaki kalici talimatlara uy (kullanicinin genel kurallari):\n\n" + "\n\n".join(
            parcalar
        )
