"""Kalıcı koordinasyon panosu ve akıllı maliyet/gizlilik yönlendiricisi testleri."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import olaylar

from app.agent.koordinasyon import DosyaMesgul, Koordinasyon
from app.agent.runner import Kullanim, Run, RunDeposu
from app.agent.workspaces import CalismaAlani
from app.services.ayarlar import KullaniciAyarlari
from app.services.yerel_llm import VARSAYILAN_MODEL
from app.services.yonlendirici import bulut_model_mi, gunluk_maliyet_usd, model_sec


def test_kalici_koordinasyon_surecler_arasi_ve_yeniden_baslatma(tmp_path: Path) -> None:
    dosya = tmp_path / "koordinasyon.json"
    t = [1000.0]
    saat = lambda: t[0]  # noqa: E731

    k1 = Koordinasyon(saat=saat, dosya=dosya)
    k2 = Koordinasyon(saat=saat, dosya=dosya)

    k1.kaydol("oturum:a", "p1", "Oturum A")
    k1.sahiplen("oturum:a", "p1", "app/a.py")

    # Ikinci ornek dosya kilidini diskten gorur
    with pytest.raises(DosyaMesgul, match="Oturum A"):
        k2.sahiplen("oturum:b", "p1", "app/a.py")

    # Ilk ornek ayrilinca ikinci ornek sahiplenebilir
    k1.ayril("oturum:a")
    k2.kaydol("oturum:b", "p1", "Oturum B")
    k2.sahiplen("oturum:b", "p1", "app/a.py")

    # Mesajlar yeniden baslatma sonrasinda korunur
    k1.kaydol("oturum:a", "p1", "Oturum A")
    k1.mesaj("oturum:a", "p1", "oturum:b", "Dosyayi kontrol et")

    k3 = Koordinasyon(saat=saat, dosya=dosya)  # yeniden baslatma simulasyonu
    aktif = k3.aktifler("p1", haric="oturum:a")
    assert len(aktif) == 1 and aktif[0]["dosyalar"] == ["app/a.py"]
    gelen = k3.teslim_al("oturum:b")
    assert len(gelen) == 1 and gelen[0].metin == "Dosyayi kontrol et"
    assert k3.teslim_al("oturum:b") == []


def test_yonlendirici_bulut_gizlilik_ve_butce() -> None:
    assert bulut_model_mi("") is False
    assert bulut_model_mi(VARSAYILAN_MODEL) is False
    assert bulut_model_mi("ollama:qwen3:8b") is False
    assert bulut_model_mi("lmstudio:llama-3.1") is False
    assert bulut_model_mi("openai:gpt-4o") is True
    assert bulut_model_mi("google/gemini-2.5-flash") is True

    ayar = KullaniciAyarlari(gunluk_butce_usd=1.0)
    normal_alan = CalismaAlani(ad="normal", gizli_proje=False)
    gizli_alan = CalismaAlani(ad="gizli", gizli_proje=True)

    # Gizli proje bulut modelini yerele ceker; yerel/ollama/lmstudio muaf
    m, u = model_sec("openai:gpt-4o", ayar, gizli_alan, bugun_usd=0.0)
    assert m == ayar.model and u is not None and "Gizli proje" in u

    for yerel in (VARSAYILAN_MODEL, "ollama:qwen3:8b", "lmstudio:qwen"):
        m_y, u_y = model_sec(yerel, ayar, gizli_alan, bugun_usd=5.0)
        assert m_y == yerel and u_y is None

    # Gunluk butce asiminda bulut yerele doner, butce altinda veya 0'da degismez
    m2, u2 = model_sec("google/gemini-2.5-flash", ayar, normal_alan, bugun_usd=0.5)
    assert m2 == "google/gemini-2.5-flash" and u2 is None

    m3, u3 = model_sec("google/gemini-2.5-flash", ayar, normal_alan, bugun_usd=1.0)
    assert m3 == ayar.model and u3 is not None and "butce" in u3.lower()

    sinirsiz = KullaniciAyarlari(gunluk_butce_usd=0.0)
    m4, u4 = model_sec("google/gemini-2.5-flash", sinirsiz, normal_alan, bugun_usd=50.0)
    assert m4 == "google/gemini-2.5-flash" and u4 is None


def test_gunluk_maliyet_usd_yalniz_bugunu_toplar(tmp_path: Path) -> None:
    depo = RunDeposu(tmp_path)
    bugun = datetime.now().isoformat(timespec="seconds")
    dun = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    depo.kaydet(Run(hedef="b1", olusturma=bugun, kullanim=Kullanim(maliyet_usd=0.25)))
    depo.kaydet(Run(hedef="b2", olusturma=bugun, kullanim=Kullanim(maliyet_usd=0.15)))
    depo.kaydet(Run(hedef="d1", olusturma=dun, kullanim=Kullanim(maliyet_usd=5.0)))
    assert gunluk_maliyet_usd(depo) == pytest.approx(0.4)


async def test_api_gizli_proje_butce_ve_sohbet_yonlendirme(app, istemci, tmp_path: Path) -> None:
    proje_yol = tmp_path / "gizli-repo"
    proje_yol.mkdir()
    p = (await istemci.post("/api/projeler", json={"yol": str(proje_yol)})).json()
    await istemci.post(f"/api/projeler/{p['id']}/etkin")

    # gizli_proje ayari + model olarak bulut modeli ver (yonlendirici yerel modele dondurecek)
    guncel = (
        await istemci.put(f"/api/projeler/{p['id']}/gizli", json={"gizli_proje": True})
    ).json()
    assert guncel["gizli_proje"] is True

    await istemci.put(
        f"/api/projeler/{p['id']}/modeller",
        json={"koordinator_model": "openai:gpt-4o", "uygulayici_model": ""},
    )

    # Ayar: gunluk_butce_usd ve /api/maliyet/durum
    ay = (await istemci.put("/api/ayarlar", json={"gunluk_butce_usd": 2.5})).json()
    assert ay["gunluk_butce_usd"] == 2.5

    bugun = datetime.now().isoformat(timespec="seconds")
    app.state.run_deposu.kaydet(
        Run(hedef="harcama", olusturma=bugun, kullanim=Kullanim(maliyet_usd=3.0))
    )
    durum = (await istemci.get("/api/maliyet/durum")).json()
    assert durum["bugun_usd"] == pytest.approx(3.0)
    assert durum["gunluk_butce_usd"] == 2.5
    assert durum["asildi"] is True

    # Sohbet: gizli projede bulut koordinator modeli yerele yonlenir ve uyari gelir
    oturum = (await istemci.post("/api/oturumlar")).json()
    r = await istemci.post(
        f"/api/oturumlar/{oturum['id']}/mesaj",
        json={"metin": "Merhaba", "ekler": []},
    )
    assert r.status_code == 200
    gelen = olaylar(r.text)
    uyari = next(
        o for o in gelen if o.get("tur") == "uyari" and o.get("kod") == "model_yonlendirildi"
    )
    assert "Gizli proje" in uyari["metin"]
    bitti = next(o for o in gelen if o.get("tur") == "bitti")
    assert bitti["mesaj"]["model"] == VARSAYILAN_MODEL
