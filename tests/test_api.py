"""API uclari: genel, ayarlar, oturumlar, ekler, sohbet akisi, test ekranlari."""

from __future__ import annotations

import io

import pytest
from conftest import olaylar

pytestmark = pytest.mark.asyncio


def png(gen: int = 40, yuk: int = 30) -> bytes:
    from PIL import Image

    t = io.BytesIO()
    Image.new("RGB", (gen, yuk), "white").save(t, "PNG")
    return t.getvalue()


async def yeni_oturum(istemci) -> str:
    return (await istemci.post("/api/oturumlar")).json()["id"]


async def test_bilgi_ve_arayuz(istemci):
    b = (await istemci.get("/api/bilgi")).json()
    assert b["urun_sahibi"] == "Umut Çelik" and "x.com/umutc6230" in b["x"]
    assert [d["deger"] for d in b["dusunme_secenekleri"]] == ["kapali", "dengeli", "derin"]
    r = await istemci.get("/")
    assert r.status_code == 200 and "Yerel AI Studio" in r.text
    js = await istemci.get("/web/app.js")
    assert js.status_code == 200 and js.headers["cache-control"] == "no-cache"  # guncel JS


async def test_durum_model_listesi(istemci, sunucu):
    d = (await istemci.get("/api/durum")).json()
    assert d["sunucu_acik"] and d["durum"] == "hazir" and d["motor_var"]
    assert {m["anahtar"] for m in d["modeller"]} == {
        "deepseek-heretic",
        "gemma4-12b-heretic",
        "gemma4-e4b-heretic",
    }
    assert all(m["dosya_var"] for m in d["modeller"])
    sunucu.saglik = False
    assert (await istemci.get("/api/durum")).json()["durum"] == "kapali"


async def test_ayarlar_oku_yaz_ve_turkce_dogrulama(istemci):
    a = (await istemci.get("/api/ayarlar")).json()
    assert a["model"] == "deepseek-heretic" and a["dusunme"] == "kapali"
    r = await istemci.put("/api/ayarlar", json={"model": "gemma4-e4b-heretic", "dusunme": "derin"})
    assert r.json()["model"] == "gemma4-e4b-heretic"
    r = await istemci.put("/api/ayarlar", json={"model": "yok"})
    assert r.status_code == 422 and r.json()["hata"] == "Bilinmeyen model: yok"
    r = await istemci.put("/api/ayarlar", json={"adres": "http://ornek.com"})
    assert r.status_code == 422 and "bu bilgisayar" in r.json()["hata"]


async def test_oturum_crud_ve_arama(istemci):
    o = await yeni_oturum(istemci)
    r = await istemci.patch(f"/api/oturumlar/{o}", json={"baslik": "Hakedis notlari"})
    assert r.json()["baslik"] == "Hakedis notlari"
    assert [x["id"] for x in (await istemci.get("/api/oturumlar?q=hakedis")).json()] == [o]
    assert (await istemci.get("/api/oturumlar?q=yokboyle")).json() == []
    assert (await istemci.delete(f"/api/oturumlar/{o}")).json() == {"silindi": o}
    r = await istemci.get(f"/api/oturumlar/{o}")
    assert r.status_code == 404 and r.json()["hata"] == "Sohbet bulunamadi."
    assert (await istemci.get("/api/oturumlar/../../x")).status_code == 404
    assert (await istemci.delete(f"/api/oturumlar/{o}")).status_code == 404


async def test_ek_yukleme(istemci):
    r = await istemci.post("/api/ekler", files={"dosya": ("a.png", png(), "image/png")})
    ek = r.json()
    assert ek["tur"] == "resim" and "metin" not in ek
    assert (await istemci.get(f"/api/ekler/{ek['id']}")).content.startswith(b"\x89PNG")
    r = await istemci.post("/api/ekler", files={"dosya": ("virus.exe", b"MZ", "x")})
    assert r.status_code == 400 and "Desteklenmeyen" in r.json()["hata"]
    r = await istemci.post("/api/ekler", files={"dosya": ("bos.txt", b"", "text/plain")})
    assert r.status_code == 400
    assert (await istemci.get("/api/ekler/123")).status_code == 404
    ornek = (await istemci.post("/api/ekler/ornek-belge")).json()
    assert ornek["tur"] == "resim" and "HAKEDİŞ" in ornek["beklenen"]


