"""Arac paketleri: uygulamaya tek tikla eklenen hazir arac setleri (REA, Craft Anything).

Bir paket = SURUMU ve OZETI SABIT bir dis kaynak + onu modele acan MCP kaydi (+ varsa skill).
Paket uygulamanin veri klasorune (<veri>/araclar/<ad>) kurulur; sistem genelinde bir sey
kurulmaz, kullanicinin Claude/Codex ayarlarina DOKUNULMAZ (paketlerin kendi `setup` komutu
hic calistirilmaz).

Guvenlik:
- Yalniz bu dosyadaki tablo kurulur; model, proje dosyasi ya da istek govdesi adres/surum veremez.
- npm: `--ignore-scripts` (kurulum betigi calismaz); kurulan paketin butunluk ozeti tablodakiyle
  karsilastirilir, uyusmazsa kurulum geri alinir.
- zip: indirilen dosyanin SHA256'si tablodakiyle uyusmazsa ACILMAZ; arsiv uyeleri hedef klasor
  disina cikamaz (zip slip), sembolik link uyeleri atlanir.
- Kurulum YALNIZ kullanicinin arayuzdeki tiklamasiyla baslar. MCP kaydi gecitle (tembel) yapilir;
  her arac cagrisi yine izin motorundan gecer.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

KURULUM_ZAMAN_ASIMI = 900
ISARET = ".kairo-arac-paketi"  # yalniz bizim kopyaladigimiz skill klasoru silinir

SKILL_NOTU = """

## Kairo'da kullanim

Bu sunucu cok buyuk oldugu icin araclari tek tek degil GECITLE sunulur. Yukaridaki metinde adi
gecen bir araci (or. `{ornek}`) dogrudan cagirma; su uc araci kullan:

1. `mcp__{ad}__arac_ara` (sorgu: Ingilizce anahtar kelime) -> uygun arac adlari
2. `mcp__{ad}__arac_sema` (arac) -> o aracin parametreleri
3. `mcp__{ad}__arac_cagir` (arac, argumanlar) -> calistirir

