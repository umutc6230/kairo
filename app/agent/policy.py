"""Izin motoru: allow / ask / deny ve onay yasam dongusu (A1.3, A1.4, A1.6, A1.10).

Kurallar BACKEND'de yasar. Sistem mesajinda "sunu yapma" demek yetkilendirme degildir; model,
skill, plugin, hook ya da alt ajan metni bu karari degistiremez. Karar sirasi:

1. Yonetilen politika (kurumsal ust sinir) -> yalniz DARALTIR, hicbir sey genisletemez
2. Kalici `ret` kurallari (hassas dosya, kok disi yol, yerel olmayan ag hedefi)
3. Mod tavani (Planla = salt okunur, Onayli = yan etkide sor)
4. Guven durumu (guvenilmeyen proje: yalniz okuma)
5. Yan etki sinifi varsayilani

Belirsizlikte `sor`/`ret` uygulanir; asla `izin` degil.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.izolasyon import IzolasyonAdaptoru, YokAdaptoru
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.agent.yollar import guvenli_coz, kanonik
from app.exceptions import YetkiYok
from app.services.depo import json_oku, json_yaz

POLITIKA_SURUMU = 1
ONAY_SURESI_SN = 300  # onay 5 dakika gecerli; islem degisirse zaten gecersiz

GIZLI_KLASORLER = {".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store"}
GIZLI_AD = re.compile(
    r"^\.env|\.pem$|\.key$|\.pfx$|\.p12$|^id_(rsa|ed25519|ecdsa|dsa)|"
    r"^login data$|^cookies$|^web data$|\.kdbx$",
    re.I,
)
# Ad kelimesiyle sir supheli DOSYALAR (credentials.json, passwords.txt). Kaynak kod dosyalari ve
# KLASORLER bu kurala girmez: `parola.py`, `password_reset/` ya da adi 'parola' gecen bir proje
# kokunun okunamamasi ajani kor birakiyordu (A13 bulgusu). Icerikteki sirlar ayrica maskelenir.
GIZLI_KELIME = re.compile(r"credential|password|passwd|parola|secret", re.I)
KOD_UZANTILARI = frozenset(
    [
        ".py",
        ".pyi",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".cs",
        ".java",
        ".kt",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".vue",
        ".svelte",
        ".html",
        ".css",
        ".scss",
        ".md",
        ".rst",
        ".sql",
        ".sh",
        ".ps1",
        ".bat",
        ".lua",
        ".dart",
        ".scala",
    ]
)
TARAYICI_PROFILI = re.compile(r"(Chrome|Edge|Firefox|Opera|Brave)[\\/].*(User Data|Profiles)", re.I)
# Uygulamanin kendi sirlari ve ajan arac yapilandirmasi: model bunlari okuyamaz
KORUMALI_KLASORLER = (".claude", ".codex", ".gemini", ".cursor", ".windsurf", ".opencode")

SIR_DESENLERI = [
    re.compile(r"(sk-(?:or-v1-|ant-|proj-)?[A-Za-z0-9_-]{12,})"),
    re.compile(r"(gh[pousr]_[A-Za-z0-9]{16,})"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"(AKIA[0-9A-Z]{12,})"),
    re.compile(r"\b(\d{8,12}:AA[A-Za-z0-9_-]{30,})\b"),
    re.compile(r"\b((?:ak|ck)_[A-Za-z0-9_-]{16,})\b"),
    re.compile(r"\b(AIza[0-9A-Za-z_-]{30,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{12,})\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|parola|password|passwd)\b\s*[:=]\s*(\S{6,})"),
    re.compile(r"(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,})"),
]
MASKE = "***"

_ARAC_ES_ADLAR = {
    "proje_dosya_yaz": "dosya_yaz",
    "dosya_yaz": "proje_dosya_yaz",
    "proje_dosya_yama": "dosya_yama",
    "dosya_yama": "proje_dosya_yama",
    "proje_dosya_tasi": "dosya_tasi",
    "dosya_tasi": "proje_dosya_tasi",
    "proje_dosya_sil": "dosya_sil",
    "dosya_sil": "proje_dosya_sil",
}


class YanEtki(StrEnum):
    oku = "oku"
    yaz = "yaz"
    sil = "sil"
    komut = "komut"
    ag = "ag"
    dis = "dis"  # e-posta, satin alma, yayinlama: geri alinamaz dis etki
    git = "git"  # dal/commit: yerel ama gecmisi degistirir; push/merge burada YOK (dis)


class Karar(StrEnum):
    izin = "izin"
    sor = "sor"
    ret = "ret"


OKUMA_DISI = {YanEtki.yaz, YanEtki.sil, YanEtki.komut, YanEtki.ag, YanEtki.dis, YanEtki.git}
HER_ZAMAN_SOR = {YanEtki.dis, YanEtki.git}  # otomatik mod da sorar (A2.6: acik yetki)

# Tam yetkide bile sorulan, geri alinamaz ve genis etkili komutlar (claw-code
# "blast radius" ilkesi): disk/dizin silme, bicimlendirme, kapatma, zorla push.
TEHLIKELI_KOMUT = re.compile(
    r"(rm\s+-[a-z]*r[a-z]*f?\s+(/|~|[a-z]:[\\/]?)\s*$|rm\s+-rf\s+(/|~)(\s|$)"
    r"|\bformat(\.com)?\s+[a-z]:|\bdiskpart\b|\bmkfs\b|\bdd\s+if="
    r"|Remove-Item\b[^\n]*-Recurse[^\n]*\s[a-z]:[\\/]?\s*$|\brd\s+/s\s+/q\s+[a-z]:[\\/]?\s*$"
    r"|\bdel\s+/[sfq][^\n]*\s[a-z]:\\\*"
    r"|\bshutdown\b|\bStop-Computer\b|\bRestart-Computer\b"
    r"|git\s+push\b[^\n]*(--force|-f\b)|\breg\s+delete\s+HKLM"
    r"|\bbcdedit\b|\bcipher\s+/w)",
    re.I,
)


class Istek(BaseModel):
    """Izin sorusu. Her giris yolu (UI, CLI, SDK, MCP, alt ajan) ayni istegi uretir."""

    arac: str
    yan_etki: YanEtki = YanEtki.oku
    yol: str | None = None
    komut: str | None = None
    host: str | None = None
    ozet: str = ""


class Sonuc(BaseModel):
    karar: Karar
    neden: str
    kural: str
    cozulmus_yol: str | None = None
    politika_surumu: int = POLITIKA_SURUMU

    @property
    def izinli(self) -> bool:
        return self.karar is Karar.izin


class YonetilenPolitika(BaseModel):
    """Kurumsal ust sinir (data/yonetilen-politika.json). Kullanici/proje/uzanti GENISLETEMEZ."""

    yasak_araclar: list[str] = []
    yasak_yan_etkiler: list[YanEtki] = []
    en_fazla_mod: Mod | None = None  # or. "onayli": otomatik mod hic acilmaz
    ag_izinli: bool = False  # eski alan: True ise kullanici ayarindan bagimsiz acar
    ag_yasak: bool = False  # kurum: interneti tamamen kapatir (kullanici acamaz)
    yasak_yol_desenleri: list[str] = []

    @classmethod
    def yukle(cls, veri_dizini: Path) -> YonetilenPolitika:
        ham = json_oku(veri_dizini / "yonetilen-politika.json", {}) or {}
        try:
            return cls(**ham)
        except ValueError:
            return cls()  # bozuk politika dosyasi KISITLARI GEVSETMEZ: varsayilan (dar) kalir

    def mod_tavani(self, mod: Mod) -> Mod:
        if self.en_fazla_mod is None:
            return mod
        sira = [Mod.sohbet, Mod.planla, Mod.onayli, Mod.otomatik]
        return mod if sira.index(mod) <= sira.index(self.en_fazla_mod) else self.en_fazla_mod


def maskele(metin: str) -> str:
    """Sonuc ve loglarda sir maskeleme (A1.6).

    Anahtar/deger bicimlerinde yalniz DEGER maskelenir."""
    if not metin:
        return metin
    sonuc = metin
    for desen in SIR_DESENLERI:
        if desen.groups >= 2:
            sonuc = desen.sub(lambda m: m.group(0).replace(m.group(2), MASKE), sonuc)
        else:
            sonuc = desen.sub(MASKE, sonuc)
    return sonuc


def hassas_mi(p: Path) -> bool:
    """Gizli bilgi icerebilecek hedef mi? KANONIK yol uzerinde bakilir (link kacisi kapanir)."""
    parcalar = {x.lower() for x in p.parts}
    if parcalar & {k.lower() for k in GIZLI_KLASORLER}:
        return True
    if parcalar & {k.lower() for k in KORUMALI_KLASORLER}:
        return True
    if GIZLI_AD.search(p.name) or TARAYICI_PROFILI.search(str(p)):
        return True
    if GIZLI_KELIME.search(p.name):
        return p.suffix.lower() not in KOD_UZANTILARI and not p.is_dir()
    return False


def yerel_host_mu(host: str | None) -> bool:
    """Hedef bu bilgisayar mi? `startswith("127.")` YETERSIZ: `127.0.0.1.evil.test` de gecerdi."""
    h = (host or "").strip().lower().strip("[]")
    if not h:
        return False
    if h == "localhost":
        return True
    try:
        return ip_address(h).is_loopback
    except ValueError:
        return False


# OpenBot "kinds of action": tam yetkide de sorulan dis eylem turleri. Arac adi + ozet + komut
# uzerinde aranir (MCP araci adi, tarayici/masaustu dugme etiketi). Digerleri tam yetkide serbest.
_S = r"(?<![a-zçğıöşü])"  # kelime siniri: harf degil (snake_case alt cizgi sinir sayilir)
_E = r"(?![a-zçğıöşü])"


def _tur(*kelimeler: str) -> re.Pattern:
    return re.compile(_S + "(" + "|".join(kelimeler) + ")" + _E, re.I)


EYLEM_TURLERI: dict[str, re.Pattern] = {
    "odeme": _tur("pay", "payment", "checkout", "purchase", "buy", "order", "invoice", "refund",
                  "transfer", "payout", "withdraw", "charge", "subscribe", "ödeme", "odeme",
                  "öde", "ode", "satın al", "sipariş", "siparis"),
    "kimlik": _tur("password", "passwd", "2fa", "two.factor", "credentials?", "parola", "şifre",
                   "sifre"),
    "silme": _tur("delete", "destroy", "erase", "purge", "wipe", "trash", "discard", "sil",
                  "silin", "kaldır"),
    "gonderme": _tur("send", "reply", "forward", "respond", "notify", "broadcast", "invite",
                     "comment", "pr_yorum", "email", "mail", "gönder", "gonder", "yanıtla", "ilet"),
    "paylasma": _tur("share", "sharing", "permissions?", "collaborators?", "grant", "paylaş",
                     "paylas"),
    "yayinlama": _tur("publish", "post", "tweet", "repost", "release", "go live", "merge", "push",
                      "pull_request", "pr_olustur", "yayınla", "yayinla"),
}  # fmt: skip


def eylem_turu(istek: Istek) -> str:
    metin = " ".join(x for x in (istek.arac, istek.ozet, istek.komut or "") if x)
    return next((ad for ad, d in EYLEM_TURLERI.items() if d.search(metin)), "")


# Onayin "bu sohbet/gorev" kapsami icin hangi run/oturumda oldugumuz (runner ve sohbet ayarlar;
# asyncio.to_thread baglami kopyalar). OpenBot "Allow for this conversation" karsiligi.
BAGLAM: contextvars.ContextVar[str] = contextvars.ContextVar("onay_baglami", default="")
KAPSAMLAR = ("tek", "sohbet", "her_zaman")
SOHBET_KAPSAM_SAAT = 24


def islem_anahtari(istek: Istek) -> str:
    """Kapsamli onay icin islem TURU: ayni arac, ayni yan etki, ayni host. Komutta komut metni de
    anahtardadir: bir komuta verilen "her zaman" onayi o aracin TUM komutlarini (rm -rf) acmasin."""
    anahtar = f"{istek.arac}|{istek.yan_etki}|{(istek.host or '').lower()}"
    if istek.yan_etki is YanEtki.komut:
        anahtar += f"|{' '.join((istek.komut or '').split())}"
    return anahtar


class Onay(BaseModel):
    """Tek bir ISLEM icin onay. Islem degisirse hash degisir ve eski onay gecersiz olur (A1.4)."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    islem_hash: str
    ozet: str
    arac: str
    yan_etki: YanEtki
    kapsam: str = "tek"  # tek | sohbet | her_zaman
    anahtar: str = ""  # islem_anahtari: kapsamli onayin eslesecegi islem turu
    baglam: str = ""  # sohbet kapsami: onayin verildigi run/oturum
    politika_surumu: int = POLITIKA_SURUMU
    olusturma: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    son: str = ""
    karar: str = "bekliyor"  # bekliyor | onayli | reddedildi

    def gecerli_mi(self, islem_hash: str) -> bool:
        if self.karar != "onayli" or self.islem_hash != islem_hash:
            return False
        if self.politika_surumu != POLITIKA_SURUMU:
            return False
        try:
            return datetime.now() <= datetime.fromisoformat(self.son)
        except ValueError:
            return False