async def test_sohbet_akisi_dusunce_cevap_kayit(istemci, sunucu):
    o = await yeni_oturum(istemci)
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Merhaba nasilsin"})
    ol = olaylar(r.text)
    turler = [x["tur"] for x in ol]
    assert turler[0] == "kullanici_mesaji" and turler[-1] == "bitti"
    assert turler.index("dusunce") < turler.index("parca")  # dusunce cevaptan once akar
    son = ol[-1]["mesaj"]
    assert son["metin"] == "Merhaba, ben yerel modelim."
    assert son["dusunce"] == sunucu.dusunce
    ist = son["istatistik"]
    assert ist["uretim_tok_sn"] == 6.5 and ist["token"] == 12 and ist["dusunce_sn"] is not None
    kayit = (await istemci.get(f"/api/oturumlar/{o}")).json()
    assert kayit["baslik"] == "Merhaba nasilsin" and [m["rol"] for m in kayit["mesajlar"]] == [
        "kullanici",
        "asistan",
    ]
    # ikinci mesajda gecmis gider, sistem istemi en basta
    await istemci.put("/api/ayarlar", json={"sistem_istemi": "Kisa cevap ver."})
    await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Tekrar", "dusunme": "derin"})
    son_istek = sunucu.istekler[-1]
    sistem = son_istek["messages"][0]
    assert sistem["role"] == "system" and sistem["content"].endswith("Kisa cevap ver.")
    assert "klasor_listele" in sistem["content"] and son_istek["tools"]
    assert [m["role"] for m in son_istek["messages"][1:]] == ["user", "assistant", "user"]
    assert son_istek["chat_template_kwargs"] == {"enable_thinking": True}


async def test_sohbet_bos_mesaj_ve_olmayan_oturum(istemci):
    o = await yeni_oturum(istemci)
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "  "})
    assert olaylar(r.text) == [{"tur": "hata", "mesaj": "Bos mesaj gonderilemez."}]
    r = await istemci.post("/api/oturumlar/abcdef123456/mesaj", json={"metin": "x"})
    assert r.status_code == 404


async def test_sohbet_resim_ses_metin_ekleri(istemci, sunucu):
    resim = (
        await istemci.post("/api/ekler", files={"dosya": ("b.png", png(3000, 1000), "x")})
    ).json()
    ses = (await istemci.post("/api/ekler", files={"dosya": ("k.wav", b"RIFF1234", "x")})).json()
    metin = (await istemci.post("/api/ekler", files={"dosya": ("n.txt", b"ozet", "x")})).json()
    o = await yeni_oturum(istemci)
    await istemci.put("/api/ayarlar", json={"model": "gemma4-e4b-heretic"})
    r = await istemci.post(
        f"/api/oturumlar/{o}/mesaj",
        json={"metin": "Bunlara bak", "ekler": [resim["id"], ses["id"], metin["id"]]},
    )
    assert olaylar(r.text)[-1]["tur"] == "bitti"
    icerik = sunucu.istekler[-1]["messages"][-1]["content"]
    assert [p["type"] for p in icerik] == ["text", "image_url", "input_audio", "text"]
    assert "[Dosya: n.txt]\nozet" in icerik[3]["text"]
    # ses desteklemeyen modelde anlasilir hata, mesaj hatasiyla kaydedilir
    await istemci.put("/api/ayarlar", json={"model": "deepseek-heretic"})
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "", "ekler": [ses["id"]]})
    hata = olaylar(r.text)[-1]  # hata akisi bitirir; sahte "bitti" gelmez (A0.5)
    assert hata["tur"] == "hata" and "ses girisini desteklemiyor" in hata["mesaj"]
    kayit = (await istemci.get(f"/api/oturumlar/{o}")).json()
    assert "desteklemiyor" in kayit["mesajlar"][-1]["hata"]


async def test_sohbet_pdf_metin_katmani_ilerleme(istemci, sunucu):
    import fitz

    belge = fitz.open()
    belge.new_page().insert_text((72, 72), "Bu PDF secilebilir yazi iceriyor ve yeterince uzun.")
    pdf = (
        await istemci.post("/api/ekler", files={"dosya": ("r.pdf", belge.tobytes(), "x")})
    ).json()
    o = await yeni_oturum(istemci)
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "", "ekler": [pdf["id"]]})
    ol = olaylar(r.text)
    assert any(x["tur"] == "ilerleme" and "sayfa 1/1" in x["metin"] for x in ol)
    son = sunucu.istekler[-1]["messages"][-1]["content"]
    assert "Bu PDF secilebilir yazi" in son[0]["text"] and "--- Sayfa 1 ---" in son[0]["text"]
    assert len(sunucu.istekler) == 1  # metin katmani: OCR istegi yok


