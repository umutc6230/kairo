"""Kullanici ayarlari (AI Ayarlari ekrani): secili model, dusunme seviyesi, model klasoru..."""

from __future__ import annotations

from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from app.config import varsayilan_llm_dizini
from app.services.depo import json_oku, json_yaz
from app.services.yerel_llm import (
    DUSUNME_SEVIYELERI,
    MODELLER,
    VARSAYILAN_ADRES,
    VARSAYILAN_MODEL,
)

YEREL_HATA = (
    "Adres yalniz bu bilgisayar olabilir: http://127.0.0.1:8080, http://localhost:8080 "
    "ya da http://[::1]:8080 biciminde, kullanici adi/sorgu icermeden."
)
IZINLI_SCHEME = ("http", "https")


def _yerel_adres_coz(ham: str, v1_ekle: bool = True) -> str:
    """Adresi ayristirarak yalniz loopback hedeflerini kabul eder."""
    v = (ham or "").strip().rstrip("/")
    if not v:
        raise ValueError(YEREL_HATA)
    try:
        ayri = urlsplit(v)
        port = ayri.port  # gecersiz portta ValueError
        host = (ayri.hostname or "").lower()
    except ValueError as e:
        raise ValueError(YEREL_HATA) from e
    if ayri.scheme not in IZINLI_SCHEME or not ayri.netloc or not host:
        raise ValueError(YEREL_HATA)
    if ayri.username or ayri.password or "@" in ayri.netloc:
        raise ValueError(YEREL_HATA)  # userinfo ile gercek host gizlenebiliyor
    if ayri.query or ayri.fragment:
        raise ValueError(YEREL_HATA)
    if host != "localhost":
        try:
            if not ip_address(host).is_loopback:
                raise ValueError(YEREL_HATA)
        except ValueError as e:  # hostname ne localhost ne de loopback IP
            raise ValueError(YEREL_HATA) from e
    konak = f"[{host}]" if ":" in host else host
    netloc = f"{konak}:{port}" if port is not None else konak
    yol = ayri.path.rstrip("/")
    if v1_ekle and not yol.endswith("/v1"):
        yol = f"{yol}/v1"
    return f"{ayri.scheme}://{netloc}{yol}"


def yerel_adres_dogrula(ham: str) -> str:
    """Adresi AYRISTIRARAK yalniz loopback hedeflerini kabul eder; `.../v1` ile dondurur.

    startswith kontrolu yetersizdi: `http://localhost.example.invalid` ve
    `http://127.0.0.1@example.invalid` gercek hostname'i uzakta birakiyordu (A0.2).
    """
    return _yerel_adres_coz(ham, v1_ekle=True)


def ollama_adres_dogrula(ham: str) -> str:
    """Ollama sunucu adresini yalniz loopback olacak sekilde dogrular (`/v1` eklemez)."""
    return _yerel_adres_coz(ham, v1_ekle=False)


UZAK_PORT = 8765  # 8443 Tailscale'in kendi portuyla cakisiyordu


