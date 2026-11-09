"""A4 kabul: baglam butcesi + ozet, model yetenegi, hafiza, oturum islemleri."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from test_a3_ajan import SahteModel, bitir, cagri, kur

from app.agent.checkpoints import dosya_hashi
from app.agent.ozet import OZET_ETIKETI, mesaj_token
from app.agent.runner import RunDurum
from app.agent.yetenek import ModelYetenegi, butce_dokumu, dogrula, uzak_yetenek, yerel_yetenek
from app.exceptions import UygulamaHatasi
from app.services.hafiza import HafizaDeposu


def yetenek(baglam: int, araclar: bool = True, dusunme: bool = True) -> ModelYetenegi:
    return ModelYetenegi(
        model="test",
        saglayici="yerel",
        araclar=araclar,
        json_cikti=True,
        goruntu=False,
        baglam=baglam,
        dusunme=dusunme,
        tokenizer="tahmin",
    )


@pytest.fixture
def proje(tmp_path: Path) -> Path:
    p = tmp_path / "proje"
    (p / "src").mkdir(parents=True)
    satirlar = "".join(f"satir {i:04d} " + "x" * 40 + "\n" for i in range(400))
    (p / "src" / "buyuk.txt").write_text(satirlar, encoding="utf-8")
    (p / "src" / "kucuk.py").write_bytes(b"A = 1\n")
    return p


def _okumalar(n: int) -> list:
    return [
        cagri("proje_dosya_oku", yol="src/buyuk.txt", baslangic_satir=1 + i * 50, satir_sayisi=50)
        for i in range(n)
    ]


# ------------------------------------------------------------ 8K / 16K / 32K


@pytest.mark.parametrize(("baglam", "okuma"), [(8192, 14), (16384, 24), (32768, 34)])
async def test_baglam_butcesi_asilmaz_ve_ozet_hedefi_korur(tmp_path, proje, baglam, okuma):
    senaryo = [
        cagri("plan_guncelle", adimlar=[{"baslik": "Dosyayi incele"}, {"baslik": "Raporla"}]),
        *_okumalar(okuma),
        cagri("proje_dosya_oku", yol="src/kucuk.py"),
        lambda m: cagri("gorevi_bitir", ozet="incelendi", kanit_adimlari=[okuma + 2]),
    ]
    model = SahteModel(senaryo)
    runner, *_ = kur(tmp_path, proje, model, yetenek=lambda: yetenek(baglam))
    run = await runner.baslat("buyuk.txt dosyasini incele ve raporla", ["rapor yazilsin"])
    await runner.mesaj(run.id, "yalniz src klasorune bak")
    run = await bitir(runner, run.id)

    assert run.durum is RunDurum.basarili, run.hata
    for gorulen in model.gorulen:  # HER istek butce icinde
        assert mesaj_token(gorulen) <= baglam
    assert run.baglam["baglam"] == baglam and run.baglam["toplam"] <= baglam
    assert set(run.baglam) >= {"sistem", "araclar", "mesajlar", "kanit", "cevap"}
    if baglam == 8192:
        assert run.ozet_sayisi >= 1
        ozet = run.mesajlar[1]["content"]
        assert ozet.startswith(OZET_ETIKETI)
        assert "buyuk.txt dosyasini incele" in ozet and "rapor yazilsin" in ozet  # hedef/kabul
        assert "yalniz src klasorune bak" in ozet  # kullanici kisiti
        assert "Dosyayi incele" in ozet and "SONRAKI EYLEM" in ozet  # plan / sonraki
        assert "ESKI olabilir" in ozet and "buyuk.txt" in ozet  # dosya/hash referansi
        arsiv = runner.depo.dizin / f"{run.id}.arsiv.jsonl"
        assert arsiv.is_file() and len(arsiv.read_text(encoding="utf-8").splitlines()) > 3
        assert run.mesajlar[0]["content"].startswith("GOREV")  # gorev mesaji hep ilk


def _cift_tutarli(mesajlar: list[dict]) -> bool:
    """Her tool sonucu, ONCEKI bir assistant tool_call'ina ait olmali (protokol bozulmaz)."""
    gorulen: set[str] = set()
    for m in mesajlar:
        if m.get("role") == "assistant":
            gorulen |= {c["id"] for c in m.get("tool_calls") or []}
        if m.get("role") == "tool" and m["tool_call_id"] not in gorulen:
            return False
    return True