async def test_sohbet_model_hatasi_kaydedilir(istemci, sunucu):
    sunucu.hata = (500, '{"error":{"message":"failed to process mtmd chunk"}}')
    o = await yeni_oturum(istemci)
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "x"})
    ol = olaylar(r.text)
    assert ol[-1]["tur"] == "hata" and "bellek yetmedi" in ol[-1]["mesaj"]
    # hata akisi bitirir (sahte "bitti" yok), ama mesaj hatasiyla diske kaydedilir (A0.5)
    kayit = (await istemci.get(f"/api/oturumlar/{o}")).json()["mesajlar"][-1]
    assert kayit["rol"] == "asistan" and "bellek yetmedi" in kayit["hata"]


async def test_model_hazirla_durdur_ve_harici(istemci, monkeypatch):
    from app.services import sistem

    cagri = []
    monkeypatch.setattr(sistem, "llama_server_durdur", lambda: cagri.append(1) or True)
    r = (await istemci.post("/api/model/hazirla", json={"model": "gemma4-e4b-heretic"})).json()
    assert r["model"] == "gemma4-e4b-heretic"
    assert (await istemci.post("/api/model/durdur", json={})).json() == {"harici_kapatildi": False}
    r = await istemci.post("/api/model/durdur", json={"harici": True})
    assert r.json() == {"harici_kapatildi": True} and cagri == [1]


async def test_baska_model_acikken_anlasilir_hata(istemci, sunucu):
    sunucu.acik_modeller = ["deepseek-heretic"]
    r = await istemci.post("/api/model/hazirla", json={"model": "gemma4-12b-heretic"})
    assert r.status_code == 503 and "baska model acik" in r.json()["hata"]


async def test_ayar_testi(istemci):
    t = (await istemci.post("/api/ayarlar/test", json={})).json()
    assert t["basarili"] and t["maliyet"] == "0 (yerel)" and t["uretim_tok_sn"] == 6.5


async def test_karsilastir_iki_model(istemci):
    r = await istemci.post(
        "/api/karsilastir",
        json={"istem": "Merhaba", "modeller": ["deepseek-heretic", "gemma4-e4b-heretic"]},
    )
    ol = olaylar(r.text)
    bitenler = [x for x in ol if x["tur"] == "model_bitti"]
    assert [b["model"] for b in bitenler] == ["deepseek-heretic", "gemma4-e4b-heretic"]
    assert all(b["metin"] == "Merhaba, ben yerel modelim." for b in bitenler)
    assert {x["model"] for x in ol if x["tur"] == "parca"} == {
        "deepseek-heretic",
        "gemma4-e4b-heretic",
    }
    assert ol[-1] == {"tur": "hepsi_bitti"}
    r = await istemci.post("/api/karsilastir", json={"istem": "x", "modeller": ["yok"]})
    assert olaylar(r.text)[0]["mesaj"] == "Bilinmeyen model: yok"


async def test_karsilastir_model_hatasi_digerini_durdurmaz(istemci, sunucu):
    sunucu.hata = (500, "boom")
    r = await istemci.post(
        "/api/karsilastir", json={"istem": "x", "modeller": ["deepseek-heretic"]}
    )
    ol = olaylar(r.text)
    assert ol[-2]["tur"] == "model_hata" and "500" in ol[-2]["mesaj"]


async def test_ocr_testi_benzerlik_ve_json(istemci):
    ek = (await istemci.post("/api/ekler/ornek-belge")).json()
    r = await istemci.post(
        "/api/ocr",
        json={
            "ek_id": ek["id"],
            "modeller": ["gemma4-12b-heretic"],
            "beklenen": ek["beklenen"],
            "json_cikar": True,
        },
    )
    son = [x for x in olaylar(r.text) if x["tur"] == "model_bitti"][0]
    assert son["benzerlik"] == 100.0 and son["turkce_harf"] >= 8
    assert son["json"] == {"alanlar": [{"ad": "Hakedis no", "deger": "7"}]}
    metin = (await istemci.post("/api/ekler", files={"dosya": ("a.txt", b"x", "t")})).json()
    r = await istemci.post(
        "/api/ocr", json={"ek_id": metin["id"], "modeller": ["deepseek-heretic"]}
    )
    assert "resim ya da PDF" in olaylar(r.text)[0]["mesaj"]


