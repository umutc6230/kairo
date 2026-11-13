from app.agent.mcp import ZAMAN_ASIMI, arac_suresi


def test_arac_suresi_timeout_argumanina_uyar():
    assert arac_suresi({}) == ZAMAN_ASIMI
    assert arac_suresi({"timeout": 120}) == 135
    assert arac_suresi({"timeout": 5}) == ZAMAN_ASIMI  # en az 30
    assert arac_suresi({"timeout": 5000}) == 600  # ust sinir
    assert arac_suresi({"timeout": "120"}) == ZAMAN_ASIMI  # gecersiz tur
    assert arac_suresi({"timeout": True}) == ZAMAN_ASIMI


def test_arac_suresi_duration_argumanina_uyar():
    # Windows-MCP Wait(duration=45) 30 sn'de kesilip "cevap vermedi" hatasi veriyordu
    assert arac_suresi({"duration": 45}) == 60
    assert arac_suresi({"duration": 45, "timeout": 100}) == 115  # buyuk olan
