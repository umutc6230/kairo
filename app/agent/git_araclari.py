"""Git araclari (A2.6). Bu dilimde YALNIZ OKUMA: status, diff, log, branch, show.

commit / push / merge / PR ayri bir yan etki sinifidir (`YanEtki.dis`) ve bu dilimde ACILMADI:
model metni tek basina gonderim yetkisi olmamali, remote URL islemin parcasi olarak
dogrulanmali. Eklenince `PolitikaMotoru.uygula` ile onaya baglanacak.

Alt komut ALLOWLIST'tir: kullanicinin/modelin verdigi metin kabuga gecmez, argumanlar listeyle
verilir (kabuk yok), boylece `git log; rm -rf` gibi zincirleme calismaz.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from app.agent import kum
from app.agent.dosyalar import ortam_allowlist
from app.exceptions import UygulamaHatasi, YetkiYok

MAX_CIKTI = 30000
TIMEOUT = 30
OKUMA_KOMUTLARI = {
    "status": ["status", "--porcelain=v1", "--branch"],
    "diff": ["diff", "--no-ext-diff", "--no-textconv"],
    "diff_staged": ["diff", "--staged", "--no-ext-diff", "--no-textconv"],
    "log": ["log", "--oneline", "-20"],
    "branch": ["branch", "--show-current"],
    "dallar": ["branch", "--list"],
    "kok": ["rev-parse", "--show-toplevel"],
}


def git_var_mi() -> bool:
    return shutil.which("git") is not None


def _calistir(argumanlar: list[str], cwd: Path) -> tuple[int, str]:
    git = shutil.which("git")
    if not git:
        raise UygulamaHatasi("Bu bilgisayarda git bulunamadi.")
    ortam = ortam_allowlist()
    kum.git_komut_sertlestir(ortam)
    try:
        ch = subprocess.run(  # noqa: S603 - sabit allowlist argumanlari, kabuk yok
            [git, "-c", "diff.external=", *argumanlar],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT,
            env=ortam,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired as e:
        raise UygulamaHatasi(f"git {argumanlar[0]} zaman asimina ugradi.") from e
    except OSError as e:
        raise UygulamaHatasi(f"git calistirilamadi: {e}") from e
    return ch.returncode, ((ch.stdout or "") + (ch.stderr or ""))[:MAX_CIKTI]


class GitAraclari:
    """Yalniz yetkili kok icinde calisir; kok disi bir repo yoluna bakilmaz."""

    def __init__(self, kapsam) -> None:  # KokKapsami
        self.kapsam = kapsam

    def _cwd(self, klasor: str = "") -> Path:
        p = self.kapsam.coz(klasor, varsayilan=".")
        return p if p.is_dir() else p.parent

    def git_durum(self, klasor: str = "") -> dict:
        """Calisma agaci durumu. Kullanicinin KENDI degisikliklerini ayirt etmek icin kullanilir."""
        try:
            cwd = self._cwd(klasor)
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        if not git_var_mi():
            return {"hata": "git bulunamadi.", "git": False}
        kod, cikti = _calistir(OKUMA_KOMUTLARI["status"], cwd)
        if kod != 0:
            return {"hata": cikti.strip() or "git status basarisiz.", "repo": False}
        dal = ""
        degisen: list[dict] = []
        for satir in cikti.splitlines():
            if satir.startswith("##"):
                dal = satir[2:].strip().split("...")[0]
                continue
            if len(satir) > 3:
                degisen.append({"durum": satir[:2].strip(), "yol": satir[3:].strip()})
        return {
            "repo": True,
            "klasor": str(cwd),
            "dal": dal,
            "degisen_sayisi": len(degisen),
            "degisenler": degisen[:100],
            "temiz": not degisen,
        }

    def git_ozet(self, klasor: str = "") -> dict:
        """Sag panel 'Degisiklikler' satiri: dal + commit edilmemis satir sayilari."""
        d = self.git_durum(klasor)
        if not d.get("repo"):
            return {"repo": False}
        # dock'taki diff ile ayni kapsam (git diff): satira tiklaninca ayni degisiklik gorunur
        _, cikti = _calistir(
            ["diff", "--no-ext-diff", "--no-textconv", "--numstat"], Path(d["klasor"])
        )
        ekle = sil = 0
        for satir in cikti.splitlines():
            p = satir.split("\t")
            if len(p) >= 3 and p[0].isdigit() and p[1].isdigit():  # ikili dosya: "-\t-"
                ekle, sil = ekle + int(p[0]), sil + int(p[1])
        return {"repo": True, "klasor": d["klasor"], "dal": d["dal"],
                "dosya": d["degisen_sayisi"], "ekle": ekle, "sil": sil}  # fmt: skip

    def git_diff(self, klasor: str = "", staged: bool = False) -> dict:
        try:
            cwd = self._cwd(klasor)
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        if not git_var_mi():
            return {"hata": "git bulunamadi.", "git": False}
        kod, cikti = _calistir(OKUMA_KOMUTLARI["diff_staged" if staged else "diff"], cwd)
        if kod != 0:
            if "not a git repository" in cikti.lower():  # ham git kullanim metni yerine
                return {"hata": "Bu klasor bir git deposu degil; diff/review icin git gerekir.",
                        "repo": False}  # fmt: skip
            return {"hata": cikti.strip() or "git diff basarisiz."}
        return {
            "klasor": str(cwd),
            "staged": staged,
            "truncated": len(cikti) >= MAX_CIKTI,
            "diff": cikti,
        }

    def git_gecmis(self, klasor: str = "", adet: int = 20) -> dict:
        try:
            cwd = self._cwd(klasor)
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}
        if not git_var_mi():
            return {"hata": "git bulunamadi.", "git": False}
        adet = max(1, min(int(adet), 100))
        kod, cikti = _calistir(["log", "--oneline", f"-{adet}"], cwd)
        if kod != 0:
            return {"hata": cikti.strip() or "git log basarisiz."}
        return {"klasor": str(cwd), "commitler": cikti.splitlines()}

    # ---- yazan islemler (izin cagirani tarafindan: YanEtki.git, her zaman onay) ----
    def dal_adi_dogrula(self, ad: str, cwd: Path) -> str:
        ad = (ad or "").strip()
        if not ad or ad.startswith("-"):
            raise UygulamaHatasi("Gecersiz dal adi.")
        kod, _ = _calistir(["check-ref-format", "--branch", ad], cwd)
        if kod != 0:
            raise UygulamaHatasi(f"Gecersiz dal adi: {ad}")
        return ad

    def dal(self, cwd: Path, ad: str, yeni: bool) -> dict:
        kod, cikti = _calistir(["switch", *(["-c"] if yeni else []), ad], cwd)
        if kod != 0:  # git, yerel degisikligi ezecek gecisi kendisi reddeder
            raise UygulamaHatasi(cikti.strip() or "git switch basarisiz.")
        return {"dal": ad, "olusturuldu": yeni, "cikti": cikti.strip()}

    def commit(self, cwd: Path, mesaj: str, yollar: list[Path]) -> dict:
        """YALNIZ verilen dosyalar commit edilir; kullanicinin diger degisiklikleri dokunulmaz."""
        goreli = [str(p) for p in yollar]
        kod, cikti = _calistir(["add", "--", *goreli], cwd)
        if kod != 0:
            raise UygulamaHatasi(cikti.strip() or "git add basarisiz.")
        kod, cikti = _calistir(["commit", "-m", mesaj, "--only", "--", *goreli], cwd)
        if kod != 0:
            raise UygulamaHatasi(cikti.strip() or "git commit basarisiz.")
        _, hash_ = _calistir(["rev-parse", "--short", "HEAD"], cwd)
        return {"commit": hash_.strip(), "dosyalar": goreli, "cikti": cikti.strip()[:2000]}


def kullanici_degisiklikleri(kapsam, klasor: str = "") -> set[str]:
    """Ajan calismaya BASLAMADAN once var olan degisiklikler (A2.3).

    Bu kume ile ajanin kendi degisiklikleri ayrilir; geri alma kullanicinin isini silmez.
    """
    try:
        durum = GitAraclari(kapsam).git_durum(klasor)
    except UygulamaHatasi:
        return set()
    if not durum.get("repo"):
        return set()
    return {d["yol"] for d in durum.get("degisenler", [])}
