"""gorsel_oku: model gorseli GORUNTU olarak gorur; mesaj sirasi (tool'lardan sonra) korunur."""

from __future__ import annotations

from PIL import Image

from app.agent.dosyalar import KokKapsami
from app.services.sohbet import arac_calistir, gorsel_mesaji, gorsel_oku


def test_gorsel_kucultulur_ve_proje_disi_reddedilir(tmp_path):
    Image.new("RGB", (4000, 2000), "white").save(tmp_path / "fatura.png")
    (tmp_path / "bozuk.png").write_bytes(b"degil")
    kapsam = KokKapsami([tmp_path])
    r = gorsel_oku(kapsam, "fatura.png")
    assert r["boyut"] == "1600x800" and r["_gorsel"]["url"].startswith("data:image/jpeg;base64,")
    assert "hata" in gorsel_oku(kapsam, "bozuk.png")
    try:
        gorsel_oku(kapsam, str(tmp_path.parent / "disari.png"))
        raise AssertionError("proje disi okunmamali")
    except Exception as e:  # noqa: BLE001 - kapsam hatasi beklenir
        assert (
            "disi" in str(e).lower() or "izin" in str(e).lower() or "bulunamadi" in str(e).lower()
        )


async def test_arac_mesajinda_gorsel_ayri_tasinir(tmp_path):
    Image.new("RGB", (10, 10), "red").save(tmp_path / "a.png")
    kapsam = KokKapsami([tmp_path])
    cagri = {"id": "c1", "function": {"name": "gorsel_oku", "arguments": '{"yol": "a.png"}'}}
    isl = {"gorsel_oku": lambda yol: gorsel_oku(kapsam, yol)}
    mesaj, kayit = await arac_calistir(cagri, isl, lambda o: None, {})
    assert "base64" not in mesaj["content"] and "base64" not in kayit["sonuc"]  # metne girmez
    g = mesaj.pop("_gorsel")
    m = gorsel_mesaji([g])
    assert m["role"] == "user" and m["content"][1]["type"] == "image_url"
