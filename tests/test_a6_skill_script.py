"""Kabul A6.2: skill scriptleri yalniz ilan edilen kapsamda ve izin motoru karariyla calisir.

- manifestte (scripts:) ilan edilmemis dosya, klasor disi yol, yasak tur (bat/exe) calismaz
- komut zinciri kurabilecek arguman reddedilir
- onayli modda onay gelmeden calismaz; onay script ICERIGINE baglidir (degisirse gecersiz)
- salt okunur mod / guvenilmeyen projede ret; bozuk skill'in scripti calismaz
- arac yalniz ajan komut araci acikken modele sunulur
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import IzoleSahte

from app.agent.araclar import AjanAracKaydi
from app.agent.checkpoints import CheckpointDeposu
from app.agent.policy import PolitikaMotoru
from app.agent.terminal import KomutServisi
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.exceptions import UygulamaHatasi
from app.services import skiller as skl

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

SCRIPT = (
    "import sys, pathlib\n"
    "pathlib.Path('cikti.txt').write_text(' '.join(sys.argv[1:]))\n"
    "print('TAMAM')\n"
)


@pytest.fixture
def skill_depo(tmp_path: Path) -> skl.SkillDeposu:
    kok = tmp_path / "skills"
    d = kok / "donustur"
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: donustur\ndescription: Dosya donusturur.\n"
        "scripts: [scripts/yaz.py, scripts/kotu.bat]\n---\nGovde\n",
        encoding="utf-8",
    )
    (d / "scripts" / "yaz.py").write_text(SCRIPT, encoding="utf-8")
    (d / "scripts" / "gizli.py").write_text(SCRIPT, encoding="utf-8")  # ilan EDILMEMIS
    (d / "scripts" / "kotu.bat").write_text("echo x\n", encoding="utf-8")  # ilan edilmis, yasak tur
    (tmp_path / "disari.py").write_text(SCRIPT, encoding="utf-8")
    b = kok / "bozuk"
    (b / "scripts").mkdir(parents=True)
    (b / "SKILL.md").write_text(
        "---\nname: bozuk\nscripts: [scripts/yaz.py\n---\n", encoding="utf-8"
    )
    (b / "scripts" / "yaz.py").write_text(SCRIPT, encoding="utf-8")
    return skl.SkillDeposu(tmp_path / "veri", [("claude", kok)])


def _kayit(tmp_path: Path, mod: Mod, guven: Guven = Guven.guvenilir, ad: str = "v"):
    proje = tmp_path / f"proje {ad}"
    proje.mkdir()
    veri = tmp_path / f"veri-{ad}"
    veri.mkdir()
    alan = CalismaAlani(id=ad * 12, ad="p", kokler=[str(proje)], guven=guven, mod=mod)
    politika = PolitikaMotoru(veri, izolasyon=IzoleSahte)
    return AjanAracKaydi(alan, politika, CheckpointDeposu(veri), KomutServisi()), politika, proje


def test_ilan_edilen_script_calisir_cikti_projede(tmp_path, skill_depo):
    kayit, _, proje = _kayit(tmp_path, Mod.otomatik)
    calistir = skl.script_isleyicisi(skill_depo, set(), kayit)["skill_scripti_calistir"]
    sonuc = calistir(ad="donustur", script="scripts/yaz.py", argumanlar=["merhaba", "dunya"])
    assert sonuc.get("cikis_kodu") == 0, sonuc
    assert "TAMAM" in sonuc["cikti"]
    assert (proje / "cikti.txt").read_text(encoding="utf-8") == "merhaba dunya"


@pytest.mark.parametrize(
    ("script", "beklenen"),
    [
        ("scripts/gizli.py", "ilan edilmemis"),
        ("../../disari.py", "ilan edilmemis"),
        ("scripts/kotu.bat", "calistirilmaz"),
    ],
)
def test_kapsam_disi_script_calismaz(tmp_path, skill_depo, script, beklenen):
    kayit, _, proje = _kayit(tmp_path, Mod.otomatik)
    sonuc = skl.script_isleyicisi(skill_depo, set(), kayit)["skill_scripti_calistir"](
        ad="donustur", script=script
    )
    assert sonuc["karar"] == "hata" and beklenen in sonuc["hata"]
    assert not (proje / "cikti.txt").exists()


@pytest.mark.parametrize("arg", ["a & del x", "a | b", "x > y", "%PATH%", 'a"b', "a\nb"])
def test_komut_zinciri_argumani_reddedilir(skill_depo, arg):
    with pytest.raises(UygulamaHatasi, match="Arguman"):
        skl.script_plani(skill_depo.getir("donustur"), "scripts/yaz.py", [arg])


def test_bozuk_skill_scripti_calismaz(skill_depo):
    with pytest.raises(UygulamaHatasi, match="bozuk"):
        skl.script_plani(skill_depo.getir("bozuk"), "scripts/yaz.py")


def test_onay_icerige_bagli(tmp_path, skill_depo):
    kayit, politika, proje = _kayit(tmp_path, Mod.onayli)
    calistir = skl.script_isleyicisi(skill_depo, set(), kayit)["skill_scripti_calistir"]
    ilk = calistir(ad="donustur", script="scripts/yaz.py", argumanlar=["bir"])
    assert ilk["karar"] == "onay_bekliyor" and not (proje / "cikti.txt").exists()
    assert "sha256" in ilk["onay"]["ozet"] and ilk["onay"]["arac"] == "skill_scripti"
    politika.onaylar.karar_ver(ilk["onay"]["id"], True)

    # onaydan SONRA script degisti -> eski onay bu icerigi kapsamaz
    hedef = skill_depo.getir("donustur").klasor / "scripts" / "yaz.py"
    hedef.write_text(SCRIPT + "# degisti\n", encoding="utf-8")
    ikinci = calistir(ad="donustur", script="scripts/yaz.py", argumanlar=["bir"])
    assert ikinci["karar"] == "onay_bekliyor" and not (proje / "cikti.txt").exists()

    politika.onaylar.karar_ver(ikinci["onay"]["id"], True)
    assert calistir(ad="donustur", script="scripts/yaz.py", argumanlar=["bir"])["cikis_kodu"] == 0
    # tek seferlik: ayni onay tekrar kullanilamaz
    assert calistir(ad="donustur", script="scripts/yaz.py", argumanlar=["bir"])["karar"] == (
        "onay_bekliyor"
    )


@pytest.mark.parametrize(
    ("mod", "guven"), [(Mod.planla, Guven.guvenilir), (Mod.otomatik, Guven.guvenilmeyen)]
)
def test_salt_okunur_halde_ret(tmp_path, skill_depo, mod, guven):
    kayit, _, proje = _kayit(tmp_path, mod, guven)
    sonuc = skl.script_isleyicisi(skill_depo, set(), kayit)["skill_scripti_calistir"](
        ad="donustur", script="scripts/yaz.py"
    )
    assert sonuc["karar"] == "ret" and not (proje / "cikti.txt").exists()


def test_kapali_skill_scripti_bulunamaz(tmp_path, skill_depo):
    kayit, *_ = _kayit(tmp_path, Mod.otomatik)
    sonuc = skl.script_isleyicisi(skill_depo, {"donustur"}, kayit)["skill_scripti_calistir"](
        ad="donustur", script="scripts/yaz.py"
    )
    assert "hata" in sonuc and "cikis_kodu" not in sonuc


def test_manifest_scriptleri_ozette(skill_depo):
    assert skill_depo.getir("donustur").ozet()["scriptler"] == [
        "scripts/kotu.bat",
        "scripts/yaz.py",
    ]
