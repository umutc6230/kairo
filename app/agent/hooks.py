# ruff: noqa: E501 - Claude uyumluluk sozlukleri
"""Hook'lar (A6.4-5): olaylarda kullanicinin tanimladigi komut calisir.

Sozlesme (surum 1): komut stdin'den JSON alir {"surum", "olay", "veri"} (sirlar maskelenmis).
- cikis 0: devam; cikis 2: ENGELLE (stderr = neden); diger kod / timeout / baslatilamama = hata.
- tur "guvenlik": hata ya da timeout da ENGELLER (fail-closed).
- tur "bilgi": hata loglanir, gorev durmaz (fail-open); engelleyemez.
Hook'lar yalniz oturumlu API/arayuzden eklenir; model, skill ya da proje dosyasi hook ekleyemez.
Hook calisirken yeni hook tetiklenmez (recursion siniri 1). Ortam allowlist ile verilir.
"""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

from app.agent.dosyalar import ortam_allowlist
from app.agent.policy import maskele
from app.agent.terminal import windows_bash
from app.exceptions import Bulunamadi
from app.services import cc_plugin as cc
from app.services.depo import json_oku, json_yaz

SOZLESME_SURUMU = 1
OLAYLAR = (
    "run_baslangic", "run_bitis", "prompt", "pre_tool", "post_tool", "izin", "compact",
    "alt_ajan_bitis", "bildirim",
)  # fmt: skip
MAX_CIKTI = 4000

Olay = Literal[
    "run_baslangic", "run_bitis", "prompt", "pre_tool", "post_tool", "izin", "compact",
    "alt_ajan_bitis", "bildirim",
]  # fmt: skip


