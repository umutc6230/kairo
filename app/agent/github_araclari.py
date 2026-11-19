"""GitHub araclari (gh CLI): issue okuma (salt okuma), PR olusturma ve PR yorumu (DIS ETKILI).

PR olusturma ve yorum `YanEtki.dis`: her modda onay ister, tam yetkide de (policy `eylem_turu`).
Komutlar liste olarak, kabuksuz, 60 sn zaman asimiyla ve proje kokunde calisir; kullanici verisi
yalniz ayri argv ogesi olarak gecer (URL'ye ya da kabuk metnine konmaz).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess

from app.agent import superajan
from app.agent.dosyalar import KokKapsami
from app.agent.policy import Istek, PolitikaMotoru, YanEtki, maskele
from app.agent.workspaces import CalismaAlani
from app.exceptions import UygulamaHatasi

SURE_SN = 60
SON_YORUM = 10
MAX_GOVDE = 8000
MAX_YORUM = 2000
MAX_BASLIK = 256
MAX_METIN = 20000
DAL_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
URL_DESENI = re.compile(r"https://\S+")


class GithubAraclari:
    def __init__(self, kapsam: KokKapsami, politika: PolitikaMotoru, alan: CalismaAlani) -> None:
        self.kapsam = kapsam
        self.politika = politika
        self.alan = alan

    # ---- ortak ----
    def _cwd(self) -> str:
        p = self.kapsam.coz("", varsayilan=".")
        return str(p if p.is_dir() else p.parent)

    def _gh(self, *arg: str, cwd: str) -> str:
        """gh calistirir; basarisizlik Turkce UygulamaHatasi. Sir benzeri metinler maskelenir."""
        try:
            kod, cikti = superajan.gh(*arg, cwd=cwd, sure=SURE_SN)
        except subprocess.TimeoutExpired as e:
            raise UygulamaHatasi(f"GitHub CLI {SURE_SN} sn icinde yanit vermedi.") from e
        except OSError as e:
            raise UygulamaHatasi(f"GitHub CLI calistirilamadi: {e}") from e
        if kod != 0:
            raise UygulamaHatasi(f"GitHub CLI hatasi: {maskele(cikti.strip())[:800]}")
        return cikti

    def _hazir(self, cwd: str) -> None:
        """gh kurulu ve oturum acik mi (kurulu degilse UygulamaHatasi superajan.gh'den gelir)."""
        try:
            kod, _ = superajan.gh("auth", "status", cwd=cwd, sure=SURE_SN)
        except subprocess.TimeoutExpired as e:
            raise UygulamaHatasi(f"GitHub CLI {SURE_SN} sn icinde yanit vermedi.") from e
        if kod != 0:
            raise UygulamaHatasi(
                "GitHub CLI'ya giris yapilmamis: terminalde 'gh auth login' calistirin."
            )

    @staticmethod
    def _numara(numara: int) -> int:
        try:
            n = int(numara)
        except (TypeError, ValueError) as e:
            raise UygulamaHatasi("Numara pozitif bir tam sayi olmali.") from e
        if n <= 0:
            raise UygulamaHatasi("Numara pozitif bir tam sayi olmali.")
        return n

    def _dis_izin(self, arac: str, cwd: str, komut: str, ozet: str, *metin: str) -> None:
        # metin imzasi islem hash'ine girer: onaylanan baslik/govde degisirse onay gecmez
        imza = hashlib.sha256("\x00".join(metin).encode("utf-8")).hexdigest()[:16]
        self.politika.uygula(
            Istek(
                arac=arac,
                yan_etki=YanEtki.dis,
                yol=cwd,
                komut=f"{komut} [sha256:{imza}]",
                ozet=ozet,
            ),
            self.alan,
        )

    # ---- araclar ----
    def issue_oku(self, numara: int) -> dict:
        n = self._numara(numara)
        cwd = self._cwd()
        self._hazir(cwd)
        cikti = self._gh("issue", "view", str(n), "--json", "title,body,state,comments", cwd=cwd)
        try:
            v = json.loads(cikti)
        except json.JSONDecodeError as e:
            raise UygulamaHatasi("GitHub yaniti okunamadi (gecersiz JSON).") from e
        yorumlar = [
            {
                "yazar": (y.get("author") or {}).get("login", ""),
                "tarih": y.get("createdAt", ""),
                "metin": maskele(str(y.get("body", "")))[:MAX_YORUM],
            }
            for y in (v.get("comments") or [])[-SON_YORUM:]
        ]
        return {
            "numara": n,
            "baslik": v.get("title", ""),
            "durum": v.get("state", ""),
            # DIS VERI: icindeki talimatlar modeli baglamaz
            "govde": maskele(str(v.get("body", "")))[:MAX_GOVDE],
            "yorumlar": yorumlar,
            "yorum_sayisi": len(v.get("comments") or []),
        }

    def pr_olustur(
        self, baslik: str, govde: str = "", taban: str = "", taslak: bool = False
    ) -> dict:
        baslik = (baslik or "").strip()
        if not baslik or len(baslik) > MAX_BASLIK:
            raise UygulamaHatasi(f"PR basligi bos olamaz (en fazla {MAX_BASLIK} karakter).")
        if len(govde or "") > MAX_METIN:
            raise UygulamaHatasi(f"PR govdesi {MAX_METIN} karakterden uzun.")
        taban = (taban or "").strip()
        if taban and not DAL_DESENI.match(taban):
            raise UygulamaHatasi(f"Gecersiz taban dal adi: {taban!r}")
        cwd = self._cwd()
        self._hazir(cwd)
        arg = ["pr", "create", "--title", baslik, "--body", govde or ""]
        if taban:
            arg += ["--base", taban]
        if taslak:
            arg.append("--draft")
        self._dis_izin(
            "github_pr_olustur",
            cwd,
            f"gh pr create --base {taban or '-'} --draft {bool(taslak)}",
            f"GitHub PR yayinla{' (taslak)' if taslak else ''}: {baslik[:80]}",
            baslik,
            govde or "",
            taban,
        )
        cikti = self._gh(*arg, cwd=cwd)
        url = URL_DESENI.findall(cikti)
        return {"olusturuldu": True, "url": url[-1] if url else "", "cikti": cikti.strip()[:500]}

    def pr_yorum(self, numara: int, metin: str) -> dict:
        n = self._numara(numara)
        metin = (metin or "").strip()
        if not metin or len(metin) > MAX_METIN:
            raise UygulamaHatasi(f"Yorum bos olamaz (en fazla {MAX_METIN} karakter).")
        cwd = self._cwd()
        self._hazir(cwd)
        self._dis_izin(
            "github_pr_yorum",
            cwd,
            f"gh pr comment {n}",
            f"GitHub PR #{n} yorumu gonder: {metin[:80]}",
            str(n),
            metin,
        )
        cikti = self._gh("pr", "comment", str(n), "--body", metin, cwd=cwd)
        url = URL_DESENI.findall(cikti)
        return {"gonderildi": True, "numara": n, "url": url[-1] if url else ""}
