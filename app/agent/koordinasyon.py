"""Oturumlar arasi koordinasyon (Claude Code gibi): ayni projede ayni anda calisan sohbetler ve
ajan gorevleri birbirini gorur, ayni dosyaya ayni anda yazmaz, mesajlasir, bekler, is devreder.

- Proje anahtari calisma alani id'sidir. Pano bellektedir: kiralar kisa omurludur, uygulama
  yeniden acilinca bos baslamak dogrudur (calisan is kalmaz).
- Katilimci kimligi: ajan gorevi "gorev:<run_id>" (AKTIF_RUN), sohbet turu "oturum:<id>".
- Dosya sahiplenme YUMUSAK kilittir: yazma aracindan once alinir, sahibi ayni dosyaya tekrar
  yazabilir; baskasi yazmak isterse yazma reddedilir ve ne yapacagi soylenir. Asil koruma yine
  hash kontroludur (yazma.py); bu katman cakismayi yazmadan ONCE fark ettirir.
- Kiralar KIRA_SN sonra duser (coken/unutulan katilimci kilit birakmaz).
"""

from __future__ import annotations

import contextvars
import threading
import time
from dataclasses import dataclass, field

from app.exceptions import UygulamaHatasi

KIRA_SN = 600
EN_FAZLA_BEKLE = 300
AKTIF_OTURUM: contextvars.ContextVar[str] = contextvars.ContextVar("koord_oturum", default="")


def kimlik() -> str:
    """Bu is parcacigindaki aracin sahibi. Ajan gorevi onceliklidir (gorev sohbetten acilir)."""
    from app.agent.terminal import AKTIF_RUN

    run = AKTIF_RUN.get()
    if run:
        return f"gorev:{run}"
    o = AKTIF_OTURUM.get()
    return f"oturum:{o}" if o else ""


class DosyaMesgul(UygulamaHatasi):
    """Baska bir oturum/gorev bu dosyayi sahiplenmis."""


@dataclass
class Katilimci:
    kimlik: str
    proje: str
    ad: str
    son: float
    dosyalar: dict[str, float] = field(default_factory=dict)  # goreli yol -> kira bitisi
    bekliyor: str = ""  # dosya_bekle ile beklenen dosya (arayuz gosterir)


@dataclass
class Mesaj:
    kimden: str
    kimden_ad: str
    kime: str
    metin: str
    tur: str = "mesaj"  # mesaj | devir
    zaman: float = field(default_factory=time.time)


class Koordinasyon:
    def __init__(self, saat=time.time) -> None:
        self.saat = saat
        self._k: dict[str, Katilimci] = {}
        self._kutu: list[Mesaj] = []
        self._kosul = threading.Condition()

    # ---- ic ----
    def _temizle(self) -> None:
        simdi = self.saat()
        for kid, k in list(self._k.items()):
            k.dosyalar = {y: b for y, b in k.dosyalar.items() if b > simdi}
            if k.son + KIRA_SN < simdi:
                del self._k[kid]

    def _sahip(self, proje: str, yol: str, haric: str) -> Katilimci | None:
        for k in self._k.values():
            if k.proje == proje and k.kimlik != haric and yol in k.dosyalar:
                return k
        return None

    # ---- kayit ----
    def kaydol(self, kid: str, proje: str, ad: str) -> None:
        if not kid or not proje:
            return
        with self._kosul:
            k = self._k.get(kid)
            if k is None or k.proje != proje:
                self._k[kid] = Katilimci(kid, proje, ad[:120], self.saat())
            else:
                k.son = self.saat()
                k.ad = ad[:120] or k.ad

    def ayril(self, kid: str) -> None:
        """Tur/gorev bitti: dosyalarini birakir (bekleyenler uyanir)."""
        with self._kosul:
            self._k.pop(kid, None)
            self._kosul.notify_all()

    # ---- dosya ----
    def sahiplen(self, kid: str, proje: str, yol: str, ad: str = "") -> None:
        if not kid or not proje:
            return  # arayuzden dogrudan yapilan islem: koordinasyon disi
        with self._kosul:
            self._temizle()
            diger = self._sahip(proje, yol, kid)
            if diger is not None:
                raise DosyaMesgul(
                    f"'{diger.ad}' ({diger.kimlik}) su an {yol} dosyasinda calisiyor. Yazma "
                    "yapilmadi. Secenekler: dosya_bekle ile serbest kalmasini bekle, "
                    "oturuma_mesaj ile sor, isi_devret ile ona birak ya da baska dosyayla devam et."
                )
            k = self._k.get(kid)
            if k is None or k.proje != proje:
                k = self._k[kid] = Katilimci(kid, proje, ad[:120] or kid, self.saat())
            k.son = self.saat()
            k.dosyalar[yol] = self.saat() + KIRA_SN

    def bekle(self, kid: str, proje: str, yol: str, sure: float) -> dict:
        """Dosya serbest kalana ya da sure dolana kadar bekler (en fazla EN_FAZLA_BEKLE sn)."""
        bitis = time.monotonic() + max(1.0, min(float(sure), EN_FAZLA_BEKLE))
        with self._kosul:
            if kid in self._k:
                self._k[kid].bekliyor = yol
            try:
                while True:
                    self._temizle()
                    diger = self._sahip(proje, yol, kid)
                    if diger is None:
                        return {"serbest": True, "dosya": yol}
                    kalan = bitis - time.monotonic()
                    if kalan <= 0:
                        return {"serbest": False, "dosya": yol, "sahip": diger.ad}
                    self._kosul.wait(timeout=min(kalan, 5.0))
            finally:
                if kid in self._k:
                    self._k[kid].bekliyor = ""

    # ---- mesaj ----
    def mesaj(self, kid: str, kime: str, metin: str, tur: str = "mesaj") -> dict:
        metin = metin.strip()[:4000]
        if not metin:
            raise UygulamaHatasi("Bos mesaj gonderilemez.")
        with self._kosul:
            self._temizle()
            if kime not in self._k:
                raise UygulamaHatasi(
                    f"'{kime}' aktif degil; oturumlari_gor ile guncel listeye bak."
                )
            ad = self._k[kid].ad if kid in self._k else (kid or "kullanici")
            self._kutu.append(Mesaj(kid, ad, kime, metin, tur))
        return {"gonderildi": True, "kime": kime}

    def teslim_al(self, kid: str) -> list[Mesaj]:
        with self._kosul:
            gelen = [m for m in self._kutu if m.kime == kid]
            self._kutu = [m for m in self._kutu if m.kime != kid]
            return gelen

    # ---- gorunum ----
    def aktifler(self, proje: str, haric: str = "") -> list[dict]:
        with self._kosul:
            self._temizle()
            return [
                {"kimlik": k.kimlik, "ad": k.ad, "dosyalar": sorted(k.dosyalar),
                 "bekliyor": k.bekliyor,
                 "gelen": sum(1 for m in self._kutu if m.kime == k.kimlik)}
                for k in self._k.values() if k.proje == proje and k.kimlik != haric
            ]  # fmt: skip

    def sistem_notu(self, kid: str, proje: str) -> str:
        """Model icin: projedeki diger aktif oturumlar + bu katilimciya gelen mesajlar."""
        diger = self.aktifler(proje, haric=kid)
        gelen = self.teslim_al(kid) if kid else []
        if not diger and not gelen:
            return ""
        satir = ["\n\n## Ayni projede calisan diger oturumlar"]
        for d in diger:
            dosya = ", ".join(d["dosyalar"][:6]) or "henuz dosya yazmadi"
            satir.append(f"- {d['ad']} ({d['kimlik']}): {dosya}")
        if diger:
            satir.append(
                "Onlarin dosyalarina yazma; benzer bir isse once oturuma_mesaj ile sor. Cakismada "
                "dosya_bekle / isi_devret kullan."
            )
        for m in gelen:
            etiket = "IS DEVRI" if m.tur == "devir" else "Mesaj"
            satir.append(f"\n{etiket} - {m.kimden_ad} ({m.kimden}): {m.metin}")
        return "\n".join(satir)


