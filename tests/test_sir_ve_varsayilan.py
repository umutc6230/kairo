import json

from app.services import dpapi
from app.services.openrouter import OpenRouterDeposu


def test_gidis_donus():
    assert dpapi.coz(dpapi.sifrele("sk-or-v1-abc")) == "sk-or-v1-abc"


def test_anahtar_diske_duz_yazilmaz_ve_eski_kayit_tasinir(tmp_path):
    anahtar = "sk-or-v1-" + "a" * 30
    (tmp_path / "openrouter.json").write_text(json.dumps({"anahtar": anahtar}))
    d = OpenRouterDeposu(tmp_path)
    assert d.anahtar() == anahtar
    assert anahtar not in (tmp_path / "openrouter.json").read_text()
    d.anahtar_kaydet(anahtar)
    assert anahtar not in (tmp_path / "openrouter.json").read_text()
    assert d.anahtar() == anahtar


def test_yeni_proje_varsayilan_modelleri_alir_mevcut_korunur(tmp_path):
    from app.agent.workspaces import WorkspaceDeposu

    (tmp_path / "p").mkdir()
    d = WorkspaceDeposu(tmp_path / "veri")
    alan = d.ac(str(tmp_path / "p"), modeller=("k/model", "u/model"))
    assert (alan.koordinator_model, alan.uygulayici_model) == ("k/model", "u/model")
    alan = d.ac(str(tmp_path / "p"), modeller=("baska", "baska"))  # mevcut proje degismez
    assert alan.koordinator_model == "k/model"


def test_hafif_profil_kucuk_yerel_modelde_otomatik(monkeypatch):
    from types import SimpleNamespace as N

    from app.services.sohbet import MODELLER, SohbetServisi

    kucuk, buyuk = "test-1b", "test-27b"
    monkeypatch.setitem(MODELLER, kucuk, N(ram_gb=3.0))
    monkeypatch.setitem(MODELLER, buyuk, N(ram_gb=18.0))
    alan = N(koordinator_model="")
    hafif = SohbetServisi.hafif_mi

    def ayar(**k):
        return N(**{"baglam_profili": "otomatik", "saglayici": "yerel", "model": kucuk, **k})

    assert hafif(None, ayar(), alan)
    assert not hafif(None, ayar(model=buyuk), alan)
    assert not hafif(None, ayar(saglayici="openrouter"), alan)
    assert not hafif(None, ayar(baglam_profili="tam"), alan)
    assert hafif(None, ayar(baglam_profili="hafif", model=buyuk), alan)
