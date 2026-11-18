"""Yerel llama-server (DeepSeek-V4-Pro-Qwen3.5-9B heretic) icin async istemci.

Projeye kopyala: app/services/yerel_llm.py
Hata siniflarini projenin exceptions.py dosyasina tasi (politika).
Bagimlilik: httpx (requests yasak). Opsiyonel: Pillow (gorsel kucultme), PyMuPDF (PDF).
Node/Electron karsiligi: yerel-llm.mjs (ayni API).

Ornek:
    llm = YerelLLM(dusunme=ayarlar.dusunme)  # "kapali" | "dengeli" | "derin" (AI Ayarlari'ndan)
    await llm.hazirla()                    # kapaliysa baslatir, hazir olana kadar bekler
    print(await llm.metin("Merhaba"))
    print(await llm.ocr(Path("fatura.png")))
    print(await llm.ocr_pdf(Path("hakedis.pdf")))  # metin katmani varsa OCR yok
    ozet = await llm.parca_parca(uzun, "Ozetle.", birlestir="Ozetleri birlestir.")
    llm.dusunme = "derin"                  # ayar degisince aninda gecerli (restart yok)
    print(await llm.metin("Zor soru"), llm.son_dusunce)
    await llm.kapat()                      # yalniz kendi baslattigi sunucuyu durdurur
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import io
import json
import mimetypes
import os
import re
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

import httpx

VARSAYILAN_ADRES = "http://127.0.0.1:8080/v1"
VARSAYILAN_MODEL = "deepseek-heretic"
VARSAYILAN_DIZIN = Path(os.environ.get("YEREL_LLM_DIZIN", r"C:\Users\umuti\Projects\llm"))
ANA_MODEL = "DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.i1-Q4_K_M.gguf"
GORUNTU_MODULU = "DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.mmproj-Q8_0.gguf"


@dataclass(frozen=True)
class ModelProfili:
    """models/ klasorundeki bir yerel model. anahtar = --alias = istekteki model adi."""

    anahtar: str
    ad: str
    dosya: str
    mmproj: str
    ram_gb: float  # model + goruntu modulu; bos RAM bundan ~1-2 GB fazla olmali
    ses: bool  # ses girisi (input_audio) var mi
    aciklama: str


MODELLER: dict[str, ModelProfili] = {
    p.anahtar: p
    for p in (
        ModelProfili(
            "deepseek-heretic",
            "DeepSeek-V4-Pro Qwen3.5 9B heretic",
            ANA_MODEL,
            GORUNTU_MODULU,
            6.2,
            False,
            "Varsayilan. Metin, OCR, arac cagirma, JSON.",
        ),
        ModelProfili(
            "gemma4-12b-heretic",
            "Gemma 4 12B heretic (QAT)",
            "gemma-4-12B-it-qat-q4_0-uncensored-heretic-Q4_0.gguf",
            "gemma-4-12B-it-qat-q4_0-uncensored-heretic-mmproj-BF16.gguf",
            7.8,
            True,
            "En guclu. Metin, OCR, arac, ses. ~9-10 GB bos RAM ister.",
        ),
        ModelProfili(
            "gemma4-e4b-heretic",
            "Gemma 4 E4B heretic",
            "gemma-4-E4B-it-ultra-uncensored-heretic.i1-Q4_K_M.gguf",
            "gemma-4-E4B-it-ultra-uncensored-heretic.mmproj-Q8_0.gguf",
            5.9,
            True,
            "Hafif. Metin, OCR, arac, ses.",
        ),
    )
}
MODEL_SECENEKLERI = [  # AI Ayarlari ekrani icin
    {"deger": p.anahtar, "ad": p.ad, "aciklama": p.aciklama, "ram_gb": p.ram_gb, "ses": p.ses}
    for p in MODELLER.values()
]
OCR_TALIMATI = "Resimdeki tum yaziyi aynen, satir satir yaz. Yorum ekleme."
KESILDI_MESAJI = "Cevap token sinirina takildi; max_tokens artirin ya da dusunmeyi azaltin."
ZAMAN_ASIMI_MESAJI = "Yerel model zamaninda cevap vermedi."
OCR_UZUN_KENAR = 1600  # gorsel bu boyuta kucultulur: token ve sure duser, 8192 context'e sigar
PDF_DPI = 200
# Uzun metin parcasi. Olcum (2026-11-08, /tokenize): Turkce ~3.3 karakter/token.
# 12000 kar ~3600 token: kapali/dengeli rahat sigar; derin cevaba +4096 ayirdigi icin 8000.
MAX_PARCA_KARAKTER = 12000
DERIN_PARCA_KARAKTER = 8000

# --- Dusunme (effort) seviyeleri -------------------------------------------------------
# Olcum (2026-11-08, ~5.6 token/sn): havuz problemi kapali 3 sn YANLIS, dusunmeli ~45 sn DOGRU.
# Butce cok kucukse (48 token) dusunme yarida kesilir ve cevap yine yanlis olur.
Dusunme = Literal["kapali", "dengeli", "derin"]
DUSUNME_SEVIYELERI: tuple[str, ...] = get_args(Dusunme)
VARSAYILAN_DUSUNME: Dusunme = "kapali"
DENGELI_BUTCE = 1024  # dusunme token siniri (thinking_budget_tokens)
DERIN_EK_TOKEN = 4096  # derin modda cevap + dusunce icin max_tokens'a eklenen pay
ZAMAN_ASIMI_SN = {"kapali": 300.0, "dengeli": 600.0, "derin": 1800.0}
DUSUNME_SECENEKLERI = [  # AI Ayarlari ekrani icin hazir metinler
    {
        "deger": "kapali",
        "ad": "Kapali (hizli)",
        "aciklama": "Cevap hemen gelir. OCR, ozet, ceviri, veri cikarma icin yeterli.",
        "sure": "birkac saniye",
    },
    {
        "deger": "dengeli",
        "ad": "Dengeli",
        "aciklama": "Kisa dusunur (en fazla 1024 token). Hesap ve mantik sorularinda daha dogru.",
        "sure": "~30 sn - 3 dk",
    },
    {
        "deger": "derin",
        "ad": "Derin (en iyi sonuc)",
        "aciklama": "Sinirsiz dusunur. Zor problem, karar ve analiz icin; bekleme uzun olabilir.",
        "sure": "~1 - 10 dk",
    },
]


# --- Hata siniflari (projede exceptions.py'ye tasi) ---------------------------------------
class YerelLLMHatasi(Exception):
    """Yerel model ile ilgili tum hatalarin tabani. Mesajlar kullaniciya gosterilebilir."""


class SunucuKapali(YerelLLMHatasi):
    def __init__(self) -> None:
        super().__init__(
            "Yerel model calismiyor. Baslatici ile acin ya da otomatik baslatmayi acin."
        )


class SunucuBaslamadi(YerelLLMHatasi):
    def __init__(self, ayrinti: str = "") -> None:
        super().__init__(f"Yerel model baslatilamadi. {ayrinti}".strip())


class GoruntuDesteklenmiyor(YerelLLMHatasi):
    def __init__(self) -> None:
        super().__init__("Goruntu modulu (mmproj) yuklu degil; resim okunamiyor.")


class ModelCevapHatasi(YerelLLMHatasi):
    pass


class BellekYetersiz(ModelCevapHatasi):
    """Gorsel kodlanirken GPU/RAM bitti (llama.cpp: "failed to process mtmd chunk",
    log'da ErrorOutOfDeviceMemory). Bu PC'de GPU, RAM'i paylasan dahili AMD Radeon; model
    ~6 GB RAM tutar, gorsel icin ek bellek gerekir. Gorseli kucultmek cogu zaman YETMEZ."""

    def __init__(self) -> None:
        super().__init__(
            "Resmi islemeye bellek yetmedi. Acik programlari (oyun, tarayici sekmeleri) kapatip "
            "tekrar deneyin; olmazsa yerel modeli yeniden baslatin."
        )


class SesDesteklenmiyor(YerelLLMHatasi):
    def __init__(self) -> None:
        super().__init__(
            "Acik model ses girisini desteklemiyor; Gemma 4 modellerinden birini secin."
        )


class FarkliModelAcik(YerelLLMHatasi):
    def __init__(self, acik: list[str], istenen: str) -> None:
        super().__init__(
            f"Yerel sunucuda baska model acik ({', '.join(acik)}); istenen: {istenen}. "
            "Acik olan sunucuyu kapatip tekrar deneyin."
        )


class GecersizDusunme(YerelLLMHatasi):
    def __init__(self, deger: object) -> None:
        super().__init__(f"Gecersiz dusunme seviyesi: {deger!r} (kapali, dengeli, derin).")


# --- Windows: uygulama cokse de sunucu kapansin (Job Object) -------------------------------
def cokunce_kapanacak_yap(surec: subprocess.Popen[bytes]) -> int | None:
    """Sureci KILL_ON_JOB_CLOSE bayrakli bir Windows Job Object'e baglar ve handle'i dondurur.
    Handle kapaninca (kapat() ya da uygulama coker/oldurulurse isletim sistemi kapatir) surec de
    olur; VRAM'de yetim llama-server kalmaz. Windows disinda ya da basarisizsa None (zararsiz)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class _Temel(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _Genis(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _Temel),
            ("IoInfo", ctypes.c_ulonglong * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    is_nesnesi = k32.CreateJobObjectW(None, None)
    if not is_nesnesi:
        return None
    bilgi = _Genis()
    bilgi.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    tamam = k32.SetInformationJobObject(
        is_nesnesi,
        9,
        ctypes.byref(bilgi),
        ctypes.sizeof(bilgi),  # 9: ExtendedLimitInformation
    ) and k32.AssignProcessToJobObject(is_nesnesi, int(surec._handle))  # type: ignore[attr-defined]
    if not tamam:
        k32.CloseHandle(is_nesnesi)
        return None
    return int(is_nesnesi)


def _job_bagla_guvenli(surec: subprocess.Popen[bytes]) -> int | None:
    """Job Object hatasi sunucu baslatmayi bozmasin (sahte surec, eski Windows vb.)."""
    try:
        return cokunce_kapanacak_yap(surec)
    except Exception:  # noqa: BLE001
        return None


def _handle_kapat(handle: int) -> None:
    import ctypes

    ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(handle))


# --- Gorsel / PDF / uzun metin yardimcilari ---------------------------------------------
def resmi_kucult(
    veri: bytes, uzun_kenar: int = OCR_UZUN_KENAR, mime: str = "image/png"
) -> tuple[bytes, str]:
    """Uzun kenari `uzun_kenar`'i asan gorseli kucultur (Pillow). PNG PNG kalir (yazi keskin),
    digerleri JPEG %90 olur. Pillow yoksa, gorsel acilamiyorsa ya da zaten kucukse aynen doner."""
    try:
        from PIL import Image
    except ImportError:
        return veri, mime
    try:
        resim = Image.open(io.BytesIO(veri))
        resim.load()
    except Exception:  # noqa: BLE001 - bozuk/bilinmeyen bicim: modele oldugu gibi gider
        return veri, mime
    if max(resim.size) <= uzun_kenar:
        return veri, mime
    resim.thumbnail((uzun_kenar, uzun_kenar), Image.Resampling.LANCZOS)
    cikti = io.BytesIO()
    if mime == "image/png":
        resim.save(cikti, "PNG", optimize=True)
        return cikti.getvalue(), "image/png"
    resim.convert("RGB").save(cikti, "JPEG", quality=90)
    return cikti.getvalue(), "image/jpeg"


def _pdf_ac(pdf: Path | bytes) -> Any:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise YerelLLMHatasi("PDF okumak icin PyMuPDF gerekli: pip install pymupdf") from e
    try:
        if isinstance(pdf, Path):
            return fitz.open(pdf)
        return fitz.open(stream=pdf, filetype="pdf")
    except Exception as e:  # noqa: BLE001 - fitz hata siniflari surume gore degisir
        raise YerelLLMHatasi(f"PDF acilamadi: {e}") from e


def pdf_sayfalari(
    pdf: Path | bytes, dpi: int = PDF_DPI, sayfalar: Iterable[int] | None = None
) -> list[bytes]:
    """PDF sayfalarini PNG olarak dondurur (0 tabanli `sayfalar`; None ise hepsi)."""
    with _pdf_ac(pdf) as belge:
        secili = range(belge.page_count) if sayfalar is None else sayfalar
        return [belge[i].get_pixmap(dpi=dpi).tobytes("png") for i in secili]


def parcala(metin: str, max_karakter: int = MAX_PARCA_KARAKTER) -> list[str]:
    """Metni once paragraf, sonra cumle sinirindan, en son zorla bolerek max_karakter'lik
    parcalara ayirir. Bos metin -> []."""
    if max_karakter < 1:
        raise ValueError("max_karakter pozitif olmali")
    birimler: list[tuple[str, str]] = []  # (metin, onceki birimle arasina girecek ayrac)
    for paragraf in re.split(r"\n\s*\n", metin.strip()):
        if len(paragraf) <= max_karakter:
            birimler.append((paragraf, "\n\n"))
            continue
        ayrac = "\n\n"  # uzun paragrafin ilk cumlesi yeni paragraf, devami ayni paragraf
        for cumle in re.split(r"(?<=[.!?])\s+", paragraf):
            for i in range(0, len(cumle), max_karakter):
                birimler.append((cumle[i : i + max_karakter], ayrac))
                ayrac = " " if i + max_karakter >= len(cumle) else ""
    parcalar: list[str] = []
    for b, ayrac in birimler:
        if not b.strip():
            continue
        if parcalar and len(parcalar[-1]) + len(ayrac) + len(b) <= max_karakter:
            parcalar[-1] += ayrac + b
        else:
            parcalar.append(b)
    return parcalar


# --- Istemci --------------------------------------------------------------------------
Isleyici = Callable[..., Any] | Callable[..., Awaitable[Any]]
Ilerleme = Callable[[int, int], Any]  # (tamamlanan, toplam) -> UI ilerleme cubugu


class YerelLLM:
    def __init__(
        self,
        adres: str = VARSAYILAN_ADRES,
        model: str = VARSAYILAN_MODEL,
        dizin: Path | None = None,
        dusunme: Dusunme = VARSAYILAN_DUSUNME,
        okuma_zaman_asimi: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        cokunce_kapat: bool = True,
        baglam: int = 8192,
    ) -> None:
        """okuma_zaman_asimi None ise dusunme seviyesine gore secilir (ZAMAN_ASIMI_SN).
        cokunce_kapat: bu nesnenin baslattigi sunucu, uygulama cokse de kapanir (Windows Job)."""
        self.cokunce_kapat = cokunce_kapat
        self.baglam = baglam  # llama-server -c (token); degisirse sunucu yeniden baslatilmali
        self._is_nesnesi: int | None = None
        self.adres = adres.rstrip("/")
        self.kok = self.adres.removesuffix("/v1")
        self.model = model
        self.dizin = Path(dizin) if dizin else VARSAYILAN_DIZIN
        self._surec: subprocess.Popen[bytes] | None = None
        self._log: Any = None
        self._kilit = asyncio.Lock()  # ayni anda iki hazirla() iki sunucu acmasin
        self.dusunme = dusunme
        self.okuma_zaman_asimi = okuma_zaman_asimi
        self.son_dusunce = ""  # son cevabin reasoning_content'i ("Dusunceyi goster" icin)
        # son cevabin llama-server olcumleri (prompt_per_second, predicted_per_second...)
        self.son_zamanlama: dict[str, Any] = {}
        # son cevabin `usage`'i: prompt/completion token, onbellek (cached_tokens), maliyet (cost)
        self.son_kullanim: dict[str, Any] = {}
        self._istemci = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=5.0), transport=transport
        )

    # ---- dusunme ayari ----
    @property
    def dusunme(self) -> Dusunme:
        return self._dusunme

    @dusunme.setter
    def dusunme(self, deger: str) -> None:
        self._dusunme = self._seviye(deger)

    @staticmethod
    def _seviye(deger: str | None) -> Dusunme:
        if deger not in DUSUNME_SEVIYELERI:
            raise GecersizDusunme(deger)
        return deger  # type: ignore[return-value]

    def _zaman_asimi(self, seviye: Dusunme) -> httpx.Timeout:
        sn = self.okuma_zaman_asimi or ZAMAN_ASIMI_SN[seviye]
        return httpx.Timeout(sn, connect=5.0)

    # ---- yasam dongusu ----
    async def saglikli(self) -> bool:
        try:
            r = await self._istemci.get(f"{self.kok}/health", timeout=3.0)
        except httpx.HTTPError:
            return False
        if r.status_code != 200:
            return False
        try:
            return r.json().get("status") == "ok"
        except ValueError:  # portta baska bir program (JSON olmayan cevap)
            return False

    async def goruntu_destegi(self) -> bool:
        r = await self._istemci.get(f"{self.kok}/props", timeout=5.0)
        r.raise_for_status()
        return bool((r.json().get("modalities") or {}).get("vision"))

    async def modeller(self) -> list[str]:
        r = await self._istemci.get(f"{self.adres}/models", timeout=5.0)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]

    @property
    def profil(self) -> ModelProfili | None:
        """Secili modelin profili; MODELLER disinda bir ad (elle acilmis sunucu) ise None."""
        return MODELLER.get(self.model)

    def _baslat_komutu(self, port: int, goruntu: bool) -> list[str]:
        if self.profil is None:
            raise SunucuBaslamadi(
                f"Bilinmeyen model: {self.model}. Otomatik baslatma yalniz su modellerde: "
                f"{', '.join(MODELLER)}"
            )
        exe = self.dizin / "llama.cpp" / "llama-server.exe"
        model = self.dizin / "models" / self.profil.dosya
        if not exe.exists():
            raise SunucuBaslamadi(f"Model klasoru bulunamadi: {self.dizin}")
        if not model.exists():
            raise SunucuBaslamadi(f"Model dosyasi bulunamadi: {model.name} ({model.parent})")
        komut = [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(port)]
        komut += ["-ngl", "99", "-c", str(self.baglam), "--jinja", "--alias", self.model]
        mmproj = self.dizin / "models" / self.profil.mmproj
        if goruntu and mmproj.exists():
            komut += ["--mmproj", str(mmproj)]
        return komut

    async def _acik_modeller(self) -> list[str]:
        """Acik sunucunun model adlari; okunamazsa [] (dogrulanamaz, kabul edilir)."""
        try:
            return await self.modeller()
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return []

    async def hazirla(self, otomatik_baslat: bool = True, bekle_sn: float = 180.0) -> None:
        """Sunucu aciksa ve istenen model ise dokunmaz; kapaliysa (izin varsa) baslatir ve hazir
        olana kadar bekler. Basaramazsa kendi baslattigi sureci durdurur (yetim surec kalmaz).
        Portta BASKA model aciksa: kendi baslattigimizsa kapatip dogru modeli acar, degilse
        FarkliModelAcik verir (kullanicinin actigina dokunmaz)."""
        async with self._kilit:
            if await self.saglikli():
                acik = await self._acik_modeller()
                if not acik or self.model in acik:
                    return
                if not (self._surec and self._surec.poll() is None):
                    raise FarkliModelAcik(acik, self.model)
                await self._sureci_durdur()  # model degisti: kendi sunucumuzu yenile
                await self._kapanana_kadar_bekle()
            if not otomatik_baslat:
                raise SunucuKapali()
            if self._surec and self._surec.poll() is None:
                await self._sureci_durdur()  # onceki yarim kalmis deneme
            port = httpx.URL(self.kok).port or 8080
            komut = self._baslat_komutu(port, goruntu=True)  # klasor yoksa burada Turkce hata
            bayrak = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            try:
                self._log = open(self.dizin / "server-app.log", "ab")  # noqa: SIM115
                self._surec = subprocess.Popen(
                    komut,
                    cwd=self.dizin,
                    stdout=self._log,
                    stderr=subprocess.STDOUT,
                    creationflags=bayrak,
                )
            except OSError as e:
                await self._sureci_durdur()
                raise SunucuBaslamadi(str(e)) from e
            if self.cokunce_kapat:
                self._is_nesnesi = _job_bagla_guvenli(self._surec)
            try:
                await self._hazir_bekle(bekle_sn)
            except BaseException:  # zaman asimi, surec cokmesi, iptal (CancelledError)
                await self._sureci_durdur()
                raise

    async def _kapanana_kadar_bekle(self, bekle_sn: float = 15.0) -> None:
        bitis = asyncio.get_running_loop().time() + bekle_sn
        while await self.saglikli() and asyncio.get_running_loop().time() < bitis:
            await asyncio.sleep(0.5)

    async def _hazir_bekle(self, bekle_sn: float) -> None:
        assert self._surec is not None
        bitis = asyncio.get_running_loop().time() + bekle_sn
        while asyncio.get_running_loop().time() < bitis:
            if self._surec.poll() is not None:
                raise SunucuBaslamadi(
                    f"Surec kapandi (kod {self._surec.returncode}), log: server-app.log"
                )
            if await self.saglikli():
                return
            await asyncio.sleep(1.0)
        raise SunucuBaslamadi("Zaman asimi; model yuklenemedi.")

    async def _sureci_durdur(self) -> None:
        """Yalniz bu nesnenin baslattigi sureci durdurur ve log dosyasini kapatir."""
        if self._surec and self._surec.poll() is None:
            self._surec.terminate()
            try:
                await asyncio.to_thread(self._surec.wait, 10)
            except subprocess.TimeoutExpired:
                self._surec.kill()
        self._surec = None
        if self._is_nesnesi:
            _handle_kapat(self._is_nesnesi)
            self._is_nesnesi = None
        if self._log:
            self._log.close()
            self._log = None

    async def kapat(self) -> None:
        """HTTP istemcisini kapatir; yalniz bu nesnenin baslattigi sunucuyu durdurur."""
        await self._istemci.aclose()
        await self._sureci_durdur()

    async def __aenter__(self) -> YerelLLM:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.kapat()

    # ---- istekler ----
    def _govde(self, mesajlar: list[dict], seviye: Dusunme, max_tokens: int, **ek: Any) -> dict:
        govde: dict[str, Any] = {
            "model": self.model,
            "messages": mesajlar,
            "temperature": ek.pop("temperature", 0.2),
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": seviye != "kapali"},
        }
        if seviye == "dengeli":
            govde["thinking_budget_tokens"] = DENGELI_BUTCE
            govde["max_tokens"] = max_tokens + DENGELI_BUTCE
        elif seviye == "derin":
            govde["max_tokens"] = max_tokens + DERIN_EK_TOKEN
        govde.update(ek)
        return govde

    async def sohbet(
        self,
        mesajlar: list[dict],
        *,
        dusunme: Dusunme | None = None,
        max_tokens: int = 1024,
        **ek: Any,
    ) -> dict:
        """Ham chat/completions cagrisi; choices[0] dondurur (message + finish_reason).
        dusunme None ise nesnenin (ayarlardaki) seviyesi kullanilir."""
        seviye = self._seviye(dusunme) if dusunme else self.dusunme
        govde = self._govde(mesajlar, seviye, max_tokens, **ek)
        try:
            r = await self._istemci.post(
                f"{self.adres}/chat/completions", json=govde, timeout=self._zaman_asimi(seviye)
            )
        except httpx.ConnectError as e:
            raise SunucuKapali() from e
        except httpx.TimeoutException as e:
            raise ModelCevapHatasi(ZAMAN_ASIMI_MESAJI) from e
        if r.status_code >= 400:
            self._hata_firlat(r.status_code, r.text)
        veri = r.json()
        self.son_zamanlama = veri.get("timings") or {}
        self.son_kullanim = veri.get("usage") or {}
        secim = veri["choices"][0]
        self.son_dusunce = (
            (secim.get("message") or {}).get("reasoning_content")
            or (secim.get("message") or {}).get("reasoning")
            or ""
        )
        return secim

    @staticmethod
    def _hata_firlat(durum: int, govde: str) -> None:
        """HTTP hata cevabini Turkce, kullaniciya gosterilebilir hataya cevirir."""
        metin = govde[:300]
        kucuk = metin.lower()
        if "mtmd chunk" in kucuk or "out of memory" in kucuk or "outofdevicememory" in kucuk:
            raise BellekYetersiz()
        if "audio" in kucuk:
            raise SesDesteklenmiyor()
        if any(k in kucuk for k in ("image", "mmproj", "multimodal")):
            raise GoruntuDesteklenmiyor()
        if "context" in kucuk:
            raise ModelCevapHatasi("Metin modelin bellegine (8192 token) sigmiyor; parcalayin.")
        raise ModelCevapHatasi(f"Yerel model hata dondu ({durum}): {metin}".rstrip(": "))

    @staticmethod
    def _icerik(secim: dict) -> str:
        """Cevap metnini dondurur; token sinirinda kesildiyse sessizce yarim metin vermez."""
        if secim.get("finish_reason") == "length":
            raise ModelCevapHatasi(KESILDI_MESAJI)
        return ((secim.get("message") or {}).get("content") or "").strip()

    async def metin(self, istem: str, *, sistem: str | None = None, **kw: Any) -> str:
        mesajlar = ([{"role": "system", "content": sistem}] if sistem else []) + [
            {"role": "user", "content": istem}
        ]
        return self._icerik(await self.sohbet(mesajlar, **kw))

    @staticmethod
    def resim_data_url(resim: Path | bytes, mime: str | None = None) -> str:
        if isinstance(resim, Path):
            mime = mime or mimetypes.guess_type(resim.name)[0] or "image/png"
            veri = resim.read_bytes()
        else:
            veri, mime = resim, mime or "image/png"
        return f"data:{mime};base64,{base64.b64encode(veri).decode()}"

    async def ocr(
        self,
        resim: Path | bytes,
        talimat: str = OCR_TALIMATI,
        *,
        dusunme: Dusunme | None = None,
        kucult: int | None = OCR_UZUN_KENAR,
        **kw: Any,
    ) -> str:
        """dusunme None ise ayar kullanilir. OCR'da "kapali" genelde yeterli ve 5-8 kat hizli.
        kucult: uzun kenar siniri (px, Pillow gerekir); None ise gorsel oldugu gibi gider."""
        if isinstance(resim, Path):
            mime = mimetypes.guess_type(resim.name)[0] or "image/png"
            veri = resim.read_bytes()
        else:
            veri, mime = resim, "image/png"
        if kucult:
            veri, mime = resmi_kucult(veri, kucult, mime)
        icerik = [
            {"type": "text", "text": talimat},
            {"type": "image_url", "image_url": {"url": self.resim_data_url(veri, mime)}},
        ]
        secim = await self.sohbet([{"role": "user", "content": icerik}], dusunme=dusunme, **kw)
        return self._icerik(secim)

    async def ses(
        self,
        ses: Path | bytes,
        talimat: str = "Bu ses kaydini aynen yaziya dok.",
        *,
        bicim: str | None = None,
        **kw: Any,
    ) -> str:
        """Ses kaydini modele verir (yalniz Gemma 4 modelleri; en fazla ~30 sn). WAV ya da MP3.
        bicim None ise dosya uzantisindan, bytes ise "wav" kabul edilir."""
        if isinstance(ses, Path):
            bicim = bicim or ses.suffix.lower().lstrip(".")
            veri = ses.read_bytes()
        else:
            veri, bicim = ses, bicim or "wav"
        if bicim not in ("wav", "mp3"):
            raise YerelLLMHatasi(f"Desteklenmeyen ses bicimi: {bicim} (wav ya da mp3).")
        icerik = [
            {"type": "text", "text": talimat},
            {
                "type": "input_audio",
                "input_audio": {"data": base64.b64encode(veri).decode(), "format": bicim},
            },
        ]
        return self._icerik(await self.sohbet([{"role": "user", "content": icerik}], **kw))

    async def ocr_pdf(
        self,
        pdf: Path | bytes,
        talimat: str = OCR_TALIMATI,
        *,
        metin_katmani: bool = True,
        dpi: int = PDF_DPI,
        ilerleme: Ilerleme | None = None,
        **kw: Any,
    ) -> list[str]:
        """PDF'i sayfa sayfa okur, sayfa basina bir metin dondurur.
        metin_katmani=True: sayfada secilebilir yazi varsa (Word'den uretilmis PDF) onu aynen alir,
        modeli calistirmaz (aninda ve %100 dogru). Yalniz taranmis sayfalar OCR'a gider."""
        sonuc: list[str] = []
        with _pdf_ac(pdf) as belge:
            toplam = belge.page_count
            for i in range(toplam):
                sayfa = belge[i]
                yazi = sayfa.get_text().strip() if metin_katmani else ""
                if len(yazi) < 20:  # taranmis sayfa ya da yalniz sayfa no gibi kirinti
                    png = sayfa.get_pixmap(dpi=dpi).tobytes("png")
                    yazi = await self.ocr(png, talimat, **kw)
                sonuc.append(yazi)
                if ilerleme:
                    ilerleme(i + 1, toplam)
        return sonuc

    async def token_say(self, metin: str) -> int:
        """Sunucunun kendi tokenizer'i ile token sayisi (POST /tokenize)."""
        try:
            r = await self._istemci.post(f"{self.kok}/tokenize", json={"content": metin})
        except httpx.ConnectError as e:
            raise SunucuKapali() from e
        if r.status_code >= 400:
            self._hata_firlat(r.status_code, r.text)
        return len(r.json().get("tokens", []))

    async def parca_parca(
        self,
        metin: str,
        talimat: str,
        *,
        birlestir: str | None = None,
        max_karakter: int | None = None,
        ilerleme: Ilerleme | None = None,
        _derinlik: int = 0,
        **kw: Any,
    ) -> str:
        """8192 context'e sigmayan metni parcalara boler, her parcaya `talimat`i uygular.
        birlestir verilirse parca sonuclari o talimatla tek cevaba indirilir (ozet icin:
        "Bu kismi ozetleri tek ozette birlestir"); verilmezse sonuclar sirayla eklenir.
        Birlesik sonuc da sigmazsa ayni islem tekrarlanir (en fazla 3 kat).
        max_karakter None ise dusunme seviyesine gore (derin: 8000, digerleri: 12000)."""
        if max_karakter is None:
            seviye = self._seviye(kw["dusunme"]) if kw.get("dusunme") else self.dusunme
            max_karakter = DERIN_PARCA_KARAKTER if seviye == "derin" else MAX_PARCA_KARAKTER
        parcalar = parcala(metin, max_karakter)
        if not parcalar:
            return ""
        sonuclar: list[str] = []
        for i, parca in enumerate(parcalar):
            sonuclar.append(await self.metin(f"{talimat}\n\n---\n{parca}", **kw))
            if ilerleme:
                ilerleme(i + 1, len(parcalar))
        if len(sonuclar) == 1 or birlestir is None:
            return "\n\n".join(sonuclar)
        birlesik = "\n\n".join(sonuclar)
        if len(birlesik) > max_karakter:
            if _derinlik >= 2:  # sessizce kirpmak yerine acik hata
                raise ModelCevapHatasi("Metin cok uzun; parca sonuclari birlestirilemedi.")
            return await self.parca_parca(
                birlesik,
                birlestir,
                birlestir=birlestir,
                max_karakter=max_karakter,
                _derinlik=_derinlik + 1,
                **kw,
            )
        return await self.metin(f"{birlestir}\n\n---\n{birlesik}", **kw)

    async def json_cikti(
        self, istem: str | list[dict], schema: dict, *, ad: str = "cikti", **kw: Any
    ) -> Any:
        mesajlar = [{"role": "user", "content": istem}] if isinstance(istem, str) else istem
        bicim = {
            "type": "json_schema",
            "json_schema": {"name": ad, "schema": schema, "strict": True},
        }
        secim = await self.sohbet(mesajlar, response_format=bicim, **kw)
        ham = self._icerik(secim)
        try:
            return json.loads(ham)
        except json.JSONDecodeError as e:
            raise ModelCevapHatasi("Model gecerli JSON dondurmedi.") from e

    async def akis(
        self,
        mesajlar: list[dict],
        *,
        dusunme: Dusunme | None = None,
        max_tokens: int = 1024,
        dusunce_cb: Callable[[str], Any] | None = None,
        **ek: Any,
    ) -> AsyncIterator[str]:
        """Cevap parcalarini verir. dusunce_cb verilirse dusunce parcalari ona gider
        (UI'da "Dusunuyor..." panelini canli doldurmak icin)."""
        seviye = self._seviye(dusunme) if dusunme else self.dusunme
        govde = self._govde(mesajlar, seviye, max_tokens, stream=True, **ek)
        self.son_dusunce = ""
        self.son_zamanlama = {}
        try:
            async with self._istemci.stream(
                "POST",
                f"{self.adres}/chat/completions",
                json=govde,
                timeout=self._zaman_asimi(seviye),
            ) as r:
                if r.status_code >= 400:
                    await r.aread()
                    self._hata_firlat(r.status_code, r.text)
                async for satir in r.aiter_lines():
                    if not satir.startswith("data: ") or satir == "data: [DONE]":
                        continue
                    parca = json.loads(satir[6:])
                    if parca.get("timings"):
                        self.son_zamanlama = parca["timings"]
                    if parca.get("usage"):
                        self.son_kullanim = parca["usage"]
                    for c in parca.get("choices", []):
                        delta = c.get("delta") or {}
                        if dusunce := (delta.get("reasoning_content") or delta.get("reasoning")):
                            self.son_dusunce += dusunce
                            if dusunce_cb:
                                dusunce_cb(dusunce)
                        if metin := delta.get("content"):
                            yield metin
                        if c.get("finish_reason") == "length":
                            raise ModelCevapHatasi(KESILDI_MESAJI)
        except httpx.ConnectError as e:
            raise SunucuKapali() from e
        except httpx.TimeoutException as e:
            raise ModelCevapHatasi(ZAMAN_ASIMI_MESAJI) from e

    async def akis_olaylari(
        self,
        mesajlar: list[dict],
        *,
        tools: list[dict] | None = None,
        dusunme: Dusunme | None = None,
        max_tokens: int = 1024,
        **ek: Any,
    ) -> AsyncIterator[dict]:
        """Akis + arac cagrilari. Olaylar: {"tur": "dusunce"|"parca", "metin"} ve en sonda,
        model arac istediyse {"tur": "arac_cagrilari", "cagrilar": [{id, function: {name,
        arguments}}]}. llama-server arac cagrisini parca parca (index'e gore) akitir; burada
        birlestirilir. Arac calistirip donguyu kurmak cagirana kalir (bkz. SKILL.md 4.3)."""
        seviye = self._seviye(dusunme) if dusunme else self.dusunme
        if tools:
            ek["tools"] = tools
        govde = self._govde(mesajlar, seviye, max_tokens, stream=True, **ek)
        self.son_dusunce = ""
        self.son_zamanlama = {}
        cagrilar: dict[int, dict] = {}
        try:
            async with self._istemci.stream(
                "POST",
                f"{self.adres}/chat/completions",
                json=govde,
                timeout=self._zaman_asimi(seviye),
            ) as r:
                if r.status_code >= 400:
                    await r.aread()
                    self._hata_firlat(r.status_code, r.text)
                async for satir in r.aiter_lines():
                    if not satir.startswith("data: ") or satir == "data: [DONE]":
                        continue
                    parca = json.loads(satir[6:])
                    if parca.get("timings"):
                        self.son_zamanlama = parca["timings"]
                    if parca.get("usage"):
                        self.son_kullanim = parca["usage"]
                    for c in parca.get("choices", []):
                        delta = c.get("delta") or {}
                        if dusunce := (delta.get("reasoning_content") or delta.get("reasoning")):
                            self.son_dusunce += dusunce
                            yield {"tur": "dusunce", "metin": dusunce}
                        if metin := delta.get("content"):
                            yield {"tur": "parca", "metin": metin}
                        for tc in delta.get("tool_calls") or []:
                            k = cagrilar.setdefault(
                                tc.get("index", len(cagrilar)),
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                },
                            )
                            k["id"] = tc.get("id") or k["id"]
                            f = tc.get("function") or {}
                            k["function"]["name"] += f.get("name") or ""
                            k["function"]["arguments"] += f.get("arguments") or ""
                        if c.get("finish_reason") == "length":
                            raise ModelCevapHatasi(KESILDI_MESAJI)
        except httpx.ConnectError as e:
            raise SunucuKapali() from e
        except httpx.TimeoutException as e:
            raise ModelCevapHatasi(ZAMAN_ASIMI_MESAJI) from e
        if cagrilar:
            sirali = [cagrilar[i] for i in sorted(cagrilar)]
            for i, k in enumerate(sirali):
                k["id"] = k["id"] or f"cagri_{i}"
            yield {"tur": "arac_cagrilari", "cagrilar": sirali}

    async def arac_dongusu(
        self,
        mesajlar: list[dict],
        tools: list[dict],
        isleyiciler: dict[str, Isleyici],
        *,
        max_tur: int = 5,
        **kw: Any,
    ) -> str:
        """Model arac cagirdikca isleyicileri calistirir, son metin cevabini dondurur.
        `mesajlar` listesi yerinde guncellenir (gecmis olarak saklanabilir)."""
        for _ in range(max_tur):
            secim = await self.sohbet(mesajlar, tools=tools, **kw)
            mesaj = secim["message"]
            cagrilar = mesaj.get("tool_calls") or []
            if not cagrilar:
                return (mesaj.get("content") or "").strip()
            mesajlar.append(
                {"role": "assistant", "content": mesaj.get("content") or "", "tool_calls": cagrilar}
            )
            for c in cagrilar:
                ad = c["function"]["name"]
                try:
                    argumanlar = json.loads(c["function"].get("arguments") or "{}")
                    fonk = isleyiciler[ad]
                    sonuc = fonk(**argumanlar)
                    if inspect.isawaitable(sonuc):
                        sonuc = await sonuc
                except KeyError:
                    sonuc = {"hata": f"Bilinmeyen arac: {ad}"}
                except Exception as e:  # noqa: BLE001 - hata modele geri bildirilir
                    sonuc = {"hata": str(e)}
                mesajlar.append(
                    {
                        "role": "tool",
                        "tool_call_id": c.get("id", ad),
                        "content": json.dumps(sonuc, ensure_ascii=False, default=str),
                    }
                )
        raise ModelCevapHatasi(f"Arac dongusu {max_tur} turda bitmedi.")
