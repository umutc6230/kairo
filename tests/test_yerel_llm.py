"""yerel_llm.py icin ornek birim testler (ag yok, httpx.MockTransport) + istege bagli canli test.

Calistir:  pytest -q test_yerel_llm.py            (birim)
           pytest -q -m canli test_yerel_llm.py   (sunucu acikken canli)
Gerekir: pytest, pytest-asyncio (asyncio_mode = "auto" ya da asagidaki isaret).
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import yerel_llm as yl
from yerel_llm import (
    ANA_MODEL,
    DENGELI_BUTCE,
    DERIN_EK_TOKEN,
    DUSUNME_SECENEKLERI,
    DUSUNME_SEVIYELERI,
    GORUNTU_MODULU,
    GecersizDusunme,
    GoruntuDesteklenmiyor,
    ModelCevapHatasi,
    SunucuBaslamadi,
    SunucuKapali,
    YerelLLM,
)

pytestmark = [
    pytest.mark.asyncio,
    # modul geneli asyncio isareti sync testlerde uyari verir; zararsiz
    pytest.mark.filterwarnings("ignore:The test <Function:pytest.PytestWarning"),
]


def cevap(content: str = "", tool_calls: list | None = None, finish: str = "stop") -> dict:
    mesaj: dict = {"role": "assistant", "content": content}
    if tool_calls:
        mesaj["tool_calls"] = tool_calls
    return {"choices": [{"index": 0, "message": mesaj, "finish_reason": finish}]}


def istemci(isleyici) -> YerelLLM:
    return YerelLLM(transport=httpx.MockTransport(isleyici))


async def test_saglikli_ok_ve_kapali():
    llm = istemci(lambda r: httpx.Response(200, json={"status": "ok"}))
    assert await llm.saglikli() is True

    def kapali(r):
        raise httpx.ConnectError("yok", request=r)

    assert await istemci(kapali).saglikli() is False


async def test_metin_dusunme_kapali_gider():
    gorulen = {}

    def isle(r: httpx.Request):
        gorulen.update(json.loads(r.content))
        return httpx.Response(200, json=cevap("Ankara"))

    assert await istemci(isle).metin("Baskent?") == "Ankara"
    assert gorulen["chat_template_kwargs"] == {"enable_thinking": False}
    assert gorulen["model"] == "deepseek-heretic"


def govde_yakala():
    gorulen: dict = {}

    def isle(r: httpx.Request):
        gorulen.clear()
        gorulen.update(json.loads(r.content))
        gorulen["_timeout"] = r.extensions["timeout"]["read"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "x", "reasoning_content": "once dusundum"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    return gorulen, isle


@pytest.mark.parametrize(
    ("seviye", "acik", "butce", "max_tok", "zaman"),
    [
        ("kapali", False, None, 100, 300.0),
        ("dengeli", True, DENGELI_BUTCE, 100 + DENGELI_BUTCE, 600.0),
        ("derin", True, None, 100 + DERIN_EK_TOKEN, 1800.0),
    ],
)
async def test_dusunme_seviyeleri_govdeye_yansir(seviye, acik, butce, max_tok, zaman):
    gorulen, isle = govde_yakala()
    llm = YerelLLM(dusunme=seviye, transport=httpx.MockTransport(isle))
    await llm.metin("?", max_tokens=100)
    assert gorulen["chat_template_kwargs"] == {"enable_thinking": acik}
    assert gorulen.get("thinking_budget_tokens") == butce
    assert gorulen["max_tokens"] == max_tok
    assert gorulen["_timeout"] == zaman


async def test_ayar_degisince_aninda_gecerli_ve_cagri_bazli_ezilir():
    gorulen, isle = govde_yakala()
    llm = YerelLLM(transport=httpx.MockTransport(isle))
    await llm.metin("?")
    assert gorulen["chat_template_kwargs"]["enable_thinking"] is False
    llm.dusunme = "derin"
    await llm.metin("?")
    assert gorulen["chat_template_kwargs"]["enable_thinking"] is True
    assert llm.son_dusunce == "once dusundum"
    await llm.ocr(b"x", dusunme="kapali")  # gorev bazli ezme, ayar degismez
    assert gorulen["chat_template_kwargs"]["enable_thinking"] is False
    assert llm.dusunme == "derin"


async def test_gecersiz_dusunme_ve_sabit_zaman_asimi():
    with pytest.raises(GecersizDusunme):
        YerelLLM(dusunme="cok")
    llm = YerelLLM()
    with pytest.raises(GecersizDusunme):
        llm.dusunme = "yuksek"
    gorulen, isle = govde_yakala()
    llm = YerelLLM(dusunme="derin", okuma_zaman_asimi=42, transport=httpx.MockTransport(isle))
    await llm.metin("?")
    assert gorulen["_timeout"] == 42


def test_ayarlar_ekrani_secenekleri_tum_seviyeleri_kapsar():
    assert [s["deger"] for s in DUSUNME_SECENEKLERI] == list(DUSUNME_SEVIYELERI)
    assert all(s["ad"] and s["aciklama"] and s["sure"] for s in DUSUNME_SECENEKLERI)


async def test_bos_cevap_length_hatasi():
    llm = istemci(lambda r: httpx.Response(200, json=cevap("", finish="length")))
    with pytest.raises(ModelCevapHatasi):
        await llm.metin("?")


async def test_ocr_data_url_gonderir():
    gorulen = {}

    def isle(r):
        gorulen.update(json.loads(r.content))
        return httpx.Response(200, json=cevap("FATURA NO: 1"))

    assert await istemci(isle).ocr(b"\x89PNG...") == "FATURA NO: 1"
    parca = gorulen["messages"][0]["content"][1]
    assert parca["type"] == "image_url"
    assert parca["image_url"]["url"].startswith("data:image/png;base64,")


async def test_goruntu_modulu_yok_hatasi():
    llm = istemci(lambda r: httpx.Response(500, text="image input is not supported - mmproj"))
    with pytest.raises(GoruntuDesteklenmiyor):
        await llm.ocr(b"x")


async def test_json_cikti():
    gorulen = {}

    def isle(r):
        gorulen.update(json.loads(r.content))
        return httpx.Response(200, json=cevap('{"sehir":"Malatya","plaka":44}'))

    veri = await istemci(isle).json_cikti("?", {"type": "object"})
    assert veri == {"sehir": "Malatya", "plaka": 44}
    assert gorulen["response_format"]["type"] == "json_schema"


async def test_arac_dongusu():
    cagri = [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "hava", "arguments": '{"sehir":"Malatya"}'},
        }
    ]
    sira = iter([cevap(tool_calls=cagri, finish="tool_calls"), cevap("14 derece")])
    govdeler = []

    def isle(r):
        govdeler.append(json.loads(r.content))
        return httpx.Response(200, json=next(sira))

    async def hava(sehir: str) -> dict:
        return {"sehir": sehir, "sicaklik": 14}

    mesajlar = [{"role": "user", "content": "Hava?"}]
    sonuc = await istemci(isle).arac_dongusu(mesajlar, tools=[{}], isleyiciler={"hava": hava})
    assert sonuc == "14 derece"
    arac_mesaji = govdeler[1]["messages"][-1]
    assert arac_mesaji["role"] == "tool" and arac_mesaji["tool_call_id"] == "c1"
    assert json.loads(arac_mesaji["content"])["sicaklik"] == 14


async def test_baglanti_yoksa_sunucu_kapali():
    def isle(r):
        raise httpx.ConnectError("yok", request=r)

    with pytest.raises(SunucuKapali):
        await istemci(isle).metin("?")


async def test_akis():
    sse = (
        'data: {"choices":[{"delta":{"content":"1, "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"2"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    llm = istemci(lambda r: httpx.Response(200, text=sse))
    parcalar = [p async for p in llm.akis([{"role": "user", "content": "say"}])]
    assert "".join(parcalar) == "1, 2"


@pytest.mark.canli
async def test_canli_kisa():
    llm = YerelLLM()
    if not await llm.saglikli():
        pytest.skip("yerel sunucu kapali")
    assert "ankara" in (await llm.metin("Turkiye'nin baskenti? Tek kelime.")).lower()
    await llm.kapat()


async def test_modeller_ve_goruntu_destegi():
    def isle(r: httpx.Request):
        if r.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "deepseek-heretic"}]})
        return httpx.Response(200, json={"modalities": {"vision": True}})

    llm = istemci(isle)
    assert await llm.modeller() == ["deepseek-heretic"]
    assert await llm.goruntu_destegi() is True


async def test_hazirla_acik_sunucuya_dokunmaz():
    llm = istemci(lambda r: httpx.Response(200, json={"status": "ok"}))
    await llm.hazirla()
    assert llm._surec is None


async def test_hazirla_otomatik_kapaliysa_hata():
    llm = istemci(lambda r: httpx.Response(503, json={"status": "loading"}))
    with pytest.raises(SunucuKapali):
        await llm.hazirla(otomatik_baslat=False)


async def test_hazirla_klasor_yoksa_hata(tmp_path):
    llm = YerelLLM(dizin=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(SunucuBaslamadi):
        await llm.hazirla()


async def test_baslat_komutu_mmproj_ekler(tmp_path):
    (tmp_path / "llama.cpp").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "llama.cpp" / "llama-server.exe").write_bytes(b"")
    (tmp_path / "models" / ANA_MODEL).write_bytes(b"")
    llm = YerelLLM(dizin=tmp_path)
    assert "--mmproj" not in llm._baslat_komutu(8080, goruntu=True)
    (tmp_path / "models" / GORUNTU_MODULU).write_bytes(b"")
    komut = llm._baslat_komutu(8081, goruntu=True)
    assert "--mmproj" in komut and "--jinja" in komut and "8081" in komut
    await llm.kapat()


async def test_hazirla_surec_baslatir_ve_kapatir(tmp_path, monkeypatch):
    import subprocess

    import yerel_llm

    durum = {"n": 0}

    def isle(r):
        durum["n"] += 1
        return httpx.Response(200 if durum["n"] > 1 else 503, json={"status": "ok"})

    class SahteSurec:
        returncode = None

        def __init__(self, *a, **k):
            self.durdu = False

        def poll(self):
            return None if not self.durdu else 0

        def terminate(self):
            self.durdu = True

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(yerel_llm.subprocess, "Popen", SahteSurec)
    monkeypatch.setattr(YerelLLM, "_baslat_komutu", lambda self, p, goruntu: ["x"])
    monkeypatch.setattr(yerel_llm.asyncio, "sleep", lambda s: _hemen())
    llm = YerelLLM(dizin=tmp_path, transport=httpx.MockTransport(isle))
    await llm.hazirla(bekle_sn=5)
    surec = llm._surec
    assert isinstance(surec, SahteSurec)
    await llm.kapat()
    assert surec.durdu and llm._surec is None
    assert subprocess  # import kullanildi


async def _hemen():
    return None


async def test_sohbet_hata_dallari():
    llm = istemci(lambda r: httpx.Response(400, text="request exceeds the available context size"))
    with pytest.raises(ModelCevapHatasi, match="8192"):
        await llm.metin("?")
    llm = istemci(lambda r: httpx.Response(500, text="bilinmeyen"))
    with pytest.raises(ModelCevapHatasi, match="500"):
        await llm.metin("?")

    def zaman(r):
        raise httpx.ReadTimeout("yavas", request=r)

    with pytest.raises(ModelCevapHatasi, match="zamaninda"):
        await istemci(zaman).metin("?", sistem="Kisa cevap ver.")


async def test_json_bozuksa_hata_ve_resim_yolu(tmp_path):
    llm = istemci(lambda r: httpx.Response(200, json=cevap("bu json degil")))
    with pytest.raises(ModelCevapHatasi):
        await llm.json_cikti([{"role": "user", "content": "?"}], {"type": "object"})
    resim = tmp_path / "a.jpg"
    resim.write_bytes(b"jpg")
    assert YerelLLM.resim_data_url(resim).startswith("data:image/jpeg;base64,")


async def test_arac_dongusu_bilinmeyen_arac_ve_tur_siniri():
    cagri = [{"id": "c1", "function": {"name": "yok", "arguments": "{}"}}]
    llm = istemci(lambda r: httpx.Response(200, json=cevap(tool_calls=cagri, finish="tool_calls")))
    mesajlar = [{"role": "user", "content": "?"}]
    with pytest.raises(ModelCevapHatasi, match="turda"):
        await llm.arac_dongusu(mesajlar, tools=[{}], isleyiciler={}, max_tur=2)
    assert "Bilinmeyen arac" in mesajlar[-1]["content"]


async def test_akis_hata_ve_baglanti():
    with pytest.raises(ModelCevapHatasi):
        _ = [p async for p in istemci(lambda r: httpx.Response(500)).akis([])]

    def kapali(r):
        raise httpx.ConnectError("yok", request=r)

    with pytest.raises(SunucuKapali):
        _ = [p async for p in istemci(kapali).akis([])]


async def test_async_with_kapatir():
    async with istemci(lambda r: httpx.Response(200, json={"status": "ok"})) as llm:
        assert await llm.saglikli()
    assert llm._istemci.is_closed


# --- 2026-11-08 duzeltmeleri icin testler -----------------------------------------------
class SahteSurec:
    sayac = 0

    def __init__(self, *a, **k):
        SahteSurec.sayac += 1
        self.durdu = False
        self.returncode = None

    def poll(self):
        return 0 if self.durdu else None

    def terminate(self):
        self.durdu = True

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def sahte_baslat(monkeypatch):
    import yerel_llm

    SahteSurec.sayac = 0
    monkeypatch.setattr(yerel_llm.subprocess, "Popen", SahteSurec)
    monkeypatch.setattr(YerelLLM, "_baslat_komutu", lambda self, p, goruntu: ["x"])
    monkeypatch.setattr(yerel_llm.asyncio, "sleep", lambda s: _hemen())
    return SahteSurec


async def test_hazirla_zaman_asiminda_sureci_durdurur(tmp_path, sahte_baslat):
    llm = YerelLLM(dizin=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(SunucuBaslamadi, match="Zaman asimi"):
        await llm.hazirla(bekle_sn=0.05)
    assert llm._surec is None and llm._log is None  # yetim surec ve acik log kalmadi
    await llm.kapat()


async def test_hazirla_klasor_hic_yoksa_turkce_hata(tmp_path):
    yok = tmp_path / "olmayan" / "llm"
    llm = YerelLLM(dizin=yok, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(SunucuBaslamadi, match="Model klasoru bulunamadi"):
        await llm.hazirla()
    assert not yok.exists()  # log acmak icin klasor olusturulmadi


async def test_hazirla_popen_oserror_turkce_hata(tmp_path, monkeypatch, sahte_baslat):
    import yerel_llm

    def patla(*a, **k):
        raise OSError("erisim engellendi")

    monkeypatch.setattr(yerel_llm.subprocess, "Popen", patla)
    llm = YerelLLM(dizin=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(SunucuBaslamadi, match="erisim engellendi"):
        await llm.hazirla()
    assert llm._log is None


async def test_hazirla_ayni_anda_iki_cagri_tek_sunucu(tmp_path, sahte_baslat):
    import asyncio

    def isle(r):
        hazir = sahte_baslat.sayac > 0
        return httpx.Response(200 if hazir else 503, json={"status": "ok"})

    llm = YerelLLM(dizin=tmp_path, transport=httpx.MockTransport(isle))
    await asyncio.gather(llm.hazirla(bekle_sn=5), llm.hazirla(bekle_sn=5))
    assert sahte_baslat.sayac == 1
    await llm.kapat()


async def test_saglikli_json_olmayan_cevap_false():
    llm = istemci(lambda r: httpx.Response(200, text="<html>baska program</html>"))
    assert await llm.saglikli() is False


async def test_akis_hata_eslemesi_ve_zaman_asimi():
    llm = istemci(lambda r: httpx.Response(400, text="image input is not supported - mmproj"))
    with pytest.raises(GoruntuDesteklenmiyor):
        _ = [p async for p in llm.akis([])]
    llm = istemci(lambda r: httpx.Response(400, text="exceeds the available context size"))
    with pytest.raises(ModelCevapHatasi, match="8192"):
        _ = [p async for p in llm.akis([])]

    def yavas(r):
        raise httpx.ReadTimeout("yavas", request=r)

    with pytest.raises(ModelCevapHatasi, match="zamaninda"):
        _ = [p async for p in istemci(yavas).akis([])]


async def test_akis_kesilirse_hata():
    sse = 'data: {"choices":[{"delta":{"content":"yari"},"finish_reason":"length"}]}\n\n'
    llm = istemci(lambda r: httpx.Response(200, text=sse))
    with pytest.raises(ModelCevapHatasi, match="token sinirina"):
        _ = [p async for p in llm.akis([])]


async def test_ocr_ve_json_kesilirse_sessiz_donmez():
    llm = istemci(lambda r: httpx.Response(200, json=cevap("FATURA NO: 1\nTOP", finish="length")))
    with pytest.raises(ModelCevapHatasi, match="token sinirina"):
        await llm.ocr(b"x")
    llm = istemci(lambda r: httpx.Response(200, json=cevap('{"sehir": "Mal', finish="length")))
    with pytest.raises(ModelCevapHatasi, match="token sinirina"):
        await llm.json_cikti("?", {"type": "object"})


# --- Gorsel / PDF / parcalama / Job Object testleri ----------------------------------------
def _png(gen: int, yuk: int, bicim: str = "PNG") -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (gen, yuk), "white").save(tampon, bicim)
    return tampon.getvalue()


def _boyut(veri: bytes) -> tuple[int, int]:
    from PIL import Image

    return Image.open(io.BytesIO(veri)).size


def test_resmi_kucult_buyuk_kucuk_bozuk_ve_pillowsuz(monkeypatch):
    veri, mime = yl.resmi_kucult(_png(3200, 1000))
    assert mime == "image/png" and _boyut(veri) == (1600, 500)
    veri, mime = yl.resmi_kucult(_png(2000, 4000, "JPEG"), 1000, "image/jpeg")
    assert mime == "image/jpeg" and _boyut(veri) == (500, 1000)
    kucuk = _png(800, 600)
    assert yl.resmi_kucult(kucuk) == (kucuk, "image/png")
    assert yl.resmi_kucult(b"bozuk") == (b"bozuk", "image/png")
    buyuk = _png(3000, 3000)
    monkeypatch.setitem(sys.modules, "PIL", None)  # Pillow kurulu degil
    assert yl.resmi_kucult(buyuk) == (buyuk, "image/png")


async def test_ocr_gorseli_kucultup_gonderir(tmp_path):
    gorulen = {}

    def isle(r):
        gorulen.update(json.loads(r.content))
        return httpx.Response(200, json=cevap("YAZI"))

    def gonderilen() -> tuple[str, bytes]:
        url = gorulen["messages"][0]["content"][1]["image_url"]["url"]
        bas, veri = url.split(",", 1)
        return bas, base64.b64decode(veri)

    llm = istemci(isle)
    assert await llm.ocr(_png(4000, 2000)) == "YAZI"
    assert _boyut(gonderilen()[1]) == (1600, 800)
    yol = tmp_path / "a.jpg"
    yol.write_bytes(_png(3000, 3000, "JPEG"))
    await llm.ocr(yol, kucult=None)  # kucultme kapali: oldugu gibi gider
    bas, veri = gonderilen()
    assert bas == "data:image/jpeg;base64" and _boyut(veri) == (3000, 3000)


def _pdf(sayfalar: list[str]) -> bytes:
    import fitz

    belge = fitz.open()
    for yazi in sayfalar:
        sayfa = belge.new_page()
        if yazi:
            sayfa.insert_text((72, 72), yazi)
    veri = belge.tobytes()
    belge.close()
    return veri


def test_pdf_sayfalari_png_dondurur(tmp_path):
    veri = _pdf(["bir", "iki", "uc"])
    pngler = yl.pdf_sayfalari(veri, dpi=50)
    assert len(pngler) == 3 and all(p.startswith(b"\x89PNG") for p in pngler)
    yol = tmp_path / "b.pdf"
    yol.write_bytes(veri)
    assert len(yl.pdf_sayfalari(yol, dpi=50, sayfalar=[2])) == 1


def test_pdf_acilamaz_ve_pymupdf_yok(monkeypatch):
    with pytest.raises(yl.YerelLLMHatasi, match="PDF acilamadi"):
        yl.pdf_sayfalari(b"pdf degil")
    monkeypatch.setitem(sys.modules, "fitz", None)
    with pytest.raises(yl.YerelLLMHatasi, match="pip install pymupdf"):
        yl.pdf_sayfalari(b"x")


async def test_ocr_pdf_metin_katmanini_kullanir_taranmisi_okur():
    istekler = []

    def isle(r):
        istekler.append(json.loads(r.content))
        return httpx.Response(200, json=cevap("TARANMIS SAYFA METNI"))

    veri = _pdf(["Bu sayfada secilebilir yazi var ve yeterince uzun.", ""])
    adimlar = []
    sonuc = await istemci(isle).ocr_pdf(veri, dpi=50, ilerleme=lambda a, b: adimlar.append((a, b)))
    assert sonuc[0].startswith("Bu sayfada secilebilir") and sonuc[1] == "TARANMIS SAYFA METNI"
    assert len(istekler) == 1  # yalniz taranmis sayfa modele gitti
    assert adimlar == [(1, 2), (2, 2)]
    sonuc = await istemci(isle).ocr_pdf(veri, dpi=50, metin_katmani=False)
    assert sonuc == ["TARANMIS SAYFA METNI"] * 2


def test_parcala_sinirlar_ve_icerik_korunur():
    assert yl.parcala("") == [] and yl.parcala("  \n\n ") == []
    assert yl.parcala("kisa metin") == ["kisa metin"]
    assert yl.parcala("a\n\nb", 100) == ["a\n\nb"]
    uzun = " ".join(f"Cumle {i} burada bitiyor." for i in range(200))
    metin = "Giris paragrafi.\n\n" + uzun + "\n\n" + "X" * 250
    parcalar = yl.parcala(metin, 100)
    assert all(len(p) <= 100 for p in parcalar)

    def sade(s: str) -> str:
        return s.replace(" ", "").replace("\n", "")

    assert sade("".join(parcalar)) == sade(metin)  # hicbir sey kaybolmadi
    assert any("bitiyor. Cumle" in p for p in parcalar)  # cumleler boslukla birlesir
    with pytest.raises(ValueError):
        yl.parcala("x", 0)


async def test_token_say_ve_hatalari():
    llm = istemci(lambda r: httpx.Response(200, json={"tokens": [1, 2, 3]}))
    assert await llm.token_say("merhaba") == 3
    with pytest.raises(ModelCevapHatasi, match="400"):
        await istemci(lambda r: httpx.Response(400, text="kotu")).token_say("x")

    def kapali(r):
        raise httpx.ConnectError("yok", request=r)

    with pytest.raises(SunucuKapali):
        await istemci(kapali).token_say("x")


async def test_parca_parca_esle_ve_birlestir():
    istemler = []

    def isle(r):
        istemler.append(json.loads(r.content)["messages"][-1]["content"])
        return httpx.Response(200, json=cevap(f"OZET{len(istemler)}"))

    metin = "\n\n".join("P" * 90 for _ in range(3))
    assert await istemci(isle).parca_parca("", "Ozetle") == ""
    sonuc = await istemci(isle).parca_parca(metin, "Ozetle", max_karakter=100)
    assert sonuc == "OZET1\n\nOZET2\n\nOZET3" and len(istemler) == 3
    istemler.clear()
    adimlar = []
    sonuc = await istemci(isle).parca_parca(
        metin,
        "Ozetle",
        birlestir="Birlestir",
        max_karakter=100,
        ilerleme=lambda a, b: adimlar.append(a),
    )
    assert sonuc == "OZET4" and istemler[-1].startswith("Birlestir") and adimlar == [1, 2, 3]
    tek = []
    llm = istemci(lambda r: tek.append(1) or httpx.Response(200, json=cevap("TEK")))
    assert await llm.parca_parca("kisa", "Ozetle", birlestir="B") == "TEK" and len(tek) == 1


async def test_parca_parca_ozyineleme_ve_cok_uzun_hatasi():
    sayac = {"n": 0}

    def uzun_cevap(r):
        sayac["n"] += 1
        return httpx.Response(200, json=cevap("Y" * 60))  # ozetler kuculmuyor

    metin = "\n\n".join("P" * 90 for _ in range(4))
    with pytest.raises(ModelCevapHatasi, match="birlestirilemedi"):
        await istemci(uzun_cevap).parca_parca(metin, "Ozetle", birlestir="B", max_karakter=100)
    assert sayac["n"] > 4  # ozyineleme oldu


async def test_parca_parca_derin_seviyede_kucuk_parca(monkeypatch):
    gorulen = []
    monkeypatch.setattr(yl, "parcala", lambda m, k: gorulen.append(k) or [m])
    llm = istemci(lambda r: httpx.Response(200, json=cevap("ok")))
    await llm.parca_parca("x", "t")
    await llm.parca_parca("x", "t", dusunme="derin")
    llm.dusunme = "derin"
    await llm.parca_parca("x", "t")
    assert gorulen == [yl.MAX_PARCA_KARAKTER, yl.DERIN_PARCA_KARAKTER, yl.DERIN_PARCA_KARAKTER]


def _yasiyor(pid: int) -> bool:
    import ctypes

    k32 = ctypes.WinDLL("kernel32")
    h = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not h:
        return False
    try:
        return k32.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT: hala calisiyor
    finally:
        k32.CloseHandle(h)


def _bekle_olsun(pid: int, sn: float = 10.0) -> bool:
    bitis = time.time() + sn
    while time.time() < bitis:
        if not _yasiyor(pid):
            return True
        time.sleep(0.2)
    return False


UYKU = [sys.executable, "-c", "import time; time.sleep(60)"]
sadece_windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object")


@sadece_windows
def test_job_handle_kapaninca_surec_olur():
    cocuk = subprocess.Popen(UYKU)
    try:
        handle = yl.cokunce_kapanacak_yap(cocuk)
        assert handle and _yasiyor(cocuk.pid)
        yl._handle_kapat(handle)
        assert _bekle_olsun(cocuk.pid)
    finally:
        cocuk.kill()


@sadece_windows
def test_uygulama_cokerse_sunucu_da_kapanir(tmp_path):
    """Ebeveyn (uygulama) cocugu baslatir, Job'a baglar, kapat() demeden aniden olur."""
    betik = tmp_path / "ebeveyn.py"
    betik.write_text(
        "import os, subprocess, sys\n"
        f"sys.path.insert(0, {str(Path(yl.__file__).parent)!r})\n"
        "import yerel_llm\n"
        f"c = subprocess.Popen({UYKU!r})\n"
        "assert yerel_llm.cokunce_kapanacak_yap(c)\n"
        "print(c.pid, flush=True)\n"
        "os._exit(3)\n",
        encoding="utf-8",
    )
    cikti = subprocess.run([sys.executable, str(betik)], capture_output=True, text=True, timeout=60)
    assert cikti.returncode == 3, cikti.stderr
    assert _bekle_olsun(int(cikti.stdout.strip())), "uygulama oldu ama cocuk surec yasiyor"


