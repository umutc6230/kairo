"""Oturumlar arasi koordinasyon: sahiplenme, kira dolumu, mesaj, bekleme, sistem notu."""

from __future__ import annotations

import threading

import pytest

from app.agent.koordinasyon import KIRA_SN, DosyaMesgul, Koordinasyon


class Saat:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def k() -> tuple[Koordinasyon, Saat]:
    s = Saat()
    return Koordinasyon(saat=s), s


def test_ayni_dosyaya_ikinci_oturum_yazamaz(k) -> None:
    ko, _ = k
    ko.kaydol("oturum:a", "p1", "Giris sayfasi")
    ko.sahiplen("oturum:a", "p1", "app/x.py")
    ko.sahiplen("oturum:a", "p1", "app/x.py")  # sahibi tekrar yazabilir
    with pytest.raises(DosyaMesgul, match="Giris sayfasi"):
        ko.sahiplen("oturum:b", "p1", "app/x.py")
    ko.sahiplen("oturum:b", "p1", "app/y.py")  # baska dosya serbest
    ko.sahiplen("oturum:b", "p2", "app/x.py")  # baska proje serbest


def test_kira_dolunca_ve_ayrilinca_serbest(k) -> None:
    ko, s = k
    ko.sahiplen("gorev:r1", "p1", "a.py")
    s.t += KIRA_SN + 1
    ko.sahiplen("oturum:b", "p1", "a.py")  # coken gorevin kilidi kalmaz
    ko.ayril("oturum:b")
    ko.sahiplen("oturum:c", "p1", "a.py")


def test_mesaj_teslimi_ve_sistem_notu(k) -> None:
    ko, _ = k
    ko.kaydol("oturum:a", "p1", "Rapor")
    ko.kaydol("oturum:b", "p1", "Test yazimi")
    ko.sahiplen("oturum:b", "p1", "tests/t.py")
    ko.mesaj("oturum:a", "oturum:b", "t.py'ye dokunma, ben yeniden adlandiriyorum")
    ko.mesaj("oturum:a", "oturum:b", "Rapor kismini sen bitir", "devir")
    with pytest.raises(Exception, match="aktif degil"):
        ko.mesaj("oturum:a", "oturum:yok", "x")
    notu_b = ko.sistem_notu("oturum:b", "p1")
    assert "Rapor (oturum:a)" in notu_b and "dokunma" in notu_b and "IS DEVRI" in notu_b
    assert "IS DEVRI" not in ko.sistem_notu("oturum:b", "p1")  # bir kez teslim edilir
    assert "tests/t.py" in ko.sistem_notu("oturum:a", "p1")  # a, b'nin dosyasini gorur


def test_bekle_serbest_kalinca_uyanir(k) -> None:
    ko, _ = k
    ko.sahiplen("oturum:a", "p1", "a.py")
    threading.Timer(0.3, ko.ayril, args=("oturum:a",)).start()
    assert ko.bekle("oturum:b", "p1", "a.py", 10)["serbest"] is True
    ko.sahiplen("oturum:c", "p1", "b.py")
    assert ko.bekle("oturum:b", "p1", "b.py", 1)["serbest"] is False


def test_kimliksiz_islem_koordinasyon_disi(k) -> None:
    ko, _ = k
    ko.sahiplen("oturum:a", "p1", "a.py")
    ko.sahiplen("", "p1", "a.py")  # arayuzden dogrudan islem: engellenmez


def test_gercek_yazma_araci_ikinci_oturumu_onaysiz_durdurur(tmp_path) -> None:
    """Uctan uca: ayni projede A oturumu dosyayi yazar; B'nin yazmasi diske dokunmadan reddedilir,
    A turunu bitirince B yazabilir."""
    from conftest import IzoleSahte

    from app.agent import koordinasyon as koord
    from app.agent.araclar import AjanAracKaydi
    from app.agent.checkpoints import CheckpointDeposu, dosya_hashi
    from app.agent.policy import PolitikaMotoru
    from app.agent.terminal import KomutServisi
    from app.agent.workspaces import CalismaAlani, Guven, Mod

    proje = tmp_path / "proje"
    proje.mkdir()
    veri = tmp_path / "veri"
    veri.mkdir()
    alan = CalismaAlani(id="k" * 12, ad="p", kokler=[str(proje)], guven=Guven.guvenilir,
                        mod=Mod.otomatik)  # fmt: skip
    yazma = AjanAracKaydi(
        alan, PolitikaMotoru(veri, izolasyon=IzoleSahte), CheckpointDeposu(veri), KomutServisi()
    ).yazma

    def yaz(oturum: str, icerik: str) -> None:
        j = koord.AKTIF_OTURUM.set(oturum)
        try:
            x = proje / "x.py"
            yazma.dosya_yaz("x.py", icerik, dosya_hashi(x) if x.exists() else None)
        finally:
            koord.AKTIF_OTURUM.reset(j)

    yaz("a", "a = 1\n")
    with pytest.raises(DosyaMesgul):
        yaz("b", "b = 2\n")
    assert (proje / "x.py").read_text() == "a = 1\n"
    koord.KOORD.ayril("oturum:a")
    yaz("b", "b = 2\n")
    assert (proje / "x.py").read_text() == "b = 2\n"
    koord.KOORD.ayril("oturum:b")


async def test_model_diger_oturumu_ve_mesaji_gorur(app, istemci, tmp_path) -> None:
    from app.agent import koordinasyon as koord

    (tmp_path / "p").mkdir()
    p = (await istemci.post("/api/projeler", json={"yol": str(tmp_path / "p")})).json()["id"]
    await istemci.post(f"/api/projeler/{p}/etkin")
    await istemci.put(f"/api/projeler/{p}/guven", json={"guven": "guvenilir"})
    await istemci.put(f"/api/projeler/{p}/mod", json={"mod": "otomatik"})  # yazma araclari acik
    s = app.state.sohbet
    koord.KOORD.kaydol("oturum:o1", p, "fatura")  # o1'in suren turu (mesaj yalniz aktif olana)
    koord.KOORD.kaydol("gorev:r9", p, "Odeme modulu refaktoru")
    koord.KOORD.sahiplen("gorev:r9", p, "odeme.py")
    koord.KOORD.mesaj("gorev:r9", "oturum:o1", "odeme.py'yi ben degistiriyorum")
    j = koord.AKTIF_OTURUM.set("o1")
    try:
        sistem, araclar, isl, _ = s.baglam_hazirla(s.yonetici.ayarlar.oku(), "fatura ekle", [])
    finally:
        koord.AKTIF_OTURUM.reset(j)
    assert "Odeme modulu refaktoru (gorev:r9): odeme.py" in sistem
    assert "odeme.py'yi ben degistiriyorum" in sistem
    assert {"oturumlari_gor", "oturuma_mesaj", "dosya_bekle", "isi_devret"} <= set(isl)
    assert any(o["kimlik"] == "oturum:o1" for o in koord.KOORD.aktifler(p))  # kendisi kaydoldu
    koord.KOORD.ayril("gorev:r9")
    koord.KOORD.ayril("oturum:o1")
