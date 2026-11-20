"""A6 skill: proje skill'i API'de yalniz guvenilir projede (birim testler test_skiller.py'de)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from app.agent.runner import Run


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

async def test_worktree_ilk_model_adimindan_once_skill_secer(
    app, istemci, skill_klasoru, tmp_path, monkeypatch
) -> None:
    skill = skill_klasoru / "project-review"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: project-review\ndescription: Audit architecture and tests\n---\n"
        "Inspect manifests before drafting the plan.",
        encoding="utf-8",
    )
    proje = tmp_path / "repo"
    proje.mkdir()
    assert (await istemci.post("/api/projeler", json={"yol": str(proje)})).status_code == 200
    calls = []

    class SahteModel:
        model = "test/koordinator"

        async def metin(self, istem, **_):
            calls.append(istem)
            return "1"

        async def sohbet(self, mesajlar, **_):
            assert "Inspect manifests before drafting the plan." in mesajlar[0]["content"]
            return {"message": {"content": "plan"}}

    @asynccontextmanager
    async def kullan(_model=None):
        yield SahteModel()

    monkeypatch.setattr(app.state.sohbet.yonetici, "kullan", kullan)
    runner = app.state.ajan_runner
    run = Run(hedef="projeyi detaylı incele", calisma_koku=str(proje), dal="kairo/test")
    sistem, semalar, _ = await runner.gorev_baglami(run)
    assert run.skill_adi == "project-review"
    assert "Inspect manifests before drafting the plan." in sistem
    assert len(calls) == 1
    assert "project-review: Audit architecture and tests" in calls[0]
    runner.depo.kaydet(run)
    run = runner.depo.getir(run.id)
    await runner.gorev_baglami(run)
    assert len(calls) == 1

    run.mesajlar = [{"role": "user", "content": run.hedef}]
    assert await runner._model(run, sistem, semalar) is not None
    adim = runner._adim_olustur(run, {"function": {"name": "plan_guncelle"}})
    assert adim.model == run.son_model == SahteModel.model