async def test_ozet_tool_cagri_ciftini_bolmez(tmp_path, proje) -> None:
    model = SahteModel([*_okumalar(16), cagri("gorevi_bitir", ozet="x", kanit_adimlari=[])])
    runner, *_ = kur(tmp_path, proje, model, yetenek=lambda: yetenek(8192))
    run = await bitir(runner, (await runner.baslat("incele")).id)
    assert run.ozet_sayisi >= 1
    assert all(_cift_tutarli(g[1:]) for g in model.gorulen)


async def test_ozetten_sonra_eski_hash_yeniden_dogrulanir(tmp_path, proje) -> None:
    """Ozetteki hash referansi ESKI olabilir: dosya degistiyse yazma reddedilir, okununca gecer."""
    yol = proje / "src" / "kucuk.py"
    eski = dosya_hashi(yol)

    def kullanici_degistirdi(_m):
        yol.write_bytes(b"A = 2  # kullanici\n")
        return cagri("proje_dosya_yama", yol="src/kucuk.py", eski_metin="A = 2",
                     yeni_metin="A = 3", beklenen_hash=eski)  # fmt: skip

    model = SahteModel(
        [
            cagri("proje_dosya_oku", yol="src/kucuk.py"),
            *_okumalar(14),
            kullanici_degistirdi,  # ozet sonrasi eski hash ile yazma -> RED
            cagri("proje_dosya_oku", yol="src/kucuk.py"),
            lambda m: cagri(
                "proje_dosya_yama",
                yol="src/kucuk.py",
                eski_metin="A = 2",
                yeni_metin="A = 3",
                beklenen_hash=dosya_hashi(yol),
            ),  # fmt: skip
            cagri("proje_dosya_oku", yol="src/kucuk.py"),
            lambda m: cagri("gorevi_bitir", ozet="ok", kanit_adimlari=[19]),
        ]
    )
    runner, *_ = kur(tmp_path, proje, model, yetenek=lambda: yetenek(8192))
    run = await bitir(runner, (await runner.baslat("A'yi 3 yap")).id)
    assert run.ozet_sayisi >= 1
    red = run.adimlar[15]
    assert red.arac == "proje_dosya_yama" and "degisti" in red.sonuc
    assert "kullanici" in yol.read_text(encoding="utf-8") and "A = 3" in yol.read_text("utf-8")
    assert run.durum is RunDurum.basarili


async def test_baglam_talimata_bile_yetmiyorsa_istek_gitmez(tmp_path, proje) -> None:
    model = SahteModel([cagri("proje_listele")])
    runner, *_ = kur(tmp_path, proje, model, yetenek=lambda: yetenek(1500))
    run = await bitir(runner, (await runner.baslat("x")).id)
    assert run.durum is RunDurum.basarisiz and "Baglam" in run.hata
    assert model.gorulen == []  # korlemesine istek gonderilmedi


# ------------------------------------------------------------ model yetenegi


async def test_aracsiz_model_ile_gorev_baslamaz(tmp_path, proje) -> None:
    runner, *_ = kur(tmp_path, proje, SahteModel([]), yetenek=lambda: yetenek(8192, araclar=False))
    with pytest.raises(UygulamaHatasi, match="arac cagirmayi desteklemiyor"):
        await runner.baslat("x")


def test_desteklenmeyen_dusunme_acik_hata() -> None:
    y = yetenek(8192, dusunme=False)
    dogrula(y, dusunme="kapali")
    with pytest.raises(UygulamaHatasi, match="dusunme"):
        dogrula(y, dusunme="derin")


def test_yetenek_profilleri_ve_model_degisimi(tmp_path) -> None:
    y = yerel_yetenek("gemma4-e4b-heretic", 16384)
    assert y.saglayici == "yerel" and y.araclar and y.baglam == 16384 and y.tokenizer == "sunucu"
    liste = tmp_path / "or.json"
    liste.write_text(
        json.dumps({"modeller": [{"id": "a/b:free", "araclar": True, "baglam": 32768}]}),
        encoding="utf-8",
    )
    u = uzak_yetenek("a/b:free", liste)
    assert u.araclar and u.baglam == 32768 and u.tokenizer == "tahmin"
    bilinmeyen = uzak_yetenek("yok/yok", liste)
    assert not bilinmeyen.araclar and bilinmeyen.baglam == 8192 and bilinmeyen.not_
    assert not uzak_yetenek("x", tmp_path / "yok.json").araclar  # liste yok: temkinli