def islem_hashi(istek: Istek, cozulmus_yol: str | None = None) -> str:
    """Islemin tam ozeti: arac, yan etki, yol, komut, host. Biri degisirse hash degisir."""
    govde = json.dumps(
        {
            "arac": istek.arac,
            "yan_etki": str(istek.yan_etki),
            "yol": cozulmus_yol or istek.yol,
            "komut": istek.komut,
            "host": istek.host,
            "surum": POLITIKA_SURUMU,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(govde.encode()).hexdigest()[:32]


class OnayDeposu:
    """Onaylar data/onaylar.json'da; islem hash'i ile dogrulanir."""

    def __init__(
        self,
        veri_dizini: Path,
        en_fazla: int = 200,
        onay_bildir: Callable[[Onay], None] | None = None,
    ) -> None:
        self.yol = veri_dizini / "onaylar.json"
        self.en_fazla = en_fazla
        self.onay_bildir = onay_bildir

    def _liste(self) -> list[Onay]:
        ham = json_oku(self.yol, []) or []
        sonuc = []
        for h in ham:
            try:
                sonuc.append(Onay(**h))
            except ValueError:
                continue
        return sonuc

    def _yaz(self, onaylar: list[Onay]) -> None:
        # "Her zaman" kurallari gecmis sinirinda dusmez; digerleri son en_fazla kayit
        kalici = [o for o in onaylar if o.kapsam == "her_zaman" and o.karar == "onayli"]
        diger = [o for o in onaylar if o not in kalici][: self.en_fazla]
        json_yaz(self.yol, [o.model_dump(mode="json") for o in [*kalici, *diger]])

    def olustur(self, istek: Istek, islem_hash: str) -> Onay:
        onay = Onay(
            islem_hash=islem_hash,
            ozet=istek.ozet or f"{istek.arac}: {istek.yol or istek.komut or ''}",
            arac=istek.arac,
            yan_etki=istek.yan_etki,
            son=(datetime.now() + timedelta(seconds=ONAY_SURESI_SN)).isoformat(timespec="seconds"),
            anahtar=islem_anahtari(istek),
            baglam=BAGLAM.get(),
        )
        self._yaz([onay, *self._liste()])
        if self.onay_bildir is not None:
            self.onay_bildir(onay)
        return onay

    def karar_ver(self, onay_id: str, onayla: bool, kapsam: str = "tek") -> Onay:
        """kapsam: tek (yalniz bu islem), sohbet (bu run/oturumda ayni tur islem, 24 saat),
        her_zaman (ayni tur islem her yerde; Ayarlar'dan kaldirilabilir kural)."""
        if kapsam not in KAPSAMLAR:
            raise YetkiYok(f"Gecersiz onay kapsami: {kapsam}")
        onaylar = self._liste()
        for o in onaylar:
            if o.id == onay_id:
                if o.karar != "bekliyor":
                    raise YetkiYok("Bu onay zaten sonuclandi.")
                o.karar = "onayli" if onayla else "reddedildi"
                if onayla and kapsam != "tek" and o.anahtar:
                    o.kapsam = kapsam
                    if kapsam == "sohbet":
                        o.son = (datetime.now() + timedelta(hours=SOHBET_KAPSAM_SAAT)).isoformat(
                            timespec="seconds"
                        )
                self._yaz(onaylar)
                return o
        raise YetkiYok("Onay kaydi bulunamadi ya da suresi gecti.")

    def tuket(self, onay_id: str) -> None:
        """Tek seferlik onay bir kez kullanilinca biter; ayni islem tekrar onay ister."""
        onaylar = self._liste()
        for o in onaylar:
            if o.id == onay_id and o.kapsam == "tek":
                o.karar = "kullanildi"
                self._yaz(onaylar)
                return

    def gecerli_onay(self, islem_hash: str, anahtar: str = "", baglam: str = "") -> Onay | None:
        liste = self._liste()
        tam = next((o for o in liste if o.gecerli_mi(islem_hash)), None)
        if tam is not None or not anahtar:
            return tam
        simdi = datetime.now().isoformat(timespec="seconds")
        for o in liste:
            if o.karar != "onayli" or o.anahtar != anahtar or o.politika_surumu != POLITIKA_SURUMU:
                continue
            if o.kapsam == "her_zaman":
                return o
            if o.kapsam == "sohbet" and baglam and o.baglam == baglam and simdi <= o.son:
                return o
        return None

    def kurallar(self) -> list[dict]:
        """Kalici 'her zaman izin ver' kurallari (Ayarlar'da listelenir/kaldirilir)."""
        return [o.model_dump(mode="json") for o in self._liste()
                if o.kapsam == "her_zaman" and o.karar == "onayli"]  # fmt: skip

    def kural_sil(self, onay_id: str) -> None:
        onaylar = self._liste()
        for o in onaylar:
            if o.id == onay_id and o.kapsam == "her_zaman":
                o.karar = "geri_alindi"
        self._yaz(onaylar)

    def gecmis(self, adet: int = 50) -> list[dict]:
        return [o.model_dump(mode="json") for o in self._liste()[:adet]]


class PolitikaMotoru:
    """Tek karar noktasi. `degerlendir` dis etki uygulamaz, yalniz karar dondurur."""

    surum = POLITIKA_SURUMU

    def __init__(
        self,
        veri_dizini: Path,
        yonetilen: YonetilenPolitika | None = None,
        izolasyon: Callable[[], IzolasyonAdaptoru] = YokAdaptoru,
    ) -> None:
        self.veri_dizini = veri_dizini
        self.yonetilen = yonetilen or YonetilenPolitika.yukle(veri_dizini)
        self.onaylar = OnayDeposu(veri_dizini)
        self.izolasyon = izolasyon
        self.kullanici_ag: Callable[[], bool] = lambda: False  # api: ayarlardaki ag_acik
        # api: ayarlardaki tam_yetki (kullanici bir kez onaylar; openbot ilk acilis onayi gibi)
        self.tam_yetki: Callable[[], bool] = lambda: False

    # ---- yardimcilar ----
    def mod(self, alan: CalismaAlani) -> Mod:
        return self.yonetilen.mod_tavani(alan.mod)

    def _yol_degerlendir(self, alan: CalismaAlani, ham: str) -> tuple[Path | None, Sonuc | None]:
        try:
            cozulmus = guvenli_coz(alan.izinli_kokler, ham)
        except YetkiYok as e:
            return None, Sonuc(karar=Karar.ret, neden=str(e), kural="kok_disi")
        if hassas_mi(cozulmus):
            return cozulmus, Sonuc(
                karar=Karar.ret,
                neden="Bu hedef gizli bilgi (anahtar, parola, oturum) icerebilir; erisilmez.",
                kural="hassas_dosya",
                cozulmus_yol=str(cozulmus),
            )
        for desen in self.yonetilen.yasak_yol_desenleri:
            try:
                if re.search(desen, str(cozulmus), re.I):
                    return cozulmus, Sonuc(
                        karar=Karar.ret,
                        neden="Yonetilen politika bu yolu engelliyor.",
                        kural="yonetilen_yol",
                        cozulmus_yol=str(cozulmus),
                    )
            except re.error:
                continue
        return cozulmus, None

    # ---- ana karar ----
    def degerlendir(self, istek: Istek, alan: CalismaAlani) -> Sonuc:
        # 1) yonetilen politika: ust sinir
        yasak = set(self.yonetilen.yasak_araclar)
        if istek.arac in yasak or _ARAC_ES_ADLAR.get(istek.arac) in yasak:
            return Sonuc(
                karar=Karar.ret,
                neden=f"Yonetilen politika '{istek.arac}' aracini engelliyor.",
                kural="yonetilen_arac",
            )
        if istek.yan_etki in self.yonetilen.yasak_yan_etkiler:
            return Sonuc(
                karar=Karar.ret,
                neden=f"Yonetilen politika '{istek.yan_etki}' yan etkisini engelliyor.",
                kural="yonetilen_yan_etki",
            )

        # 2) kalici ret: yol kapsami ve hassas hedef
        cozulmus: Path | None = None
        if istek.yol is not None:
            cozulmus, ret = self._yol_degerlendir(alan, istek.yol)
            if ret is not None:
                return ret

        mod = self.mod(alan)
        yol_metni = str(cozulmus) if cozulmus else None

        # 3) ag hedefi: yerel olmayan hedef acik izin ister
        if istek.yan_etki is YanEtki.ag and not yerel_host_mu(istek.host):
            if alan.guven is Guven.guvenilmeyen:
                return Sonuc(
                    karar=Karar.ret,
                    neden="Guvenilmeyen projede dis ag kullanilmaz.",
                    kural="guven_salt_okunur",
                    cozulmus_yol=yol_metni,
                )
            if not self.ag_acik():
                return Sonuc(
                    karar=Karar.ret,
                    neden=f"Yerel olmayan ag hedefi kapali: {istek.host}",
                    kural="ag_kapali",
                )
            if self.tam_yetki() and mod not in (Mod.planla, Mod.sohbet):
                return Sonuc(
                    karar=Karar.izin,
                    neden="Tam yetki: web istegi.",
                    kural="tam_yetki",
                    cozulmus_yol=yol_metni,
                )
            from app.agent.web import ARAMA_HOSTLARI

            if (istek.host or "").lower() in ARAMA_HOSTLARI:
                return Sonuc(karar=Karar.izin, neden="Web aramasi (salt okuma).", kural="web_arama")
            return Sonuc(karar=Karar.sor, neden="Dis ag hedefi onay ister.", kural="ag_onay")

        # 3b) TAM YETKI: Claude Code "bypass" / openbot danger-full-access gibi. Yonetilen politika,
        # hassas dosya ve kok kapsami yukarida zaten uygulandi; burada yalniz Planla/Sohbet (salt
        # okunur modlar) ve geri alinamaz genis komutlar sorulur.
        if (
            self.tam_yetki()
            and mod not in (Mod.planla, Mod.sohbet)
            and alan.guven is not Guven.guvenilmeyen
        ):
            if istek.yan_etki is YanEtki.dis and (tur := eylem_turu(istek)):
                # OpenBot "kinds of action": gonderme, paylasma, yayinlama, odeme, silme, parola
                # gibi geri alinamaz dis eylemler tam yetkide de sorulur; "Her zaman" ile sorulmaz
                return Sonuc(
                    karar=Karar.sor,
                    neden=f"Geri alinamaz dis eylem ({tur}): tam yetkide de onay ister.",
                    kural="eylem_turu",
                    cozulmus_yol=yol_metni,
                )
            if istek.yan_etki is YanEtki.komut and TEHLIKELI_KOMUT.search(istek.komut or ""):
                return Sonuc(
                    karar=Karar.sor,
                    neden="Geri alinamaz, genis etkili komut: tam yetkide de onay ister.",
                    kural="tehlikeli_komut",
                    cozulmus_yol=yol_metni,
                )
            return Sonuc(
                karar=Karar.izin,
                neden="Tam yetki: kullanici onaylamadan uygulanir.",
                kural="tam_yetki",
                cozulmus_yol=yol_metni,
            )

        # 4) salt okunur haller
        if istek.yan_etki in OKUMA_DISI:
            if mod in (Mod.sohbet, Mod.planla):
                return Sonuc(
                    karar=Karar.ret,
                    neden=f"'{mod}' modu salt okunur; bu islem uygulanmaz.",
                    kural="mod_salt_okunur",
                    cozulmus_yol=yol_metni,
                )
            if alan.guven is Guven.guvenilmeyen:
                return Sonuc(
                    karar=Karar.ret,
                    neden="Guvenilmeyen projede yalniz okuma yapilir.",
                    kural="guven_salt_okunur",
                    cozulmus_yol=yol_metni,
                )

        # 5) yan etki sinifi
        if istek.yan_etki is YanEtki.oku:
            return Sonuc(
                karar=Karar.izin,
                neden="Yetkili kok icinde okuma.",
                kural="oku",
                cozulmus_yol=yol_metni,
            )
        if istek.yan_etki in HER_ZAMAN_SOR:
            return Sonuc(
                karar=Karar.sor,
                neden=(
                    "Dis etkili islem her zaman onay ister."
                    if istek.yan_etki is YanEtki.dis
                    else "Git dal/commit islemi her zaman onay ister."
                ),
                kural="dis_etki" if istek.yan_etki is YanEtki.dis else "git_onay",
                cozulmus_yol=yol_metni,
            )
        if mod is Mod.otomatik and istek.yan_etki is YanEtki.komut and not self.izolasyon().izole:
            return Sonuc(
                karar=Karar.sor,
                neden="Izolasyon yok: komut kullanicinin tum yetkileriyle calisir, onay gerekir.",
                kural="izolasyonsuz_komut",
                cozulmus_yol=yol_metni,
            )
        if mod is Mod.otomatik:
            return Sonuc(
                karar=Karar.izin,
                neden="Otomatik mod: politika kapsaminda uygulanir.",
                kural="otomatik",
                cozulmus_yol=yol_metni,
            )
        return Sonuc(
            karar=Karar.sor,
            neden="Onayli mod: yan etkili adim kullanici onayi ister.",
            kural="onayli_mod",
            cozulmus_yol=yol_metni,
        )

    def ag_acik(self) -> bool:
        """Internet: kurum yasaklamadiysa ve (kullanici actiysa ya da eski kurum izni varsa)."""
        if self.yonetilen.ag_yasak:
            return False
        return bool(self.yonetilen.ag_izinli or self.kullanici_ag())

    def uygula(self, istek: Istek, alan: CalismaAlani) -> Sonuc:
        """Karari uygular: `ret` -> YetkiYok, `sor` -> gecerli onay yoksa OnayGerekli."""
        from app.exceptions import OnayGerekli

        sonuc = self.degerlendir(istek, alan)
        if sonuc.karar is Karar.ret:
            raise YetkiYok(sonuc.neden)
        if sonuc.karar is Karar.sor:
            h = islem_hashi(istek, sonuc.cozulmus_yol)
            gecerli = self.onaylar.gecerli_onay(h, islem_anahtari(istek), BAGLAM.get())
            if gecerli is None:
                onay = self.onaylar.olustur(istek, h)
                raise OnayGerekli(sonuc.neden, onay.model_dump(mode="json"))
            self.onaylar.tuket(gecerli.id)  # ayni onay ikinci kez kullanilamaz
        return sonuc

    def okuma_yolu(self, alan: CalismaAlani, arac: str, ham: str) -> Path:
        """Salt okunur arac icin yol izni; reddi YetkiYok olarak atar."""
        sonuc = self.degerlendir(
            Istek(arac=arac, yan_etki=YanEtki.oku, yol=ham, ozet=f"{arac}: {ham}"), alan
        )
        if not sonuc.izinli or not sonuc.cozulmus_yol:
            raise YetkiYok(sonuc.neden)
        return Path(sonuc.cozulmus_yol)

    def bilgi(self, alan: CalismaAlani) -> dict[str, Any]:
        """Arayuzde gorunen izin kapsami (kullanici neyin acik oldugunu gorebilsin)."""
        mod = self.mod(alan)
        iz = self.izolasyon().durum()
        return {
            "mod": str(mod),
            "mod_tavani_uygulandi": mod != alan.mod,
            "guven": str(alan.guven),
            "politika_surumu": self.surum,
            "kokler": [str(k) for k in alan.izinli_kokler],
            "salt_okunur": alan.salt_okunur_mu() or mod in (Mod.sohbet, Mod.planla),
            "talimat_okunur": alan.talimat_okunur_mu(),
            "ag_izinli": self.ag_acik(),
            "ag_kurum_yasak": self.yonetilen.ag_yasak,
            "yasak_araclar": self.yonetilen.yasak_araclar,
            "izolasyon": iz["ad"] if iz["izole"] else "yok",
            "izolasyon_secimi": iz["ad"],
            "izolasyon_kullanilabilir": iz["kullanilabilir"],
            "izolasyon_notu": iz["not"],
            "otomatik_komut": "izinli" if iz["izole"] else "onay ister",
        }


def kanonik_kok(yol: str | Path) -> str:
    return str(kanonik(yol))