def test_job_windows_disinda_none_ve_hata_guvenli(monkeypatch):
    monkeypatch.setattr(yl.sys, "platform", "linux")
    assert yl.cokunce_kapanacak_yap(object()) is None  # type: ignore[arg-type]
    monkeypatch.setattr(yl, "cokunce_kapanacak_yap", lambda s: 1 / 0)
    assert yl._job_bagla_guvenli(object()) is None  # type: ignore[arg-type]


@sadece_windows
async def test_hazirla_gercek_surecle_job_baglar_ve_kapatinca_birakir(tmp_path, monkeypatch):
    durum = {"n": 0}

    def isle(r):
        durum["n"] += 1
        return httpx.Response(200 if durum["n"] > 1 else 503, json={"status": "ok"})

    monkeypatch.setattr(YerelLLM, "_baslat_komutu", lambda self, p, goruntu: UYKU)
    monkeypatch.setattr(yl.asyncio, "sleep", lambda s: _hemen())
    llm = YerelLLM(dizin=tmp_path, transport=httpx.MockTransport(isle))
    await llm.hazirla(bekle_sn=5)
    pid = llm._surec.pid
    assert llm._is_nesnesi and _yasiyor(pid)
    await llm.kapat()
    assert llm._is_nesnesi is None and _bekle_olsun(pid)


