"""Hugging Face model magazasi: GGUF ara, bu PC'de calisir mi degerlendir, indir (devam edebilir,
SHA256 dogrulamali), kaydet, sil. Yalniz .gguf veri dosyalari indirilir;
hicbir sey calistirilmaz."""

from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import struct
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz
from app.services.yerel_llm import MODELLER, ModelProfili

HF = "https://huggingface.co"
BAYT_PER_PARAMETRE_Q4KM = 0.62  # Q4_K_M ~4.9 bit/parametre
MMPROJ_TAHMIN_GB = 0.7
ISLETIM_PAYI_GB = 5.0  # Windows + acik programlar icin birakilacak RAM
ONBELLEK_SN = 600
YASAKLI = re.compile(r"mtp|-0000\d-of-|imatrix\.gguf$", re.I)  # MTP taslak, parcali, imatrix verisi
QUANT_SIRASI = ["i1-Q4_K_M", "Q4_K_M", "Q4_K_S", "IQ4_XS", "Q4_0"]
MMPROJ_SIRASI = ["Q8_0", "q8_0", "F16", "f16", "BF16", "bf16"]


# ---------------- arama ----------------
def dosya_sec(dosyalar: list[str]) -> tuple[str | None, str | None]:
    """(model .gguf, mmproj .gguf): tercih edilen 4-bit quant ve en kucuk mmproj."""
    ggufler = [d for d in dosyalar if d.lower().endswith(".gguf") and "/" not in d]
    mmprojler = [d for d in ggufler if "mmproj" in d.lower()]
    modeller = [d for d in ggufler if d not in mmprojler and not YASAKLI.search(d)]
    model = next(
        (d for q in QUANT_SIRASI for d in sorted(modeller, key=len) if f"{q}.gguf" in d), None
    )
    mmproj = next(
        (d for q in MMPROJ_SIRASI for d in mmprojler if q in d), mmprojler[0] if mmprojler else None
    )
    return model, mmproj


def tahmini_boyut_gb(parametre: int | None, gorsel: bool) -> float | None:
    if not parametre:
        return None
    return round(parametre * BAYT_PER_PARAMETRE_Q4KM / 1e9 + (MMPROJ_TAHMIN_GB if gorsel else 0), 1)


def uyumluluk(boyut_gb: float | None, bellek: dict, disk_bos_gb: float | None) -> dict:
    """Bu PC'de calisir mi? gereken RAM = model * 1.15 + 1 GB (baglam onbellegi, calisma alani)."""
    toplam = bellek.get("toplam_gb")
    if boyut_gb is None or not toplam:
        return {"durum": "bilinmiyor", "neden": "Boyut ya da RAM bilinmiyor."}
    gereken = round(boyut_gb * 1.15 + 1, 1)
    bos = bellek.get("bos_gb") or 0
    sonuc: dict[str, Any] = {"gereken_ram_gb": gereken, "simdi_acilir": bos >= gereken}
    if gereken <= toplam - ISLETIM_PAYI_GB:
        sonuc |= {"durum": "calisir", "neden": f"~{gereken} GB RAM ister; {toplam} GB var."}
    elif gereken <= toplam - 2:
        sonuc |= {
            "durum": "zorlanir",
            "neden": f"~{gereken} GB RAM ister; {toplam} GB'ta diger programlar kapali olmali.",
        }
    else:
        sonuc |= {"durum": "calismaz", "neden": f"~{gereken} GB RAM ister; {toplam} GB yetmez."}
    if disk_bos_gb is not None and boyut_gb > disk_bos_gb - 2:
        sonuc |= {"disk_yetmez": True, "neden": sonuc["neden"] + f" Diskte {disk_bos_gb} GB bos."}
    return sonuc


def aday_olustur(m: dict) -> dict | None:
    dosyalar = [s["rfilename"] for s in m.get("siblings", [])]
    model, mmproj = dosya_sec(dosyalar)
    if not model:
        return None
    gguf = m.get("gguf") or {}
    sablon = str(gguf.get("chat_template") or "")
    gorsel = bool(mmproj) or m.get("pipeline_tag") == "image-text-to-text"
    return {
        "repo": m["id"],
        "ad": m["id"].split("/")[-1].removesuffix("-GGUF").removesuffix("-gguf"),
        "yazar": m["id"].split("/")[0],
        "indirme": m.get("downloads", 0),
        "begeni": m.get("likes", 0),
        "guncelleme": (m.get("lastModified") or "")[:10],
        "parametre_milyar": round(gguf["total"] / 1e9, 1) if gguf.get("total") else None,
        "mimari": gguf.get("architecture"),
        "gorsel": gorsel,
        "mmproj_ayri_repoda": gorsel and not mmproj,
        "arac": "tool" in sablon,
        "model_dosyasi": model,
        "mmproj_dosyasi": mmproj,
        "tahmini_gb": tahmini_boyut_gb(gguf.get("total"), gorsel),
    }


