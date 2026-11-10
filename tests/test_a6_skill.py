"""A6 skill: metadata, bozuk frontmatter, duzenleme, proje kapsami."""

from __future__ import annotations

from pathlib import Path

from app.services import skiller as skl


def _depo(tmp_path: Path) -> skl.SkillDeposu:
    return skl.SkillDeposu(tmp_path, [("uygulama", tmp_path / "skills")])


def test_metadata_ve_izin_notu(tmp_path) -> None:
    d = _depo(tmp_path)
    s = d.olustur(
        "rapor", "Rapor yazar", "Adimlar", surum="1.2", gereken_araclar=["proje_dosya_oku", "x"]
    )
    o = s.ozet()
    assert o["surum"] == "1.2" and o["gereken_araclar"] == ["proje_dosya_oku", "x"]
    assert len(o["hash"]) == 16 and o["guven"] == "kullanici" and not o["hata"]
    isl = skl.arac_isleyicileri(d, set(), lambda: {"proje_dosya_oku"})
    r = isl["skill_kullan"]("rapor")
    assert r["eksik_araclar"] == ["x"] and "IZIN VERMEZ" in r["izin_notu"]


def test_bozuk_frontmatter_anlasilir_hata_ve_yuklenmez(tmp_path) -> None:
    k = tmp_path / "skills" / "bozuk"
    k.mkdir(parents=True)
    (k / "SKILL.md").write_text(
        "---\nname: bozuk\ndescription: [kapanmamis\n---\ngovde", encoding="utf-8"
    )
    d = _depo(tmp_path)
    s = d.getir("bozuk")
    assert "YAML hatasi" in s.hata
    r = skl.arac_isleyicileri(d, set())["skill_kullan"]("bozuk")
    assert "bozuk, yuklenmedi" in r["hata"]


def test_duzenleme_yalniz_uygulama_skillinde(tmp_path) -> None:
    d = _depo(tmp_path)
    s1 = d.olustur("a", "aciklama", "eski")
    s2 = d.guncelle("a", "yeni aciklama", "yeni", surum="2")
    assert s2.aciklama == "yeni aciklama" and s2.surum == "2" and s1.hash != s2.hash


def test_proje_skilli_yalniz_kaynak_verilince(tmp_path) -> None:
    proje = tmp_path / "p" / ".claude" / "skills" / "proje-skill"
    proje.mkdir(parents=True)
    (proje / "SKILL.md").write_text(
        "---\nname: proje-skill\ndescription: d\n---\nx", encoding="utf-8"
    )
    d = _depo(tmp_path)
    assert "proje-skill" not in {s.ad for s in d.kesfet()}  # guvenilmeyen/yok: eklenmez
    d.proje_kaynaklari = lambda: [("proje", tmp_path / "p" / ".claude" / "skills")]
    s = d.getir("proje-skill")
    assert s.kaynak == "proje" and s.ozet()["guven"] == "proje" and not s.ozet()["duzenlenebilir"]


async def test_api_guvenilmeyen_projede_proje_skill_yok(istemci, tmp_path) -> None:
    p = tmp_path / "repo"
    sk = p / ".claude" / "skills" / "kotu"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: kotu\ndescription: d\n---\nx", encoding="utf-8")
    await istemci.post("/api/projeler", json={"yol": str(p), "guven": "sinirli"})
    adlar = {s["ad"] for s in (await istemci.get("/api/skiller")).json()["skiller"]}
    assert "kotu" not in adlar
    await istemci.post("/api/projeler", json={"yol": str(p), "guven": "guvenilir"})
    adlar = {s["ad"] for s in (await istemci.get("/api/skiller")).json()["skiller"]}
    assert "kotu" in adlar
    t = (await istemci.get("/api/skiller/kotu/test")).json()
    assert t["skill"]["kaynak"] == "proje" and "talimat" in t["model_gorur"]
