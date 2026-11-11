"""Izole calisma (A8.3): gorev ayri bir git worktree'de ve ajan/<id> dalinda calisir.

Entegrasyon kurallari:
- Ana calisma agacinda kullanicinin commit edilmemis degisikligi varsa birlestirme YAPILMAZ.
- Istenirse ortak test komutu once worktree'de calisir; basarisizsa birlestirilmez.
- Birlestirme `git merge --no-ff`; catisma olursa `merge --abort` ile geri alinir ve catisan
  dosyalar raporlanir. Catisma ASLA otomatik cozulmez; reset --hard kullanilmaz.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from app.agent.dosyalar import ortam_allowlist
from app.exceptions import UygulamaHatasi

ZAMAN = 120


def _git(cwd: Path, *a: str, sure: int = ZAMAN) -> tuple[int, str]:
    git = shutil.which("git")
    if not git:
        raise UygulamaHatasi("Bu bilgisayarda git bulunamadi.")
    try:
        r = subprocess.run(  # noqa: S603 - sabit argumanlar, kabuk yok
            [git, *a], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=sure, env=ortam_allowlist(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )  # fmt: skip
    except subprocess.TimeoutExpired as e:
        raise UygulamaHatasi(f"git {a[0]} zaman asimina ugradi.") from e
    return r.returncode, (r.stdout + r.stderr).strip()


def depo_koku(proje: Path) -> Path:
    kod, cikti = _git(proje, "rev-parse", "--show-toplevel")
    if kod != 0:
        raise UygulamaHatasi("Izole calisma icin proje bir git deposu olmali.")
    return Path(cikti)


def olustur(proje: Path, hedef_dizin: Path, run_id: str) -> tuple[Path, str]:
    kok = depo_koku(proje)
    dal = f"ajan/{run_id}"
    yol = hedef_dizin / run_id
    yol.parent.mkdir(parents=True, exist_ok=True)
    kod, cikti = _git(kok, "worktree", "add", "-b", dal, str(yol), "HEAD")
    if kod != 0:
        raise UygulamaHatasi(f"Worktree olusturulamadi: {cikti[:300]}")
    return yol, dal


def entegre_et(proje: Path, yol: Path, dal: str, mesaj: str, test_komutu: str = "") -> dict:
    kok = depo_koku(proje)
    if not yol.is_dir():
        raise UygulamaHatasi("Bu gorevin worktree'si bulunamadi (zaten entegre ya da silinmis).")
    # 1) worktree'deki degisiklikler ajan dalina commit
    _git(yol, "add", "-A")
    kod, cikti = _git(yol, "-c", "user.name=Kairo", "-c", "user.email=ajan@yerel",
                      "commit", "-m", mesaj[:200] or "ajan degisikligi")  # fmt: skip
    if kod != 0 and "nothing to commit" not in cikti:
        raise UygulamaHatasi(f"Ajan dalina commit yapilamadi: {cikti[:300]}")
    degisen = _git(kok, "diff", "--name-only", f"HEAD...{dal}")[1].splitlines()
    if not degisen:
        return {"durum": "degisiklik_yok", "dosyalar": []}
    # 2) ortak test worktree'de
    if test_komutu.strip():
        r = subprocess.run(  # noqa: S602 - kullanicinin entegrasyon ekraninda verdigi komut
            test_komutu, shell=True, cwd=str(yol), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900, env=ortam_allowlist(),
        )  # fmt: skip
        if r.returncode != 0:
            return {"durum": "test_basarisiz", "dosyalar": degisen, "cikis_kodu": r.returncode,
                    "cikti": (r.stdout + r.stderr)[-3000:]}  # fmt: skip
    # 3) kullanicinin degisiklikleri korunur
    if _git(kok, "status", "--porcelain", "--untracked-files=no")[1].strip():
        return {"durum": "kullanici_degisikligi_var", "dosyalar": degisen,
                "not": "Ana agacta commit edilmemis degisiklik var; once commit edin."}  # fmt: skip
    # 4) birlestirme; catisma sessiz cozulmez
    kod, cikti = _git(kok, "merge", "--no-ff", "--no-edit", dal)
    if kod != 0:
        catisan = _git(kok, "diff", "--name-only", "--diff-filter=U")[1].splitlines()
        _git(kok, "merge", "--abort")
        return {"durum": "catisma", "dosyalar": degisen, "catisan": catisan,
                "not": f"Catisma cozulmedi; birlestirme geri alindi. Dal: {dal}"}  # fmt: skip
    _git(kok, "worktree", "remove", "--force", str(yol))
    _git(kok, "branch", "-d", dal)
    return {"durum": "birlestirildi", "dosyalar": degisen}


def at(proje: Path, yol: Path, dal: str) -> dict:
    """Izole calismayi birlestirmeden siler (ana agaca dokunmaz)."""
    kok = depo_koku(proje)
    _git(kok, "worktree", "remove", "--force", str(yol))
    _git(kok, "branch", "-D", dal)
    return {"durum": "atildi"}
