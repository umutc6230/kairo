"""Model magazasi: arama, uyumluluk, indirme (devam, SHA256), kayit, silme. Ag yok (sahte HF)."""

from __future__ import annotations

import asyncio
import hashlib
import struct

import httpx
import pytest

from app.services import model_magaza as mm
from app.services.yerel_llm import MODELLER

MODEL_VERI = b"GGUF" + b"m" * 5000
MMPROJ_VERI = b"GGUF" + b"p" * 300


def mmproj_ses(ses: bool) -> bytes:
    anahtar = b"clip.has_audio_encoder"
    return (
        b"GGUF"
        + struct.pack("<IQQ", 3, 0, 1)
        + struct.pack("<Q", len(anahtar))
        + anahtar
        + struct.pack("<I", 7)
        + (b"\x01" if ses else b"\x00")
    )


class SahteHF:
    def __init__(self, mmproj: bytes = MMPROJ_VERI) -> None:
        self.dosyalar = {
            "org/Ornek-9B-heretic-GGUF": {
                "Ornek-9B-heretic.Q4_K_M.gguf": MODEL_VERI,
                "Ornek-9B-heretic.Q8_0.gguf": b"x",
                "Ornek-9B-heretic.mmproj-f16.gguf": b"big",
                "Ornek-9B-heretic.mmproj-Q8_0.gguf": mmproj,
            },
            "org/Ornek-9B-heretic-i1-GGUF": {"Ornek-9B-heretic.i1-Q4_K_M.gguf": MODEL_VERI},
        }
        self.dosyalar["org/Ornek-9B-heretic-GGUF-static"] = {}
        self.bozuk_sha = False
        self.range_istekleri: list[str] = []

    def __call__(self, r: httpx.Request) -> httpx.Response:
        yol = r.url.path
        if yol == "/api/models":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": repo,
                        "downloads": 100 - i,
                        "likes": 5,
                        "lastModified": "2026-10-01T00:00:00Z",
                        "pipeline_tag": "image-text-to-text",
                        "gguf": {
                            "total": 9_000_000_000,
                            "architecture": "qwen35",
                            "chat_template": "tools",
                        },
                        "siblings": [{"rfilename": d} for d in dosyalar],
                    }
                    for i, (repo, dosyalar) in enumerate(self.dosyalar.items())
                ]
                + [{"id": "org/bos", "siblings": [{"rfilename": "README.md"}]}],
            )
        if yol.startswith("/api/models/"):
            repo = yol.removeprefix("/api/models/")
            return httpx.Response(
                200,
                json={
                    "siblings": [
                        {
                            "rfilename": ad,
                            "size": len(v),
                            "lfs": {
                                "sha256": "0" * 64
                                if self.bozuk_sha
                                else hashlib.sha256(v).hexdigest()
                            },
                        }
                        for ad, v in self.dosyalar.get(repo, {}).items()
                    ]
                },
            )
        repo, _, ad = yol.lstrip("/").partition("/resolve/main/")
        veri = self.dosyalar[repo][ad]
        if rng := r.headers.get("Range"):
            self.range_istekleri.append(rng)
            bas = int(rng.removeprefix("bytes=").rstrip("-"))
            return httpx.Response(206, content=veri[bas:])
        return httpx.Response(200, content=veri)


@pytest.fixture
def hf():
    return SahteHF()


@pytest.fixture
def ortam(tmp_path, hf):
    klasor = tmp_path / "llm"
    (klasor / "models").mkdir(parents=True)
    magaza = mm.Magaza(httpx.AsyncClient(transport=httpx.MockTransport(hf)))
    kayit = mm.ModelKaydi(tmp_path / "veri")
    (tmp_path / "veri").mkdir()
    yield magaza, kayit, mm.Indirici(magaza, kayit, lambda: klasor), klasor
    for p in kayit.oku():
        MODELLER.pop(p["anahtar"], None)


def test_dosya_sec_tercih_sirasi():
    m, p = mm.dosya_sec(
        [
            "a.Q8_0.gguf",
            "a.Q4_K_M.gguf",
            "a-MTP-Q4_K_M.gguf",
            "a.mmproj-BF16.gguf",
            "a.mmproj-Q8_0.gguf",
            "x/b.Q4_K_M.gguf",
        ]
    )
    assert (m, p) == ("a.Q4_K_M.gguf", "a.mmproj-Q8_0.gguf")
    assert mm.dosya_sec(["a.i1-Q4_K_M.gguf", "a.i1-IQ4_XS.gguf"]) == ("a.i1-Q4_K_M.gguf", None)
    assert mm.dosya_sec(["a.Q8_0.gguf", "README.md"]) == (None, None)
    assert mm.dosya_sec(["a.Q4_0.gguf", "mmproj-model.gguf"])[1] == "mmproj-model.gguf"


