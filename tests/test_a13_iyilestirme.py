"""A13 bulgularindan cikan iyilestirmelerin regresyon testleri."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_a3_ajan import proje  # noqa: F401 - fixture

from app.agent.dosyalar import KokKapsami
from app.agent.policy import hassas_mi

SIRLAR = [
    "credentials.json",
    "passwords.txt",
    "parola.txt",
    ".env",
    ".env.local",
    "id_rsa",
    "sunucu.pem",
    "kasa.kdbx",
    "secret.yaml",
]


@pytest.mark.parametrize("ad", SIRLAR)
def test_sir_dosyalari_hala_gizli(tmp_path, ad) -> None:
    assert hassas_mi(tmp_path / ad)


@pytest.mark.parametrize(
    "ad", ["parola.py", "password_reset.ts", "Credentials.cs", "secret_test.go"]
)
def test_kaynak_kod_adi_sir_kelimesi_icerse_okunur(tmp_path, ad) -> None:
    assert not hassas_mi(tmp_path / ad)


def test_proje_koku_ve_klasor_adi_sir_kelimesi_icerse_okunur(tmp_path) -> None:
    kok = tmp_path / "kesif-parola-hash"
    (kok / "password_reset").mkdir(parents=True)
    (kok / "password_reset" / "views.py").write_text("x = 1\n", encoding="utf-8")
    (kok / "password_reset" / "passwords.txt").write_text("gizli\n", encoding="utf-8")
    k = KokKapsami([kok])
    assert k.coz(".") == kok.resolve() or k.coz(".") == kok
    assert k.coz("password_reset/views.py").name == "views.py"
    with pytest.raises(Exception, match="gizli bilgi"):
        k.coz("password_reset/passwords.txt")
    assert Path(".ssh") and hassas_mi(tmp_path / ".ssh" / "config")


async def test_ardisik_izin_reddinde_butce_yenmeden_durur(tmp_path, proje) -> None:  # noqa: F811
    from test_a3_ajan import SahteModel, bitir, cagri, kur

    from app.agent.runner import RunDurum

    model = SahteModel([cagri("proje_dosya_oku", yol=f"../disari{i}.txt") for i in range(30)])
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("disariyi oku")).id)
    assert run.durum is RunDurum.basarisiz and "Ardisik 6" in run.hata
    assert run.kullanim.adim <= 7


def test_dosya_ara_bos_klasor_proje_kokunu_kullanir(tmp_path) -> None:
    from app.services.sohbet_araclari import DosyaAraclari

    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    assert DosyaAraclari([tmp_path])._coz("") == tmp_path.resolve()
