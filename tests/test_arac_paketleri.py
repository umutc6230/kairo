"""Arac paketleri (REA, Craft Anything) ve buyuk MCP sunuculari icin gecit (ara/sema/cagir).

Kurulumlar SAHTE npm/indirme ile denenir: testler aga cikmaz, gercek paket kurmaz."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

from app.agent import mcp as mcp_modulu
from app.agent.mcp import McpYoneticisi, arac_ara
from app.exceptions import Bulunamadi, OnayGerekli, UygulamaHatasi
from app.services import arac_paketleri as ap
from app.services.arac_paketleri import ISARET, PAKETLER, AracPaketleri, guvenli_ac

SUNUCU = str(Path(__file__).parent / "mcp_test_sunucusu.py")
REA = PAKETLER["rea"]


# ------------------------------------------------------------------ gecit (tembel MCP)


@pytest.fixture
def yon(tmp_path):
    y = McpYoneticisi(tmp_path)
    y.ekle({"ad": "buyuk", "komut": sys.executable, "argumanlar": ["-I", SUNUCU],
            "izinli_araclar": ["selam"], "tembel": True})  # fmt: skip
    yield y
    y.kapat()


def test_tembel_sunucu_uc_gecit_araci_sunar(yon) -> None:
    semalar, isl = yon.semalar_ve_isleyiciler(lambda *_a: None)
    adlar = {s["function"]["name"] for s in semalar}
    assert adlar == {"mcp__buyuk__arac_ara", "mcp__buyuk__arac_sema", "mcp__buyuk__arac_cagir"}
    assert set(isl) == adlar  # gercek araclar modele TEK TEK verilmez

    bulunan = isl["mcp__buyuk__arac_ara"](sorgu="selam")
    assert bulunan["araclar"][0]["arac"] == "selam" and bulunan["toplam"] >= 1
    sema = isl["mcp__buyuk__arac_sema"](arac="selam")
    assert sema["arac"] == "selam" and "sema" in sema
    assert isl["mcp__buyuk__arac_cagir"](arac="selam", argumanlar={"ad": "Umut"})["metin"] == (
        "Merhaba Umut"
    )


def test_gecit_cagrisi_gercek_arac_adiyla_izin_motorundan_gecer(yon) -> None:
    gorulen: list[tuple] = []

    def izin(ad, oku, ozet, kw):
        gorulen.append((ad, oku, kw))
        if not oku:
            raise OnayGerekli("onay", {"id": "o1"})

    _, isl = yon.semalar_ve_isleyiciler(izin)
    assert "metin" in isl["mcp__buyuk__arac_cagir"](arac="selam", argumanlar={"ad": "A"})
    r = isl["mcp__buyuk__arac_cagir"](arac="coz", argumanlar={})
    assert r["karar"] == "onay_bekliyor"  # izinli isaretlenmemis arac onay ister
    assert [g[:2] for g in gorulen] == [("mcp__buyuk__selam", True), ("mcp__buyuk__coz", False)]
    # ara/sema yalniz yerel listeyi okur: izin motoruna gitmez
    isl["mcp__buyuk__arac_ara"](sorgu="x")
    isl["mcp__buyuk__arac_sema"](arac="selam")
    assert len(gorulen) == 2


def test_gecit_bilinmeyen_arac_ve_bozuk_arguman(yon) -> None:
    _, isl = yon.semalar_ve_isleyiciler(lambda *_a: None)
    assert "arac_ara" in isl["mcp__buyuk__arac_cagir"](arac="yok_boyle")["hata"]
    assert isl["mcp__buyuk__arac_sema"](arac="")["karar"] == "hata"
    # argumanlar nesne degilse bos nesne sayilir (model dize gonderebilir)
    assert "metin" in isl["mcp__buyuk__arac_cagir"](arac="selam", argumanlar="bozuk")


def test_semalar_buyukse_kendiliginden_gecit(tmp_path, monkeypatch) -> None:
    y = McpYoneticisi(tmp_path)
    y.ekle({"ad": "t", "komut": sys.executable, "argumanlar": ["-I", SUNUCU]})
    try:
        normal, _ = y.semalar_ve_isleyiciler(lambda *_a: None)
        assert "mcp__t__selam" in {s["function"]["name"] for s in normal}
        monkeypatch.setattr(mcp_modulu, "TEMBEL_ESIK", 0)
        gecit, _ = y.semalar_ve_isleyiciler(lambda *_a: None)
        assert {s["function"]["name"] for s in gecit} == {
            "mcp__t__arac_ara", "mcp__t__arac_sema", "mcp__t__arac_cagir",
        }  # fmt: skip
        assert y.test("t")["tembel"] is True
    finally:
        y.kapat()


def test_arac_ara_puanlama_ve_dev_sema_kisaltma(tmp_path, monkeypatch) -> None:
    araclar = [
        {"name": "list_strings", "description": "List strings of the binary"},
        {"name": "open_binary", "description": "Open a native binary", "inputSchema": {
            "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        {"name": "decompile", "description": "Decompile a function of the open binary"},
    ]  # fmt: skip
    sonuc = arac_ara(araclar, "open binary")
    assert sonuc[0]["arac"] == "open_binary" and sonuc[0]["zorunlu"] == ["path"]
    assert [x["arac"] for x in arac_ara(araclar, "zzz")] == []
    assert len(arac_ara(araclar, "", limit=2)) == 2  # bos sorgu: ilk araclar

    y = McpYoneticisi(tmp_path)
    y.ekle({"ad": "b", "komut": sys.executable, "argumanlar": ["-I", SUNUCU], "tembel": True})
    try:
        monkeypatch.setattr(mcp_modulu, "MAX_SEMA", 5)
        _, isl = y.semalar_ve_isleyiciler(lambda *_a: None)
        s = isl["mcp__b__arac_sema"](arac="selam")
        assert s["truncated"] is True and "parametreler" in s and len(s["sema_basi"]) == 5
    finally:
        y.kapat()


# ------------------------------------------------------------------ npm paketi (REA)


class SahteNpm:
    """`npm install`'i taklit eder: package-lock + paketin skill klasorunu yazar."""

    def __init__(self, butunluk: str = REA["butunluk"], node: str = "v24.18.0", kod: int = 0):
        self.butunluk, self.node, self.kod = butunluk, node, kod
        self.komutlar: list[list[str]] = []

    def __call__(self, komut: list[str], cwd: Path) -> tuple[int, str]:
        self.komutlar.append(komut)
        if komut[1:] == ["--version"]:
            return 0, self.node
        if self.kod:
            return self.kod, "npm ERR! ag yok"
        hedef = Path(komut[komut.index("--prefix") + 1])
        paket = hedef / "node_modules" / REA["paket"]
        skill = hedef / REA["skill"]
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: reverse-engineer-anything\n---\nREA", "utf-8")
        (skill / "references" / "a.md").write_text("ref", "utf-8")
        (paket / "scripts").mkdir(parents=True, exist_ok=True)
        (paket / "scripts" / "rea.mjs").write_text("// sahte", "utf-8")
        kilit = {"packages": {f"node_modules/{REA['paket']}": {
            "version": REA["surum"], "integrity": self.butunluk}}}  # fmt: skip
        (hedef / "package-lock.json").write_text(json.dumps(kilit), "utf-8")
        return 0, "added 144 packages"


