"""Jupyter not defteri araclari: notebook_oku (salt okuma) ve notebook_duzenle (yazma).

Yazma, `YazmaAraclari.dosya_yaz` uzerinden gecer: izin -> beklenen hash -> checkpoint -> atomik
yazim. Boylece geri alma ve bayat-yazim korumasi dosya araclariyla birebir aynidir.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.agent.checkpoints import icerik_hashi
from app.agent.dosyalar import MAX_DOSYA_BAYT, KokKapsami
from app.agent.yazma import YazmaAraclari
from app.exceptions import UygulamaHatasi

TURLER = ("code", "markdown")
ISLEMLER = ("degistir", "ekle", "sil")


def _kaynak_metni(hucre: dict) -> str:
    k = hucre.get("source", "")
    return "".join(k) if isinstance(k, list) else str(k)


def _yukle(p: Path) -> tuple[dict, bytes]:
    if p.suffix.lower() != ".ipynb":
        raise UygulamaHatasi(f"Bu bir Jupyter not defteri (.ipynb) degil: {p.name}")
    if not p.is_file():
        raise UygulamaHatasi(f"Not defteri bulunamadi: {p}")
    if p.stat().st_size > MAX_DOSYA_BAYT:
        raise UygulamaHatasi("Not defteri cok buyuk; islenmedi.")
    ham = p.read_bytes()
    try:
        nb = json.loads(ham.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise UygulamaHatasi(f"Gecersiz not defteri JSON'u ({p.name}): {e}") from e
    if not isinstance(nb, dict) or not isinstance(nb.get("cells"), list):
        raise UygulamaHatasi(f"Gecersiz not defteri: 'cells' listesi yok ({p.name}).")
    return nb, ham


def _yeni_hucre(nb: dict, tur: str, kaynak: str) -> dict:
    hucre: dict = {
        "cell_type": tur,
        "metadata": {},
        "source": kaynak.splitlines(keepends=True),
    }
    if tur == "code":
        hucre["outputs"] = []
        hucre["execution_count"] = None
    if int(nb.get("nbformat_minor", 0) or 0) >= 5:
        hucre["id"] = uuid.uuid4().hex[:8]  # nbformat 4.5+ hucre kimligi ister
    return hucre


class NotebookAraclari:
    def __init__(self, kapsam: KokKapsami, yazma: YazmaAraclari) -> None:
        self.kapsam = kapsam
        self.yazma = yazma

    def notebook_oku(self, yol: str) -> dict:
        p = self.kapsam.coz(yol)
        nb, ham = _yukle(p)
        hucreler = [
            {
                "no": i,
                "tur": h.get("cell_type", "?"),
                "kaynak": _kaynak_metni(h),
                "cikti_sayisi": len(h.get("outputs") or []),
            }
            for i, h in enumerate(nb["cells"])
        ]
        return {
            "dosya": str(p),
            "goreli": self.kapsam.goreli(p),
            "hucre_sayisi": len(hucreler),
            "hucreler": hucreler,
            # notebook_duzenle `beklenen_hash` olarak ister
            "hash": icerik_hashi(ham),
        }

    def notebook_duzenle(
        self,
        yol: str,
        islem: str,
        hucre_no: int | None = None,
        kaynak: str = "",
        tur: str = "",
        beklenen_hash: str | None = None,
    ) -> dict:
        if islem not in ISLEMLER:
            raise UygulamaHatasi(f"Gecersiz islem '{islem}': {', '.join(ISLEMLER)} olmali.")
        if tur and tur not in TURLER:
            raise UygulamaHatasi(f"Gecersiz hucre turu '{tur}': code ya da markdown olmali.")
        p = self.kapsam.coz(yol)
        nb, _ = _yukle(p)
        hucreler: list = nb["cells"]
        n = len(hucreler)

        if islem == "ekle":
            no = n if hucre_no is None else hucre_no
            if not 0 <= no <= n:
                raise UygulamaHatasi(f"Gecersiz hucre_no {no}: ekleme icin 0-{n} araligi olmali.")
            hucreler.insert(no, _yeni_hucre(nb, tur or "code", kaynak))
        else:
            if hucre_no is None or not 0 <= hucre_no < n:
                raise UygulamaHatasi(
                    f"Gecersiz hucre_no {hucre_no}: not defterinde {n} hucre var (0 tabanli)."
                )
            no = hucre_no
            if islem == "sil":
                del hucreler[no]
            else:
                eski = hucreler[no]
                yeni = _yeni_hucre(nb, tur or eski.get("cell_type", "code"), kaynak)
                # kimlik ve ust veri korunur; code hucrenin eski ciktilari bayat oldugu icin atilir
                yeni["metadata"] = eski.get("metadata", {})
                if "id" in eski:
                    yeni["id"] = eski["id"]
                hucreler[no] = yeni

        icerik = json.dumps(nb, indent=1, ensure_ascii=False) + "\n"  # nbformat bicimi
        sonuc = self.yazma.dosya_yaz(str(p), icerik, beklenen_hash)
        return {**sonuc, "islem": islem, "hucre_no": no, "hucre_sayisi": len(hucreler)}
