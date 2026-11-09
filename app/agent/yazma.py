"""Yazma araclari: dosya_yaz, dosya_yama, dosya_tasi, dosya_sil (A2.2, A2.3).

Her islem sirayla: IZIN (PolitikaMotoru.uygula) -> BEKLENEN ESKI HASH -> CHECKPOINT -> ATOMIK YAZIM.

- Beklenen hash: model dosyayi okuduktan sonra dosya degistiyse yazma durur (kullanicinin ya da
  baska bir surecin degisikligi ezilmez). Yeni dosyada `beklenen_hash` verilmez.
- Atomik yazim: gecici dosya + `os.replace`. TEK DOSYA icin atomiktir; cok dosyali bir is
  yarida kalabilir, bu durum sonucta acikca raporlanir (tam atomiklik IDDIA EDILMEZ).
- Checkpoint: her islem once/sonra hash'i ve eski icerikle kaydedilir, geri alinabilir.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.agent.checkpoints import Checkpoint, CheckpointDeposu, DosyaDurumu, Islem, dosya_hashi
from app.agent.dosyalar import MAX_DOSYA_BAYT, KokKapsami, ikili_mi
from app.agent.policy import Istek, PolitikaMotoru, YanEtki
from app.agent.workspaces import CalismaAlani
from app.exceptions import OnayGerekli, UygulamaHatasi, YetkiYok

MAX_YAZMA_KARAKTER = 400_000


def atomik_yaz(yol: Path, veri: bytes) -> None:
    """Gecici dosyaya yazip `os.replace` ile yerine koyar: yarim dosya kalmaz."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(f".{yol.name}.yas-tmp")
    try:
        with open(gecici, "wb") as f:
            f.write(veri)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, yol)
    except BaseException:
        gecici.unlink(missing_ok=True)
        raise


