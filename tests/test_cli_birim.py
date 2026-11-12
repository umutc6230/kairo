"""cli.py surec ici birim testleri (A10.3). Gercek uctan uca akis test_a10_cli_sdk.py'de alt
surecte kosar ve kapsama girmez; burada ayni dallar sahte Studio ile surec icinde denenir."""

from __future__ import annotations

import json

import pytest

from app import cli


def _run(durum: str, adimlar: list[dict] | None = None, ozet: str = "", hata: str = "") -> dict:
    return {"id": "r1", "durum": durum, "adimlar": adimlar or [],
            "kullanim": {"adim": len(adimlar or [])},
            "sonuc": {"ozet": ozet, "kanit": [1] if ozet else []}, "hata": hata}  # fmt: skip


class SahteStudio:
    def __init__(self, akis: list[dict], ilk_durum: str = "calisiyor") -> None:
        self.akis = akis
        self.ilk_durum = ilk_durum
        self.cagrilar: list[tuple] = []

    def onay(self, oid: str, kabul: bool) -> None:
        self.cagrilar.append(("onay", oid, kabul))

    def durum(self, run_id: str) -> dict:
        return {"durum": self.ilk_durum}

    def islem(self, run_id: str, islem: str) -> None:
        self.cagrilar.append(("islem", run_id, islem))

    def proje_ac(self, yol: str, guven: str, mod: str) -> dict:
        self.cagrilar.append(("proje", yol, guven, mod))
        return {"id": "p1"}

    def gorev(self, hedef, kabul, max_adim, izole) -> dict:
        self.cagrilar.append(("gorev", hedef, tuple(kabul), max_adim, izole))
        return {"id": "r1"}

    def izle(self, run_id: str, aralik: float):
        yield from self.akis


ADIM_ONAY = {"no": 2, "arac": "proje_dosya_yaz", "durum": "onay_bekliyor", "onay_id": "o9"}
ADIM_TAMAM = {"no": 1, "arac": "proje_dosya_oku", "durum": "tamam", "onay_id": None}


def test_yeni_gorev_basarili_metin(capsys) -> None:
    s = SahteStudio([_run("calisiyor"), _run("basarili", [ADIM_TAMAM], ozet="bitti")])
    args = cli.arg_ayristir(["duzelt", "--proje", "P", "--kabul", "test", "--max-adim", "5",
                             "--izole", "--mod", "otomatik"])  # fmt: skip
    assert cli.calistir(args, s) == 0
    assert ("proje", "P", "sinirli", "otomatik") in s.cagrilar
    assert ("gorev", "duzelt", ("test",), 5, True) in s.cagrilar
    cikti = capsys.readouterr().out
    assert "[calisiyor] adim 0" in cikti
    assert "son: proje_dosya_oku tamam" in cikti
    assert "Sonuc: basarili - bitti" in cikti


def test_onay_bekleyince_kod_3_ve_devam_komutu(capsys) -> None:
    s = SahteStudio([_run("onay_bekliyor", [ADIM_TAMAM, ADIM_ONAY])])
    assert cli.calistir(cli.arg_ayristir(["h", "--proje", "P"]), s) == 3
    cikti = capsys.readouterr().out
    assert "--onayla o9 --devam r1" in cikti


def test_json_cikti_ve_bekleyen_onaylar(capsys) -> None:
    s = SahteStudio([_run("onay_bekliyor", [ADIM_ONAY])])
    assert cli.calistir(cli.arg_ayristir(["h", "--proje", "P", "--json"]), s) == 3
    satirlar = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert satirlar[0]["tur"] == "run"
    assert satirlar[-1]["tur"] == "sonuc"
    assert satirlar[-1]["bekleyen_onaylar"] == [
        {"adim": 2, "arac": "proje_dosya_yaz", "onay_id": "o9"}
    ]


def test_devam_onayla_reddet_ve_durmus_gorevi_surdurur(capsys) -> None:
    s = SahteStudio([_run("basarisiz", hata="test kaldi")], ilk_durum="onay_bekliyor")
    args = cli.arg_ayristir(["--devam", "r1", "--onayla", "a", "--reddet", "b"])
    assert cli.calistir(args, s) == 1
    assert s.cagrilar[:3] == [("onay", "a", True), ("onay", "b", False), ("islem", "r1", "devam")]
    assert "Sonuc: basarisiz - test kaldi" in capsys.readouterr().out


def test_devam_bitmis_goreve_islem_gondermez() -> None:
    s = SahteStudio([_run("dogrulanmadi")], ilk_durum="basarili")
    assert cli.calistir(cli.arg_ayristir(["--devam", "r1"]), s) == 2
    assert not [c for c in s.cagrilar if c[0] == "islem"]


@pytest.mark.parametrize("argv", [[], ["hedef"], ["--proje", "P"]])
def test_eksik_arguman_kod_4(argv, capsys) -> None:
    assert cli.calistir(cli.arg_ayristir(argv), SahteStudio([])) == 4
    assert "hedef ve --proje gerekli" in capsys.readouterr().err


def test_bilinmeyen_durum_kod_4() -> None:
    assert cli.calistir(cli.arg_ayristir(["h", "--proje", "P"]), SahteStudio([_run("tuhaf")])) == 4


def test_main_studio_hatasi_kod_4(monkeypatch, capsys) -> None:
    class Sunucu:
        should_exit = False

    sunucu = Sunucu()
    monkeypatch.setattr(cli, "_sunucu_baslat", lambda: (sunucu, "http://x", "k"))

    class HataliStudio:
        def __init__(self, *a) -> None:
            pass

        def __enter__(self):
            raise cli.StudioHatasi("baglanilamadi")

        def __exit__(self, *a) -> None:
            pass

    monkeypatch.setattr(cli, "Studio", HataliStudio)
    assert cli.main(["h", "--proje", "P"]) == 4
    assert "Hata: baglanilamadi" in capsys.readouterr().err
    assert sunucu.should_exit is True  # sunucu her durumda kapatilir


def test_main_openrouter_modeli_ayar_yazar_ve_listeyi_yeniler(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("YAS_VERI_DIZINI", str(tmp_path))

    class Sunucu:
        should_exit = False

    monkeypatch.setattr(cli, "_sunucu_baslat", lambda: (Sunucu(), "http://x", "k"))
    yenilendi = []

    class KayitStudio(SahteStudio):
        def __init__(self, *a) -> None:
            super().__init__([_run("basarili", ozet="ok")])

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            pass

        def openrouter_listesi_yenile(self) -> dict:
            yenilendi.append(True)
            return {}

    monkeypatch.setattr(cli, "Studio", KayitStudio)
    assert cli.main(["h", "--proje", "P", "--openrouter-model", "x/y"]) == 0
    assert yenilendi == [True]
    from app.services.ayarlar import AyarDeposu

    a = AyarDeposu(tmp_path).oku()
    assert (a.saglayici, a.or_model) == ("openrouter", "x/y")
