"""A8.2 takim panosu: bagimlilik, claim/lease, heartbeat, yetim gorev, mesaj tekrari."""

from __future__ import annotations

import asyncio
import json

from test_a3_ajan import SahteModel, bitir, cagri, kur

from app.agent.takim import KIRA_SN, TakimPanosu


class Saat:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_bagimlilik_claim_yetim_ve_sahiplik(tmp_path) -> None:
    saat = Saat()
    p = TakimPanosu(tmp_path, saat=saat)
    lider = p.isleyiciler("kok", "lider")
    a = p.isleyiciler("kok", "arastirmaci")
    b = p.isleyiciler("kok", "uygulayici")
    g1 = lider["takim_gorev_ekle"](baslik="arastir")["id"]
    g2 = lider["takim_gorev_ekle"](baslik="uygula", bagimli=[g1])["id"]
    assert "bagimlilik" in lider["takim_gorev_ekle"](baslik="x", bagimli=["yok"])["hata"]

    assert "bagimliliklar" in b["takim_gorev_al"](id=g2)["hata"]  # g1 bitmeden olmaz
    assert a["takim_gorev_al"](id=g1) == {"alindi": g1}
    assert "alindi" in b["takim_gorev_al"](id=g1)["hata"]  # cifte claim yok
    assert "kendi" in b["takim_gorev_tamamla"](id=g1)["hata"]  # baskasinin gorevini bitiremez

    saat.t += KIRA_SN + 1  # arastirmaci coktu: heartbeat yok
    assert b["takim_gorev_listesi"]()["gorevler"][0]["durum"] == "acik"  # yetim geri acildi
    assert b["takim_gorev_al"](id=g1) == {"alindi": g1}
    saat.t += KIRA_SN - 10
    b["takim_gorev_listesi"]()  # heartbeat: kiralama yenilenir
    saat.t += 20
    assert b["takim_gorev_tamamla"](id=g1, sonuc="bulundu") == {"tamam": g1}
    assert b["takim_gorev_al"](id=g2) == {"alindi": g2}


def test_mesaj_tekrari_teslim_edilmez(tmp_path) -> None:
    p = TakimPanosu(tmp_path)
    lider = p.isleyiciler("kok", "lider")
    alt = p.isleyiciler("kok", "alt1")
    assert lider["takim_mesaj_gonder"](alici="alt1", metin="testleri calistir", mesaj_id="m1")
    assert lider["takim_mesaj_gonder"](alici="alt1", metin="testleri calistir", mesaj_id="m1") == {
        "tekrar": "m1"
    }
    lider["takim_mesaj_gonder"](alici="hepsi", metin="duyuru")
    gelen = alt["takim_mesajlari_oku"]()["mesajlar"]
    assert [m["metin"] for m in gelen] == ["testleri calistir", "duyuru"]
    assert alt["takim_mesajlari_oku"]()["mesajlar"] == []  # bir kez okunur


def test_lider_ve_alt_ajan_ayni_panoyu_kullanir(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()

    def ilk_gorev(m):
        import json

        icerik = json.loads([x for x in m if x["role"] == "tool"][-1]["content"])
        return cagri("takim_gorev_al", id=icerik["gorevler"][0]["id"])

    model = SahteModel([
        cagri("takim_gorev_ekle", baslik="dosyalari listele"),
        cagri("alt_ajan", gorev="takim panosundaki gorevi yap", araclar=["proje_listele"]),
        # --- alt ajan ---
        cagri("takim_gorev_listesi"),
        ilk_gorev,
        cagri("proje_listele"),
        cagri("gorevi_bitir", ozet="listelendi", kanit_adimlari=[3]),
        # --- lider ---
        cagri("takim_gorev_listesi"),
        cagri("gorevi_bitir", ozet="takim bitti", kanit_adimlari=[]),
    ])  # fmt: skip
    runner, *_ = kur(tmp_path, proje, model)
    runner.takim = TakimPanosu(tmp_path / "takim")
    run = asyncio.run(_calistir(runner))
    pano = runner.takim.pano(run.id)
    assert pano["gorevler"][0]["sahip"] == run.cocuklar[0]  # alt ajan ayni panoda claim etti


async def _calistir(runner):
    r = await runner.baslat("takim isi")
    return await bitir(runner, r.id)


def test_adla_mesaj_ve_itmeli_teslim(tmp_path) -> None:
    p = TakimPanosu(tmp_path)
    yazar = p.isleyiciler("kok", "run-y", "Yazar")
    lider = p.isleyiciler("kok", "run-l", "lider")
    yazar["takim_mesaj_gonder"](alici="lider", metin="taslak hazir")
    lider["takim_mesaj_gonder"](alici="yazar", metin="3. bolumu kisalt")  # buyuk/kucuk farketmez
    lider["takim_mesaj_gonder"](alici="hepsi", metin="toplanti yok")
    assert p.teslim_al("kok", {"run-l", "lider"}) == [{"kimden": "Yazar", "metin": "taslak hazir"}]
    gelen = p.teslim_al("kok", {"run-y", "Yazar"})
    assert [m["metin"] for m in gelen] == ["3. bolumu kisalt", "toplanti yok"]
    assert p.teslim_al("kok", {"run-y", "Yazar"}) == []  # bir kez teslim
    assert p.teslim_al("kok", {"run-l", "lider"}) == []  # kendi 'hepsi' mesaji kendine gelmez


def test_alt_ajan_mesaji_lidere_kendiliginden_ulasir(tmp_path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    gorulen = {}

    def lider_gorur(m):
        gorulen["mesaj"] = [x["content"] for x in m if x["role"] == "user"
                            and "[Takim mesaji" in str(x["content"])]  # fmt: skip
        return cagri("gorevi_bitir", ozet="tamam", kanit_adimlari=[])

    model = SahteModel([
        _alt_ajan_cagrisi({"gorev": "taslak yaz", "araclar": ["proje_listele"], "ad": "Yazar"}),
        # --- alt ajan (Yazar) ---
        cagri("takim_mesaj_gonder", alici="lider", metin="taslak hazir, kontrol et"),
        cagri("gorevi_bitir", ozet="yazildi", kanit_adimlari=[]),
        # --- lider: okuma araci CAGIRMADAN mesaj baglaminda ---
        lider_gorur,
    ])  # fmt: skip
    runner, *_ = kur(tmp_path, proje, model)
    runner.takim = TakimPanosu(tmp_path / "takim")
    run = asyncio.run(_calistir(runner))
    assert gorulen["mesaj"] == ["[Takim mesaji - Yazar] taslak hazir, kontrol et"]
    cocuk = runner.depo.getir(run.cocuklar[0])
    assert cocuk.ad == "Yazar"


def _alt_ajan_cagrisi(arg: dict) -> dict:
    c = cagri("alt_ajan")  # yardimcinin ilk parametresi 'ad': alt_ajan'in 'ad' argumaniyla cakisir
    c["tool_calls"][0]["function"]["arguments"] = json.dumps(arg)
    return c
