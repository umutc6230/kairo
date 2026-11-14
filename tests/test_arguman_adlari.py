"""Model Turkce karakterli arguman adi gonderince (açıklama) arac yine calisir."""

from app.agent.runner import arguman_adlari


def test_turkce_anahtar_ascii_deger_korunur():
    a = arguman_adlari({"komut": "gh api user", "açıklama": "Hesabı oku", "İçerik": "ş"})
    assert a == {"komut": "gh api user", "aciklama": "Hesabı oku", "Icerik": "ş"}