Yukaridaki `npx ... setup` / `doctor` adimlarini CALISTIRMA: sunucu Kairo tarafindan kuruldu ve
kayitli. Araclar gorunmuyorsa kullaniciya Ayarlar > Baglayicilar > Arac paketleri'ni soyle.
"""

PAKETLER: dict[str, dict[str, Any]] = {
    "rea": {
        "baslik": "REA - Reverse Engineer Anything",
        "aciklama": (
            "Derlenmiş uygulamaları inceler: Electron/JavaScript, .NET, Android APK, yerel ikili "
            "(Ghidra/IDA/Hopper varsa), firmware, tarayıcı ve ağ kayıtları. 139 araç + skill."
        ),
        "kaynak": "https://github.com/morluto/rea",
        "lisans": "MIT",
        "tur": "npm",
        "paket": "rea-agents",
        "surum": "6.3.0",
        "butunluk": (
            "sha512-1l3L22PYqlzW70I2Z8fVjWufdBp8lN5dwXSiBERLKPP7pybiFSHeCD8LnXfAoilYkmSQe1Nf"
            "RgOrbIr9ujkOfQ=="
        ),
        "node": (22, 19),
        "boyut_mb": 101,
        "komut": "{node}",
        "argumanlar": ["{kok}/node_modules/rea-agents/scripts/rea.mjs", "mcp"],
        "skill": "node_modules/rea-agents/skills/reverse-engineer-anything",
        "skill_ornek": "open_binary",
        "uyari": (
            "Yerel ikili analiz için Ghidra/IDA/Hopper, Android için JADX + Java ayrıca kurulu "
            "olmalıdır; REA bunları kurmaz. JavaScript/Electron ve paket incelemesi ek araç "
            "istemez."
        ),
    },
    "craft-anything": {
        "baslik": "Craft Anything",
        "aciklama": (
            "Bir site, uygulama, oyun ya da dosyanın nasıl çalıştığını inceleyip yeniden kurmaya "
            "yardım eden araç seti (320 araç, MCP sunucusu). Erken alfa."
        ),
        "kaynak": "https://github.com/storytold/craft-anything",
        "lisans": "MIT OR Apache-2.0",
        "tur": "zip",
        "surum": "0.6.1",
        "url": (
            "https://github.com/storytold/craft-anything/releases/download/v0.6.1/"
            "craft-anything-0.6.1-windows-x64-portable.zip"
        ),
        "sha256": "bd370fbaa2b44dbc13581db5ffd2bf66924ed40e433c7902212aa17ca781de54",
        "platform": "win32",
        "boyut_mb": 70,
        "calistirilabilir": "craft-anything-cli.exe",
        "komut": "{exe}",
        # --all-tools: sunucu varsayilan olarak yalniz ~30 temel araci listeler; gecit buyuk listeyi
        # tasir. --deep: hedefin kodunu/dosyalarini okuyan araclar (108 -> 323 arac); onsuz "clean
        # room" kipinde kalir. --allow-run BILEREK YOK (kod calistiran araclar onaysiz acilmaz).
        "argumanlar": ["mcp", "--all-tools", "--deep"],
        "uyari": (
            "Hazır derlenmiş program indirilir; kaynak koduyla aynı olduğu DOĞRULANAMAZ (yalnız "
            "yayın özeti karşılaştırılır). Depo çok yeni (2026-10-31). Program kendini "
            "güncelleyebilir, çalışırken ek araç indirebilir ve kodlama ajanları başlatabilir."
        ),
    },
}


def _calistir(komut: list[str], cwd: Path) -> tuple[int, str]:
    r = subprocess.run(  # noqa: S603 - sabit tablo komutu, kabuk yok
        komut, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=KURULUM_ZAMAN_ASIMI, check=False,
    )  # fmt: skip
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _indir(url: str, hedef: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with hedef.open("wb") as f:
            for parca in r.iter_bytes(1 << 20):
                f.write(parca)


def _sha256(yol: Path) -> str:
    h = hashlib.sha256()
    with yol.open("rb") as f:
        while blok := f.read(4 << 20):
            h.update(blok)
    return h.hexdigest()


def guvenli_ac(arsiv: Path, hedef: Path) -> int:
    """Zip'i hedefe acar; hedef disina cikan ya da sembolik link olan uye varsa HIC acmaz."""
    kok = hedef.resolve()
    with zipfile.ZipFile(arsiv) as z:
        uyeler = z.infolist()
        for u in uyeler:
            if (u.external_attr >> 16) & 0o170000 == 0o120000:
                raise UygulamaHatasi(f"Arsivde sembolik link var, acilmadi: {u.filename[:120]}")
            if not (kok / u.filename).resolve().is_relative_to(kok):
                raise UygulamaHatasi(f"Arsiv klasor disina yaziyor, acilmadi: {u.filename[:120]}")
        z.extractall(kok)  # noqa: S202 - uyeler yukarida dogrulandi
    return len(uyeler)


