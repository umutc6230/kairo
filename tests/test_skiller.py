"""Skill'ler ve talimatlar (Claude Code mantigi)."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import olaylar

from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services import skiller as skl
from app.services import talimatlar as tal


def skill_yaz(
    kok: Path, ad: str, aciklama: str, govde: str = "Talimat govdesi.", **dosyalar
) -> Path:
    d = kok / ad
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {ad}\ndescription: >-\n  {aciklama}\n---\n\n{govde}\n", encoding="utf-8"
    )
    for yol, icerik in dosyalar.items():
        hedef = d / yol.replace("__", "/")
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(icerik if isinstance(icerik, bytes) else icerik.encode())
    return d


@pytest.fixture
def depo(tmp_path) -> skl.SkillDeposu:
    claude = tmp_path / "claude"
    brain = tmp_path / "brain"
    skill_yaz(claude, "hakedis-kontrol", "Hakedis raporunu kontrol eder, metraj ve birim fiyat.")
    skill_yaz(
        claude,
        "markitdown",
        "PDF ve Word dosyalarini markdown'a cevirir.",
        "Uzun talimat " * 2000,
        references__ornek_md="# ornek",
        ikili_bin=b"\x00\x01",
    )
    (brain).mkdir()
    (brain / "brain-query.md").write_text("# Brain sorgu\nVault'ta arama yapar.", encoding="utf-8")
    skill_yaz(brain, "hakedis-kontrol", "Ayni ad: atlanmali.")  # ad cakismasi
    (brain / "bozuk").mkdir()
    (brain / "bozuk" / "SKILL.md").write_text("---\nname: [bozuk\n---\ngovde", encoding="utf-8")
    return skl.SkillDeposu(
        tmp_path / "veri",
        [("claude", claude), ("brain", brain), ("uygulama", tmp_path / "veri" / "skills")],
    )


def test_frontmatter():
    meta, govde = skl.frontmatter("---\nname: x\ndescription: |\n  iki\n  satir\n---\n\nGovde")
    assert meta == {"name": "x", "description": "iki\nsatir"} and govde == "Govde"
    assert skl.frontmatter("duz metin") == ({}, "duz metin")
    assert skl.frontmatter("---\nkapanmayan") == ({}, "---\nkapanmayan")
    assert skl.frontmatter("---\n- liste\n---\nG") == ({}, "G")


def test_kesfet_kaynaklar_ve_tekillestirme(depo):
    s = {x.ad: x for x in depo.kesfet()}
    assert set(s) == {"hakedis-kontrol", "markitdown", "brain-query", "bozuk"}
    assert s["hakedis-kontrol"].kaynak == "claude"  # brain'deki ayni ad atlandi
    assert s["brain-query"].klasor is None and s["brain-query"].aciklama == "Brain sorgu"
    assert s["bozuk"].aciklama == "govde"  # bozuk YAML: govdeden aciklama
    assert s["markitdown"].ozet()["silinebilir"] is False


def test_ayni_dosya_iki_kaynakta_bir_kez(tmp_path):
    kok = tmp_path / "k"
    skill_yaz(kok, "tek", "Tek skill.")
    d = skl.SkillDeposu(tmp_path, [("claude", kok), ("brain", kok)])
    assert [s.ad for s in d.kesfet()] == ["tek"]


def test_uygun_skiller_siralama_ve_esik(depo):
    etkin = depo.kesfet()
    assert [s.ad for s in skl.uygun_skiller(etkin, "hakedis raporunu kontrol et")][
        0
    ] == "hakedis-kontrol"
    assert [s.ad for s in skl.uygun_skiller(etkin, "bu pdf dosyasini cevir")] == ["markitdown"]
    assert skl.uygun_skiller(etkin, "merhaba nasilsin") == []
    assert skl.uygun_skiller(etkin, "") == []
    metin = skl.sistem_metni(skl.uygun_skiller(etkin, "hakedis"))
    assert "skill_kullan(ad)" in metin and "- hakedis-kontrol:" in metin
    assert skl.sistem_metni([]) == ""


def test_skill_araclari(depo):
    i = skl.arac_isleyicileri(depo, kapali={"brain-query"})
    s = i["skill_kullan"]("markitdown")
    assert s["not"] == "Talimat kisaltildi." and len(s["talimat"]) == skl.MAX_SKILL_KARAKTER
    assert sorted(s["dosyalar"]) == ["ikili_bin", "references/ornek_md"]
    assert i["skill_kullan"]("brain-query") == {"hata": "Skill bulunamadi: brain-query"}  # kapali
    assert "hata" in i["skill_kullan"]("yok")
    yol = next(f for f in s["dosyalar"] if f.startswith("references"))
    assert i["skill_dosyasi_oku"]("markitdown", yol)["icerik"] == "# ornek"
    assert "yok" in i["skill_dosyasi_oku"]("markitdown", "../../../Windows/win.ini")["hata"]
    ikili = next(f for f in s["dosyalar"] if f.startswith("ikili"))
    assert "Ikili" in i["skill_dosyasi_oku"]("markitdown", ikili)["hata"]
    assert "hata" in i["skill_dosyasi_oku"]("yok", "x")
    i2 = skl.arac_isleyicileri(depo, kapali=set())
    assert "tek dosya" in i2["skill_dosyasi_oku"]("brain-query", "x")["hata"]
    assert i["skill_ara"]("pdf markdown")["sonuc"][0]["ad"] == "markitdown"
    assert [a["function"]["name"] for a in skl.ARACLAR] == list(i)


def test_uygulama_skill_ekle_sil(depo):
    s = depo.olustur("Fatura-Okuma", "Faturadan alanlari cikarir.", "Adimlar...")
    assert s.ad == "fatura-okuma" and s.kaynak == "uygulama" and s.ozet()["silinebilir"]
    meta, govde = skl.frontmatter(s.dosya.read_text(encoding="utf-8"))
    assert meta["description"] == "Faturadan alanlari cikarir." and govde.strip() == "Adimlar..."
    with pytest.raises(UygulamaHatasi, match="zaten var"):
        depo.olustur("fatura-okuma", "x", "y")
    with pytest.raises(UygulamaHatasi, match="kucuk harf"):
        depo.olustur("kötü ad", "x", "y")
    with pytest.raises(UygulamaHatasi, match="Aciklama"):
        depo.olustur("bos", " ", "y")
    with pytest.raises(UygulamaHatasi, match="Yalniz uygulamada"):
        depo.sil("markitdown")
    depo.sil("fatura-okuma")
    with pytest.raises(Bulunamadi):
        depo.getir("fatura-okuma")


# ---- talimatlar ----
def test_import_zinciri_dongu_ve_kod_blogu(tmp_path, monkeypatch):
    monkeypatch.setattr(tal.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "brain").mkdir()
    (tmp_path / "brain" / "POLICY.md").write_text("Kural 1\n@alt.md\n", encoding="utf-8")
    (tmp_path / "brain" / "alt.md").write_text("Alt kural\n@POLICY.md\n", encoding="utf-8")  # dongu
    ana = tmp_path / "CLAUDE.md"
    ana.write_text(
        "Baslik\n@~/brain/POLICY.md\n```\n@kod/icinde.md\n```\n@yok.md\n", encoding="utf-8"
    )
    k = tal.importlari_coz(ana)
    assert [Path(x["yol"]).name for x in k] == ["CLAUDE.md", "POLICY.md", "alt.md"]
    assert "@kod/icinde.md" in k[0]["metin"] and "@~/brain" not in k[0]["metin"]
    assert k[1]["metin"] == "Kural 1"
    assert tal.importlari_coz(tmp_path / "yok.md") == []


def test_talimat_deposu(tmp_path, monkeypatch):
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("Turkce cevap ver.", encoding="utf-8")
    monkeypatch.setattr(tal, "claude_md_yolu", lambda: claude)
    monkeypatch.setattr(tal, "MAX_KAYNAK_KARAKTER", 10)
    d = tal.TalimatDeposu(tmp_path)
    assert d.uygulama_oku() == ""
    assert d.uygulama_yaz("  Kisa yaz.  ") == "Kisa yaz.\n"
    k = d.kaynaklar()
    assert [x["tur"] for x in k] == ["claude", "uygulama"] and k[0]["kisaltildi"] is True
    assert '<talimat kaynak="CLAUDE.md">' in d.sistem_metni()
    assert d.sistem_metni(claude=False, uygulama=False) == ""
    assert d.uygulama_yaz("") == ""


# ---- API + sohbet entegrasyonu ----
async def test_talimat_ve_skill_uclari(istemci, skill_klasoru, tmp_path):
    (tmp_path / "CLAUDE.md").write_text("Genel kural: kisa yaz.", encoding="utf-8")
    skill_yaz(skill_klasoru, "hakedis-kontrol", "Hakedis raporunu kontrol eder.")
    t = (await istemci.get("/api/talimatlar")).json()
    assert t["claude"][0]["metin"] == "Genel kural: kisa yaz." and t["baglam_token"] == 16384
    assert (await istemci.put("/api/talimatlar", json={"metin": "Uygulama kurali"})).json() == {
        "uygulama": "Uygulama kurali\n"
    }
    liste = (await istemci.get("/api/skiller")).json()
    assert [s["ad"] for s in liste["skiller"]] == ["hakedis-kontrol"] and liste["skiller"][0][
        "acik"
    ]
    assert (
        "Hakedis raporunu" in (await istemci.get("/api/skiller/hakedis-kontrol")).json()["icerik"]
    )
    r = await istemci.post(
        "/api/skiller", json={"ad": "not-al", "aciklama": "Not alir.", "icerik": "x"}
    )
    assert r.json()["kaynak"] == "uygulama"
    await istemci.put("/api/skiller/not-al/durum", json={"acik": False})
    assert (await istemci.get("/api/ayarlar")).json()["kapali_skiller"] == ["not-al"]
    await istemci.put("/api/skiller/not-al/durum", json={"acik": True})
    assert (await istemci.delete("/api/skiller/not-al")).json() == {"silindi": "not-al"}
    assert (await istemci.delete("/api/skiller/hakedis-kontrol")).status_code == 400
    assert (await istemci.get("/api/skiller/yok")).status_code == 404
    r = await istemci.put("/api/ayarlar", json={"baglam_token": 1000})
    assert r.status_code == 422 and "8192" in r.json()["hata"]


async def test_sohbet_sistemine_talimat_ve_uygun_skill_girer(
    istemci, sunucu, skill_klasoru, tmp_path
):
    (tmp_path / "CLAUDE.md").write_text("Genel kural: kisa yaz.", encoding="utf-8")
    skill_yaz(skill_klasoru, "hakedis-kontrol", "Hakedis raporunu kontrol eder.")
    skill_yaz(skill_klasoru, "tv-debloat", "Android TV uygulamalarini temizler.")
    await istemci.put("/api/talimatlar", json={"metin": "Uygulama kurali"})
    o = (await istemci.post("/api/oturumlar")).json()["id"]
    await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Hakedis raporunu kontrol et"})
    istek = sunucu.istekler[-1]
    sistem = istek["messages"][0]["content"]
    assert "Genel kural: kisa yaz." in sistem and "Uygulama kurali" in sistem
    # 16K: Claude Code gibi tum skill'ler listelenir; guclu eslesen otomatik yuklenir (en sonda)
    assert "- hakedis-kontrol:" in sistem and "- tv-debloat:" in sistem
    assert sistem.rstrip().endswith("</skill>") and '<skill ad="hakedis-kontrol">' in sistem
    assert sistem.index("Uygulama kurali") < sistem.index("Kullanilabilir skill")  # sabit once
    adlar = [a["function"]["name"] for a in istek["tools"]]
    assert "skill_kullan" in adlar and "klasor_listele" in adlar
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Hakedis raporu kontrol"})
    oto = [x for x in olaylar(r.text) if x["tur"] == "arac_sonucu"]
    assert oto and oto[0]["ad"] == "skill_kullan" and oto[0]["ozet"] == "otomatik yüklendi"
    kayit = (await istemci.get(f"/api/oturumlar/{o}")).json()["mesajlar"][-1]["araclar"]
    assert kayit[0]["argumanlar"] == {"ad": "hakedis-kontrol"}
    # 8K: yer yok, yalniz mesaja uygun olanlar
    await istemci.put("/api/ayarlar", json={"baglam_token": 8192})
    await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Hakedis raporunu kontrol et"})
    sistem = sunucu.istekler[-1]["messages"][0]["content"]
    assert "- hakedis-kontrol:" in sistem and "tv-debloat" not in sistem
    await istemci.put("/api/ayarlar", json={"claude_talimatlari": False, "skiller_acik": False})
    await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "Hakedis raporu"})
    sistem = sunucu.istekler[-1]["messages"][0]["content"]
    assert (
        "Genel kural" not in sistem
        and "hakedis-kontrol" not in sistem
        and "Uygulama kurali" in sistem
    )


async def test_talimatlar_baglami_doldurursa_uyari(istemci, tmp_path):
    (tmp_path / "CLAUDE.md").write_text("kural " * 9000, encoding="utf-8")  # ~16k karakter
    await istemci.put("/api/ayarlar", json={"baglam_token": 8192, "max_tokens": 4096})
    o = (await istemci.post("/api/oturumlar")).json()["id"]
    r = await istemci.post(f"/api/oturumlar/{o}/mesaj", json={"metin": "selam"})
    assert any(x["tur"] == "uyari" and "bağlamı dolduruyor" in x["metin"] for x in olaylar(r.text))


async def test_isitma_sabit_oneki_gonderir(istemci, sunucu, tmp_path):
    import asyncio

    (tmp_path / "CLAUDE.md").write_text("Politika metni.", encoding="utf-8")
    await istemci.post("/api/model/hazirla", json={})
    for _ in range(50):
        if any(i.get("max_tokens") == 1 for i in sunucu.istekler):
            break
        await asyncio.sleep(0.02)
    isitma = next(i for i in sunucu.istekler if i.get("max_tokens") == 1)
    assert "Politika metni." in isitma["messages"][0]["content"] and isitma["tools"]


def test_tam_liste_ve_otomatik(depo):
    etkin = depo.kesfet()
    metin = skl.tam_liste_metni(etkin)
    assert metin.index("- brain-query") < metin.index("- markitdown")  # alfabetik, sabit
    assert skl.tam_liste_metni([]) == ""
    assert skl.otomatik_skill(etkin, "hakedis raporunu kontrol et").ad == "hakedis-kontrol"
    assert skl.otomatik_skill(etkin, "merhaba") is None
    uzun = skl.otomatik_metin(depo.getir("markitdown"), sinir=50)
    assert "kisaltildi" in uzun and uzun.endswith("</skill>")
    assert "CALISTIRAMAZSIN" in uzun and "CALISTIRAMAZSIN" in metin
