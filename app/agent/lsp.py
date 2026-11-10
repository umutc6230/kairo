"""LSP adaptoru (A10.1): tanim, referans, sembol, tani. Herhangi bir dil sunucusu (stdio).

- Sunucu yalniz kullanicinin Ayarlar'da tanimladigi komuttur (uzanti -> komut). Proje dosyasi sunucu
  tanimlayamaz. Ortam allowlist ile verilir.
- Sonuclar yalniz yetkili proje koklerindeki dosyalara filtrelenir; satir/sutun 1 tabanli.
- Sunucu yoksa, cokerse ya da zaman asimina duserse KONTROLLU YEDEK: metin aramasi (rg/python),
  sonucta "yedek": true ve neden yazilir (anlamsal sonuc gibi sunulmaz).
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from app.agent.dosyalar import ortam_allowlist
from app.exceptions import UygulamaHatasi

ZAMAN = 15.0
MAX_SONUC = 200


def _uri(p: Path) -> str:
    return p.resolve().as_uri()


def _yol(uri: str) -> Path:
    return Path(url2pathname(unquote(urlsplit(uri).path)))


def komut_parcala(komut: str) -> list[str]:
    """Windows'ta posix=False tirnaklari tokende birakir: "C:\\Program Files\\x.exe" calismazdi."""
    parcalar = shlex.split(komut, posix=sys.platform != "win32")
    return [x[1:-1] if len(x) > 1 and x[0] == x[-1] == '"' else x for x in parcalar]


class LspIstemci:
    def __init__(self, komut: str, kok: Path) -> None:
        self.komut, self.kok = komut, kok
        self.surec: subprocess.Popen[bytes] | None = None
        self.sayac = 0
        self.kilit = threading.Lock()
        self.cevaplar: dict[int, Any] = {}
        self.tanilar: dict[str, list] = {}
        self.acik: set[str] = set()
        self._olay = threading.Condition()

    # ---- tasima: Content-Length cerceveli JSON-RPC ----
    def _gonder(self, m: dict) -> None:
        assert self.surec and self.surec.stdin
        govde = json.dumps(m).encode("utf-8")
        try:
            self.surec.stdin.write(b"Content-Length: %d\r\n\r\n" % len(govde) + govde)
            self.surec.stdin.flush()
        except OSError as e:
            self.kapat()
            raise UygulamaHatasi("Dil sunucusu baglantisi koptu.") from e

    def _okuyucu(self) -> None:
        akis = self.surec.stdout if self.surec else None
        while akis:
            uzunluk = 0
            while True:
                satir = akis.readline()
                if not satir:
                    with self._olay:
                        self._olay.notify_all()
                    return
                if satir in (b"\r\n", b"\n"):
                    break
                if satir.lower().startswith(b"content-length:"):
                    uzunluk = int(satir.split(b":")[1])
            try:
                m = json.loads(akis.read(uzunluk))
            except (ValueError, OSError):
                continue
            if "method" in m and "id" in m:  # sunucu istegi (or. workspace/configuration)
                self._gonder({"jsonrpc": "2.0", "id": m["id"], "result": None})
            elif m.get("method") == "textDocument/publishDiagnostics":
                p = m.get("params") or {}
                self.tanilar[p.get("uri", "")] = p.get("diagnostics") or []
                with self._olay:
                    self._olay.notify_all()
            elif "id" in m:
                with self._olay:
                    self.cevaplar[m["id"]] = m
                    self._olay.notify_all()

    def _istek(self, metod: str, params: dict) -> Any:
        self.sayac += 1
        no = self.sayac
        self._gonder({"jsonrpc": "2.0", "id": no, "method": metod, "params": params})
        bitis = time.monotonic() + ZAMAN
        with self._olay:
            while no not in self.cevaplar:
                kalan = bitis - time.monotonic()
                if kalan <= 0 or (self.surec and self.surec.poll() is not None):
                    raise UygulamaHatasi(f"Dil sunucusu cevap vermedi ({metod}).")
                self._olay.wait(kalan)
            m = self.cevaplar.pop(no)
        if "error" in m:
            raise UygulamaHatasi(f"Dil sunucusu hatasi: {str(m['error'].get('message'))[:200]}")
        return m.get("result")

    def _bildir(self, metod: str, params: dict) -> None:
        self._gonder({"jsonrpc": "2.0", "method": metod, "params": params})

    def hazirla(self) -> None:
        if self.surec and self.surec.poll() is None:
            return
        try:
            self.surec = subprocess.Popen(  # noqa: S603 - kullanicinin tanimladigi dil sunucusu
                komut_parcala(self.komut), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=str(self.kok),
                env=ortam_allowlist(),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )  # fmt: skip
        except OSError as e:
            raise UygulamaHatasi(f"Dil sunucusu baslatilamadi: {e}") from e
        self.acik.clear()
        threading.Thread(target=self._okuyucu, daemon=True).start()
        self._istek("initialize", {"processId": None, "rootUri": _uri(self.kok),
                                   "capabilities": {}, "workspaceFolders": None})  # fmt: skip
        self._bildir("initialized", {})

    def _ac(self, p: Path) -> str:
        uri = _uri(p)
        if uri not in self.acik:
            dil = {".py": "python", ".ts": "typescript", ".js": "javascript"}.get(p.suffix, "")
            self._bildir("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": dil, "version": 1,
                "text": p.read_text(encoding="utf-8", errors="replace")}})  # fmt: skip
            self.acik.add(uri)
        return uri

    def cagir(self, metod: str, p: Path, satir: int = 0, sutun: int = 0, **ek: Any) -> Any:
        with self.kilit:
            self.hazirla()
            uri = self._ac(p)
            params: dict[str, Any] = {"textDocument": {"uri": uri}, **ek}
            if metod != "textDocument/documentSymbol":
                params["position"] = {"line": satir - 1, "character": sutun - 1}
            return self._istek(metod, params)

    def tani(self, p: Path, bekle: float = 3.0) -> list:
        with self.kilit:
            self.hazirla()
            uri = self._ac(p)
        bitis = time.monotonic() + bekle
        with self._olay:
            while uri not in self.tanilar and time.monotonic() < bitis:
                self._olay.wait(bitis - time.monotonic())
        return self.tanilar.get(uri, [])

    def kapat(self) -> None:
        if self.surec and self.surec.poll() is None:
            self.surec.kill()
        self.surec = None