def test_uyumluluk_kademeleri():
    b = {"toplam_gb": 15.3, "bos_gb": 7.0}
    assert mm.uyumluluk(5.4, b, 50)["durum"] == "calisir"
    z = mm.uyumluluk(10.0, b, 50)
    assert z["durum"] == "zorlanir" and z["simdi_acilir"] is False
    assert mm.uyumluluk(17.4, b, 50)["durum"] == "calismaz"
    d = mm.uyumluluk(5.4, b, 6)
    assert d["disk_yetmez"] and "Diskte 6" in d["neden"]
    assert mm.uyumluluk(None, b, 1)["durum"] == "bilinmiyor"
    assert mm.tahmini_boyut_gb(None, True) is None
    assert mm.tahmini_boyut_gb(9_000_000_000, True) == 6.3


async def test_arama_ve_onbellek(ortam, hf):
    magaza, *_ = ortam
    s = await magaza.ara("heretic")
    assert [a["repo"] for a in s] == ["org/Ornek-9B-heretic-GGUF", "org/Ornek-9B-heretic-i1-GGUF"]
    a = s[0]
    assert a["model_dosyasi"] == "Ornek-9B-heretic.Q4_K_M.gguf" and a["arac"] and a["gorsel"]
    assert a["parametre_milyar"] == 9.0 and a["tahmini_gb"] == 6.3
    hf.dosyalar.clear()  # onbellekten gelmeli
    assert await magaza.ara("Heretic ") == s


async def test_arama_ag_hatasi():
    def kapali(r):
        raise httpx.ConnectError("yok", request=r)

    magaza = mm.Magaza(httpx.AsyncClient(transport=httpx.MockTransport(kapali)))
    with pytest.raises(mm.UygulamaHatasi, match="Hugging Face"):
        await magaza.ara("x")
    with pytest.raises(mm.UygulamaHatasi, match="Model bilgisi"):
        await magaza.dosya_bilgileri("a/b")


async def bekle(indirme, *durumlar):
    for _ in range(300):
        if indirme.durum in durumlar:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(indirme.durum)


async def test_indir_dogrula_kaydet_sil(ortam, hf):
    magaza, kayit, indirici, klasor = ortam
    hf.dosyalar["org/Ornek-9B-heretic-GGUF"]["Ornek-9B-heretic.mmproj-Q8_0.gguf"] = mmproj_ses(True)
    i = await indirici.baslat("org/Ornek-9B-heretic-GGUF")
    assert [d["ad"] for d in i.dosyalar] == [
        "Ornek-9B-heretic.Q4_K_M.gguf",
        "Ornek-9B-heretic.mmproj-Q8_0.gguf",
    ]
    await bekle(i, "bitti", "hata")
    assert i.durum == "bitti" and i.ozet()["yuzde"] == 100
    assert (klasor / "models" / "Ornek-9B-heretic.Q4_K_M.gguf").read_bytes() == MODEL_VERI
    p = MODELLER["ornek-9b-heretic"]
    assert p.ses is True and p.mmproj == "Ornek-9B-heretic.mmproj-Q8_0.gguf"
    assert kayit.kaynak("ornek-9b-heretic") == "org/Ornek-9B-heretic-GGUF"
    with pytest.raises(mm.UygulamaHatasi, match="zaten indiriliyor"):
        indirici.indirmeler[i.id].durum = "iniyor"
        await indirici.baslat("org/Ornek-9B-heretic-GGUF")
    indirici.indirmeler[i.id].durum = "bitti"
    # yeni surec: kayit yeniden yuklenince model geri gelir
    MODELLER.pop("ornek-9b-heretic")
    mm.ModelKaydi(kayit.yol.parent).yukle()
    assert "ornek-9b-heretic" in MODELLER
    parca = klasor / "_indirme" / f"{p.dosya}.part"  # yarim kalmis eski indirme de gider
    parca.write_bytes(b"x")
    assert indirici.sil("ornek-9b-heretic")["silindi"] == [p.dosya, f"{p.dosya}.part", p.mmproj]
    assert not parca.exists() and not (klasor / "models" / p.dosya).exists()
    assert "ornek-9b-heretic" not in MODELLER and kayit.oku() == []
    with pytest.raises(mm.Bulunamadi):
        indirici.sil("yok")


