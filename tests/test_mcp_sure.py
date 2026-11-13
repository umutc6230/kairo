from app.agent.mcp import ZAMAN_ASIMI, arac_suresi


def test_arac_suresi_timeout_argumanina_uyar():
    assert arac_suresi({}) == ZAMAN_ASIMI
    assert arac_suresi({"timeout": 120}) == 135
    assert arac_suresi({"timeout": 5}) == ZAMAN_ASIMI  # en az 30
    assert arac_suresi({"timeout": 5000}) == 600  # ust sinir
    assert arac_suresi({"timeout": "120"}) == ZAMAN_ASIMI  # gecersiz tur
    assert arac_suresi({"timeout": True}) == ZAMAN_ASIMI