async def test_ocr_testi_pdf_ocr_zorla(istemci, sunucu):
    import fitz

    belge = fitz.open()
    belge.new_page().insert_text((72, 72), "Secilebilir yazi var ama OCR zorlanacak, uzun metin.")
    pdf = (
        await istemci.post("/api/ekler", files={"dosya": ("p.pdf", belge.tobytes(), "x")})
    ).json()
    r = await istemci.post("/api/ocr", json={"ek_id": pdf["id"], "modeller": ["deepseek-heretic"]})
    ol = olaylar(r.text)
    assert any(x["tur"] == "ilerleme" for x in ol)
    son = [x for x in ol if x["tur"] == "model_bitti"][0]
    assert "HAKEDİŞ" in son["metin"]  # metin_katmani=False: sayfa resme cevrilip OCR'landi
    assert "benzerlik" not in son


async def test_arac_testi_olaylari(istemci):
    araclar = (await istemci.get("/api/araclar")).json()
    assert len(araclar["araclar"]) == 5 and araclar["ornekler"]
    r = await istemci.post("/api/arac-testi", json={"istem": "1250 dolar kac TL?"})
    ol = olaylar(r.text)
    cagri = next(x for x in ol if x["tur"] == "arac_cagrisi")
    assert cagri["ad"] == "kur_getir" and cagri["argumanlar"] == {"para_birimi": "USD"}
    sonuc = next(x for x in ol if x["tur"] == "arac_sonucu")
    assert sonuc["sonuc"]["tl_karsiligi"] == 41.2
    bitti = next(x for x in ol if x["tur"] == "model_bitti")
    assert "51.500" in bitti["cevap"] and bitti["cagri_sayisi"] == 1 and bitti["tur_sayisi"] == 2


async def test_test_paketi_puan(istemci):
    r = await istemci.post("/api/test-paketi", json={"modeller": ["gemma4-e4b-heretic"]})
    ol = olaylar(r.text)
    sonuclar = {x["test"]: x["basarili"] for x in ol if x["tur"] == "test_sonucu"}
    assert sonuclar == {"mantik": True, "arac": True, "json": True, "ocr": True, "sansursuz": True}
    bitti = next(x for x in ol if x["tur"] == "model_bitti")
    assert bitti["puan"] == 5 and bitti["toplam"] == 5


async def test_test_paketi_hatali_test_basarisiz_sayilir(istemci, sunucu):
    sunucu.hata = (500, "boom")
    r = await istemci.post("/api/test-paketi", json={"modeller": ["deepseek-heretic"]})
    ol = olaylar(r.text)
    assert all(not x["basarili"] for x in ol if x["tur"] == "test_sonucu")
    assert next(x for x in ol if x["tur"] == "model_bitti")["puan"] == 0


async def test_sohbet_devaminda_onceki_resim_ve_pdf_modele_gider(istemci, sunucu):
    import base64

    import fitz
    from PIL import Image

    resim = (
        await istemci.post("/api/ekler", files={"dosya": ("f.png", png(3000, 1500), "x")})
    ).json()
    belge = fitz.open()
    belge.new_page().insert_text((72, 72), "Sozlesme bedeli 500.000 TL olarak belirlenmistir.")
    pdf = (
        await istemci.post("/api/ekler", files={"dosya": ("s.pdf", belge.tobytes(), "x")})
    ).json()
    o = await yeni_oturum(istemci)
    await istemci.post(
        f"/api/oturumlar/{o}/mesaj", json={"metin": "Bu fatura", "ekler": [resim["id"]]}
    )
    await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Bu da", "ekler": [pdf["id"]]})
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Ilk resimde ne vardi?"})
    assert olaylar(r.text)[-1]["tur"] == "bitti"
    mesajlar = sunucu.istekler[-1]["messages"][1:]  # [0]: arac sistem notu
    assert [m["role"] for m in mesajlar] == ["user", "assistant", "user", "assistant", "user"]
    ilk = mesajlar[0]["content"]
    assert ilk[0]["text"] == "Bu fatura" and ilk[1]["type"] == "image_url"
    veri = base64.b64decode(ilk[1]["image_url"]["url"].split(",", 1)[1])
    assert max(Image.open(io.BytesIO(veri)).size) == 1024  # gecmiste kucultulmus
    assert "Sozlesme bedeli 500.000 TL" in mesajlar[2]["content"][1]["text"]
    assert mesajlar[-1] == {"role": "user", "content": "Ilk resimde ne vardi?"}


