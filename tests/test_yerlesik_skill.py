"""Uygulamayla gelen belge skill'leri (docx, pdf; Apache-2.0, app/skills/NOTICE.txt)."""

from __future__ import annotations

from pathlib import Path

from app.config import yerlesik_skill_dizini
from app.services.skiller import SkillDeposu, varsayilan_kaynaklar


def test_varsayilan_kaynaklarda_en_sonda(tmp_path: Path) -> None:
    kaynaklar = varsayilan_kaynaklar(tmp_path)
    assert kaynaklar[-1] == ("yerlesik", yerlesik_skill_dizini())


def test_docx_pdf_hatasiz_lisansli_ve_kairo_notlu() -> None:
    kok = yerlesik_skill_dizini()
    d = SkillDeposu(Path("."), [("yerlesik", kok)])
    bulunan = {s.ad: s for s in d.kesfet()}
    assert set(bulunan) == {"docx", "pdf"}  # NOTICE skill sanilmaz
    for ad, s in bulunan.items():
        assert not s.hata and s.aciklama
        assert "Apache License" in (kok / ad / "LICENSE.txt").read_text(encoding="utf-8")
        assert "Kairo (Windows) notu" in (kok / ad / "SKILL.md").read_text(encoding="utf-8")
    assert "\x07" not in (kok / "pdf" / "SKILL.md").read_text(encoding="utf-8")


def test_ayni_adli_kullanici_skilli_onde(tmp_path: Path) -> None:
    benim = tmp_path / "skills" / "pdf"
    benim.mkdir(parents=True)
    (benim / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: benim pdf\n---\nx", encoding="utf-8"
    )
    d = SkillDeposu(
        tmp_path, [("uygulama", tmp_path / "skills"), ("yerlesik", yerlesik_skill_dizini())]
    )
    pdf = [s for s in d.kesfet() if s.ad == "pdf"]
    assert pdf[0].kaynak == "uygulama"