async def test_gorsel_bellek_yetmezse_anlasilir_hata():
    govde = '{"error":{"code":500,"message":"failed to process mtmd chunk"}}'
    llm = istemci(lambda r: httpx.Response(500, text=govde))
    with pytest.raises(yl.BellekYetersiz, match="bellek yetmedi"):
        await llm.ocr(b"x")
    with pytest.raises(ModelCevapHatasi):  # BellekYetersiz bir ModelCevapHatasi'dir
        await llm.ocr(b"x")


# --- Coklu model ve ses -----------------------------------------------------------------
def test_model_profilleri_ve_baslat_komutu(tmp_path):
    assert set(yl.MODELLER) == {"deepseek-heretic", "gemma4-12b-heretic", "gemma4-e4b-heretic"}
    assert [s["deger"] for s in yl.MODEL_SECENEKLERI] == list(yl.MODELLER)
    (tmp_path / "llama.cpp").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "llama.cpp" / "llama-server.exe").write_bytes(b"")
    profil = yl.MODELLER["gemma4-12b-heretic"]
    llm = YerelLLM(dizin=tmp_path, model="gemma4-12b-heretic")
    with pytest.raises(SunucuBaslamadi, match="Model dosyasi bulunamadi"):
        llm._baslat_komutu(8080, goruntu=True)
    (tmp_path / "models" / profil.dosya).write_bytes(b"")
    (tmp_path / "models" / profil.mmproj).write_bytes(b"")
    komut = llm._baslat_komutu(8080, goruntu=True)
    assert profil.dosya in komut[2] and "gemma4-12b-heretic" in komut and profil.mmproj in komut[-1]
    with pytest.raises(SunucuBaslamadi, match="Bilinmeyen model"):
        YerelLLM(dizin=tmp_path, model="baska")._baslat_komutu(8080, goruntu=True)
    assert YerelLLM(model="baska").profil is None