async def test_sohbet_baglama_sigmayan_eski_resim_uyarisi(istemci, sunucu):
    ekler = [
        (await istemci.post("/api/ekler", files={"dosya": (f"r{i}.png", png(), "x")})).json()
        for i in range(5)
    ]
    await istemci.put("/api/ayarlar", json={"max_tokens": 4096, "baglam_token": 8192})
    o = await yeni_oturum(istemci)
    for ek in ekler:
        await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "bak", "ekler": [ek["id"]]})
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Hepsini ozetle"})
    uyari = next(x for x in olaylar(r.text) if x["tur"] == "uyari")
    assert "r0.png" in uyari["metin"] and "r4.png" not in uyari["metin"]  # en eski duser
    gorseller = [
        p
        for m in sunucu.istekler[-1]["messages"]
        if isinstance(m["content"], list)
        for p in m["content"]
        if p["type"] == "image_url"
    ]
    assert 1 <= len(gorseller) < 5  # en yeniler gitti, en eskiler dustu


async def test_sohbette_arac_masaustunu_listeler(istemci, sunucu, tmp_path, monkeypatch):
    from app.services import sohbet_araclari

    masa = tmp_path / "Masaustu"
    (masa / "Projeler").mkdir(parents=True)
    (masa / "notlar.txt").write_text("merhaba", encoding="utf-8")
    monkeypatch.setattr(sohbet_araclari, "bilinen_klasor", lambda ad: masa)
    o = await yeni_oturum(istemci)
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Masaustumde ne var?"})
    ol = olaylar(r.text)
    turler = [x["tur"] for x in ol]
    assert turler.index("arac_cagrisi") < turler.index("arac_sonucu") < turler.index("parca")
    cagri = next(x for x in ol if x["tur"] == "arac_cagrisi")
    assert cagri["ad"] == "klasor_listele" and cagri["argumanlar"] == {"yol": "masaustu"}
    sonuc = next(x for x in ol if x["tur"] == "arac_sonucu")
    assert sonuc["ozet"] == "1 klasor, 1 dosya"
    son = ol[-1]["mesaj"]
    assert "[klasor] Projeler" in son["metin"] and "notlar.txt" in son["metin"]
    assert son["araclar"][0]["ad"] == "klasor_listele"
    tool = [m for m in sunucu.istekler[-1]["messages"] if m["role"] == "tool"][0]
    assert tool["tool_call_id"] == "m1"


async def test_sohbet_araclari_kapatilabilir(istemci, sunucu):
    await istemci.put("/api/ayarlar", json={"sohbet_araclari": False, "skiller_acik": False})
    o = await yeni_oturum(istemci)
    await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Masaustumde ne var?"})
    istek = sunucu.istekler[-1]
    assert "tools" not in istek and istek["messages"][0]["role"] == "user"


async def test_ayni_resim_tekrar_eklenince_eskisi_gonderilmez_uyari_yok(istemci, sunucu):
    resim = (await istemci.post("/api/ekler", files={"dosya": ("ayni.png", png(), "x")})).json()
    o = await yeni_oturum(istemci)
    for metin in ("ilk", "tekrar"):
        await istemci.post(
            f"/api/oturumlar/{o}/mesaj", json={"metin": metin, "ekler": [resim["id"]]}
        )
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "bu resim ne?"})
    assert not [x for x in olaylar(r.text) if x["tur"] == "uyari"]
    mesajlar = sunucu.istekler[-1]["messages"][1:]
    gorseller = [
        p
        for m in mesajlar
        if isinstance(m["content"], list)
        for p in m["content"]
        if p["type"] == "image_url"
    ]
    assert len(gorseller) == 1  # yalniz en yeni kopya
    assert "asagida tekrar gonderildi" in mesajlar[0]["content"]
    # simdiki mesajda da varsa gecmisteki hic gonderilmez
    await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "yine", "ekler": [resim["id"]]})
    son = sunucu.istekler[-1]["messages"]
    gecmis_gorsel = [
        p
        for m in son[1:-1]
        if isinstance(m["content"], list)
        for p in m["content"]
        if p["type"] == "image_url"
    ]
    assert gecmis_gorsel == [] and son[-1]["content"][1]["type"] == "image_url"
