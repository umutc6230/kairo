"""Uygulama hatalari. Mesajlar kullaniciya gosterilir (Turkce).
Yerel model hatalari services/yerel_llm.py'de tanimli; burada tek yerden disari verilir."""

from app.services.yerel_llm import (  # noqa: F401 - tek giris noktasi
    BellekYetersiz,
    FarkliModelAcik,
    GoruntuDesteklenmiyor,
    ModelCevapHatasi,
    SesDesteklenmiyor,
    SunucuBaslamadi,
    SunucuKapali,
    YerelLLMHatasi,
)


class UygulamaHatasi(Exception):
    """Kullaniciya gosterilebilir uygulama hatasi; durum = HTTP kodu."""

    durum = 400

    def __init__(self, mesaj: str) -> None:
        super().__init__(mesaj)
        self.mesaj = mesaj


class Bulunamadi(UygulamaHatasi):
    durum = 404


class GecersizEk(UygulamaHatasi):
    pass


class MesgulHatasi(UygulamaHatasi):
    durum = 409


class YetkiYok(UygulamaHatasi):
    """Izin motoru ya da yol kapsami islemi reddetti (A1)."""

    durum = 403


class OnayGerekli(UygulamaHatasi):
    """Islem kullanici onayi bekliyor; onay kaydi `onay` alaninda doner (A1.4)."""

    durum = 409

    def __init__(self, mesaj: str, onay: dict | None = None) -> None:
        super().__init__(mesaj)
        self.onay = onay or {}