def _sunucu(acik_model: str | None):
    def isle(r: httpx.Request):
        if r.url.path == "/v1/models":
            if acik_model is None:
                return httpx.Response(500)
            return httpx.Response(200, json={"data": [{"id": acik_model}]})
        return httpx.Response(200, json={"status": "ok"})

    return isle


async def test_hazirla_baska_model_acikken_dokunmaz_hata_verir():
    llm = YerelLLM(
        model="gemma4-e4b-heretic", transport=httpx.MockTransport(_sunucu("deepseek-heretic"))
    )
    with pytest.raises(yl.FarkliModelAcik, match="deepseek-heretic"):
        await llm.hazirla()
    ayni = YerelLLM(
        model="deepseek-heretic", transport=httpx.MockTransport(_sunucu("deepseek-heretic"))
    )
    await ayni.hazirla()  # dogru model acik: kullanilir
    okunamaz = YerelLLM(model="gemma4-e4b-heretic", transport=httpx.MockTransport(_sunucu(None)))
    await okunamaz.hazirla()  # model listesi okunamiyorsa dogrulanamaz, kabul edilir


async def test_hazirla_kendi_sunucumuzda_model_degisince_yeniden_baslatir(tmp_path, sahte_baslat):
    durum = {"acik": "deepseek-heretic", "saglik": True}

    def isle(r: httpx.Request):
        if r.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": durum["acik"]}]})
        return httpx.Response(200 if durum["saglik"] else 503, json={"status": "ok"})

    llm = YerelLLM(dizin=tmp_path, model="gemma4-e4b-heretic", transport=httpx.MockTransport(isle))
    eski = sahte_baslat()
    llm._surec = eski  # onceki model bizim baslattigimiz

    orijinal_terminate = eski.terminate

    def kapat_ve_degistir():
        orijinal_terminate()
        durum["saglik"] = False  # eski sunucu kapandi

    eski.terminate = kapat_ve_degistir
    sayac_once = sahte_baslat.sayac

    async def yeni_hazir(self, bekle_sn):
        durum.update(acik="gemma4-e4b-heretic", saglik=True)

    import yerel_llm

    yerel_llm.YerelLLM._hazir_bekle, eski_bekle = yeni_hazir, yerel_llm.YerelLLM._hazir_bekle
    try:
        await llm.hazirla()
    finally:
        yerel_llm.YerelLLM._hazir_bekle = eski_bekle
    assert eski.durdu and sahte_baslat.sayac == sayac_once + 1
    await llm.kapat()


