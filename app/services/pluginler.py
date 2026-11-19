"""Plugin'ler (A7.4-5, A7.7): manifest, karantina, inceleme, kurulum, surum/geri alma, kaldirma.

Plugin = klasor + plugin.json {name, version, description, skills?: "skills"}. Plugin skill, komut,
ajan, hook ve MCP tasir; hook ve MCP komut calistirdigi icin kurulumda KAPALI gelir, kullanici
`bilesen_ac` ile acikca acar.
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
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.agent.dosyalar import ortam_allowlist
from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services import cc_plugin as cc
from app.services.depo import json_oku, json_yaz, klasor_sil

AD = r"^[a-z0-9][a-z0-9_-]{0,47}$"
SURUM = r"^\d+\.\d+\.\d+$"
MAX_DOSYA = 10_000  # gercek Claude Code plugin'leri node_modules ile gelebiliyor (telegram: 3622)
MAX_BOYUT = 150 * 1024 * 1024
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
    description: str = Field(default="", max_length=600)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _manifest_oku(kok: Path) -> Manifest:
    """Claude Code formati (.claude-plugin/plugin.json) ya da kokte plugin.json."""
    try:
        ham = cc.ham_manifest(kok)  # utf-8-sig: Windows araclari BOM ekliyor
    except (ValueError, OSError) as e:
        raise UygulamaHatasi(f"plugin.json gecersiz: {str(e)[:300]}") from e
    if ham is None:
        raise UygulamaHatasi(
            "plugin.json bulunamadi (.claude-plugin/plugin.json ya da plugin.json)."
        )
    if not ham.get("name"):
        raise UygulamaHatasi("plugin.json gecersiz: 'name' zorunlu.")
    try:
        return Manifest(
            name=cc.ad_normalize(ham["name"]),
            version=cc.surum_normalize(ham.get("version")),
            description=str(ham.get("description") or "")[:600],
        )
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

    def karantinaya_al(self, kaynak: str, ad: str = "") -> dict:
        k = Path(kaynak).expanduser()
        if not k.is_dir():
            raise UygulamaHatasi(f"Klasor bulunamadi: {kaynak}")
        dosyalar = [p for p in k.rglob("*") if p.is_file()]
        if len(dosyalar) > MAX_DOSYA or sum(p.stat().st_size for p in dosyalar) > MAX_BOYUT:
            raise UygulamaHatasi(
                f"Plugin cok buyuk ({MAX_DOSYA} dosya / {MAX_BOYUT // 2**20} MB siniri)."
            )
        if cc.ham_manifest(k) is None:
            # Claude Code 'strict: false': manifest marketplace'te olabilir; ad/surum klasorden
            icerik = [p for p in k.iterdir() if p.name not in (".in_use", ".orphaned_at")]
            if not icerik:
                raise UygulamaHatasi("Plugin klasoru bos (indirilmemis ya da yarim kurulum).")
            surum = cc.surum_normalize(k.name) if k.name[:1].isdigit() else "0.0.0"
            ad_ = ad or (k.parent.name if k.name[:1].isdigit() else k.name)
            m = Manifest(name=cc.ad_normalize(ad_.split("@")[0]), version=surum)
            self._politika(m.name)
            hedef = self.karantina / f"{m.name}-{m.version}"
            if hedef.exists():
                shutil.rmtree(hedef)
            shutil.copytree(k, hedef, symlinks=True)
            (hedef / ".claude-plugin").mkdir(exist_ok=True)
            (hedef / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": m.name, "version": m.version,
                            "description": "(manifest yok; klasorden turetildi)"}),
                encoding="utf-8",
            )  # fmt: skip
            return {"manifest": m.model_dump(), "rapor": inceleme_raporu(hedef),
                    "karantina": hedef.name, "bilesenler": _ozet(cc.bilesenler(hedef))}  # fmt: skip
        m = _manifest_oku(k)
        self._politika(m.name)
        hedef = self.karantina / f"{m.name}-{m.version}"
        if hedef.exists():
            shutil.rmtree(hedef)
        shutil.copytree(k, hedef, symlinks=True)  # link takip edilmez; raporda reddedilir
        return {
            "manifest": m.model_dump(),
            "rapor": inceleme_raporu(hedef),
            "karantina": hedef.name,
            "bilesenler": _ozet(cc.bilesenler(hedef)),
        }

    def git_karantina(self, url: str, ref: str = "") -> dict:
        """Git kaynagini indirir ve HICBIR SEY calistirmadan karantinaya alir."""
        if not re.fullmatch(r"https://[\w.-]+/[\w./-]+", url or ""):
            raise UygulamaHatasi("Yalniz https git adresi kabul edilir.")
        gecici = Path(tempfile.mkdtemp(prefix="indir-", dir=self.karantina))
        try:
            arg = ["git", "-c", "core.hooksPath=" + str(gecici / "yok"), "clone", "--depth", "1"]
            if ref and re.fullmatch(r"[\w./-]{1,100}", ref):
                arg += ["--branch", ref]
            r = subprocess.run(  # noqa: S603 - sabit argumanlar
                [*arg, url, str(gecici / "r")],
                capture_output=True,
                text=True,
                timeout=180,
                env=ortam_allowlist(),
            )
            if r.returncode != 0:
                raise UygulamaHatasi(f"Indirilemedi: {(r.stdout + r.stderr)[-300:]}")
            klasor_sil(gecici / "r" / ".git")
            return self.karantinaya_al(str(gecici / "r"))
        finally:
            klasor_sil(gecici)

    # ---- Claude Code marketplace + bu bilgisayardaki Claude Code plugin'leri ----
    def marketplace(self, kaynak: str) -> dict:
        try:
            return cc.marketplace_oku(Path(kaynak).expanduser())
        except (ValueError, OSError) as e:
            raise UygulamaHatasi(f"Marketplace okunamadi: {e}") from e

    def marketplace_karantina(self, kaynak: str, ad: str) -> dict:
        p = next((x for x in self.marketplace(kaynak)["pluginler"] if x["name"] == ad), None)
        if p is None:
            raise Bulunamadi("Marketplace'te boyle bir plugin yok.")
        k = p["kaynak"]
        if k["tur"] == "yol":
            return self.karantinaya_al(k["yol"])
        return self.git_karantina(k["url"], k["ref"])

    def claude_code_pluginleri(self) -> list[dict]:
        durum = json_oku(self.kok / "cc-esitleme.json", {}) or {}
        return [{**p, "esitleme": durum.get(p["ad"], {}).get("durum", "")}
                for p in cc.claude_code_kurulu()]  # fmt: skip

    def claude_code_esitle(self, dur: threading.Event | None = None) -> dict:
        """Claude Code'da kurulu plugin'leri otomatik ice aktarir ve guncel tutar.
        - `dur` set edilince (uygulama kapaniyor) kalan plugin'ler sonraki acilisa birakilir.
        - Ayni kurulum yolu islendiyse atlanir; surum degisince yol degisir ve guncellenir.
        - Inceleme raporunda risk varsa KURULMAZ, karantinada onay bekler.
        - Kullanicinin kaldirdigi plugin tekrar kurulmaz. Hook/MCP her zaman kapali baslar.
        """
        yol = self.kok / "cc-esitleme.json"
        durum: dict = json_oku(yol, {}) or {}
        kayit = self._kayit()
        ozet = {"kuruldu": [], "inceleme": [], "hata": [], "atlandi": 0}
        for p in cc.claude_code_kurulu():
            if dur is not None and dur.is_set():
                break  # yapilan kadari kaydedilir; kapanis bir plugin'den fazla beklemez
            anahtar, d = p["ad"], durum.get(p["ad"], {})
            if d.get("durum") == "kuruldu" and d.get("ad") not in kayit:
                d["durum"] = "kaldirildi"  # kullanici Kairo'dan kaldirdi: zorla geri getirme
            if (
                p["bos"]
                or d.get("durum") == "kaldirildi"
                or (d.get("yol") == p["yol"] and d.get("durum") in ("kuruldu", "inceleme"))
            ):
                ozet["atlandi"] += 1
                durum[anahtar] = d | ({} if d else {"durum": "bos"})
                continue
            try:
                k = self.karantinaya_al(p["yol"], anahtar)
                ad = k["manifest"]["name"]
                # Kullanici bunu Claude Code'a zaten kurmus (guvendigi icerik). Rapordaki desenler
                # cogunlukla dokumandaki "API_KEY" gibi yanlis alarm; yine de sembolik link
                # ya da gizli Unicode varsa kurulmaz, onay bekler. Kod calistiran hook/MCP kapali.
                ciddi = [r for r in k["rapor"]["riskler"]
                         if r["neden"].startswith(("sembolik", "gizli Unicode"))]  # fmt: skip
                if ciddi:
                    durum[anahtar] = {"yol": p["yol"], "ad": ad, "durum": "inceleme",
                                      "karantina": k["karantina"]}  # fmt: skip
                    ozet["inceleme"].append(ad)
                    continue
                self.kur(k["karantina"])
                durum[anahtar] = {"yol": p["yol"], "ad": ad, "durum": "kuruldu",
                                  "uyari": len(k["rapor"]["riskler"])}  # fmt: skip
                ozet["kuruldu"].append(ad)
            except (UygulamaHatasi, Bulunamadi, OSError, ValueError) as e:
                durum[anahtar] = {"yol": p["yol"], "durum": "hata", "hata": str(e)[:200]}
                ozet["hata"].append(f"{anahtar}: {str(e)[:120]}")
        json_yaz(yol, durum)
        return ozet

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
        kok = self.kok / ad / g["aktif"] if g.get("aktif") else None
        m = _manifest_oku(kok) if kok else None
        return {
            **g,
            "ad": ad,
            "aciklama": m.description if m else "",
            "acik": not g.get("kapali"),
            "bilesenler": _ozet(cc.bilesenler(kok)) if kok else {},
            "hooks_acik": bool(g.get("hooks_acik")),
            "mcp_acik": bool(g.get("mcp_acik")),
        }

    def bilesen_ac(self, ad: str, tur: str, acik: bool) -> dict:
        """Hook ve MCP komut CALISTIRIR: kurulumda kapali gelir, kullanici acikca acar."""
        if tur not in ("hooks", "mcp"):
            raise UygulamaHatasi("Tur: hooks ya da mcp.")
        kayit = self._kayit()
        if ad not in kayit:
            raise Bulunamadi("Plugin bulunamadi.")
        kayit[ad][f"{tur}_acik"] = acik
        json_yaz(self.kayit, kayit)
        return self.liste_ogesi(ad)

    def _acik_pluginler(self) -> list[tuple[str, Path]]:
        out = []
        for ad, g in self._kayit().items():
            if g.get("kapali") or not g.get("aktif"):
                continue
            try:
                self._politika(ad)
            except UygulamaHatasi:
                continue
            out.append((ad, self.kok / ad / g["aktif"]))
        return out

    def komutlar(self) -> list[dict]:
        out = []
        for ad, kok in self._acik_pluginler():
            for k in cc.bilesenler(kok)["komutlar"]:
                out.append({"komut": f"{ad}:{k['ad']}", "kisa": k["ad"], "plugin": ad,
                            "aciklama": k["aciklama"], "ipucu": k["ipucu"]})  # fmt: skip
        return out

    def komut_genislet(self, komut: str, arg: str) -> dict:
        ad, _, kisa = komut.partition(":")
        for p, kok in self._acik_pluginler():
            if kisa and p != ad:
                continue
            hedef = kisa or ad
            for k in cc.bilesenler(kok)["komutlar"]:
                if k["ad"] == hedef:
                    istem = cc.komut_genislet(k["govde"], arg, kok)
                    return {"plugin": p, "komut": k["ad"], "istem": istem}
        raise Bulunamadi(f"/{komut} plugin komutu bulunamadi.")

    def ajan_profilleri(self) -> dict[str, dict]:
        return {
            f"{ad}:{a['ad']}": a
            for ad, kok in self._acik_pluginler()
            for a in cc.bilesenler(kok)["ajanlar"]
        }

    def hook_tanimlari(self) -> list[dict]:
        out = []
        for ad, kok in self._acik_pluginler():
            if not self._kayit()[ad].get("hooks_acik"):
                continue
            for i, h in enumerate(cc.bilesenler(kok)["hooks"]):
                out.append({
                    "id": f"p{i:02d}{ad}"[:12], "ad": f"{ad} ({h['olay']})"[:80],
                    "olay": h["olay"], "tur": "guvenlik", "komut": cc.hook_komutu(h["komut"], kok),
                    "eslesen": h["eslesen"], "timeout": max(1, min(h["timeout"], 120)),
                    "bicim": "claude", "kaynak": f"plugin:{ad}",
                    "ortam": {"CLAUDE_PLUGIN_ROOT": kok.as_posix()},
                })  # fmt: skip
        return out

    def mcp_tanimlari(self) -> list[dict]:
        out = []
        for ad, kok in self._acik_pluginler():
            if not self._kayit()[ad].get("mcp_acik"):
                continue
            for sad, ham in cc.bilesenler(kok)["mcp"].items():
                d = cc.mcp_donustur(cc.ad_normalize(f"{ad}-{sad}")[:32], ham, kok)
                if d:
                    out.append(d)
        return out

    def liste(self) -> list[dict]:
        return [self.liste_ogesi(ad) for ad in sorted(self._kayit())]

    def skill_kaynaklari(self) -> list[tuple[str, Path]]:
        """Aktif ve acik plugin'lerin skill klasorleri (politika her seferinde kontrol edilir:
        sonradan yasaklanan plugin'in skill'leri hemen devre disi kalir)."""
        return [
            (f"plugin:{ad}", d)
            for ad, kok in self._acik_pluginler()
            for d in cc.bilesenler(kok)["skills"]
        ]


def _ozet(b: dict) -> dict:
    skill = sum(len([x for x in d.iterdir() if (x / "SKILL.md").is_file()]) for d in b["skills"])
    return {
        "skill": skill,
        "komut": [k["ad"] for k in b["komutlar"]],
        "ajan": [a["ad"] for a in b["ajanlar"]],
        "hook": len(b["hooks"]),
        "mcp": list(b["mcp"]),
        "desteklenmeyen": b["desteklenmeyen"],
    }
