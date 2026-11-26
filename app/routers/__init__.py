"""FastAPI alan bazli APIRouter modulleri ve ortak istek semalari."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.agent.runner import Butce
from app.agent.workspaces import Guven, Mod
from app.exceptions import UygulamaHatasi, YerelLLMHatasi

UPLOAD_PARCA_BAYT = 1024 * 1024  # upload akisinda tek seferde okunan parca
OTURUM_BASLIGI = "x-yas-oturum"  # loopback API'de oturum kimligi (A1.9)
ACIK_YOLLAR = ("/", "/web", "/docs", "/openapi.json", "/favicon.ico")
DIKTE_MAX_SN = 30  # Gemma 4 ses girisi ~30 sn
DIKTE_UZAK = (
    "Bulut dikte kapali: ses buluta gonderilmez. Ayarlar > 'Sesli dikte bulutta' acilirsa "
    "ayri dikte modeli (OpenRouter) kullanilir."
)
DIKTE_UZAK_SESSIZ = (
    "Dikte modeli sesi anlamiyor ya da listede yok; Ayarlar'da ses girisli bir dikte modeli "
    "yazin (or. google/gemini-2.5-flash)."
)
DIKTE_SESSIZ = "Secili model sesi anlamiyor; dikte icin Gemma 4 (E4B/12B) secin."
DIKTE_TALIMATI = "Bu ses kaydini oldugu gibi yaziya dok. Yalniz soylenen metni yaz."
DIKTE_MAX_BAYT = 16000 * 2 * DIKTE_MAX_SN + 4096  # 16 kHz mono 16 bit WAV

OZET_TALIMATI = (
    "Asagidaki sohbeti, devam edilebilmesi icin ozetle. Su basliklari kullan: Amac, Alinan "
    "kararlar, Onemli bilgiler (dosya yolu, ad, sayi, kod parcasi gibi birebir gerekenler), Acik "
    "kalan isler. Uydurma; yalniz sohbette geceni yaz. Kisa ve maddeli yaz."
)
OZET_ONAY = "Anlaşıldı; bu özet üzerinden devam ediyorum."


class ProjeIstegi(BaseModel):
    yol: str = Field(min_length=1, max_length=4096)
    ad: str = Field(default="", max_length=80)
    guven: Guven = Guven.sinirli


class YolIstegi(BaseModel):
    yol: str = Field(min_length=1, max_length=4096)


class ModIstegi(BaseModel):
    mod: Mod


class GuvenIstegi(BaseModel):
    guven: Guven


class GizliProjeIstegi(BaseModel):
    gizli_proje: bool


class EditorBaglamIstegi(BaseModel):
    dosya: str = Field(min_length=1, max_length=4096)
    satir_baslangic: int = Field(default=1, ge=1)
    satir_bitis: int = Field(default=1, ge=1)
    secim: str = Field(default="", max_length=20000)
    proje_kok: str = Field(default="", max_length=4096)
    kaynak: str = Field(default="vscode", max_length=40)


class ModellerIstegi(BaseModel):
    koordinator_model: str = Field(default="", max_length=200)
    uygulayici_model: str = Field(default="", max_length=200)


class CcIzinIstegi(BaseModel):
    arac: str = Field(max_length=200)
    girdi: dict = {}
    klasor: str = Field(default="", max_length=1000)
    baglam: str = Field(default="", max_length=200)


class OnayIstegi(BaseModel):
    onayla: bool
    kapsam: Literal["tek", "sohbet", "her_zaman"] = "tek"


class GorevIstegi(BaseModel):
    hedef: str = Field(min_length=1, max_length=8000)
    kabul: list[str] = Field(default=[], max_length=20)
    butce: Butce = Field(default_factory=Butce)
    izole: bool = False  # ayri git worktree'de calis (A8.3)
    onceki: str = Field(default="", max_length=12)  # ayni sohbetteki onceki gorev (sureklilik)
    etkilesimli: bool = False  # sohbetten: ajan soru_sor ile kullaniciya soru sorabilir


class IsEmriIstegi(BaseModel):
    gorev: str = Field(default="", max_length=8000)
    baslik: str = Field(default="", max_length=120)
    proje_kok: str = Field(default="", max_length=4096)
    kaynak: Literal["elle", "sohbet"] = "elle"


class EntegreIstegi(BaseModel):
    test_komutu: str = Field(default="", max_length=2000)


class GorevMesaji(BaseModel):
    metin: str = Field(min_length=1, max_length=4000)


class HafizaIstegi(BaseModel):
    metin: str = Field(min_length=1, max_length=1000)
    kapsam: str = Field(default="genel", max_length=40)
    guven: str = "orta"
    gecerlilik: str | None = None


class KararIstegi(BaseModel):
    adim: int
    karar: str


class GeriAlIstegi(BaseModel):
    yollar: list[str] = []


class HunkIstegi(BaseModel):
    yol: str
    hunklar: list[int] = Field(min_length=1)


class GirdiIstegi(BaseModel):
    metin: str = Field(max_length=10000)


class KartKomutIstegi(BaseModel):
    komut: str = Field(min_length=1, max_length=2000)
    onay: bool = False  # arayuz modalinda kullanici "Calistir" dedi


class AdIstegi(BaseModel):
    baslik: str


class AjanRunKaydi(BaseModel):
    run: str = Field(min_length=1, max_length=64)
    metin: str = ""


class SkillIceIstegi(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class SkillIceAdIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=64)


class SkillIceKurIstegi(BaseModel):
    adlar: list[str] = Field(min_length=1, max_length=50)
    riskli_onay: bool = False
    yeni_adlar: dict[str, str] = {}


class AltOturumIstegi(BaseModel):
    baslik: str = Field(min_length=1, max_length=200)
    kaynak: str = Field(default="", max_length=64)


class SonrakiOneriIstegi(BaseModel):
    kullanici: str = Field(default="", max_length=4000)
    asistan: str = Field(default="", max_length=6000)


class GeriSarIstegi(BaseModel):
    mesaj_id: str = Field(default="", max_length=64)
    run: str = Field(default="", max_length=64)


class OneriRedIstegi(BaseModel):
    kaynak: str = Field(min_length=1, max_length=64)
    karar: str = Field(default="reddedildi", pattern=r"^(reddedildi|is:[0-9a-f]{12})$")


class AnahtarIstegi(BaseModel):
    anahtar: str = Field(max_length=300)


class SaglayiciIstegi(BaseModel):
    anahtar: str = Field(default="", max_length=400)
    adres: str = Field(default="", max_length=300)


class ModelIstegi(BaseModel):
    model: str | None = None


class DurdurIstegi(BaseModel):
    harici: bool = False


class OllamaIndirIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=200)


class IndirIstegi(BaseModel):
    repo: str = Field(pattern=r"^[\w.-]+/[\w.-]+$", max_length=200)


class TalimatIstegi(BaseModel):
    metin: str = Field(default="", max_length=40000)


class SkillIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=64)
    aciklama: str = Field(min_length=1, max_length=600)
    icerik: str = Field(min_length=1, max_length=40000)
    surum: str = Field(default="", max_length=40)
    gereken_araclar: list[str] = Field(default=[], max_length=30)


class SkillDurumIstegi(BaseModel):
    acik: bool


def dogrulama_mesaji(e: ValidationError) -> str:
    """pydantic hatasini kullaniciya gosterilebilir kisa metne cevirir."""
    return (
        "; ".join(str(h.get("msg", "")).removeprefix("Value error, ") for h in e.errors())
        or "Gecersiz deger."
    )


def sse(olaylar: AsyncIterator[dict]) -> StreamingResponse:
    async def akis() -> AsyncIterator[str]:
        try:
            async for olay in olaylar:
                yield f"data: {json.dumps(olay, ensure_ascii=False, default=str)}\n\n"
        except (UygulamaHatasi, YerelLLMHatasi) as e:
            mesaj = e.mesaj if isinstance(e, UygulamaHatasi) else str(e)
            yield f"data: {json.dumps({'tur': 'hata', 'mesaj': mesaj}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        akis(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
