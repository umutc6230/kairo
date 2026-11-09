"""Kabul A2: dosya, terminal, Git ve checkpoint araclari.

Ana senaryo gecici bir Python ve bir TS projesinde uctan uca:
oku -> yama -> test calistir -> diff -> geri al.

Ayrica: CRLF, Turkce ve bosluklu yol, stale hash, dirty repo korumasi, yeni dosya,
silme/tasima, zaman asimi ve tum cocuk sureclerin kapanmasi.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import IzoleSahte

from app.agent.araclar import AjanAracKaydi
from app.agent.checkpoints import CheckpointDeposu, dosya_hashi
from app.agent.dosyalar import GitIgnore, KokKapsami, ortam_allowlist
from app.agent.policy import PolitikaMotoru
from app.agent.terminal import KomutServisi
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.agent.yazma import atomik_yaz
from app.exceptions import OnayGerekli, UygulamaHatasi, YetkiYok

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def py_proje(tmp_path: Path) -> Path:
    """Gercek, calisan bir Python projesi (testi gecen)."""
    p = tmp_path / "ornek proje"  # BOSLUKLU yol bilerek
    (p / "src").mkdir(parents=True)
    (p / "tests").mkdir()
    (p / "src" / "hesap.py").write_text(
        "def topla(a, b):\n    return a - b  # hatali\n", encoding="utf-8"
    )
    (p / "tests" / "test_hesap.py").write_text(
        "import sys\nsys.path.insert(0, 'src')\nfrom hesap import topla\n\n"
        "def test_topla():\n    assert topla(2, 3) == 5\n",
        encoding="utf-8",
    )
    (p / "README.md").write_text("# ornek\n", encoding="utf-8")
    (p / ".gitignore").write_text("gecici/\n*.log\n", encoding="utf-8")
    (p / "gecici").mkdir()
    (p / "gecici" / "ara.txt").write_text("yoksayilir", encoding="utf-8")
    (p / "cikti.log").write_text("yoksayilir", encoding="utf-8")
    (p / "türkçe dosya.txt").write_text("şçğüöı\n", encoding="utf-8")
    (p / "crlf.txt").write_bytes(b"bir\r\niki\r\nuc\r\n")
    return p


@pytest.fixture
def ortam(tmp_path: Path, py_proje: Path):
    """(kayit, alan, checkpointler, kapsam) - otomatik modda tam yetkili ajan araclari."""
    veri = tmp_path / "veri"
    veri.mkdir()
    alan = CalismaAlani(
        id="a" * 12, ad="ornek", kokler=[str(py_proje)], guven=Guven.guvenilir, mod=Mod.otomatik
    )
    politika = PolitikaMotoru(veri, izolasyon=IzoleSahte)
    cp = CheckpointDeposu(veri)
    kayit = AjanAracKaydi(alan, politika, cp, KomutServisi())
    return kayit, alan, cp, kayit.kapsam


# ------------------------------------------------------------ okuma (A2.1)


def test_satir_numarali_okuma_ve_sayfalama(ortam, py_proje: Path) -> None:
    kayit, *_ = ortam
    s = kayit.okuma.dosya_oku("src/hesap.py")
    assert s["toplam_satir"] == 2 and s["satir_baslangic"] == 1
    assert "     1\tdef topla(a, b):" in s["icerik"]
    assert s["truncated"] is False and s["sonraki_satir"] is None

    uzun = py_proje / "uzun.txt"
    uzun.write_text("\n".join(f"s{i}" for i in range(1, 1001)), encoding="utf-8")
    ilk = kayit.okuma.dosya_oku("uzun.txt", satir_sayisi=10)
    assert ilk["truncated"] and ilk["sonraki_satir"] == 11 and ilk["toplam_satir"] == 1000
    ikinci = kayit.okuma.dosya_oku("uzun.txt", baslangic_satir=ilk["sonraki_satir"])
    assert ikinci["satir_baslangic"] == 11


def test_crlf_ve_turkce_yol(ortam) -> None:
    kayit, *_ = ortam
    crlf = kayit.okuma.dosya_oku("crlf.txt")
    assert crlf["satir_sonu"] == "CRLF" and crlf["toplam_satir"] == 3
    tr = kayit.okuma.dosya_oku("türkçe dosya.txt")
    assert "şçğüöı" in tr["icerik"] and tr["kodlama"] == "utf-8"


def test_ikili_ve_buyuk_dosya(ortam, py_proje: Path) -> None:
    kayit, *_ = ortam
    (py_proje / "resim.png").write_bytes(b"\x89PNG\x00\x00veri")
    assert "ikili" in kayit.okuma.dosya_oku("resim.png")["hata"]
    assert "bulunamadi" in kayit.okuma.dosya_oku("yok.txt")["hata"]


def test_kok_disi_okuma_reddedilir(ortam, tmp_path: Path) -> None:
    kayit, *_ = ortam
    (tmp_path / "disarida.txt").write_text("sir", encoding="utf-8")
    sonuc = kayit.okuma.dosya_oku(str(tmp_path / "disarida.txt"))
    assert sonuc["karar"] == "ret"


def test_listele_glob_ve_gitignore(ortam) -> None:
    kayit, *_ = ortam
    liste = kayit.okuma.klasor_listele("", derinlik=2)
    adlar = " ".join(liste["ogeler"])
    assert "src" in adlar and "gecici" not in adlar and "cikti.log" not in adlar

    glob = kayit.okuma.glob_bul("**/*.py")
    assert sorted(Path(x).name for x in glob["bulunan"]) == ["hesap.py", "test_hesap.py"]


def test_gitignore_eslestirici(tmp_path: Path) -> None:
    kok = tmp_path / "g"
    kok.mkdir()
    (kok / ".gitignore").write_text("*.log\nbuild/\n!onemli.log\n", encoding="utf-8")
    (kok / "build").mkdir()
    g = GitIgnore(kok)
    assert g.yok_sayilir(kok / "a.log")
    assert g.yok_sayilir(kok / "build")
    assert not g.yok_sayilir(kok / "onemli.log")
    assert not g.yok_sayilir(kok / "src" / "ana.py")
    assert not GitIgnore(tmp_path / "yok").yok_sayilir(tmp_path / "x")


def test_icerik_arama(ortam) -> None:
    kayit, *_ = ortam
    s = kayit.okuma.icerik_ara(r"def topla")
    assert s["sayi"] >= 1
    assert any(e["dosya"].endswith("hesap.py") and e["satir"] == 1 for e in s["eslesmeler"])
    assert "hata" in kayit.okuma.icerik_ara("")


def test_python_arama_yedegi(ortam) -> None:
    """rg yoksa da arama calismali (ayni sozlesme)."""
    kayit, *_ = ortam
    s = kayit.okuma._python_ara(r"topla", kayit.kapsam.coz(""), "*.py")
    assert s["motor"] == "python" and s["sayi"] >= 1
    assert "Gecersiz desen" in kayit.okuma._python_ara("[bozuk(", kayit.kapsam.coz(""), "")["hata"]


# ------------------------------------------------------------ yazma (A2.2)


def test_yeni_dosya_olustur_ve_uzerine_yazma_hash_ister(ortam, py_proje: Path) -> None:
    kayit, *_ = ortam
    s = kayit.yazma.dosya_yaz("yeni.txt", "merhaba\n")
    assert (py_proje / "yeni.txt").read_text(encoding="utf-8") == "merhaba\n"
    assert s["islem"] == "olustur" and s["checkpoint"]

    # var olan dosyaya hash'siz yazma REDDEDILIR
    with pytest.raises(UygulamaHatasi, match="beklenen_hash"):
        kayit.yazma.dosya_yaz("yeni.txt", "baska")
    # yanlis hash de reddedilir
    with pytest.raises(UygulamaHatasi, match="degisti"):
        kayit.yazma.dosya_yaz("yeni.txt", "baska", beklenen_hash="0" * 32)
    # dogru hash ile gecer
    dogru = dosya_hashi(py_proje / "yeni.txt")
    kayit.yazma.dosya_yaz("yeni.txt", "ikinci\n", beklenen_hash=dogru)
    assert (py_proje / "yeni.txt").read_text(encoding="utf-8") == "ikinci\n"


def test_yama_benzersiz_olmali(ortam, py_proje: Path) -> None:
    kayit, *_ = ortam
    hedef = py_proje / "tekrar.txt"
    hedef.write_text("x = 1\nx = 1\n", encoding="utf-8")
    h = dosya_hashi(hedef)
    with pytest.raises(UygulamaHatasi, match="2 yerde"):
        kayit.yazma.dosya_yama("tekrar.txt", "x = 1", "x = 2", beklenen_hash=h)
    with pytest.raises(UygulamaHatasi, match="bulunamadi"):
        kayit.yazma.dosya_yama("tekrar.txt", "yok boyle", "y", beklenen_hash=h)
    with pytest.raises(UygulamaHatasi, match="ayni"):
        kayit.yazma.dosya_yama("tekrar.txt", "x = 1", "x = 1", beklenen_hash=h)


def test_tasi_ve_sil(ortam, py_proje: Path) -> None:
    kayit, _, cp, _ = ortam
    kayit.yazma.dosya_yaz("tasinacak.txt", "veri\n")
    kayit.yazma.dosya_tasi("tasinacak.txt", "alt/tasindi.txt")
    assert (py_proje / "alt" / "tasindi.txt").is_file()
    assert not (py_proje / "tasinacak.txt").exists()
    with pytest.raises(UygulamaHatasi, match="Kaynak bulunamadi"):
        kayit.yazma.dosya_tasi("tasinacak.txt", "x.txt")

    s = kayit.yazma.dosya_sil("alt/tasindi.txt")
    assert s["silindi"] and not (py_proje / "alt" / "tasindi.txt").exists()
    # geri alinca dosya geri gelir
    assert cp.geri_al(s["checkpoint"])["tamam"]
    assert (py_proje / "alt" / "tasindi.txt").read_text(encoding="utf-8") == "veri\n"


def test_atomik_yazim_yarim_dosya_birakmaz(tmp_path: Path) -> None:
    hedef = tmp_path / "a.txt"
    hedef.write_text("eski", encoding="utf-8")
    with pytest.raises(TypeError):
        atomik_yaz(hedef, "bayt degil")  # type: ignore[arg-type]
    assert hedef.read_text(encoding="utf-8") == "eski"  # eski icerik bozulmadi
    assert not list(tmp_path.glob(".*yas-tmp"))  # gecici dosya temizlendi


def test_kok_disina_yazilamaz(ortam, tmp_path: Path) -> None:
    kayit, *_ = ortam
    with pytest.raises(YetkiYok):
        kayit.yazma.dosya_yaz(str(tmp_path / "disarida.txt"), "x")


def test_hassas_dosyaya_yazilamaz(ortam) -> None:
    kayit, *_ = ortam
    with pytest.raises(YetkiYok):
        kayit.yazma.dosya_yaz(".env", "API_KEY=1")


# ------------------------------------------------- mod ve onay (A1 x A2)


def test_planla_modunda_yazma_araci_SUNULMAZ(tmp_path: Path, py_proje: Path) -> None:
    veri = tmp_path / "v2"
    veri.mkdir()
    alan = CalismaAlani(id="b" * 12, kokler=[str(py_proje)], mod=Mod.planla)
    kayit = AjanAracKaydi(alan, PolitikaMotoru(veri), CheckpointDeposu(veri), KomutServisi())
    adlar = {s["function"]["name"] for s in kayit.semalar()}
    assert "proje_dosya_oku" in adlar
    assert "proje_dosya_yaz" not in adlar and "komut_calistir" not in adlar
    assert "proje_dosya_yaz" not in kayit.isleyiciler()
    # sema gorunmese de dogrudan cagri yine reddedilir
    with pytest.raises(YetkiYok):
        kayit.yazma.dosya_yaz("x.txt", "y")


def test_onayli_modda_yazma_onay_bekler(tmp_path: Path, py_proje: Path) -> None:
    veri = tmp_path / "v3"
    veri.mkdir()
    alan = CalismaAlani(id="c" * 12, kokler=[str(py_proje)], mod=Mod.onayli)
    politika = PolitikaMotoru(veri)
    kayit = AjanAracKaydi(alan, politika, CheckpointDeposu(veri), KomutServisi())
    adlar = {s["function"]["name"] for s in kayit.semalar()}
    assert "proje_dosya_yaz" in adlar  # sorulabilir: sunulur

    with pytest.raises(OnayGerekli) as bilgi:
        kayit.yazma.dosya_yaz("onayli.txt", "x")
    assert not (py_proje / "onayli.txt").exists()  # onaysiz YAZILMADI

    # isleyici uzerinden modele anlasilir sonuc doner
    sonuc = kayit.isleyiciler()["proje_dosya_yaz"](yol="onayli.txt", icerik="x")
    assert sonuc["karar"] == "onay_bekliyor"

    politika.onaylar.karar_ver(bilgi.value.onay["id"], True)
    kayit.yazma.dosya_yaz("onayli.txt", "x")
    assert (py_proje / "onayli.txt").read_text(encoding="utf-8") == "x"


# ------------------------------------------------------- checkpoint (A2.7)


def test_geri_alma_kullanici_degisikligini_korur(ortam, py_proje: Path) -> None:
    kayit, _, cp, _ = ortam
    hedef = py_proje / "src" / "hesap.py"
    h = dosya_hashi(hedef)
    s = kayit.yazma.dosya_yama("src/hesap.py", "a - b", "a + b", beklenen_hash=h)
    assert "a + b" in hedef.read_text(encoding="utf-8")

    # KULLANICI ayni dosyayi degistirdi
    hedef.write_text("# kullanicinin kendi degisikligi\n", encoding="utf-8")
    onizleme = cp.onizle(s["checkpoint"])
    assert onizleme["cakisma_var"] is True

    sonuc = cp.geri_al(s["checkpoint"])
    assert sonuc["tamam"] is False and sonuc["cakisan"]
    assert hedef.read_text(encoding="utf-8") == "# kullanicinin kendi degisikligi\n"


def test_geri_alma_temiz_durumda_calisir(ortam, py_proje: Path) -> None:
    kayit, _, cp, _ = ortam
    hedef = py_proje / "src" / "hesap.py"
    once = hedef.read_text(encoding="utf-8")
    s = kayit.yazma.dosya_yama("src/hesap.py", "a - b", "a + b", beklenen_hash=dosya_hashi(hedef))
    assert cp.geri_al(s["checkpoint"])["tamam"]
    assert hedef.read_text(encoding="utf-8") == once
    assert cp.onizle(s["checkpoint"])["geri_alindi"] is True


def test_olusturulan_dosya_geri_alinca_silinir(ortam, py_proje: Path) -> None:
    kayit, _, cp, _ = ortam
    s = kayit.yazma.dosya_yaz("gecici-yeni.txt", "x")
    assert cp.geri_al(s["checkpoint"])["tamam"]
    assert not (py_proje / "gecici-yeni.txt").exists()


def test_secili_dosya_geri_alma_ve_temizlik(ortam, py_proje: Path, tmp_path: Path) -> None:
    kayit, _, cp, _ = ortam
    s1 = kayit.yazma.dosya_yaz("bir.txt", "1")
    kayit.yazma.dosya_yaz("iki.txt", "2")
    sonuc = cp.geri_al(s1["checkpoint"], yollar=[str(py_proje / "bir.txt")])
    assert sonuc["geri_alinan"] and not (py_proje / "bir.txt").exists()
    assert (py_proje / "iki.txt").exists()
    assert cp.liste()[0]["arac"] == "dosya_yaz"
    assert cp.temizle(saklanan=1) >= 0


# ----------------------------------------------------------- terminal (A2.4)


async def test_komut_cikis_kodu_ve_cikti(py_proje: Path) -> None:
    s = KomutServisi()
    is_ = await s.baslat("echo selam", py_proje)
    await s.bekle(is_)
    ozet = s.ozet(is_)
    assert ozet["durum"] == "bitti" and ozet["cikis_kodu"] == 0 and "selam" in ozet["cikti"]

    hatali = await s.baslat("exit 7" if sys.platform == "win32" else "exit 7", py_proje)
    await s.bekle(hatali)
    assert s.ozet(hatali)["cikis_kodu"] == 7  # GERCEK cikis kodu


async def test_komut_zaman_asiminda_agac_kapanir(py_proje: Path) -> None:
    bekle = "ping -n 30 127.0.0.1 > nul" if sys.platform == "win32" else "sleep 30"
    s = KomutServisi()
    is_ = await s.baslat(bekle, py_proje, timeout=2)
    await s.bekle(is_)
    ozet = s.ozet(is_)
    assert ozet["durum"] == "zaman_asimi" and ozet["sure_sn"] < 10
    assert is_.surec is not None and is_.surec.returncode is not None  # surec gercekten oldu


async def test_arka_plan_isi_ve_durdurma(py_proje: Path) -> None:
    bekle = "ping -n 30 127.0.0.1 > nul" if sys.platform == "win32" else "sleep 30"
    s = KomutServisi()
    is_ = await s.baslat(bekle, py_proje, timeout=600, arka_plan=True)
    assert s.ozet(is_)["durum"] == "calisiyor"
    sonuc = await s.durdur(is_.durum.id)
    assert sonuc["durum"] == "durduruldu"
    assert is_.surec is not None and is_.surec.returncode is not None


async def test_bos_komut_ve_olmayan_klasor(py_proje: Path) -> None:
    s = KomutServisi()
    with pytest.raises(UygulamaHatasi):
        await s.baslat("   ", py_proje)
    with pytest.raises(UygulamaHatasi):
        await s.baslat("echo x", py_proje / "yok-klasor")


async def test_cikti_siniri(py_proje: Path) -> None:
    from app.agent import terminal as t

    s = KomutServisi()
    komut = (
        "python -c \"print('x'*200)\" "
        if sys.platform == "win32"
        else "python -c \"print('x'*200)\""
    )
    is_ = await s.baslat(komut, py_proje)
    await s.bekle(is_)
    kirpik, kesildi = t._kirp("y" * 100, 40)
    assert kesildi and "atlandi" in kirpik and len(kirpik) < 100


def test_ortam_allowlist_sir_sizdirmaz(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-SAHTE")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_SAHTE")
    ortam = ortam_allowlist()
    assert "OPENROUTER_API_KEY" not in ortam and "GITHUB_TOKEN" not in ortam
    assert "PATH" in ortam and ortam["PYTHONIOENCODING"] == "utf-8"


# --------------------------------------------------------------- git (A2.6)


def _git(*a: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, timeout=30)


@pytest.mark.skipif(shutil.which("git") is None, reason="git yok")
def test_git_durum_diff_ve_gecmis(ortam, py_proje: Path) -> None:
    kayit, *_ = ortam
    _git("init", "-q", cwd=py_proje)
    _git("config", "user.email", "t@test", cwd=py_proje)
    _git("config", "user.name", "test", cwd=py_proje)
    _git("add", "-A", cwd=py_proje)
    _git("commit", "-qm", "ilk", cwd=py_proje)

    durum = kayit.git.git_durum()
    assert durum["repo"] is True and durum["temiz"] is True

    kayit.yazma.dosya_yama(
        "src/hesap.py", "a - b", "a + b", beklenen_hash=dosya_hashi(py_proje / "src" / "hesap.py")
    )
    durum2 = kayit.git.git_durum()
    assert durum2["temiz"] is False and any("hesap.py" in d["yol"] for d in durum2["degisenler"])
    assert "a + b" in kayit.git.git_diff()["diff"]
    assert kayit.git.git_gecmis(adet=5)["commitler"]


def test_git_olmayan_klasorde_anlasilir_sonuc(ortam) -> None:
    kayit, *_ = ortam
    durum = kayit.git.git_durum()
    assert durum.get("repo") is False or durum.get("git") is False or "hata" in durum


def test_git_kok_disi_reddedilir(ortam, tmp_path: Path) -> None:
    kayit, *_ = ortam
    assert kayit.git.git_durum(str(tmp_path))["karar"] == "ret"


# ----------------------------------------- UCTAN UCA: oku -> yama -> test -> geri al


async def test_uctan_uca_hata_duzeltme_dongusu(ortam, py_proje: Path) -> None:
    """Kabul A2 ana senaryosu: testi kirik proje duzeltilir, test gecer, sonra geri alinir."""
    kayit, _, cp, _ = ortam

    # 1) test BASARISIZ
    once = await asyncio.to_thread(
        kayit.komut_calistir, f'"{sys.executable}" -m pytest -q tests', timeout=120
    )
    assert once["cikis_kodu"] != 0

    # 2) oku -> hatayi bul
    okunan = kayit.okuma.dosya_oku("src/hesap.py")
    assert "a - b" in okunan["icerik"]

    # 3) yama (beklenen hash ile)
    h = dosya_hashi(py_proje / "src" / "hesap.py")
    yama = kayit.yazma.dosya_yama("src/hesap.py", "a - b  # hatali", "a + b", beklenen_hash=h)

    # 4) test GECER
    sonra = await asyncio.to_thread(
        kayit.komut_calistir, f'"{sys.executable}" -m pytest -q tests', timeout=120
    )
    assert sonra["cikis_kodu"] == 0, sonra["cikti"][-500:]

    # 5) geri al -> dosya eski haline doner
    assert cp.geri_al(yama["checkpoint"])["tamam"]
    assert "a - b" in (py_proje / "src" / "hesap.py").read_text(encoding="utf-8")


async def test_ts_projesinde_okuma_ve_yama(tmp_path: Path) -> None:
    """Python disinda bir dilde de ayni dongu (derleyici olmadan: dosya duzeyinde)."""
    kok = tmp_path / "ts proje"
    (kok / "src").mkdir(parents=True)
    (kok / "src" / "topla.ts").write_text(
        "export function topla(a: number, b: number): number {\n  return a - b;\n}\n",
        encoding="utf-8",
    )
    veri = tmp_path / "v4"
    veri.mkdir()
    alan = CalismaAlani(id="d" * 12, kokler=[str(kok)], mod=Mod.otomatik)
    kayit = AjanAracKaydi(alan, PolitikaMotoru(veri), CheckpointDeposu(veri), KomutServisi())

    assert kayit.okuma.glob_bul("**/*.ts")["sayi"] == 1
    h = dosya_hashi(kok / "src" / "topla.ts")
    kayit.yazma.dosya_yama("src/topla.ts", "a - b", "a + b", beklenen_hash=h)
    assert "a + b" in (kok / "src" / "topla.ts").read_text(encoding="utf-8")


def test_kapsam_ve_yardimcilar(ortam, py_proje: Path) -> None:
    _, _, _, kapsam = ortam
    assert kapsam.goreli(py_proje / "src" / "hesap.py") == str(Path("src") / "hesap.py")
    assert kapsam.kok_of(py_proje / "src") == py_proje
    bos = KokKapsami([])
    with pytest.raises(YetkiYok):
        bos.coz("x.txt")


def test_ajan_araclari_yalniz_projede_acilir(tmp_path: Path, py_proje: Path) -> None:
    """Kisisel kapsamda (proje yok) kod araclari VERILMEZ."""
    from app.services.sohbet import VARSAYILAN_ALAN_ID, SohbetServisi

    veri = tmp_path / "v5"
    veri.mkdir()
    servis = SohbetServisi.__new__(SohbetServisi)
    servis.politika = PolitikaMotoru(veri)
    servis.checkpointler = CheckpointDeposu(veri)
    servis.komutlar = KomutServisi()
    kisisel = CalismaAlani(id=VARSAYILAN_ALAN_ID, kokler=[str(py_proje)])
    assert servis.ajan_araclari(kisisel) is None
    proje = CalismaAlani(id="e" * 12, kokler=[str(py_proje)])
    assert servis.ajan_araclari(proje) is not None


def test_dosya_araclari_tekil_sonuc_sozlesmesi(ortam) -> None:
    """Tum okuma araclari ayni hata sozlesmesini kullanir: {'hata', 'karar': 'ret'}."""
    kayit, *_ = ortam
    for cagri in (
        lambda: kayit.okuma.dosya_oku("C:\\Windows\\win.ini"),
        lambda: kayit.okuma.klasor_listele("C:\\Windows"),
        lambda: kayit.okuma.glob_bul("*.py", "C:\\Windows"),
        lambda: kayit.okuma.icerik_ara("x", "C:\\Windows"),
    ):
        sonuc = cagri()
        assert sonuc.get("karar") == "ret" and "hata" in sonuc


async def test_komut_servisi_hepsini_durdurur(py_proje: Path) -> None:
    bekle = "ping -n 30 127.0.0.1 > nul" if sys.platform == "win32" else "sleep 30"
    s = KomutServisi()
    i1 = await s.baslat(bekle, py_proje, timeout=600, arka_plan=True)
    i2 = await s.baslat(bekle, py_proje, timeout=600, arka_plan=True)
    await s.hepsini_durdur()
    await asyncio.sleep(0.1)
    assert i1.surec.returncode is not None and i2.surec.returncode is not None
