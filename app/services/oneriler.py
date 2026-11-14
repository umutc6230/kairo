"""Proaktif oneriler (Grok Bot fikri): yeni sohbet ekraninda ne yapilabilecegini hatirlatir.
Kaynaklar: projelerin DURUM.md yarim/acik maddeleri, insan bekleyen thread'ler, yaklasan rutinler.
Model cagrisi yok; yalniz yerel dosya ve kayitlar okunur."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from app.agent.superajan import INSAN_BEKLIYOR
from app.agent.zamanlayici import sonraki

_MADDE = re.compile(r"^\s*[-*]\s*\[( |~)\]\s*(.+)$")
MAX_DURUM_OKU = 200_000


def durum_maddeleri(kok: str, en_fazla: int = 2) -> list[str]:
    """DURUM.md'den once yarim ([~]) sonra acik ([ ]) maddeler; markdown isaretleri temizlenir."""
    try:
        metin = (Path(kok) / "DURUM.md").read_text(encoding="utf-8", errors="ignore")[
            :MAX_DURUM_OKU
        ]
    except OSError:
        return []
    yarim, acik = [], []
    for satir in metin.splitlines():
        m = _MADDE.match(satir)
        if m:
            temiz = re.sub(r"[*`]", "", m.group(2)).strip()
            (yarim if m.group(1) == "~" else acik).append(temiz[:160])
    return (yarim + acik)[:en_fazla]


def oneriler(
    projeler: list, isler: list[dict], zamanlamalar: list, simdi: datetime, en_fazla: int = 6
) -> list[dict]:
    """projeler: CalismaAlani (yeni once), isler: _is_ozet sozlukleri, zamanlamalar: Zamanlama,
    simdi: UTC."""

    sonuc: list[dict] = []
    for x in isler:
        if x.get("asama") in INSAN_BEKLIYOR:
            sonuc.append(
                {
                    "tur": "thread",
                    "metin": x.get("baslik", "Thread"),
                    "ayrinti": "Thread seni bekliyor",
                    "proje_kok": x.get("proje_kok", ""),
                }
            )
    for z in zamanlamalar:
        if not z.aktif or z.tamamlandi:
            continue
        try:
            an = sonraki(z, simdi)
        except ValueError:
            continue
        if an - simdi <= timedelta(hours=24):
            sonuc.append(
                {
                    "tur": "rutin",
                    "metin": z.ad,
                    "zaman": an.isoformat(),
                    "ayrinti": "Rutin 24 saat icinde calisacak",
                    "proje_kok": z.proje_kok,
                }
            )
    for p in projeler[:6]:
        if not p.kokler:
            continue
        for madde in durum_maddeleri(p.kokler[0], 1):
            sonuc.append(
                {
                    "tur": "durum",
                    "metin": madde,
                    "ayrinti": p.ad,
                    "proje_id": p.id,
                    "proje_kok": p.kokler[0],
                }
            )
    return sonuc[:en_fazla]