class Magaza:
    def __init__(self, istemci: httpx.AsyncClient | None = None) -> None:
        self._istemci = istemci or httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10))
        self._onbellek: dict[str, tuple[float, list[dict]]] = {}

    async def ara(self, sorgu: str, limit: int = 100, imlec: str = "") -> tuple[list[dict], str]:
        """Bos sorgu = tum GGUF modelleri. Doner: (sonuclar, sonraki sayfa imleci; bos = son)."""
        anahtar = f"{sorgu.strip().lower()}|{limit}|{imlec}"
        if (k := self._onbellek.get(anahtar)) and time.time() - k[0] < ONBELLEK_SN:
            return k[1]
        parametreler = [
            *([("search", sorgu.strip())] if sorgu.strip() else []),
            *([("cursor", imlec)] if imlec else []),
            ("filter", "gguf"),
            ("sort", "downloads"),
            ("direction", "-1"),
            ("limit", str(limit)),
        ] + [
            ("expand[]", e)
            for e in ("siblings", "gguf", "downloads", "likes", "lastModified", "pipeline_tag")
        ]
        try:
            r = await self._istemci.get(f"{HF}/api/models", params=parametreler)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise UygulamaHatasi(f"Hugging Face'e ulasilamadi: {e}") from e
        sonuc = [a for m in r.json() if (a := aday_olustur(m))]
        # HF sayfalama: Link: <...?cursor=X>; rel="next"
        sonraki_url = (r.links.get("next") or {}).get("url", "")
        sonraki = httpx.URL(sonraki_url).params.get("cursor", "") if sonraki_url else ""
        self._onbellek[anahtar] = (time.time(), (sonuc, sonraki))
        return sonuc, sonraki

    async def dosya_bilgileri(self, repo: str) -> dict[str, dict]:
        """{dosya: {boyut, sha256}} (LFS kaydi)."""
        try:
            r = await self._istemci.get(f"{HF}/api/models/{repo}", params={"blobs": "true"})
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise UygulamaHatasi(f"Model bilgisi alinamadi ({repo}): {e}") from e
        return {
            s["rfilename"]: {
                "boyut": s.get("size") or 0,
                "sha256": (s.get("lfs") or {}).get("sha256", ""),
            }
            for s in r.json().get("siblings", [])
        }

    async def kapat(self) -> None:
        await self._istemci.aclose()


# ---------------- kayitli (indirilmis) modeller ----------------
def anahtar_uret(repo: str) -> str:
    ad = repo.split("/")[-1].lower().removesuffix("-gguf")
    ad = re.sub(r"[^a-z0-9.]+", "-", ad).strip("-")
    return ad[:48].rstrip("-.") or "model"


def gguf_ses_var(yol: Path) -> bool:
    """mmproj GGUF basliginda clip.has_audio_encoder = true mi (dosyayi calistirmadan okur)."""
    try:
        with yol.open("rb") as f:
            if f.read(4) != b"GGUF":
                return False
            _, _, kv = struct.unpack("<IQQ", f.read(20))
            for _ in range(min(kv, 4096)):
                (n,) = struct.unpack("<Q", f.read(8))
                if n > 1024:  # anahtar adi bu kadar uzun olamaz: bozuk/yabanci dosya
                    return False
                anahtar = f.read(n).decode("utf-8", "replace")
                (tur,) = struct.unpack("<I", f.read(4))
                if tur == 7:  # bool
                    deger = f.read(1) == b"\x01"
                    if anahtar == "clip.has_audio_encoder":
                        return deger
                elif tur == 8:  # string
                    (n,) = struct.unpack("<Q", f.read(8))
                    f.seek(n, 1)
                elif tur in (0, 1):
                    f.seek(1, 1)
                elif tur in (2, 3):
                    f.seek(2, 1)
                elif tur in (4, 5, 6):
                    f.seek(4, 1)
                elif tur in (10, 11, 12):
                    f.seek(8, 1)
                else:  # dizi vb.: ses anahtari genelde oncedir; durmak guvenli
                    return False
    except (OSError, struct.error, OverflowError, ValueError):
        return False
    return False


