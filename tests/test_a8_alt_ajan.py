"""A8.1/A8.4 alt ajan: dar arac seti, dosya sahipligi, butce kesme, derinlik, iptal, cokme."""

from __future__ import annotations

import asyncio
import json

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
    # sirali: 2 cocuk x 2 cagri x 0.3 = 1.2 sn (+ebeveyn 0.6); paralel: ~0.6 + 0.6
    assert sure < 1.6, f"alt ajanlar paralel kosmadi ({sure:.2f} sn)"
