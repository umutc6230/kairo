"""Sembol indeksi (BM25 + AST/regex) ve maliyet/tasarruf analitigi testleri."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.agent.araclar import AjanAracKaydi
from app.agent.checkpoints import CheckpointDeposu
from app.agent.dosyalar import KokKapsami
from app.agent.policy import PolitikaMotoru
from app.agent.runner import Kullanim, Run, RunDeposu
from app.agent.sembol_indeks import SembolIndeksi
from app.agent.terminal import KomutServisi
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.services.ayarlar import KullaniciAyarlari
from app.services.yerel_llm import VARSAYILAN_MODEL
from app.services.yonlendirici import maliyet_analitigi


def test_sembol_indeksi_python_ast_ve_js_ts(tmp_path: Path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "servis.py").write_text(
        '''"""Kullanici modulu."""

class KullaniciServisi:
    """Kullanici islemleri."""

    def dogrula(self, ad: str, sifre: str) -> bool:
        """Kimlik dogrular."""
        return bool(ad and sifre)

    async def getir(self, uid: int) -> dict:
        return {"id": uid}


def yardimci_hesap(x: int) -> int:
    return x * 2
''',
        encoding="utf-8",
    )
    (proje / "istemci.ts").write_text(
        """export interface KullaniciDTO {
  id: number;
}

export type KullaniciRol = "admin" | "uye";

export class OturumIstemcisi {
  gonder() {}
}

export async function kullaniciYukle(id: string) {
  return id;
}

