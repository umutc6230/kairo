"""A0 regresyon testleri (AGENT-GELISTIRME-TALIMATI.md, Kabul A0).

Bu testler duzeltmeden ONCE basarisiz olacak sekilde yazildi:
- A0.2 sahte loopback adresinin reddi
- A0.3 kesilen arac sonucunda gecerli JSON + devam bilgisi
- A0.4 sonraki turda arac kaniti (tool_call/tool_result cifti)
- A0.5 iptalde uretilmis arac sonuclarinin kaydi
- A0.6 biriken arac ciktisinda tur basina baglam siniri
- A0.7 akis sirasinda upload boyut siniri
- A0.8 ayni oturuma eszamanli mesaj ve silinmis oturuma gec cevap
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.services import ekler as ekler_modulu
from app.services.ayarlar import AyarDeposu, KullaniciAyarlari
from app.services.oturumlar import Mesaj, OturumDeposu
from app.services.sohbet import (
    ARAC_SONUC_KARAKTER,
    MesajIstegi,
    SohbetServisi,
    cevap_akit,
    gecmis_mesajlari,
)
from app.services.sohbet_araclari import DosyaAraclari
from app.services.yerel_llm import YerelLLM


@pytest.fixture
def servis_kur(veri: Path, sunucu, llm_dizin: Path, skill_klasoru: Path):
    """Gercek SohbetServisi + sahte llama-server; akis dogrudan surulur (iptal deterministik).
    `isleyici` ile istek govdesine gore cevap veren ozel transport verilebilir."""
    from app.services.ekler import EkDeposu
    from app.services.model_yonetici import ModelYonetici
    from app.services.skiller import SkillDeposu
    from app.services.talimatlar import TalimatDeposu

    def kur(isleyici=None):
        ayarlar = AyarDeposu(veri)
        ayarlar.guncelle({"llm_dizin": str(llm_dizin), "skiller_acik": False})
        yonetici = ModelYonetici(
            ayarlar,
            lambda **kw: YerelLLM(transport=httpx.MockTransport(isleyici or sunucu), **kw),
        )
        oturumlar = OturumDeposu(veri)
        servis = SohbetServisi(
            yonetici,
            oturumlar,
            EkDeposu(veri),
            TalimatDeposu(veri),
            SkillDeposu(veri, [("claude", skill_klasoru)]),
        )
        return servis, oturumlar

    return kur


@pytest.fixture
def sohbet_servisi(servis_kur):
    return servis_kur()


# ---------------------------------------------------------------- A0.2 adres


@pytest.mark.parametrize(
    "adres",
    [
        "http://localhost.example.invalid",
        "http://127.0.0.1@example.invalid",
        "http://127.0.0.1.example.invalid:8080",
        "http://localhost@evil.test/v1",
        "http://example.test",
        "ftp://127.0.0.1:8080",
        "http://[::2]:8080",
        "not a url",
        "http://",
    ],
)
def test_adres_yerel_olmayan_reddedilir(adres: str) -> None:
    with pytest.raises(ValidationError):
        KullaniciAyarlari(adres=adres)


@pytest.mark.parametrize(
    ("adres", "beklenen"),
    [
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080/v1"),
        ("http://127.0.0.1:8080/v1", "http://127.0.0.1:8080/v1"),
        ("http://localhost:8080/", "http://localhost:8080/v1"),
        ("https://127.0.0.1:8443", "https://127.0.0.1:8443/v1"),
        ("http://[::1]:8080", "http://[::1]:8080/v1"),
        ("http://127.0.0.1", "http://127.0.0.1/v1"),
    ],
)
def test_adres_yerel_kabul(adres: str, beklenen: str) -> None:
    assert KullaniciAyarlari(adres=adres).adres == beklenen


def test_adres_bozuk_ayar_dosyasinda_varsayilana_doner(veri: Path) -> None:
    """Diskteki eski/kotu adres uygulamayi kilitlemesin, varsayilan yerel adrese donsun."""
    depo = AyarDeposu(veri)
    (veri / "ayarlar.json").write_text(
        json.dumps({"adres": "http://127.0.0.1@example.invalid"}), encoding="utf-8"
    )
    assert "example.invalid" not in depo.oku().adres


# ----------------------------------------------------- A0.3 arac sonucu kisaltma


def test_dosya_oku_yapisal_devam_bilgisi(tmp_path: Path) -> None:
    dosya = tmp_path / "uzun.txt"
    dosya.write_text("\n".join(f"satir {i}" for i in range(1, 1001)), encoding="utf-8")
    # A1: dosya araclari yetkili koklere bagli; tmp_path'i kok olarak ver
    araclar = DosyaAraclari([tmp_path])
    dosya_oku = araclar.dosya_oku

    bas = dosya_oku(str(dosya))
    assert bas["truncated"] is True
    assert bas["toplam_satir"] == 1000
    assert bas["satir_baslangic"] == 1
    assert bas["next_offset"] > 0
    assert bas["icerik"]

    son = dosya_oku(str(dosya), baslangic=bas["next_offset"])
    assert son["satir_baslangic"] >= bas["satir_bitis"]
    assert son["truncated"] is False
    assert son["next_offset"] is None
    # iki parca birlesince tum dosya cikar (CRLF oldugu gibi korunur)
    assert bas["icerik"] + son["icerik"] == dosya.read_bytes().decode("utf-8")


async def test_arac_sonucu_kesilse_de_gecerli_json(tmp_path: Path) -> None:
    """7000+ karakterlik sonuc modelin eline GECERLI JSON olarak ulassin, devam bilgisi kalsin."""
    from app.services.sohbet import arac_calistir

    def kocaman(**_: object) -> dict:
        return {"icerik": "x" * 40000, "toplam_karakter": 40000, "next_offset": 6000}

    cagri = {"id": "t1", "function": {"name": "kocaman", "arguments": "{}"}}
    mesaj, kayit = await arac_calistir(cagri, {"kocaman": kocaman}, lambda o: None, {})

    assert len(mesaj["content"]) <= ARAC_SONUC_KARAKTER
    govde = json.loads(mesaj["content"])  # duzeltmeden once JSONDecodeError
    assert govde["truncated"] is True
    assert govde["toplam_karakter"] == 40000
    assert govde["next_offset"] == 6000
    assert json.loads(kayit["sonuc"])["truncated"] is True


def test_sonuc_kisalt_kenar_durumlari() -> None:
    from app.services.sohbet import sonuc_kisalt

    # sigan sonuc oldugu gibi gecer
    metin, kesildi = sonuc_kisalt({"a": "kisa"})
    assert kesildi is False and json.loads(metin) == {"a": "kisa"}

    # dict olmayan buyuk sonuc da gecerli JSON'a sarilir
    metin, kesildi = sonuc_kisalt("u" * 50000)
    govde = json.loads(metin)
    assert kesildi and govde["truncated"] and govde["toplam_karakter"] == 50000

    # kisaltilacak metin alani yok (uzun liste): protokol korunur, JSON gecerli kalir
    metin, kesildi = sonuc_kisalt({"ogeler": list(range(20000))})
    assert kesildi and json.loads(metin)["truncated"] is True

    # cok kucuk sinirda bile gecerli JSON doner
    metin, kesildi = sonuc_kisalt({"icerik": "v" * 5000}, sinir=60)
    assert kesildi and json.loads(metin)["truncated"] is True


def test_baglami_darat_sinir_durumlari() -> None:
    from app.services.sohbet import baglami_darat

    mesajlar = [{"role": "user", "content": "x" * 400}]
    # butce verilmezse dokunulmaz
    assert baglami_darat(mesajlar, None, 0, lambda o: None) is mesajlar

    # rezerv butceyi tamamen yerse acik uyari verilir, mesaj degismez
    olaylar_: list[dict] = []
    assert baglami_darat(mesajlar, 100, 5000, olaylar_.append) is mesajlar
    assert olaylar_[0]["kod"] == "baglam_asildi"

    # sigan baglam dokunulmaz
    assert baglami_darat(mesajlar, 16384, 1024, lambda o: None) is mesajlar

    # eski mesajlar dusurulur, sistem ve son mesaj kalir
    olaylar_.clear()
    cok = [{"role": "system", "content": "s"}] + [
        {"role": "user", "content": "y" * 3000} for _ in range(10)
    ]
    sonuc = baglami_darat(cok, 2000, 0, olaylar_.append)
    assert len(sonuc) < len(cok)
    assert sonuc[0]["role"] == "system" and sonuc[-1] == cok[-1]
    assert any(o["kod"] == "baglam_daraldi" for o in olaylar_)


def test_mesaj_token_arac_cagrisini_sayar() -> None:
    from app.services.sohbet import mesaj_token

    cagri = {"id": "a", "function": {"name": "f", "arguments": '{"yol": "masaustu"}'}}
    with_ = {"role": "assistant", "content": "", "tool_calls": [cagri]}
    assert mesaj_token(with_) > mesaj_token({"role": "assistant", "content": ""})


async def test_hata_yolunda_arac_kayitlari_saklanir(servis_kur, sunucu) -> None:
    """Model arac sonrasi hata verirse, calisan arac asistan kaydinda kalsin (A0.5)."""

    def arac_sonrasi_coker(r: httpx.Request) -> httpx.Response:
        """Arac sonucu iceren ISTEKTE coker: zamanlamaya bagli olmayan deterministik hata."""
        if r.url.path.startswith("/v1/chat") and r.content:
            govde = json.loads(r.content)
            if any(m.get("role") == "tool" for m in govde.get("messages", [])):
                return httpx.Response(500, text='{"error":{"message":"out of device memory"}}')
        return sunucu(r)

    servis, oturumlar = servis_kur(arac_sonrasi_coker)
    (Path.home() / "Desktop").mkdir(parents=True, exist_ok=True)
    oturum = oturumlar.olustur()

    gorulen: list[dict] = []
    async for olay in servis.mesaj_gonder(oturum.id, MesajIstegi(metin="masaustunde ne var")):
        gorulen.append(olay)

    assert gorulen[-1]["tur"] == "hata"
    asistan = oturumlar.getir(oturum.id).mesajlar[-1]
    assert asistan.hata and [a["ad"] for a in asistan.araclar] == ["klasor_listele"]


# -------------------------------------------------- A0.4 gecmiste arac kaniti


async def test_gecmis_arac_kaniti_sonraki_tura_gider(veri: Path, sunucu) -> None:
    from app.services.ekler import EkDeposu

    llm = YerelLLM(transport=httpx.MockTransport(sunucu))
    gecmis = [
        Mesaj(rol="kullanici", metin="masaustunde ne var"),
        Mesaj(
            rol="asistan",
            metin="Masaustunde rapor.txt var.",
            araclar=[
                {
                    "id": "m1",
                    "ad": "klasor_listele",
                    "argumanlar": {"yol": "masaustu"},
                    "ozet": "0 klasor, 1 dosya",
                    "sonuc": json.dumps({"ogeler": ["BENZERSIZ-KANIT-9173.txt"]}),
                    "sure_ms": 3,
                }
            ],
        ),
    ]
    mesajlar, _ = await gecmis_mesajlari(llm, EkDeposu(veri), gecmis, 8000, lambda o: None)

    duz = json.dumps(mesajlar, ensure_ascii=False)
    assert "BENZERSIZ-KANIT-9173" in duz  # duzeltmeden once bulunamaz
    # tool_call ve tool_result dogru sirada ve eslesen id ile
    roller = [m["role"] for m in mesajlar]
    assert "tool" in roller
    cagiran = next(m for m in mesajlar if m.get("tool_calls"))
    arac = next(m for m in mesajlar if m["role"] == "tool")
    assert roller.index("tool") > roller.index(cagiran["role"])
    assert arac["tool_call_id"] == cagiran["tool_calls"][0]["id"] == "m1"


async def test_gecmis_arac_kaniti_butce_dolunca_dusurulur(veri: Path, sunucu) -> None:
    from app.services.ekler import EkDeposu

    llm = YerelLLM(transport=httpx.MockTransport(sunucu))
    gecmis = [
        Mesaj(rol="kullanici", metin="oku"),
        Mesaj(
            rol="asistan",
            metin="okudum",
            araclar=[{"id": "a", "ad": "dosya_oku", "argumanlar": {}, "sonuc": "y" * 30000}],
        ),
    ]
    mesajlar, _ = await gecmis_mesajlari(llm, EkDeposu(veri), gecmis, 200, lambda o: None)
    assert len(json.dumps(mesajlar)) < 30000  # butceye sigmayan kanit baglamı sismesin


# ------------------------------------------------ A0.5 iptal / hata yolunda kayit


async def test_iptalde_arac_sonuclari_kaydedilir(sohbet_servisi, veri: Path) -> None:
    """Akis ortasinda kopan istemcide, o ana kadar calisan araclar asistan kaydinda kalsin."""
    servis, oturumlar = sohbet_servisi
    (Path.home() / "Desktop").mkdir(parents=True, exist_ok=True)
    oturum = oturumlar.olustur()

    akis = servis.mesaj_gonder(oturum.id, MesajIstegi(metin="masaustunde ne var"))
    async for olay in akis:
        if olay["tur"] == "arac_sonucu":
            await akis.aclose()  # istemci koptu / kullanici durdurdu
            break

    asistan = oturumlar.getir(oturum.id).mesajlar[-1]
    assert asistan.rol == "asistan"
    assert asistan.hata == "Durduruldu."
    assert [a["ad"] for a in asistan.araclar] == ["klasor_listele"]  # duzeltmeden once bos
    assert asistan.araclar[0]["durum"] == "tamam"


async def test_sonucsuz_arac_cagrisi_isaretlenir(sunucu) -> None:
    """Tur siniri doldugunda sonucu alinmamis cagri acik durumla kaydedilsin."""

    async def dondurme(**_: object) -> dict:
        raise AssertionError("cagrilmamaliydi")

    sunucu.dusunce = ""
    llm = YerelLLM(transport=httpx.MockTransport(sunucu))
    sonuc = await cevap_akit(
        llm,
        [{"role": "user", "content": "masaustunde ne var"}],
        lambda o: None,
        araclar=[{"type": "function", "function": {"name": "klasor_listele", "parameters": {}}}],
        isleyiciler={},  # isleyici yok: sonuc alinamaz
        max_tur=1,
    )
    assert sonuc["araclar"], "sonucsuz cagri da kaydedilmeli"
    assert sonuc["araclar"][0]["durum"] in {"sonucsuz", "hata"}


# ------------------------------------------------------- A0.6 tur basina butce


async def test_butce_her_turda_yeniden_hesaplanir(sunucu) -> None:
    """Biriken arac ciktilari baglami asarsa istek korlemesine gonderilmesin."""
    sunucu.dusunce = ""
    llm = YerelLLM(transport=httpx.MockTransport(sunucu))
    uyarilar: list[dict] = []

    def buyuk(**_: object) -> dict:
        return {"icerik": "z" * 20000}

    await cevap_akit(
        llm,
        [{"role": "user", "content": "masaustunde ne var"}],
        lambda o: uyarilar.append(o) if o["tur"] == "uyari" else None,
        araclar=[{"type": "function", "function": {"name": "klasor_listele", "parameters": {}}}],
        isleyiciler={"klasor_listele": buyuk},
        max_tur=3,
        baglam_token=2000,
    )
    son_istek = json.dumps(sunucu.istekler[-1], ensure_ascii=False)
    assert len(son_istek) < 20000, "baglam asildiginda arac kaniti daraltilmali"
    assert any(o.get("kod") == "baglam_daraldi" for o in uyarilar)


def test_protokol_temizle_yetim_arac_mesajini_atar() -> None:
    from app.services.sohbet import protokol_temizle

    cagri = {"id": "x1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
    # cagrisi dusurulmus sonuc + sonucu dusurulmus cagri
    karisik = [
        {"role": "system", "content": "s"},
        {"role": "tool", "tool_call_id": "eski", "content": "{}"},
        {"role": "assistant", "content": "", "tool_calls": [cagri]},
        {"role": "assistant", "content": "cevap"},
        {"role": "user", "content": "devam"},
    ]
    temiz = protokol_temizle(karisik)
    assert not [m for m in temiz if m.get("role") == "tool"]
    assert not [m for m in temiz if m.get("tool_calls")]
    assert [m["role"] for m in temiz] == ["system", "assistant", "user"]

    # eslesen cift korunur
    saglam = [
        {"role": "assistant", "content": "", "tool_calls": [cagri]},
        {"role": "tool", "tool_call_id": "x1", "content": "{}"},
        {"role": "assistant", "content": "bitti"},
    ]
    assert protokol_temizle(saglam) == saglam


def test_gorsel_base64_butceyi_sismesin() -> None:
    """Resim parcasi base64 KARAKTER sayisiyla olculmemeli; yoksa her resimli sohbette
    baglam yanlisliktan dolu sayilir ve gecmis bosa dusurulur."""
    from app.services.sohbet import RESIM_TOKEN, mesaj_token

    resimli = {
        "role": "user",
        "content": [
            {"type": "text", "text": "buna bak"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 1_500_000}},
        ],
    }
    assert mesaj_token(resimli) < RESIM_TOKEN * 2


async def test_resimli_gecmis_butce_uyarisi_vermez(sunucu) -> None:
    sunucu.dusunce = ""
    llm = YerelLLM(transport=httpx.MockTransport(sunucu))
    olaylar_: list[dict] = []
    resim = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 900_000}}
    await cevap_akit(
        llm,
        [
            {"role": "user", "content": [{"type": "text", "text": "selam"}, resim]},
            {"role": "assistant", "content": "gorduk"},
            {"role": "user", "content": "devam"},
        ],
        olaylar_.append,
        baglam_token=16384,
        rezerv=1024,
    )
    assert not [o for o in olaylar_ if o.get("kod") == "baglam_daraldi"]
    assert len(sunucu.istekler[-1]["messages"]) == 3  # gecmis dusurulmedi


# ----------------------------------------------------------- A0.7 upload siniri


async def test_upload_boyut_siniri_akista_uygulanir(istemci, monkeypatch) -> None:
    monkeypatch.setattr(ekler_modulu, "MAX_BOYUT", 4096)
    cevap = await istemci.post(
        "/api/ekler", files={"dosya": ("buyuk.txt", b"a" * 9000, "text/plain")}
    )
    assert cevap.status_code == 400
    assert "buyuk" in cevap.json()["hata"].lower() or "büyük" in cevap.json()["hata"].lower()


async def test_upload_sinir_altinda_calisir(istemci, monkeypatch) -> None:
    monkeypatch.setattr(ekler_modulu, "MAX_BOYUT", 4096)
    cevap = await istemci.post(
        "/api/ekler", files={"dosya": ("kucuk.txt", b"a" * 100, "text/plain")}
    )
    assert cevap.status_code == 200
    assert cevap.json()["boyut"] == 100


# ------------------------------------------- A0.8 eszamanlilik ve silinmis oturum


async def test_eszamanli_mesajlar_kaybolmaz(istemci, veri: Path) -> None:
    oturum = (await istemci.post("/api/oturumlar")).json()

    async def gonder(metin: str) -> None:
        async with istemci.stream(
            "POST", f"/api/oturumlar/{oturum['id']}/mesaj", json={"metin": metin}
        ) as c:
            async for _ in c.aiter_lines():
                pass

    await asyncio.gather(gonder("birinci soru"), gonder("ikinci soru"))

    kayit = OturumDeposu(veri).getir(oturum["id"])
    metinler = [m.metin for m in kayit.mesajlar if m.rol == "kullanici"]
    assert sorted(metinler) == ["birinci soru", "ikinci soru"]  # hicbiri kaybolmadi
    assert len([m for m in kayit.mesajlar if m.rol == "asistan"]) == 2


async def test_silinmis_oturuma_gec_cevap_cokmez(sohbet_servisi) -> None:
    """Cevap akarken oturum silinirse akis anlasilir uyariyla bitsin, istisna sizmasin."""
    servis, oturumlar = sohbet_servisi
    oturum = oturumlar.olustur()
    gorulen: list[dict] = []
    silindi = False
    async for olay in servis.mesaj_gonder(oturum.id, MesajIstegi(metin="merhaba")):
        gorulen.append(olay)
        if not silindi and olay["tur"] == "kullanici_mesaji":
            oturumlar.sil(oturum.id)  # kullanici sohbeti silerken cevap akiyor
            silindi = True

    assert silindi
    turler = [o["tur"] for o in gorulen]
    assert "uyari" in turler
    assert "bitti" not in turler  # silinmis sohbete "kaydedildi" denmez
    assert any(o.get("kod") == "oturum_silindi" for o in gorulen)
