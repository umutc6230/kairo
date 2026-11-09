"""Checkpoint: degisiklik oncesi anlik goruntu ve CAKISMA FARKINDA geri alma (A2.7).

Tasarim kurallari:
- Her yazma isleminden ONCE dosyanin icerigi ve hash'i saklanir; sonra hash'i de kaydedilir.
- Geri alma, dosyanin SU ANKI hash'i ile kaydin `sonra_hash` degerini karsilastirir. Fark varsa
  dosya ajandan sonra (muhtemelen kullanici tarafindan) degismistir: USTUNE YAZILMAZ, cakisma
  bildirilir. Kullanicinin kendi degisikligini sessizce silmek kabul edilemez.
- `git reset --hard` ya da genel calisma agaci sifirlama KULLANILMAZ: ajanin dokunmadigi
  dosyalar etkilenmez.
- Bu bir transaction sistemi DEGILDIR: ag istegi, paket kurulumu, veritabani ve dis servis
  yan etkileri geri alinamaz; yalniz dosya etkileri geri alinir.
"""

from __future__ import annotations

import difflib
import hashlib
import shutil
import uuid
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz

MAX_CHECKPOINT = 100
MAX_SNAPSHOT_BAYT = 5 * 1024 * 1024


class Islem(StrEnum):
    olustur = "olustur"
    degistir = "degistir"
    sil = "sil"
    tasi = "tasi"