def _paketler(tmp_path, npm, **kw) -> tuple[AracPaketleri, McpYoneticisi]:
    y = McpYoneticisi(tmp_path)
    return AracPaketleri(tmp_path, y, calistir=npm, bul=lambda ad: f"C:/sahte/{ad}", **kw), y


def test_rea_kurulur_baglayici_gecitle_skill_notlu(tmp_path) -> None:
    npm = SahteNpm()
    p, y = _paketler(tmp_path, npm)
    once = next(x for x in p.liste() if x["ad"] == "rea")
    assert once["kurulu"] is False and once["engel"] == ""

    sonuc = p.kur("rea")
    assert sonuc["kurulu"] and sonuc["baglayici"] and sonuc["skill"]
    kur = next(k for k in npm.komutlar if "install" in k)
    assert "--ignore-scripts" in kur and kur[-1] == "rea-agents@6.3.0"  # betik YOK, surum sabit
    s = y.liste()[0]
    assert s.ad == "rea" and s.tembel is True and s.komut == "C:/sahte/node"
    assert s.argumanlar[0].endswith("araclar/rea/node_modules/rea-agents/scripts/rea.mjs")
    assert s.argumanlar[1] == "mcp"
    skill = tmp_path / "skills" / "reverse-engineer-anything"
    metin = (skill / "SKILL.md").read_text("utf-8")
    assert "mcp__rea__arac_cagir" in metin and "CALISTIRMA" in metin  # setup/doctor calismaz
    assert (skill / ISARET).is_file() and (skill / "references" / "a.md").is_file()
    with pytest.raises(UygulamaHatasi, match="zaten kurulu"):
        p.kur("rea")

    assert p.kaldir("rea") == {"kaldirildi": "rea"}
    assert y.liste() == [] and not skill.exists() and not (tmp_path / "araclar" / "rea").exists()
    with pytest.raises(UygulamaHatasi, match="kurulu degil"):
        p.kaldir("rea")