def test_butce_dokumu_ayri_kalemler() -> None:
    d = butce_dokumu(
        "sistem metni",
        [{"type": "function"}],
        [{"role": "user", "content": "a"}, {"role": "tool", "content": "b" * 300}],
        1024,
        8192,
    )
    assert d["kanit"] > d["mesajlar"] > 0 and d["cevap"] == 1024
    assert d["toplam"] == sum(d[k] for k in ("sistem", "araclar", "mesajlar", "kanit", "cevap"))


# ------------------------------------------------------------ uzak servis / fallback


async def test_yerel_saglayicida_uzaga_istek_gitmez(istemci, app) -> None:
    """Yerelden buluta sessiz aktarim yok: yerel secimde OpenRouter'a tek istek gitmez."""
    giden: list[str] = []
    gercek = httpx.AsyncClient.send

    async def izle(self, request, **kw):
        giden.append(str(request.url))
        return await gercek(self, request, **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx.AsyncClient, "send", izle)
        y = (await istemci.get("/api/model/yetenek")).json()
        o = (await istemci.post("/api/oturumlar")).json()["id"]
        await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "merhaba"})
    assert y["saglayici"] == "yerel"
    assert not [u for u in giden if "openrouter.ai" in u]


# ------------------------------------------------------------ hafiza


def test_hafiza_kayit_kapsam_gecerlilik_ve_sir(tmp_path) -> None:
    h = HafizaDeposu(tmp_path)
    a = h.ekle("Testler pytest -q ile calisir", kapsam="p1", guven="yuksek")
    h.ekle("Yanitlar Turkce olsun")
    h.ekle("Eski bilgi", gecerlilik="2000-01-01")
    with pytest.raises(UygulamaHatasi, match="gizli"):
        h.ekle("api_key=sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789")
    with pytest.raises(UygulamaHatasi, match="zaten"):
        h.ekle("Yanitlar Turkce olsun")
    metin = h.sistem_metni("p1")
    assert "pytest -q" in metin and "Turkce" in metin and "Eski bilgi" not in metin
    assert "pytest" not in h.sistem_metni("baska-proje")  # proje kapsami
    assert a["kaynak"] == "kullanici" and a["tarih"]
    h.guncelle(a["id"], {"aktif": False})
    assert "pytest" not in h.sistem_metni("p1")
    with pytest.raises(UygulamaHatasi, match="gizli"):
        h.guncelle(a["id"], {"metin": "password=gizli123456"})
    assert len(h.disa_aktar()["kayitlar"]) == 3
    h.sil(a["id"])
    assert len(h.liste()) == 2


async def test_hafiza_ajan_sistemine_girer(tmp_path, proje) -> None:
    model = SahteModel([cagri("gorevi_bitir", ozet="x", kanit_adimlari=[])])
    runner, *_ = kur(tmp_path, proje, model, hafiza=lambda: "HAFIZA:\n- testler pytest ile")
    await bitir(runner, (await runner.baslat("x")).id)
    assert "testler pytest ile" in model.gorulen[0][0]["content"]


async def test_hafiza_api_ve_temizle_hafizayi_silmez(istemci) -> None:
    r = await istemci.post("/api/hafiza", json={"metin": "Proje Python 3.12"})
    kayit = r.json()
    assert r.status_code == 200 and kayit["kaynak"] == "kullanici"
    o = (await istemci.post("/api/oturumlar")).json()["id"]
    await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "selam"})
    k = (await istemci.post(f"/api/oturumlar/{o}/catal")).json()
    assert k["id"] != o and len(k["mesajlar"]) == 2 and "(kopya)" in k["baslik"]
    t = (await istemci.post(f"/api/oturumlar/{o}/temizle")).json()
    assert t["mesajlar"] == []
    assert len((await istemci.get(f"/api/oturumlar/{k['id']}")).json()["mesajlar"]) == 2
    assert len((await istemci.get("/api/hafiza")).json()["kayitlar"]) == 1  # clear != memory
    md = await istemci.get(f"/api/oturumlar/{k['id']}/disa-aktar?bicim=md")
    assert (
        md.status_code == 200
        and "selam" in md.text
        and "attachment" in md.headers["content-disposition"]
    )
    js = await istemci.get(f"/api/oturumlar/{k['id']}/disa-aktar")
    assert js.json()["id"] == k["id"]
    p = await istemci.patch(f"/api/hafiza/{kayit['id']}", json={"guven": "yuksek"})
    assert p.json()["guven"] == "yuksek"
    assert (await istemci.get("/api/hafiza-disa-aktar")).json()["kayitlar"]
    assert (await istemci.delete(f"/api/hafiza/{kayit['id']}")).status_code == 200
    assert (await istemci.delete(f"/api/hafiza/{kayit['id']}")).status_code == 404