class Hook(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ad: str = Field(min_length=1, max_length=80)
    olay: Olay
    tur: Literal["guvenlik", "bilgi"] = "bilgi"
    komut: str = Field(min_length=1, max_length=2000)
    arac: str = Field(default="", max_length=80)  # pre/post_tool icin filtre; bos = hepsi
    timeout: int = Field(default=10, ge=1, le=120)
    aktif: bool = True
    # Claude Code plugin hook'lari: matcher regex'i, Claude stdin bicimi, CLAUDE_PLUGIN_ROOT
    eslesen: str = Field(default="", max_length=200)
    bicim: Literal["yerel", "claude"] = "yerel"
    kaynak: str = ""
    ortam: dict[str, str] = {}


class HookSonucu(BaseModel):
    izin: bool = True
    neden: str = ""
    calisan: list[dict] = []
    baglam: list[str] = []  # Claude SessionStart hook'larinin additionalContext'i (orn. DURUM.md)


_yerel = threading.local()


def _oldur(p: subprocess.Popen) -> None:
    """Hook surecini (shell=True: cocuklariyla) sonlandirir."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)  # fmt: skip
    else:
        p.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        p.wait(timeout=5)


def _async_mi(p: subprocess.Popen, zaman: float) -> tuple[bool | None, bytes]:
    """Claude Code async hook sozlesmesi: ilk stdout satiri {"async": true} ise hook arka
    planda surer (security-guidance ilk kurulumda ~2 dk paket kurar; beklemek sohbeti dondurur).
    Okunan ilk satir da doner: tek satirlik JSON cikti (additionalContext) kaybolmasin."""
    kutu: list[bytes] = []
    okuyucu = threading.Thread(target=lambda: kutu.append(p.stdout.readline()), daemon=True)
    okuyucu.start()
    okuyucu.join(zaman)
    if okuyucu.is_alive():  # ilk satir bile gelmedi: zaman asimi (cagiran communicate'te yakalar)
        _oldur(p)
        okuyucu.join(5)
        return None, b""
    satir = kutu[0] if kutu else b""
    try:
        ilk = json.loads(satir.decode("utf-8", "replace").strip() or "{}")
    except ValueError:
        return False, satir
    return isinstance(ilk, dict) and ilk.get("async") is True, satir


def _bitir(p: subprocess.Popen, zaman: float, ad: str) -> None:
    try:
        _, hata = p.communicate(timeout=max(zaman, 180))
        if p.returncode not in (0, None):
            logger.warning("Async hook ({}) cikis {}: {}", ad, p.returncode,
                           hata.decode("utf-8", "replace")[:300])  # fmt: skip
    except subprocess.TimeoutExpired:
        _oldur(p)
        logger.warning("Async hook ({}) zaman asimi; durduruldu.", ad)


def _eslesir(desen: str, arac: str) -> bool:
    """Claude matcher'i (or. 'Edit|Write', 'Bash') hem Claude hem bu uygulamanin arac adina uyar."""
    if desen in ("*", ""):
        return True
    adlar = {arac, cc.TERS_ESLESME.get(arac, "")}
    try:
        return any(a and re.fullmatch(desen, a) for a in adlar)
    except re.error:
        return desen in adlar


def _ek_baglam(cikti: bytes) -> str:
    """Claude Code hook stdout'u: {"hookSpecificOutput": {"additionalContext": ...}}; degilse bos."""
    try:
        ham = json.loads(cikti.decode("utf-8", "replace") or "{}")
        return str((ham.get("hookSpecificOutput") or {}).get("additionalContext") or "")
    except (ValueError, AttributeError):
        return ""


def _maskeli(x: object) -> object:
    if isinstance(x, str):
        return maskele(x)
    if isinstance(x, dict):
        return {k: _maskeli(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_maskeli(v) for v in x]
    return x


class HookDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "hooks.json"
        self.ek_kaynak = lambda: []  # plugin hook tanimlari (api baglar)

    def liste(self) -> list[Hook]:
        sonuc = []
        for h in json_oku(self.yol, []) or []:
            try:
                sonuc.append(Hook(**h))
            except ValueError:
                continue
        return sonuc

    def tum(self) -> list[Hook]:
        """Kullanicinin hook'lari + etkinlestirilmis plugin hook'lari (plugin'ler diske YAZILMAZ)."""
        ek = []
        for h in self.ek_kaynak():
            try:
                ek.append(Hook(**h))
            except ValueError:
                continue
        return [*self.liste(), *ek]

    def _yaz(self, hooks: list[Hook]) -> None:
        json_yaz(self.yol, [h.model_dump() for h in hooks])

    def ekle(self, veri: dict) -> Hook:
        h = Hook(**veri)
        self._yaz([*self.liste(), h])
        return h

    def guncelle(self, hook_id: str, veri: dict) -> Hook:
        hooks = self.liste()
        for i, h in enumerate(hooks):
            if h.id == hook_id:
                hooks[i] = Hook(**(h.model_dump() | veri | {"id": hook_id}))
                self._yaz(hooks)
                return hooks[i]
        raise Bulunamadi("Hook bulunamadi.")

    def sil(self, hook_id: str) -> None:
        hooks = self.liste()
        kalan = [h for h in hooks if h.id != hook_id]
        if len(kalan) == len(hooks):
            raise Bulunamadi("Hook bulunamadi.")
        self._yaz(kalan)

    @staticmethod
    def _calistir(h: Hook, olay: str, veri: dict, cwd: Path | None) -> tuple[str, str]:
        """('izin'|'engel'|'hata', mesaj)."""
        # maske DEGERLERE uygulanir: serilestirilmis metne uygulamak JSON tirnaklarini bozuyordu
        if h.bicim == "claude":  # Claude Code hook stdin bicimi
            claude_olay = {v: k for k, v in cc.OLAY_ESLESME.items()}.get(olay, olay)
            arac = str(veri.get("arac", ""))
            govde = {"hook_event_name": claude_olay, "session_id": str(veri.get("run", "")),
                     "cwd": str(cwd or ""), "tool_name": cc.TERS_ESLESME.get(arac, arac),
                     "tool_input": _maskeli(veri.get("argumanlar", {})), "prompt": veri.get("metin", ""),
                     "message": veri.get("metin", ""),
                     "last_assistant_message": veri.get("cevap", ""), "model": veri.get("model", "")}  # fmt: skip
        else:
            govde = {"surum": SOZLESME_SURUMU, "olay": olay, "veri": _maskeli(veri)}
        girdi = json.dumps(govde, ensure_ascii=False, default=str)
        try:
            # Claude Code plugin hook'lari bash sozdizimiyle yazilir; Claude Code Windows'ta da
            # Git Bash ile calistirir (cmd'de "'SCRIPT' is not recognized" hatasi veriyordu)
            gb = windows_bash() if h.bicim == "claude" else None
            p = subprocess.Popen(  # noqa: S602 - kullanicinin kendi tanimladigi hook komutu
                [gb, "-c", h.komut] if gb else h.komut,
                shell=not gb,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd) if cwd and cwd.is_dir() else None,
                env={**ortam_allowlist(), **h.ortam, "CLAUDE_PROJECT_DIR": str(cwd or "")},
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except OSError as e:
            return "hata", f"baslatilamadi: {e}"
        if h.bicim != "claude":
            try:
                cikti, hata_b = p.communicate(input=girdi.encode("utf-8"), timeout=h.timeout)
            except subprocess.TimeoutExpired:
                _oldur(p)
                return "hata", f"{h.timeout} sn zaman asimi"
        else:

            def _yaz_stdin() -> None:
                try:
                    assert p.stdin is not None
                    p.stdin.write(girdi.encode("utf-8"))
                    p.stdin.close()
                except OSError:
                    pass

            threading.Thread(target=_yaz_stdin, daemon=True).start()
            asenkron, ilk_satir = _async_mi(p, h.timeout)
            if asenkron is None:
                return "hata", f"{h.timeout} sn zaman asimi"
            if asenkron:
                # Claude Code async hook'u ({"async": true} ilk satir): arka planda bitsin
                threading.Thread(target=_bitir, args=(p, h.timeout, h.ad), daemon=True).start()
                return "izin", ""
            try:
                cikti, hata_b = p.communicate(timeout=h.timeout)
                cikti = ilk_satir + cikti
            except subprocess.TimeoutExpired:
                _oldur(p)
                return "hata", f"{h.timeout} sn zaman asimi"
        hata = maskele(hata_b.decode("utf-8", "replace").strip())[:MAX_CIKTI]
        if p.returncode == 0:
            return "izin", _ek_baglam(cikti) if h.bicim == "claude" else ""
        if p.returncode == 2:
            return "engel", hata or "Hook islemi engelledi."
        return "hata", f"cikis {p.returncode}: {hata}"

    def tetikle(
        self, olay: str, veri: dict, *, arac: str = "", cwd: Path | None = None
    ) -> HookSonucu:
        if getattr(_yerel, "icinde", False):  # hook icinden yeni hook yok
            return HookSonucu()
        sonuc = HookSonucu()
        _yerel.icinde = True
        try:
            for h in self.tum():
                if not h.aktif or h.olay != olay or (h.arac and h.arac != arac):
                    continue
                if h.eslesen and not _eslesir(h.eslesen, arac):
                    continue
                durum, mesaj = self._calistir(h, olay, veri, cwd)
                if durum == "izin" and mesaj:
                    sonuc.baglam.append(mesaj)
                    mesaj = ""
                sonuc.calisan.append({"hook": h.ad, "tur": h.tur, "durum": durum, "mesaj": mesaj})
                if durum == "hata":
                    logger.warning("Hook hatasi ({}): {}", h.ad, mesaj)
                # guvenlik hook'u hata/timeout'ta da engeller; Claude hook'u (Claude gibi) yalniz cikis 2
                # Claude Code plugin hook'u: Claude Code gibi YALNIZ cikis 2 engeller; bozuk
                # kurulum (cikis 127 vb.) sohbeti kilitlemez, uyari olarak kalir
                if h.bicim == "claude":
                    engeller = durum == "engel"
                else:
                    engeller = h.tur == "guvenlik" and durum in ("engel", "hata")
                if engeller and sonuc.izin:
                    sonuc.izin = False
                    sonuc.neden = f"Guvenlik hook'u '{h.ad}' engelledi: {mesaj}"
        finally:
            _yerel.icinde = False
        return sonuc

    def test_et(self, hook_id: str) -> dict:
        h = next((x for x in self.liste() if x.id == hook_id), None)
        if h is None:
            raise Bulunamadi("Hook bulunamadi.")
        durum, mesaj = self._calistir(h, h.olay, {"test": True, "arac": h.arac or "ornek"}, None)
        return {"durum": durum, "mesaj": mesaj}