def test_butunluk_uyusmazsa_kurulum_geri_alinir(tmp_path) -> None:
    p, y = _paketler(tmp_path, SahteNpm(butunluk="sha512-BASKA"))
    with pytest.raises(UygulamaHatasi, match="butunluk"):
        p.kur("rea")
    assert y.liste() == [] and not (tmp_path / "araclar" / "rea").exists()
    assert not (tmp_path / "skills" / "reverse-engineer-anything").exists()
    assert next(x for x in p.liste() if x["ad"] == "rea")["kurulu"] is False


def test_npm_hatasi_eski_node_ve_node_yok(tmp_path) -> None:
    p, _ = _paketler(tmp_path, SahteNpm(kod=1))
    with pytest.raises(UygulamaHatasi, match="npm kurulumu basarisiz"):
        p.kur("rea")
    eski, _ = _paketler(tmp_path / "a", SahteNpm(node="v20.11.1"))
    assert "22.19" in eski.engel("rea")
    with pytest.raises(UygulamaHatasi, match="22.19"):
        eski.kur("rea")
    yok = AracPaketleri(tmp_path / "b", McpYoneticisi(tmp_path / "b"), bul=lambda _ad: None)
    assert "Node.js" in yok.engel("rea")
    with pytest.raises(Bulunamadi):
        yok.kur("olmayan-paket")


def test_ayni_adli_baglayici_ve_kullanici_skilli_korunur(tmp_path) -> None:
    p, y = _paketler(tmp_path, SahteNpm())
    y.ekle({"ad": "rea", "komut": "node", "argumanlar": ["x"]})
    with pytest.raises(UygulamaHatasi, match="baglayici zaten var"):
        p.kur("rea")
    y.sil("rea")
    benim = tmp_path / "skills" / "reverse-engineer-anything"
    benim.mkdir(parents=True)
    (benim / "SKILL.md").write_text("BENIM", "utf-8")
    assert p.kur("rea")["skill"] is False  # kullanicinin skill'inin ustune yazilmaz
    assert (benim / "SKILL.md").read_text("utf-8") == "BENIM"
    p.kaldir("rea")
    assert (benim / "SKILL.md").read_text("utf-8") == "BENIM"  # kaldirirken de silinmez


# ------------------------------------------------------------------ zip paketi (Craft Anything)


