from app.services import talimatlar
from app.services.talimatlar import TalimatDeposu


def test_kairo_md_brain_policy_import_eder_ve_tekrarlamaz(tmp_path, monkeypatch):
    policy = tmp_path / "Documents" / "brain" / "BRAIN-POLICY.md"
    policy.parent.mkdir(parents=True)
    policy.write_text("Kural: kisa yaz.", encoding="utf-8")
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("@~/Documents/brain/BRAIN-POLICY.md\n", encoding="utf-8")
    monkeypatch.setattr(talimatlar.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(talimatlar, "claude_md_yolu", lambda: claude)
    monkeypatch.setattr(talimatlar, "BRAIN_POLICY", policy)
    veri = tmp_path / "veri"
    veri.mkdir()
    d = TalimatDeposu(veri)
    assert "@~/Documents/brain/BRAIN-POLICY.md" in (veri / "KAIRO.md").read_text(encoding="utf-8")
    assert d.sistem_metni().count("Kural: kisa yaz.") == 1  # iki kaynak import etse de bir kez
    assert d.sistem_metni(claude=False).count("Kural: kisa yaz.") == 1  # yalniz KAIRO.md ile de


def test_eski_agents_md_kairo_md_ye_tasinir(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Eski talimat", encoding="utf-8")
    d = TalimatDeposu(tmp_path)
    assert d.uygulama_oku() == "Eski talimat" and not (tmp_path / "AGENTS.md").exists()