class YazmaAraclari:
    """Yan etkili dosya araclari. Izin motoru olmadan ORNEKLENMEZ."""

    def __init__(
        self,
        kapsam: KokKapsami,
        politika: PolitikaMotoru,
        alan: CalismaAlani,
        checkpointler: CheckpointDeposu,
        oturum_id: str = "",
    ) -> None:
        self.kapsam = kapsam
        self.politika = politika
        self.alan = alan
        self.checkpointler = checkpointler
        self.oturum_id = oturum_id

    # ---- ortak ----
    def _izin(self, arac: str, yan_etki: YanEtki, yol: Path, ozet: str) -> None:
        self.politika.uygula(
            Istek(arac=arac, yan_etki=yan_etki, yol=str(yol), ozet=ozet), self.alan
        )

    def _checkpoint(self, arac: str, durumlar: list[DosyaDurumu], aciklama: str) -> str:
        cp = self.checkpointler.kaydet(
            Checkpoint(arac=arac, aciklama=aciklama, oturum_id=self.oturum_id, dosyalar=durumlar)
        )
        return cp.id

    @staticmethod
    def _hash_kontrol(p: Path, beklenen: str | None) -> None:
        simdiki = dosya_hashi(p)
        if simdiki is None:
            if beklenen:
                raise UygulamaHatasi(f"Dosya yok ama beklenen hash verildi: {p}")
            return
        if beklenen is None:
            raise UygulamaHatasi(
                f"Dosya zaten var: {p}. Uzerine yazmak icin once oku ve `beklenen_hash` gonder."
            )
        if beklenen != simdiki:
            raise UygulamaHatasi(
                f"Dosya en son okudugundan beri degisti ({p}). Yeniden oku ve tekrar dene; "
                "kullanicinin degisikligi ezilmedi."
            )

    def _metin_kontrol(self, icerik: str) -> bytes:
        if len(icerik) > MAX_YAZMA_KARAKTER:
            raise UygulamaHatasi(f"Icerik {MAX_YAZMA_KARAKTER} karakterden uzun.")
        return icerik.encode("utf-8")

    # ---- araclar ----
    def dosya_yaz(self, yol: str, icerik: str, beklenen_hash: str | None = None) -> dict:
        """Dosya olusturur ya da (beklenen hash ile) uzerine yazar."""
        p = self.kapsam.coz(yol)
        vardi = p.is_file()
        self._izin(
            "dosya_yaz",
            YanEtki.yaz,
            p,
            f"{'Uzerine yaz' if vardi else 'Olustur'}: {self.kapsam.goreli(p)}",
        )
        self._hash_kontrol(p, beklenen_hash)
        veri = self._metin_kontrol(icerik)
        once_hash, kopya, boyut = self.checkpointler.anlik_al(p)
        atomik_yaz(p, veri)
        sonra = dosya_hashi(p)
        cp = self._checkpoint(
            "dosya_yaz",
            [
                DosyaDurumu(
                    yol=str(p),
                    islem=Islem.degistir if vardi else Islem.olustur,
                    once_hash=once_hash,
                    sonra_hash=sonra,
                    once_kopya=kopya,
                    boyut=boyut,
                )
            ],
            f"{'Degistirildi' if vardi else 'Olusturuldu'}: {self.kapsam.goreli(p)}",
        )
        return {
            "dosya": str(p),
            "goreli": self.kapsam.goreli(p),
            "islem": "degistir" if vardi else "olustur",
            "yeni_hash": sonra,
            "satir": icerik.count("\n") + 1,
            "checkpoint": cp,
        }

    def dosya_yama(
        self, yol: str, eski_metin: str, yeni_metin: str, beklenen_hash: str | None = None
    ) -> dict:
        """Dosyadaki TEK ve BENZERSIZ bir metin parcasini degistirir (satir araligi degil)."""
        p = self.kapsam.coz(yol)
        self._izin("dosya_yama", YanEtki.yaz, p, f"Yama: {self.kapsam.goreli(p)}")
        if not p.is_file():
            raise UygulamaHatasi(f"Dosya bulunamadi: {p}")
        if not eski_metin:
            raise UygulamaHatasi("`eski_metin` bos olamaz; yeni dosya icin dosya_yaz kullan.")
        if eski_metin == yeni_metin:
            raise UygulamaHatasi("`eski_metin` ve `yeni_metin` ayni.")
        ham = p.read_bytes()
        if ikili_mi(p, ham) or len(ham) > MAX_DOSYA_BAYT:
            raise UygulamaHatasi("Bu dosya yamaya uygun degil (ikili ya da cok buyuk).")
        self._hash_kontrol(p, beklenen_hash)
        metin = ham.decode("utf-8", errors="strict")
        adet = metin.count(eski_metin)
        if adet == 0:
            raise UygulamaHatasi(
                "Degistirilecek metin dosyada bulunamadi. Dosyayi yeniden oku: girinti ve "
                "satir sonu (CRLF/LF) birebir eslesmeli."
            )
        if adet > 1:
            raise UygulamaHatasi(f"Metin {adet} yerde geciyor; benzersiz olacak kadar baglam ekle.")
        once_hash, kopya, boyut = self.checkpointler.anlik_al(p)
        atomik_yaz(p, metin.replace(eski_metin, yeni_metin, 1).encode("utf-8"))
        sonra = dosya_hashi(p)
        cp = self._checkpoint(
            "dosya_yama",
            [
                DosyaDurumu(
                    yol=str(p),
                    islem=Islem.degistir,
                    once_hash=once_hash,
                    sonra_hash=sonra,
                    once_kopya=kopya,
                    boyut=boyut,
                )
            ],
            f"Yama: {self.kapsam.goreli(p)}",
        )
        return {
            "dosya": str(p),
            "goreli": self.kapsam.goreli(p),
            "degisen": 1,
            "yeni_hash": sonra,
            "checkpoint": cp,
        }

    def dosya_tasi(self, kaynak: str, hedef: str) -> dict:
        k = self.kapsam.coz(kaynak)
        h = self.kapsam.coz(hedef)
        self._izin(
            "dosya_tasi",
            YanEtki.yaz,
            h,
            f"Tasi: {self.kapsam.goreli(k)} -> {self.kapsam.goreli(h)}",
        )
        if not k.exists():
            raise UygulamaHatasi(f"Kaynak bulunamadi: {k}")
        if h.exists():
            raise UygulamaHatasi(f"Hedef zaten var: {h}")
        once_hash, kopya, boyut = self.checkpointler.anlik_al(k)
        h.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(k), str(h))
        cp = self._checkpoint(
            "dosya_tasi",
            [
                DosyaDurumu(
                    yol=str(k),
                    islem=Islem.tasi,
                    once_hash=once_hash,
                    sonra_hash=None,  # kaynak artik yok
                    once_kopya=kopya,
                    hedef=str(h),
                    boyut=boyut,
                )
            ],
            f"Tasindi: {self.kapsam.goreli(k)} -> {self.kapsam.goreli(h)}",
        )
        return {"kaynak": str(k), "hedef": str(h), "checkpoint": cp}

    def dosya_sil(self, yol: str, beklenen_hash: str | None = None) -> dict:
        p = self.kapsam.coz(yol)
        self._izin("dosya_sil", YanEtki.sil, p, f"SIL: {self.kapsam.goreli(p)}")
        if not p.is_file():
            raise UygulamaHatasi(f"Dosya bulunamadi: {p}")
        simdiki = dosya_hashi(p)
        if beklenen_hash and beklenen_hash != simdiki:
            raise UygulamaHatasi("Dosya en son okudugundan beri degisti; silme iptal edildi.")
        once_hash, kopya, boyut = self.checkpointler.anlik_al(p)
        p.unlink()
        cp = self._checkpoint(
            "dosya_sil",
            [
                DosyaDurumu(
                    yol=str(p),
                    islem=Islem.sil,
                    once_hash=once_hash,
                    sonra_hash=None,
                    once_kopya=kopya,
                    boyut=boyut,
                )
            ],
            f"Silindi: {self.kapsam.goreli(p)}",
        )
        return {"dosya": str(p), "silindi": True, "checkpoint": cp}


def sonuc_veya_hata(cagrilabilir, *args, **kw) -> dict:
    """Arac isleyicisi icin: izin/dogrulama hatalarini modele ANLASILIR sonuc olarak dondurur."""
    try:
        return cagrilabilir(*args, **kw)
    except OnayGerekli as e:
        return {"hata": e.mesaj, "karar": "onay_bekliyor", "onay": e.onay}
    except YetkiYok as e:
        return {"hata": str(e), "karar": "ret"}
    except UygulamaHatasi as e:
        return {"hata": e.mesaj, "karar": "hata"}
    except OSError as e:
        return {"hata": f"Dosya sistemi hatasi: {e}", "karar": "hata"}
