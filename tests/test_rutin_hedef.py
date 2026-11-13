"""OpenBot rutin cumlesi: simdi bir kez, yalniz bildir, hedefe ulasinca dur."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.agent.zamanlayici import Zamanlayici


def test_bir_kez_hemen_calisir_ve_kapanir(tmp_path):
    z = Zamanlayici(tmp_path)
    simdi = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    r = z.ekle({"ad": "tek", "hedef": "x", "proje_kok": str(tmp_path), "tur": "bir_kez"}, simdi)
    ilk = z.tick(simdi + timedelta(seconds=5), lambda _: "calisiyor")
    assert [t.zamanlama for t in ilk] == [r.id]
    assert not z.liste()[0].aktif
    assert z.tick(simdi + timedelta(days=2), lambda _: "basarili") == []


def test_bildir_ve_bitis_kosulu_alanlari_ve_hedefe_ulasma(tmp_path):
    z = Zamanlayici(tmp_path)
    r = z.ekle({"ad": "izle", "hedef": "surum notlarini izle", "proje_kok": str(tmp_path),
                "tur": "aralik", "aralik_dk": 60, "davranis": "bildir",
                "bitis_kosulu": "v2 yayinlandi"})  # fmt: skip
    assert r.davranis == "bildir" and r.bitis_kosulu == "v2 yayinlandi"
    z.hedefe_ulasti(r.id, datetime(2026, 11, 13, tzinfo=UTC))
    son = z.liste()[0]
    assert not son.aktif and son.tamamlandi.startswith("2026-11-13")