class KullaniciAyarlari(BaseModel):
    model: str = VARSAYILAN_MODEL
    dusunme: str = "kapali"
    llm_dizin: str = Field(default_factory=lambda: str(varsayilan_llm_dizini()))
    adres: str = VARSAYILAN_ADRES
    otomatik_baslat: bool = True
    sohbet_araclari: bool = True  # salt okunur dosya araclari + hesap/saat
    claude_talimatlari: bool = True  # ~/.claude/CLAUDE.md + @importlar (brain policy)
    uygulama_talimati: bool = True  # <veri>/KAIRO.md (+ @importlar)
    skiller_acik: bool = True  # Claude Code / brain / uygulama skill'leri
    kapali_skiller: list[str] = []
    sunucu_acik: bool = True  # Ollama gibi yerel sunucu: diger uygulamalar modelleri kullanir
    sunucu_port: int = Field(default=11434, ge=1024, le=65535)  # 11434 = Ollama'nin portu
    baglam_token: int = 16384  # llama-server -c; talimatlar ~3k token yer
    sistem_istemi: str = Field(default="", max_length=4000)
    sicaklik: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=16, le=8192)
    saglayici: Literal["yerel", "openrouter", "ollama", "uyumlu"] = "yerel"
    uyumlu_model: str = Field(default="", max_length=240)  # <saglayici>:<model> (or. groq:x)
    or_model: str = Field(default="", max_length=200)  # OpenRouter model id (or. x/y:free)
    ollama_model: str = Field(default="", max_length=200)  # Ollama model adi (or. qwen3:8b)
    # Kairo'nun kendi gecidi 11434'te; Kairo'nun baslattigi Ollama ayri portta calisir
    ollama_adres: str = Field(default="http://127.0.0.1:11435", max_length=200)
    # yeni projelerin varsayilan koordinator/uygulayici modeli (bos = aktif model)
    varsayilan_koordinator: str = Field(default="", max_length=200)
    varsayilan_uygulayici: str = Field(default="", max_length=200)
    gunluk_butce_usd: float = Field(default=0.0, ge=0.0, le=1000.0)
    # hafif: kucuk modelde skill/MCP/ek araclar gonderilmez; otomatik = kucuk yerel modelde hafif
    baglam_profili: Literal["otomatik", "tam", "hafif"] = "otomatik"
    # gorsel_uret araci (OpenRouter /images); bos = arac kapali
    gorsel_model: str = Field(default="recraft/recraft-v4.1-flash-v2:free", max_length=200)
    # otomatik: Codex CLI kuruluysa ChatGPT aboneligiyle Codex, degilse OpenRouter
    gorsel_saglayici: Literal["otomatik", "codex", "openrouter"] = "otomatik"
    # video_uret araci (OpenRouter /videos, UCRETLI); bos = arac kapali
    video_model: str = Field(default="", max_length=200)
    izolasyon: Literal["yok", "konteyner", "kum"] = "yok"  # A1.8: komutlar nerede calisir
    hafiza_acik: bool = True  # kayitli notlar sisteme eklenir
    dikte_bulut: bool = False  # sesli dikte OpenRouter modeline gidebilir (acik izinle)
    # dikte icin ayri OpenRouter modeli: sohbet modeli/saglayicisi ne olursa olsun mikrofon calisir
    dikte_model: str = Field(default="google/gemini-2.5-flash", max_length=200)
    ag_acik: bool = True  # web_ara/web_getir; tam yetkide onaysiz, degilse istek basina onay
    tam_yetki: bool = (
        False  # tek seferlik onayla: dosya/komut/MCP/git/web onaysiz (tehlikeli komut haric)
    )
    tarayici_acik: bool = True  # A9.2: izole profilli tarayici araclari (proje acikken)
    masaustu_izinli: list[str] = Field(default=[], max_length=20)  # A9.5: exe adlari; bos=kapali
    uzak_ag: Literal["tailscale", "yerel_ag"] = "tailscale"  # A12: varsayilan yalniz tailnet
    uzak_port: int = Field(
        default=UZAK_PORT, ge=1024, le=65535
    )  # A12: Remote Control (varsayilan kapali)
    saat_dilimi: str = "Europe/Istanbul"  # A11: zamanlamalarin varsayilani
    lsp_sunuculari: dict[str, str] = {}  # A10.1: {".py": "pylsp"}; yalniz kullanici tanimlar
    otomatik_ogrenme: bool = False  # ajan kendi not ekleyebilir (A4.4: kullanici acar)
    otomatik_inceleme: bool = True  # gorev dosya yazdiysa bitince model inceler (Chimera)
    # ---- Claude Desktop ayar karsiliklari ----
    dil: Literal["tr", "en"] = "tr"  # arayuz dili (app/web/i18n.js + en.json)
    tema: Literal["sistem", "acik", "koyu", "onedark", "dracula", "tokyonight"] = "koyu"
    yazi_boyutu: Literal["kucuk", "orta", "buyuk"] = "orta"
    sohbet_genisligi: Literal["dar", "genis"] = "dar"
    hareket: Literal["sistem", "azalt"] = "sistem"
    bildirim_yanit: bool = False  # yanit bitince (pencere arka plandayken)
    bildirim_onay: bool = True  # onay beklerken
    bildirim_zamanlama: bool = True  # rutin bitince / calisamayinca
    baslangicta_ac: bool = False  # Windows oturum acilinca baslat (Baslangic klasoru kisayolu)
    sistem_tepsisi: bool = True  # kapatinca tepside calismaya devam et
    hizli_kisayol: str = Field(default="Ctrl+Alt+Space", max_length=40)  # her yerden ac
    dikte_kisayolu: str = Field(default="Ctrl+D", max_length=40)
    ayrinti: Literal["normal", "dusunme", "ayrintili"] = "normal"  # sohbet ayrinti duzeyi
    cikti_stili: Literal["varsayilan", "aciklayici", "ogretici", "kisa"] = "varsayilan"
    branch_oneki: str = Field(default="kairo", pattern=r"^[A-Za-z0-9._-]{0,30}$")
    arsiv_gun: int = Field(default=0, ge=0, le=365)  # 0 = hic; N gun dokunulmayan sohbet arsivlenir
    konteyner_imaj: str = Field(
        default="python:3.12-slim", pattern=r"^[a-z0-9][a-z0-9._/:@-]{0,199}$"
    )

    @property
    def aktif_model(self) -> str:
        if self.saglayici == "ollama" and self.ollama_model:
            return f"ollama:{self.ollama_model}"
        if self.saglayici == "uyumlu" and self.uyumlu_model:
            return self.uyumlu_model
        return self.or_model if self.saglayici == "openrouter" and self.or_model else self.model

    @field_validator("uzak_port")
    @classmethod
    def _uzak_port(cls, v: int) -> int:
        # 8443 eski varsayilandi; Tailscale (tailscaled) kendi IP'sinde bu portu dinler ve uzak
        # erisim hic acilamiyordu. Kayitli eski deger yeni varsayilana tasinir.
        return UZAK_PORT if v == 8443 else v

    @field_validator("model")
    @classmethod
    def _model(cls, v: str) -> str:
        if v not in MODELLER:
            raise ValueError(f"Bilinmeyen model: {v}")
        return v

    @field_validator("dusunme")
    @classmethod
    def _dusunme(cls, v: str) -> str:
        if v not in DUSUNME_SEVIYELERI:
            raise ValueError(f"Gecersiz dusunme seviyesi: {v}")
        return v

    @field_validator("baglam_token")
    @classmethod
    def _baglam(cls, v: int) -> int:
        if v not in (8192, 16384, 32768):
            raise ValueError("Baglam 8192, 16384 ya da 32768 olabilir.")
        return v

    @field_validator("adres")
    @classmethod
    def _adres(cls, v: str) -> str:
        return yerel_adres_dogrula(v)

    @field_validator("ollama_adres")
    @classmethod
    def _ollama_adres(cls, v: str) -> str:
        return ollama_adres_dogrula(v)


class AyarDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "ayarlar.json"

    def oku(self) -> KullaniciAyarlari:
        ham = json_oku(self.yol, {}) or {}
        try:
            return KullaniciAyarlari(**ham)
        except ValueError:  # eski/bozuk ayar: varsayilana don, gecerli alanlari koru
            gecerli = {}
            for anahtar, deger in ham.items():
                try:
                    KullaniciAyarlari(**{anahtar: deger})
                    gecerli[anahtar] = deger
                except (ValueError, TypeError):
                    continue
            return KullaniciAyarlari(**gecerli)

    def yaz(self, ayarlar: KullaniciAyarlari) -> KullaniciAyarlari:
        json_yaz(self.yol, ayarlar.model_dump())
        return ayarlar

    def guncelle(self, degisiklik: dict) -> KullaniciAyarlari:
        yeni = KullaniciAyarlari(**(self.oku().model_dump() | degisiklik))
        return self.yaz(yeni)