def _zip(yol: Path, uyeler: dict[str, bytes]) -> str:
    with zipfile.ZipFile(yol, "w") as z:
        for ad, veri in uyeler.items():
            z.writestr(ad, veri)
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _craft(tmp_path, monkeypatch, uyeler, sha=None, platform="win32"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    kaynak = tmp_path / "kaynak.zip"
    gercek = _zip(kaynak, uyeler)
    monkeypatch.setitem(ap.PAKETLER, "craft-anything", {
        **PAKETLER["craft-anything"], "sha256": sha or gercek})  # fmt: skip
    indirilen: list[str] = []

    def indir(url: str, hedef: Path) -> None:
        indirilen.append(url)
        hedef.write_bytes(kaynak.read_bytes())

    y = McpYoneticisi(tmp_path / "veri")
    return AracPaketleri(tmp_path / "veri", y, indir=indir, platform=platform), y, indirilen


def test_zip_paketi_ozet_dogrulanir_ve_cli_kaydedilir(tmp_path, monkeypatch) -> None:
    p, y, indirilen = _craft(tmp_path, monkeypatch, {
        "craft-anything/craft-anything.exe": b"MZ-app",
        "craft-anything/craft-anything-cli.exe": b"MZ-cli"})  # fmt: skip
    sonuc = p.kur("craft-anything")
    assert sonuc["kurulu"] and sonuc["skill"] is False
    assert indirilen == [PAKETLER["craft-anything"]["url"]]  # adres YALNIZ tablodan
    s = y.liste()[0]
    assert s.komut.endswith("craft-anything/craft-anything-cli.exe")
    assert s.argumanlar == ["mcp", "--all-tools", "--deep"]
    assert "--allow-run" not in s.argumanlar  # kod calistiran araclar onaysiz acilmaz
    assert s.tembel is True
    assert not (tmp_path / "veri" / "araclar" / "craft-anything" / "indirilen.zip").exists()
    p.kaldir("craft-anything")
    assert y.liste() == []


def test_zip_ozet_uyusmazsa_acilmaz(tmp_path, monkeypatch) -> None:
    p, y, _ = _craft(tmp_path, monkeypatch, {"craft-anything-cli.exe": b"MZ"}, sha="0" * 64)
    with pytest.raises(UygulamaHatasi, match="SHA256"):
        p.kur("craft-anything")
    assert y.liste() == [] and not (tmp_path / "veri" / "araclar" / "craft-anything").exists()


def test_zip_cli_yoksa_ve_baska_platformda_kurulmaz(tmp_path, monkeypatch) -> None:
    p, y, _ = _craft(tmp_path, monkeypatch, {"craft-anything.exe": b"MZ"})
    with pytest.raises(UygulamaHatasi, match="bulunamadi"):
        p.kur("craft-anything")
    assert y.liste() == []
    linux, _, indirilen = _craft(tmp_path / "l", monkeypatch, {"x": b"1"}, platform="linux")
    assert "Windows" in linux.engel("craft-anything")
    with pytest.raises(UygulamaHatasi, match="Windows"):
        linux.kur("craft-anything")
    assert indirilen == []  # engel varken hicbir sey indirilmez


def test_guvenli_ac_klasor_disina_yazan_arsivi_reddeder(tmp_path) -> None:
    kotu = tmp_path / "kotu.zip"
    _zip(kotu, {"../disari.txt": b"x", "iceri.txt": b"y"})
    hedef = tmp_path / "hedef"
    hedef.mkdir()
    with pytest.raises(UygulamaHatasi, match="disina"):
        guvenli_ac(kotu, hedef)
    assert not (tmp_path / "disari.txt").exists() and not (hedef / "iceri.txt").exists()

    link = tmp_path / "link.zip"
    with zipfile.ZipFile(link, "w") as z:
        bilgi = zipfile.ZipInfo("baglanti")
        bilgi.external_attr = 0o120777 << 16
        z.writestr(bilgi, "C:/Windows")
    with pytest.raises(UygulamaHatasi, match="sembolik"):
        guvenli_ac(link, hedef)


# ------------------------------------------------------------------ API


async def test_api_liste_kur_kaldir(app, istemci, veri) -> None:
    app.state.arac_paketleri.calistir = SahteNpm()
    app.state.arac_paketleri.bul = lambda ad: f"C:/sahte/{ad}"
    r = await istemci.get("/api/arac-paketleri")
    assert r.status_code == 200
    assert {p["ad"] for p in r.json()["paketler"]} == {"rea", "craft-anything"}

    # istek govdesi adres/surum degistiremez: uc govde almaz, tablo sabittir
    r = await istemci.post("/api/arac-paketleri/rea/kur", json={"surum": "0.0.1", "url": "x"})
    assert r.status_code == 200 and r.json()["kurulu_surum"] == "6.3.0"
    mcp = (await istemci.get("/api/mcp")).json()["sunucular"]
    assert [(s["ad"], s["tembel"]) for s in mcp] == [("rea", True)]
    assert (await istemci.post("/api/arac-paketleri/yok/kur")).status_code == 404
    assert (await istemci.delete("/api/arac-paketleri/rea")).json() == {"kaldirildi": "rea"}
    assert (await istemci.get("/api/mcp")).json()["sunucular"] == []
