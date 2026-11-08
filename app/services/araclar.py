"""Arac cagirma testi icin demo araclar. Hepsi cevrimdisi ve zararsiz; kur/hava verisi SABIT
ornek veridir (gercek degil), amac modelin araci dogru secip dogru argumanla cagirmasini gormek."""

from __future__ import annotations

import ast
import operator
from datetime import datetime
from typing import Any

DEMO_KURLAR = {"USD": 41.2, "EUR": 47.8, "GBP": 54.9, "CHF": 51.3, "JPY": 0.27, "TRY": 1.0}
DEMO_HAVA = {
    "istanbul": (18, "parcali bulutlu"),
    "ankara": (12, "gunesli"),
    "izmir": (22, "gunesli"),
    "malatya": (14, "acik"),
    "antalya": (24, "gunesli"),
}

_ISLEMLER = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _hesapla(dugum: ast.AST) -> float:
    if isinstance(dugum, ast.Expression):
        return _hesapla(dugum.body)
    if isinstance(dugum, ast.Constant) and isinstance(dugum.value, int | float):
        return dugum.value
    if isinstance(dugum, ast.BinOp) and type(dugum.op) in _ISLEMLER:
        sol, sag = _hesapla(dugum.left), _hesapla(dugum.right)
        if isinstance(dugum.op, ast.Pow) and abs(sag) > 100:
            raise ValueError("Us cok buyuk")
        return _ISLEMLER[type(dugum.op)](sol, sag)
    if isinstance(dugum, ast.UnaryOp) and type(dugum.op) in _ISLEMLER:
        return _ISLEMLER[type(dugum.op)](_hesapla(dugum.operand))
    raise ValueError("Yalniz sayi ve + - * / ** % kullanilabilir")


def hesapla(ifade: str) -> dict:
    temiz = ifade.replace(",", ".").replace("x", "*").replace("×", "*").strip()
    try:
        sonuc = _hesapla(ast.parse(temiz, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError) as e:
        return {"hata": f"Hesaplanamadi: {e}"}
    return {"ifade": ifade, "sonuc": round(sonuc, 6)}


def kur_getir(para_birimi: str) -> dict:
    kod = para_birimi.strip().upper()
    if kod not in DEMO_KURLAR:
        return {"hata": f"Bilinmeyen para birimi: {kod}", "bilinenler": list(DEMO_KURLAR)}
    return {"para_birimi": kod, "tl_karsiligi": DEMO_KURLAR[kod], "not": "demo sabit kur"}


def hava_durumu(sehir: str) -> dict:
    anahtar = sehir.strip().translate(str.maketrans("İIıŞşÇçĞğÖöÜü", "iiissccggoouu")).lower()
    derece, durum = DEMO_HAVA.get(anahtar, (16, "bilinmiyor (demo)"))
    return {"sehir": sehir, "derece_c": derece, "durum": durum, "not": "demo veri"}


def saat_kac() -> dict:
    an = datetime.now()
    return {
        "tarih": an.strftime("%Y-%m-%d"),
        "saat": an.strftime("%H:%M"),
        "gun": an.strftime("%A"),
    }


def birim_cevir(deger: float, kaynak: str, hedef: str) -> dict:
    oranlar = {("km", "mil"): 0.621371, ("mil", "km"): 1.609344, ("kg", "lb"): 2.204623,
               ("lb", "kg"): 0.453592, ("m", "ft"): 3.28084, ("ft", "m"): 0.3048}  # fmt: skip
    k, h = kaynak.strip().lower(), hedef.strip().lower()
    if (k, h) == ("c", "f"):
        return {"sonuc": round(float(deger) * 9 / 5 + 32, 4), "birim": "F"}
    if (k, h) == ("f", "c"):
        return {"sonuc": round((float(deger) - 32) * 5 / 9, 4), "birim": "C"}
    if (k, h) not in oranlar:
        return {"hata": f"Desteklenmeyen donusum: {k} -> {h}"}
    return {"sonuc": round(float(deger) * oranlar[(k, h)], 4), "birim": h}


def _fonk(ad: str, aciklama: str, ozellikler: dict, zorunlu: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": ad,
            "description": aciklama,
            "parameters": {"type": "object", "properties": ozellikler, "required": zorunlu},
        },
    }


ARACLAR: list[dict] = [
    _fonk(
        "kur_getir",
        "Bir para biriminin TL karsiligini verir (demo sabit kur).",
        {"para_birimi": {"type": "string", "description": "USD, EUR, GBP, CHF, JPY"}},
        ["para_birimi"],
    ),
    _fonk(
        "hesapla",
        "Aritmetik ifadeyi hesaplar. Ornek: 1250*41.2",
        {"ifade": {"type": "string"}},
        ["ifade"],
    ),
    _fonk(
        "hava_durumu",
        "Bir sehrin hava durumunu verir (demo veri).",
        {"sehir": {"type": "string"}},
        ["sehir"],
    ),
    _fonk("saat_kac", "Bu bilgisayarin tarih ve saatini verir.", {}, []),
    _fonk(
        "birim_cevir",
        "Birim cevirir: km-mil, kg-lb, m-ft, c-f.",
        {
            "deger": {"type": "number"},
            "kaynak": {"type": "string"},
            "hedef": {"type": "string"},
        },
        ["deger", "kaynak", "hedef"],
    ),
]
ISLEYICILER: dict[str, Any] = {
    "kur_getir": kur_getir,
    "hesapla": hesapla,
    "hava_durumu": hava_durumu,
    "saat_kac": saat_kac,
    "birim_cevir": birim_cevir,
}
ORNEK_ISTEMLER = [
    "1250 dolar kac TL eder? Kuru aracla ogren, hesabi da aracla yap.",
    "Malatya'da hava nasil ve su an saat kac?",
    "42 km kac mil? 30 derece C kac F?",
    "500 euro ile 300 sterlinin toplami kac TL?",
]
