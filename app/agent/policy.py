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
    r"^\.env|\.pem$|\.key$|\.pfx$|\.p12$|^id_(rsa|ed25519|ecdsa|dsa)|credential|password|parola|"
    r"^login data$|^cookies$|^web data$|\.kdbx$",
    re.I,
)
TARAYICI_PROFILI = re.compile(r"(Chrome|Edge|Firefox|Opera|Brave)[\\/].*(User Data|Profiles)", re.I)
# Uygulamanin kendi sirlari ve ajan arac yapilandirmasi: model bunlari okuyamaz
KORUMALI_KLASORLER = (".claude", ".codex", ".gemini", ".cursor", ".windsurf", ".opencode")

SIR_DESENLERI = [
    re.compile(r"(sk-[A-Za-z0-9]{12,})"),
    re.compile(r"(gh[pousr]_[A-Za-z0-9]{16,})"),
    re.compile(r"(AKIA[0-9A-Z]{12,})"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|parola|password|passwd)\b\s*[:=]\s*(\S{6,})"),
    re.compile(r"(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,})"),
]
MASKE = "***"


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
    return bool(GIZLI_AD.search(p.name) or TARAYICI_PROFILI.search(str(p)))


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


class Onay(BaseModel):
    """Tek bir ISLEM icin onay. Islem degisirse hash degisir ve eski onay gecersiz olur (A1.4)."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    islem_hash: str
    ozet: str
    arac: str
    yan_etki: YanEtki
    kapsam: str = "tek"  # tek | oturum
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

    def __init__(self, veri_dizini: Path, en_fazla: int = 200) -> None:
        self.yol = veri_dizini / "onaylar.json"
        self.en_fazla = en_fazla

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
        json_yaz(self.yol, [o.model_dump(mode="json") for o in onaylar[: self.en_fazla]])

    def olustur(self, istek: Istek, islem_hash: str) -> Onay:
        onay = Onay(
            islem_hash=islem_hash,
            ozet=istek.ozet or f"{istek.arac}: {istek.yol or istek.komut or ''}",
            arac=istek.arac,
            yan_etki=istek.yan_etki,
            son=(datetime.now() + timedelta(seconds=ONAY_SURESI_SN)).isoformat(timespec="seconds"),
        )
        self._yaz([onay, *self._liste()])
        return onay

    def karar_ver(self, onay_id: str, onayla: bool) -> Onay:
        onaylar = self._liste()
        for o in onaylar:
            if o.id == onay_id:
                if o.karar != "bekliyor":
                    raise YetkiYok("Bu onay zaten sonuclandi.")
                o.karar = "onayli" if onayla else "reddedildi"
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

    def gecerli_onay(self, islem_hash: str) -> Onay | None:
        return next((o for o in self._liste() if o.gecerli_mi(islem_hash)), None)

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
        if istek.arac in self.yonetilen.yasak_araclar:
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

        # 3) ag hedefi: yerel olmayan hedef acik izin ister
        if istek.yan_etki is YanEtki.ag and not yerel_host_mu(istek.host):
            if not self.ag_acik():
                return Sonuc(
                    karar=Karar.ret,
                    neden=f"Yerel olmayan ag hedefi kapali: {istek.host}",
                    kural="ag_kapali",
                )
            return Sonuc(karar=Karar.sor, neden="Dis ag hedefi onay ister.", kural="ag_onay")

        mod = self.mod(alan)
        yol_metni = str(cozulmus) if cozulmus else None

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
            gecerli = self.onaylar.gecerli_onay(h)
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