class ModelKaydi:
    """data/modeller.json: magazadan indirilen modellerin profilleri (MODELLER'e eklenir)."""

    def __init__(self, veri_dizini: Path) -> None:
        self.yol = veri_dizini / "modeller.json"
        self.yerlesik = set(MODELLER)  # uygulamayla gelenler

    def oku(self) -> list[dict]:
        return json_oku(self.yol, []) or []

    def yukle(self) -> None:
        for p in self.oku():
            MODELLER[p["anahtar"]] = ModelProfili(
                **{
                    k: p[k]
                    for k in ("anahtar", "ad", "dosya", "mmproj", "ram_gb", "ses", "aciklama")
                }
            )

    def ekle(self, profil: dict) -> None:
        liste = [p for p in self.oku() if p["anahtar"] != profil["anahtar"]] + [profil]
        json_yaz(self.yol, liste)
        self.yukle()

    def cikar(self, anahtar: str) -> None:
        json_yaz(self.yol, [p for p in self.oku() if p["anahtar"] != anahtar])
        if anahtar not in self.yerlesik:
            MODELLER.pop(anahtar, None)

    def kaynak(self, anahtar: str) -> str | None:
        return next((p.get("repo") for p in self.oku() if p["anahtar"] == anahtar), None)


# ---------------- indirme ----------------
@dataclass
class Indirme:
    id: str
    repo: str
    anahtar: str
    dosyalar: list[dict]  # {ad, boyut, sha256, repo}
    toplam: int
    inen: int = 0
    hiz: float = 0.0  # bayt/sn
    durum: str = "bekliyor"  # bekliyor | iniyor | dogrulaniyor | bitti | hata | iptal
    hata: str = ""
    baslangic: float = field(default_factory=time.time)

    def ozet(self) -> dict:
        d = asdict(self)
        d["yuzde"] = round(self.inen / self.toplam * 100, 1) if self.toplam else 0
        kalan = (self.toplam - self.inen) / self.hiz if self.hiz > 0 else None
        d["kalan_sn"] = round(kalan) if kalan else None
        return d