class AracPaketleri:
    def __init__(
        self,
        veri_dizini: Path,
        mcp: Any,
        calistir: Callable[[list[str], Path], tuple[int, str]] = _calistir,
        indir: Callable[[str, Path], None] = _indir,
        bul: Callable[[str], str | None] = shutil.which,
        platform: str = sys.platform,
    ) -> None:
        self.kok = veri_dizini / "araclar"
        self.skill_kok = veri_dizini / "skills"
        self.mcp = mcp
        self.calistir, self.indir, self.bul, self.platform = calistir, indir, bul, platform
        self.mesgul: set[str] = set()

    # ---- durum ----
    def _tanim(self, ad: str) -> dict:
        if ad not in PAKETLER:
            raise Bulunamadi("Boyle bir arac paketi yok.")
        return PAKETLER[ad]

    def _kayit(self, ad: str) -> dict:
        return json_oku(self.kok / ad / "kurulum.json", {}) or {}

    def _node(self) -> tuple[str | None, tuple[int, ...]]:
        node = self.bul("node")
        if not node:
            return None, ()
        try:
            kod, cikti = self.calistir([node, "--version"], Path.cwd())
        except (OSError, subprocess.SubprocessError):
            return node, ()
        m = re.search(r"v(\d+)\.(\d+)\.(\d+)", cikti) if kod == 0 else None
        return node, tuple(int(x) for x in m.groups()) if m else ()

    def engel(self, ad: str) -> str:
        """Kurulumu engelleyen kosul (bos = kurulabilir). Hicbir sey indirmez."""
        t = self._tanim(ad)
        if t.get("platform") and t["platform"] != self.platform:
            return "Bu paketin hazir surumu yalniz Windows icin tanimli."
        if t["tur"] == "npm":
            node, surum = self._node()
            if not node or not self.bul("npm"):
                return "Node.js ve npm gerekli (nodejs.org); bulunamadi."
            if surum and surum[:2] < tuple(t["node"]):
                gerek = ".".join(str(x) for x in t["node"])
                return f"Node.js {gerek} ya da yenisi gerekli; kurulu: {'.'.join(map(str, surum))}."
        return ""

    def liste(self) -> list[dict]:
        kayitli = {s.ad for s in self.mcp.liste()}
        sonuc = []
        for ad, t in PAKETLER.items():
            k = self._kayit(ad)
            sonuc.append({
                "ad": ad, "baslik": t["baslik"], "aciklama": t["aciklama"], "kaynak": t["kaynak"],
                "lisans": t["lisans"], "tur": t["tur"], "surum": t["surum"],
                "boyut_mb": t["boyut_mb"], "uyari": t.get("uyari", ""),
                "kurulu": bool(k), "kurulu_surum": k.get("surum", ""),
                "baglayici": ad in kayitli, "skill": bool(k.get("skill")),
                "mesgul": ad in self.mesgul, "engel": "" if k else self.engel(ad),
            })  # fmt: skip
        return sonuc

    # ---- kurulum ----
    def kur(self, ad: str) -> dict:
        t = self._tanim(ad)
        if self._kayit(ad):
            raise UygulamaHatasi("Bu paket zaten kurulu.")
        if ad in self.mesgul:
            raise UygulamaHatasi("Bu paketin kurulumu suruyor.")
        if neden := self.engel(ad):
            raise UygulamaHatasi(neden)
        if any(s.ad == ad for s in self.mcp.liste()):
            raise UygulamaHatasi(f"'{ad}' adinda bir baglayici zaten var; once onu kaldirin.")
        hedef = self.kok / ad
        self.mesgul.add(ad)
        try:
            if hedef.exists():  # yarim kalmis onceki deneme
                shutil.rmtree(hedef)
            hedef.mkdir(parents=True)
            degisken = self._npm_kur(t, hedef) if t["tur"] == "npm" else self._zip_kur(t, hedef)
            degisken["kok"] = hedef.as_posix()
            skill = self._skill_kur(ad, t, hedef)
            self.mcp.ekle({
                "ad": ad, "komut": t["komut"].format(**degisken),
                "argumanlar": [a.format(**degisken) for a in t["argumanlar"]], "tembel": True,
            })  # fmt: skip
            json_yaz(hedef / "kurulum.json", {"ad": ad, "surum": t["surum"], "skill": skill})
        except BaseException:
            shutil.rmtree(hedef, ignore_errors=True)
            self._skill_sil(ad, t)
            raise
        finally:
            self.mesgul.discard(ad)
        logger.info("Arac paketi kuruldu: {} {}", ad, t["surum"])
        return next(p for p in self.liste() if p["ad"] == ad)

    def _npm_kur(self, t: dict, hedef: Path) -> dict:
        node, _ = self._node()
        npm = self.bul("npm")
        try:
            kod, cikti = self.calistir(
                [str(npm), "install", "--ignore-scripts", "--no-audit", "--no-fund",
                 "--prefix", str(hedef), f"{t['paket']}@{t['surum']}"],
                hedef,
            )  # fmt: skip
        except subprocess.TimeoutExpired as e:
            raise UygulamaHatasi("Kurulum zaman asimina ugradi (ag yavas olabilir).") from e
        except OSError as e:
            raise UygulamaHatasi(f"npm calistirilamadi: {e}") from e
        if kod != 0:
            raise UygulamaHatasi(f"npm kurulumu basarisiz: {cikti.strip()[-400:]}")
        kilit = json_oku(hedef / "package-lock.json", {}) or {}
        girdi = (kilit.get("packages") or {}).get(f"node_modules/{t['paket']}") or {}
        if girdi.get("version") != t["surum"] or girdi.get("integrity") != t["butunluk"]:
            raise UygulamaHatasi(
                "Kurulan paketin butunluk ozeti beklenenle uyusmuyor; kurulum geri alindi."
            )
        return {"node": str(node)}

    def _zip_kur(self, t: dict, hedef: Path) -> dict:
        arsiv = hedef / "indirilen.zip"
        try:
            self.indir(t["url"], arsiv)
        except (httpx.HTTPError, OSError) as e:
            raise UygulamaHatasi(f"Indirme basarisiz: {str(e)[:200]}") from e
        if _sha256(arsiv) != t["sha256"]:
            raise UygulamaHatasi("Indirilen dosyanin SHA256 ozeti uyusmuyor; acilmadi, silindi.")
        guvenli_ac(arsiv, hedef)
        arsiv.unlink()
        exe = next(iter(sorted(hedef.rglob(t["calistirilabilir"]))), None)
        if exe is None:
            raise UygulamaHatasi(f"Pakette {t['calistirilabilir']} bulunamadi.")
        return {"exe": exe.as_posix()}

    def _skill_kur(self, ad: str, t: dict, hedef: Path) -> str:
        if not t.get("skill"):
            return ""
        kaynak = hedef / t["skill"]
        if not (kaynak / "SKILL.md").is_file():
            raise UygulamaHatasi("Pakette beklenen skill bulunamadi.")
        yer = self.skill_kok / kaynak.name
        if yer.exists() and not (yer / ISARET).exists():
            return ""  # kullanicinin ayni adli kendi skill'i: ustune yazilmaz
        shutil.rmtree(yer, ignore_errors=True)
        shutil.copytree(kaynak, yer)
        md = yer / "SKILL.md"
        not_ = SKILL_NOTU.format(ad=ad, ornek=t.get("skill_ornek", "arac"))
        md.write_text(md.read_text(encoding="utf-8") + not_, encoding="utf-8", newline="\n")
        (yer / ISARET).write_text(json.dumps({"paket": ad}), encoding="utf-8")
        return kaynak.name

    def _skill_sil(self, ad: str, t: dict) -> None:
        if not t.get("skill"):
            return
        yer = self.skill_kok / Path(t["skill"]).name
        if (yer / ISARET).exists():
            shutil.rmtree(yer, ignore_errors=True)

    def kaldir(self, ad: str) -> dict:
        t = self._tanim(ad)
        if ad in self.mesgul:
            raise UygulamaHatasi("Bu paketin kurulumu suruyor.")
        if not self._kayit(ad):
            raise UygulamaHatasi("Bu paket kurulu degil.")
        if any(s.ad == ad for s in self.mcp.liste()):
            self.mcp.sil(ad)  # once sureci kapat: Windows'ta acik dosya silinemez
        self._skill_sil(ad, t)
        try:
            shutil.rmtree(self.kok / ad)
        except OSError as e:
            raise UygulamaHatasi(
                f"Paket klasoru silinemedi (dosya kullanimda olabilir): {e}"
            ) from e
        return {"kaldirildi": ad}
