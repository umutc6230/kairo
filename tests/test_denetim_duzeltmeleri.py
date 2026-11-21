"""Denetim bulgulari regresyon testleri: Faz 1 guvenlik + Faz 2 arka uc + uzak erisim."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import pytest

from app import uzak
from app.agent.araclar import AjanAracKaydi
from app.agent.checkpoints import Checkpoint, CheckpointDeposu, DosyaDurumu, Islem
from app.agent.dosyalar import AjanDosyaAraclari, KokKapsami
from app.agent.github_araclari import GithubAraclari
from app.agent.izolasyon import KONTEYNER_KOK, KonteynerAdaptoru
from app.agent.mcp import McpYoneticisi
from app.agent.mcp_oauth import kesif as oauth_kesif
from app.agent.notebook import _yeni_hucre
from app.agent.ozet import mesaj_token as ozet_mesaj_token
from app.agent.policy import (
    CalismaAlani,
    Guven,
    Istek,
    Karar,
    Mod,
    PolitikaMotoru,
    YanEtki,
    maskele,
)
from app.agent.runner import Adim, AdimDurum, AgentRunner, Run, RunDeposu
from app.agent.takim import TakimPanosu
from app.agent.terminal import KomutServisi
from app.agent.web import yerel_hedef_mi
from app.agent.webhook import WebhookDeposu
from app.agent.webhook import imza as webhook_imza
from app.agent.yetenek import butce_dokumu
from app.exceptions import UygulamaHatasi, YetkiYok
from app.services import cc_plugin as cc
from app.services.ayarlar import ollama_adres_dogrula
from app.services.hafiza import HafizaDeposu
from app.services.ollama import Ollama, OllamaHatasi
from app.services.openrouter import OpenRouterDeposu, OpenRouterHatasi, onbellek_isaretle
from app.services.oturumlar import OturumDeposu
from app.services.sohbet_araclari import DosyaAraclari as SohbetDosyaAraclari
from app.services.telegram import TelegramKanali
from app.services.yerel_llm import ModelCevapHatasi, YerelLLM


def _alan(kok: Path, *, mod: Mod = Mod.onayli, guven: Guven = Guven.guvenilir) -> CalismaAlani:
    return CalismaAlani(id="testalan", ad="Test", kokler=[str(kok)], mod=mod, guven=guven)


# ---------------- Faz 1: Guvenlik ve izinler ----------------


def test_policy_sir_alias_guvenilmeyen_ag_ve_tam_yetki(tmp_path: Path) -> None:
    for sir in (
        "sk-or-v1-" + "a" * 30,
        "sk-ant-api03-" + "b" * 30,
        "sk-proj-" + "c" * 30,
        "github_pat_" + "d" * 24,
        "123456789:AA" + "e" * 30,
        "ak_" + "f" * 16,
        "ck_" + "g" * 16,
        "AIza" + "h" * 35,
        "xoxb-" + "1234567890-abcdef",
    ):
        assert sir not in maskele(f"token={sir}"), sir

    p = PolitikaMotoru(tmp_path)
    alan = _alan(tmp_path)
    p.yonetilen.yasak_araclar = ["proje_dosya_yaz"]
    assert p.degerlendir(Istek(arac="dosya_yaz", yan_etki=YanEtki.yaz), alan).karar is Karar.ret
    p.yonetilen.yasak_araclar = ["dosya_sil"]
    assert (
        p.degerlendir(Istek(arac="proje_dosya_sil", yan_etki=YanEtki.sil), alan).karar is Karar.ret
    )
    p.yonetilen.yasak_araclar = []

    p.kullanici_ag = lambda: True
    guvensiz = _alan(tmp_path, mod=Mod.otomatik, guven=Guven.guvenilmeyen)
    assert (
        p.degerlendir(
            Istek(arac="web_getir", yan_etki=YanEtki.ag, host="example.com"), guvensiz
        ).karar
        is Karar.ret
    )

    p.tam_yetki = lambda: True
    for salt_mod in (Mod.planla, Mod.sohbet):
        a = _alan(tmp_path, mod=salt_mod)
        assert (
            p.degerlendir(
                Istek(arac="proje_dosya_yaz", yan_etki=YanEtki.yaz, hedef="a.py"), a
            ).karar
            is Karar.ret
        )
        assert (
            p.degerlendir(
                Istek(arac="komut_calistir", yan_etki=YanEtki.komut, komut="echo hi"), a
            ).karar
            is Karar.ret
        )


def test_github_ve_dosya_tasi_izinleri(tmp_path: Path) -> None:
    p = PolitikaMotoru(tmp_path)
    p.kullanici_ag = lambda: False
    alan = _alan(tmp_path, mod=Mod.otomatik)
    cp = CheckpointDeposu(tmp_path)
    kayit = AjanAracKaydi(
        alan=alan,
        politika=p,
        checkpointler=cp,
        komutlar=KomutServisi(),
    )
    adlar = {s["function"]["name"] for s in kayit.semalar()}
    assert "github_issue_oku" not in adlar
    assert "github_issue_oku" not in kayit.isleyiciler()

    gh = GithubAraclari(KokKapsami([tmp_path]), p, alan)
    with pytest.raises(YetkiYok):
        gh.issue_oku(1)

    (tmp_path / ".env").write_text("SECRET=123\n", encoding="utf-8")
    with pytest.raises(YetkiYok):
        kayit.yazma.dosya_tasi(".env", "kopya.txt")


def test_dosyalar_ve_sohbet_araclari_hassas_ve_maske(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("API=sk-or-v1-" + "z" * 30, encoding="utf-8")
    (tmp_path / "kod.py").write_text("KEY = 'sk-or-v1-" + "z" * 30 + "'\n", encoding="utf-8")
    da = AjanDosyaAraclari(KokKapsami([tmp_path]))
    assert ".env" not in str(da.glob_bul("*"))
    ara = da.icerik_ara("sk-or-v1")
    assert all(".env" not in e["dosya"] for e in ara["eslesmeler"])
    assert "zzzzzz" not in json.dumps(ara)

    sda = SohbetDosyaAraclari([tmp_path])
    sara = sda.dosya_ara("env", str(tmp_path))
    assert not any(".env" in str(x) for x in sara.get("bulunan", []))


def test_cc_plugin_ortam_ve_yol_gezinme(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YAS_OPENROUTER_ANAHTARI", "gizli-or-key")
    monkeypatch.setenv("YAS_OTURUM", "gizli-oturum")
    monkeypatch.setenv("NORMAL_VAR", "tamam")
    assert "gizli-or-key" not in cc.degisken_ac("${YAS_OPENROUTER_ANAHTARI}", tmp_path)
    assert cc.degisken_ac("${NORMAL_VAR}", tmp_path) == "tamam"
    assert cc.komut_genislet("Merhaba $ARGUMENTS ${YAS_OTURUM} $NORMAL_VAR", "Ali", tmp_path) == (
        "Merhaba Ali ${YAS_OTURUM} $NORMAL_VAR"
    )
    dis = tmp_path / "dis.json"
    dis.write_text('{"name":"kotu","plugins":[]}', encoding="utf-8")
    pazar = tmp_path / "pazar"
    (pazar / ".claude-plugin").mkdir(parents=True)
    mp = pazar / ".claude-plugin" / "marketplace.json"
    try:
        os.symlink(dis, mp)
    except (OSError, NotImplementedError):
        pytest.skip("Windows symlink izni yok")
    with pytest.raises(UygulamaHatasi):
        cc.marketplace_oku(pazar)


def test_telegram_mcp_webhook_dpapi(tmp_path: Path) -> None:
    tg = TelegramKanali(tmp_path)
    tg.kaydet({"token": "123456789:AA" + "x" * 25, "aktif": False})
    ham_tg = (tmp_path / "telegram.json").read_text(encoding="utf-8")
    assert "xxxxxxxxxx" not in ham_tg and "token_sifreli" in ham_tg
    assert tg.durum()["token_var"] is True

    mcp = McpYoneticisi(tmp_path)
    mcp.ekle(
        {
            "ad": "test",
            "komut": "python",
            "ortam": {"TOKEN": "gizli-env-123456"},
            "basliklar": {"Authorization": "Bearer gizli-baslik"},
        }
    )
    ham_mcp = (tmp_path / "mcp.json").read_text(encoding="utf-8")
    assert "gizli-env-123456" not in ham_mcp and "gizli-baslik" not in ham_mcp
    assert "dpapi:" in ham_mcp
    mcp.guncelle("test", {"ortam": {"TOKEN": "****", "YENI": "abc12345"}})
    sakli = mcp.liste()[0]
    assert sakli.ortam["TOKEN"] == "gizli-env-123456" and sakli.ortam["YENI"] == "abc12345"

    wh = WebhookDeposu(tmp_path)
    w = wh.ekle({"ad": "wh", "hedef": "kontrol et", "proje_kok": str(tmp_path)})
    ham_wh = (tmp_path / "webhooklar.json").read_text(encoding="utf-8")
    assert w.sir not in ham_wh and "dpapi:" in ham_wh
    zaman = str(int(time.time()))
    teslim = "teslim-0001"
    govde = b'{"olay":"test"}'
    baslik = {
        "x-yas-zaman": zaman,
        "x-yas-teslim": teslim,
        "x-yas-imza": webhook_imza(w.sir, zaman, teslim, govde),
    }
    assert wh.dogrula_ve_kuyruga_al(w.id, baslik, govde) == 1


def test_hafiza_ayar_ollama_web_oauth_video_ve_izolasyon(tmp_path: Path) -> None:
    gizli = tmp_path / ".env"
    gizli.write_text("PAROLA=abc\n", encoding="utf-8")
    h = HafizaDeposu(tmp_path)
    with pytest.raises(UygulamaHatasi):
        h.ekle("test notu", kapsam="p", dayanak=[f"{gizli}::PAROLA=sk-or-v1-" + "q" * 30])
    from app.services.hafiza import Hafiza

    assert Hafiza(metin="x", dayanak=[f"{gizli}::PAROLA"]).dayanak_tutuyor_mu() is False

    buyuk = tmp_path / "buyuk.txt"
    buyuk.write_bytes(b"a" * 1_100_000)
    assert Hafiza(metin="x", dayanak=[f"{buyuk}::a"]).dayanak_tutuyor_mu() is False

    assert ollama_adres_dogrula("http://127.0.0.1:11435/") == "http://127.0.0.1:11435"
    with pytest.raises(ValueError):
        ollama_adres_dogrula("https://evil.example:11435")

    assert yerel_hedef_mi("::ffff:127.0.0.1") is True

    # External OAuth endpoint pointing auth server to 127.0.0.1 -> SSRF blocked
    def sahte_oauth(r: httpx.Request) -> httpx.Response:
        if "oauth-protected-resource" in r.url.path:
            return httpx.Response(200, json={"authorization_servers": ["https://127.0.0.1:9999"]})
        return httpx.Response(404)

    with (
        httpx.Client(transport=httpx.MockTransport(sahte_oauth)) as c,
        pytest.raises(UygulamaHatasi),
    ):
        oauth_kesif("https://mcp.ornek.test/mcp", c)

    # video_uret polling_url baska origin engellenir
    def sahte_video(r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "v1", "polling_url": "https://evil.test/steal"})

    or_depo = OpenRouterDeposu(tmp_path, transport=httpx.MockTransport(sahte_video))
    or_depo.anahtar_kaydet("sk-or-v1-" + "x" * 30)
    with pytest.raises(OpenRouterHatasi, match="Gecersiz video"):
        or_depo.video_uret("m", "test", bekle=lambda _s: None)

    # KonteynerAdaptoru.sar .git varsa :ro baglar
    proje = tmp_path / "repo"
    (proje / ".git").mkdir(parents=True)
    adaptor = KonteynerAdaptoru("python:3.12-slim", motor="docker")
    adaptor._onbellek = (time.monotonic(), {"izole": True, "kullanilabilir": True, "not": ""})
    cmd = adaptor.sar("pytest", proje, proje)
    assert f"{proje / '.git'}:{KONTEYNER_KOK}/.git:ro" in cmd


@pytest.mark.asyncio
async def test_ollama_etiketler_traversal_ve_dikte(tmp_path: Path, app, istemci) -> None:
    o = Ollama(lambda: "http://127.0.0.1:11435", lambda: 8192)
    with pytest.raises(OllamaHatasi):
        await o.etiketler("qwen/../evil")

    await istemci.put("/api/ayarlar", json={"saglayici": "ollama", "ollama_model": ""})
    d = (await istemci.get("/api/dikte/durum")).json()
    assert d["kullanilabilir"] is False


# ---------------- Faz 2: Arka uc duzeltmeleri ----------------


@pytest.mark.asyncio
async def test_openrouter_cache_ve_yerel_llm_sse_kenar(tmp_path: Path) -> None:
    m = onbellek_isaretle(
        [
            {"role": "system", "content": "Sistem"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Bu nedir?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                ],
            },
        ]
    )
    user_parts = m[1]["content"]
    assert user_parts[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in user_parts[1]

    # bozuk SSE + index=None tool call + son_kullanim sifirlama + SSE error
    cagri = {"index": None, "id": "c1", "function": {"name": "f", "arguments": "{}"}}
    sse_ok = "\n".join(
        [
            "data: {bozuk-json",
            "data: "
            + json.dumps(
                {"choices": [{"delta": {"tool_calls": [cagri]}}], "usage": {"total_tokens": 5}}
            ),
            "data: [DONE]",
            "",
        ]
    )
    llm = YerelLLM(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=sse_ok)))
    llm.son_kullanim = {"total_tokens": 999}
    olaylar = [o async for o in llm.akis_olaylari([{"role": "user", "content": "hi"}])]
    assert olaylar[-1]["tur"] == "arac_cagrilari" and llm.son_kullanim == {"total_tokens": 5}

    sse_err = 'data: {"error":{"message":"kota doldu"}}\n\n'
    llm2 = YerelLLM(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=sse_err)))
    llm2.son_kullanim = {"stale": 1}
    with pytest.raises(ModelCevapHatasi, match="kota doldu"):
        async for _ in llm2.akis([{"role": "user", "content": "hi"}]):
            pass
    assert llm2.son_kullanim == {}


@pytest.mark.asyncio
async def test_api_lifespan_skill_kaydet_ve_rutin_calistir(
    tmp_path: Path, app, istemci, monkeypatch
) -> None:
    # omur lifespan baglam yoneticisi olmali (acilis + kapanis temiz calismali)
    from app.api import uygulama_olustur

    t_app = uygulama_olustur(tmp_path / "lifespan_veri", gecit=False)
    ajan_gorevleri: list[asyncio.Task] = []
    async with t_app.router.lifespan_context(t_app):
        ajan_gorevleri = [
            t
            for t in asyncio.all_tasks()
            if getattr(t.get_coro(), "__name__", "") == "_ajan_dongusu"
        ]
        assert len(ajan_gorevleri) >= 1
    await asyncio.sleep(0)
    assert all(t.done() for t in ajan_gorevleri)

    proje = tmp_path / "proje"
    proje.mkdir()
    alan_d = (
        await istemci.post("/api/projeler", json={"yol": str(proje), "guven": "guvenilir"})
    ).json()
    await istemci.put(f"/api/projeler/{alan_d['id']}/mod", json={"mod": "onayli"})
    # Mod.onayli altinda skill_kaydet OnayGerekli -> onay_bekliyor doner
    _, _, isleyiciler = app.state.ajan_runner.araclar("hedef")
    sonuc = isleyiciler["skill_kaydet"]("deneme-sk", "aciklama", "icerik")
    assert sonuc["karar"] == "onay_bekliyor" and sonuc.get("onay")

    # zamanlama_calistir bildir + bitis_kosulu hedef metnine eklenmeli
    hedefler: list[str] = []

    async def sahte_baslat(hedef, *_args, **_kw):
        hedefler.append(hedef)
        return type("R", (), {"id": "run1"})()

    monkeypatch.setattr(app.state.ajan_runner, "baslat", sahte_baslat)
    z = (
        await istemci.post(
            "/api/zamanlamalar",
            json={
                "ad": "kontrol",
                "hedef": "duruma bak",
                "tur": "aralik",
                "aralik_dk": 60,
                "davranis": "bildir",
                "bitis_kosulu": "v2 cikti",
            },
        )
    ).json()
    assert (await istemci.post(f"/api/zamanlamalar/{z['id']}/calistir")).json() == {"run": "run1"}
    assert "YALNIZ BILDIR" in hedefler[-1] and "BITIS KOSULU: v2 cikti" in hedefler[-1]


@pytest.mark.asyncio
async def test_runner_tekrar_arac_mesaji_atlandi_ve_multimodal_token(tmp_path: Path) -> None:
    depo = RunDeposu(tmp_path)
    runner = AgentRunner(depo, lambda: None, lambda _h: ("", [], {}))
    a = Adim(no=1, arac="dosya_oku", argumanlar={}, cagri_id="c1")
    run_m = Run(hedef="x")
    runner._arac_mesaji(run_m, a, {"veri": "z" * 10000})
    son_icerik = run_m.mesajlar[-1]["content"]
    assert json.loads(son_icerik)["kisaltildi"] is True

    # _ayni_cagri_sayisi AdimDurum.atlandi durumunu saymali
    r_loop = Run(
        hedef="x",
        adimlar=[
            Adim(no=1, arac="dosya_oku", argumanlar={"yol": "a.py"}, durum=AdimDurum.atlandi),
            Adim(no=2, arac="dosya_oku", argumanlar={"yol": "a.py"}, durum=AdimDurum.tamam),
        ],
    )
    assert (
        runner._ayni_cagri_sayisi(r_loop, Adim(no=3, arac="dosya_oku", argumanlar={"yol": "a.py"}))
        == 3
    )

    # tekrar() cevapsiz tool_calls'i kapatmali
    r_kap = Run(
        hedef="h",
        durum="basarisiz",
        mesajlar=[
            {"role": "user", "content": "h"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c_koptu", "type": "function", "function": {"name": "a"}}],
            },
        ],
    )
    depo.kaydet(r_kap)
    runner._calistir = lambda _rid: None
    tekrar_run = await runner.tekrar(r_kap.id)
    roller = [m["role"] for m in tekrar_run.mesajlar]
    assert roller == ["user", "assistant", "tool", "user"]
    assert tekrar_run.mesajlar[2]["tool_call_id"] == "c_koptu"

    # multimodal base64 ham karakter sayisiyla sismemeli
    dev_img = {
        "role": "user",
        "content": [
            {"type": "text", "text": "bak"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 120_000}},
        ],
    }
    assert butce_dokumu("", [], [dev_img], 100, 32000)["mesajlar"] < 2000
    assert ozet_mesaj_token([dev_img]) < 2000


def test_notebook_checkpoints_takim_oturum_ve_uzak(tmp_path: Path) -> None:
    nb = {"nbformat": 4, "nbformat_minor": 5, "cells": []}
    c1 = _yeni_hucre(nb, "code", "print(1)")
    nb["cells"].append(c1)
    c2 = _yeni_hucre(nb, "code", "print(1)")
    assert c1["id"] and c2["id"] and c1["id"] != c2["id"]

    # checkpoints Islem.tasi hedefi de siler
    cp_depo = CheckpointDeposu(tmp_path)
    kaynak = tmp_path / "eski.txt"
    hedef = tmp_path / "yeni.txt"
    eski_veri = b"orijinal icerik"
    kaynak.write_bytes(eski_veri)
    eh, ek, _ = cp_depo.anlik_al(kaynak)
    kaynak.rename(hedef)
    cp = cp_depo.kaydet(
        Checkpoint(
            aciklama="tasi",
            dosyalar=[
                DosyaDurumu(
                    yol=str(kaynak),
                    hedef=str(hedef),
                    islem=Islem.tasi,
                    once_hash=eh,
                    sonra_hash=None,
                    once_kopya=ek,
                )
            ],
        )
    )
    cp_depo.geri_al(cp.id)
    assert kaynak.read_bytes() == eski_veri and not hedef.exists()

    # takim 'hepsi' mesaji iki farkli aliciya da teslim edilir
    tp = TakimPanosu(tmp_path)
    lider = tp.isleyiciler("k", "r-lider", "Lider")
    lider["takim_mesaj_gonder"](alici="hepsi", metin="herkese duyuru")
    assert len(tp.teslim_al("k", {"r-a", "AjanA"})) == 1
    assert len(tp.teslim_al("k", {"r-b", "AjanB"})) == 1
    assert tp.teslim_al("k", {"r-a", "AjanA"}) == []

    # oturumlar catal & temizle
    od = OturumDeposu(tmp_path)
    o = od.olustur(alan="proje1")
    o.ajan_runlari = [{"run": "r1", "metin": "hi"}]
    o.oneri_kararlari = {"k": "reddedildi"}
    od.kaydet(o)
    dal = od.catal(o.id)
    assert dal.alan == "proje1" and dal.ajan_runlari == [{"run": "r1", "metin": "hi"}]
    temiz = od.temizle(o.id)
    assert temiz.mesajlar == [] and temiz.ajan_runlari == [] and temiz.oneri_kararlari == {}

    # uzak gecis penceresi
    saat = [1000.0]
    ud = uzak.UzakDeposu(tmp_path, saat=lambda: saat[0])
    kod = ud.kod_olustur("tam")["kod"]
    ilk = ud.esles(kod, "tel")["token"]
    # gecis_sn=60 ile sessiz yenileme eski tokeni 60 sn korur
    yeni = ud.yenile(ilk, gecis_sn=60)["token"]
    assert ud.dogrula(ilk).ad == "tel"
    assert all("onceki_token_ozet" not in x for x in ud.liste())
    saat[0] += 61
    with pytest.raises(uzak.UzakHata):
        ud.dogrula(ilk)
    # varsayilan yenile (gecis_sn=0) eski tokeni aninda gecersiz kilar
    yeni2 = ud.yenile(yeni)["token"]
    with pytest.raises(uzak.UzakHata):
        ud.dogrula(yeni)
    assert ud.dogrula(yeni2).ad == "tel"