async def test_indir_kaldigi_yerden_devam(ortam, hf):
    _, _, indirici, klasor = ortam
    gecici = klasor / "_indirme"
    gecici.mkdir()
    (gecici / "Ornek-9B-heretic.Q4_K_M.gguf.part").write_bytes(MODEL_VERI[:1000])
    i = await indirici.baslat("org/Ornek-9B-heretic-GGUF")
    await bekle(i, "bitti", "hata")
    assert i.durum == "bitti" and hf.range_istekleri == ["bytes=1000-"]
    assert (klasor / "models" / "Ornek-9B-heretic.Q4_K_M.gguf").read_bytes() == MODEL_VERI


async def test_sha_uyusmazsa_silinir(ortam, hf):
    _, _, indirici, klasor = ortam
    hf.bozuk_sha = True
    i = await indirici.baslat("org/Ornek-9B-heretic-GGUF")
    await bekle(i, "hata", "bitti")
    assert i.durum == "hata" and "SHA256" in i.hata
    assert not (klasor / "models" / "Ornek-9B-heretic.Q4_K_M.gguf").exists()
    assert not (klasor / "_indirme" / "Ornek-9B-heretic.Q4_K_M.gguf.part").exists()


async def test_i1_deposu_mmproj_statik_depodan(ortam, hf):
    _, _, indirici, _ = ortam
    i = await indirici.baslat("org/Ornek-9B-heretic-i1-GGUF")
    assert i.dosyalar[1]["repo"] == "org/Ornek-9B-heretic-GGUF"
    await bekle(i, "bitti", "hata")
    assert i.durum == "bitti" and MODELLER["ornek-9b-heretic-i1"].ses is False


async def test_disk_yetmez_ve_uygun_dosya_yok(ortam, hf, monkeypatch):
    _, _, indirici, _ = ortam
    monkeypatch.setattr(indirici, "disk_bos_gb", lambda: 1.0)
    with pytest.raises(mm.UygulamaHatasi, match="Diskte yer yok"):
        await indirici.baslat("org/Ornek-9B-heretic-GGUF")
    hf.dosyalar["org/sadece-q8"] = {"a.Q8_0.gguf": b"x"}
    with pytest.raises(mm.UygulamaHatasi, match="4-bit"):
        await indirici.baslat("org/sadece-q8")


async def test_iptal(ortam, hf):
    _, _, indirici, _ = ortam
    olay = asyncio.Event()

    async def yavas(*a, **k):
        await olay.wait()

    indirici._dosya_indir = yavas
    i = await indirici.baslat("org/Ornek-9B-heretic-GGUF")
    await asyncio.sleep(0.02)
    indirici.iptal(i.id)
    await bekle(i, "iptal")
    with pytest.raises(mm.Bulunamadi):
        indirici.iptal("yok")


def test_anahtar_ve_ses_okuma(tmp_path):
    assert mm.anahtar_uret("org/Gemma-4-E4B_it heretic-GGUF") == "gemma-4-e4b-it-heretic"
    assert mm.anahtar_uret("org/---") == "model"
    yol = tmp_path / "m.gguf"
    yol.write_bytes(mmproj_ses(True))
    assert mm.gguf_ses_var(yol) is True
    yol.write_bytes(mmproj_ses(False))
    assert mm.gguf_ses_var(yol) is False
    yol.write_bytes(b"degil")
    assert mm.gguf_ses_var(yol) is False
    assert mm.gguf_ses_var(tmp_path / "yok.gguf") is False


async def test_magaza_api(istemci, monkeypatch):
    from app.services import sistem

    monkeypatch.setattr(sistem, "bellek", lambda: {"toplam_gb": 15.3, "bos_gb": 8.0})
    yuklu = (await istemci.get("/api/magaza/yuklu")).json()
    assert {m["anahtar"] for m in yuklu["modeller"]} >= {"deepseek-heretic", "gemma4-e4b-heretic"}
    assert yuklu["sistem"]["toplam_ram_gb"] == 15.3 and all(
        m["yerlesik"] for m in yuklu["modeller"]
    )
    assert (await istemci.get("/api/magaza/indirmeler")).json() == []
    r = await istemci.post("/api/magaza/indir", json={"repo": "kotu repo adi"})
    assert r.status_code == 422
    sil = (await istemci.delete("/api/magaza/yuklu/gemma4-e4b-heretic")).json()
    assert len(sil["silindi"]) == 2
    assert not next(
        m
        for m in (await istemci.get("/api/magaza/yuklu")).json()["modeller"]
        if m["anahtar"] == "gemma4-e4b-heretic"
    )["dosya_var"]
