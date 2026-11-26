"""Projeler, izinler/onaylar, kod inceleme, terminal/masaustu/tarayici ve sir kasasi uclari."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter

from app import URUN_ADI
from app.agent import cli_ajan
from app.agent import koordinasyon as koord
from app.agent import review as rv
from app.agent import superajan as sa
from app.agent.dosyalar import AjanDosyaAraclari, KokKapsami
from app.agent.policy import Istek, Karar, YanEtki
from app.agent.tarayici import playwright_var
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.exceptions import UygulamaHatasi, YerelLLMHatasi, YetkiYok
from app.routers import (
    CcIzinIstegi,
    GeriAlIstegi,
    GirdiIstegi,
    GizliProjeIstegi,
    GuvenIstegi,
    HunkIstegi,
    KartKomutIstegi,
    ModellerIstegi,
    ModIstegi,
    OnayIstegi,
    ProjeIstegi,
    YolIstegi,
)
from app.services import masaustu_ayar as mda
from app.services import sirlar
from app.services.sohbet import VARSAYILAN_ALAN_ID
from app.services.yerel_llm import MODELLER
from app.services.yonlendirici import gunluk_maliyet_usd, maliyet_analitigi

PR_ALANLARI = "number,title,url,state,isDraft,additions,deletions,changedFiles,author,createdAt"
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


def router_olustur(b: Any) -> APIRouter:
    r = APIRouter()
    pr_onbellek: dict[tuple[str, str], tuple[float, dict | None]] = {}

    def _okuyucu() -> AjanDosyaAraclari:
        return AjanDosyaAraclari(KokKapsami(b.sohbet.aktif_alan().izinli_kokler))

    def _proje_git():
        alan = b.sohbet.aktif_alan()
        kayit = b.sohbet.ajan_araclari(alan)
        if kayit is None:
            raise UygulamaHatasi("Review icin once bir proje acin.")
        return alan, kayit

    def _dal_pr(klasor: str, dal: str) -> dict | None:
        kayit = pr_onbellek.get((klasor, dal))
        if kayit and time.monotonic() - kayit[0] < 300:
            return kayit[1]
        pr = None
        try:
            kod, cikti = sa.gh(
                "pr",
                "view",
                "--json",
                "number,title,url,additions,deletions,state",
                cwd=klasor,
                sure=15,
            )
            pr = json.loads(cikti) if kod == 0 else None
        except (UygulamaHatasi, subprocess.TimeoutExpired, OSError, ValueError):
            pass
        pr_onbellek[(klasor, dal)] = (time.monotonic(), pr)
        return pr

    # ---- Review ve GitHub PR karti ----
    @r.get("/api/review/diff")
    async def review_diff(staged: bool = False) -> dict:
        _, kayit = _proje_git()
        return await asyncio.to_thread(kayit.git.git_diff, "", staged)

    @r.get("/api/github/pr")
    async def github_pr(url: str) -> dict:
        if not PR_URL.fullmatch(url):
            raise UygulamaHatasi("Gecersiz PR adresi.")
        kayit = pr_onbellek.get(("url", url))
        if kayit and time.monotonic() - kayit[0] < 120:
            return kayit[1] or {}

        def _getir() -> dict | None:
            try:
                kod, cikti = sa.gh("pr", "view", url, "--json", PR_ALANLARI, sure=15)
                return json.loads(cikti) if kod == 0 else None
            except (UygulamaHatasi, subprocess.TimeoutExpired, OSError, ValueError):
                return None

        pr = await asyncio.to_thread(_getir)
        pr_onbellek[("url", url)] = (time.monotonic(), pr)
        return pr or {}

    @r.get("/api/proje/degisiklikler")
    async def proje_degisiklikler() -> dict:
        kayit = b.sohbet.ajan_araclari(b.sohbet.aktif_alan())
        makine = {"bilgisayar": platform.node()}
        if kayit is None:
            return {"repo": False} | makine
        ozet = await asyncio.to_thread(kayit.git.git_ozet) | makine
        if ozet.get("klasor"):
            ozet["worktree"] = (Path(ozet["klasor"]) / ".git").is_file()
        if ozet["repo"] and b.ayarlar.oku().ag_acik:
            ozet["pr"] = await asyncio.to_thread(_dal_pr, ozet["klasor"], ozet["dal"])
        return ozet

    @r.post("/api/review")
    async def review_yap(staged: bool = False, derin: bool = False) -> dict:
        alan, kayit = _proje_git()
        d = await asyncio.to_thread(kayit.git.git_diff, "", staged)
        if d.get("hata"):
            raise UygulamaHatasi(d["hata"])
        diff = d.get("diff") or ""
        if not diff.strip():
            return {
                "ozet": "Incelenecek degisiklik yok (git diff bos).",
                "bulgular": [],
                "dosyalar": [],
                "diff_kesildi": False,
            }
        kural = rv.review_md_oku(alan.izinli_kokler) if alan.talimat_okunur_mu() else ""
        odaklar = list(rv.ODAKLAR) if derin else [None]
        gecisler: dict[str, dict] = {}
        async with b.yonetici.kullan() as llm:
            for odak in odaklar:
                istem_ = rv.odakli_istem(diff, kural, odak) if odak else rv.istem(diff, kural)
                try:
                    cevap = await llm.json_cikti(
                        istem_, rv.SEMA, ad="review", max_tokens=3000, dusunme="kapali"
                    )
                except YerelLLMHatasi as e:
                    raise UygulamaHatasi(f"Review yapilamadi: {e}") from e
                gecisler[odak or "genel"] = cevap if isinstance(cevap, dict) else {}
        sonuc = rv.birlestir(gecisler, diff) if derin else rv.sonuclandir(gecisler["genel"], diff)
        sonuc["review_md"] = bool(kural)
        return sonuc

    # ---- Projeler / Calisma alani ----
    @r.get("/api/projeler")
    async def proje_listesi() -> dict:
        aktif = b.projeler.aktif()
        return {
            "alanlar": [a.model_dump(mode="json") for a in b.projeler.liste()],
            "aktif": aktif.model_dump(mode="json") if aktif else None,
            "etkin": b.sohbet.aktif_alan().model_dump(mode="json"),
            "modlar": [str(m) for m in Mod],
            "guvenler": [str(g) for g in Guven],
        }

    @r.get("/api/proje/dosyalar")
    async def proje_dosyalar(yol: str = "") -> dict:
        res = await asyncio.to_thread(_okuyucu().klasor_listele, yol, 1)
        if "hata" in res:
            raise UygulamaHatasi(res["hata"])
        return {
            "klasor": res["klasor"],
            "ogeler": [
                {"ad": o.removeprefix("[klasor] "), "klasor": o.startswith("[klasor] ")}
                for o in res["ogeler"]
            ],
        }

    @r.get("/api/proje/dosya")
    async def proje_dosya(yol: str) -> dict:
        res = await asyncio.to_thread(_okuyucu().dosya_oku, yol, 1, 2000)
        if "hata" in res:
            raise UygulamaHatasi(res["hata"])
        return res

    @r.post("/api/projeler")
    async def proje_ac(istek: ProjeIstegi) -> dict:
        a = b.ayarlar.oku()
        varsayilan = (a.varsayilan_koordinator, a.varsayilan_uygulayici)
        return b.projeler.ac(istek.yol, istek.ad, istek.guven, varsayilan).model_dump(mode="json")

    @r.post("/api/projeler/{alan_id}/etkin")
    async def proje_etkin(alan_id: str) -> dict:
        if alan_id == VARSAYILAN_ALAN_ID:
            b.projeler.kapat()
        else:
            b.projeler.etkinlestir(alan_id)
        return {"etkin": b.sohbet.aktif_alan().model_dump(mode="json")}

    @r.post("/api/projeler/kapat")
    async def proje_kapat() -> dict:
        b.projeler.kapat()
        return {"aktif": None, "etkin": b.sohbet.aktif_alan().model_dump(mode="json")}

    @r.delete("/api/projeler/{alan_id}")
    async def proje_sil(alan_id: str) -> dict:
        b.projeler.sil(alan_id)
        return {"silindi": alan_id, "silinen_sohbet": b.alan_sohbetlerini_sil(alan_id)}

    @r.put("/api/projeler/{alan_id}/mod")
    async def proje_mod(alan_id: str, istek: ModIstegi) -> dict:
        return b.projeler.mod_ayarla(alan_id, istek.mod).model_dump(mode="json")

    @r.put("/api/projeler/{alan_id}/modeller")
    async def proje_modeller(alan_id: str, istek: ModellerIstegi) -> dict:
        if b.ayarlar.oku().saglayici == "openrouter":
            for m in (istek.koordinator_model, istek.uygulayici_model):
                if m.strip() in MODELLER:
                    raise UygulamaHatasi(f"OpenRouter seçili; yerel model ({m}) kullanılamaz.")
        if istek.koordinator_model.strip().startswith("cli:"):
            raise UygulamaHatasi("Abonelik CLI'ı (cli:...) yalnızca uygulayıcı olabilir.")
        if (u := istek.uygulayici_model.strip()).startswith("cli:"):
            ad = u.split(":")[1] if u.count(":") else ""
            if not cli_ajan.durum().get(ad):
                raise UygulamaHatasi(
                    f"'{ad}' CLI'ı kurulu değil; cli:claude, cli:codex ya da cli:antigravity seçin."
                )
        return b.projeler.modeller_ayarla(
            alan_id, istek.koordinator_model, istek.uygulayici_model
        ).model_dump(mode="json")

    @r.put("/api/projeler/{alan_id}/guven")
    async def proje_guven(alan_id: str, istek: GuvenIstegi) -> dict:
        return b.projeler.guven_ayarla(alan_id, istek.guven).model_dump(mode="json")

    @r.put("/api/projeler/{alan_id}/gizli")
    async def proje_gizli(alan_id: str, istek: GizliProjeIstegi) -> dict:
        return b.projeler.gizli_ayarla(alan_id, istek.gizli_proje).model_dump(mode="json")

    @r.get("/api/maliyet/durum")
    async def maliyet_durum() -> dict:
        bugun = gunluk_maliyet_usd(b.run_deposu, b.oturumlar)
        sinir = b.ayarlar.oku().gunluk_butce_usd
        return {
            "bugun_usd": bugun,
            "gunluk_butce_usd": sinir,
            "asildi": bool(sinir > 0 and bugun >= sinir),
        }

    @r.get("/api/maliyet/analitik")
    async def maliyet_analitik() -> dict:
        return maliyet_analitigi(b.run_deposu, b.ayarlar.oku())

    @r.post("/api/projeler/{alan_id}/kok")
    async def proje_kok_ekle(alan_id: str, istek: YolIstegi) -> dict:
        return b.projeler.kok_ekle(alan_id, istek.yol).model_dump(mode="json")

    @r.post("/api/projeler/{alan_id}/klasor")
    async def proje_klasor(alan_id: str, istek: YolIstegi) -> dict:
        return b.projeler.klasor_yetkilendir(alan_id, istek.yol).model_dump(mode="json")

    # ---- Izinler, onaylar ve etkinlik ----
    @r.get("/api/izinler")
    async def izinler() -> dict:
        alan = b.sohbet.aktif_alan()
        return {**b.politika.bilgi(alan), "alan": alan.model_dump(mode="json")}

    @r.get("/api/onaylar")
    async def onay_gecmisi() -> dict:
        return {"onaylar": b.politika.onaylar.gecmis()}

    @r.get("/api/etkinlik")
    async def etkinlik(adet: int = 200, yalniz_yan_etkili: bool = False) -> dict:
        onay_kapsami = {o["id"]: o for o in b.politika.onaylar.gecmis(500)}
        satirlar = []
        for run in b.run_deposu.liste():
            for a in run.adimlar:
                if a.arac in ("plan_guncelle", "gorevi_bitir"):
                    continue
                if yalniz_yan_etkili and not a.yan_etkili:
                    continue
                o = onay_kapsami.get(a.onay_id) if a.onay_id else None
                satirlar.append(
                    {
                        "zaman": a.zaman,
                        "run": run.id,
                        "gorev": run.hedef[:120],
                        "no": a.no,
                        "arac": a.arac,
                        "durum": str(a.durum.value),
                        "yan_etkili": a.yan_etkili,
                        "aciklama": a.aciklama[:200],
                        "dosya": a.dosya,
                        "onay": (
                            {"karar": o["karar"], "kapsam": o.get("kapsam", "tek")} if o else None
                        ),
                    }
                )
        satirlar.sort(key=lambda x: x["zaman"], reverse=True)
        return {"etkinlik": satirlar[: max(1, min(adet, 1000))]}

    @r.get("/api/onay-kurallari")
    async def onay_kurallari() -> dict:
        return {"kurallar": b.politika.onaylar.kurallar()}

    @r.delete("/api/onay-kurallari/{onay_id}")
    async def onay_kurali_sil(onay_id: str) -> dict:
        b.politika.onaylar.kural_sil(onay_id)
        return {"kurallar": b.politika.onaylar.kurallar()}

    @r.post("/api/cc-izin")
    async def cc_izin_karar(istek: CcIzinIstegi) -> dict:
        from app.agent import cc_izin
        from app.agent.policy import BAGLAM, islem_anahtari, islem_hashi

        iz = cc_izin.istek_cevir(istek.arac, istek.girdi)
        kok = [str(Path(istek.klasor).resolve())] if istek.klasor else []
        alan = CalismaAlani(ad="CLI Izin Koprusu", kokler=kok, mod=Mod.otomatik)
        sonuc = b.politika.degerlendir(iz, alan)
        if sonuc.karar is not Karar.sor:
            return {"izin": sonuc.izinli, "neden": sonuc.neden}
        h = islem_hashi(iz, sonuc.cozulmus_yol)
        jeton = BAGLAM.set(istek.baglam)
        try:
            gecerli = b.politika.onaylar.gecerli_onay(h, islem_anahtari(iz), istek.baglam)
            if gecerli is not None:
                b.politika.onaylar.tuket(gecerli.id)
                return {"izin": True, "neden": "Onceki onay gecerli."}
            onay = b.politika.onaylar.olustur(iz, h)
        finally:
            BAGLAM.reset(jeton)
        karar = "bekliyor"
        for _ in range(cc_izin.BEKLEME_SN):
            await asyncio.sleep(1)
            o = next((x for x in b.politika.onaylar.gecmis(200) if x["id"] == onay.id), None)
            karar = o["karar"] if o else "yok"
            if karar != "bekliyor":
                break
        if karar == "onayli":
            b.politika.onaylar.tuket(onay.id)
            return {"izin": True, "neden": "Kullanici onayladi."}
        if karar == "bekliyor":
            with contextlib.suppress(YetkiYok):
                b.politika.onaylar.karar_ver(onay.id, False)
        return {"izin": False, "neden": f"Kullanici onaylamadi ({sonuc.neden})"}

    @r.post("/api/onaylar/{onay_id}")
    async def onay_karar(onay_id: str, istek: OnayIstegi) -> dict:
        return await b.onay_islem(onay_id, istek.onayla, istek.kapsam)

    # ---- Checkpoint, Terminal, Masaustu, Tarayici, Koordinasyon ve Sirlar ----
    @r.post("/api/tarayici/kapat")
    async def tarayici_kapat() -> dict:
        return await asyncio.to_thread(b.sohbet.tarayici.kapat)

    @r.get("/api/koordinasyon")
    async def koordinasyon_durumu() -> dict:
        return {
            "proje": koord.KOORD.aktifler(b.sohbet.aktif_alan().id),
            "tum": koord.KOORD.tumu(),
        }

    @r.put("/api/tarayici/panel")
    async def tarayici_paneli(istek: dict) -> dict:
        adres = str(istek.get("adres", "")).strip()[:2000]
        u = urlsplit(adres)
        if adres and (u.scheme not in ("http", "https") or not u.hostname or u.username):
            raise UygulamaHatasi("Gecersiz adres.")
        b.sohbet.tarayici_paneli = adres
        return {"adres": adres}

    @r.get("/api/tarayici")
    async def tarayici_durum() -> dict:
        return {"acik": b.sohbet.tarayici.acik_mi(), "playwright": playwright_var()}

    @r.post("/api/masaustu/durdur")
    async def masaustu_durdur() -> dict:
        return b.sohbet.masaustu.durdur()

    @r.post("/api/masaustu/devam")
    async def masaustu_devam() -> dict:
        return b.sohbet.masaustu.devam()

    @r.get("/api/checkpointler")
    async def checkpoint_listesi() -> dict:
        return {"checkpointler": b.checkpointler.liste()}

    @r.get("/api/checkpointler/{cp_id}")
    async def checkpoint_onizle(cp_id: str) -> dict:
        return b.checkpointler.onizle(cp_id)

    @r.post("/api/checkpointler/{cp_id}/geri-al")
    async def checkpoint_geri_al(cp_id: str, istek: GeriAlIstegi) -> dict:
        return b.checkpointler.geri_al(cp_id, istek.yollar or None)

    @r.get("/api/checkpointler/{cp_id}/hunklar")
    async def checkpoint_hunklar(cp_id: str, yol: str) -> dict:
        return b.checkpointler.hunklar(cp_id, yol)

    @r.post("/api/checkpointler/{cp_id}/hunk-geri-al")
    async def checkpoint_hunk_geri_al(cp_id: str, istek: HunkIstegi) -> dict:
        return b.checkpointler.hunk_geri_al(cp_id, istek.yol, istek.hunklar)

    @r.post("/api/komutlar/{is_id}/girdi")
    async def komut_girdi_ucu(is_id: str, istek: GirdiIstegi) -> dict:
        return await b.komutlar.girdi_gonder(is_id, istek.metin)

    @r.post("/api/kart-komut")
    async def kart_komut(istek: KartKomutIstegi) -> dict:
        alan = b.sohbet.aktif_alan()
        if b.politika.mod(alan) in (Mod.planla, Mod.sohbet):
            raise YetkiYok("Planla veya Sohbet modunda karttan komut calistirilmaz.")
        if not alan.izinli_kokler:
            raise YetkiYok("Etkin calisma alaninda izinli klasor yok.")
        kok = alan.izinli_kokler[0]
        sonuc = b.politika.degerlendir(
            Istek(
                arac="kart_komut",
                yan_etki=YanEtki.komut,
                yol=str(kok),
                komut=istek.komut,
                ozet=f"Kart komutu: {istek.komut}",
            ),
            alan,
        )
        if sonuc.karar is Karar.ret:
            raise YetkiYok(sonuc.neden)
        if not istek.onay:
            raise YetkiYok("Kart komutu kullanici onayi olmadan calistirilmaz.")
        is_ = await b.komutlar.baslat(istek.komut, Path(kok), timeout=30, kok=Path(kok))
        await b.komutlar.bekle(is_)
        return b.komutlar.ozet(is_)

    @r.get("/api/komutlar")
    async def komut_listesi() -> dict:
        return {"isler": [b.komutlar.ozet(i) for i in b.komutlar.isler.values()]}

    @r.get("/api/masaustu")
    async def masaustu_durum() -> dict:
        return {
            "baslangicta_ac": mda.baslangic_durumu(),
            "kisayol_hata": b.kisayol.hata,
            "depolama": await asyncio.to_thread(mda.depolama, b.veri_dizini),
            "veri_dizini": str(b.veri_dizini),
        }

    @r.post("/api/bildirim")
    async def bildirim_gonder(veri: dict) -> dict:
        ok = await asyncio.to_thread(
            mda.bildirim, str(veri.get("baslik", URUN_ADI)), str(veri.get("metin", ""))
        )
        return {"gonderildi": ok}

    @r.get("/api/sirlar")
    async def sir_listesi() -> dict:
        return {"adlar": sirlar.KASA.adlar()}

    @r.post("/api/sirlar")
    async def sir_ekle(istek: dict) -> dict:
        ad = await asyncio.to_thread(
            sirlar.KASA.ekle, str(istek.get("deger", "")), str(istek.get("ad", ""))
        )
        return {"ad": ad}

    @r.delete("/api/sirlar/{ad}")
    async def sir_sil(ad: str) -> dict:
        await asyncio.to_thread(sirlar.KASA.sil, ad)
        return {"silindi": ad}

    @r.post("/api/dosya/goster")
    async def dosya_goster(istek: dict) -> dict:
        ham = str(istek.get("yol", "")).strip().strip('"')
        p = Path(ham)
        if not ham or not p.is_absolute() or not p.exists():
            raise UygulamaHatasi("Bu yol bulunamadi.")
        hedef = ["explorer", str(p)] if p.is_dir() else ["explorer", f"/select,{p}"]
        subprocess.Popen(hedef)  # noqa: S603
        return {"gosterildi": True}

    @r.post("/api/masaustu/klasor-ac")
    async def veri_klasoru_ac() -> dict:
        os.startfile(b.veri_dizini)  # noqa: S606
        return {"acildi": True}

    @r.get("/api/uyanik")
    async def uyanik_durum() -> dict:
        return {"acik": b.uyanik.acik}

    @r.put("/api/uyanik")
    async def uyanik_ayarla(veri: dict) -> dict:
        return {"acik": b.uyanik.ayarla(bool(veri.get("acik")))}

    @r.post("/api/terminal")
    async def terminal_calistir(veri: dict) -> dict:
        kokler = b.sohbet.aktif_alan().izinli_kokler
        cwd = Path(kokler[0]) if kokler else Path.home()
        is_ = await b.komutlar.baslat(
            str(veri.get("komut", ""))[:4000],
            cwd,
            arka_plan=True,
            timeout=3600,
            sahip="terminal",
            bash=False,
        )
        return b.komutlar.ozet(is_)

    @r.get("/api/komutlar/{is_id}")
    async def komut_getir(is_id: str) -> dict:
        return b.komutlar.ozet(b.komutlar.getir(is_id))

    @r.post("/api/komutlar/{is_id}/durdur")
    async def komut_durdur_ucu(is_id: str) -> dict:
        return await b.komutlar.durdur(is_id)

    return r
