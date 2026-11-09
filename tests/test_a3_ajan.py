"""A3 kabul: kalici ajan dongusu. Senaryolu sahte model + GERCEK arac kaydi (gecici proje)."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from conftest import IzoleSahte

from app.agent.araclar import AjanAracKaydi
from app.agent.checkpoints import CheckpointDeposu, dosya_hashi
from app.agent.policy import PolitikaMotoru
from app.agent.runner import (
    Adim,
    AdimDurum,
    AgentRunner,
    Butce,
    Run,
    RunDeposu,
    RunDurum,
    _json_onar,
)
from app.agent.terminal import KomutServisi
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.exceptions import UygulamaHatasi
from app.services.yerel_llm import ModelCevapHatasi, SunucuKapali


def cagri(ad: str, **arg) -> dict:
    return {
        "content": "",
        "tool_calls": [
            {
                "id": uuid.uuid4().hex[:8],
                "type": "function",
                "function": {"name": ad, "arguments": json.dumps(arg)},
            }
        ],
    }


def ham_cagri(ad: str, ham_arguman: str) -> dict:
    fonk = {"name": ad, "arguments": ham_arguman}
    return {"content": "", "tool_calls": [{"id": uuid.uuid4().hex[:8], "function": fonk}]}


def cokmus_run(depo: RunDeposu, yol: str, icerik: str) -> Run:
    """Cokmus calismayi taklit eder: yan etki NIYET kaydi diskte, sonucu yok."""
    run = Run(hedef="dosya yaz", durum=RunDurum.calisiyor)
    run.mesajlar = [{"role": "user", "content": "GOREV"}, {**ham_cagri("proje_dosya_yaz", "{}")}]
    run.mesajlar[1]["role"] = "assistant"
    run.mesajlar[1]["tool_calls"][0]["id"] = "c1"
    run.adimlar = [
        Adim(
            no=1,
            arac="proje_dosya_yaz",
            argumanlar={"yol": yol, "icerik": icerik},
            cagri_id="c1",
            durum=AdimDurum.niyet,
            yan_etkili=True,
        )
    ]
    return depo.kaydet(run)


class SahteModel:
    """Senaryo: her eleman bir mesaj sozlugu, ya da mesajlari alip mesaj donduren fonksiyon,
    ya da firlatilacak istisna. Senaryo bitince arac kullanmayan metin doner."""

    def __init__(self, senaryo: list) -> None:
        self.senaryo = list(senaryo)
        self.gorulen: list[list[dict]] = []

    async def sohbet(self, mesajlar, **_):
        self.gorulen.append(mesajlar)
        adim = self.senaryo.pop(0) if self.senaryo else {"content": "bitti sanirim"}
        if isinstance(adim, Exception):
            raise adim
        if callable(adim):
            adim = adim(mesajlar)
        return {"message": adim, "finish_reason": "stop"}


@pytest.fixture
def proje(tmp_path: Path) -> Path:
    p = tmp_path / "ornek proje"
    (p / "src").mkdir(parents=True)
    (p / "tests").mkdir()
    (p / "src" / "hesap.py").write_bytes(b"def topla(a, b):\n    return a - b  # hatali\n")
    (p / "tests" / "test_hesap.py").write_bytes(
        b"import sys\nsys.path.insert(0, 'src')\nfrom hesap import topla\n\n"
        b"def test_topla():\n    assert topla(2, 3) == 5\n"
    )
    return p


def kur(tmp_path: Path, proje: Path, model: SahteModel, mod: Mod = Mod.otomatik, **runner_kw):
    veri = tmp_path / "veri"
    veri.mkdir(exist_ok=True)
    alan = CalismaAlani(id="a" * 12, kokler=[str(proje)], guven=Guven.guvenilir, mod=mod)
    politika = PolitikaMotoru(veri, izolasyon=IzoleSahte)
    kayit = AjanAracKaydi(alan, politika, CheckpointDeposu(veri), KomutServisi())
    sayac: dict[str, int] = {}

    def sayan(ad, fonk):
        def f(**kw):
            sayac[ad] = sayac.get(ad, 0) + 1
            return fonk(**kw)

        return f

    def baglam(_hedef):
        isl = {ad: sayan(ad, f) for ad, f in kayit.isleyiciler().items()}
        return "", kayit.semalar(), isl

    @asynccontextmanager
    async def llm():
        yield model

    def onay_durumu(onay_id):
        return next(
            (o["karar"] for o in politika.onaylar.gecmis(500) if o["id"] == onay_id), "bekliyor"
        )

    depo = RunDeposu(veri)
    runner = AgentRunner(depo, baglam, llm, onay_durumu, bekleme=(0.01,), **runner_kw)
    return runner, depo, politika, sayac


async def bitir(runner: AgentRunner, run_id: str) -> Run:
    await asyncio.wait_for(runner._gorevler[run_id], 60)
    return runner.depo.getir(run_id)


PYTEST = f'"{sys.executable}" -m pytest -q tests'


def _hash_ile_yama(proje: Path):
    def f(_m):
        h = dosya_hashi(proje / "src" / "hesap.py")
        return cagri(
            "proje_dosya_yama",
            yol="src/hesap.py",
            eski_metin="a - b  # hatali",
            yeni_metin="a + b",
            beklenen_hash=h,
        )

    return f


# --------------------------------------------------- 10+ adim, test hatasi ve duzeltme


async def test_on_adimli_gorev_test_hatasi_duzeltme_ve_kanit(tmp_path, proje) -> None:
    model = SahteModel(
        [
            cagri("plan_guncelle", adimlar=[{"baslik": "Hatayi bul"}, {"baslik": "Duzelt"}]),
            cagri("proje_listele"),
            cagri("proje_glob", desen="**/*.py"),
            cagri("proje_ara", desen="def topla"),
            cagri("proje_dosya_oku", yol="src/hesap.py"),
            cagri("komut_calistir", komut=PYTEST, timeout=120),  # 6: KIRMIZI
            cagri("proje_dosya_oku", yol="tests/test_hesap.py"),
            _hash_ile_yama(proje),
            cagri("gorevi_bitir", ozet="erken", kanit_adimlari=[6]),  # 9: reddedilmeli
            cagri("komut_calistir", komut=PYTEST, timeout=120),  # 10: YESIL
            cagri("git_durum"),
            cagri("plan_guncelle", adimlar=[{"baslik": "Duzelt", "durum": "tamam"}]),
            cagri("gorevi_bitir", ozet="topla duzeltildi, test gecti", kanit_adimlari=[10, 99]),
        ]
    )
    runner, _, _, _ = kur(tmp_path, proje, model)
    run = await runner.baslat("topla fonksiyonunu duzelt", ["pytest gecsin"])
    run = await bitir(runner, run.id)

    assert run.durum is RunDurum.basarili, (run.hata, [a.sonuc[:80] for a in run.adimlar])
    assert run.sonuc.kanit == [10] and run.sonuc.dogrulandi  # 99 yok sayildi
    assert len(run.adimlar) == 13 and run.kullanim.adim == 13
    assert run.adimlar[8].durum is AdimDurum.hata and "gecersiz" in run.adimlar[8].sonuc
    assert json.loads(run.adimlar[5].sonuc)["cikis_kodu"] != 0
    assert "a + b" in (proje / "src" / "hesap.py").read_text(encoding="utf-8")
    assert [p.baslik for p in run.plan] == ["Duzelt"]
    # gizli dusunce zinciri yok; arac sonuclari modele tool mesaji olarak gitti
    assert all(m["role"] != "tool" or m["tool_call_id"] for m in run.mesajlar)


async def test_kanitsiz_bitis_dogrulanmadi(tmp_path, proje) -> None:
    model = SahteModel([cagri("gorevi_bitir", ozet="yaptim", kanit_adimlari=[])])
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.durum is RunDurum.dogrulanmadi and not run.sonuc.dogrulandi


# --------------------------------------------------- izin reddi ve onay


async def test_onay_reddi_yeni_plan_ister_ve_tekrarlamaz(tmp_path, proje) -> None:
    yaz = cagri("proje_dosya_yaz", yol="yeni.txt", icerik="x")
    model = SahteModel([yaz, cagri("gorevi_bitir", ozet="yazamadim", kanit_adimlari=[])])
    runner, depo, politika, sayac = kur(tmp_path, proje, model, mod=Mod.onayli)
    run = await bitir(runner, (await runner.baslat("dosya yaz")).id)
    assert run.durum is RunDurum.onay_bekliyor
    adim = run.adimlar[0]
    assert adim.durum is AdimDurum.onay_bekliyor and adim.onay_id

    politika.onaylar.karar_ver(adim.onay_id, False)
    await runner.devam(run.id)
    run = await bitir(runner, run.id)
    assert run.adimlar[0].durum is AdimDurum.reddedildi
    assert not (proje / "yeni.txt").exists()
    son_tool = [m for m in model.gorulen[-1] if m["role"] == "tool"][-1]
    assert "REDDETTI" in son_tool["content"]
    assert sayac.get("proje_dosya_yaz") == 1  # onay istemek icin bir kez; tekrar YOK
    assert run.durum is RunDurum.dogrulanmadi


async def test_onay_verilince_ayni_adim_calisir(tmp_path, proje) -> None:
    model = SahteModel(
        [
            cagri("proje_dosya_yaz", yol="yeni.txt", icerik="merhaba"),
            cagri("proje_dosya_oku", yol="yeni.txt"),
            cagri("gorevi_bitir", ozet="yazildi", kanit_adimlari=[2]),
        ]
    )
    runner, _, politika, _ = kur(tmp_path, proje, model, mod=Mod.onayli)
    run = await bitir(runner, (await runner.baslat("dosya yaz")).id)
    politika.onaylar.karar_ver(run.adimlar[0].onay_id, True)
    await runner.devam(run.id)
    run = await bitir(runner, run.id)
    assert run.durum is RunDurum.basarili
    assert (proje / "yeni.txt").read_text(encoding="utf-8") == "merhaba"


async def test_izolasyonsuz_otomatikte_komut_onay_bekler(tmp_path, proje) -> None:
    model = SahteModel([cagri("komut_calistir", komut="echo x")])
    runner, *_ = kur(tmp_path, proje, model)
    veri = tmp_path / "v-iz"  # GERCEK politika: varsayilan izolasyon "yok"
    veri.mkdir()
    alan = CalismaAlani(id="b" * 12, kokler=[str(proje)], guven=Guven.guvenilir, mod=Mod.otomatik)
    kayit = AjanAracKaydi(alan, PolitikaMotoru(veri), CheckpointDeposu(veri), KomutServisi())
    runner.araclar = lambda _h: ("", kayit.semalar(), kayit.isleyiciler())
    run = await bitir(runner, (await runner.baslat("komut")).id)
    assert run.durum is RunDurum.onay_bekliyor


# --------------------------------------------------- model kesintisi


async def test_gecici_model_kesintisi_tekrar_denenir(tmp_path, proje) -> None:
    model = SahteModel(
        [
            SunucuKapali(),
            cagri("proje_listele"),
            cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[1]),
        ]
    )
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("listele")).id)
    assert run.durum is RunDurum.basarili
    assert any("yeniden deneniyor" in g for g in run.guncellemeler)


async def test_kalici_model_hatasi_basarisiz(tmp_path, proje) -> None:
    model = SahteModel([ModelCevapHatasi("bozuk istek")])
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.durum is RunDurum.basarisiz and "bozuk istek" in run.hata


async def test_surekli_kesinti_sinirli_deneme(tmp_path, proje) -> None:
    model = SahteModel([SunucuKapali()] * 5)
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.durum is RunDurum.basarisiz and len(model.gorulen) == 3  # 1 + 2 tekrar


# --------------------------------------------------- cokme, yeniden acma, yinelenmeyen yan etki


async def test_cokme_sonrasi_belirsiz_adim_tekrarlanmaz(tmp_path, proje) -> None:
    model = SahteModel(
        [
            cagri("proje_dosya_oku", yol="a.txt"),
            cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[2]),
        ]
    )
    runner, depo, _, sayac = kur(tmp_path, proje, model)
    run = cokmus_run(depo, "a.txt", "x")
    (proje / "a.txt").write_text("x", encoding="utf-8")  # cokmeden once gercekten yazilmisti
    assert depo.kurtar() == [run.id]  # uygulama yeniden acildi
    run = depo.getir(run.id)
    assert run.durum is RunDurum.karar_bekliyor
    assert run.adimlar[0].durum is AdimDurum.belirsiz
    with pytest.raises(UygulamaHatasi, match="belirsiz"):
        await runner.devam(run.id)

    await runner.karar(run.id, 1, "tamamlandi")  # kullanici: dosya zaten yazilmis
    run = await runner.devam(run.id)
    run = await bitir(runner, run.id)
    assert sayac.get("proje_dosya_yaz") is None  # yan etki YINELENMEDI
    assert run.durum is RunDurum.basarili


async def test_belirsiz_adim_kullanici_isterse_tekrarlanir(tmp_path, proje) -> None:
    model = SahteModel(
        [
            cagri("proje_dosya_oku", yol="b.txt"),
            cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[2]),
        ]
    )
    runner, depo, _, sayac = kur(tmp_path, proje, model)
    run = cokmus_run(depo, "b.txt", "y")
    depo.kurtar()
    await runner.karar(run.id, 1, "tekrarla")
    await runner.devam(run.id)
    run = await bitir(runner, run.id)
    assert sayac["proje_dosya_yaz"] == 1 and (proje / "b.txt").exists()
    assert run.durum is RunDurum.basarili


# --------------------------------------------------- butce, tekrar eden hata, ilerlemesizlik


async def test_adim_butcesi(tmp_path, proje) -> None:
    model = SahteModel([cagri("proje_listele") for _ in range(10)])
    runner, *_ = kur(tmp_path, proje, model)
    run = await runner.baslat("sonsuz", butce=Butce(max_adim=3))
    run = await bitir(runner, run.id)
    assert run.durum is RunDurum.basarisiz and "Adim butcesi" in run.hata
    assert run.kullanim.adim == 3


async def test_ayni_basarisiz_cagri_tekrar_calistirilmaz(tmp_path, proje) -> None:
    kotu = lambda _m: cagri("proje_dosya_oku", yol="yok.txt")  # noqa: E731
    model = SahteModel([kotu, kotu, kotu])
    runner, _, _, sayac = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("oku")).id)
    assert sayac["proje_dosya_oku"] == 2  # ucuncude calistirilmadi
    assert "CALISTIRILMADI" in run.adimlar[2].sonuc


async def test_ilerlemesizlik_durur(tmp_path, proje) -> None:
    model = SahteModel([{"content": "dusunuyorum"}] * 5)
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.durum is RunDurum.dogrulanmadi and "Ilerleme yok" in run.hata
    assert len(model.gorulen) == 3


async def test_bozuk_json_onarim(tmp_path, proje) -> None:
    assert _json_onar('```json\n{"yol": "a",}\n```') == {"yol": "a"}
    assert _json_onar("cop") is None
    model = SahteModel(
        [
            ham_cagri("proje_listele", "{bozuk"),
            ham_cagri("proje_listele", '{"yol": "src",}'),  # sondaki virgul onarilir
            cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[2]),
        ]
    )
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.adimlar[0].durum is AdimDurum.hata and "JSON" in run.adimlar[0].sonuc
    assert run.adimlar[1].durum is AdimDurum.tamam and run.durum is RunDurum.basarili


# --------------------------------------------------- yonlendirme, duraklat/devam/iptal/tekrar


async def test_kullanici_yonlendirmesi_guvenli_sinirda_islenir(tmp_path, proje) -> None:
    model = SahteModel(
        [cagri("proje_listele"), cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[1])]
    )
    runner, *_ = kur(tmp_path, proje, model)
    run = await runner.baslat("x")
    await runner.mesaj(run.id, "src klasorune odaklan")
    run = await bitir(runner, run.id)
    gorulen = json.dumps(model.gorulen[-1], ensure_ascii=False)
    assert "src klasorune odaklan" in gorulen
    assert any("Kullanici:" in g for g in run.guncellemeler)
    with pytest.raises(UygulamaHatasi, match="Biten"):
        await runner.mesaj(run.id, "gec")


class YavasModel(SahteModel):
    async def sohbet(self, mesajlar, **kw):
        await asyncio.sleep(0.2)
        return await super().sohbet(mesajlar, **kw)


async def test_duraklat_devam_iptal_tekrar(tmp_path, proje) -> None:
    model = YavasModel([cagri("proje_listele") for _ in range(50)])
    runner, *_ = kur(tmp_path, proje, model)
    run = await runner.baslat("uzun is")
    await asyncio.sleep(0.3)
    run = await runner.duraklat(run.id)
    assert run.durum is RunDurum.duraklatildi
    adim = run.kullanim.adim
    await asyncio.sleep(0.3)
    assert runner.depo.getir(run.id).kullanim.adim == adim  # duraklatilinca ilerlemedi

    await runner.devam(run.id)
    await asyncio.sleep(0.3)
    run = await runner.iptal(run.id)  # model beklenirken oncelikli iptal
    assert run.durum is RunDurum.iptal
    with pytest.raises(UygulamaHatasi):
        await runner.devam(run.id)

    model.senaryo = [cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[1])]
    run = await runner.tekrar(run.id)
    assert run.deneme == 2
    run = await bitir(runner, run.id)
    assert run.durum is RunDurum.basarili


async def test_bos_hedef_ve_gecersiz_karar(tmp_path, proje) -> None:
    runner, *_ = kur(tmp_path, proje, SahteModel([]))
    with pytest.raises(UygulamaHatasi):
        await runner.baslat("  ")
    model = SahteModel(
        [cagri("proje_listele"), cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[1])]
    )
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.durum is RunDurum.basarili
    with pytest.raises(UygulamaHatasi, match="karar beklemiyor"):
        await runner.karar(run.id, 1, "tamamlandi")
    with pytest.raises(UygulamaHatasi, match="tekrarlanir"):
        await runner.tekrar(run.id)  # basarili gorev tekrarlanmaz
    with pytest.raises(UygulamaHatasi, match="Biten"):
        await runner.devam(run.id)


# --------------------------------------------------- API


async def test_api_proje_yokken_gorev_baslamaz(istemci) -> None:
    r = await istemci.post("/api/gorevler", json={"hedef": "x"})
    assert r.status_code >= 400 and "proje" in r.json()["hata"]
    assert (await istemci.get("/api/gorevler")).json() == {"gorevler": []}
    r = await istemci.post("/api/gorevler/" + "0" * 12 + "/bilinmeyen")
    assert r.status_code == 400 and "duraklat" in r.json()["hata"]
    assert (await istemci.get("/api/gorevler/" + "0" * 12)).status_code == 404
    assert (
        await istemci.get("/api/gorevler/x..y")
    ).status_code == 404  # gecersiz id: dosya yolu kurulmaz


async def test_istek_siniri_429_gecici_sayilir(tmp_path, proje) -> None:
    from app.services.openrouter import OpenRouterLLM

    with pytest.raises(Exception) as bilgi:
        OpenRouterLLM._hata_firlat(429, "rate limited")
    assert bilgi.value.gecici
    with pytest.raises(Exception) as bilgi:
        OpenRouterLLM._hata_firlat(401, "")
    assert not bilgi.value.gecici
    model = SahteModel(
        [
            bilgi.type("sinir", gecici=True),
            cagri("proje_listele"),
            cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[1]),
        ]
    )
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.durum is RunDurum.basarili and len(model.gorulen) == 3


async def test_degisiklik_oncesi_kanit_gecersiz(tmp_path, proje) -> None:
    """Canli denemede model degisiklik ONCESI bir listeleme adimini kanit gosterdi."""
    model = SahteModel(
        [
            cagri("proje_listele"),  # 1: degisiklik oncesi
            cagri("proje_dosya_yaz", yol="yeni.txt", icerik="x"),  # 2
            cagri("gorevi_bitir", ozet="yaptim", kanit_adimlari=[1]),  # 3: reddedilir
            cagri("proje_dosya_oku", yol="yeni.txt"),  # 4: son durumu dogrular
            cagri("gorevi_bitir", ozet="yaptim", kanit_adimlari=[4]),
        ]
    )
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.adimlar[2].durum is AdimDurum.hata and "SONRA" in run.adimlar[2].sonuc
    assert run.durum is RunDurum.basarili and run.sonuc.kanit == [4]


def test_okuma_araci_hash_verir_yama_onunla_calisir(tmp_path, proje) -> None:
    runner, *_ = kur(tmp_path, proje, SahteModel([]))
    isl = runner.araclar("")[2]
    okunan = isl["proje_dosya_oku"](yol="src/hesap.py")
    assert len(okunan["hash"]) == 32
    eksik = isl["proje_dosya_yama"](yol="src/hesap.py", eski_metin="a - b", yeni_metin="a + b")
    assert "proje_dosya_oku" in eksik["hata"]  # model ne yapacagini anlar
    s = isl["proje_dosya_yama"](
        yol="src/hesap.py", eski_metin="a - b", yeni_metin="a + b", beklenen_hash=okunan["hash"]
    )
    assert "hata" not in s


async def test_model_adim_numarasini_gorur_ve_uzun_basarisiz_cikti_kanit_olamaz(
    tmp_path, proje
) -> None:
    uzun = "import sys; print('x' * 5000); sys.exit(1)"
    model = SahteModel(
        [
            cagri("komut_calistir", komut=f'"{sys.executable}" -c "{uzun}"'),
            cagri("gorevi_bitir", ozet="gecti", kanit_adimlari=[1]),
        ]
    )
    runner, *_ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("x")).id)
    tool = next(m for m in model.gorulen[-1] if m["role"] == "tool")
    assert json.loads(tool["content"])["adim"] == 1
    assert run.adimlar[0].cikis_kodu == 1
    assert run.adimlar[1].durum is AdimDurum.hata  # kirpilmis cikti "basarili" sayilmadi
