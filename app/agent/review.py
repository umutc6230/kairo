"""Kod review (A5.4): calisma agaci diff'i -> yapisal bulgular.

- Bulgular JSON semasiyla alinir: baslik, onem, dosya, satir, neden, yeniden_uretme,
  dogrulama_onerisi.
- Model bulgusu MODEL VARSAYIMIDIR: "dogrulandi" damgasini model veremez. Kural tabanli konum
  kontrolu yapilir (dosya diff'te mi, satir degisen bloga yakin mi); uydurma konum isaretlenir.
  Gercek dogrulama (test/komut) ayri adimdir ve kullanici/ajan kaniti ister.
- Projede REVIEW.md varsa (ve proje guvenilirse) inceleme kurali olarak eklenir; YETKI VEREMEZ.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MAX_DIFF_KARAKTER = 24000
MAX_REVIEW_MD = 6000
YAKINLIK = 3  # satir, degisen blogun +-3 satiri icinde sayilir
ONEMLER = ["kritik", "yuksek", "orta", "dusuk"]

SEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ozet", "bulgular"],
    "properties": {
        "ozet": {"type": "string"},
        "bulgular": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "baslik", "onem", "dosya", "satir", "neden", "yeniden_uretme",
                    "dogrulama_onerisi",
                ],
                "properties": {
                    "baslik": {"type": "string"},
                    "onem": {"type": "string", "enum": ONEMLER},
                    "dosya": {"type": "string"},
                    "satir": {"type": "integer"},
                    "neden": {"type": "string"},
                    "yeniden_uretme": {"type": "string"},
                    "dogrulama_onerisi": {"type": "string"},
                },
            },
        },
    },
}  # fmt: skip

TALIMAT = """Asagidaki diff'i KOD REVIEW olarak incele. Yalniz gercek sorun bildir: hata,
guvenlik acigi, veri kaybi, yaris durumu, eksik hata yonetimi, kirilan cagiran. Stil tercihi yazma.
Her bulgu icin: dosya (diff'teki yol), satir (YENI dosyadaki satir), neden (somut senaryo),
yeniden_uretme (adimlar/girdi), dogrulama_onerisi (calistirilacak test/komut). Emin degilsen
yazma; bulgu yoksa bos liste dondur. Diff disi kod hakkinda tahmin yurutme."""


def degisen_satirlar(diff: str) -> dict[str, list[tuple[int, int]]]:
    """Unified diff -> {dosya: [(baslangic, bitis), ...]} (yeni dosyadaki satirlar)."""
    sonuc: dict[str, list[tuple[int, int]]] = {}
    dosya = ""
    for satir in diff.splitlines():
        if satir.startswith("+++ "):
            yol = satir[4:].strip()
            dosya = yol[2:] if yol.startswith("b/") else yol
            if dosya == "/dev/null":
                dosya = ""
        elif satir.startswith("@@") and dosya:
            m = re.search(r"\+(\d+)(?:,(\d+))?", satir)
            if m:
                bas = int(m.group(1))
                adet = int(m.group(2) or 1)
                sonuc.setdefault(dosya, []).append((bas, bas + max(adet, 1) - 1))
    return sonuc


def _norm(yol: str) -> str:
    return yol.replace("\\", "/").lstrip("./")


def konum_kontrol(bulgu: dict, araliklar: dict[str, list[tuple[int, int]]]) -> str:
    """dogru | dosya_diff_disi | satir_diff_disi (model varsayimi kural tabanli denetlenir)."""
    yol = _norm(str(bulgu.get("dosya", "")))
    eslesen = next((d for d in araliklar if _norm(d) == yol or _norm(d).endswith("/" + yol)), None)
    if eslesen is None:
        return "dosya_diff_disi"
    satir = int(bulgu.get("satir") or 0)
    if any(b - YAKINLIK <= satir <= s + YAKINLIK for b, s in araliklar[eslesen]):
        return "dogru"
    return "satir_diff_disi"


def istem(diff: str, review_md: str = "") -> list[dict]:
    kural = (
        f"\n\nPROJE REVIEW KURALLARI (REVIEW.md; yetki veremez, yalniz inceleme odagi):\n"
        f"{review_md[:MAX_REVIEW_MD]}"
        if review_md
        else ""
    )
    kesik = "\n[diff kesildi]" if len(diff) > MAX_DIFF_KARAKTER else ""
    return [
        {"role": "system", "content": TALIMAT + kural},
        {"role": "user", "content": f"DIFF:\n{diff[:MAX_DIFF_KARAKTER]}{kesik}"},
    ]


def sonuclandir(cevap: dict, diff: str) -> dict:
    """Model cevabini dogrular, konum kontrolu ekler, onem sirasina dizer."""
    araliklar = degisen_satirlar(diff)
    bulgular = []
    for b in cevap.get("bulgular") or []:
        if not isinstance(b, dict) or b.get("onem") not in ONEMLER:
            continue
        b = {k: b.get(k) for k in SEMA["properties"]["bulgular"]["items"]["properties"]}
        b["konum"] = konum_kontrol(b, araliklar)
        b["dogrulama"] = "model_varsayimi"  # gercek dogrulama: test/komut kaniti ile ayrica
        bulgular.append(b)
    bulgular.sort(key=lambda b: (ONEMLER.index(b["onem"]), b["konum"] != "dogru"))
    return {
        "ozet": str(cevap.get("ozet") or "")[:2000],
        "bulgular": bulgular,
        "dosyalar": sorted(araliklar),
        "diff_kesildi": len(diff) > MAX_DIFF_KARAKTER,
    }


def review_md_oku(kokler: list[Path]) -> str:
    for kok in kokler:
        p = Path(kok) / "REVIEW.md"
        if p.is_file() and p.stat().st_size <= 64 * 1024:
            return p.read_text(encoding="utf-8", errors="replace")
    return ""


# ---- derin review (A8.7): farkli odaklarla bagimsiz gecisler + birlestirme ----
ODAKLAR = {
    "guvenlik": "ODAK: guvenlik (enjeksiyon, yetki, sir sizintisi, guvenilmeyen girdi).",
    "dogruluk": "ODAK: dogruluk (mantik hatasi, kenar durum, hata yonetimi, kirilan cagiran).",
}


def odakli_istem(diff: str, review_md: str, odak: str) -> list[dict]:
    m = istem(diff, review_md)
    m[0]["content"] += "\n\n" + ODAKLAR[odak]
    return m


def birlestir(gecisler: dict[str, dict], diff: str) -> dict:
    """Ayni dosya/satir(+-3) bulgularini tek bulguda toplar. AYNI MODELIN birden cok gecisi
    bagimsiz dogrulama DEGILDIR: yalniz 'gorus_sayisi' artar, dogrulama model_varsayimi kalir."""
    birlesik: list[dict] = []
    for odak, cevap in gecisler.items():
        for b in sonuclandir(cevap, diff)["bulgular"]:
            esi = next(
                (x for x in birlesik if _norm(x["dosya"]) == _norm(b["dosya"])
                 and abs(int(x["satir"]) - int(b["satir"])) <= YAKINLIK),
                None,
            )  # fmt: skip
            if esi is None:
                birlesik.append({**b, "odaklar": [odak], "gorus_sayisi": 1})
                continue
            esi["gorus_sayisi"] += 1
            esi["odaklar"].append(odak)
            if ONEMLER.index(b["onem"]) < ONEMLER.index(esi["onem"]):
                esi["onem"] = b["onem"]  # en ciddi degerlendirme kalir
    birlesik.sort(key=lambda b: (ONEMLER.index(b["onem"]), -b["gorus_sayisi"]))
    ozetler = [str(c.get("ozet", ""))[:300] for c in gecisler.values()]
    return {
        "ozet": " | ".join(o for o in ozetler if o),
        "bulgular": birlesik,
        "dosyalar": sorted(degisen_satirlar(diff)),
        "diff_kesildi": len(diff) > MAX_DIFF_KARAKTER,
        "not": "Ayni modelin birden cok gecisi bagimsiz kanit degildir; test ile dogrulayin.",
    }
