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
