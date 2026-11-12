"""degerlendir.py birim testleri: model ya da gercek Claude Code cagirmadan harness mantigi
(kosu dongusu, onay sayimi, zaman asimi, kota ayrimi, Claude Code JSON ayristirma, rapor)."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from app import degerlendir as d

GOREV = {"id": "g1", "kategori": "hata", "dil": "py", "hedef": "duzelt", "kabul": ["test gecsin"],
         "max_adim": 9, "korunan": [], "dosyalar": {}, "kontroller": []}  # fmt: skip


def _kosu(gorev="g1", kategori="hata", durum="basarili", basari=True, **ek) -> dict:
    k = {"gorev": gorev, "kategori": kategori, "ajan_durumu": durum, "basari": basari,
         "yanlis_basari_beyani": durum == "basarili" and not basari, "mudahale": 0,
         "arac_hatasi": 0, "sure_sn": 1.5, "token": 10, "adim": 3,
         "kontrol_nedeni": "a|b\nc"}  # fmt: skip
    return k | ek


@pytest.fixture
def sahte_kontrol(monkeypatch):
    sonuc = {"basari": True, "neden": ""}
    monkeypatch.setattr(d, "kur", lambda g, p: {})
    monkeypatch.setattr(d, "gizli_kontrol", lambda g, p, k: dict(sonuc))
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    return sonuc


class SahteStudio:
    def __init__(self, durumlar: list[dict]) -> None:
        self.durumlar = durumlar
        self.onaylar: list[str] = []
        self.islemler: list[str] = []

    def proje_ac(self, *a, **k) -> None:
        pass

    def gorev(self, *a, **k) -> dict:
        return {"id": "r1", "adimlar": []}

    def durum(self, rid: str) -> dict:
        return self.durumlar.pop(0) if len(self.durumlar) > 1 else self.durumlar[0]

    def onay(self, oid: str, kabul: bool) -> None:
        self.onaylar.append(oid)

    def islem(self, rid: str, islem: str) -> dict:
        self.islemler.append(islem)
        return {"durum": "iptal", "adimlar": [], "hata": ""}


def test_ozet_tablo_olculemeyeni_ayirir_kararsizi_bulur() -> None:
    kosular = [_kosu(), _kosu(basari=False), _kosu("g2", "kesif", durum="saglayici_limiti",
               basari=False), _kosu("g3", "kesif", durum="zaman_asimi", basari=False,
               maliyet_usd=0.5)]  # fmt: skip
    o = d.ozet_tablo(kosular)
    assert (o["kosu"], o["olculemedi"], o["olculemeyen_gorevler"]) == (3, 1, ["g2"])
    assert o["basari_yuzde"] == 33.3
    assert o["kategori"]["kesif"] == {"kosu": 1, "basari_yuzde": 0.0}
    assert o["yanlis_basari_beyani"] == 1
    assert o["zaman_asimi"] == 1
    assert o["kararsiz_gorevler"] == ["g1"]
    assert o["toplam_maliyet_usd"] == 0.5
    assert d.ozet_tablo([])["basari_yuzde"] == 0.0


def test_markdown_tablo_ve_kacis() -> None:
    kosular = [_kosu(), _kosu(basari=False)]
    rapor = {"zaman": "Z", "ozet": d.ozet_tablo(kosular), "kosular": kosular,
             "surumler": {"model": "m", "saglayici": "s", "gorev_seti": "v1",
                          "ortam": {"cpu": "c", "ram_gb": 16}}}  # fmt: skip
    md = d.markdown(rapor)
    assert "| hata | 2 | 50.0 |" in md
    assert "| g1 | basarili | KALDI |" in md
    assert "a/b c" in md  # boru ve satir sonu tabloyu bozmaz
    assert "kararsiz gorevler: g1" in md


def test_kos_onaylari_sayar_ve_basarili_biter(sahte_kontrol) -> None:
    bekleyen = {
        "durum": "onay_bekliyor",
        "adimlar": [
            {"durum": "onay_bekliyor", "onay_id": "o1"},
            {"durum": "tamam", "onay_id": None},
        ],
    }
    bitti = {"durum": "basarili", "adimlar": [{"durum": "tamam"}, {"durum": "hata"}],
             "kullanim": {"adim": 4, "token": 99}}  # fmt: skip
    s = SahteStudio([bekleyen, bitti])
    k = d.kos(s, GOREV, None, sure_siniri=30)
    assert s.onaylar == ["o1"]
    assert (k["ajan_durumu"], k["basari"], k["mudahale"]) == ("basarili", True, 1)
    assert (k["arac_hatasi"], k["adim"], k["token"]) == (1, 4, 99)
    assert k["ilk_adim_sn"] is not None


def test_kos_yanlis_basari_beyani_ve_karar_mudahalesi(sahte_kontrol) -> None:
    sahte_kontrol |= {"basari": False, "neden": "kontrol 0"}
    k = d.kos(SahteStudio([{"durum": "basarili", "adimlar": []}]), GOREV, None, 30)
    assert k["yanlis_basari_beyani"] is True
    k = d.kos(SahteStudio([{"durum": "karar_bekliyor", "adimlar": []}]), GOREV, None, 30)
    assert k["mudahale"] == 1


def test_kos_kota_hatasi_olculemedi_sayilir(sahte_kontrol) -> None:
    s = SahteStudio([{"durum": "basarisiz", "adimlar": [], "hata": "OpenRouter 429"}])
    assert d.kos(s, GOREV, None, 30)["ajan_durumu"] == "saglayici_limiti"


def test_kos_zaman_asiminda_iptal_eder(sahte_kontrol) -> None:
    s = SahteStudio([{"durum": "calisiyor", "adimlar": []}])
    k = d.kos(s, GOREV, None, sure_siniri=0)
    assert k["ajan_durumu"] == "zaman_asimi"
    assert s.islemler == ["iptal"]


def _cc_calistir(monkeypatch, stdout: str = "", hata: Exception | None = None) -> list:
    cagrilar: list = []

    def calistir(argv, **k):
        cagrilar.append(argv)
        if hata:
            raise hata
        return SimpleNamespace(stdout=stdout, returncode=0)

    monkeypatch.setattr(d.subprocess, "run", calistir)
    monkeypatch.setattr(d, "claude_exe", lambda: "claude.exe")
    return cagrilar


def test_kos_claude_code_basarili_json(monkeypatch, sahte_kontrol) -> None:
    veri = {"subtype": "success", "is_error": False, "session_id": "s1", "num_turns": 5,
            "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": None},
            "total_cost_usd": 0.12, "modelUsage": {"claude-opus-5-5": {}}}  # fmt: skip
    cagrilar = _cc_calistir(monkeypatch, "log satiri\n" + json.dumps(veri))
    k = d.kos_claude_code(GOREV, None, 60, 2.0, model="opus")
    assert (k["ajan_durumu"], k["adim"], k["token"], k["model"]) == (
        "basarili",
        5,
        15,
        "claude-opus-5-5",
    )
    argv = cagrilar[0]
    assert argv[argv.index("--max-turns") + 1] == "9"
    assert argv[-2:] == ["--model", "opus"]
    assert "Kabul: test gecsin" in argv[2]


@pytest.mark.parametrize(("stdout", "beklenen"), [
    (json.dumps({"subtype": "error_max_turns", "result": "doldu"}), "error_max_turns"),
    ("json degil", "basarisiz"),
    ("", "basarisiz"),
])  # fmt: skip
def test_kos_claude_code_hata_durumlari(monkeypatch, sahte_kontrol, stdout, beklenen) -> None:
    _cc_calistir(monkeypatch, stdout)
    k = d.kos_claude_code(GOREV, None, 60, 2.0)
    assert k["ajan_durumu"] == beklenen
    assert "--model" not in json.dumps(k)


def test_kos_claude_code_zaman_asimi(monkeypatch, sahte_kontrol) -> None:
    _cc_calistir(monkeypatch, hata=subprocess.TimeoutExpired("claude", 1))
    assert d.kos_claude_code(GOREV, None, 1, 2.0)["ajan_durumu"] == "zaman_asimi"


def test_claude_exe_ve_argv(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(d.shutil, "which", lambda ad: None)
    assert d.claude_exe() == "claude"
    exe = tmp_path / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert d.claude_exe() == str(exe)
    assert d._argv(["{py}", "-c", "{node}", "{dotnet}"])[1:] == ["-c", "node", "dotnet"]


def test_ortam_bilgisi_powershell_ciktisi(monkeypatch) -> None:
    monkeypatch.setattr(d.sys, "platform", "win32")
    monkeypatch.setattr(
        d.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="Islemci X\nGPU A\nGPU B\n")
    )
    b = d.ortam_bilgisi()
    assert (b["cpu"], b["gpu"]) == ("Islemci X", "GPU A, GPU B")

    def bozuk(*a, **k):
        raise OSError

    monkeypatch.setattr(d.subprocess, "run", bozuk)
    assert "gpu" not in d.ortam_bilgisi()


def test_sil_salt_okunur_dosyayi_da_siler(tmp_path) -> None:
    import os
    import stat

    f = tmp_path / "k" / "nesne"
    f.parent.mkdir()
    f.write_text("x")
    os.chmod(f, stat.S_IREAD)
    d.sil(tmp_path / "k")
    assert not (tmp_path / "k").exists()


def test_main_claude_code_rapor_yazar(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(d, "gorevleri_yukle", lambda: ("v9", [GOREV, {**GOREV, "id": "g2"}]))
    monkeypatch.setattr(d, "kos_claude_code", lambda g, p, s, b, m: _kosu(
        g["id"], maliyet_usd=0.1, model="claude-opus-5-5"))  # fmt: skip
    monkeypatch.setattr(d.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="2.1.322\n"))
    monkeypatch.setattr(d, "ortam_bilgisi", lambda: {})
    monkeypatch.setattr(d.tempfile, "mkdtemp", lambda prefix: str(tmp_path / "calisma"))
    rapor = tmp_path / "rapor"
    assert d.main(["--ajan", "claude-code", "--gorev", "g2", "--tekrar", "2",
                   "--rapor", str(rapor)]) == 0  # fmt: skip
    js = json.loads(next(rapor.glob("rapor-claude-code-*.json")).read_text(encoding="utf-8"))
    assert js["surumler"]["uygulama"] == "2.1.322"
    assert [k["gorev"] for k in js["kosular"]] == ["g2", "g2"]
    assert js["ozet"]["basari_yuzde"] == 100.0
    assert len(next(rapor.glob("kosular-*.jsonl")).read_text(encoding="utf-8").splitlines()) == 2
    assert "[2] g2 #2: GECTI" in capsys.readouterr().out


def test_main_yerel_harness_hatasi_rapora_girer(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(d, "KOK", tmp_path)  # gercek data/ayarlar.json okunmaz
    monkeypatch.setattr(d, "gorevleri_yukle", lambda: ("v9", [GOREV]))
    monkeypatch.setattr(d.tempfile, "mkdtemp", lambda prefix: str(tmp_path / "calisma"))
    monkeypatch.setattr(d, "ortam_bilgisi", lambda: {})
    monkeypatch.delenv("YAS_VERI_DIZINI", raising=False)

    from app import cli, sdk

    class Sunucu:
        should_exit = False

    sunucu = Sunucu()
    monkeypatch.setattr(cli, "_sunucu_baslat", lambda: (sunucu, "http://x", "k"))
    yenilendi = []

    class Studio:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            pass

        def bilgi(self) -> dict:
            return {"surum": "0.1.0"}

        def openrouter_listesi_yenile(self) -> None:
            yenilendi.append(1)

    monkeypatch.setattr(sdk, "Studio", Studio)
    sira = iter([RuntimeError("baglanti koptu"), _kosu()])

    def kos(s, g, proje, sure):
        x = next(sira)
        if isinstance(x, Exception):
            raise x
        (proje / "x").parent.mkdir(parents=True, exist_ok=True)
        return x

    monkeypatch.setattr(d, "kos", kos)
    rapor = tmp_path / "rapor"
    assert d.main(["--openrouter-model", "x/y", "--tekrar", "2", "--rapor", str(rapor)]) == 0
    js = json.loads(next(rapor.glob("rapor-2*.json")).read_text(encoding="utf-8"))
    assert [k["ajan_durumu"] for k in js["kosular"]] == ["harness_hatasi", "basarili"]
    assert js["ozet"]["olculemedi"] == 1
    assert js["surumler"]["model"] == "x/y" and js["surumler"]["uygulama"] == "0.1.0"
    assert yenilendi == [1] and sunucu.should_exit is True
    assert not (tmp_path / "calisma" / "projeler").exists()  # --sakla yoksa silinir
    assert (rapor / next(rapor.glob("rapor-2*.md")).name).exists()
