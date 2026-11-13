"""Kairo ve Claude Code degerlendirme raporlarini yan yana karsilastirir.

Kullanim: python degerlendirme/karsilastir.py <cikti.md> --yerel R1.json [R2.json ...] --cc RCC.json
Yerel tarafta verilen TUM raporlarin TUM kosulari birlikte sayilir (yalniz iyi kosular secilmez);
saglayici kotasi / harness hatasi olan kosular basari oranina girmez, ayri gosterilir.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.degerlendir import OLCULEMEDI, gorevleri_yukle, ozet_tablo  # noqa: E402

KAT = {"hata": "Hata duzeltme", "ozellik": "Ozellik/refactor", "test": "Test/build",
       "kesif": "Kesif/review", "uzun": "Uzun baglam/devam", "toparlanma": "Toparlanma",
       "entegrasyon": "Web/entegrasyon"}  # fmt: skip


def _ort_sure(liste: list[dict]) -> float:
    return round(sum(k["sure_sn"] for k in liste) / max(len(liste), 1), 1)


def rapor(yerel_r: list[dict], cc: dict) -> str:
    yerel = [k for r in yerel_r for k in r["kosular"]]
    oy, oc = ozet_tablo(yerel), cc["ozet"]
    ortam = yerel_r[0]["surumler"]["ortam"]
    _, gorevler = gorevleri_yukle()
    yg: dict[str, list[dict]] = defaultdict(list)
    for k in yerel:
        if k["ajan_durumu"] not in OLCULEMEDI:
            yg[k["gorev"]].append(k)
    cg = {k["gorev"]: k for k in cc["kosular"]}
    olculen = [k for k in yerel if k["ajan_durumu"] not in OLCULEMEDI]
    s = [
        f"# Kairo ajan vs Claude Code: olculmus karsilastirma ({cc['zaman'][:8]})", "",
        "Gorev seti `degerlendirme/gorevler.py` (30 gorev; Python, TypeScript, JavaScript, C#).",
        "Basari = modelin gormedigi gizli kontroller; gorunur testler degerlendirmeden once",
        "orijinaline geri yuklenir. Ayni hedef metni, adim siniri ve 600 sn sure siniri.", "",
        "## Kosullar", "", "| | Kairo | Claude Code |", "|---|---|---|",
        f"| Model | `{yerel_r[0]['surumler']['model']}` ({yerel_r[0]['surumler']['saglayici']}) "
        f"| `{cc['surumler']['model']}` |",
        f"| Surum | `feature/ajan-katmani` | {cc['surumler']['uygulama']} |",
        f"| Kosu | {len(yerel)} ({oy['kosu']} olculen) | {len(cc['kosular'])} (gorev basina 1) |",
        "| Izinler | otomatik mod; onaylar harness tarafindan verildi ve SAYILDI | "
        "acceptEdits + Bash/Read/Edit/Write/Glob/Grep on-izinli |",
        f"| Istemci donanimi | {ortam.get('cpu')}, {ortam.get('ram_gb')} GB | ayni makine |", "",
        "## Sonuc", "", "| Olcut | Kairo | Claude Code |", "|---|---|---|",
        f"| Basari (olculen kosular) | **%{oy['basari_yuzde']}** ({oy['kosu']}) "
        f"| **%{oc['basari_yuzde']}** ({oc['kosu']}) |",
        f"| Yanlis basari beyani | {oy['yanlis_basari_beyani']} | {oc['yanlis_basari_beyani']} |",
        f"| Kullanici mudahalesi (onay) | {oy['mudahale_toplam']} | 0 (on-izinli) |",
        f"| Ortalama sure / kosu | {_ort_sure(olculen)} sn | {_ort_sure(cc['kosular'])} sn |",
        f"| Maliyet | 0 $ (ucretsiz model) | {oc.get('toplam_maliyet_usd', '?')} $ |",
        f"| Olculemedi | {oy['olculemedi']} (kota/harness) | {oc.get('olculemedi', 0)} |", "",
        "## Kategori", "", "| Kategori | Kairo | Claude Code | Fark (puan) |",
        "|---|---|---|---|",
    ]  # fmt: skip
    gerileyen = []
    for c, ad in KAT.items():
        y, k = oy["kategori"].get(c, {}), oc["kategori"].get(c, {})
        fark = round(y.get("basari_yuzde", 0) - k.get("basari_yuzde", 0), 1)
        if fark < 0:
            gerileyen.append(ad)
        s.append(f"| {ad} | %{y.get('basari_yuzde', '-')} ({y.get('kosu', 0)}) "
                 f"| %{k.get('basari_yuzde', '-')} ({k.get('kosu', 0)}) | {fark:+} |")  # fmt: skip
    s += ["", "## Gorev bazinda", "",
          "| Gorev | Yerel (gecen/olculen) | Claude Code | Yerel ort. sn | CC sn |",
          "|---|---|---|---|---|"]  # fmt: skip
    for g in gorevler:
        liste, c = yg[g["id"]], cg.get(g["id"])
        s.append(f"| {g['id']} | {sum(k['basari'] for k in liste)}/{len(liste)} | "
                 f"{'GECTI' if c and c['basari'] else 'KALDI'} | {_ort_sure(liste)} | "
                 f"{c['sure_sn'] if c else '-'} |")  # fmt: skip
    fark = round(oy["basari_yuzde"] - oc["basari_yuzde"], 1)
    s += [
        "", "## Degerlendirme", "",
        f"- Genel fark **{fark:+} puan**. Onceden belirlenen esdegerlik olcutu (fark <= 5 puan ve",
        "  kritik kategoride gerileme yok) **SAGLANMADI**. Gerileyen kategoriler: "
        f"{', '.join(gerileyen) or 'yok'}.",
        "- Fark urun ile modelin TOPLAMIDIR (farkli modeller). Ayni guclu modelle Kairo",
        "  olculmeden farkin urun payi AYRISTIRILAMAZ.",
        f"- Yerel ilk surum kapisi (>= %80): {'GECTI' if oy['basari_yuzde'] >= 80 else 'GECMEDI'}"
        f" (%{oy['basari_yuzde']}). Yanlis basari beyani {oy['yanlis_basari_beyani']} kosu.",
        "- Belirsizlik: Claude Code gorev basina 1 kosu; %100 tavan etkisi (set onun icin kolay).",
        "  Ayirt edici olcum icin daha zor gorevlerle set buyutulmeli.",
        f"- Kararsiz yerel gorevler: {', '.join(oy['kararsiz_gorevler']) or 'yok'}.",
        "", "Ham veri: `degerlendirme/raporlar/` (yerelde; git'e eklenmez).",
    ]  # fmt: skip
    return "\n".join(s) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cikti")
    p.add_argument("--yerel", nargs="+", required=True)
    p.add_argument("--cc", required=True)
    a = p.parse_args()
    yerel = [json.loads(Path(y).read_text(encoding="utf-8")) for y in a.yerel]
    cc = json.loads(Path(a.cc).read_text(encoding="utf-8"))
    Path(a.cikti).write_text(rapor(yerel, cc), encoding="utf-8")
    print(a.cikti)


if __name__ == "__main__":
    main()
