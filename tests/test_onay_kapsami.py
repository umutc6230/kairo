"""OpenBot tarzi onay kapsamlari: bir kez / bu gorev / her zaman, ve dis etkili eylem turleri."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.policy import BAGLAM, Istek, Karar, PolitikaMotoru, YanEtki
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.exceptions import OnayGerekli, YetkiYok


def _kur(tmp_path: Path, tam: bool = False):
    m = PolitikaMotoru(tmp_path)
    m.tam_yetki = lambda: tam
    m.kullanici_ag = lambda: True
    alan = CalismaAlani(id="a" * 12, kokler=[str(tmp_path)], mod=Mod.onayli, guven=Guven.sinirli)
    return m, alan


def _iste(m, alan, komut="npm test"):
    ist = Istek(arac="komut_calistir", yan_etki=YanEtki.komut, komut=komut)
    try:
        m.uygula(ist, alan)
        return None
    except OnayGerekli as e:
        return e.onay["id"]


def test_bir_kez_onay_yalniz_ayni_islem(tmp_path):
    m, alan = _kur(tmp_path)
    BAGLAM.set("run1")
    oid = _iste(m, alan)
    m.onaylar.karar_ver(oid, True, "tek")
    assert _iste(m, alan) is None  # ayni islem: onayli
    assert _iste(m, alan) is not None  # tek seferlik: tekrar sorar
    assert _iste(m, alan, "npm run build") is not None


def test_sohbet_kapsami_ayni_baglamda_ayni_tur(tmp_path):
    m, alan = _kur(tmp_path)
    BAGLAM.set("run1")
    oid = _iste(m, alan)
    m.onaylar.karar_ver(oid, True, "sohbet")
    assert _iste(m, alan, "npm run build") is None  # ayni tur, farkli komut
    assert _iste(m, alan, "pytest") is None
    BAGLAM.set("run2")
    assert _iste(m, alan, "pytest") is not None  # baska gorev: tekrar sorar


def test_her_zaman_kurali_her_yerde_ve_kaldirilabilir(tmp_path):
    m, alan = _kur(tmp_path)
    BAGLAM.set("run1")
    oid = _iste(m, alan)
    m.onaylar.karar_ver(oid, True, "her_zaman")
    BAGLAM.set("run9")
    assert _iste(m, alan, "ls") is None
    kurallar = m.onaylar.kurallar()
    assert len(kurallar) == 1
    m.onaylar.kural_sil(kurallar[0]["id"])
    assert _iste(m, alan, "ls") is not None


def test_ret_kapsam_vermez_ve_gecersiz_kapsam(tmp_path):
    m, alan = _kur(tmp_path)
    BAGLAM.set("r")
    oid = _iste(m, alan)
    m.onaylar.karar_ver(oid, False, "her_zaman")
    assert m.onaylar.kurallar() == []
    with pytest.raises(YetkiYok):
        m.onaylar.karar_ver(_iste(m, alan, "x"), True, "sonsuz")


@pytest.mark.parametrize(
    "arac,ozet",
    [("mcp_github_create_pull_request", ""), ("mcp_gmail_send_message", ""),
     ("tarayici_tikla", "Place your order"), ("masaustu_tikla", "Gönder düğmesi"),
     ("mcp_drive_share_file", ""), ("mcp_github_delete_file", "")],
)  # fmt: skip
def test_tam_yetkide_riskli_dis_eylem_sorar(tmp_path, arac, ozet):
    m, alan = _kur(tmp_path, tam=True)
    s = m.degerlendir(Istek(arac=arac, yan_etki=YanEtki.dis, ozet=ozet), alan)
    assert s.karar is Karar.sor and s.kural == "eylem_turu"


@pytest.mark.parametrize(
    "arac,ozet",
    [("tarayici_tikla", "Login"), ("masaustu_yaz", "Not Defteri metin"),
     ("mcp_github_get_me", ""), ("mcp_github_list_commits", "")],
)  # fmt: skip
def test_tam_yetkide_siradan_dis_eylem_sormaz(tmp_path, arac, ozet):
    m, alan = _kur(tmp_path, tam=True)
    assert (
        m.degerlendir(Istek(arac=arac, yan_etki=YanEtki.dis, ozet=ozet), alan).karar is Karar.izin
    )
