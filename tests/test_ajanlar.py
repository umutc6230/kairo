"""Kalici ajanlar: depo, FIFO kuyruk, ajanlar arasi mesaj ve dagitim dongusu (gercek runner)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.agent.ajanlar import MAX_ZINCIR, AjanDeposu, KuyrukOgesi
from app.exceptions import UygulamaHatasi


def test_olustur_klasor_ve_ad_kurallari(tmp_path: Path) -> None:
    d = AjanDeposu(tmp_path)
    a = d.olustur({"ad": "Arastirmaci", "aciklama": "web arastirmasi", "talimat": "Kisa yaz."})
    assert d.klasor(a).is_dir() and d.klasor(a).name == "calisma"
    with pytest.raises(UygulamaHatasi, match="Bu adda"):
        d.olustur({"ad": "arastirmaci"})
    with pytest.raises(UygulamaHatasi, match="adi"):
        d.olustur({"ad": "kotu/ad"})
    assert d.getir("ARASTIRMACI").id == a.id  # ad ile de bulunur


def test_fifo_kuyruk_ve_mesgulken_bekleme(tmp_path: Path) -> None:
    d = AjanDeposu(tmp_path)
    a = d.olustur({"ad": "Yazar"})
    for m in ("bir", "iki", "uc"):
        d.kuyruga_ekle(a.id, KuyrukOgesi(metin=m))
    _, oge = d.al(a.id)
    assert oge.metin == "bir"
    assert d.al(a.id) is None  # mesgul: ikinci is alinmaz
    d.basladi(a.id, "run1")
    d.bitti(a.id, "run1", "basarili", "tamam")
    _, oge = d.al(a.id)
    assert oge.metin == "iki"  # sira korunur
    x = d.getir(a.id)
    assert x.son_run == "run1" and [m.rol for m in x.konusma][:2] == ["gelen", "gelen"]


def test_duraklatilan_ajan_is_almaz_ve_zincir_siniri(tmp_path: Path) -> None:
    d = AjanDeposu(tmp_path)
    a = d.olustur({"ad": "A"})
    d.duzenle(a.id, {"duraklatildi": True})
    d.kuyruga_ekle(a.id, KuyrukOgesi(metin="x"))
    assert d.al(a.id) is None
    with pytest.raises(UygulamaHatasi, match="zinciri"):
        d.kuyruga_ekle(a.id, KuyrukOgesi(metin="y", zincir=MAX_ZINCIR + 1))


def test_sistem_metni_kimlik_talimat_not_ve_diger_ajanlar(tmp_path: Path) -> None:
    d = AjanDeposu(tmp_path)
    a = d.olustur({"ad": "Lider", "talimat": "Turkce yaz."})
    b = d.olustur({"ad": "Kodcu", "aciklama": "Python yazar"})
    d.hafizaya_ekle(a.id, "Kullanici kisa cevap sever.")
    m = d.sistem_metni(d.getir(a.id), [b])
    assert (
        "'Lider'" in m and "Turkce yaz." in m and "kisa cevap" in m and "Kodcu: Python yazar" in m
    )


async def test_api_ajan_mesaj_kuyruk_ve_ajanlar_arasi_cevap(istemci, app, monkeypatch) -> None:
    """Dagitim: ajan bosken mesaj hemen baslar; bitince cevap gonderen ajanin kuyruguna doner."""
    import types

    from app.agent.runner import Run, RunDurum, Sonuc

    depo = app.state.ajan_deposu
    runlar: dict[str, Run] = {}

    async def sahte_baslat(hedef, **kw):
        r = Run(hedef=hedef, ajan_id=kw.get("ajan_id", ""), calisma_koku=kw.get("calisma_koku", ""))
        r.durum, r.sonuc = RunDurum.basarili, Sonuc(ozet=f"bitti: {hedef[:30]}")
        runlar[r.id] = r
        return r

    ajan_runner = app.state.ajan_runner
    monkeypatch.setattr(ajan_runner, "baslat", sahte_baslat)
    monkeypatch.setattr(
        ajan_runner.depo, "getir", types.MethodType(lambda self, i: runlar[i], ajan_runner.depo)
    )

    lider = (await istemci.post("/api/ajanlar", json={"ad": "Lider"})).json()
    kodcu = (await istemci.post("/api/ajanlar", json={"ad": "Kodcu"})).json()
    r = await istemci.post(f"/api/ajanlar/{kodcu['id']}/mesaj", json={"metin": "merhaba"})
    assert r.status_code == 200 and r.json()["durum"] == "calisiyor"

    # Lider'in calisan isi Kodcu'ya mesaj atar (ajan araci)
    depo.kuyruga_ekle(lider["id"], KuyrukOgesi(metin="kodcuya sor"))
    await app.state.ajan_dagit()
    l_run = runlar[depo.getir(lider["id"]).aktif_run]
    sema, isl = ajan_runner.ajan_araclari(l_run)
    assert {s["function"]["name"] for s in sema} == {"ajana_mesaj", "ajan_notu"}
    assert isl["ajana_mesaj"](ajan="Kodcu", mesaj="fib yaz")["gonderildi"] == "Kodcu"
    assert "hata" in isl["ajana_mesaj"](ajan="Lider", mesaj="kendime")
    assert isl["ajan_notu"](**{"not": "Kodcu Python bilir"})["kaydedildi"] is True

    for _ in range(4):  # kapat -> sonraki isi al -> kapat -> cevap lidere doner
        await app.state.ajan_dagit()
    konusma = (await istemci.get(f"/api/ajanlar/{lider['id']}")).json()["konusma"]
    assert any("[Kodcu cevabi" in m["metin"] for m in konusma if m["rol"] == "gelen")
    assert "Kodcu Python bilir" in depo.getir(lider["id"]).hafiza
    assert (await istemci.delete(f"/api/ajanlar/{kodcu['id']}")).status_code == 200
    await asyncio.sleep(0)


async def test_telegram_izinli_sohbet_ajana_gider_izinsize_yalniz_kimlik(tmp_path: Path) -> None:
    import json

    import httpx

    from app.services.telegram import TelegramKanali

    giden: list[dict] = []

    def bot(r: httpx.Request) -> httpx.Response:
        yontem = r.url.path.rsplit("/", 1)[-1]
        if yontem == "sendMessage":
            giden.append(json.loads(r.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    t = TelegramKanali(tmp_path, transport=httpx.MockTransport(bot))
    d = t.kaydet({"token": "123456:ABCDEFGHIJKLMNOP", "izinli": ["42"], "aktif": True})
    assert d["token"] == "123456...MNOP" and d["izinli"] == [42]
    alinan: list[tuple] = []

    async def isle(chat, metin, ad):
        alinan.append((chat, metin, ad))
        return "ise aldi"

    async with httpx.AsyncClient(transport=httpx.MockTransport(bot)) as c:
        await t._isle(c, 42, "rapor yaz", {"from": {"first_name": "Umut"}}, isle)
        await t._isle(c, 999, "dosyalari sil", {}, isle)
    assert alinan == [(42, "rapor yaz", "Umut")]  # izinsiz sohbet ajana ULASMAZ
    assert giden[0] == {"chat_id": 42, "text": "ise aldi"}
    assert (
        giden[1]["chat_id"] == 999
        and "999" in giden[1]["text"]
        and "izinli degil" in giden[1]["text"]
    )
    assert t.durum()["bekleyen_kimlikler"] == [999]
    await t.gonder(42, "x" * 9000)  # uzun cevap parcalanir (Telegram 4096 siniri)
    assert [len(g["text"]) for g in giden[2:]] == [4000, 4000, 1000]


def test_cli_komutlari_ve_olay_isleme(tmp_path: Path, monkeypatch) -> None:
    from app.agent import cli_ajan

    monkeypatch.setattr(cli_ajan, "claude_yolu", lambda: "claude.exe")
    monkeypatch.setattr(cli_ajan, "codex_komutu", lambda: ["node", "codex.js"])
    k = cli_ajan.komut_kur(
        "claude", "selam", tmp_path, oturum="S1", tam_yetki=True, ek_sistem="kim"
    )
    assert k[:3] == ["claude.exe", "-p", "selam"] and "bypassPermissions" in k
    assert k[k.index("--resume") + 1] == "S1" and "--append-system-prompt" in k
    assert "acceptEdits" in cli_ajan.komut_kur("claude", "x", tmp_path)
    c = cli_ajan.komut_kur("codex", "selam", tmp_path, oturum="T1")
    assert c[-3:] == ["resume", "T1", "selam"] and "workspace-write" in c
    s = cli_ajan.CliSonuc()
    for e in [
        {"type": "system", "subtype": "init", "session_id": "abc"},
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "a"}}]
            },
        },
        {
            "type": "result",
            "result": "Yazdim.",
            "is_error": False,
            "total_cost_usd": 0.01,
            "session_id": "abc",
        },
    ]:
        cli_ajan.olay_isle("claude", e, s)
    assert (s.oturum, s.ozet, s.durum) == ("abc", "Yazdim.", "basarili") and s.log[0].startswith(
        "🔧 Write"
    )
    x = cli_ajan.CliSonuc()
    for e in [
        {"type": "thread.started", "thread_id": "t9"},
        {"type": "turn.failed", "error": {"message": "usage limit"}},
    ]:
        cli_ajan.olay_isle("codex", e, x)
    assert x.oturum == "t9" and x.durum == "basarisiz" and "usage limit" in x.ozet


def test_ajan_skill_olusturur_gunceller_surum_saklar_geri_alir(tmp_path: Path) -> None:
    from app.services.skiller import SkillDeposu

    claude = tmp_path / "claude"
    (claude / "hazir").mkdir(parents=True)
    (claude / "hazir" / "SKILL.md").write_text("---\nname: hazir\ndescription: x\n---\nA", "utf-8")
    d = SkillDeposu(
        tmp_path / "veri", [("claude", claude), ("uygulama", tmp_path / "veri" / "skills")]
    )
    assert d.ajan_kaydet("fatura-okuma", "Fatura PDF okur", "1. oku")["revizyon"] == 1
    with pytest.raises(UygulamaHatasi, match="revizyon 1"):  # okumadan guncelleme yok
        d.ajan_kaydet("fatura-okuma", "Fatura PDF okur", "2. yeni", okunan_revizyon=0)
    assert (
        d.ajan_kaydet("fatura-okuma", "Fatura PDF okur", "2. yeni", okunan_revizyon=1)["revizyon"]
        == 2
    )
    assert d.revizyonlar("fatura-okuma") == [
        {"revizyon": 1, "boyut": d.revizyonlar("fatura-okuma")[0]["boyut"]}
    ]
    d.geri_al("fatura-okuma", 1)
    assert "1. oku" in (tmp_path / "veri" / "skills" / "fatura-okuma" / "SKILL.md").read_text(
        "utf-8"
    )
    with pytest.raises(UygulamaHatasi, match="claude kaynakli"):  # Claude skill'i korunur
        d.ajan_kaydet("hazir", "x", "ezme")
