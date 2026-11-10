"""Kalici ajan dongusu (A3): model -> arguman dogrulama -> izin -> arac -> gozlem -> dogrulama.

Kurallar:
- Run ve her adim diske ATOMIK yazilir; uygulama kapansa da kaldigi yer bellidir.
- Yan etkili aractan ONCE "niyet" kaydi yazilir. Cokme sonrasi "niyet"te kalan adim BELIRSIZ
  olur ve otomatik TEKRARLANMAZ; kullanici karar verir (tamamlandi say / atla / tekrarla).
  Genel exactly-once garantisi YOKTUR.
- Butce: adim, sure, token. Ayni basarisiz cagri ve ilerlemesizlik sinirli. Sinirsiz dongu yok.
- `basarili` icin arac kaniti zorunlu (gorevi_bitir + basarili adim numaralari). Kanit yoksa
  `dogrulanmadi`; kanit olarak gosterilen test basarisizsa bitirme reddedilir.
- Gizli dusunce zinciri kaydedilmez; yalniz eylem, kisa guncelleme ve kanit.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.agent.ozet import mesaj_token, ozetle_gerekirse
from app.agent.yetenek import ModelYetenegi, butce_dokumu, dogrula, tahmini_token
from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

YAN_ETKILI = {
    "proje_dosya_yaz",
    "proje_dosya_yama",
    "proje_dosya_tasi",
    "proje_dosya_sil",
    "komut_calistir",
    "komut_girdi",
    "komut_durdur",
    "git_dal",
    "git_commit",
}
DEGISTIREN = {"proje_dosya_yaz", "proje_dosya_yama", "proje_dosya_tasi", "proje_dosya_sil"}
VARSAYILAN_BAGLAM = 16384
CEVAP_TOKEN = 2048
GECICI_HATA_DENEME = 2  # model kesintisinde sinirli yeniden deneme
BEKLEME_SN = (5.0, 15.0)  # istek siniri (429) icin kisa bekleme yetmiyor
SONUC_SINIRI = 6000


class RunDurum(StrEnum):
    calisiyor = "calisiyor"
    duraklatildi = "duraklatildi"
    onay_bekliyor = "onay_bekliyor"
    karar_bekliyor = "karar_bekliyor"  # cokme sonrasi belirsiz yan etki
    iptal = "iptal"
    basarili = "basarili"
    dogrulanmadi = "dogrulanmadi"
    basarisiz = "basarisiz"


BITMIS = {RunDurum.iptal, RunDurum.basarili, RunDurum.dogrulanmadi, RunDurum.basarisiz}


class AdimDurum(StrEnum):
    sirada = "sirada"
    niyet = "niyet"  # yan etki baslatildi, sonucu yazilmadi
    tamam = "tamam"
    hata = "hata"
    onay_bekliyor = "onay_bekliyor"
    reddedildi = "reddedildi"
    belirsiz = "belirsiz"
    atlandi = "atlandi"
    tekrarla = "tekrarla"


class Butce(BaseModel):
    max_adim: int = Field(default=40, ge=1, le=500)
    max_sure_sn: int = Field(default=1800, ge=10, le=24 * 3600)
    # cagri basina gonderilen baglamin TOPLAMI; 32K baglamda ~60 cagri
    max_token: int = Field(default=2_000_000, ge=1000, le=20_000_000)
    max_ayni_hata: int = Field(default=2, ge=1, le=10)
    max_ilerlemesiz: int = Field(default=3, ge=1, le=10)


class Kullanim(BaseModel):
    adim: int = 0
    token: int = 0
    sure_sn: float = 0.0
    model_cagrisi: int = 0


class PlanAdimi(BaseModel):
    baslik: str
    durum: str = "bekliyor"  # bekliyor | suruyor | tamam | atlandi
    kanit: str = ""


class Adim(BaseModel):
    no: int
    arac: str
    argumanlar: dict = {}
    cagri_id: str = ""
    durum: AdimDurum = AdimDurum.sirada
    yan_etkili: bool = False
    sonuc: str = ""
    onay_id: str = ""
    cikis_kodu: int | None = None  # komut adimlarinda gercek cikis kodu
    dosya: str = ""  # okunan/yazilan dosya (ozet icin; kirpilmis sonuctan parse edilmez)
    hash: str = ""
    checkpoint: str = ""  # yazma adiminin checkpoint kimligi (diff / geri alma ekrani)
    zaman: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class Sonuc(BaseModel):
    ozet: str = ""
    kanit: list[int] = []
    dogrulandi: bool = False


class Run(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    hedef: str
    kabul: list[str] = []
    model: str = ""
    durum: RunDurum = RunDurum.calisiyor
    butce: Butce = Field(default_factory=Butce)
    kullanim: Kullanim = Field(default_factory=Kullanim)
    deneme: int = 1
    plan: list[PlanAdimi] = []
    adimlar: list[Adim] = []
    mesajlar: list[dict] = []  # modele giden gecmis (sistem haric)
    kuyruk: list[str] = []  # calisirken gelen kullanici mesajlari
    guncellemeler: list[str] = []  # kisa kullanici guncellemeleri
    sonuc: Sonuc = Field(default_factory=Sonuc)
    hata: str = ""
    ilerlemesiz: int = 0
    baglam: dict = {}  # son model cagrisinin butce dokumu (A4.1)
    ozet_sayisi: int = 0
    parent: str = ""  # alt ajan ise ebeveyn run kimligi
    izinli_araclar: list[str] = []  # alt ajanin dar arac seti
    sahip_dosyalar: list[str] = []  # alt ajanin yazabilecegi dosyalar (goreli yol)
    cocuklar: list[str] = []
    calisma_koku: str = ""  # izole worktree (A8.3); bos = proje kokunde
    dal: str = ""
    hata_sayaci: dict[str, int] = {}
    olusturma: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    guncelleme: str = ""

    def ozet(self) -> dict:
        return self.model_dump(mode="json", exclude={"mesajlar", "hata_sayaci"})


def _f(ad: str, aciklama: str, ozellikler: dict, zorunlu: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": ad,
            "description": aciklama,
            "parameters": {"type": "object", "properties": ozellikler, "required": zorunlu},
        },
    }


RUNNER_ARACLARI = [
    _f(
        "plan_guncelle",
        "Gorev planini yazar/gunceller. Her adim: baslik, durum (bekliyor|suruyor|tamam|atlandi), "
        "kanit (ornek: 'adim 7: pytest gecti').",
        {"adimlar": {"type": "array", "items": {"type": "object"}}},
        ["adimlar"],
    ),
    _f(
        "gorevi_bitir",
        "Gorev bittiginde cagir. `kanit_adimlari`: hedefin saglandigini gosteren BASARILI arac "
        "adimlarinin numaralari (ornek: testin gectigi komut_calistir adimi).",
        {
            "ozet": {"type": "string"},
            "kanit_adimlari": {"type": "array", "items": {"type": "integer"}},
        },
        ["ozet", "kanit_adimlari"],
    ),
]
META = {"plan_guncelle", "gorevi_bitir"}

# A8.1 alt ajan: ayri baglam, dar arac seti, sahip olunan dosyalar, ebeveynden KESILEN butce.
ALT_AJAN_ARACI = _f(
    "alt_ajan",
    "Ayri baglamli bir alt ajana dar bir is ver (or. arastirma, tek dosyada degisiklik, test). "
    "`araclar`: alt ajanin kullanabilecegi arac adlari (en az yetki). `dosyalar`: yazabilecegi "
    "dosyalar (bos = yazamaz). Alt ajan bitince sonucunu (durum, ozet, kanit) doner. "
    "Butcesi senin kalan butcenden duser.",
    {
        "gorev": {"type": "string"},
        "araclar": {"type": "array", "items": {"type": "string"}},
        "dosyalar": {"type": "array", "items": {"type": "string"}},
        "max_adim": {"type": "integer"},
    },
    ["gorev", "araclar"],
)
YAZAN_ARACLAR = {"proje_dosya_yaz", "proje_dosya_yama", "proje_dosya_tasi", "proje_dosya_sil"}

SISTEM = """Sen bir yazilim ajanisin. Gorevi ARACLARLA yap; tahmin etme, oku ve dogrula.
Kurallar:
- Ilk is plan_guncelle ile kisa bir plan yaz; ilerledikce guncelle.
- Dosyayi degistirmeden once oku; yama icin beklenen_hash kullan.
- Degisiklikten sonra testi/komutu calistirip sonucu kontrol et.
- Bir cagri reddedilirse AYNISINI tekrarlama; farkli bir yol planla.
- Bitince gorevi_bitir'i, hedefi kanitlayan basarili adim numaralariyla cagir.
- Kullaniciya kisa yaz: ne yaptin, siradaki adim, varsa engel. Uzun aciklama yapma."""


def _norm_yol(yol: str) -> str:
    return str(yol).replace("\\", "/").strip().lstrip("./").lower()


def _json_onar(ham: str) -> dict | None:
    """Sinirli onarim: kod citi, sondaki virgul, metin icindeki ilk {...}."""
    s = ham.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        s = m.group(0)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    try:
        v = json.loads(s)
    except json.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None


class RunDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.dizin = veri_dizini / "runs"
        self.dizin.mkdir(parents=True, exist_ok=True)

    def _yol(self, run_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", run_id or ""):
            raise Bulunamadi("Gorev bulunamadi.")
        return self.dizin / f"{run_id}.json"

    def kaydet(self, run: Run) -> Run:
        run.guncelleme = datetime.now().isoformat(timespec="seconds")
        json_yaz(self._yol(run.id), run.model_dump(mode="json"))
        return run

    def getir(self, run_id: str) -> Run:
        ham = json_oku(self._yol(run_id), None)
        if ham is None:
            raise Bulunamadi("Gorev bulunamadi.")
        return Run(**ham)

    def liste(self) -> list[Run]:
        runlar = []
        for p in self.dizin.glob("*.json"):
            try:
                runlar.append(Run(**json_oku(p, {})))
            except (ValueError, TypeError):
                continue
        return sorted(runlar, key=lambda r: r.olusturma, reverse=True)

    def kurtar(self) -> list[str]:
        """Uygulama acilisinda: 'calisiyor' kalan run'lar yarim kalmistir.
        'niyet'teki yan etkili adim BELIRSIZ olur ve kullanici kararina birakilir."""
        degisen = []
        for run in self.liste():
            if run.durum is not RunDurum.calisiyor:
                continue
            belirsiz = False
            for a in run.adimlar:
                if a.durum is AdimDurum.niyet:
                    a.durum = AdimDurum.belirsiz
                    a.sonuc = "Uygulama bu adim sirasinda kapandi; sonucu bilinmiyor."
                    belirsiz = True
            run.durum = RunDurum.karar_bekliyor if belirsiz else RunDurum.duraklatildi
            run.hata = "Uygulama kapandi; gorev durduruldu."
            self.kaydet(run)
            degisen.append(run.id)
        return degisen


# (sistem metni, arac semalari, isleyiciler) - her calismada guncel proje/izinlerle uretilir
AracSaglayici = Callable[[str], tuple[str, list[dict], dict[str, Callable[..., Any]]]]
LLMSaglayici = Callable[[], AbstractAsyncContextManager[Any]]


class AgentRunner:
    def __init__(
        self,
        depo: RunDeposu,
        araclar: AracSaglayici,
        llm: LLMSaglayici,
        onay_durumu: Callable[[str], str] | None = None,
        bekleme: tuple[float, ...] = BEKLEME_SN,
        yetenek: Callable[[], ModelYetenegi] | None = None,
        hafiza: Callable[[], str] | None = None,
        hooks: Any = None,  # HookDeposu
    ) -> None:
        self.depo = depo
        self.araclar = araclar
        self.llm = llm
        self.onay_durumu = onay_durumu or (lambda _id: "bekliyor")
        self.bekleme = bekleme
        self.yetenek = yetenek
        self.hafiza = hafiza or (lambda: "")
        self.hooks = hooks
        self.araclar_kok: Callable[[str, str], tuple] | None = None
        self._gorevler: dict[str, asyncio.Task] = {}
        self._iptal: set[str] = set()
        self._duraklat: set[str] = set()
        self._aracta: set[str] = set()
        self._kilit = asyncio.Lock()  # tek yerel model: run'lar sirayla model kullanir

    # ---------------------------------------------------------------- kontrol
    def calisiyor_mu(self, run_id: str) -> bool:
        g = self._gorevler.get(run_id)
        return bool(g and not g.done())

    async def baslat(
        self,
        hedef: str,
        kabul: list[str] | None = None,
        butce: Butce | None = None,
        model: str = "",
        izole_kur: Callable[[str], tuple[str, str]] | None = None,
    ) -> Run:
        if self.yetenek is not None:  # aracsiz modelle gorev baslamaz (acik hata)
            dogrula(self.yetenek(), araclar_gerekli=True)
        if not hedef.strip():
            raise UygulamaHatasi("Gorev hedefi bos olamaz.")
        run = Run(hedef=hedef.strip(), kabul=kabul or [], butce=butce or Butce(), model=model)
        kabul_metni = "\n".join(f"- {k}" for k in run.kabul) or "- (belirtilmedi: hedefi kanitla)"
        run.mesajlar = [
            {"role": "user", "content": f"GOREV: {run.hedef}\n\nKABUL KOSULLARI:\n{kabul_metni}"}
        ]
        await self._hook("run_baslangic", {"run": run.id, "hedef": run.hedef})  # engel: baslamaz
        if izole_kur is not None:  # A8.3: ayri worktree + ajan/<id> dali
            run.calisma_koku, run.dal = izole_kur(run.id)
        self.depo.kaydet(run)
        self._calistir(run.id)
        return run

    async def _hook(self, olay: str, veri: dict) -> None:
        """Guvenlik hook'u engellerse islem UygulamaHatasi ile durur."""
        if self.hooks is None:
            return
        h = await asyncio.to_thread(self.hooks.tetikle, olay, veri)
        if not h.izin:
            raise UygulamaHatasi(h.neden)

    def _calistir(self, run_id: str) -> None:
        if self.calisiyor_mu(run_id):
            return
        self._iptal.discard(run_id)
        self._duraklat.discard(run_id)
        self._gorevler[run_id] = asyncio.create_task(self._dongu(run_id))

    async def mesaj(self, run_id: str, metin: str) -> Run:
        """Kullanici yonlendirmesi: guvenli sinirda (sonraki model cagrisi oncesi) islenir."""
        if not metin.strip():
            raise UygulamaHatasi("Bos mesaj gonderilemez.")
        run = self.depo.getir(run_id)
        if run.durum in BITMIS:
            raise UygulamaHatasi("Biten goreve mesaj eklenemez; 'tekrar' ile yeniden baslatin.")
        await self._hook("prompt", {"run": run_id, "metin": metin})
        run.kuyruk.append(metin.strip()[:4000])
        return self.depo.kaydet(run)

    async def duraklat(self, run_id: str) -> Run:
        self.depo.getir(run_id)
        self._duraklat.add(run_id)
        if not self.calisiyor_mu(run_id):
            run = self.depo.getir(run_id)
            if run.durum is RunDurum.calisiyor:
                run.durum = RunDurum.duraklatildi
                self.depo.kaydet(run)
        await self._bitmesini_bekle(run_id)
        return self.depo.getir(run_id)

    async def iptal(self, run_id: str) -> Run:
        """Oncelikli kanal: model beklenirken hemen keser; arac calisirken araci bitirir."""
        run = self.depo.getir(run_id)
        self._iptal.add(run_id)
        g = self._gorevler.get(run_id)
        if g and not g.done() and run_id not in self._aracta:
            g.cancel()
        await self._bitmesini_bekle(run_id)
        run = self.depo.getir(run_id)
        if run.durum not in BITMIS:
            run.durum = RunDurum.iptal
            run.hata = "Kullanici iptal etti."
            self.depo.kaydet(run)
        return run

    async def devam(self, run_id: str) -> Run:
        run = self.depo.getir(run_id)
        if run.durum in BITMIS:
            raise UygulamaHatasi("Biten gorev devam ettirilemez; 'tekrar' kullanin.")
        if any(a.durum is AdimDurum.belirsiz for a in run.adimlar):
            raise UygulamaHatasi("Sonucu belirsiz adim var; once karar verin.")
        run.durum = RunDurum.calisiyor
        run.hata = ""
        self.depo.kaydet(run)
        self._calistir(run_id)
        return run

    async def tekrar(self, run_id: str) -> Run:
        """Biten (basarisiz/iptal/dogrulanmadi) gorevi gecmisiyle YENI denemede surdurur."""
        run = self.depo.getir(run_id)
        if run.durum not in BITMIS - {RunDurum.basarili}:
            raise UygulamaHatasi("Yalniz basarisiz, iptal ya da dogrulanmamis gorev tekrarlanir.")
        if any(a.durum is AdimDurum.belirsiz for a in run.adimlar):
            raise UygulamaHatasi("Sonucu belirsiz adim var; once karar verin.")
        run.deneme += 1
        run.kullanim = Kullanim()
        run.ilerlemesiz = 0
        run.hata_sayaci = {}
        run.mesajlar.append(
            {
                "role": "user",
                "content": f"Onceki deneme '{run.durum}' bitti ({run.hata or run.sonuc.ozet}). "
                "Durumu kontrol edip goreve devam et.",
            }
        )
        run.durum, run.hata, run.sonuc = RunDurum.calisiyor, "", Sonuc()
        self.depo.kaydet(run)
        self._calistir(run_id)
        return run

    async def karar(self, run_id: str, adim_no: int, karar: str) -> Run:
        """Belirsiz yan etki icin kullanici karari: tamamlandi | atla | tekrarla."""
        run = self.depo.getir(run_id)
        a = next((x for x in run.adimlar if x.no == adim_no), None)
        if a is None or a.durum is not AdimDurum.belirsiz:
            raise UygulamaHatasi("Bu adim karar beklemiyor.")
        if karar == "tamamlandi":
            a.durum = AdimDurum.tamam
            self._arac_mesaji(run, a, {"not": "Kullanici bu adimin tamamlandigini onayladi."})
        elif karar == "atla":
            a.durum = AdimDurum.atlandi
            self._arac_mesaji(run, a, {"hata": "Uygulanmadi kabul edildi; durumu kontrol et."})
        elif karar == "tekrarla":
            a.durum = AdimDurum.tekrarla
        else:
            raise UygulamaHatasi("Karar: tamamlandi, atla ya da tekrarla.")
        if not any(x.durum is AdimDurum.belirsiz for x in run.adimlar):
            run.durum = RunDurum.duraklatildi
        return self.depo.kaydet(run)

    async def _bitmesini_bekle(self, run_id: str, sure: float = 30.0) -> None:
        g = self._gorevler.get(run_id)
        if g and not g.done():
            await asyncio.wait({g}, timeout=sure)

    async def kapat(self) -> None:
        for run_id in list(self._gorevler):
            if self.calisiyor_mu(run_id):
                self._duraklat.add(run_id)
                await self._bitmesini_bekle(run_id, 5.0)

    # ---------------------------------------------------------------- dongu
    def _arac_mesaji(self, run: Run, a: Adim, sonuc: Any) -> None:
        if isinstance(sonuc, dict) and isinstance(sonuc.get("cikis_kodu"), int):
            a.cikis_kodu = sonuc["cikis_kodu"]  # kanit kontrolu kirpilmis metne guvenmez
        if isinstance(sonuc, dict) and (h := sonuc.get("yeni_hash") or sonuc.get("hash")):
            a.dosya, a.hash = str(sonuc.get("goreli") or sonuc.get("dosya") or ""), str(h)
        if isinstance(sonuc, dict) and isinstance(sonuc.get("checkpoint"), str):
            a.checkpoint = sonuc["checkpoint"]
        # model kanit gosterirken adim numarasini bilmeli; yoksa numara uyduruyor (canli bulgu)
        sonuc = (
            {"adim": a.no, **sonuc} if isinstance(sonuc, dict) else {"adim": a.no, "sonuc": sonuc}
        )
        metin = json.dumps(sonuc, ensure_ascii=False, default=str)
        if len(metin) > SONUC_SINIRI:
            metin = metin[:SONUC_SINIRI] + '..."[kesildi]"'
        a.sonuc = metin[:2000]
        run.mesajlar.append({"role": "tool", "tool_call_id": a.cagri_id, "content": metin})

    def _butce_asildi(self, run: Run) -> str:
        b, k = run.butce, run.kullanim
        if k.adim >= b.max_adim:
            return f"Adim butcesi doldu ({b.max_adim})."
        if k.sure_sn >= b.max_sure_sn:
            return f"Sure butcesi doldu ({b.max_sure_sn} sn)."
        if k.token >= b.max_token:
            return f"Token butcesi doldu ({b.max_token})."
        return ""

    async def _dongu(self, run_id: str) -> None:
        run = self.depo.getir(run_id)
        bas = time.monotonic() - run.kullanim.sure_sn
        try:
            if run.calisma_koku and self.araclar_kok is not None:  # izole worktree araclari
                sistem, semalar, isleyiciler = self.araclar_kok(run.hedef, run.calisma_koku)
            else:
                sistem, semalar, isleyiciler = self.araclar(run.hedef)
            if hafiza := self.hafiza():
                sistem = f"{sistem}\n\n{hafiza}".strip()
            semalar = [*semalar, *RUNNER_ARACLARI]
            if run.parent:  # alt ajan: yalniz verilen araclar; alt ajan acamaz (derinlik 1)
                izinli = set(run.izinli_araclar) | META
                semalar = [s for s in semalar if s["function"]["name"] in izinli]
                isleyiciler = {
                    k: self._sahiplik_sarmali(run, k, f)
                    for k, f in isleyiciler.items()
                    if k in izinli
                }
            else:
                semalar = [*semalar, ALT_AJAN_ARACI]
            run.durum = RunDurum.calisiyor
            self.depo.kaydet(run)
            while True:
                run.kullanim.sure_sn = round(time.monotonic() - bas, 1)
                if run_id in self._iptal:
                    run.durum, run.hata = RunDurum.iptal, "Kullanici iptal etti."
                    break
                if run_id in self._duraklat:
                    run.durum = RunDurum.duraklatildi
                    break
                if neden := self._butce_asildi(run):
                    run.durum, run.hata = RunDurum.basarisiz, neden
                    break
                # 1) bekleyen arac adimlari (onay sonrasi, tekrarla, yarim kalan sira)
                if await self._bekleyenleri_isle(run, isleyiciler):
                    break  # onay bekleniyor ya da gorev bitti
                if run.durum is not RunDurum.calisiyor:
                    break
                if run_id in self._iptal or run_id in self._duraklat:
                    continue  # bayraklar dongu basinda islenir; model cagrilmaz
                # 2) kullanici yonlendirmeleri: guvenli sinirda
                while run.kuyruk:
                    m = run.kuyruk.pop(0)
                    run.mesajlar.append(
                        {"role": "user", "content": f"[Kullanici yonlendirmesi] {m}"}
                    )
                    run.guncellemeler.append(f"Kullanici: {m[:200]}")
                self.depo.kaydet(run)
                # 3) model
                mesaj = await self._model(run, sistem, semalar)
                if mesaj is None:
                    break
                cagrilar = mesaj.get("tool_calls") or []
                icerik = (mesaj.get("content") or "").strip()
                if icerik:
                    run.guncellemeler.append(icerik[:500])
                if not cagrilar:
                    run.mesajlar.append({"role": "assistant", "content": icerik})
                    run.ilerlemesiz += 1
                    if run.ilerlemesiz >= run.butce.max_ilerlemesiz:
                        run.durum = RunDurum.dogrulanmadi
                        run.sonuc = Sonuc(ozet=icerik or "Model arac kullanmadan durdu.")
                        run.hata = "Ilerleme yok: model gorevi_bitir ile kanit sunmadi."
                        break
                    run.mesajlar.append(
                        {
                            "role": "user",
                            "content": "Devam et: siradaki araci cagir. Bittiyse gorevi_bitir'i "
                            "kanit adim numaralariyla cagir.",
                        }
                    )
                    self.depo.kaydet(run)
                    continue
                run.ilerlemesiz = 0
                run.mesajlar.append(
                    {"role": "assistant", "content": icerik, "tool_calls": cagrilar}
                )
                for c in cagrilar:
                    run.adimlar.append(self._adim_olustur(run, c))
                self.depo.kaydet(run)
        except asyncio.CancelledError:
            run.durum, run.hata = RunDurum.iptal, "Kullanici iptal etti."
            for a in run.adimlar:  # iptal model beklerken olur; niyet kalmamali
                if a.durum is AdimDurum.niyet:
                    a.durum = AdimDurum.belirsiz
            raise
        except Exception as e:  # noqa: BLE001 - dongu cokmesi run'a yazilir, uygulama dusmez
            logger.exception("Ajan dongusu coktu: {}", run_id)
            run.durum, run.hata = RunDurum.basarisiz, f"Beklenmeyen hata: {e}"
        finally:
            run.kullanim.sure_sn = round(time.monotonic() - bas, 1)
            self.depo.kaydet(run)
            self._iptal.discard(run_id)
            self._duraklat.discard(run_id)
            if self.hooks is not None and run.durum in BITMIS:  # bilgilendirme; hata yutulur
                await asyncio.to_thread(
                    self.hooks.tetikle, "run_bitis", {"run": run.id, "durum": str(run.durum)}
                )

    def _adim_olustur(self, run: Run, c: dict) -> Adim:
        ad = (c.get("function") or {}).get("name", "")
        ham = (c.get("function") or {}).get("arguments") or "{}"
        if isinstance(ham, dict):
            arg: dict | None = ham
        else:
            try:
                arg = json.loads(ham)
                arg = arg if isinstance(arg, dict) else None
            except json.JSONDecodeError:
                arg = _json_onar(ham)
        a = Adim(
            no=len(run.adimlar) + 1,
            arac=ad,
            argumanlar=arg if arg is not None else {"_ham": str(ham)[:500]},
            cagri_id=c.get("id") or uuid.uuid4().hex[:8],
            yan_etkili=ad in YAN_ETKILI,
        )
        if arg is None:  # onarilamadi: calistirma, modele bildir
            a.durum = AdimDurum.hata
            self._arac_mesaji(
                run, a, {"hata": "Gecersiz arguman JSON'u; gecerli JSON ile tekrar gonder."}
            )
        return a

    def _baglami_hazirla(self, run: Run, sistem: str, semalar: list[dict]) -> bool:
        """Butceyi hesaplar; gerekirse ozetler, sonra eski arac sonuclarini kisaltir.
        Hala sigmiyorsa istegi KORLEMESINE gondermez: gorev basarisiz olur (A0.6, A4.1)."""
        baglam = self.yetenek().baglam if self.yetenek else VARSAYILAN_BAGLAM
        sabit = tahmini_token(sistem) + tahmini_token(json.dumps(semalar, ensure_ascii=False))
        mesaj_siniri = baglam - sabit - CEVAP_TOKEN
        if mesaj_siniri <= 0:
            run.durum = RunDurum.basarisiz
            run.hata = f"Baglam ({baglam}) talimat ve arac tanimlarina bile yetmiyor; buyutun."
            return False
        if ozetle_gerekirse(run, mesaj_siniri, self.depo.dizin / f"{run.id}.arsiv.jsonl"):
            run.ozet_sayisi += 1
            run.guncellemeler.append("Baglam doldu: eski adimlar ozetlendi (arsivde duruyor).")
            if self.hooks is not None:  # bilgilendirme (senkron: _baglami_hazirla async degil)
                self.hooks.tetikle("compact", {"run": run.id, "ozet_sayisi": run.ozet_sayisi})
        for m in run.mesajlar[:-2]:  # son iki mesaj ham kalir
            if mesaj_token(run.mesajlar) <= mesaj_siniri:
                break
            if m.get("role") == "tool" and len(str(m.get("content", ""))) > 300:
                m["content"] = json.dumps(
                    {"truncated": True, "not": "Eski arac sonucu baglama sigmadi; gerekirse "
                     "araci tekrar cagir."}, ensure_ascii=False,
                )  # fmt: skip
        run.baglam = butce_dokumu(sistem, semalar, run.mesajlar, CEVAP_TOKEN, baglam)
        if run.baglam["toplam"] > baglam:
            run.durum = RunDurum.basarisiz
            run.hata = f"Baglam yetersiz ({run.baglam['toplam']}/{baglam} token); buyutun."
            return False
        return True

    async def _model(self, run: Run, sistem: str, semalar: list[dict]) -> dict | None:
        from app.services.yerel_llm import ModelCevapHatasi, SunucuKapali

        sistem_metni = f"{SISTEM}\n\n{sistem}".strip()
        if not self._baglami_hazirla(run, sistem_metni, semalar):
            return None
        gonderilen = [{"role": "system", "content": sistem_metni}, *run.mesajlar]
        for deneme in range(GECICI_HATA_DENEME + 1):
            try:
                async with self._kilit, self.llm() as llm:
                    secim = await llm.sohbet(gonderilen, tools=semalar, max_tokens=CEVAP_TOKEN)
                break
            except (SunucuKapali, ModelCevapHatasi) as e:
                gecici = (
                    isinstance(e, SunucuKapali)
                    or "zamaninda" in str(e)
                    or getattr(e, "gecici", False)  # or. OpenRouter 429/5xx
                )
                if not gecici or deneme == GECICI_HATA_DENEME:
                    run.durum, run.hata = RunDurum.basarisiz, f"Model hatasi: {e}"
                    return None
                run.guncellemeler.append(f"Model kesintisi, yeniden deneniyor ({deneme + 1}).")
                self.depo.kaydet(run)
                await asyncio.sleep(self.bekleme[min(deneme, len(self.bekleme) - 1)])
        run.kullanim.model_cagrisi += 1
        mesaj = secim.get("message") or {}
        run.kullanim.token += tahmini_token(json.dumps(gonderilen, ensure_ascii=False)) + (
            tahmini_token(json.dumps(mesaj, ensure_ascii=False))
        )
        return mesaj

    async def _bekleyenleri_isle(self, run: Run, isleyiciler: dict) -> bool:
        """Sirada/onay bekleyen/tekrarlanacak adimlari sirayla isler.
        True: dongu durmali (onay bekleniyor ya da gorev bitti)."""
        for a in run.adimlar:
            if a.durum not in (AdimDurum.sirada, AdimDurum.onay_bekliyor, AdimDurum.tekrarla):
                continue
            if run.id in self._iptal or run.id in self._duraklat:
                return False
            if a.durum is AdimDurum.onay_bekliyor:
                karar = self.onay_durumu(a.onay_id)
                if karar == "bekliyor":
                    run.durum = RunDurum.onay_bekliyor
                    return True
                if karar == "reddedildi":
                    a.durum = AdimDurum.reddedildi
                    self._arac_mesaji(
                        run,
                        a,
                        {
                            "hata": "Kullanici bu islemi REDDETTI. Ayni cagriyi tekrarlama; "
                            "plani degistir.",
                            "karar": "ret",
                        },
                    )
                    self.depo.kaydet(run)
                    continue
            await self._adim_calistir(run, a, isleyiciler)
            if a.durum is AdimDurum.onay_bekliyor:
                run.durum = RunDurum.onay_bekliyor
                self.depo.kaydet(run)
                return True
            if run.durum in BITMIS:
                return True
        return False

    async def _adim_calistir(self, run: Run, a: Adim, isleyiciler: dict) -> None:
        run.kullanim.adim += 1
        anahtar = f"{a.arac}:{json.dumps(a.argumanlar, sort_keys=True, ensure_ascii=False)}"
        if run.hata_sayaci.get(anahtar, 0) >= run.butce.max_ayni_hata:
            a.durum = AdimDurum.hata
            self._arac_mesaji(
                run,
                a,
                {"hata": f"Bu cagri {run.hata_sayaci[anahtar]} kez basarisiz oldu; CALISTIRILMADI. "
                 "Farkli bir yol dene."},
            )  # fmt: skip
            self.depo.kaydet(run)
            return
        if a.arac == "plan_guncelle":
            self._plan(run, a)
            return
        if a.arac == "alt_ajan" and not run.parent:
            await self._alt_ajan(run, a)
            return
        if a.arac == "gorevi_bitir":
            self._bitir(run, a)
            return
        fonk = isleyiciler.get(a.arac)
        if fonk is None:
            a.durum = AdimDurum.hata
            self._arac_mesaji(run, a, {"hata": f"Bilinmeyen ya da izin verilmeyen arac: {a.arac}"})
            self.depo.kaydet(run)
            return
        if self.hooks is not None:  # pre_tool: guvenlik hook'u engelleyebilir (fail-closed)
            h = await asyncio.to_thread(
                self.hooks.tetikle, "pre_tool",
                {"run": run.id, "arac": a.arac, "argumanlar": a.argumanlar}, arac=a.arac,
            )  # fmt: skip
            if not h.izin:
                a.durum = AdimDurum.reddedildi
                run.hata_sayaci[anahtar] = run.hata_sayaci.get(anahtar, 0) + 1
                ret = {"hata": h.neden, "karar": "ret", "not": "Ayni cagriyi tekrarlama."}
                self._arac_mesaji(run, a, ret)
                self.depo.kaydet(run)
                return
        if a.yan_etkili:  # NIYET once diske: cokerse belirsiz kalir, otomatik tekrar edilmez
            a.durum = AdimDurum.niyet
            self.depo.kaydet(run)
        self._aracta.add(run.id)
        try:
            sonuc = await asyncio.to_thread(fonk, **a.argumanlar)
        except (TypeError, ValueError, OSError, UygulamaHatasi) as e:
            sonuc = {"hata": f"{type(e).__name__}: {e}"}
        finally:
            self._aracta.discard(run.id)
        if isinstance(sonuc, dict) and sonuc.get("karar") == "onay_bekliyor":
            a.durum = AdimDurum.onay_bekliyor
            a.onay_id = (sonuc.get("onay") or {}).get("id", "")
            run.guncellemeler.append(f"Onay bekleniyor: {a.arac}")
            self.depo.kaydet(run)
            return
        if isinstance(sonuc, dict) and sonuc.get("karar") == "ret":
            a.durum = AdimDurum.reddedildi
            sonuc = {**sonuc, "not": "Izin reddi: ayni cagriyi tekrarlama, yeni plan yap."}
        elif isinstance(sonuc, dict) and "hata" in sonuc:
            a.durum = AdimDurum.hata
        else:
            a.durum = AdimDurum.tamam
        if a.durum is not AdimDurum.tamam:
            run.hata_sayaci[anahtar] = run.hata_sayaci.get(anahtar, 0) + 1
        self._arac_mesaji(run, a, sonuc)
        self.depo.kaydet(run)
        if self.hooks is not None:  # post_tool: bilgilendirme; sonuc zaten uygulandi
            await asyncio.to_thread(
                self.hooks.tetikle, "post_tool",
                {"run": run.id, "arac": a.arac, "durum": str(a.durum), "sonuc": a.sonuc[:2000]},
                arac=a.arac,
            )  # fmt: skip

    # ---------------------------------------------------------------- alt ajan (A8.1, A8.4)
    def _sahiplik_sarmali(self, run: Run, ad: str, fonk: Callable[..., Any]) -> Callable[..., Any]:
        """Alt ajanin yazma araclari YALNIZ sahip oldugu dosyalarda calisir."""
        if ad not in YAZAN_ARACLAR:
            return fonk

        def sarili(**kw: Any) -> Any:
            hedefler = [kw.get("yol"), kw.get("kaynak"), kw.get("hedef")]
            sahip = {_norm_yol(x) for x in run.sahip_dosyalar}
            for h in filter(None, hedefler):
                if _norm_yol(h) not in sahip:
                    return {"hata": f"Bu alt ajan '{h}' dosyasina yazamaz (sahip oldugu: "
                            f"{', '.join(run.sahip_dosyalar) or 'yok'}).",
                            "karar": "ret"}  # fmt: skip
            return fonk(**kw)

        return sarili

    def _sahiplik_cakisiyor(self, dosyalar: list[str], haric: str) -> str:
        """Calisan baska bir alt ajan ayni dosyaya sahipse onun kimligi."""
        istenen = {_norm_yol(d) for d in dosyalar}
        for r in self.depo.liste():
            if r.id == haric or not r.parent or r.durum in BITMIS:
                continue
            if istenen & {_norm_yol(d) for d in r.sahip_dosyalar}:
                return r.id
        return ""

    async def _alt_ajan(self, run: Run, a: Adim) -> None:
        g = a.argumanlar
        gorev = str(g.get("gorev") or "").strip()
        araclar = [str(x) for x in g.get("araclar") or []][:30]
        dosyalar = [str(x) for x in g.get("dosyalar") or []][:50]
        kalan_adim = run.butce.max_adim - run.kullanim.adim
        kalan_token = run.butce.max_token - run.kullanim.token
        hata = ""
        if not gorev or not araclar:
            hata = "alt_ajan icin gorev ve en az bir arac gerekli."
        elif kalan_adim < 2:
            hata = "Alt ajana verilecek butce kalmadi."
        elif cakisan := self._sahiplik_cakisiyor(dosyalar, run.id):
            hata = f"Bu dosyalar calisan baska bir alt ajanda ({cakisan}); once o bitsin."
        if hata:
            a.durum = AdimDurum.hata
            self._arac_mesaji(run, a, {"hata": hata})
            self.depo.kaydet(run)
            return
        istenen = int(g.get("max_adim") or 15)
        cocuk = Run(
            hedef=gorev,
            model=run.model,
            parent=run.id,
            izinli_araclar=araclar,
            sahip_dosyalar=dosyalar,
            # butce KESILIR: cocuk ebeveynin kalanindan fazlasini alamaz, toplam cogalmaz
            butce=Butce(
                max_adim=max(1, min(istenen, kalan_adim - 1)),
                max_sure_sn=run.butce.max_sure_sn,
                max_token=max(1000, kalan_token),
                max_ayni_hata=run.butce.max_ayni_hata,
                max_ilerlemesiz=run.butce.max_ilerlemesiz,
            ),
        )
        sahiplik = ", ".join(dosyalar) or "yok (salt okunur)"
        cocuk.mesajlar = [{"role": "user", "content": (
            f"GOREV (alt ajan, ebeveyn {run.id}): {gorev}\n\nKULLANABILECEGIN ARACLAR: "
            f"{', '.join(araclar)}\nYAZABILECEGIN DOSYALAR: {sahiplik}\n"
            "Bitince gorevi_bitir'i kanit adimlariyla cagir; sonucun ebeveyne doner."
        )}]  # fmt: skip
        self.depo.kaydet(cocuk)
        run.cocuklar.append(cocuk.id)
        run.guncellemeler.append(f"Alt ajan baslatildi: {gorev[:80]}")
        a.durum = AdimDurum.niyet
        self.depo.kaydet(run)
        try:
            await self._dongu(cocuk.id)  # tek yerel model: cocuk sirali calisir
        finally:
            c = self.depo.getir(cocuk.id)
            run.kullanim.adim += c.kullanim.adim  # cocugun harcamasi ebeveynden duser
            run.kullanim.token += c.kullanim.token
        sonuc = {
            "alt_ajan": c.id,
            "durum": str(c.durum),
            "ozet": c.sonuc.ozet or c.hata,
            "dogrulandi": c.sonuc.dogrulandi,
            "degisen_dosyalar": sorted(
                {x.dosya for x in c.adimlar if x.dosya and x.arac in YAZAN_ARACLAR}
            ),
        }
        a.durum = AdimDurum.tamam if c.durum is RunDurum.basarili else AdimDurum.hata
        self._arac_mesaji(run, a, sonuc)
        self.depo.kaydet(run)

    def _plan(self, run: Run, a: Adim) -> None:
        try:
            run.plan = [
                PlanAdimi(**{k: str(v) for k, v in x.items() if k in PlanAdimi.model_fields})
                for x in a.argumanlar.get("adimlar") or []
                if isinstance(x, dict) and x.get("baslik")
            ][:30]
        except (ValueError, TypeError) as e:
            a.durum = AdimDurum.hata
            self._arac_mesaji(run, a, {"hata": f"Plan gecersiz: {e}"})
        else:
            a.durum = AdimDurum.tamam
            self._arac_mesaji(run, a, {"tamam": True, "adim_sayisi": len(run.plan)})
        self.depo.kaydet(run)

    def _bitir(self, run: Run, a: Adim) -> None:
        """Kanit kontrolu: referans verilen adim basarili gercek bir arac adimi olmali ve SON
        dosya degisikliginden SONRA atilmis olmali (degisiklik oncesi okuma son durumu kanitlamaz).
        """
        ozet = str(a.argumanlar.get("ozet") or "")[:2000]
        numaralar = [n for n in a.argumanlar.get("kanit_adimlari") or [] if isinstance(n, int)]
        adimlar = {x.no: x for x in run.adimlar}
        son_degisiklik = max(
            (x.no for x in run.adimlar if x.arac in DEGISTIREN and x.durum is AdimDurum.tamam),
            default=0,
        )
        gecerli: list[int] = []
        for n in numaralar:
            x = adimlar.get(n)
            if x is None or x.arac in META or x.durum is not AdimDurum.tamam:
                continue
            if n <= son_degisiklik:  # degisikligin kendisi kanit degil
                continue
            if x.arac == "komut_calistir":
                kod = x.cikis_kodu
                if kod != 0:  # bilinmeyen kod da kanit olamaz
                    a.durum = AdimDurum.hata
                    self._arac_mesaji(
                        run,
                        a,
                        {"hata": f"Kanit adimi {n} basarisiz (cikis kodu {kod}); gorev bitmedi. "
                         "Hatayi duzelt ve testi tekrar calistir."},
                    )  # fmt: skip
                    self.depo.kaydet(run)
                    return
            gecerli.append(n)
        a.durum = AdimDurum.tamam
        if (
            numaralar and not gecerli
        ):  # kanit verdi ama gecersiz: bitirme reddedilir, model duzeltir
            a.durum = AdimDurum.hata
            self._arac_mesaji(
                run,
                a,
                {"hata": f"Kanit adimlari {numaralar} gecersiz: son dosya degisikligi adim "
                 f"{son_degisiklik}; kanit bundan SONRA basarili bir adim olmali (or. testi "
                 "tekrar calistir). Kanitin yoksa kanit_adimlari=[] ile bitir."},
            )  # fmt: skip
            self.depo.kaydet(run)
            return
        run.sonuc = Sonuc(ozet=ozet, kanit=gecerli, dogrulandi=bool(gecerli))
        run.durum = RunDurum.basarili if gecerli else RunDurum.dogrulanmadi
        if not gecerli:
            run.hata = (
                "Gecerli arac kaniti gosterilmedi (son degisiklikten sonra basarili bir adim "
                "gerekir); sonuc dogrulanmadi."
            )
        self._arac_mesaji(run, a, {"tamam": True, "durum": str(run.durum)})
        self.depo.kaydet(run)


async def olay_akisi(depo: RunDeposu, run_id: str, aralik: float = 1.0) -> AsyncIterator[dict]:
    """Basit SSE kaynagi: durum degistikce ozet gonderir; bitince kapanir."""
    son = ""
    while True:
        run = depo.getir(run_id)
        if run.guncelleme != son:
            son = run.guncelleme
            yield {"tur": "run", "run": run.ozet()}
        if run.durum in BITMIS:
            return
        await asyncio.sleep(aralik)
