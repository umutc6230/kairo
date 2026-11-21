"""Sohbet ici gorsel araclar: mini arayuz (arayuz_goster) ve sunucu onizlemesi (onizleme_baslat).

GUVENLIK: arayuz HTML'i istemcide YALNIZ <iframe sandbox="allow-scripts" srcdoc> + kisitli CSP
ile calisir (inceleme.onizlemeSrcdoc); burada yalniz boyut/bicim denetlenir. Onizleme sunucusu
komut_calistir uzerinden baslar (politika/onay aynen gecerli) ve adres yalniz localhost olur.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from typing import Any

MAX_ARAYUZ_BAYT = 200_000
ONIZLEME_BEKLEME_SN = 60
ONIZLEME_TIMEOUT_SN = 900  # shortcut: komut servisi siniri (MAX_TIMEOUT); uzun oturum icin artir


def _fonk(ad: str, aciklama: str, ozellikler: dict, zorunlu: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": ad,
            "description": aciklama,
            "parameters": {"type": "object", "properties": ozellikler, "required": zorunlu},
        },
    }


S = {"type": "string"}

ARAYUZ_ARACI = _fonk(
    "arayuz_goster",
    "Sohbetin icinde kucuk, etkilesimli bir arayuz gosterir (panel, grafik, tablo, hesaplayici, "
    "sistem monitoru). `html`: tek parca HTML; CSS <style>, JS <script> icinde. Ag erisimi YOK "
    "(fetch, dis CDN, dis resim calismaz): veriyi once araclarla topla, HTML'e gom. Koyu zemine "
    "uygun renk kullan. `baslik`: 2-4 kelime. CANLI VERI: kartta `await kairo.komut('komut')` "
    "bir komut calistirir (kullanici her seferinde onaylar, izin kurallari gecerli) ve "
    "{ok, cikti, cikis_kodu, hata} doner; 'Yenile' gibi dugmeyle guncel veriyi bununla cek, "
    "cikti'yi ayristirip karti guncelle. Komut sabit olsun, kullanici girdisini komuta katma.",
    {"baslik": S, "html": S},
    ["baslik", "html"],
)

ONIZLEME_ARACI = _fonk(
    "onizleme_baslat",
    "Projenin dev sunucusunu arka planda baslatir ve port acilinca sohbette canli onizleme "
    "gosterir (Claude preview gibi). `komut`: or. 'npm run dev' ya da 'python -m http.server "
    "8000'; `port`: sunucunun dinledigi port; `yol`: acilacak sayfa (varsayilan /). Sunucu "
    "zaten aciksa komut bos birakilabilir. Sunucu en fazla 15 dk calisir.",
    {"komut": S, "port": {"type": "integer"}, "klasor": S, "yol": S, "aciklama": S},
    ["port"],
)

ARAYUZ_DESENI = (
    r"aray[uü]z|panel|dashboard|pano|grafik|chart|monit[oö]r|widget|g[oö]rselle[sş]tir|"
    r"interaktif|etkile[sş]imli|hesap ?makinesi|tablo (olarak )?g[oö]ster|mini uygulama|kart"
)
ONIZLEME_DESENI = (
    r"[oö]nizle|preview|dev server|localhost|sunucuyu? (a[cç]|ba[sş]lat|[cç]al[iı][sş]t[iı]r)|"
    r"uygulamay[iı] [cç]al[iı][sş]t[iı]r|siteyi (a[cç]|g[oö]ster)"
)


def arayuz_goster(baslik: str = "", html: str = "") -> dict:
    """Kart istemcide arguman HTML'inden cizilir; burada yalniz denetim ve kisa sonuc."""
    if not html.strip():
        return {"hata": "html bos."}
    boyut = len(html.encode("utf-8"))
    if boyut > MAX_ARAYUZ_BAYT:
        return {"hata": f"html {boyut} bayt; en fazla {MAX_ARAYUZ_BAYT}. Daha kisa yaz."}
    return {"gosterildi": True, "baslik": baslik[:80], "boyut": boyut}


def port_acik(port: int, host: str = "127.0.0.1", sure: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=sure):
            return True
    except OSError:
        return False


def onizleme_isleyici(
    komut_calistir: Callable[..., dict] | None,
    komut_durumu: Callable[..., dict] | None,
    bekleme_sn: float = ONIZLEME_BEKLEME_SN,
) -> Callable[..., dict]:
    def onizleme_baslat(
        port: int, komut: str = "", klasor: str = "", yol: str = "/", aciklama: str = ""
    ) -> dict:
        try:
            port = int(port)
        except (TypeError, ValueError):
            return {"hata": "port sayi olmali."}
        if not 1 <= port <= 65535:
            return {"hata": "port 1-65535 araliginda olmali."}
        yol = "/" + (yol or "").lstrip("/")
        url = f"http://localhost:{port}{yol}"
        if port_acik(port):
            if komut.strip():  # canli testte bulundu: port baska uygulamadaydi, o gosteriliyordu
                return {
                    "hata": f"{port} portu baska bir surecte kullaniliyor; sunucu baslatilmadi. "
                    "Bos bir port sec ya da mevcut sunucu icin komutu bos birak."
                }
            return {"url": url, "is_id": "", "not": "Port zaten acik; mevcut sunucu gosteriliyor."}
        if not komut.strip():
            return {"hata": f"{port} portunda calisan sunucu yok; `komut` ver."}
        if komut_calistir is None:
            return {"hata": "Komut calistirma bu sohbette kapali (proje ac ya da yetki ver)."}
        r = komut_calistir(
            komut=komut,
            klasor=klasor,
            arka_plan=True,
            timeout=ONIZLEME_TIMEOUT_SN,
            aciklama=aciklama or "Onizleme sunucusunu baslat",
        )
        if not isinstance(r, dict) or "hata" in r:
            return r if isinstance(r, dict) else {"hata": str(r)}
        is_id = r.get("id", "")
        son = time.monotonic() + bekleme_sn
        while time.monotonic() < son:
            if port_acik(port):
                return {"url": url, "is_id": is_id, "not": "Onizleme hazir."}
            d = komut_durumu(is_id=is_id) if komut_durumu and is_id else {}
            if d.get("durum") not in (None, "calisiyor"):  # sunucu port acmadan kapandi
                return {"hata": "Sunucu port acmadan kapandi.", "cikti": d.get("cikti", "")[-2000:]}
            time.sleep(0.5)
        d = komut_durumu(is_id=is_id) if komut_durumu and is_id else {}
        return {
            "hata": f"{bekleme_sn:.0f} sn icinde {port} portu acilmadi; port dogru mu?",
            "is_id": is_id,
            "cikti": d.get("cikti", "")[-2000:],
        }

    return onizleme_baslat


def isleyiciler(isleyici_tablosu: dict[str, Any]) -> dict[str, Any]:
    return {
        "arayuz_goster": arayuz_goster,
        "onizleme_baslat": onizleme_isleyici(
            isleyici_tablosu.get("komut_calistir"), isleyici_tablosu.get("komut_durumu")
        ),
    }
