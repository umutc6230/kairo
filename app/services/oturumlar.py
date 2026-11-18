"""Sohbet oturumlari: her oturum data/oturumlar/<id>.json."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services.depo import json_oku, json_yaz


def simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


class EkOzet(BaseModel):
    id: str
    ad: str
    tur: str  # resim | pdf | ses | metin


class Mesaj(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    rol: str  # kullanici | asistan
    metin: str = ""
    ekler: list[EkOzet] = []
    dusunce: str = ""
    model: str = ""
    istatistik: dict = {}
    araclar: list[dict] = []  # sohbette cagrilan araclar (ad, argumanlar, ozet)
    hata: str = ""
    zaman: str = Field(default_factory=simdi)


class Oturum(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    baslik: str = "Yeni sohbet"
    olusturma: str = Field(default_factory=simdi)
    guncelleme: str = Field(default_factory=simdi)
    mesajlar: list[Mesaj] = []
    # Sohbetten baslatilan ajan gorevleri ({run, metin}); eskiden yalniz tarayici deposundaydi ve
    # her acilista degisen port yuzunden kayboluyordu.
    ajan_runlari: list[dict] = []
    ust: str = ""  # alt oturumsa ana oturumun id'si (listede altinda acilir)
    alan: str = ""  # olusturuldugu proje (calisma alani) id'si; bos = eski kayit / proje yok
    # model alt_oturum_oner ile onerdi; kullanici karari: kaynak -> alt oturum id | "reddedildi"
    oneri_kararlari: dict[str, str] = {}


def baslik_uret(metin: str) -> str:
    tek = re.sub(r"\s+", " ", metin).strip()
    return (tek[:48] + "...") if len(tek) > 48 else (tek or "Yeni sohbet")


class OturumDeposu:
    def __init__(self, veri_dizini: Path) -> None:
        self.dizin = veri_dizini / "oturumlar"
        self.dizin.mkdir(parents=True, exist_ok=True)

    def _yol(self, oturum_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{6,32}", oturum_id):
            raise Bulunamadi("Sohbet bulunamadi.")
        return self.dizin / f"{oturum_id}.json"

    def olustur(self, alan: str = "") -> Oturum:
        return self.kaydet(Oturum(alan=alan))

    def getir(self, oturum_id: str) -> Oturum:
        ham = json_oku(self._yol(oturum_id))
        if ham is None:
            raise Bulunamadi("Sohbet bulunamadi.")
        return Oturum(**ham)

    def kaydet(self, oturum: Oturum) -> Oturum:
        oturum.guncelleme = simdi()
        json_yaz(self._yol(oturum.id), oturum.model_dump())
        return oturum

    def sil(self, oturum_id: str) -> None:
        yol = self._yol(oturum_id)
        if not yol.exists():
            raise Bulunamadi("Sohbet bulunamadi.")
        yol.unlink()

    def catal(self, oturum_id: str) -> Oturum:
        """Ayni gecmisle YENI oturum (fork); asil oturum degismez."""
        asil = self.getir(oturum_id)
        kopya = Oturum(baslik=f"{asil.baslik} (kopya)"[:120], mesajlar=list(asil.mesajlar))
        return self.kaydet(kopya)

    def geri_sar(self, oturum_id: str, mesaj_id: str = "", run: str = "") -> tuple[Oturum, str]:
        """Claude Code rewind: secilen kullanici mesaji ve SONRASI silinir; metni geri doner
        (girdiye konur). Ajan turlarinda `run` ile o gorev kaydi ve sonrakiler silinir.
        Dosya degisikliklerine dokunmaz (onlar checkpoint /rewind ile geri alinir)."""
        o = self.getir(oturum_id)
        if mesaj_id:
            i = next((n for n, m in enumerate(o.mesajlar) if m.id == mesaj_id), None)
            if i is None or o.mesajlar[i].rol != "kullanici":
                raise UygulamaHatasi("Geri sarilacak kullanici mesaji bulunamadi.")
            metin = o.mesajlar[i].metin
            o.mesajlar = o.mesajlar[:i]
        elif run:
            i = next((n for n, k in enumerate(o.ajan_runlari) if k.get("run") == run), None)
            if i is None:
                raise UygulamaHatasi("Geri sarilacak ajan turu bulunamadi.")
            metin = str(o.ajan_runlari[i].get("metin", ""))
            o.ajan_runlari = o.ajan_runlari[:i]
        else:
            raise UygulamaHatasi("Geri sarmak icin mesaj ya da ajan turu secilmeli.")
        return self.kaydet(o), metin

    def temizle(self, oturum_id: str) -> Oturum:
        """Mesajlari siler, oturum kalir. Kalici hafizaya DOKUNMAZ (A4.5)."""
        o = self.getir(oturum_id)
        o.mesajlar = []
        return self.kaydet(o)

    def disa_aktar_md(self, oturum_id: str) -> str:
        o = self.getir(oturum_id)
        satirlar = [f"# {o.baslik}", f"_olusturma: {o.olusturma}_", ""]
        for m in o.mesajlar:
            satirlar += [f"## {m.rol}", m.metin or "", ""]
        return "\n".join(satirlar)

    def ajan_run_ekle(self, oturum_id: str, run: str, metin: str) -> Oturum:
        oturum = self.getir(oturum_id)
        if not any(k.get("run") == run for k in oturum.ajan_runlari):
            oturum.ajan_runlari.append({"run": str(run)[:64], "metin": str(metin)[:4000]})
            oturum = self.kaydet(oturum)
        return oturum

    def alt_olustur(self, ust_id: str, baslik: str, kaynak: str = "") -> Oturum:
        """Kullanici onayiyla alt oturum: bos gecmisle baslar, listede ana oturumun altinda."""
        ust = self.getir(ust_id)
        alt = self.kaydet(Oturum(baslik=baslik_uret(baslik)[:80], ust=ust.id, alan=ust.alan))
        if kaynak:
            ust.oneri_kararlari[kaynak[:64]] = alt.id
            self.kaydet(ust)
        return alt

    def oneri_reddet(self, ust_id: str, kaynak: str, karar: str = "reddedildi") -> Oturum:
        """karar: "reddedildi" ya da "is:<is emri id>" (oneri arka planda is emri olarak acildi)."""
        ust = self.getir(ust_id)
        ust.oneri_kararlari[kaynak[:64]] = karar
        return self.kaydet(ust)

    def yeniden_adlandir(self, oturum_id: str, baslik: str) -> Oturum:
        oturum = self.getir(oturum_id)
        oturum.baslik = baslik.strip()[:80] or "Yeni sohbet"
        return self.kaydet(oturum)

    def liste(self, arama: str = "") -> list[dict]:
        aranan = arama.strip().lower()
        sonuc = []
        for yol in self.dizin.glob("*.json"):
            ham = json_oku(yol)
            if not ham:
                continue
            if (
                aranan
                and aranan not in ham.get("baslik", "").lower()
                and not any(aranan in m.get("metin", "").lower() for m in ham.get("mesajlar", []))
            ):
                continue
            sonuc.append(
                {
                    "id": ham["id"],
                    "baslik": ham.get("baslik", ""),
                    "guncelleme": ham.get("guncelleme", ""),
                    "mesaj_sayisi": len(ham.get("mesajlar", [])),
                    "ajan_sayisi": len(ham.get("ajan_runlari", [])),
                    "ust": ham.get("ust", ""),
                    "alan": ham.get("alan", ""),
                }
            )
        return sorted(sonuc, key=lambda o: o["guncelleme"], reverse=True)
