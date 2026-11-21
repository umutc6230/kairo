"""Artımlı görev SSE akışı ve Telegram onay komutları/bildirimleri testleri."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from conftest import olaylar

from app.agent.policy import Istek, YanEtki
from app.agent.runner import Adim, AdimDurum, Run, RunDeposu, RunDurum, olay_akisi
from app.services.telegram import TelegramKanali


async def test_olay_akisi_tam_ve_artimli(tmp_path: Path) -> None:
    depo = RunDeposu(tmp_path)
    run = Run(
        hedef="Test gorevi",
        durum=RunDurum.calisiyor,
        adimlar=[Adim(no=1, arac="dosya_oku", durum=AdimDurum.tamam)],
    )
    depo.kaydet(run)

    # 1) mod="tam" mevcut davranisi korur
    async def tam_guncelle() -> None:
        await asyncio.sleep(0.03)
        r = depo.getir(run.id)
        r.durum = RunDurum.basarili
        r.guncelleme = "2026-11-21T15:00:01"
        depo.kaydet(r)
        # depo.kaydet ayni saniyeyi yazsa bile farkli guncelleme icin elle set
        r.guncelleme = "2026-11-21T15:00:01"
        depo._yol(r.id)  # noqa: SLF001

    run.guncelleme = "2026-11-21T15:00:00"
    json.dumps(run.model_dump(mode="json"))
    # Dogrudan dosya guncelleyelim ki saniye cakismasi olmasin
    run.durum = RunDurum.basarili
    depo.kaydet(run)
    tam_olaylar = [o async for o in olay_akisi(depo, run.id, aralik=0.01, mod="tam")]
    assert len(tam_olaylar) == 1
    assert tam_olaylar[0]["tur"] == "run"
    assert tam_olaylar[0]["run"]["id"] == run.id

    # 2) mod="artimli": ilk 'run', yeni adimda 'delta', adim azalinca tekrar 'run'
    run2 = Run(
        hedef="Artimli gorev",
        durum=RunDurum.calisiyor,
        adimlar=[Adim(no=1, arac="dosya_oku", durum=AdimDurum.tamam)],
    )
    depo.kaydet(run2)

    async def adim_guncelle() -> None:
        await asyncio.sleep(0.03)
        r = depo.getir(run2.id)
        r.adimlar.append(Adim(no=2, arac="komut_calistir", durum=AdimDurum.niyet))
        depo.kaydet(r)
        await asyncio.sleep(0.03)
        r = depo.getir(run2.id)
        r.adimlar = [Adim(no=1, arac="dosya_oku", durum=AdimDurum.tamam)]
        r.durum = RunDurum.basarili
        depo.kaydet(r)

    gorev = asyncio.create_task(adim_guncelle())
    artimli_olaylar = [o async for o in olay_akisi(depo, run2.id, aralik=0.01, mod="artimli")]
    await gorev

    assert artimli_olaylar[0]["tur"] == "run"
    assert len(artimli_olaylar[0]["run"]["adimlar"]) == 1

    deltalar = [o for o in artimli_olaylar if o["tur"] == "delta"]
    assert deltalar, f"Delta bekleniyordu: {artimli_olaylar}"
    assert [d["i"] for d in deltalar[0]["adimlar"]] == [1]
    assert deltalar[0]["adimlar"][0]["adim"]["arac"] == "komut_calistir"
    assert "adimlar" not in deltalar[0]["meta"]

    assert artimli_olaylar[-1]["tur"] == "run"
    assert artimli_olaylar[-1]["run"]["durum"] == "basarili"


async def test_api_gorev_olaylari_artimli(app, istemci) -> None:
    depo = app.state.run_deposu
    run = Run(
        hedef="API artimli gorev",
        durum=RunDurum.calisiyor,
        adimlar=[Adim(no=1, arac="dosya_oku", durum=AdimDurum.tamam)],
    )
    depo.kaydet(run)

    async def bitir() -> None:
        await asyncio.sleep(0.15)
        r = depo.getir(run.id)
        r.adimlar.append(Adim(no=2, arac="proje_dosya_yaz", durum=AdimDurum.tamam))
        r.durum = RunDurum.basarili
        depo.kaydet(r)

    t = asyncio.create_task(bitir())
    r = await istemci.get(f"/api/gorevler/{run.id}/olaylar?mod=artimli")
    await t
    assert r.status_code == 200
    gelen = olaylar(r.text)
    assert gelen[0]["tur"] == "run"
    assert any(o["tur"] == "delta" and o["adimlar"][0]["i"] == 1 for o in gelen)
    assert gelen[-1]["meta"]["durum"] == "basarili"


async def test_telegram_bildir_herkese_ve_hatalari_yutar(tmp_path: Path) -> None:
    giden: list[dict] = []

    def bot(r: httpx.Request) -> httpx.Response:
        govde = json.loads(r.content)
        if govde["chat_id"] == 100:
            return httpx.Response(500, json={"ok": False, "description": "gecici hata"})
        giden.append(govde)
        return httpx.Response(200, json={"ok": True, "result": {}})

    t = TelegramKanali(tmp_path, transport=httpx.MockTransport(bot))
    await t.bildir_herkese("gitmemeli")
    assert giden == []

    t.kaydet({"token": "123456:ABCDEFGHIJKLMNOP", "izinli": ["100", "200"], "aktif": False})
    await t.bildir_herkese("pasifken gitmemeli")
    assert giden == []

    t.kaydet({"aktif": True})
    await t.bildir_herkese("Onay mesaji")
    assert giden == [{"chat_id": 200, "text": "Onay mesaji"}]


async def test_telegram_onay_komutlari_ve_bildirim(app, monkeypatch) -> None:
    giden: list[dict] = []

    def bot(r: httpx.Request) -> httpx.Response:
        if r.url.path.endswith("/sendMessage"):
            giden.append(json.loads(r.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    tg: TelegramKanali = app.state.telegram
    tg.transport = httpx.MockTransport(bot)
    tg.kaydet({"token": "123456:ABCDEFGHIJKLMNOP", "izinli": ["42"], "aktif": True})

    devam_edilen: list[str] = []

    async def sahte_devam(run_id: str) -> Run:
        devam_edilen.append(run_id)
        return app.state.run_deposu.getir(run_id)

    monkeypatch.setattr(app.state.ajan_runner, "devam", sahte_devam)

    # Onay olusunca Telegram bildirimi gider
    onay1 = app.state.politika.onaylar.olustur(
        Istek(arac="komut_calistir", yan_etki=YanEtki.komut, komut="echo selam", ozet="echo selam"),
        "hash-1",
    )
    run = Run(
        hedef="Onay bekleyen gorev",
        durum=RunDurum.onay_bekliyor,
        adimlar=[
            Adim(no=1, arac="komut_calistir", durum=AdimDurum.onay_bekliyor, onay_id=onay1.id)
        ],
    )
    app.state.run_deposu.kaydet(run)

    await asyncio.sleep(0.05)
    assert len(giden) == 1
    assert giden[0]["chat_id"] == 42
    assert f"/onayla {onay1.id}" in giden[0]["text"]
    assert f"/reddet {onay1.id}" in giden[0]["text"]
    assert "komut_calistir" in giden[0]["text"]

    # /onaylar bekleyen onayi listeler
    yanit_liste = await app.state.telegram_mesaj(42, "/onaylar", "Umut")
    assert onay1.id in yanit_liste
    assert "komut_calistir" in yanit_liste

    # /onayla <id> onayi verir ve gorevi devam ettirir
    yanit_onayla = await app.state.telegram_mesaj(42, f"/onayla {onay1.id}", "Umut")
    assert f"Onaylandi: {onay1.id}" in yanit_onayla
    assert devam_edilen == [run.id]
    assert app.state.politika.onaylar.gecmis(10)[0]["karar"] == "onayli"

    # Eksik arguman ve olmayan id
    assert "Kullanim: /onayla" in await app.state.telegram_mesaj(42, "/onayla", "Umut")
    assert "bulunamadi" in (await app.state.telegram_mesaj(42, "/reddet yokid", "Umut")).lower()

    # Ikinci onay: /reddet <id>
    onay2 = app.state.politika.onaylar.olustur(
        Istek(arac="proje_dosya_yaz", yan_etki=YanEtki.yaz, yol="a.txt", ozet="a.txt yaz"),
        "hash-2",
    )
    await asyncio.sleep(0.05)
    yanit_ret = await app.state.telegram_mesaj(42, f"/reddet {onay2.id}", "Umut")
    assert f"Reddedildi: {onay2.id}" in yanit_ret
    assert await app.state.telegram_mesaj(42, "/onaylar", "Umut") == "Bekleyen onay yok."
