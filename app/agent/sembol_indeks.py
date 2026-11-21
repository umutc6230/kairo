"""Hafif sembol indeksi ve hibrit BM25 kod arama (sifir ek bagimlilik).

Python icin `ast`, JS/TS/Go/Rust/C#/Java icin hafif duzenli ifadelerle sinif/fonksiyon/metod
tanimlarini cikarir; dosya degismedikce onbellekten servis eder. Gizli dosyalar, symlink'ler
ve `.gitignore` ile dislanan dosyalar indekslenmez.
"""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent import policy
from app.agent.dosyalar import ATLANAN, GitIgnore, KokKapsami
from app.agent.yollar import icinde_mi, kanonik
from app.exceptions import YetkiYok

MAX_INDEKS_BAYT = 1024 * 1024  # 1 MB ustu dosyalar indekslenmez
UZANTILAR = {
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".cs",
    ".java",
}

_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u00c0-\u024f]+")

# Çok dilli regex tanımları
_JS_CLASS_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"
)
_JS_FUNC_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*(\([^)]*\))"
)
_JS_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)
_JS_IFACE_RE = re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)")
_JS_TYPE_RE = re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=")

_GO_FUNC_RE = re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)\s*(\([^)]*\))")
_GO_TYPE_RE = re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+(struct|interface)\b")

_RS_FN_RE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*(\([^)]*\))"
)
_RS_TYPE_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(struct|trait|enum|type)\s+([A-Za-z_]\w*)")

_C_TYPE_RE = re.compile(
    r"^\s*(?:public|private|protected|internal|static|abstract|sealed|final|\s)+"
    r"(class|interface|struct|enum)\s+([A-Za-z_]\w*)"
)
_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*(\([^)]*\))")
_PY_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)(?:\s*(\([^)]*\)))?")


