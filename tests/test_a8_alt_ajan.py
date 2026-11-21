"""A8.1/A8.4 alt ajan: dar arac seti, dosya sahipligi, butce kesme, derinlik, iptal, cokme."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from test_a3_ajan import SahteModel, YavasModel, bitir, cagri, kur

from app.agent.checkpoints import dosya_hashi
from app.agent.runner import AdimDurum, Butce, RunDurum


def _araclar(mesajlar_listesi: list) -> set[str]:
    return set()


class AracGozleyen(SahteModel):
    """Her cagrida modele sunulan arac adlarini kaydeder."""

    def __init__(self, senaryo):
        super().__init__(senaryo)
        self.araclar: list[set[str]] = []

    async def sohbet(self, mesajlar, **kw):
        self.araclar.append({t["function"]["name"] for t in kw.get("tools") or []})
        return await super().sohbet(mesajlar, **kw)


def test_alt_ajan_uygulayici_yalniz_sahip_oldugu_dosyaya_yazar(tmp_path) -> None:
    proje = tmp_path / "proje"
    (proje / "src").mkdir(parents=True)
    (proje / "src" / "a.py").write_bytes(b"x = 1\n")
    (proje / "src" / "b.py").write_bytes(b"y = 1\n")

    def yama(yol, eski, yeni):
        return lambda _m: cagri("proje_dosya_yama", yol=yol, eski_metin=eski, yeni_metin=yeni,
                                beklenen_hash=dosya_hashi(proje / yol))  # fmt: skip

    model = AracGozleyen([
        cagri("alt_ajan", gorev="a.py'de x'i 2 yap",
              araclar=["proje_dosya_oku", "proje_dosya_yama"],
              dosyalar=["src/a.py"], max_adim=8),  # fmt: skip
        # --- cocuk baglami ---
        yama("src/b.py", "y = 1", "y = 9"),  # sahip DEGIL -> reddedilir
        yama("src/a.py", "x = 1", "x = 2"),
        cagri("proje_dosya_oku", yol="src/a.py"),
        cagri("gorevi_bitir", ozet="x=2", kanit_adimlari=[3]),
        # --- ebeveyn devam ---
        cagri("proje_dosya_oku", yol="src/a.py"),
        cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[2]),
    ])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)
    run = asyncio.run(_calistir(runner, "x'i 2 yap"))

    assert run.durum is RunDurum.basarili, run.hata
    assert (proje / "src" / "a.py").read_bytes() == b"x = 2\n"
    assert (proje / "src" / "b.py").read_bytes() == b"y = 1\n"
    assert "alt_ajan" in model.araclar[0]
    cocuk_araclari = model.araclar[1]
    assert "alt_ajan" not in cocuk_araclari  # derinlik 1
    assert "komut_calistir" not in cocuk_araclari and "proje_dosya_yama" in cocuk_araclari
    cocuk = depo.getir(run.cocuklar[0])
    assert cocuk.parent == run.id and cocuk.adimlar[0].durum is AdimDurum.reddedildi
    sonuc = json.loads(run.adimlar[0].sonuc)
    assert sonuc["durum"] == "basarili" and sonuc["degisen_dosyalar"]
    # butce: cocugun harcamasi ebeveynde
    assert run.kullanim.adim >= 1 + cocuk.kullanim.adim


async def _calistir(runner, hedef, butce=None):
    run = await runner.baslat(hedef, butce=butce)
    return await bitir(runner, run.id)


def test_butce_cocuga_aktarilinca_cogalmaz(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    model = SahteModel([
        cagri("alt_ajan", gorev="sonsuz", araclar=["proje_listele"], max_adim=100),
        *[cagri("proje_listele") for _ in range(20)],
    ])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)
    run = asyncio.run(_calistir(runner, "x", Butce(max_adim=6)))
    cocuk = depo.getir(run.cocuklar[0])
    assert cocuk.butce.max_adim == 4  # 6 - alt_ajan adimi - 1 pay; 100 istense de
    assert run.kullanim.adim <= 6 + 1 and run.durum is RunDurum.basarisiz


def test_ayni_dosyaya_iki_calisan_alt_ajan_olamaz(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    runner, depo, *_ = kur(tmp_path, proje, SahteModel([]))
    from app.agent.runner import Run

    baska = Run(hedef="diger", parent="ffffffffffff", sahip_dosyalar=["src/a.py"])
    depo.kaydet(baska)  # calisiyor durumunda
    assert runner._sahiplik_cakisiyor(["SRC\\a.py"], "x") == baska.id
    assert runner._sahiplik_cakisiyor(["src/b.py"], "x") == ""


def test_ebeveyn_iptali_cocugu_durdurur(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    model = YavasModel([
        cagri("alt_ajan", gorev="uzun", araclar=["proje_listele"]),
        *[cagri("proje_listele") for _ in range(50)],
    ])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)

    async def senaryo():
        run = await runner.baslat("x")
        await asyncio.sleep(0.8)
        return await runner.iptal(run.id)

    run = asyncio.run(senaryo())
    assert run.durum is RunDurum.iptal
    cocuk = depo.getir(run.cocuklar[0])
    assert cocuk.durum is RunDurum.iptal  # yetim kalmadi


def test_eksik_arguman_ve_cokme_sonrasi_belirsiz(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    model = SahteModel([cagri("alt_ajan", gorev="", araclar=[]),
                        cagri("gorevi_bitir", ozet="x", kanit_adimlari=[])])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)
    run = asyncio.run(_calistir(runner, "x"))
    assert run.adimlar[0].durum is AdimDurum.hata and "gerekli" in run.adimlar[0].sonuc


def test_ayni_mesajdaki_alt_ajanlar_uzak_modelde_paralel_calisir(tmp_path) -> None:
    """Canli testte iki alt ajan sirayla kostu; uzak modelde ayni anda kosmali."""
    import time

    proje = tmp_path / "proje"
    (proje / "src").mkdir(parents=True)
    (proje / "src" / "a.py").write_bytes(b"x = 1\n")

    class Yonlendiren:
        """Mesaja gore cevap verir (paralel siralamadan bagimsiz); her cagri 0.3 sn surer."""

        async def sohbet(self, mesajlar, **_):
            await asyncio.sleep(0.3)
            ilk = mesajlar[1]["content"] if len(mesajlar) > 1 else ""
            arac_sonucu = [m for m in mesajlar if m.get("role") == "tool"]
            if "alt ajan" in ilk:  # cocuk: once oku, sonra bitir
                if not arac_sonucu:
                    return {
                        "message": cagri("proje_dosya_oku", yol="src/a.py"),
                        "finish_reason": "stop",
                    }
                return {"message": cagri("gorevi_bitir", ozet="okundu", kanit_adimlari=[1]),
                        "finish_reason": "stop"}  # fmt: skip
            if not arac_sonucu:  # ebeveyn: tek mesajda iki alt ajan

                def alt(g):
                    return cagri("alt_ajan", gorev=g, araclar=["proje_dosya_oku"], max_adim=8)

                iki = {"content": "", "tool_calls": [
                    alt(g)["tool_calls"][0] for g in ("A incele", "B incele")]}  # fmt: skip
                for i, c in enumerate(iki["tool_calls"]):
                    c["id"] = f"c{i}"
                return {"message": iki, "finish_reason": "stop"}
            return {"message": cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[1, 2]),
                    "finish_reason": "stop"}  # fmt: skip

    runner, depo, *_ = kur(tmp_path, proje, Yonlendiren())
    runner.paralel_model = lambda: True
    bas = time.monotonic()
    run = asyncio.run(_calistir(runner, "ikili inceleme"))
    sure = time.monotonic() - bas
    assert run.durum is RunDurum.basarili, run.hata
    cocuklar = [depo.getir(c) for c in run.cocuklar]
    assert len(cocuklar) == 2 and all(c.durum is RunDurum.basarili for c in cocuklar)
    # sirali: yalniz uykular 2 cocuk x 2 cagri x 0.3 = 1.2 sn + ebeveyn 0.6 = en az 1.8 sn;
    # paralel: ~0.6 + 0.6 + sabit ek yuk (yavas makinede ~0.45 sn). 1.8 alti = cakisma kaniti.
    assert sure < 1.8, f"alt ajanlar paralel kosmadi ({sure:.2f} sn)"


def test_proje_modeli_lider_koordinator_alt_ajan_uygulayici(tmp_path) -> None:
    """model_sabit: lider kendi (koordinator) modeliyle, alt ajan projenin uygulayici modeliyle."""
    proje = tmp_path / "proje"
    proje.mkdir()
    model = SahteModel([
        cagri("alt_ajan", gorev="listele", araclar=["proje_listele"], max_adim=8),
        cagri("proje_listele"),
        cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[1]),
        cagri("proje_listele"),
        cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[2]),
    ])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)
    istenen: list = []

    @asynccontextmanager
    async def llm(m=None):
        istenen.append(m)
        yield model

    runner.llm = llm
    runner.uygulayici_model = lambda _="": "kucuk/model"

    async def calistir():
        run = await runner.baslat("x", model="buyuk/model", model_sabit=True)
        return await bitir(runner, run.id)

    run = asyncio.run(calistir())
    cocuk = depo.getir(run.cocuklar[0])
    assert (cocuk.model, cocuk.model_sabit) == ("kucuk/model", True)
    assert istenen[0] == "buyuk/model" and "kucuk/model" in istenen and None not in istenen


def test_ayni_adli_arac_modele_bir_kez_gider() -> None:
    """Gemini ayni adli iki arac tanimini 400 ile reddediyor (canli bulgu)."""
    from app.agent.runner import _tekil

    def s(ad: str, d: str = "") -> dict:
        return {"type": "function", "function": {"name": ad, "description": d}}

    sonuc = _tekil([s("a", "ilk"), s("b"), s("a", "ikinci")])
    assert [x["function"]["name"] for x in sonuc] == ["a", "b"]
    assert sonuc[0]["function"]["description"] == "ilk"


def test_alt_ajan_ebeveynin_izole_kokunu_ve_dalini_alir(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    model = AracGozleyen([
        cagri("alt_ajan", gorev="bak", araclar=["proje_dosya_oku"], max_adim=8),
        cagri("gorevi_bitir", ozet="yok", kanit_adimlari=[]),
        cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[]),
    ])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)

    async def calistir():
        run = await runner.baslat("izole is", izole_kur=lambda _id: (str(proje), "ajan/x"))
        return await bitir(runner, run.id)

    run = asyncio.run(calistir())
    cocuk = depo.getir(run.cocuklar[0])
    assert (cocuk.calisma_koku, cocuk.dal) == (str(proje), "ajan/x")


def test_calisan_goreve_gelen_mesaj_kaybolmaz(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "a.txt").write_bytes(b"x\n")
    gorulen: list = []
    runner_ref: list = []

    def ilk(_m):
        r = runner_ref[0]
        run_id = next(iter(r._gorevler))
        asyncio.get_running_loop().create_task(r.mesaj(run_id, "YONLENDIRME-42"))
        return cagri("proje_dosya_oku", yol="a.txt")

    def ikinci(m):
        gorulen.extend(m)
        return cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[1])

    model = AracGozleyen([ilk, ikinci])
    runner, *_ = kur(tmp_path, proje, model)
    runner_ref.append(runner)
    asyncio.run(_calistir(runner, "oku"))
    assert any("YONLENDIRME-42" in str(x.get("content")) for x in gorulen)

def test_model_router_rapor_yazimini_uygulayiciya_devreder(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    model = AracGozleyen([
        cagri("proje_dosya_yaz", yol="yanlis.md", icerik="lider yazamaz"),
        cagri("alt_ajan", gorev="Markdown raporunu yaz ve oku",
              araclar=["proje_dosya_yaz", "proje_dosya_oku"], dosyalar=["inceleme.md"]),
        cagri("proje_dosya_yaz", yol="inceleme.md", icerik="# Inceleme\n\n## Bulgular"),
        cagri("proje_dosya_oku", yol="inceleme.md"),
        cagri("gorevi_bitir", ozet="inceleme.md yazildi", kanit_adimlari=[2]),
        cagri("proje_dosya_oku", yol="inceleme.md"),
        cagri("gorevi_bitir", ozet="inceleme.md\n" + "x" * 2500, kanit_adimlari=[3]),
    ])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)
    istenen = []

    @asynccontextmanager
    async def llm(m=None):
        istenen.append(m)
        yield model

    runner.llm = llm
    runner.uygulayici_model = lambda _="": "baska/model"

    async def calistir():
        run = await runner.baslat(
            "Detayli inceleme raporu yaz", model="qwen/model", model_sabit=True,
            model_rol="koordinator", uygulayici_model="deepseek/model",
        )
        return await bitir(runner, run.id)

    run = asyncio.run(calistir())
    assert run.durum is RunDurum.basarili, run.hata
    assert "proje_dosya_yaz" not in model.araclar[0]
    assert "proje_dosya_yaz" in model.araclar[2]
    assert not (proje / "yanlis.md").exists()
    assert (proje / "inceleme.md").read_text() == "# Inceleme\n\n## Bulgular"
    assert depo.getir(run.cocuklar[0]).model == run.adimlar[1].devredilen_model == "deepseek/model"
    assert istenen == ["qwen/model"] * 2 + ["deepseek/model"] * 3 + ["qwen/model"] * 2
    assert run.sonuc.ozet.endswith("x" * 2500)

def test_profile_model_effort_and_permissions(tmp_path) -> None:
    from app.services.cc_plugin import ajan_profili

    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "a.txt").write_text("x")
    tanim = tmp_path / "review.md"
    tanim.write_text(
        "---\nname: review\nmodel: test/reviewer\neffort: high\npermissionMode: plan\n"
        "isolation: worktree\nskills: [review-skill]\nmcpServers: [docs]\n"
        "tools: [Read, Write, Bash]\ndisallowedTools: [Bash]\n---\nReview only.\n"
    )
    profil = ajan_profili(tanim)
    model = AracGozleyen([
        cagri("alt_ajan", gorev="incele", profil="review",
              araclar=["proje_dosya_oku", "proje_dosya_yaz", "komut_calistir"]),
        cagri("proje_dosya_oku", yol="a.txt"),
        cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[1]),
        cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[1]),
    ])  # fmt: skip
    runner, depo, *_ = kur(tmp_path, proje, model)
    runner.ajan_profilleri = lambda _: {"review": profil}
    runner.alt_worktree_kur = lambda _run, _id: (str(proje), "alt-ajan/ornek")
    modeller = []

    @asynccontextmanager
    async def llm(ad=None):
        modeller.append(ad)
        yield model

    runner.llm = llm
    eski_sohbet = model.sohbet
    effort = []

    async def sohbet(mesajlar, **kwargs):
        effort.append(kwargs.get("dusunme"))
        return await eski_sohbet(mesajlar, **kwargs)

    model.sohbet = sohbet
    run = asyncio.run(_calistir(runner, "incele"))
    alt = depo.getir(run.cocuklar[0])
    assert alt.bagimsiz_worktree and alt.dal == "alt-ajan/ornek"
    assert alt.profil_skilleri == ["review-skill"] and alt.profil_mcp == ["docs"]
    assert "proje_dosya_oku" in model.araclar[1]
    assert not model.araclar[1] & {"proje_dosya_yaz", "komut_calistir"}
    assert modeller == [None, "test/reviewer", "test/reviewer", None]
    assert effort == [None, "derin", "derin", None]
