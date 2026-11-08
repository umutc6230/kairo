"""Servis birim testleri: araclar, depolar, sohbet yardimcilari, sistem, config, main."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from app import config
from app.main import PencereApi, arg_ayristir, bos_port, pencere_boyutu
from app.services import araclar, sistem
from app.services.ayarlar import AyarDeposu
from app.services.depo import json_oku, json_yaz
from app.services.ekler import EkDeposu, tur_bul
from app.services.oturumlar import Mesaj, OturumDeposu, baslik_uret
from app.services.sohbet import gecmis, kuyruktan_akit
from app.services.testler import bellek_uyarisi, benzerlik


# ---- araclar ----
def test_hesapla_guvenli():
    assert araclar.hesapla("1250*41,2")["sonuc"] == 51500
    assert araclar.hesapla("2 x 3")["sonuc"] == 6
    assert araclar.hesapla("-(2+3)**2 % 7")["sonuc"] == 3
    assert "hata" in araclar.hesapla("__import__('os')")
    assert "hata" in araclar.hesapla("1/0")
    assert "hata" in araclar.hesapla("2**1000")
    assert "hata" in araclar.hesapla("1 +")


def test_diger_araclar():
    assert araclar.kur_getir(" usd ")["tl_karsiligi"] == 41.2
    assert "hata" in araclar.kur_getir("XYZ")
    assert araclar.hava_durumu("İstanbul")["derece_c"] == 18
    assert araclar.hava_durumu("Kars")["durum"].startswith("bilinmiyor")
    assert set(araclar.saat_kac()) == {"tarih", "saat", "gun"}
    assert araclar.birim_cevir(10, "km", "mil")["sonuc"] == 6.2137
    assert araclar.birim_cevir(30, "C", "F")["sonuc"] == 86
    assert araclar.birim_cevir(86, "f", "c")["sonuc"] == 30
    assert "hata" in araclar.birim_cevir(1, "km", "kg")
    assert set(araclar.ISLEYICILER) == {a["function"]["name"] for a in araclar.ARACLAR}


# ---- depolar ----
def test_json_atomik_ve_bozuk(tmp_path):
    yol = tmp_path / "a" / "b.json"
    json_yaz(yol, {"x": "ç"})
    assert json_oku(yol) == {"x": "ç"} and not list(yol.parent.glob("*.tmp"))
    yol.write_text("{bozuk", encoding="utf-8")
    assert json_oku(yol, "vars") == "vars"
    assert json_oku(tmp_path / "yok.json", 1) == 1


def test_ayar_deposu_bozuk_alan_kurtarilir(tmp_path):
    depo = AyarDeposu(tmp_path)
    json_yaz(depo.yol, {"model": "silinmis-model", "dusunme": "dengeli", "max_tokens": 9})
    a = depo.oku()
    assert a.model == "deepseek-heretic" and a.dusunme == "dengeli" and a.max_tokens == 1024
    assert depo.guncelle({"adres": "http://localhost:9000"}).adres == "http://localhost:9000/v1"
    with pytest.raises(ValueError):
        depo.guncelle({"dusunme": "cok"})


def test_oturum_deposu_ve_baslik(tmp_path):
    depo = OturumDeposu(tmp_path)
    o = depo.olustur()
    o.mesajlar.append(Mesaj(rol="kullanici", metin="gizli kelime"))
    depo.kaydet(o)
    (depo.dizin / "bozuk.json").write_text("{", encoding="utf-8")
    assert [x["id"] for x in depo.liste("GIZLI")] == [o.id]
    assert depo.yeniden_adlandir(o.id, "   ").baslik == "Yeni sohbet"
    assert baslik_uret("  a\n b ") == "a b" and baslik_uret("") == "Yeni sohbet"
    assert baslik_uret("x" * 60).endswith("...")


def test_ek_deposu(tmp_path):
    depo = EkDeposu(tmp_path)
    assert tur_bul("A.JPG") == ("resim", ".jpg") and tur_bul("k.mp3") == ("ses", ".mp3")
    from app.exceptions import GecersizEk

    with pytest.raises(GecersizEk):
        depo.kaydet("b.png", b"x" * (50 * 1024 * 1024 + 1))
    ek = depo.kaydet("not.md", "çay".encode())
    assert depo.getir(ek.id).metin == "çay"
    assert depo.metin_kaydet(ek, "yeni").metin == "yeni" and depo.getir(ek.id).metin == "yeni"


# ---- sohbet yardimcilari ----
def test_gecmis_sinir_ve_ekler():
    mesajlar = [
        Mesaj(rol="kullanici", metin="a" * 50, ekler=[{"id": "1", "ad": "r.png", "tur": "resim"}]),
        Mesaj(rol="asistan", metin="", hata="Durduruldu."),
        Mesaj(rol="asistan", metin="b" * 50),
        Mesaj(rol="kullanici", metin="c" * 50),
    ]
    g = gecmis(mesajlar, sinir=120)
    assert [m["role"] for m in g] == ["assistant", "user"]  # en eski sigmadi, hatali atlandi
    g = gecmis(mesajlar)
    assert g[0]["content"].startswith("[Ek: r.png]\n")


async def test_kuyruktan_akit_iptalde_gorevi_durdurur():
    durdu = asyncio.Event()

    async def uret(gonder):
        gonder({"tur": "a"})
        try:
            await asyncio.sleep(10)
        finally:
            durdu.set()

    akis = kuyruktan_akit(uret)
    assert await akis.__anext__() == {"tur": "a"}
    await akis.aclose()
    assert durdu.is_set()


async def test_kuyruktan_akit_sonuc_ve_hata():
    async def iyi(gonder):
        gonder({"tur": "x"})
        return 5

    assert [o async for o in kuyruktan_akit(iyi)] == [{"tur": "x"}, ("sonuc", 5)]

    async def kotu(gonder):
        raise ValueError("bozuk")

    with pytest.raises(ValueError):
        _ = [o async for o in kuyruktan_akit(kotu)]


def test_benzerlik_ve_bellek_uyarisi(monkeypatch):
    assert benzerlik("a\nb", "b\na") == 100.0
    assert benzerlik("", "x") == 0.0
    assert 0 < benzerlik("Toplam: 100", "Toplam: 10O") < 100
    monkeypatch.setattr(sistem, "bellek", lambda: {"bos_gb": 2.0})
    assert "Bos RAM 2.0" in bellek_uyarisi("gemma4-12b-heretic")
    monkeypatch.setattr(sistem, "bellek", lambda: {"bos_gb": 64.0})
    assert bellek_uyarisi("gemma4-12b-heretic") == ""


# ---- sistem / config / main ----
def test_sistem_bellek_ve_dosyalar(tmp_path, monkeypatch):
    b = sistem.bellek()
    if sys.platform == "win32":
        assert b["toplam_gb"] > 0 and b["bos_gb"] >= 0
    assert all(not v["dosya_var"] for v in sistem.model_dosyalari(tmp_path).values())
    assert sistem.motor_var(tmp_path) is False
    monkeypatch.setattr(sistem.sys, "platform", "linux")
    assert sistem.bellek() == {"bos_gb": None, "toplam_gb": None}
    assert sistem.llama_server_durdur() is False


def test_config_veri_dizini_portable(tmp_path, monkeypatch):
    hedef = tmp_path / "ozel"
    assert config.veri_dizini(config.OrtamAyarlari(veri_dizini=hedef)) == hedef and hedef.exists()
    exe = tmp_path / "Portable" / "YerelAIStudio.exe"
    exe.parent.mkdir()
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(exe))
    assert config.veri_dizini(config.OrtamAyarlari()) == exe.parent / "data"  # AppData degil
    monkeypatch.delattr(config.sys, "frozen")
    assert config.veri_dizini(config.OrtamAyarlari()) == config.PROJE_KOKU / "data"
    assert (config.web_dizini() / "index.html").exists()


def test_varsayilan_llm_dizini_aday_sirasi(tmp_path, monkeypatch):
    monkeypatch.setenv("YEREL_LLM_DIZIN", str(tmp_path / "env"))
    assert config.varsayilan_llm_dizini() == tmp_path / "env"
    monkeypatch.delenv("YEREL_LLM_DIZIN")
    kok = tmp_path / "Portable" / "YerelAIStudio"
    kok.mkdir(parents=True)
    monkeypatch.setattr(config, "uygulama_klasoru", lambda: kok)
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path / "ev"))
    assert config.varsayilan_llm_dizini() == tmp_path / "ev" / "Projects" / "llm"  # hicbiri yok
    yan = kok.parent / "llm" / "llama.cpp"
    yan.mkdir(parents=True)
    (yan / "llama-server.exe").write_bytes(b"")
    assert config.varsayilan_llm_dizini() == kok.parent / "llm"


def test_main_argumanlar_ve_pencere(capsys):
    with pytest.raises(SystemExit):
        arg_ayristir(["--version"])
    cikti = capsys.readouterr().out
    assert "Umut" in cikti and "github.com/umutc6230" in cikti
    assert arg_ayristir(["--tarayici", "--port", "9"]).port == 9
    assert 0 < bos_port() < 65536

    class SahtePencere:
        def __init__(self):
            self.cagri = []

        def __getattr__(self, ad):
            return lambda: self.cagri.append(ad)

    api = PencereApi()
    api._pencere = SahtePencere()
    api.kucult()
    assert api.buyut() is True and api.buyut() is False
    api.kapat()
    assert api._pencere.cagri == ["minimize", "maximize", "restore", "destroy"]


def test_web_dosyalari_native_dialog_kullanmaz():
    web = Path(config.web_dizini())
    for js in web.glob("*.js"):
        metin = js.read_text(encoding="utf-8")
        for yasak in ("alert(", "confirm(", "prompt("):
            assert f"window.{yasak}" not in metin and f" {yasak}" not in metin, (js.name, yasak)


def test_pencere_boyutu_ekrana_sigar():
    class E:
        width, height = 1664, 944

    assert pencere_boyutu([E()]) == (1440, 830)
    assert pencere_boyutu([]) == (1280, 820)


async def test_durdur_kilidi_beklemez(tmp_path):
    """Model yuklenirken (kilit tutulurken) durdur hemen calismali."""
    import asyncio

    from app.services.model_yonetici import ModelYonetici

    class SahteLLM:
        def __init__(self, **kw):
            self.durduruldu = asyncio.Event()
            self.dusunme = "kapali"
            self.model = ""

        async def saglikli(self):
            return False

        async def hazirla(self, **kw):
            await self.durduruldu.wait()  # surec durdurulana kadar "yukleniyor"
            raise RuntimeError("surec kapandi")

        async def _sureci_durdur(self):
            self.durduruldu.set()

        async def kapat(self):
            pass

    y = ModelYonetici(AyarDeposu(tmp_path), SahteLLM)
    yukleme = asyncio.create_task(y.hazirla("deepseek-heretic"))
    await asyncio.sleep(0.05)
    assert y.mesgul
    sonuc = await asyncio.wait_for(y.durdur(), timeout=1)
    assert sonuc == {"harici_kapatildi": False} and y.durum == "kapali"
    with pytest.raises(RuntimeError):
        await yukleme