async def test_ses_govdesi_bicim_ve_hatalar(tmp_path):
    gorulen = {}

    def isle(r):
        gorulen.update(json.loads(r.content))
        return httpx.Response(200, json=cevap("Toplam bin iki yuz"))

    llm = istemci(isle)
    assert await llm.ses(b"RIFF....WAVE") == "Toplam bin iki yuz"
    parca = gorulen["messages"][0]["content"][1]
    assert parca["type"] == "input_audio" and parca["input_audio"]["format"] == "wav"
    assert base64.b64decode(parca["input_audio"]["data"]) == b"RIFF....WAVE"
    mp3 = tmp_path / "kayit.MP3"
    mp3.write_bytes(b"ID3")
    await llm.ses(mp3, "Ozetle")
    assert gorulen["messages"][0]["content"][1]["input_audio"]["format"] == "mp3"
    with pytest.raises(yl.YerelLLMHatasi, match="Desteklenmeyen ses"):
        await llm.ses(b"x", bicim="ogg")
    hatali = istemci(lambda r: httpx.Response(500, text="audio input is not supported"))
    with pytest.raises(yl.SesDesteklenmiyor):
        await hatali.ses(b"x")


async def test_zamanlama_sohbet_ve_akista_saklanir():
    govde = cevap("ok")
    govde["timings"] = {"predicted_per_second": 6.1, "prompt_per_second": 40.0}
    llm = istemci(lambda r: httpx.Response(200, json=govde))
    await llm.metin("?")
    assert llm.son_zamanlama["predicted_per_second"] == 6.1
    sse = (
        'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"timings":{"predicted_n":3}}\n\n'
        "data: [DONE]\n\n"
    )
    llm = istemci(lambda r: httpx.Response(200, text=sse))
    _ = [p async for p in llm.akis([])]
    assert llm.son_zamanlama == {"predicted_n": 3}
