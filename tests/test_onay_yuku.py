"""Onay yuku: guvenilir projede otomatik modda test/derleme komutlari onaysiz, gerisi sorulur."""

from __future__ import annotations

import pytest

from app.agent.policy import Istek, Karar, PolitikaMotoru, YanEtki, gelistirici_komutu_mu
from app.agent.workspaces import CalismaAlani, Guven, Mod

GUVENLI = ["pytest -q", "python -m pytest tests", "npm test", "npm run build", "dotnet test",
           "cargo check", "go test ./...", "git status", "git diff", "ruff check ."]  # fmt: skip
SORULAN = ["pytest && rm -rf x", "npm test > out.txt", "echo $(whoami)", "rm -rf build",
           "npm install left-pad", "git push", "python x.py", "ls\nrm a", "cat .env",
           "dir %USERPROFILE%", "pytestx", "git branch -D main", "npm test | tee x"]  # fmt: skip


@pytest.mark.parametrize("komut", GUVENLI)
def test_gelistirici_komutu(komut):
    assert gelistirici_komutu_mu(komut)


@pytest.mark.parametrize("komut", SORULAN)
def test_gelistirici_komutu_degil(komut):
    assert not gelistirici_komutu_mu(komut)


def _karar(tmp_path, komut, guven=Guven.guvenilir, mod=Mod.otomatik):
    politika = PolitikaMotoru(tmp_path / "veri")
    alan = CalismaAlani(kokler=[str(tmp_path)], guven=guven, mod=mod)
    return politika.degerlendir(Istek(arac="komut_calistir", yan_etki=YanEtki.komut,
                                      komut=komut), alan).karar  # fmt: skip


def test_guvenilir_otomatikte_test_onaysiz(tmp_path):
    assert _karar(tmp_path, "pytest -q") is Karar.izin
    assert _karar(tmp_path, "rm -rf build") is Karar.sor


def test_sinirli_projede_ve_onayli_modda_yine_sorulur(tmp_path):
    assert _karar(tmp_path, "pytest -q", guven=Guven.sinirli) is not Karar.izin
    assert _karar(tmp_path, "pytest -q", mod=Mod.onayli) is Karar.sor
