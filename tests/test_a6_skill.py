"""A6 skill: proje skill'i API'de yalniz guvenilir projede (birim testler test_skiller.py'de)."""

from __future__ import annotations


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
