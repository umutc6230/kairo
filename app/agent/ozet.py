"""Ajan baglaminin ozetlenmesi (A4.3).

Ozet MODELE YAZDIRILMAZ: Run'in kayitli durumundan (hedef, kabul, plan, adimlar, kullanici
mesajlari) kural tabanli uretilir. Boylece "bozuk ozet" riski yoktur; yine de uretilen ozet
dogrulanir ve gecersizse eski baglam KORUNUR. Cikarilan mesajlar silinmez, arsiv dosyasina yazilir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.yetenek import tahmini_token

OZET_ETIKETI = "[BAGLAM OZETI]"
ESIK = 0.70  # mesajlar baglamin %70'ini gecince ozetle
KUYRUK_PAYI = 0.35  # son mesajlara ayrilan pay (ham haliyle kalir)
MAX_ADIM_SATIRI = 40


def _js(x: object) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


def mesaj_token(mesajlar: list[dict]) -> int:
    return sum(tahmini_token(_js(m)) for m in mesajlar)


def ozet_metni(run: Any) -> str:
    """Hedef, kisitlar, plan, tamamlanan adimlar, dosya/hash, acik hatalar, sonraki eylem."""
    satirlar = [OZET_ETIKETI, f"HEDEF: {run.hedef}"]
    if run.kabul:
        satirlar.append("KABUL KOSULLARI: " + "; ".join(run.kabul))
    kisitlar = [
        g.removeprefix("Kullanici: ") for g in run.guncellemeler if g.startswith("Kullanici:")
    ]
    if kisitlar:
        satirlar.append("KULLANICI KISITLARI/YONLENDIRMELERI:")
        satirlar += [f"- {k}" for k in kisitlar]
    if run.plan:
        satirlar.append("PLAN:")
        satirlar += [
            f"- [{p.durum}] {p.baslik}" + (f" (kanit: {p.kanit})" if p.kanit else "")
            for p in run.plan
        ]
    gercek = [a for a in run.adimlar if a.arac not in ("plan_guncelle",)]
    if gercek:
        satirlar.append(f"YAPILAN ADIMLAR (son {MAX_ADIM_SATIRI}):")
        for a in gercek[-MAX_ADIM_SATIRI:]:
            arg = ", ".join(f"{k}={str(v)[:40]}" for k, v in a.argumanlar.items() if k != "icerik")
            kod = f" cikis={a.cikis_kodu}" if a.cikis_kodu is not None else ""
            satirlar.append(f"- adim {a.no}: {a.arac}({arg}) -> {a.durum}{kod}")
    dosyalar: dict[str, str] = {}
    for a in run.adimlar:
        if a.dosya and a.hash and a.durum == "tamam":
            dosyalar[a.dosya] = f"{a.hash} (adim {a.no})"
    if dosyalar:
        satirlar.append(
            "DOSYA/HASH REFERANSLARI (ESKI olabilir; yazmadan once "
            "proje_dosya_oku ile yeniden oku):"
        )
        satirlar += [f"- {y}: {h}" for y, h in dosyalar.items()]
    hatalar = [a for a in run.adimlar if a.durum in ("hata", "reddedildi")][-5:]
    if hatalar:
        satirlar.append("ACIK HATALAR / REDLER:")
        satirlar += [f"- adim {a.no} {a.arac}: {a.sonuc[:160]}" for a in hatalar]
    sonraki = next((p.baslik for p in run.plan if p.durum not in ("tamam", "atlandi")), "")
    satirlar.append(
        f"SONRAKI EYLEM: {sonraki or 'plana bak, gerekirse plan_guncelle ile guncelle'}"
    )
    return "\n".join(satirlar)


def _gecerli(ozet: str, run: Any) -> bool:
    return ozet.startswith(OZET_ETIKETI) and run.hedef[:50] in ozet and "SONRAKI EYLEM" in ozet


def _kesim_noktasi(mesajlar: list[dict], kuyruk_sinir: int) -> int:
    """Son mesajlardan kuyruk_sinir'a sigan en uzun parcanin baslangici. Kesim bir assistant
    mesajinda olmali: tool_call / tool sonucu cifti bolunmez."""
    toplam = 0
    kesim = len(mesajlar)
    for i in range(len(mesajlar) - 1, 0, -1):
        toplam += tahmini_token(_js(mesajlar[i]))
        if toplam > kuyruk_sinir:
            break
        if mesajlar[i].get("role") in ("assistant", "user"):
            kesim = i
    return kesim


def ozetle_gerekirse(run: Any, baglam_mesaj_siniri: int, arsiv: Path) -> bool:
    """Mesajlar siniri asiyorsa: [GOREV, OZET, son mesajlar]. Ozetlendiyse True."""
    if mesaj_token(run.mesajlar) <= baglam_mesaj_siniri * ESIK or len(run.mesajlar) < 4:
        return False
    bas = 1  # mesajlar[0] = GOREV mesaji, daima kalir
    if len(run.mesajlar) > 1 and str(run.mesajlar[1].get("content", "")).startswith(OZET_ETIKETI):
        bas = 2  # eski ozet yenisiyle degisecek
    kesim = _kesim_noktasi(run.mesajlar, int(baglam_mesaj_siniri * KUYRUK_PAYI))
    if kesim <= bas:
        return False  # tek bir dev mesaj: ozetle cozulmez (arac sonucu kisaltma ayri)
    ozet = ozet_metni(run)
    if not _gecerli(ozet, run):
        return False  # bozuk ozet eski saglam baglamin yerine GECMEZ
    arsiv.parent.mkdir(parents=True, exist_ok=True)
    with arsiv.open("a", encoding="utf-8") as f:  # cikarilanlar kaybolmaz
        for m in run.mesajlar[1:kesim]:
            f.write(_js(m) + "\n")
    run.mesajlar = [run.mesajlar[0], {"role": "user", "content": ozet}, *run.mesajlar[kesim:]]
    return True
