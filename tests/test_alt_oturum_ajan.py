"""Alt oturum onerisi (kullanici onayiyla acilir), sohbetten ajan olusturma ve sinirsiz adim."""

from app.agent.runner import AgentRunner, Butce, Kullanim, Run
from app.services.sohbet_araclari import alt_oturum_isleyici


async def test_alt_oturum_onay_ve_ret(istemci):
    ust = (await istemci.post("/api/oturumlar")).json()["id"]
    alt = (
        await istemci.post(
            f"/api/oturumlar/{ust}/alt", json={"baslik": "Testleri yaz", "kaynak": "c1"}
        )
    ).json()
    assert alt["ust"] == ust and alt["baslik"] == "Testleri yaz"
    o = (await istemci.get(f"/api/oturumlar/{ust}")).json()
    assert o["oneri_kararlari"] == {"c1": alt["id"]}
    r = (await istemci.post(f"/api/oturumlar/{ust}/oneri-reddet", json={"kaynak": "c2"})).json()
    assert r["oneri_kararlari"]["c2"] == "reddedildi"
    # listede alt oturumun ana oturumu gorunur (arayuz altina girintiler)
    liste = (await istemci.get("/api/oturumlar")).json()
    assert {x["id"]: x["ust"] for x in liste}[alt["id"]] == ust
    # olmayan ana oturuma alt oturum acilamaz
    assert (
        await istemci.post("/api/oturumlar/abcdef123456/alt", json={"baslik": "x"})
    ).status_code == 404


def test_alt_oturum_isleyici_yalniz_oneri():
    assert "hata" in alt_oturum_isleyici(baslik="", gorev="x")
    s = alt_oturum_isleyici(baslik=" Rapor ", gorev="Raporu yaz")
    assert s["oneri"] == {"baslik": "Rapor", "gorev": "Raporu yaz"}


async def test_sohbetten_ajan_olustur_onayli_modda_sorar(app):
    sohbet = app.state.sohbet
    _, araclar, isl, _ = sohbet.baglam_hazirla(app.state.yonetici.ayarlar.oku(), "", [])
    adlar = {a["function"]["name"] for a in araclar}
    assert {"alt_oturum_oner", "ajan_olustur"} <= adlar
    arg = {
        "ad": "Arastirmaci",
        "avatar": "🔎",
        "aciklama": "Web'de arar",
        "talimat": "Kaynakli yaz.",
    }
    s = isl["ajan_olustur"](**arg)
    assert s.get("karar") == "onay_bekliyor"  # varsayilan onayli mod: yan etki sorulur
    assert app.state.ajan_deposu.liste() == []
    app.state.politika.tam_yetki = lambda: True  # tam yetkide sormadan olusur
    s = isl["ajan_olustur"](**arg)
    assert s["olusturuldu"]["ad"] == "Arastirmaci"
    a = app.state.ajan_deposu.getir("Arastirmaci")
    assert a.avatar == "🔎" and a.talimat == "Kaynakli yaz."


def test_adim_butcesi_varsayilan_sinirsiz():
    assert Butce().max_adim == 0
    run = Run(hedef="x", butce=Butce(max_sure_sn=10_000), kullanim=Kullanim(adim=5000))
    assert "Adim" not in AgentRunner._butce_asildi(None, run)  # type: ignore[arg-type]
    run.butce.max_adim = 3
    assert "Adim butcesi" in AgentRunner._butce_asildi(None, run)  # type: ignore[arg-type]


class _TekrarlayanModel:
    """Her turda ayni arac cagrisini yapar; `farkli` turdan sonra cevap yazar."""

    model, dusunme, son_zamanlama = "sahte", "kapali", {}

    def __init__(self, ayni: bool, tur_sayisi: int) -> None:
        self.ayni, self.tur_sayisi, self.tur = ayni, tur_sayisi, 0

    async def akis_olaylari(self, mesajlar, **_):
        self.tur += 1
        if self.tur > self.tur_sayisi:
            yield {"tur": "parca", "metin": "bitti"}
            return
        arg = "{}" if self.ayni else f'{{"n": {self.tur}}}'
        yield {"tur": "arac_cagrilari", "cagrilar": [
            {"id": f"c{self.tur}", "function": {"name": "say", "arguments": arg}}
        ]}  # fmt: skip


async def test_sohbet_tur_siniri_yok_ama_ayni_cagri_dongusu_durur():
    from app.services.sohbet import cevap_akit

    sema = [{"type": "function", "function": {"name": "say", "parameters": {}}}]
    olaylar: list = []
    # 30 farkli arac turu: eskiden 20'de "tur siniri" ile kesiliyordu
    s = await cevap_akit(_TekrarlayanModel(False, 30), [{"role": "user", "content": "x"}],
                         olaylar.append, araclar=sema, isleyiciler={"say": lambda **_: {"ok": 1}},
                         max_tur=0)  # fmt: skip
    assert s["durum"] == "tamam" and s["metin"] == "bitti" and len(s["araclar"]) == 30
    # ayni cagri ust uste 3 kez: dongu durur, 3. cagri calistirilmaz
    s = await cevap_akit(_TekrarlayanModel(True, 100), [{"role": "user", "content": "x"}],
                         olaylar.append, araclar=sema, isleyiciler={"say": lambda **_: {"ok": 1}},
                         max_tur=0)  # fmt: skip
    assert s["durum"] == "dongu" and [a["durum"] for a in s["araclar"]][-1] == "sonucsuz"
    assert any(o.get("kod") == "dongu" for o in olaylar)


async def test_sohbet_projeye_ozgu_ve_proje_etkinlestirme(istemci, tmp_path):
    kisisel = (await istemci.post("/api/oturumlar")).json()
    assert kisisel["alan"] == "0" * 12  # proje kapaliyken kisisel alan
    klasor = tmp_path / "proje"
    klasor.mkdir()
    p = (
        await istemci.post("/api/projeler", json={"yol": str(klasor), "guven": "guvenilir"})
    ).json()
    o = (await istemci.post("/api/oturumlar")).json()
    assert o["alan"] == p["id"]
    alt = (await istemci.post(f"/api/oturumlar/{o['id']}/alt", json={"baslik": "x"})).json()
    assert alt["alan"] == p["id"]  # alt oturum ana oturumun projesinde
    liste = {x["id"]: x["alan"] for x in (await istemci.get("/api/oturumlar")).json()}
    assert liste[o["id"]] == p["id"] and liste[kisisel["id"]] == "0" * 12
    # kisisel sohbete donunce proje kapanir; proje sohbetine donunce ayarlariyla geri gelir
    r = (await istemci.post(f"/api/projeler/{'0' * 12}/etkin")).json()
    assert r["etkin"]["id"] == "0" * 12
    r = (await istemci.post(f"/api/projeler/{p['id']}/etkin")).json()
    assert r["etkin"]["id"] == p["id"] and r["etkin"]["guven"] == "guvenilir"  # guven sifirlanmaz
    assert (await istemci.post("/api/projeler/abcdef123456/etkin")).status_code == 404