KOORD = Koordinasyon()


def _f(ad: str, aciklama: str, ozellikler: dict, zorunlu: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": ad,
            "description": aciklama,
            "parameters": {"type": "object", "properties": ozellikler, "required": zorunlu},
        },
    }


SEMALAR = [
    _f(
        "oturumlari_gor",
        "Ayni projede su an calisan diger sohbet/gorevleri ve yazdiklari dosyalari listeler.",
        {},
        [],
    ),  # fmt: skip
    _f(
        "oturuma_mesaj",
        "Projedeki baska bir oturuma/goreve mesaj gonderir (soru, uyari, "
        "koordinasyon). Cevap beklemek zorunda degilsin.",
        {
            "kime": {"type": "string", "description": "oturumlari_gor'daki kimlik"},
            "metin": {"type": "string"},
        },
        ["kime", "metin"],
    ),  # fmt: skip
    _f(
        "dosya_bekle",
        "Baskasinin calistigi dosya serbest kalana kadar bekler (en fazla 300 sn).",
        {
            "dosya": {"type": "string", "description": "projeye gore yol"},
            "sure_sn": {"type": "integer"},
        },
        ["dosya"],
    ),  # fmt: skip
    _f(
        "isi_devret",
        "Bu isi, konuyla zaten ugrasan diger oturuma devreder: neyi neden "
        "devrettigini ve gereken baglami yaz. Sonra o dosyalara dokunma.",
        {"kime": {"type": "string"}, "gorev": {"type": "string"}},
        ["kime", "gorev"],
    ),  # fmt: skip
]


def isleyiciler(proje: str, goreli) -> dict:
    """proje: calisma alani id. goreli: kullanici yolunu projeye gore yola ceviren fonksiyon."""
    from app.agent.yazma import sonuc_veya_hata

    return {
        "oturumlari_gor": lambda: sonuc_veya_hata(
            lambda: {"oturumlar": KOORD.aktifler(proje, haric=kimlik())}
        ),
        "oturuma_mesaj": lambda kime, metin: sonuc_veya_hata(KOORD.mesaj, kimlik(), kime, metin),
        "dosya_bekle": lambda dosya, sure_sn=120: sonuc_veya_hata(
            KOORD.bekle, kimlik(), proje, goreli(dosya), sure_sn
        ),
        "isi_devret": lambda kime, gorev: sonuc_veya_hata(
            KOORD.mesaj, kimlik(), kime, gorev, "devir"
        ),
    }