def icerik_hashi(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()[:32]


def dosya_hashi(yol: Path) -> str | None:
    """Dosyanin icerik hash'i; dosya yoksa None (yoklugun kendisi de bir durumdur)."""
    try:
        return icerik_hashi(yol.read_bytes())
    except OSError:
        return None


class DosyaDurumu(BaseModel):
    yol: str
    islem: Islem
    once_hash: str | None = None
    sonra_hash: str | None = None
    once_kopya: str | None = None  # snapshot dosyasinin adi (yoksa dosya onceden yoktu)
    hedef: str | None = None  # tasima hedefi
    boyut: int = 0


class Checkpoint(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    aciklama: str = ""
    arac: str = ""
    oturum_id: str = ""
    zaman: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    dosyalar: list[DosyaDurumu] = []
    geri_alindi: bool = False


class CakismaHatasi(UygulamaHatasi):
    """Dosya ajandan sonra degismis; geri alma kullanicinin degisikligini silmez."""

    durum = 409


class CheckpointDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.dizin = veri_dizini / "checkpoints"
        self.dizin.mkdir(parents=True, exist_ok=True)
        self.yol = self.dizin / "kayit.json"

    # ---- kayit ----
    def _liste(self) -> list[Checkpoint]:
        sonuc = []
        for h in json_oku(self.yol, []) or []:
            try:
                sonuc.append(Checkpoint(**h))
            except ValueError:
                continue
        return sonuc

    def _yaz(self, kayitlar: list[Checkpoint]) -> None:
        json_yaz(self.yol, [k.model_dump(mode="json") for k in kayitlar[:MAX_CHECKPOINT]])

    def liste(self, adet: int = 30) -> list[dict]:
        return [k.model_dump(mode="json") for k in self._liste()[:adet]]

    def getir(self, checkpoint_id: str) -> Checkpoint:
        for k in self._liste():
            if k.id == checkpoint_id:
                return k
        raise Bulunamadi("Checkpoint bulunamadi.")

    # ---- olusturma ----
    def anlik_al(self, yol: Path) -> tuple[str | None, str | None, int]:
        """Dosyanin SU ANKI halini saklar: (hash, kopya adi, boyut). Dosya yoksa (None, None, 0)."""
        try:
            veri = yol.read_bytes()
        except OSError:
            return None, None, 0
        if len(veri) > MAX_SNAPSHOT_BAYT:
            raise UygulamaHatasi(
                f"Dosya {MAX_SNAPSHOT_BAYT // (1024 * 1024)} MB'dan buyuk; geri alinabilir "
                "degisiklik yapilamaz."
            )
        ad = f"{uuid.uuid4().hex[:16]}.snap"
        (self.dizin / ad).write_bytes(veri)
        return icerik_hashi(veri), ad, len(veri)

    def kaydet(self, checkpoint: Checkpoint) -> Checkpoint:
        self._yaz([checkpoint, *self._liste()])
        return checkpoint

    # ---- geri alma ----
    def onizle(self, checkpoint_id: str) -> dict:
        """Geri alma neyi degistirir, nerede cakisma var? Hicbir sey yazilmaz."""
        k = self.getir(checkpoint_id)
        satirlar = []
        for d in k.dosyalar:
            p = Path(d.yol)
            simdiki = dosya_hashi(p)
            cakisma = simdiki != d.sonra_hash
            satirlar.append(
                {
                    "yol": d.yol,
                    "islem": str(d.islem),
                    "cakisma": cakisma,
                    "durum": ("ajandan sonra degismis" if cakisma else "geri alinabilir"),
                    "geri_donus": "silinecek" if d.once_hash is None else "eski icerik yazilacak",
                }
            )
        return {
            "id": k.id,
            "aciklama": k.aciklama,
            "zaman": k.zaman,
            "geri_alindi": k.geri_alindi,
            "dosyalar": satirlar,
            "cakisma_var": any(s["cakisma"] for s in satirlar),
        }

    def geri_al(self, checkpoint_id: str, yollar: list[str] | None = None) -> dict:
        """Secili dosyalari (ya da hepsini) geri alir. Cakisan dosyaya DOKUNULMAZ."""
        k = self.getir(checkpoint_id)
        istenen = {str(Path(y)) for y in yollar} if yollar else None
        geri: list[str] = []
        cakisan: list[str] = []
        atlanan: list[str] = []
        for d in k.dosyalar:
            p = Path(d.yol)
            if istenen is not None and str(p) not in istenen:
                atlanan.append(d.yol)
                continue
            if dosya_hashi(p) != d.sonra_hash:
                cakisan.append(d.yol)  # kullanicinin degisikligi: USTUNE YAZMA
                continue
            try:
                self._tek_geri_al(d, p)
            except OSError as e:
                raise UygulamaHatasi(f"Geri alinamadi: {d.yol} ({e})") from e
            geri.append(d.yol)
        if geri and not cakisan and istenen is None:
            k.geri_alindi = True
            self._yaz([k if x.id == k.id else x for x in self._liste()])
        return {
            "id": k.id,
            "geri_alinan": geri,
            "cakisan": cakisan,
            "atlanan": atlanan,
            "tamam": not cakisan,
            "not": (
                "Cakisan dosyalar ajandan sonra degistigi icin korundu."
                if cakisan
                else "Dosya etkileri geri alindi. Komut, ag ve paket yan etkileri geri ALINMAZ."
            ),
        }

    # ---- hunk bazli geri alma ----
    def _hunk_hazirla(self, checkpoint_id: str, yol: str) -> tuple:
        k = self.getir(checkpoint_id)
        d = next((x for x in k.dosyalar if Path(x.yol) == Path(yol)), None)
        if d is None:
            raise Bulunamadi(f"Bu checkpoint'te dosya yok: {yol}")
        if d.islem is not Islem.degistir or not d.once_kopya:
            raise UygulamaHatasi("Parca parca geri alma yalniz degistirilen dosyalarda yapilir.")
        p = Path(d.yol)
        if dosya_hashi(p) != d.sonra_hash:
            raise CakismaHatasi(f"Dosya ajandan sonra degismis, dokunulmadi: {d.yol}")
        try:
            once = (self.dizin / d.once_kopya).read_bytes().decode("utf-8")
            simdi = p.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise UygulamaHatasi(f"Metin dosyasi okunamadi: {d.yol} ({e})") from e
        once_s, simdi_s = once.splitlines(keepends=True), simdi.splitlines(keepends=True)
        ops = difflib.SequenceMatcher(None, once_s, simdi_s, autojunk=False).get_opcodes()
        return k, d, once_s, simdi_s, ops

    def hunklar(self, checkpoint_id: str, yol: str) -> dict:
        """Ajanin degisikligini bloklara ayirir (0'dan numarali); hicbir sey yazilmaz."""
        _, d, once, simdi, ops = self._hunk_hazirla(checkpoint_id, yol)
        degisen = [o for o in ops if o[0] != "equal"]
        bloklar = [
            {"no": i, "satir": j1 + 1, "eski": "".join(once[i1:i2]), "yeni": "".join(simdi[j1:j2])}
            for i, (_, i1, i2, j1, j2) in enumerate(degisen)
        ]
        return {"yol": d.yol, "hunklar": bloklar}

    def hunk_geri_al(self, checkpoint_id: str, yol: str, numaralar: list[int]) -> dict:
        """Yalniz secili bloklari eski haline dondurur; digerleri ve dosyanin kalani korunur."""
        k, d, once, simdi, ops = self._hunk_hazirla(checkpoint_id, yol)
        toplam = sum(1 for o in ops if o[0] != "equal")
        secili = set(numaralar)
        if not secili or not secili <= set(range(toplam)):
            raise UygulamaHatasi(f"Gecersiz blok numarasi; 0-{toplam - 1} arasi secin.")
        sonuc: list[str] = []
        no = -1
        for etiket, i1, i2, j1, j2 in ops:
            if etiket != "equal":
                no += 1
            sonuc += once[i1:i2] if etiket != "equal" and no in secili else simdi[j1:j2]
        p = Path(d.yol)
        veri = "".join(sonuc).encode("utf-8")
        gecici = p.with_suffix(p.suffix + ".geri-tmp")
        gecici.write_bytes(veri)
        gecici.replace(p)
        d.sonra_hash = icerik_hashi(veri)  # tam geri alma sonradan da tutarli calissin
        self._yaz([k if x.id == k.id else x for x in self._liste()])
        return {"yol": d.yol, "geri_alinan_bloklar": sorted(secili), "kalan": toplam - len(secili)}

    def _tek_geri_al(self, d: DosyaDurumu, p: Path) -> None:
        if d.once_hash is None:  # dosya ajan tarafindan olusturulmustu
            p.unlink(missing_ok=True)
            if d.islem is Islem.tasi and d.hedef:
                Path(d.hedef).unlink(missing_ok=True)
            return
        kopya = self.dizin / (d.once_kopya or "")
        if not kopya.is_file():
            raise UygulamaHatasi(f"Eski icerik bulunamadi: {d.yol}")
        p.parent.mkdir(parents=True, exist_ok=True)
        gecici = p.with_suffix(p.suffix + ".geri-tmp")
        shutil.copyfile(kopya, gecici)
        gecici.replace(p)

    def temizle(self, saklanan: int = MAX_CHECKPOINT) -> int:
        """Kayit disi kalan snapshot dosyalarini siler; kac dosya silindigini dondurur."""
        kayitlar = self._liste()[:saklanan]
        self._yaz(kayitlar)
        kullanilan = {d.once_kopya for k in kayitlar for d in k.dosyalar if d.once_kopya}
        silinen = 0
        for p in self.dizin.glob("*.snap"):
            if p.name not in kullanilan:
                p.unlink(missing_ok=True)
                silinen += 1
        return silinen
