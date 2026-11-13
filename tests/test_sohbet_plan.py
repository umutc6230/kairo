from app.services.sohbet_araclari import PLAN_ARACI, plan_isleyici


def test_plan_normallestirir():
    s = plan_isleyici(
        [{"baslik": " A ", "durum": "tamam"}, {"baslik": "B", "durum": "xx"}, {"x": 1}]
    )
    assert s["plan"] == [{"baslik": "A", "durum": "tamam"}, {"baslik": "B", "durum": "bekliyor"}]
    assert s["ilerleme"] == "1/2"


def test_bos_plan_hata():
    assert "hata" in plan_isleyici([])


def test_sema_adi():
    assert PLAN_ARACI["function"]["name"] == "plan_guncelle"
