"""Plugin'ler (A7.4-5, A7.7): manifest, karantina, inceleme, kurulum, surum/geri alma, kaldirma.

Plugin = klasor + plugin.json {name, version, description, skills?: "skills"}. Bu surumde plugin
yalniz SKILL tasir (MCP/hook eklemez: onlar kullanicinin acik onayiyla ayrica eklenir).
Akis: kaynak klasor -> KARANTINA kopyasi (hicbir sey calistirilmaz) -> inceleme raporu (dosya
listesi, sha256, riskli desenler) -> kullanici "kur" der -> plugins/<ad>/<surum>/ + aktif surum.
Kurulum scripti (install.*, postinstall, setup.py) ASLA calistirilmaz; raporda isaretlenir.
Hash ve imza tek basina guvenlik kaniti sayilmaz; rapor yalniz inceleme yardimcisidir.
Kurumsal politika: data/plugin-politika.json {"yasak": [ad], "izinli": [ad]} (izinli bossa serbest).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

AD = r"^[a-z0-9][a-z0-9_-]{0,47}$"
SURUM = r"^\d+\.\d+\.\d+$"
MAX_DOSYA = 500
MAX_BOYUT = 20 * 1024 * 1024
RISKLI = [
    (re.compile(r"curl[^\n|]*\|\s*(ba)?sh|iwr[^\n|]*\|\s*iex", re.I), "uzaktan indirip calistirma"),
    (re.compile(r"\beval\s*\(|\bexec\s*\(", re.I), "dinamik kod calistirma"),
    (
        re.compile(r"base64\s*-d|b64decode|FromBase64String", re.I),
        "base64 cozme (gizli kod olabilir)",
    ),
    (re.compile(r"rm\s+-rf|Remove-Item[^\n]*-Recurse", re.I), "toplu silme"),
    (re.compile(r"\.ssh|\.env\b|id_rsa|api[_-]?key|token", re.I), "sir/anahtar dosyasina erisim"),
    (re.compile(r"ignore (all|previous) instructions|kurallari yok say", re.I), "prompt injection"),
    (re.compile(r"[​-‏‪-‮⁦-⁩]"), "gizli Unicode karakter"),
]
KURULUM_SCRIPTI = re.compile(r"^(install|setup|postinstall|preinstall)\.|^setup\.py$", re.I)


class Manifest(BaseModel):
    name: str = Field(pattern=AD)
    version: str = Field(pattern=SURUM)
    description: str = Field(min_length=1, max_length=600)
    skills: str = "skills"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _manifest_oku(kok: Path) -> Manifest:
    yol = kok / "plugin.json"
    if not yol.is_file():
        raise UygulamaHatasi("plugin.json bulunamadi.")
    try:
        # utf-8-sig: Windows araclari (Not Defteri, PowerShell) BOM ekliyor
        return Manifest(**json.loads(yol.read_text(encoding="utf-8-sig")))
    except (ValueError, TypeError) as e:
        raise UygulamaHatasi(f"plugin.json gecersiz: {str(e)[:300]}") from e


def klasor_hashi(kok: Path) -> str:
    """Goreli yol + icerik hash'lerinden tek ozet (katalog kilidi icin)."""
    h = hashlib.sha256()
    for p in sorted(x for x in kok.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(kok)).replace("\\", "/").encode() + b"\0" + _sha(p).encode())
    return h.hexdigest()


def inceleme_raporu(kok: Path) -> dict:
    dosyalar, riskler, scriptler, toplam = [], [], [], 0
    for p in sorted(kok.rglob("*")):
        if p.is_symlink():
            riskler.append(
                {"dosya": str(p.relative_to(kok)), "neden": "sembolik link (reddedilir)"}
            )
            continue
        if not p.is_file():
            continue
        goreli = str(p.relative_to(kok)).replace("\\", "/")
        toplam += p.stat().st_size
        dosyalar.append({"dosya": goreli, "boyut": p.stat().st_size, "sha256": _sha(p)[:16]})
        if KURULUM_SCRIPTI.match(p.name):
            scriptler.append(goreli)
        try:
            metin = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for desen, neden in RISKLI:
            if m := desen.search(metin):
                satir = metin.count("\n", 0, m.start()) + 1
                riskler.append({"dosya": f"{goreli}:{satir}", "neden": neden})
    return {
        "dosya_sayisi": len(dosyalar),
        "toplam_bayt": toplam,
        "dosyalar": dosyalar[:200],
        "klasor_hashi": klasor_hashi(kok),
        "riskler": riskler[:100],
        "kurulum_scriptleri": scriptler,
        "not": "Scriptler calistirilmaz. Hash/imza guvenlik kaniti degildir; dosyalari incele.",
    }


class PluginDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.kok = veri_dizini / "plugins"
        self.karantina = self.kok / "_karantina"
        self.kayit = self.kok / "kayit.json"
        self.politika_yolu = veri_dizini / "plugin-politika.json"
        self.karantina.mkdir(parents=True, exist_ok=True)

    # ---- kayit: {ad: {"aktif": surum|None, "surumler": [...], "kurulum": tarih}} ----
    def _kayit(self) -> dict:
        return json_oku(self.kayit, {}) or {}

    def _politika(self, ad: str) -> None:
        p = json_oku(self.politika_yolu, {}) or {}
        if ad in (p.get("yasak") or []):
            raise UygulamaHatasi(f"Kurum politikasi '{ad}' plugin'ini yasakliyor.")
        izinli = p.get("izinli") or []
        if izinli and ad not in izinli:
            raise UygulamaHatasi(
                f"Kurum politikasi yalniz izinli plugin'lere izin veriyor: {ad} listede yok."
            )

    def karantinaya_al(self, kaynak: str) -> dict:
        k = Path(kaynak).expanduser()
        if not k.is_dir():
            raise UygulamaHatasi(f"Klasor bulunamadi: {kaynak}")
        m = _manifest_oku(k)
        self._politika(m.name)
        dosyalar = [p for p in k.rglob("*") if p.is_file()]
        if len(dosyalar) > MAX_DOSYA or sum(p.stat().st_size for p in dosyalar) > MAX_BOYUT:
            raise UygulamaHatasi("Plugin cok buyuk (500 dosya / 20 MB siniri).")
        hedef = self.karantina / f"{m.name}-{m.version}"
        if hedef.exists():
            shutil.rmtree(hedef)
        shutil.copytree(k, hedef, symlinks=True)  # link takip edilmez; raporda reddedilir
        return {
            "manifest": m.model_dump(),
            "rapor": inceleme_raporu(hedef),
            "karantina": hedef.name,
        }

    # ---- katalog (A7.5): data/plugin-katalog.json [{name, version, yol, sha256}] ----
    def katalog(self) -> list[dict]:
        k = json_oku(self.kok.parent / "plugin-katalog.json", []) or []
        return [
            x for x in k if isinstance(x, dict) and {"name", "version", "yol", "sha256"} <= set(x)
        ]

    def katalogdan_karantina(self, ad: str) -> dict:
        oge = next((x for x in self.katalog() if x["name"] == ad), None)
        if oge is None:
            raise Bulunamadi("Katalogda boyle bir plugin yok.")
        k = self.karantinaya_al(str(oge["yol"]))
        m = k["manifest"]
        if m["version"] != oge["version"] or k["rapor"]["klasor_hashi"] != oge["sha256"]:
            shutil.rmtree(self.karantina / k["karantina"], ignore_errors=True)
            raise UygulamaHatasi(
                "Katalog kilidi uyusmuyor (surum ya da icerik hash'i farkli); kurulmadi."
            )
        return k

    def kur(self, karantina_adi: str) -> dict:
        kaynak = self.karantina / karantina_adi
        if not re.fullmatch(r"[a-z0-9_-]+-\d+\.\d+\.\d+", karantina_adi) or not kaynak.is_dir():
            raise Bulunamadi("Karantinada boyle bir plugin yok.")
        m = _manifest_oku(kaynak)
        self._politika(m.name)
        if any(r["neden"].startswith("sembolik") for r in inceleme_raporu(kaynak)["riskler"]):
            raise UygulamaHatasi("Sembolik link iceren plugin kurulamaz.")
        hedef = self.kok / m.name / m.version
        if hedef.exists():
            shutil.rmtree(hedef)
        hedef.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(kaynak), str(hedef))
        kayit = self._kayit()
        g = kayit.setdefault(m.name, {"surumler": []})
        if m.version not in g["surumler"]:
            g["surumler"].append(m.version)
        g["onceki"] = g.get("aktif")
        g["aktif"] = m.version
        g["kurulum"] = datetime.now().isoformat(timespec="seconds")
        json_yaz(self.kayit, kayit)
        return self.liste_ogesi(m.name)

    def geri_al(self, ad: str) -> dict:
        kayit = self._kayit()
        g = kayit.get(ad)
        if not g or not g.get("onceki") or g["onceki"] not in g["surumler"]:
            raise UygulamaHatasi("Geri alinacak onceki surum yok.")
        g["aktif"], g["onceki"] = g["onceki"], g["aktif"]
        json_yaz(self.kayit, kayit)
        return self.liste_ogesi(ad)

    def ac_kapat(self, ad: str, acik: bool) -> dict:
        kayit = self._kayit()
        if ad not in kayit:
            raise Bulunamadi("Plugin bulunamadi.")
        kayit[ad]["kapali"] = not acik
        json_yaz(self.kayit, kayit)
        return self.liste_ogesi(ad)

    def kaldir(self, ad: str) -> None:
        kayit = self._kayit()
        if ad not in kayit or not re.fullmatch(AD, ad):
            raise Bulunamadi("Plugin bulunamadi.")
        shutil.rmtree(self.kok / ad, ignore_errors=True)
        kayit.pop(ad)
        json_yaz(self.kayit, kayit)

    def liste_ogesi(self, ad: str) -> dict:
        g = self._kayit()[ad]
        m = _manifest_oku(self.kok / ad / g["aktif"]) if g.get("aktif") else None
        return {"ad": ad, **g, "aciklama": m.description if m else "", "acik": not g.get("kapali")}

    def liste(self) -> list[dict]:
        return [self.liste_ogesi(ad) for ad in sorted(self._kayit())]

    def skill_kaynaklari(self) -> list[tuple[str, Path]]:
        """Aktif ve acik plugin'lerin skill klasorleri (politika her seferinde kontrol edilir:
        sonradan yasaklanan plugin'in skill'leri hemen devre disi kalir)."""
        sonuc = []
        for ad, g in self._kayit().items():
            if g.get("kapali") or not g.get("aktif"):
                continue
            try:
                self._politika(ad)
                m = _manifest_oku(self.kok / ad / g["aktif"])
            except UygulamaHatasi:
                continue
            sonuc.append((f"plugin:{ad}", self.kok / ad / g["aktif"] / m.skills))
        return sonuc