class Indirici:
    def __init__(self, magaza: Magaza, kayit: ModelKaydi, klasor: Callable[[], Path]) -> None:
        self.magaza = magaza
        self.kayit = kayit
        self._klasor = klasor  # ayarlardaki model klasoru (degisebilir)
        self.indirmeler: dict[str, Indirme] = {}
        self._gorevler: dict[str, asyncio.Task] = {}

    @property
    def model_klasoru(self) -> Path:
        return self._klasor()

    def disk_bos_gb(self) -> float | None:
        try:
            hedef = self.model_klasoru if self.model_klasoru.exists() else self.model_klasoru.anchor
            return round(shutil.disk_usage(hedef).free / 1024**3, 1)
        except OSError:
            return None

    async def baslat(self, repo: str) -> Indirme:
        if any(
            i.repo == repo and i.durum in ("bekliyor", "iniyor") for i in self.indirmeler.values()
        ):
            raise UygulamaHatasi("Bu model zaten indiriliyor.")
        bilgi = await self.magaza.dosya_bilgileri(repo)
        model, mmproj = dosya_sec(list(bilgi))
        if not model:
            raise UygulamaHatasi("Bu depoda uygun 4-bit GGUF dosyasi yok.")
        dosyalar = [{"ad": model, "repo": repo, **bilgi[model]}]
        mmproj_repo = repo
        if not mmproj and "-i1-GGUF" in repo:  # mradermacher: mmproj statik depoda
            mmproj_repo = repo.replace("-i1-GGUF", "-GGUF")
            ek = await self.magaza.dosya_bilgileri(mmproj_repo)
            _, mmproj = dosya_sec(list(ek))
            bilgi |= ek
        if mmproj:
            dosyalar.append({"ad": mmproj, "repo": mmproj_repo, **bilgi[mmproj]})
        toplam = sum(d["boyut"] for d in dosyalar)
        bos = self.disk_bos_gb()
        if bos is not None and toplam / 1024**3 > bos - 2:
            raise UygulamaHatasi(
                f"Diskte yer yok: {toplam / 1024**3:.1f} GB gerekli, {bos} GB bos (2 GB pay)."
            )
        i = Indirme(uuid.uuid4().hex[:10], repo, anahtar_uret(repo), dosyalar, toplam)
        self.indirmeler[i.id] = i
        self._gorevler[i.id] = asyncio.create_task(self._calistir(i))
        return i

    def iptal(self, indirme_id: str) -> None:
        if indirme_id not in self.indirmeler:
            raise Bulunamadi("Indirme bulunamadi.")
        if (g := self._gorevler.get(indirme_id)) and not g.done():
            g.cancel()

    async def _calistir(self, i: Indirme) -> None:
        gecici = self.model_klasoru / "_indirme"
        gecici.mkdir(parents=True, exist_ok=True)
        try:
            i.durum = "iniyor"
            onceki = 0
            for d in i.dosyalar:
                await self._dosya_indir(i, d, gecici / f"{d['ad']}.part", onceki)
                onceki += d["boyut"]
            i.durum = "dogrulaniyor"
            for d in i.dosyalar:
                parca = gecici / f"{d['ad']}.part"
                if d["sha256"] and await asyncio.to_thread(_sha256, parca) != d["sha256"]:
                    parca.unlink(missing_ok=True)
                    raise UygulamaHatasi(f"SHA256 eslesmedi, dosya silindi: {d['ad']}")
            for d in i.dosyalar:
                (gecici / f"{d['ad']}.part").replace(self.model_klasoru / "models" / d["ad"])
            model, mmproj = i.dosyalar[0], (i.dosyalar[1] if len(i.dosyalar) > 1 else None)
            ses = bool(mmproj) and gguf_ses_var(self.model_klasoru / "models" / mmproj["ad"])
            ozellik = "metin" + (", resim" if mmproj else "") + (", ses" if ses else "")
            self.kayit.ekle(
                {
                    "anahtar": i.anahtar,
                    "ad": i.repo.split("/")[-1].removesuffix("-GGUF"),
                    "dosya": model["ad"],
                    "mmproj": mmproj["ad"] if mmproj else "",
                    "ram_gb": round(i.toplam / 1024**3, 1),
                    "ses": ses,
                    "aciklama": f"Hugging Face: {i.repo}. {ozellik}.",
                    "repo": i.repo,
                }
            )
            i.durum = "bitti"
            logger.info("Model indirildi: {} -> {}", i.repo, i.anahtar)
        except asyncio.CancelledError:
            i.durum = "iptal"
        except (httpx.HTTPError, OSError, UygulamaHatasi) as e:
            i.durum, i.hata = "hata", getattr(e, "mesaj", str(e))
            logger.warning("Indirme hatasi {}: {}", i.repo, i.hata)
        except Exception as e:  # noqa: BLE001 - indirme asla "iniyor"da takili kalmasin
            i.durum, i.hata = "hata", f"Beklenmeyen hata: {e}"
            logger.exception("Indirme beklenmeyen hata {}", i.repo)

    async def _dosya_indir(self, i: Indirme, d: dict, hedef: Path, onceki: int) -> None:
        mevcut = hedef.stat().st_size if hedef.exists() else 0
        if d["boyut"] and mevcut >= d["boyut"]:
            i.inen = onceki + d["boyut"]
            return
        basliklar = {"Range": f"bytes={mevcut}-"} if mevcut else {}
        url = f"{HF}/{d['repo']}/resolve/main/{d['ad']}"
        async with self.magaza._istemci.stream(
            "GET",
            url,
            headers=basliklar,
            follow_redirects=True,
            timeout=httpx.Timeout(60, connect=15),
        ) as r:
            if r.status_code == 200 and mevcut:  # sunucu devam etmeyi desteklemedi: bastan
                mevcut = 0
            r.raise_for_status()
            olcum_bas, olcum_bayt = time.monotonic(), 0
            with hedef.open("ab" if mevcut else "wb") as f:
                async for parca in r.aiter_bytes(1024 * 1024):
                    f.write(parca)
                    mevcut += len(parca)
                    olcum_bayt += len(parca)
                    i.inen = onceki + mevcut
                    gecen = time.monotonic() - olcum_bas
                    if gecen >= 1:
                        i.hiz, olcum_bas, olcum_bayt = olcum_bayt / gecen, time.monotonic(), 0

    def sil(self, anahtar: str) -> dict:
        profil = MODELLER.get(anahtar)
        if profil is None:
            raise Bulunamadi(f"Model bulunamadi: {anahtar}")
        silinen = []
        for ad in (profil.dosya, profil.mmproj):
            if not ad:
                continue
            # komple: model dosyasi + yarim kalmis indirme parcasi
            for yol in (
                self.model_klasoru / "models" / ad,
                self.model_klasoru / "_indirme" / f"{ad}.part",
            ):
                if yol.exists():
                    yol.unlink()
                    silinen.append(yol.name)
        self.kayit.cikar(anahtar)
        return {"silindi": silinen}


def _sha256(yol: Path) -> str:
    h = hashlib.sha256()
    with yol.open("rb") as f:
        while blok := f.read(8 << 20):
            h.update(blok)
    return h.hexdigest()
