"""A1.8: izolasyon adaptoru ve otomatik modun izolasyona gore daraltilmasi."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import IzoleSahte

from app.agent.izolasyon import KonteynerAdaptoru, YokAdaptoru, adaptor_olustur
from app.agent.policy import Istek, Karar, PolitikaMotoru, YanEtki
from app.agent.terminal import KomutServisi
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.exceptions import UygulamaHatasi
from app.services.ayarlar import KullaniciAyarlari


@pytest.fixture
def alan(tmp_path: Path) -> CalismaAlani:
    kok = tmp_path / "proje"
    (kok / "alt").mkdir(parents=True)
    return CalismaAlani(id="9" * 12, kokler=[str(kok)], guven=Guven.guvenilir, mod=Mod.otomatik)


def _karar(motor: PolitikaMotoru, alan: CalismaAlani, yan_etki: YanEtki):
    return motor.degerlendir(
        Istek(arac="x", yan_etki=yan_etki, yol=alan.kokler[0], komut="pytest"), alan
    )


def test_izolasyonsuz_otomatik_modda_komut_onay_ister(tmp_path: Path, alan) -> None:
    motor = PolitikaMotoru(tmp_path)  # varsayilan: YokAdaptoru
    s = _karar(motor, alan, YanEtki.komut)
    assert s.karar is Karar.sor and s.kural == "izolasyonsuz_komut"
    assert _karar(motor, alan, YanEtki.yaz).karar is Karar.izin  # dosya yazma daraltilmadi
    bilgi = motor.bilgi(alan)
    assert bilgi["izolasyon"] == "yok" and bilgi["otomatik_komut"] == "onay ister"


def test_izole_adaptorle_otomatik_komut_izinli(tmp_path: Path, alan) -> None:
    motor = PolitikaMotoru(tmp_path, izolasyon=IzoleSahte)
    assert _karar(motor, alan, YanEtki.komut).karar is Karar.izin
    assert motor.bilgi(alan)["otomatik_komut"] == "izinli"


def test_planla_modu_izolasyonla_genislemez(tmp_path: Path, alan) -> None:
    alan.mod = Mod.planla
    motor = PolitikaMotoru(tmp_path, izolasyon=IzoleSahte)
    assert _karar(motor, alan, YanEtki.komut).karar is Karar.ret


def test_motor_yoksa_kullanilamaz_ve_sessiz_dusus_yok(tmp_path: Path) -> None:
    a = KonteynerAdaptoru("python:3.12-slim", motor="")
    d = a.durum()
    assert not d["kullanilabilir"] and not a.izole
    with pytest.raises(UygulamaHatasi, match="kullanilamiyor"):
        a.sar("echo x", tmp_path, tmp_path)


async def test_komut_servisi_izolasyon_kullanilamazsa_calistirmaz(tmp_path: Path) -> None:
    s = KomutServisi(izolasyon=lambda: KonteynerAdaptoru("python:3.12-slim", motor=""))
    with pytest.raises(UygulamaHatasi, match="kullanilamiyor"):
        await s.baslat("echo x", tmp_path)
    assert s.isler == {}  # hicbir surec baslamadi


def _sahte_calistir(kodlar: dict[str, int]):
    def calistir(*a: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(a), kodlar.get(a[0], 0), "", "")

    return calistir


def test_yoklama_makine_kapali_ve_imaj_yok(monkeypatch) -> None:
    a = KonteynerAdaptoru("python:3.12-slim", motor="podman")
    monkeypatch.setattr(a, "_calistir", _sahte_calistir({"info": 125}))
    assert "machine start" in a.durum()["not"]

    b = KonteynerAdaptoru("python:3.12-slim", motor="podman")
    monkeypatch.setattr(b, "_calistir", _sahte_calistir({"image": 1}))
    d = b.durum()
    assert not d["kullanilabilir"] and "podman pull python:3.12-slim" in d["not"]  # indirmez

    c = KonteynerAdaptoru("python:3.12-slim", motor="podman")
    monkeypatch.setattr(c, "_calistir", _sahte_calistir({}))
    assert c.izole and c.durum()["kullanilabilir"]


def test_konteyner_argv_ag_kapali_yalniz_proje_bagli(monkeypatch, alan) -> None:
    a = KonteynerAdaptoru("python:3.12-slim", motor="podman")
    monkeypatch.setattr(a, "_calistir", _sahte_calistir({}))
    kok = Path(alan.kokler[0])
    argv = a.sar("pytest -q; echo 'tirnak'", kok / "alt", kok)
    assert argv is not None
    metin = " ".join(argv)
    assert "--network none" in metin and "--pull=never" in metin and "--cap-drop ALL" in metin
    assert "no-new-privileges" in metin and f"{kok}:/w" in argv
    assert argv[argv.index("-w") + 1] == "/w/alt"
    assert argv[-3:] == ["sh", "-c", "pytest -q; echo 'tirnak'"]  # komut tek arguman, kabuk icinde


def test_adaptor_secimi_ve_ayar_dogrulama() -> None:
    assert isinstance(adaptor_olustur("yok", "x"), YokAdaptoru)
    assert isinstance(adaptor_olustur("konteyner", "python:3.12-slim"), KonteynerAdaptoru)
    with pytest.raises(ValueError):
        KullaniciAyarlari(konteyner_imaj="python; rm -rf /")
    with pytest.raises(ValueError):
        KullaniciAyarlari(izolasyon="wsl")
    assert KullaniciAyarlari().izolasyon == "yok"


async def test_api_izin_bilgisi_izolasyonu_gosterir(istemci) -> None:
    r = await istemci.put("/api/ayarlar", json={"izolasyon": "konteyner"})
    assert r.status_code == 200 and r.json()["izolasyon"] == "konteyner"
