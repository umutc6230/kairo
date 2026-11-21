"""Uygulama ici surum kontrolu: GitHub Releases latest kontrolu + 24 saatlik onbellek."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import httpx

from app import __version__
from app.services.depo import json_oku, json_yaz

ONBELLEK_SN = 24 * 60 * 60


def surum_demeti(s: str) -> tuple[int, ...]:
    """'v0.2.1' -> (0, 2, 1); karsilastirma icin sayisal parcalari cikarir."""
    parcalar = [int(x) for x in re.findall(r"\d+", str(s or ""))]
    return tuple(parcalar) if parcalar else (0,)


class GuncellemeDenetleyici:
    """GitHub Releases uzerinden yeni surum olup olmadigini denetler."""

    def __init__(
        self,
        veri_dizini: Path,
        depo: str = "umutc6230/kairo",
        transport: Any = None,
    ) -> None:
        self.yol = veri_dizini / "guncelleme-onbellek.json"
        self.depo = depo
        self.transport = transport

    def _onbellekten_kur(self, kayit: dict, **ek: Any) -> dict[str, Any]:
        son = str(kayit.get("son") or __version__)
        return {
            "mevcut": __version__,
            "son": son,
            "etiket": str(kayit.get("etiket") or son),
            "yeni_var": surum_demeti(son) > surum_demeti(__version__),
            "adres": str(kayit.get("adres") or f"https://github.com/{self.depo}/releases"),
            "notlar": str(kayit.get("notlar") or "")[:1200],
            "yayin_tarihi": str(kayit.get("yayin_tarihi") or ""),
            "kontrol_zamani": float(kayit.get("kontrol_zamani") or 0.0),
            **ek,
        }

    async def kontrol(self, zorla: bool = False, ag_acik: bool = True) -> dict[str, Any]:
        kayit = json_oku(self.yol, {}) or {}
        if not isinstance(kayit, dict):
            kayit = {}
        simdi = time.time()

        if not ag_acik:
            if kayit.get("son"):
                sonuc = self._onbellekten_kur(
                    kayit,
                    uyari="Ag erisimi kapali; son kayit gosteriliyor.",
                )
                sonuc["not"] = "Ag erisimi kapali."
                return sonuc
            return {
                "mevcut": __version__,
                "son": __version__,
                "yeni_var": False,
                "adres": f"https://github.com/{self.depo}/releases",
                "notlar": "",
                "not": "Ag erisimi kapali.",
            }

        if (
            not zorla
            and kayit.get("son")
            and (simdi - float(kayit.get("kontrol_zamani") or 0.0)) < ONBELLEK_SN
        ):
            return self._onbellekten_kur(kayit, onbellekten=True)

        url = f"https://api.github.com/repos/{self.depo}/releases/latest"
        try:
            async with httpx.AsyncClient(timeout=10, transport=self.transport) as c:
                r = await c.get(
                    url,
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "Kairo"},
                )
            if r.status_code == 404:
                sonuc = {
                    "mevcut": __version__,
                    "son": __version__,
                    "etiket": __version__,
                    "yeni_var": False,
                    "adres": f"https://github.com/{self.depo}/releases",
                    "notlar": "",
                    "yayin_tarihi": "",
                    "kontrol_zamani": simdi,
                    "not": "Henuz yayinlanmis surum yok.",
                }
                json_yaz(self.yol, sonuc)
                return sonuc
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
            j = r.json()
            etiket = str(j.get("tag_name") or "").strip()
            son = etiket.lstrip("vV") or __version__
            sonuc = {
                "mevcut": __version__,
                "son": son,
                "etiket": etiket or son,
                "yeni_var": surum_demeti(son) > surum_demeti(__version__),
                "adres": str(j.get("html_url") or f"https://github.com/{self.depo}/releases"),
                "notlar": str(j.get("body") or "")[:1200],
                "yayin_tarihi": str(j.get("published_at") or ""),
                "kontrol_zamani": simdi,
            }
            json_yaz(self.yol, sonuc)
            return sonuc
        except (httpx.HTTPError, RuntimeError, ValueError) as e:
            uyari = f"Surum kontrolu basarisiz: {str(e)[:120]}"
            if kayit.get("son"):
                return self._onbellekten_kur(kayit, uyari=uyari)
            return {
                "mevcut": __version__,
                "son": __version__,
                "yeni_var": False,
                "adres": f"https://github.com/{self.depo}/releases",
                "notlar": "",
                "uyari": uyari,
            }