def _kucult(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def tokenle(metin: str) -> list[str]:
    """Metni camelCase, snake_case ve noktalama sinirlarindan kucuk harf tokenlara ayirir."""
    sonuc: list[str] = []
    for ham in _TOKEN_RE.findall(metin or ""):
        tam = _kucult(ham)
        if not tam:
            continue
        sonuc.append(tam)
        parcali = _CAMEL_RE.sub(r"\1 \2", ham).replace("_", " ")
        for parca in parcali.split():
            p = _kucult(parca)
            if p and p != tam:
                sonuc.append(p)
    return sonuc


@dataclass
class Sembol:
    ad: str
    tur: str  # class | function | method | interface | type | struct | trait | enum
    dosya: str
    satir: int
    bitis_satir: int
    imza: str = ""
    ozet: str = ""


def _ilk_satir_doc(node: ast.AST) -> str:
    doc = ast.get_docstring(node, clean=True) or ""  # type: ignore[arg-type]
    if not doc:
        return ""
    return doc.splitlines()[0].strip()[:120]


def _python_sembolleri(metin: str, dosya: str) -> list[Sembol]:
    try:
        agac = ast.parse(metin)
    except SyntaxError:
        return _regex_sembolleri(metin, ".py", dosya)

    sonuc: list[Sembol] = []

    def gez_govde(govde: list[ast.stmt], sinif: str = "") -> None:
        for n in govde:
            if isinstance(n, ast.ClassDef):
                ad = f"{sinif}.{n.name}" if sinif else n.name
                bazlar = ", ".join(ast.unparse(b) for b in n.bases) if n.bases else ""
                sonuc.append(
                    Sembol(
                        ad=ad,
                        tur="class",
                        dosya=dosya,
                        satir=n.lineno,
                        bitis_satir=n.end_lineno or n.lineno,
                        imza=f"({bazlar})" if bazlar else "",
                        ozet=_ilk_satir_doc(n),
                    )
                )
                gez_govde(n.body, sinif=ad)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                ad = f"{sinif}.{n.name}" if sinif else n.name
                tur = "method" if sinif else "function"
                try:
                    arglar = ast.unparse(n.args)
                except Exception:  # noqa: BLE001
                    arglar = "..."
                oneki = "async " if isinstance(n, ast.AsyncFunctionDef) else ""
                sonuc.append(
                    Sembol(
                        ad=ad,
                        tur=tur,
                        dosya=dosya,
                        satir=n.lineno,
                        bitis_satir=n.end_lineno or n.lineno,
                        imza=f"{oneki}({arglar})"[:140],
                        ozet=_ilk_satir_doc(n),
                    )
                )

    gez_govde(agac.body)
    return sonuc


def _regex_sembolleri(metin: str, uzanti: str, dosya: str) -> list[Sembol]:
    sonuc: list[Sembol] = []
    for no, satir in enumerate(metin.splitlines(), 1):
        if uzanti == ".py":
            if m := _PY_CLASS_RE.match(satir):
                sonuc.append(Sembol(m.group(1), "class", dosya, no, no, m.group(2) or ""))
            elif m := _PY_DEF_RE.match(satir):
                sonuc.append(Sembol(m.group(1), "function", dosya, no, no, m.group(2)[:140]))
        elif uzanti in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
            if m := _JS_CLASS_RE.match(satir):
                sonuc.append(Sembol(m.group(1), "class", dosya, no, no))
            elif m := _JS_IFACE_RE.match(satir):
                sonuc.append(Sembol(m.group(1), "interface", dosya, no, no))
            elif m := _JS_TYPE_RE.match(satir):
                sonuc.append(Sembol(m.group(1), "type", dosya, no, no))
            elif (m := _JS_FUNC_RE.match(satir)) or (m := _JS_ARROW_RE.match(satir)):
                sonuc.append(Sembol(m.group(1), "function", dosya, no, no, m.group(2)[:140]))
        elif uzanti == ".go":
            if m := _GO_TYPE_RE.match(satir):
                sonuc.append(Sembol(m.group(1), m.group(2), dosya, no, no))
            elif m := _GO_FUNC_RE.match(satir):
                sonuc.append(Sembol(m.group(1), "function", dosya, no, no, m.group(2)[:140]))
        elif uzanti == ".rs":
            if m := _RS_TYPE_RE.match(satir):
                sonuc.append(Sembol(m.group(2), m.group(1), dosya, no, no))
            elif m := _RS_FN_RE.match(satir):
                sonuc.append(Sembol(m.group(1), "function", dosya, no, no, m.group(2)[:140]))
        elif uzanti in {".cs", ".java"} and (m := _C_TYPE_RE.match(satir)):
            sonuc.append(Sembol(m.group(2), m.group(1), dosya, no, no))
    return sonuc


def sembolleri_cikar(dosya_yolu: Path, goreli: str) -> list[Sembol]:
    metin = dosya_yolu.read_text(encoding="utf-8", errors="replace")
    uzanti = dosya_yolu.suffix.lower()
    if uzanti == ".py":
        return _python_sembolleri(metin, goreli)
    return _regex_sembolleri(metin, uzanti, goreli)


class SembolIndeksi:
    """Yetkili kokler icinde dosya degisimi duyarli sembol indeksi ve hibrit BM25 arama."""

    def __init__(self, kapsam: KokKapsami) -> None:
        self.kapsam = kapsam
        self._onbellek: dict[Path, tuple[int, int, list[Sembol]]] = {}

    def _dosyalari_topla(self, kok: Path) -> list[tuple[Path, str]]:
        ana_kok = self.kapsam.kok_of(kok)
        yoksay = GitIgnore(ana_kok)
        dosyalar: list[tuple[Path, str]] = []
        yigin: list[Path] = [kok]
        while yigin:
            d = yigin.pop(0)
            try:
                ogeler = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except OSError:
                continue
            for p in ogeler:
                if p.is_symlink():
                    continue
                try:
                    cp = kanonik(p)
                except YetkiYok:
                    continue
                if not icinde_mi(kok, cp) or policy.hassas_mi(cp) or yoksay.yok_sayilir(p):
                    continue
                if p.name in ATLANAN:
                    continue
                if p.is_dir():
                    yigin.append(p)
                    continue
                if p.suffix.lower() not in UZANTILAR:
                    continue
                try:
                    goreli = cp.relative_to(kanonik(kok)).as_posix()
                except ValueError:
                    goreli = cp.name
                dosyalar.append((cp, goreli))
        return dosyalar

    def _indeksle(self, kok: Path) -> tuple[list[Sembol], int]:
        dosyalar = self._dosyalari_topla(kok)
        mevcut_yollar: set[Path] = set()
        tum_semboller: list[Sembol] = []
        taranan = 0

        for cp, goreli in dosyalar:
            try:
                st = cp.stat()
            except OSError:
                continue
            if st.st_size > MAX_INDEKS_BAYT:
                continue
            taranan += 1
            mevcut_yollar.add(cp)
            kayit = self._onbellek.get(cp)
            if kayit is None or kayit[0] != st.st_mtime_ns or kayit[1] != st.st_size:
                try:
                    semboller = sembolleri_cikar(cp, goreli)
                except OSError:
                    semboller = []
                self._onbellek[cp] = (st.st_mtime_ns, st.st_size, semboller)
            else:
                semboller = kayit[2]
            tum_semboller.extend(semboller)

        # Silinen/kapsam disi kalan dosyalari temizle (yalniz o kok altindakiler)
        for eski in list(self._onbellek):
            if eski not in mevcut_yollar and icinde_mi(kok, eski):
                del self._onbellek[eski]

        return tum_semboller, taranan

    def ara(self, sorgu: str, klasor: str = "", tur: str = "", limit: int = 20) -> dict[str, Any]:
        sorgu_temiz = (sorgu or "").strip()
        if not sorgu_temiz:
            return {"hata": "Arama sorgusu bos olamaz."}
        try:
            kok = self.kapsam.coz(klasor, varsayilan=".")
        except YetkiYok as e:
            return {"hata": str(e), "karar": "ret"}

        limit = max(1, min(int(limit or 20), 50))
        tur_filtre = _kucult((tur or "").strip())
        semboller, taranan = self._indeksle(kok)
        if not semboller:
            return {"sonuclar": [], "taranan_dosya": taranan, "toplam_sembol": 0}

        q_kucuk = _kucult(sorgu_temiz)
        q_tokenler = list(dict.fromkeys(tokenle(sorgu_temiz)))
        if not q_tokenler:
            q_tokenler = [q_kucuk]

        # Belge token frekanslari (alan agirlikli)
        belgeler: list[tuple[Sembol, Counter[str], int]] = []
        df: Counter[str] = Counter()
        toplam_uzunluk = 0
        for s in semboller:
            c: Counter[str] = Counter()
            for tok in tokenle(s.ad):
                c[tok] += 3
            for tok in tokenle(s.dosya):
                c[tok] += 1
            for tok in tokenle(f"{s.imza} {s.ozet}"):
                c[tok] += 1
            dl = sum(c.values()) or 1
            toplam_uzunluk += dl
            for t in c:
                df[t] += 1
            belgeler.append((s, c, dl))

        n = len(belgeler)
        avgdl = toplam_uzunluk / max(n, 1)
        k1, b = 1.5, 0.75

        eslesenler: list[tuple[float, Sembol]] = []
        for s, tf, dl in belgeler:
            if tur_filtre and _kucult(s.tur) != tur_filtre:
                continue
            puan = 0.0
            for qt in q_tokenler:
                f = tf.get(qt, 0)
                if f > 0:
                    idf = math.log(1.0 + (n - df[qt] + 0.5) / (df[qt] + 0.5))
                    puan += idf * ((f * (k1 + 1.0)) / (f + k1 * (1.0 - b + b * (dl / avgdl))))

            ad_kucuk = _kucult(s.ad)
            son_parca = ad_kucuk.rsplit(".", 1)[-1]
            if ad_kucuk == q_kucuk or son_parca == q_kucuk:
                puan += 20.0
            elif ad_kucuk.startswith(q_kucuk) or son_parca.startswith(q_kucuk):
                puan += 10.0
            elif q_kucuk in ad_kucuk:
                puan += 4.0
            if q_kucuk in _kucult(s.dosya):
                puan += 2.0

            if puan > 0:
                eslesenler.append((puan, s))

        eslesenler.sort(key=lambda item: (-item[0], item[1].dosya, item[1].satir))
        sonuclar = [
            {
                "ad": s.ad,
                "tur": s.tur,
                "dosya": s.dosya,
                "satir": s.satir,
                "bitis_satir": s.bitis_satir,
                "imza": s.imza,
                "ozet": s.ozet,
                "puan": round(puan, 3),
            }
            for puan, s in eslesenler[:limit]
        ]
        return {
            "sonuclar": sonuclar,
            "taranan_dosya": taranan,
            "toplam_sembol": len(semboller),
        }