export const tokenCoz = (ham: string) => ham.trim();
""",
        encoding="utf-8",
    )

    indeks = SembolIndeksi(KokKapsami([proje]))

    r = indeks.ara("dogrula")
    assert r["taranan_dosya"] == 2
    assert r["sonuclar"][0]["ad"] == "KullaniciServisi.dogrula"
    assert r["sonuclar"][0]["tur"] == "method"
    assert r["sonuclar"][0]["ozet"] == "Kimlik dogrular."
    assert r["sonuclar"][0]["bitis_satir"] >= r["sonuclar"][0]["satir"]

    siniflar = indeks.ara("Kullanici", tur="class")
    assert all(x["tur"] == "class" for x in siniflar["sonuclar"])
    assert any(x["ad"] == "KullaniciServisi" for x in siniflar["sonuclar"])

    ts_sonuc = indeks.ara("kullaniciYukle")
    assert ts_sonuc["sonuclar"][0]["ad"] == "kullaniciYukle"
    assert ts_sonuc["sonuclar"][0]["dosya"] == "istemci.ts"
    assert any(
        x["ad"] == "KullaniciDTO" and x["tur"] == "interface"
        for x in indeks.ara("KullaniciDTO")["sonuclar"]
    )
    assert any(
        x["ad"] == "tokenCoz" and x["tur"] == "function" for x in indeks.ara("tokenCoz")["sonuclar"]
    )


def test_sembol_indeksi_bm25_onbellek_guvenlik_ve_arac_kaydi(tmp_path: Path) -> None:
    proje = tmp_path / "repo"
    proje.mkdir()
    veri = tmp_path / "veri"
    veri.mkdir()

    (proje / ".gitignore").write_text("yoksay.py\n", encoding="utf-8")
    (proje / ".env").write_text("SECRET_KEY=123\ndef gizli_fn(): pass\n", encoding="utf-8")
    (proje / "yoksay.py").write_text("def yoksayilan_fonksiyon():\n    pass\n", encoding="utf-8")
    (proje / "yardimci.py").write_text(
        "def eski_model_yonetici_yardimcisi():\n    return 1\n", encoding="utf-8"
    )
    ana = proje / "yonetici.py"
    ana.write_text("class ModelYonetici:\n    pass\n", encoding="utf-8")

    alan = CalismaAlani(
        id="a" * 12,
        ad="repo",
        kokler=[str(proje)],
        guven=Guven.guvenilir,
        mod=Mod.otomatik,
    )
    kayit = AjanAracKaydi(alan, PolitikaMotoru(veri), CheckpointDeposu(veri), KomutServisi())
    semalar = {s["function"]["name"] for s in kayit.semalar()}
    assert "proje_sembol_ara" in semalar
    isl = kayit.isleyiciler()

    # Tam ad eslesmesi ilk sirada ve .env / .gitignore dosyalarina girilmez
    s1 = isl["proje_sembol_ara"](sorgu="ModelYonetici")
    assert s1["sonuclar"][0]["ad"] == "ModelYonetici"
    assert isl["proje_sembol_ara"](sorgu="yoksayilan_fonksiyon")["sonuclar"] == []
    assert isl["proje_sembol_ara"](sorgu="gizli_fn")["sonuclar"] == []

    # Dosya guncellenince onbellek tazelenir
    ana.write_text(
        "class ModelYonetici:\n    def yeni_ozellik(self):\n        return 42\n",
        encoding="utf-8",
    )
    s2 = isl["proje_sembol_ara"](sorgu="yeni_ozellik")
    assert s2["sonuclar"][0]["ad"] == "ModelYonetici.yeni_ozellik"

    # Kok disi klasor yetkisi reddedilir
    dis_sonuc = isl["proje_sembol_ara"](sorgu="ModelYonetici", klasor=str(tmp_path))
    assert dis_sonuc.get("karar") == "ret"


async def test_maliyet_analitigi_ve_api(app, istemci, tmp_path: Path) -> None:
    depo: RunDeposu = app.state.run_deposu
    simdi = datetime.now()
    t_bugun = simdi.isoformat(timespec="seconds")
    t_5_gun = (simdi - timedelta(days=5)).isoformat(timespec="seconds")
    t_20_gun = (simdi - timedelta(days=20)).isoformat(timespec="seconds")
    t_45_gun = (simdi - timedelta(days=45)).isoformat(timespec="seconds")

    depo.kaydet(
        Run(
            hedef="Bugun bulut",
            proje_id="p1",
            model="openai:gpt-4o",
            son_model="openai:gpt-4o",
            olusturma=t_bugun,
            kullanim=Kullanim(
                model_cagrisi=2,
                token=1000,
                onbellek_token=400,
                maliyet_usd=0.6,
                model_dokumu={"openai:gpt-4o": {"cagri": 2, "token": 1000, "maliyet_usd": 0.6}},
            ),
        )
    )
    depo.kaydet(
        Run(
            hedef="Bugun yerel",
            proje_id="p1",
            model=VARSAYILAN_MODEL,
            son_model=VARSAYILAN_MODEL,
            olusturma=t_bugun,
            kullanim=Kullanim(
                model_cagrisi=1,
                token=500,
                onbellek_token=100,
                maliyet_usd=0.0,
                model_dokumu={VARSAYILAN_MODEL: {"cagri": 1, "token": 500, "maliyet_usd": 0.0}},
            ),
        )
    )
    depo.kaydet(
        Run(
            hedef="5 gun once",
            proje_id="p2",
            model="anthropic/claude",
            son_model="anthropic/claude",
            olusturma=t_5_gun,
            kullanim=Kullanim(model_cagrisi=1, token=500, onbellek_token=0, maliyet_usd=0.4),
        )
    )
    depo.kaydet(
        Run(
            hedef="20 gun once",
            proje_id="p2",
            model="openai:gpt-4o",
            son_model="openai:gpt-4o",
            olusturma=t_20_gun,
            kullanim=Kullanim(model_cagrisi=1, token=1000, onbellek_token=500, maliyet_usd=1.0),
        )
    )
    depo.kaydet(
        Run(
            hedef="45 gun once",
            proje_id="",
            model="openai:gpt-4o",
            son_model="openai:gpt-4o",
            olusturma=t_45_gun,
            kullanim=Kullanim(model_cagrisi=1, token=1000, onbellek_token=0, maliyet_usd=2.0),
        )
    )

    await istemci.put("/api/ayarlar", json={"gunluk_butce_usd": 0.5})
    r = await istemci.get("/api/maliyet/analitik")
    assert r.status_code == 200
    d = r.json()
    assert d["bugun_usd"] == pytest.approx(0.6)
    assert d["son_7_gun_usd"] == pytest.approx(1.0)
    assert d["son_30_gun_usd"] == pytest.approx(2.0)
    assert d["toplam_usd"] == pytest.approx(4.0)
    assert d["gunluk_butce_usd"] == 0.5
    assert d["butce_asildi"] is True
    assert d["butce_yuzde"] == 100.0
    assert len(d["gunluk_seri"]) == 7
    assert d["gunluk_seri"][-1]["tarih"] == simdi.date().isoformat()
    assert d["gunluk_seri"][-1]["maliyet_usd"] == pytest.approx(0.6)
    assert d["gunluk_seri"][-1]["gorev"] == 2

    # Modeller maliyete gore azalan, yerel bayragi dogru
    assert d["modeller"][0]["model"] == "openai:gpt-4o"
    assert d["modeller"][0]["yerel"] is False
    yerel_satir = next(m for m in d["modeller"] if m["model"] == VARSAYILAN_MODEL)
    assert yerel_satir["yerel"] is True

    # Tasarruf oranlari: onbellek 1000/4000 = %25.0; yerel 1/5 = %20.0
    assert d["tasarruf"]["onbellek_token"] == 1000
    assert d["tasarruf"]["toplam_token"] == 4000
    assert d["tasarruf"]["onbellek_orani"] == pytest.approx(25.0)
    assert d["tasarruf"]["yerel_gorev"] == 1
    assert d["tasarruf"]["bulut_gorev"] == 4
    assert d["tasarruf"]["yerel_orani"] == pytest.approx(20.0)

    # Dogrudan fonksiyon cagrisi
    dogrudan = maliyet_analitigi(depo, KullaniciAyarlari())
    assert dogrudan["butce_yuzde"] is None and dogrudan["butce_asildi"] is False
