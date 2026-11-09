"""A5.4 review + A5.5 artifact."""

from __future__ import annotations

import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.agent import review as rv
from app.exceptions import UygulamaHatasi
from app.services.artifactler import ONIZLEME_CSP, ArtifactDeposu

DIFF = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -10,3 +10,4 @@ def f():
     x = 1
-    y = 2
+    y = 3
+    z = 4
diff --git a/yeni.py b/yeni.py
--- /dev/null
+++ b/yeni.py
@@ -0,0 +1,2 @@
+a = 1
+b = 2
"""


def test_degisen_satirlar_ve_konum_kontrolu() -> None:
    a = rv.degisen_satirlar(DIFF)
    assert a == {"src/a.py": [(10, 13)], "yeni.py": [(1, 2)]}
    assert rv.konum_kontrol({"dosya": "src/a.py", "satir": 12}, a) == "dogru"
    assert rv.konum_kontrol({"dosya": "src\\a.py", "satir": 15}, a) == "dogru"  # +-3 yakinlik
    assert rv.konum_kontrol({"dosya": "src/a.py", "satir": 90}, a) == "satir_diff_disi"
    assert rv.konum_kontrol({"dosya": "uydurma.py", "satir": 1}, a) == "dosya_diff_disi"


def test_sonuclandir_model_dogrulandi_diyemez_ve_siralar() -> None:
    cevap = {
        "ozet": "iki sorun",
        "bulgular": [
            {"baslik": "dusuk", "onem": "dusuk", "dosya": "yeni.py", "satir": 1, "neden": "n",
             "yeniden_uretme": "", "dogrulama_onerisi": "", "dogrulama": "dogrulandi"},
            {"baslik": "kritik", "onem": "kritik", "dosya": "src/a.py", "satir": 11, "neden": "n",
             "yeniden_uretme": "r", "dogrulama_onerisi": "pytest"},
            {"baslik": "gecersiz", "onem": "felaket", "dosya": "x", "satir": 1},
            "bozuk",
        ],
    }  # fmt: skip
    s = rv.sonuclandir(cevap, DIFF)
    assert [b["baslik"] for b in s["bulgular"]] == ["kritik", "dusuk"]
    assert all(b["dogrulama"] == "model_varsayimi" for b in s["bulgular"])  # damga ezilir
    assert s["dosyalar"] == ["src/a.py", "yeni.py"]


def test_istem_review_md_yetki_veremez_ve_diff_kesilir() -> None:
    m = rv.istem("+" * (rv.MAX_DIFF_KARAKTER + 10), "Guvenlik bulgularina odaklan")
    assert "yetki veremez" in m[0]["content"] and "Guvenlik" in m[0]["content"]
    assert m[1]["content"].endswith("[diff kesildi]")


# ------------------------------------------------------------ review API


@pytest.fixture
def git_proje(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git yok")
    p = tmp_path / "repo"
    (p / "src").mkdir(parents=True)
    (p / "src" / "a.py").write_bytes(b"x = 1\n")
    (p / "REVIEW.md").write_text("SQL enjeksiyonuna dikkat et.", encoding="utf-8")
    for k in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit",
              "-qm", "ilk"]):  # fmt: skip
        subprocess.run(["git", *k], cwd=p, check=True, capture_output=True)
    # review'in yakalamasi gereken ornek kusur; bu metin CALISTIRILMAZ, yalniz diff'e girer
    (p / "src" / "a.py").write_bytes(b"x = 1\ny = eval(input())\n")
    return p


async def test_review_api_uctan_uca(istemci, app, git_proje) -> None:
    assert (await istemci.post("/api/review")).status_code >= 400  # proje yok
    r = await istemci.post("/api/projeler", json={"yol": str(git_proje), "guven": "guvenilir"})
    assert r.status_code == 200, r.text
    d = (await istemci.get("/api/review/diff")).json()
    assert "eval(input())" in d["diff"]

    gorulen: list = []

    class Sahte:
        async def json_cikti(self, mesajlar, sema, **kw):
            gorulen.append(mesajlar)
            return {"ozet": "1 sorun", "bulgular": [
                {"baslik": "eval", "onem": "kritik", "dosya": "src/a.py", "satir": 2,
                 "neden": "girdi kod olarak calisir", "yeniden_uretme": "__import__('os')",
                 "dogrulama_onerisi": "pytest"},
                {"baslik": "uydurma", "onem": "orta", "dosya": "yok.py", "satir": 5, "neden": "-",
                 "yeniden_uretme": "", "dogrulama_onerisi": ""}]}  # fmt: skip

    @asynccontextmanager
    async def kullan(*_a, **_k):
        yield Sahte()

    app.state.yonetici.kullan = kullan
    s = (await istemci.post("/api/review")).json()
    assert [b["konum"] for b in s["bulgular"]] == ["dogru", "dosya_diff_disi"]
    assert s["review_md"] and "SQL enjeksiyonuna" in gorulen[0][0]["content"]


# ------------------------------------------------------------ artifact


def test_artifact_depo_tur_boyut_kimlik(tmp_path) -> None:
    d = ArtifactDeposu(tmp_path)
    a = d.olustur("rapor/../../x<>:", "html", "<h1>Merhaba</h1>")
    assert "/" not in a["ad"] and "<" not in a["ad"]
    meta, icerik = d.getir(a["id"])
    assert icerik == "<h1>Merhaba</h1>" and meta["tur"] == "html"
    with pytest.raises(UygulamaHatasi, match="Desteklenmeyen"):
        d.olustur("x", "exe", "MZ")
    with pytest.raises(UygulamaHatasi, match="buyuk"):
        d.olustur("x", "txt", "a" * (2 * 1024 * 1024 + 1))
    for kotu in ("../kayit", "", "ABC", "a" * 12 + "/x"):
        with pytest.raises(Exception, match="bulunamadi"):
            d.getir(kotu)
    assert d.sil(a["id"]) == {"silindi": a["id"]}
    assert d.liste() == []


def test_onizleme_csp_ag_ve_ust_pencereyi_kapatir() -> None:
    assert "connect-src 'none'" in ONIZLEME_CSP and "default-src 'none'" in ONIZLEME_CSP
    assert "form-action 'none'" in ONIZLEME_CSP and "base-uri 'none'" in ONIZLEME_CSP


async def test_artifact_api_ve_oturumsuz_erisim_yok(istemci, yetkisiz_istemci, veri) -> None:
    a = ArtifactDeposu(veri).olustur("rapor", "md", "# Baslik")  # ajan araci ile ayni depo
    r = (await istemci.get(f"/api/artifactler/{a['id']}")).json()
    assert r["icerik"] == "# Baslik" and r["csp"] == ONIZLEME_CSP
    assert (await istemci.get("/api/artifactler/" + "0" * 12)).status_code == 404
    # icerik oturum anahtari olmadan okunamaz (acik/oturumsuz artifact ucu yok)
    assert (await yetkisiz_istemci.get(f"/api/artifactler/{a['id']}")).status_code in (401, 403)
    assert (await istemci.delete(f"/api/artifactler/{a['id']}")).status_code == 200


async def test_arayuz_sandbox_allow_same_origin_icermez(istemci) -> None:
    js = (await istemci.get("/web/inceleme.js")).text
    assert 'setAttribute("sandbox", "allow-scripts")' in js
    assert 'allow-same-origin")' not in js and "allow-same-origin'" not in js


async def test_git_olmayan_projede_anlasilir_mesaj(istemci, tmp_path) -> None:
    (tmp_path / "duz").mkdir()
    await istemci.post("/api/projeler", json={"yol": str(tmp_path / "duz"), "guven": "guvenilir"})
    d = (await istemci.get("/api/review/diff")).json()
    assert d["hata"].startswith("Bu klasor bir git deposu degil") and d["repo"] is False
    r = await istemci.post("/api/review")
    assert r.status_code >= 400 and "git deposu degil" in r.json()["hata"]