class KodZekasi:
    """Uzantiya gore sunucu secer; yoksa/cokerse metin aramasina duser."""

    def __init__(self, sunucular: Any, kapsam: Any, arama: Any) -> None:
        self.sunucular = sunucular  # () -> {".py": "komut"}
        self.kapsam = kapsam
        self.arama = arama  # (desen, dosya_deseni) -> proje_ara sonucu
        self._istemciler: dict[tuple[str, str], LspIstemci] = {}

    def _istemci(self, p: Path) -> LspIstemci | None:
        komut = (self.sunucular() or {}).get(p.suffix.lower())
        if not komut:
            return None
        kok = self.kapsam.kok_of(p)
        anahtar = (komut, str(kok))
        if anahtar not in self._istemciler:
            self._istemciler[anahtar] = LspIstemci(komut, kok)
        return self._istemciler[anahtar]

    def kapat(self) -> None:
        for i in self._istemciler.values():
            i.kapat()

    def _konumlar(self, sonuc: Any) -> list[dict]:
        if sonuc is None:
            return []
        liste = sonuc if isinstance(sonuc, list) else [sonuc]
        cikti = []
        for x in liste:
            uri = x.get("uri") or x.get("targetUri")
            ar = x.get("range") or x.get("targetSelectionRange") or {}
            if not uri:
                continue
            p = _yol(uri)
            try:
                self.kapsam.coz(str(p))  # proje disi sonuc gosterilmez
            except Exception:  # noqa: BLE001 - kapsam disi / hassas
                continue
            bas = ar.get("start", {})
            cikti.append({"dosya": self.kapsam.goreli(p), "satir": bas.get("line", 0) + 1,
                          "sutun": bas.get("character", 0) + 1})  # fmt: skip
        return cikti[:MAX_SONUC]

    def _kelime(self, p: Path, satir: int, sutun: int) -> str:
        satirlar = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if not 1 <= satir <= len(satirlar):
            return ""
        m = next((m for m in re.finditer(r"\w+", satirlar[satir - 1])
                  if m.start() <= sutun - 1 <= m.end()), None)  # fmt: skip
        return m.group(0) if m else ""

    def _yedek(self, neden: str, desen: str, p: Path) -> dict:
        r = self.arama(desen, f"*{p.suffix}") if desen else {"eslesmeler": []}
        return {"yedek": True, "neden": neden, "not": "Anlamsal degil, metin aramasi sonucu.",
                "sonuclar": r.get("eslesmeler") or r.get("sonuclar") or r}  # fmt: skip

    def _calistir(self, tur: str, yol: str, satir: int = 1, sutun: int = 1) -> dict:
        p = self.kapsam.coz(yol)
        if not p.is_file():
            raise UygulamaHatasi(f"Dosya yok: {yol}")
        istemci = self._istemci(p)
        kelime = self._kelime(p, satir, sutun) if tur in ("tanim", "referans") else ""
        desen = {"tanim": rf"(def|class|function|const|let|var)\s+{re.escape(kelime)}\b",
                 "referans": rf"\b{re.escape(kelime)}\b", "sembol": r"^\s*(def|class) \w+",
                 "tani": ""}[tur]  # fmt: skip
        if istemci is None:
            return self._yedek(f"'{p.suffix}' icin dil sunucusu tanimli degil", desen, p)
        try:
            if tur == "tanim":
                return {
                    "sonuclar": self._konumlar(
                        istemci.cagir("textDocument/definition", p, satir, sutun)
                    )
                }
            if tur == "referans":
                return {
                    "sonuclar": self._konumlar(
                        istemci.cagir(
                            "textDocument/references",
                            p,
                            satir,
                            sutun,
                            context={"includeDeclaration": True},
                        )
                    )
                }
            if tur == "sembol":
                s = istemci.cagir("textDocument/documentSymbol", p) or []
                return {
                    "sonuclar": [
                        {
                            "ad": x.get("name"),
                            "tur": x.get("kind"),
                            "satir": (
                                (x.get("range") or x.get("location", {}).get("range") or {})
                                .get("start", {})
                                .get("line", 0)
                            )
                            + 1,
                        }
                        for x in s
                    ][:MAX_SONUC]
                }
            t = istemci.tani(p)
            return {"sonuclar": [{"satir": d["range"]["start"]["line"] + 1,
                                  "mesaj": d.get("message", "")[:300],
                                  "onem": d.get("severity")} for d in t][:MAX_SONUC]}  # fmt: skip
        except UygulamaHatasi as e:
            istemci.kapat()  # cokmus/takilmis sunucu sonraki cagrida yeniden baslar
            return self._yedek(f"dil sunucusu kullanilamadi: {e.mesaj}", desen, p)

    def isleyiciler(self) -> dict:
        from app.agent.yazma import sonuc_veya_hata

        return {
            "kod_tanim": lambda yol, satir, sutun: sonuc_veya_hata(
                self._calistir, "tanim", yol, satir, sutun),
            "kod_referanslar": lambda yol, satir, sutun: sonuc_veya_hata(
                self._calistir, "referans", yol, satir, sutun),
            "kod_semboller": lambda yol: sonuc_veya_hata(self._calistir, "sembol", yol),
            "kod_tanilar": lambda yol: sonuc_veya_hata(self._calistir, "tani", yol),
        }  # fmt: skip


def _f(ad: str, aciklama: str, oz: dict, zorunlu: list[str]) -> dict:
    p = {"type": "object", "properties": oz, "required": zorunlu}
    return {"type": "function", "function": {"name": ad, "description": aciklama, "parameters": p}}


_S, _I = {"type": "string"}, {"type": "integer"}
_KONUM = {"yol": _S, "satir": _I, "sutun": _I}
SEMALAR = [
    _f("kod_tanim", "Bir sembolun tanimini bulur (satir/sutun 1 tabanli).", _KONUM, list(_KONUM)),
    _f("kod_referanslar", "Bir sembolun tum kullanimlarini bulur.", _KONUM, list(_KONUM)),
    _f("kod_semboller", "Dosyadaki fonksiyon/sinif listesi.", {"yol": _S}, ["yol"]),
    _f("kod_tanilar", "Dil sunucusunun hata/uyari listesi.", {"yol": _S}, ["yol"]),
]
