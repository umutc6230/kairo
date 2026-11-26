"""Ajan gorevleri, kalici ajanlar, Superajan, Telegram, zamanlamalar, webhook, uzak ve akislar."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError

from app import uzak as uzak_mod
from app.agent import akis as akis_mod
from app.agent import cli_ajan
from app.agent import superajan as sa
from app.agent import worktree as wt
from app.agent.ajanlar import KuyrukOgesi
from app.agent.akis import Akis, sablon_uygula
from app.agent.runner import BITMIS as BITMIS_RUN
from app.agent.runner import Butce, RunDurum, olay_akisi
from app.agent.webhook import WebhookHatasi
from app.exceptions import UygulamaHatasi
from app.routers import (
    EntegreIstegi,
    GorevIstegi,
    GorevMesaji,
    IsEmriIstegi,
    KararIstegi,
    sse,
)
from app.services.oneriler import oneriler as oneriler_hesapla


def router_olustur(b: Any) -> APIRouter:
    r = APIRouter()
    akis_gorevleri: set[asyncio.Task] = set()
    worktree_kilidi = asyncio.Lock()

    # ---- Superajan ----
    @r.get("/api/superajan")
    async def superajan_liste() -> dict:
        isler = [b.is_ozet(x) for x in reversed(b.superajan_deposu.liste())]
        bekleyen = sum(1 for x in isler if x["asama"] in sa.INSAN_BEKLIYOR)
        return {"isler": isler, "aktif_proje": b.aktif_kok(), "insan_bekliyor": bekleyen}

    @r.post("/api/superajan/isler")
    async def superajan_yeni(istek: IsEmriIstegi) -> dict:
        kok = istek.proje_kok or b.aktif_kok()
        if not kok:
            raise UygulamaHatasi("Once bir proje ac ya da proje klasoru sec.")
        if not await asyncio.to_thread(wt.git_mi, Path(kok)):
            raise UygulamaHatasi(
                "GIT_YOK: Is emri ayri dalda calisir; proje bir git deposu olmali."
            )
        await b.ollama_yetenek_hazirla()
        import app.api as api_mod

        api_mod.dogrula(b.model_yetenegi(), araclar_gerekli=True, dusunme=b.ayarlar.oku().dusunme)
        baslik = istek.baslik.strip() or istek.gorev.strip().splitlines()[0][:80]
        is_ = b.superajan_deposu.olustur(
            baslik, istek.gorev, kok, istek.kaynak, {"yazan": "kullanici", "guc": "acik"}
        )
        await b.superajan_tick()
        return b.is_ozet(b.superajan_deposu.getir(is_.id))

    @r.post("/api/superajan/git-baslat")
    async def superajan_git_baslat(istek: IsEmriIstegi) -> dict:
        kok = istek.proje_kok or b.aktif_kok()
        if not kok:
            raise UygulamaHatasi("Once bir proje ac.")
        return await asyncio.to_thread(wt.git_baslat, Path(kok))

    @r.post("/api/superajan/isler/{iid}/mesaj")
    async def superajan_mesaj(iid: str, istek: GorevMesaji) -> dict:
        is_ = b.superajan_deposu.getir(iid)
        if is_.durum != "acik":
            raise UygulamaHatasi("Bu is emri kapali.")
        durum, _ = b.durum_ozet(is_)
        if durum in ("calisiyor", "duraklatildi", "onay_bekliyor", "cevap_bekliyor"):
            await b.ajan.mesaj(is_.runlar[-1], istek.metin)
        else:
            is_.bekleyen_mesaj = istek.metin.strip()[:4000]
            is_.olay("Takip mesaji: yeni atama sirada.")
            b.superajan_deposu.guncelle(is_)
            await b.superajan_tick()
        return b.is_ozet(b.superajan_deposu.getir(iid))

    @r.post("/api/superajan/isler/{iid}/tekrar")
    async def superajan_tekrar(iid: str) -> dict:
        is_ = b.superajan_deposu.getir(iid)
        is_.durum, is_.bekleyen_mesaj = "acik", "Onceki atama bitti; isi tamamla ya da duzelt."
        is_.olay("Tekrar istendi.")
        b.superajan_deposu.guncelle(is_)
        await b.superajan_tick()
        return b.is_ozet(b.superajan_deposu.getir(iid))

    @r.post("/api/superajan/isler/{iid}/durdur")
    async def superajan_durdur(iid: str) -> dict:
        is_ = b.superajan_deposu.getir(iid)
        if is_.runlar and b.ajan.calisiyor_mu(is_.runlar[-1]):
            await b.ajan.iptal(is_.runlar[-1])
        is_.durum = "durduruldu"
        is_.olay("Kullanici durdurdu.")
        b.superajan_deposu.guncelle(is_)
        return b.is_ozet(is_)

    @r.post("/api/superajan/isler/{iid}/birlestir")
    async def superajan_birlestir(iid: str, istek: EntegreIstegi) -> dict:
        is_ = b.superajan_deposu.getir(iid)
        if not is_.calisma_koku or not is_.dal:
            raise UygulamaHatasi("Bu is emrinin birlestirilecek dali yok.")
        s = await asyncio.to_thread(
            wt.entegre_et,
            Path(is_.proje_kok),
            Path(is_.calisma_koku),
            is_.dal,
            f"Is emri: {is_.baslik}",
            istek.test_komutu,
        )
        if s.get("durum") == "birlestirildi":
            is_.durum = "bitti"
            is_.olay("Ana dala birlestirildi.")
            b.superajan_deposu.guncelle(is_)
        return {**s, "is": b.is_ozet(is_)}

    @r.post("/api/superajan/isler/{iid}/baslat")
    async def superajan_baslat(iid: str) -> dict:
        is_ = b.superajan_deposu.getir(iid)
        is_.onay_bekliyor = False
        is_.olay("Kullanici baslatti.")
        b.superajan_deposu.guncelle(is_)
        await b.superajan_tick()
        return b.is_ozet(b.superajan_deposu.getir(iid))

    @r.post("/api/superajan/isler/{iid}/teslim")
    async def superajan_teslim(iid: str) -> dict:
        s = await asyncio.to_thread(b.teslim, iid)
        return {**s, "is": b.is_ozet(b.superajan_deposu.getir(iid))}

    @r.get("/api/superajan/github")
    async def superajan_github() -> dict:
        return b.superajan_deposu.github()["ayar"].model_dump() | {"gh": bool(sa.gh_yolu())}

    @r.put("/api/superajan/github")
    async def superajan_github_kaydet(veri: dict) -> dict:
        g = b.superajan_deposu.github()
        ayar = sa.GithubAyar(**{k: v for k, v in veri.items() if k != "gh"}).dogrula()
        ayar.proje_kok = ayar.proje_kok or b.aktif_kok()
        if ayar.aktif and not ayar.izinli:
            kod, cikti = await asyncio.to_thread(sa.gh, "api", "user", "-q", ".login")
            if kod != 0 or not cikti.strip():
                raise UygulamaHatasi("gh hesabi okunamadi; once GitHub'a baglan.")
            ayar.izinli = [cikti.strip().lower()]
        if ayar.aktif and not (ayar.depo and ayar.proje_kok):
            raise UygulamaHatasi("Depo ve proje klasoru gerekli.")
        ayni = ayar.depo == g["ayar"].depo
        b.superajan_deposu.github_yaz(ayar, g["gorulen"] if ayni else [], g["etag"] if ayni else {})
        return ayar.model_dump()

    @r.post("/api/superajan/yokla")
    async def superajan_yokla() -> dict:
        s = await asyncio.to_thread(b.gh_yokla)
        await b.superajan_tick()
        return s

    @r.post("/api/superajan/isler/{iid}/at")
    async def superajan_at(iid: str) -> dict:
        is_ = b.superajan_deposu.getir(iid)
        if is_.runlar and b.ajan.calisiyor_mu(is_.runlar[-1]):
            await b.ajan.iptal(is_.runlar[-1])
        if is_.calisma_koku and is_.dal:
            await asyncio.to_thread(wt.at, Path(is_.proje_kok), Path(is_.calisma_koku), is_.dal)
        is_.durum = "bitti"
        is_.olay("Degisiklikler atildi (ana dala dokunulmadi).")
        b.superajan_deposu.guncelle(is_)
        return b.is_ozet(is_)

    @r.delete("/api/superajan/isler/{iid}")
    async def superajan_sil(iid: str) -> dict:
        is_ = b.superajan_deposu.getir(iid)
        if is_.durum == "acik" and is_.runlar:
            raise UygulamaHatasi("Acik is emri silinmez; once birlestir, at ya da durdur.")
        b.superajan_deposu.sil(iid)
        return {"silindi": iid}

    # ---- Kalici ajanlar ve Telegram ----
    @r.get("/api/ajanlar")
    async def ajan_listesi() -> dict:
        return {"ajanlar": [a.ozet() for a in b.ajan_deposu.liste()]}

    @r.post("/api/ajanlar")
    async def ajan_olustur(veri: dict) -> dict:
        return b.ajan_deposu.olustur(veri).ozet()

    @r.get("/api/ajanlar/{ajan_id}")
    async def ajan_getir(ajan_id: str) -> dict:
        a = b.ajan_deposu.getir(ajan_id)
        return {
            **a.ozet(),
            "konusma": [m.model_dump() for m in a.konusma],
            "canli": b.cli_canli.get(a.id, [])[-40:] if a.aktif_run.startswith("cli:") else [],
            "kuyruk": [k.model_dump() for k in a.kuyruk],
            "klasor_yolu": str(b.ajan_deposu.klasor(a)),
        }

    @r.put("/api/ajanlar/{ajan_id}")
    async def ajan_duzenle(ajan_id: str, veri: dict) -> dict:
        return b.ajan_deposu.duzenle(ajan_id, veri).ozet()

    @r.delete("/api/ajanlar/{ajan_id}")
    async def ajan_sil(ajan_id: str) -> dict:
        a = b.ajan_deposu.getir(ajan_id)
        if a.id in b.cli_isleri:
            b.cli_isleri.pop(a.id).cancel()
        elif a.aktif_run and a.aktif_run != "baslatiliyor":
            with contextlib.suppress(Exception):
                await b.ajan.iptal(a.aktif_run)
        b.ajan_deposu.sil(a.id)
        return {"silindi": a.id}

    @r.post("/api/ajanlar/{ajan_id}/mesaj")
    async def ajana_yaz(ajan_id: str, veri: dict) -> dict:
        metin = str(veri.get("metin") or "").strip()
        if not metin:
            raise UygulamaHatasi("Mesaj bos olamaz.")
        a = b.ajan_deposu.kuyruga_ekle(ajan_id, KuyrukOgesi(metin=metin, kimden="kullanici"))
        await b.ajan_dagit()
        return b.ajan_deposu.getir(a.id).ozet()

    @r.get("/api/ajanlar-saglayicilar")
    async def ajan_saglayicilari() -> dict:
        return {"saglayicilar": cli_ajan.SAGLAYICILAR, "kurulu": cli_ajan.durum()}

    @r.post("/api/ajanlar/{ajan_id}/iptal")
    async def ajan_is_iptal(ajan_id: str) -> dict:
        a = b.ajan_deposu.getir(ajan_id)
        if a.id in b.cli_isleri:
            b.cli_isleri[a.id].cancel()
        elif a.aktif_run and a.aktif_run != "baslatiliyor":
            await b.ajan.iptal(a.aktif_run)
        return {"iptal": True}

    @r.delete("/api/ajanlar/{ajan_id}/kuyruk/{oge_id}")
    async def ajan_kuyruk_sil(ajan_id: str, oge_id: str) -> dict:
        return b.ajan_deposu.kuyruktan_sil(b.ajan_deposu.getir(ajan_id).id, oge_id).ozet()

    @r.get("/api/telegram")
    async def telegram_durum() -> dict:
        return b.telegram.durum()

    @r.put("/api/telegram")
    async def telegram_kaydet(veri: dict) -> dict:
        d = b.telegram.kaydet(veri)
        if d["aktif"] and d["token_var"]:
            b.telegram.baslat(b.telegram_mesaj)
        return d

    @r.post("/api/telegram/dene")
    async def telegram_dene(veri: dict) -> dict:
        chat = int(veri.get("chat") or 0)
        if chat not in b.telegram.ayar().get("izinli", []):
            raise UygulamaHatasi("Bu sohbet izin listesinde degil.")
        await b.telegram.gonder(chat, "Kairo baglantisi calisiyor.")
        return {"gonderildi": True}

    # ---- Ajan gorevleri ----
    @r.post("/api/gorevler")
    async def gorev_baslat(istek: GorevIstegi) -> dict:
        await asyncio.to_thread(b.ajan_baglami, istek.hedef)
        proje_m = b.proje_modeli("koordinator")
        hedef_model = proje_m["model"] if proje_m["model_sabit"] else ""
        await b.ollama_yetenek_hazirla(hedef_model)
        if not str(proje_m["model"]).startswith("cli:"):
            import app.api as api_mod

            api_mod.dogrula(
                b.model_yetenegi(hedef_model),
                araclar_gerekli=True,
                dusunme=b.ayarlar.oku().dusunme,
            )
        izole_kur = None
        if istek.izole:
            proje = Path(b.sohbet.aktif_alan().kokler[0])
            wt.depo_koku(proje)

            def izole_kur(run_id: str) -> tuple[str, str]:
                onek = b.ayarlar.oku().branch_oneki
                yol, dal = wt.olustur(proje, b.veri_dizini / "worktrees", run_id, onek)
                return str(yol), dal

        run = await b.ajan.baslat(
            istek.hedef,
            istek.kabul,
            istek.butce,
            **proje_m,
            izole_kur=izole_kur,
            onceki=istek.onceki,
            etkilesimli=istek.etkilesimli,
        )
        return run.ozet()

    async def gorev_worktree_isle(run_id: str, istek: EntegreIstegi | None = None) -> dict:
        async with worktree_kilidi:
            run = b.run_deposu.getir(run_id)
            if not run.calisma_koku or not run.dal or (run.parent and not run.bagimsiz_worktree):
                raise UygulamaHatasi("Bu gorevin bagimsiz worktree'si yok.")
            if run.durum not in BITMIS_RUN:
                raise UygulamaHatasi("Once gorev bitmeli.")
            if run.worktree_durumu:
                return {"durum": run.worktree_durumu}
            yol = Path(run.calisma_koku)
            if not yol.is_dir():
                return {"durum": "kapali"}
            proje = Path(b.sohbet.aktif_alan().kokler[0])
            if run.proje_id:
                proje = Path(b.projeler.getir(run.proje_id).kokler[0])
            await asyncio.to_thread(wt.worktree_dogrula, proje, yol, run.dal)
            if istek is None:
                sonuc = await asyncio.to_thread(wt.at, proje, yol, run.dal)
            else:
                if run.durum not in (RunDurum.basarili, RunDurum.dogrulanmadi):
                    raise UygulamaHatasi("Yalniz tamamlanan gorevler birlestirilebilir.")
                sonuc = await asyncio.to_thread(
                    wt.entegre_et, proje, yol, run.dal, run.hedef, istek.test_komutu
                )
            if sonuc["durum"] in {"birlestirildi", "atildi", "degisiklik_yok"}:
                run.worktree_durumu = sonuc["durum"]
                b.run_deposu.kaydet(run)
            return sonuc

    @r.post("/api/gorevler/{run_id}/entegre")
    async def gorev_entegre(run_id: str, istek: EntegreIstegi) -> dict:
        return await gorev_worktree_isle(run_id, istek)

    @r.post("/api/gorevler/{run_id}/at")
    async def gorev_at(run_id: str) -> dict:
        return await gorev_worktree_isle(run_id)

    @r.get("/api/gorevler")
    async def gorev_listesi() -> dict:
        return {"gorevler": [x.ozet() for x in b.run_deposu.liste()[:50]]}

    @r.get("/api/gorevler/{run_id}")
    async def gorev_getir(run_id: str) -> dict:
        return b.run_deposu.getir(run_id).ozet()

    @r.get("/api/gorevler/{run_id}/takim")
    async def gorev_takim(run_id: str) -> dict:
        run = b.run_deposu.getir(run_id)
        return b.ajan.takim.pano(run.parent or run.id)

    @r.get("/api/gorevler/{run_id}/olaylar")
    async def gorev_olaylari(run_id: str, mod: str = "tam") -> StreamingResponse:
        b.run_deposu.getir(run_id)
        secilen = "artimli" if mod == "artimli" else "tam"
        return sse(olay_akisi(b.run_deposu, run_id, mod=secilen))

    @r.post("/api/gorevler/{run_id}/mesaj")
    async def gorev_mesaj(run_id: str, istek: GorevMesaji) -> dict:
        return (await b.ajan.mesaj(run_id, istek.metin)).ozet()

    @r.post("/api/gorevler/{run_id}/karar")
    async def gorev_karar(run_id: str, istek: KararIstegi) -> dict:
        return (await b.ajan.karar(run_id, istek.adim, istek.karar)).ozet()

    @r.post("/api/gorevler/{run_id}/{islem}")
    async def gorev_islem(run_id: str, islem: str) -> dict:
        fonk = {
            "duraklat": b.ajan.duraklat,
            "devam": b.ajan.devam,
            "iptal": b.ajan.iptal,
            "tekrar": b.ajan.tekrar,
        }.get(islem)
        if fonk is None:
            raise UygulamaHatasi("Islem: duraklat, devam, iptal ya da tekrar.")
        return (await fonk(run_id)).ozet()

    # ---- Zamanlamalar ve oneriler ----
    @r.get("/api/oneriler")
    async def oneri_listesi() -> dict:
        alanlar = sorted(b.projeler.liste(), key=lambda a: a.guncelleme, reverse=True)
        isler = [b.is_ozet(x) for x in b.superajan_deposu.liste()]
        return {
            "oneriler": await asyncio.to_thread(
                oneriler_hesapla, alanlar, isler, b.zamanlayici.liste(), datetime.now(UTC)
            )
        }

    @r.get("/api/zamanlamalar")
    async def zamanlama_listesi() -> dict:
        return {
            "zamanlamalar": [z.model_dump() for z in b.zamanlayici.liste()],
            "gecmis": b.zamanlayici.gecmis()[-50:],
            "not": "Zamanlamalar yalniz uygulama acikken calisir.",
        }

    @r.post("/api/zamanlamalar")
    async def zamanlama_ekle(veri: dict) -> dict:
        veri = {"saat_dilimi": b.ayarlar.oku().saat_dilimi, **veri}
        if not veri.get("proje_kok"):
            alan = b.sohbet.projeler.aktif() if b.sohbet.projeler else None
            if alan is None or not alan.kokler:
                raise UygulamaHatasi("Zamanlama icin once bir proje acin.")
            veri["proje_kok"] = alan.kokler[0]
        try:
            return b.zamanlayici.ekle(veri).model_dump()
        except ValidationError as e:
            raise UygulamaHatasi(f"Gecersiz zamanlama: {e.errors()[0].get('msg')}") from e

    @r.patch("/api/zamanlamalar/{zid}")
    async def zamanlama_guncelle(zid: str, veri: dict) -> dict:
        try:
            return b.zamanlayici.guncelle(zid, veri).model_dump()
        except ValidationError as e:
            raise UygulamaHatasi(f"Gecersiz zamanlama: {e.errors()[0].get('msg')}") from e

    @r.post("/api/zamanlamalar/{zid}/calistir")
    async def zamanlama_calistir(zid: str) -> dict:
        z = next((x for x in b.zamanlayici.liste() if x.id == zid), None)
        if z is None:
            raise UygulamaHatasi("Rutin bulunamadi.")
        alan = b.sohbet.projeler.aktif() if b.sohbet.projeler else None
        if alan is None or not alan.kokler or Path(alan.kokler[0]) != Path(z.proje_kok):
            raise UygulamaHatasi(f"Once rutinin projesini acin: {z.proje_kok}")
        run = await b.ajan.baslat(
            b.rutin_hedefi(z, "rutin"),
            [],
            Butce(max_adim=z.max_adim),
            model=b.ayarlar.oku().aktif_model,
        )
        return {"run": run.id}

    @r.delete("/api/zamanlamalar/{zid}")
    async def zamanlama_sil(zid: str) -> dict:
        b.zamanlayici.sil(zid)
        return {"silindi": zid}

    # ---- Webhook ----
    @r.post("/api/webhook/{wid}")
    async def webhook_tetikle(wid: str, istek: Request) -> Response:
        govde = await istek.body()
        try:
            basliklar = {k.lower(): v for k, v in istek.headers.items()}
            sira = b.webhooklar.dogrula_ve_kuyruga_al(wid, basliklar, govde)
        except WebhookHatasi as e:
            return JSONResponse({"hata": e.mesaj}, status_code=e.kod)
        try:
            durum_ = await b.webhook_isle(wid)
        except Exception as e:  # noqa: BLE001
            durum_ = f"kuyrukta ({e})"
        return JSONResponse({"kabul": True, "sira": sira, "durum": durum_}, status_code=202)

    @r.get("/api/webhooklar")
    async def webhook_listesi() -> dict:
        return {"webhooklar": b.webhooklar.liste()}

    @r.post("/api/webhooklar")
    async def webhook_ekle(veri: dict) -> dict:
        if veri.get("ajan"):
            veri["ajan"] = b.ajan_deposu.getir(str(veri["ajan"])).id
        elif not veri.get("proje_kok"):
            alan = b.sohbet.projeler.aktif() if b.sohbet.projeler else None
            if alan is None or not alan.kokler:
                raise UygulamaHatasi("Webhook icin once bir proje acin.")
            veri["proje_kok"] = alan.kokler[0]
        try:
            w = b.webhooklar.ekle(veri)
        except ValidationError as e:
            raise UygulamaHatasi(f"Gecersiz webhook: {e.errors()[0].get('msg')}") from e
        return w.model_dump(exclude={"kuyruk"}) | {
            "adres": f"/api/webhook/{w.id}",
            "not": "Sir yalniz simdi gosterilir; saklayin.",
        }

    @r.delete("/api/webhooklar/{wid}")
    async def webhook_sil(wid: str) -> dict:
        b.webhooklar.sil(wid)
        return {"silindi": wid}

    # ---- Uzak erisim (Remote Control) ----
    def _uzak_hostlar() -> list[str]:
        if b.ayarlar.oku().uzak_ag == "tailscale":
            ts = uzak_mod.tailscale_ip()
            return [ts] if ts else []
        return [i for i in uzak_mod.yerel_ipler() if i != "127.0.0.1"]

    def _uzak_durum() -> dict:
        _, _, parmak = uzak_mod.sertifika(b.veri_dizini / "uzak-tls")
        a = b.ayarlar.oku()
        hostlar = _uzak_hostlar()
        return {
            "acik": b.uzak_sunucu.acik_mi(),
            "port": a.uzak_port,
            "ag": a.uzak_ag,
            "parmak_izi": parmak,
            "adresler": [f"https://{h}:{a.uzak_port}/" for h in hostlar],
            "tailscale_yok": a.uzak_ag == "tailscale" and not hostlar,
            "cihazlar": b.uzak_depo.liste(),
            "denetim": b.uzak_depo.denetim(20),
        }

    @r.get("/api/uzak")
    async def uzak_durum() -> dict:
        return await asyncio.to_thread(_uzak_durum)

    @r.post("/api/uzak/ac")
    async def uzak_ac() -> dict:
        a = b.ayarlar.oku()
        hostlar = await asyncio.to_thread(_uzak_hostlar)
        if not hostlar:
            raise UygulamaHatasi(
                "Tailscale bagli degil: Tailscale'i acip oturum acin."
                if a.uzak_ag == "tailscale"
                else "Yerel ag adresi bulunamadi."
            )
        cert, key, parmak = await asyncio.to_thread(
            uzak_mod.sertifika, b.veri_dizini / "uzak-tls", hostlar
        )
        uapp = uzak_mod.uzak_uygulamasi(
            b.uzak_depo, b.app.state.uzak_ic_cagri, parmak, lambda: b.ayarlar.oku().dil
        )
        aglar = uzak_mod.TAILSCALE_AGLARI if a.uzak_ag == "tailscale" else None
        asgi = uzak_mod.tam_erisim_asgi(b.uzak_depo, uapp, b.app, b.oturum_anahtari, aglar)
        try:
            baglan = hostlar[0] if a.uzak_ag == "tailscale" else "0.0.0.0"
            await b.uzak_sunucu.ac(asgi, a.uzak_port, cert, key, baglan)
        except OSError as e:
            raise UygulamaHatasi(f"Uzak erisim acilamadi: {e}") from e
        return await asyncio.to_thread(_uzak_durum)

    @r.post("/api/uzak/kapat")
    async def uzak_kapat() -> dict:
        await b.uzak_sunucu.kapat()
        return {"acik": False}

    @r.post("/api/uzak/kod")
    async def uzak_kod(veri: dict) -> dict:
        try:
            return b.uzak_depo.kod_olustur(veri.get("rol", "izleyici"))
        except uzak_mod.UzakHata as e:
            raise UygulamaHatasi(e.mesaj) from e

    @r.delete("/api/uzak/cihaz/{cihaz_id}")
    async def uzak_cihaz_iptal(cihaz_id: str) -> dict:
        try:
            b.uzak_depo.iptal(cihaz_id)
        except uzak_mod.UzakHata as e:
            raise UygulamaHatasi(e.mesaj) from e
        return {"iptal": cihaz_id}

    # ---- Is akislari ve sablonlar ----
    def _akis_baslat(a: Akis) -> None:
        alan = b.sohbet.aktif_alan()
        kayit = b.sohbet.ajan_araclari(alan)
        if kayit is None:
            raise UygulamaHatasi("Is akisi icin once bir proje acin.")

        async def ajan_adimi(hedef: str) -> tuple[str, str, str]:
            run = await b.ajan.baslat(hedef, model=b.ayarlar.oku().aktif_model)
            g = b.ajan._gorevler.get(run.id)
            if g:
                await asyncio.wait({g})
            run = b.run_deposu.getir(run.id)
            return str(run.durum), run.sonuc.ozet or run.hata, run.id

        t = asyncio.create_task(
            akis_mod.calistir(
                a, b.akislar, ajan_adimi, lambda k: kayit.komut_calistir(k, timeout=600)
            )
        )
        akis_gorevleri.add(t)
        t.add_done_callback(akis_gorevleri.discard)

    @r.post("/api/akislar")
    async def akis_olustur(veri: dict) -> dict:
        a = akis_mod.dogrula_veri(veri)
        for x in a.adimlar:
            x.durum, x.deneme, x.sonuc, x.run_id = "bekliyor", 0, "", ""
        b.akislar.kaydet(a)
        _akis_baslat(a)
        return a.model_dump()

    @r.get("/api/akislar")
    async def akis_listesi() -> dict:
        return {"akislar": b.akislar.liste()}

    @r.get("/api/akislar/{akis_id}")
    async def akis_getir(akis_id: str) -> dict:
        return b.akislar.getir(akis_id).model_dump()

    @r.post("/api/akislar/{akis_id}/devam")
    async def akis_devam(akis_id: str) -> dict:
        a = b.akislar.getir(akis_id)
        if a.durum == "calisiyor":
            raise UygulamaHatasi("Akis zaten calisiyor.")
        for x in a.adimlar:
            if x.durum in ("onay_bekliyor", "calisiyor"):
                x.durum = "bekliyor"
        _akis_baslat(a)
        return a.model_dump()

    @r.get("/api/akis-sablonlari")
    async def akis_sablon_listesi() -> dict:
        return {"sablonlar": b.sablonlar.liste()}

    @r.post("/api/akis-sablonlari")
    async def akis_sablon_kaydet(veri: dict) -> dict:
        return b.sablonlar.kaydet(veri).model_dump()

    @r.delete("/api/akis-sablonlari/{sid}")
    async def akis_sablon_sil(sid: str) -> dict:
        b.sablonlar.sil(sid)
        return {"silindi": sid}

    @r.post("/api/akis-sablonlari/{sid}/calistir")
    async def akis_sablon_calistir(sid: str, veri: dict | None = None) -> dict:
        param = (veri or {}).get("parametreler") or {}
        if not isinstance(param, dict):
            raise UygulamaHatasi("parametreler sozluk olmali.")
        a = sablon_uygula(b.sablonlar.getir(sid), {str(k): str(v) for k, v in param.items()})
        b.akislar.kaydet(a)
        _akis_baslat(a)
        return a.model_dump()

    return r
