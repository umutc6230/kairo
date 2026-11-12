"""Claude Code esdegerlik eksikleri (2026-11-12): konusma surekliligi, soru_sor, yeni hook
olaylari, ozel slash komutlari (.claude/commands) ve sohbet ozeti (/compact)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from test_a3_ajan import (
    PYTEST,
    SahteModel,
    bitir,
    cagri,
    kur,
)

from app.agent.hooks import HookDeposu
from app.agent.runner import GECMIS_SINIRI, AdimDurum, Run, RunDurum, gecmis_ozeti
from app.exceptions import UygulamaHatasi
from app.services import cc_plugin as cc
from app.services.oturumlar import Mesaj, OturumDeposu


@pytest.fixture
def proje(tmp_path: Path) -> Path:
    # test_a3_ajan'daki ornek projeyle ayni (fixture ice aktarmak F811 uretiyor)
    p = tmp_path / "ornek proje"
    (p / "src").mkdir(parents=True)
    (p / "tests").mkdir()
    (p / "src" / "hesap.py").write_bytes(b"def topla(a, b):\n    return a - b  # hatali\n")
    (p / "tests" / "test_hesap.py").write_bytes(
        b"import sys\nsys.path.insert(0, 'src')\nfrom hesap import topla\n\n"
        b"def test_topla():\n    assert topla(2, 3) == 5\n"
    )
    return p


# ------------------------------------------------------------ konusma surekliligi


async def test_sonraki_gorev_onceki_turun_ozetini_gorur(tmp_path, proje) -> None:
    model = SahteModel(
        [
            cagri("komut_calistir", komut=PYTEST.replace("tests", "--version"), timeout=60),
            cagri("gorevi_bitir", ozet="pytest surumu okundu: kurulu", kanit_adimlari=[1]),
            cagri("gorevi_bitir", ozet="ikinci tur", kanit_adimlari=[]),
        ]
    )
    runner, depo, _, _ = kur(tmp_path, proje, model)
    ilk = await bitir(runner, (await runner.baslat("pytest kurulu mu bak")).id)
    assert ilk.durum is RunDurum.basarili

    ikinci = await runner.baslat("peki onu calistir", onceki=ilk.id)
    ikinci = await bitir(runner, ikinci.id)

    assert ikinci.onceki == ilk.id
    ilk_mesaj = ikinci.mesajlar[0]["content"]
    assert "pytest kurulu mu bak" in ilk_mesaj and "pytest surumu okundu" in ilk_mesaj
    assert ilk_mesaj.index("ONCEKI TURLAR") < ilk_mesaj.index("GOREV: peki onu calistir")
    # ucuncu tur: ozet ZINCIRLENIR (ilk iki turun ikisi de gorunur)
    ucuncu = await runner.baslat("ucuncu", onceki=ikinci.id)
    assert "pytest kurulu mu bak" in ucuncu.gecmis and "peki onu calistir" in ucuncu.gecmis
    await bitir(runner, ucuncu.id)
    assert depo.getir(ilk.id).mesajlar == ilk.mesajlar  # onceki gorev degismedi


async def test_onceki_yoksa_ya_da_bulunamazsa_gorev_normal_baslar(tmp_path, proje) -> None:
    runner, _, _, _ = kur(tmp_path, proje, SahteModel([]))
    run = await runner.baslat("tek basina", onceki="0" * 12)  # silinmis/olmayan gorev
    assert run.onceki == "" and run.mesajlar[0]["content"].startswith("GOREV: tek basina")
    await bitir(runner, run.id)


def test_gecmis_ozeti_sinirli_ve_en_yeni_tur_kalir() -> None:
    eski = Run(hedef="x", gecmis="ESKI " * 3000)
    eski.durum, eski.sonuc.ozet = RunDurum.basarili, "SON-SONUC"
    ozet = gecmis_ozeti(eski)
    assert len(ozet) <= GECMIS_SINIRI and ozet.endswith("SON-SONUC")


# ------------------------------------------------------------ soru_sor (AskUserQuestion)


async def test_soru_sor_gorevi_durdurur_cevap_arac_sonucu_olur(tmp_path, proje) -> None:
    model = SahteModel(
        [
            cagri("soru_sor", soru="Hangi dosya?", secenekler=["src/hesap.py", "tests"]),
            cagri("proje_dosya_oku", yol="src/hesap.py"),
            cagri("gorevi_bitir", ozet="okundu", kanit_adimlari=[2]),
        ]
    )
    runner, depo, _, _ = kur(tmp_path, proje, model)
    run = await runner.baslat("bir dosya oku", etkilesimli=True)
    run = await bitir(runner, run.id)

    assert run.durum is RunDurum.cevap_bekliyor
    assert run.adimlar[0].durum is AdimDurum.cevap_bekliyor
    assert run.kullanim.adim == 0  # soru butce yemez
    assert len(model.gorulen) == 1  # cevap gelmeden model TEKRAR cagrilmadi
    try:
        await runner.devam(run.id)
        raise AssertionError("cevapsiz devam edilmemeli")
    except UygulamaHatasi as e:
        assert "soru" in e.mesaj

    await runner.mesaj(run.id, "src/hesap.py")
    run = await bitir(runner, run.id)
    assert run.durum is RunDurum.basarili
    assert run.adimlar[0].durum is AdimDurum.tamam
    arac_mesaji = next(m for m in run.mesajlar if m.get("role") == "tool")
    assert json.loads(arac_mesaji["content"])["cevap"] == "src/hesap.py"
    assert not depo.getir(run.id).kuyruk  # cevap yonlendirme kuyruguna DUSMEDI


async def test_soru_sor_yalniz_etkilesimli_gorevde_sunulur(tmp_path, proje) -> None:
    gorulen: list[set[str]] = []

    class Kaydeden(SahteModel):
        async def sohbet(self, mesajlar, **kw):
            gorulen.append({t["function"]["name"] for t in kw.get("tools") or []})
            return await super().sohbet(mesajlar, **kw)

    model = Kaydeden(
        [
            cagri("soru_sor", soru="?"),  # headless: arac yok -> bilinmeyen arac hatasi, durmaz
            cagri("gorevi_bitir", ozet="x", kanit_adimlari=[]),
            cagri("gorevi_bitir", ozet="y", kanit_adimlari=[]),
        ]
    )
    runner, _, _, _ = kur(tmp_path, proje, model)
    headless = await bitir(runner, (await runner.baslat("zamanlanmis is")).id)
    assert "soru_sor" not in gorulen[0]
    assert headless.durum is RunDurum.dogrulanmadi  # cevap bekleyip ASILI KALMADI
    assert headless.adimlar[0].durum is AdimDurum.hata

    await bitir(runner, (await runner.baslat("sohbetten", etkilesimli=True)).id)
    assert "soru_sor" in gorulen[-1]


# ------------------------------------------------------------ hook olaylari


async def test_bildirim_hooku_soru_sorulunca_tetiklenir(tmp_path, proje) -> None:
    veri = tmp_path / "veri"
    veri.mkdir(exist_ok=True)
    iz = tmp_path / "iz.jsonl"
    betik = tmp_path / "hook.py"
    betik.write_text(
        "import sys\n"
        "veri = sys.stdin.read().replace('\\n', ' ')\n"
        f"open(r'{iz}', 'a', encoding='utf-8').write(veri + '\\n')\n",
        encoding="utf-8",
    )
    hooks = HookDeposu(veri)
    hooks.ekle({"ad": "bildir", "olay": "bildirim", "komut": f'"{sys.executable}" "{betik}"'})
    model = SahteModel([cagri("soru_sor", soru="Devam edeyim mi?")])
    runner, _, _, _ = kur(tmp_path, proje, model, hooks=hooks)
    run = await bitir(runner, (await runner.baslat("is", etkilesimli=True)).id)

    assert run.durum is RunDurum.cevap_bekliyor
    olay = json.loads(iz.read_text(encoding="utf-8").splitlines()[0])
    assert olay["olay"] == "bildirim" and olay["veri"]["tur"] == "soru"
    assert "Devam edeyim mi?" in olay["veri"]["metin"]


def test_claude_hook_olaylari_eslenir() -> None:
    assert cc.OLAY_ESLESME["SubagentStop"] == "alt_ajan_bitis"
    assert cc.OLAY_ESLESME["Notification"] == "bildirim"


# ------------------------------------------------------------ ozel slash komutlari


def test_komut_dosyalari_ad_alani_ve_frontmatter(tmp_path: Path) -> None:
    d = tmp_path / "commands"
    (d / "git").mkdir(parents=True)
    (d / "selam.md").write_text(
        "---\ndescription: Selam verir\nargument-hint: <kim>\n---\nSelam $ARGUMENTS, ilk: $1",
        encoding="utf-8",
    )
    (d / "git" / "ozet.md").write_text("Son commitleri ozetle", encoding="utf-8")
    (d / "not.txt").write_text("komut degil", encoding="utf-8")
    komutlar = {k["ad"]: k for k in cc.komut_dosyalari(d)}

    assert set(komutlar) == {"selam", "git:ozet"}
    assert komutlar["selam"]["aciklama"] == "Selam verir" and komutlar["selam"]["ipucu"] == "<kim>"
    assert (
        cc.komut_genislet(komutlar["selam"]["govde"], "Ali Veli", d) == "Selam Ali Veli, ilk: Ali"
    )
    assert cc.komut_dosyalari(tmp_path / "yok") == []


async def test_ozel_komut_api_proje_yalniz_guvenilirde_ve_kullaniciyi_ezer(
    app, istemci, tmp_path
) -> None:
    kullanici = app.state.kullanici_komut_dizini()
    kullanici.mkdir(parents=True)
    (kullanici / "ortak.md").write_text("KULLANICI govdesi", encoding="utf-8")
    (kullanici / "benim.md").write_text("---\ndescription: bana ozel\n---\nBenim $1", "utf-8")
    proje = tmp_path / "repo"
    (proje / ".claude" / "commands").mkdir(parents=True)
    (proje / ".claude" / "commands" / "ortak.md").write_text("PROJE govdesi", encoding="utf-8")

    async def adlar() -> dict:
        r = await istemci.get("/api/pluginler/komutlar")
        return {k["komut"]: k["kaynak"] for k in r.json()["komutlar"] if not k["plugin"]}

    assert await adlar() == {"ortak": "kullanici", "benim": "kullanici"}  # proje yok
    alan = (await istemci.post("/api/projeler", json={"yol": str(proje)})).json()
    assert (await adlar())["ortak"] == "kullanici"  # sinirli guven: proje komutu YOK
    await istemci.put(f"/api/projeler/{alan['id']}/guven", json={"guven": "guvenilir"})
    assert (await adlar())["ortak"] == "proje"

    r = await istemci.post("/api/pluginler/komut", json={"komut": "ortak", "arg": ""})
    assert r.json()["istem"] == "PROJE govdesi" and r.json()["kaynak"] == "proje"
    r = await istemci.post("/api/pluginler/komut", json={"komut": "benim", "arg": "x y"})
    assert r.json()["istem"] == "Benim x"
    r = await istemci.post("/api/pluginler/komut", json={"komut": "olmayan", "arg": ""})
    assert r.status_code == 404


# ------------------------------------------------------------ sohbet ozeti (/compact)


async def test_sohbet_ozetle_eskiyi_ozetler_son_turu_korur(app, istemci, veri, sunucu) -> None:
    depo = OturumDeposu(veri)
    o = depo.olustur()
    o.mesajlar = [
        Mesaj(rol="kullanici", metin="proje adi Kairo olsun"),
        Mesaj(rol="asistan", metin="tamam, Kairo"),
        Mesaj(rol="kullanici", metin="rengi turuncu yap"),
        Mesaj(rol="asistan", metin="turuncu yapildi"),
        Mesaj(rol="kullanici", metin="SON SORU"),
        Mesaj(rol="asistan", metin="SON CEVAP"),
    ]
    depo.kaydet(o)

    r = await istemci.post(f"/api/oturumlar/{o.id}/ozetle")
    assert r.status_code == 200, r.text
    assert r.json()["ozetlenen"] == 4
    yeni = depo.getir(o.id).mesajlar
    assert [m.rol for m in yeni] == ["kullanici", "asistan", "kullanici", "asistan"]
    assert (
        yeni[0].metin.startswith("[Önceki konuşmanın özeti]") and r.json()["ozet"] in yeni[0].metin
    )
    assert [m.metin for m in yeni[2:]] == ["SON SORU", "SON CEVAP"]
    giden = json.dumps(sunucu.istekler[-1], ensure_ascii=False, default=str)
    assert "proje adi Kairo olsun" in giden and "SON SORU" not in giden


async def test_sohbet_ozetle_kisa_sohbette_degistirmez(istemci, veri) -> None:
    depo = OturumDeposu(veri)
    o = depo.olustur()
    o.mesajlar = [Mesaj(rol="kullanici", metin="selam"), Mesaj(rol="asistan", metin="selam")]
    depo.kaydet(o)
    r = await istemci.post(f"/api/oturumlar/{o.id}/ozetle")
    assert r.status_code == 400 and len(depo.getir(o.id).mesajlar) == 2


async def test_bos_soru_hata_olur_gorev_durmaz(tmp_path, proje) -> None:
    model = SahteModel(
        [
            cagri("soru_sor", soru="   "),
            cagri("proje_dosya_oku", yol="src/hesap.py"),
            cagri("gorevi_bitir", ozet="okundu", kanit_adimlari=[2]),
        ]
    )
    runner, _, _, _ = kur(tmp_path, proje, model)
    run = await bitir(runner, (await runner.baslat("oku", etkilesimli=True)).id)
    assert run.adimlar[0].durum is AdimDurum.hata  # bos soru kullaniciya gitmez
    assert run.durum is not RunDurum.cevap_bekliyor


def test_komut_dosyalari_olmayan_dizin_ve_buyuk_dosya(tmp_path: Path) -> None:
    assert cc.komut_dosyalari(tmp_path / "yok") == []
    d = tmp_path / "commands"
    d.mkdir()
    (d / "kucuk.md").write_text("govde", encoding="utf-8")
    (d / "dev.md").write_text("x" * 200_001, encoding="utf-8")  # sinir ustu: atlanir
    (d / "not.txt").write_text("komut degil", encoding="utf-8")
    assert [k["ad"] for k in cc.komut_dosyalari(d)] == ["kucuk"]
