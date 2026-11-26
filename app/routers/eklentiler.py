"""Eklentiler: pluginler, uzantilar, MCP, OAuth, arac paketleri, Composio, hook'lar ve skiller."""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.agent import mcp_ice, mcp_oauth
from app.agent.hooks import OLAYLAR as HOOK_OLAYLARI
from app.exceptions import UygulamaHatasi
from app.routers import (
    SkillDurumIstegi,
    SkillIceAdIstegi,
    SkillIceIstegi,
    SkillIceKurIstegi,
    SkillIstegi,
    TalimatIstegi,
)
from app.services import cc_plugin as ccp
from app.services import skiller as skl
from app.services.sohbet import VARSAYILAN_ALAN_ID
from app.services.uzantilar import ONIZLEME_CSP


def router_olustur(b: Any) -> APIRouter:
    r = APIRouter()
    oauth_bekleyen: dict[str, dict] = {}

    def ozel_komutlar() -> list[dict]:
        kaynaklar: list[tuple[str, Path]] = []
        alan = b.sohbet.aktif_alan()
        if alan.id != VARSAYILAN_ALAN_ID and alan.talimat_okunur_mu():
            kaynaklar += [("proje", Path(k) / ".claude" / "commands") for k in alan.kokler]
        kaynaklar.append(("kullanici", b.app.state.kullanici_komut_dizini()))
        out: list[dict] = []
        gorulen: set[str] = set()
        for kaynak, dizin in kaynaklar:
            for k in ccp.komut_dosyalari(dizin):
                if k["ad"] not in gorulen:
                    gorulen.add(k["ad"])
                    out.append({**k, "kaynak": kaynak, "kok": dizin})
        return out

    # ---- Pluginler ----
    @r.get("/api/pluginler")
    async def plugin_listesi() -> dict:
        return {"pluginler": b.pluginler.liste()}

    @r.post("/api/pluginler/karantina")
    async def plugin_karantina(veri: dict) -> dict:
        return await asyncio.to_thread(
            b.pluginler.karantinaya_al, str(veri.get("yol", "")), str(veri.get("ad", ""))
        )

    @r.get("/api/pluginler/katalog")
    async def plugin_katalog() -> dict:
        return {"katalog": b.pluginler.katalog()}

    @r.post("/api/pluginler/katalog/{ad}")
    async def plugin_katalogdan(ad: str) -> dict:
        return await asyncio.to_thread(b.pluginler.katalogdan_karantina, ad)

    @r.post("/api/pluginler/claude-code/esitle")
    async def plugin_cc_esitle() -> dict:
        return await asyncio.to_thread(b.cc_esitle)

    @r.get("/api/pluginler/claude-code")
    async def plugin_claude_code() -> dict:
        return {"pluginler": b.pluginler.claude_code_pluginleri()}

    @r.post("/api/pluginler/marketplace")
    async def plugin_marketplace(veri: dict) -> dict:
        return b.pluginler.marketplace(str(veri.get("kaynak", "")))

    @r.post("/api/pluginler/marketplace/kur")
    async def plugin_marketplace_karantina(veri: dict) -> dict:
        return await asyncio.to_thread(
            b.pluginler.marketplace_karantina, str(veri.get("kaynak", "")), str(veri.get("ad", ""))
        )

    @r.post("/api/pluginler/git")
    async def plugin_git(veri: dict) -> dict:
        return await asyncio.to_thread(
            b.pluginler.git_karantina, str(veri.get("url", "")), str(veri.get("ref", ""))
        )

    @r.get("/api/pluginler/komutlar")
    async def plugin_komutlari() -> dict:
        ozel = [
            {
                "komut": k["ad"],
                "kisa": k["ad"],
                "plugin": "",
                "kaynak": k["kaynak"],
                "aciklama": k["aciklama"],
                "ipucu": k["ipucu"],
            }
            for k in await asyncio.to_thread(ozel_komutlar)
        ]
        return {"komutlar": [*ozel, *b.pluginler.komutlar()]}

    @r.post("/api/pluginler/komut")
    async def plugin_komut(veri: dict) -> dict:
        komut, arg = str(veri.get("komut", "")), str(veri.get("arg", ""))[:4000]
        for k in await asyncio.to_thread(ozel_komutlar):
            if k["ad"] == komut:
                istem = ccp.komut_genislet(k["govde"], arg, k["kok"])
                return {"plugin": "", "kaynak": k["kaynak"], "komut": komut, "istem": istem}
        return b.pluginler.komut_genislet(komut, arg)

    @r.put("/api/pluginler/{ad}/bilesen")
    async def plugin_bilesen(ad: str, veri: dict) -> dict:
        return b.pluginler.bilesen_ac(ad, str(veri.get("tur", "")), bool(veri.get("acik")))

    @r.post("/api/pluginler/kur")
    async def plugin_kur(veri: dict) -> dict:
        return await asyncio.to_thread(b.pluginler.kur, str(veri.get("karantina", "")))

    @r.post("/api/pluginler/{ad}/geri-al")
    async def plugin_geri_al(ad: str) -> dict:
        return b.pluginler.geri_al(ad)

    @r.put("/api/pluginler/{ad}/durum")
    async def plugin_durum(ad: str, veri: dict) -> dict:
        return b.pluginler.ac_kapat(ad, bool(veri.get("acik")))

    @r.delete("/api/pluginler/{ad}")
    async def plugin_kaldir(ad: str) -> dict:
        b.pluginler.kaldir(ad)
        return {"silindi": ad}

    # ---- Uzantilar ----
    @r.get("/api/uzantilar")
    async def uzanti_listesi() -> dict:
        return {"uzantilar": b.uzantilar.liste(), "komutlar": b.uzantilar.komut_listesi()}

    @r.post("/api/uzantilar/karantina")
    async def uzanti_karantina(veri: dict) -> dict:
        yol = str(veri.get("yol", "")).strip()
        if yol.startswith("https://"):
            return await asyncio.to_thread(b.uzantilar.git_karantina, yol)
        return await asyncio.to_thread(b.uzantilar.karantinaya_al, yol)

    @r.get("/api/uzantilar/ui")
    async def uzanti_ui() -> dict:
        return {"yuzeyler": await asyncio.to_thread(b.uzantilar.ui)}

    @r.post("/api/uzantilar/kur")
    async def uzanti_kur(veri: dict) -> dict:
        return await asyncio.to_thread(b.uzantilar.kur, str(veri.get("ad", "")))

    @r.put("/api/uzantilar/{ad}/durum")
    async def uzanti_durum(ad: str, veri: dict) -> dict:
        return b.uzantilar.ac_kapat(ad, bool(veri.get("acik")))

    @r.delete("/api/uzantilar/{ad}")
    async def uzanti_kaldir(ad: str) -> dict:
        b.uzantilar.kaldir(ad)
        return {"silindi": ad}

    @r.post("/api/uzantilar/komut")
    async def uzanti_komut(veri: dict) -> dict:
        return await asyncio.to_thread(
            b.uzantilar.komut, str(veri.get("komut", "")), str(veri.get("arg", ""))
        )

    @r.get("/api/uzantilar/{ad}/panel")
    async def uzanti_panel(ad: str) -> dict:
        p = await asyncio.to_thread(b.uzantilar.panel, ad)
        return {**p, "csp": ONIZLEME_CSP}

    # ---- MCP, OAuth, Arac Paketleri, Composio ----
    @r.post("/api/mcp/{ad}/oauth")
    async def mcp_oauth_baslat(ad: str, istek: Request) -> dict:
        s = next((x for x in b.mcp.liste() if x.ad == ad), None)
        if s is None or not s.url:
            raise UygulamaHatasi("OAuth girisi yalniz uzak (URL) baglayicilar icin.")
        geri = str(istek.base_url).rstrip("/") + "/api/mcp/oauth/geri"

        def _baslat() -> tuple[str, dict]:
            with httpx.Client(timeout=mcp_oauth.ZAMAN) as c:
                return mcp_oauth.baslat(s.url, geri, c, s.oauth.get("client_id", ""))

        adres, bek = await asyncio.to_thread(_baslat)
        simdi = time.time()
        for k in [k for k, v in oauth_bekleyen.items() if simdi - v["zaman"] > 600]:
            oauth_bekleyen.pop(k)
        oauth_bekleyen[bek["durum"]] = bek | {"ad": ad}
        await asyncio.to_thread(webbrowser.open, adres)
        return {"adres": adres}

    @r.get("/api/mcp/oauth/geri")
    async def mcp_oauth_geri(state: str = "", code: str = "", error: str = "") -> Response:
        bek = oauth_bekleyen.pop(state, None)
        if bek is None or time.time() - bek["zaman"] > 600:
            sonuc = "Gecersiz ya da suresi dolmus giris istegi."
        elif error or not code:
            sonuc = f"Giris iptal edildi: {error or 'kod yok'}"
        else:
            try:

                def _tamamla() -> dict:
                    with httpx.Client(timeout=mcp_oauth.ZAMAN) as c:
                        return mcp_oauth.tamamla(bek, code, c)

                b.mcp.oauth_kaydet(bek["ad"], await asyncio.to_thread(_tamamla))
                sonuc = f"'{bek['ad']}' baglayicisina giris yapildi. Bu sekmeyi kapatabilirsin."
            except UygulamaHatasi as e:
                sonuc = str(e)
        govde = (
            "<!doctype html><meta charset=utf-8><title>Kairo</title>"
            f"<body style='font:16px system-ui;padding:40px'>{sonuc.replace('<', '&lt;')}</body>"
        )
        return Response(govde, media_type="text/html; charset=utf-8")

    @r.get("/api/mcp/ice-aktar")
    async def mcp_bulunanlar() -> dict:
        var = {s.ad for s in b.mcp.liste()}
        bulunan = await asyncio.to_thread(mcp_ice.bul)
        return {
            "bulunan": [x | {"var": x["ad"] in var} for x in bulunan],
            "dizin": [d | {"var": d["ad"] in var} for d in mcp_ice.DIZIN],
        }

    @r.post("/api/mcp/ice-aktar")
    async def mcp_ice_aktar(veri: dict) -> dict:
        istenen = set(veri.get("anahtarlar") or [])
        eklenen, hatalar = [], []
        for x in await asyncio.to_thread(mcp_ice.bul):
            if x["anahtar"] not in istenen:
                continue
            try:
                b.mcp.ekle(x["veri"])
                eklenen.append(x["ad"])
            except (UygulamaHatasi, ValueError) as e:
                hatalar.append(f"{x['ad']}: {str(e)[:120]}")
        return {"eklenen": eklenen, "hatalar": hatalar}

    @r.get("/api/arac-paketleri")
    async def arac_paketi_listesi() -> dict:
        return {"paketler": await asyncio.to_thread(b.app.state.arac_paketleri.liste)}

    @r.post("/api/arac-paketleri/{ad}/kur")
    async def arac_paketi_kur(ad: str) -> dict:
        return await asyncio.to_thread(b.app.state.arac_paketleri.kur, ad)

    @r.delete("/api/arac-paketleri/{ad}")
    async def arac_paketi_kaldir(ad: str) -> dict:
        return await asyncio.to_thread(b.app.state.arac_paketleri.kaldir, ad)

    @r.get("/api/mcp")
    async def mcp_listesi() -> dict:
        durum = await asyncio.to_thread(b.mcp.durumlar)
        kendi = {s.ad for s in b.mcp.liste()}
        return {
            "sunucular": [
                {**s.disari(), "ek": s.ad not in kendi, "baglanti": durum.get(s.ad, {})}
                for s in b.mcp.tum()
            ]
        }

    @r.post("/api/github/baglan")
    async def github_baglan(kontrol: bool = False) -> dict:
        import app.api as api_mod

        gh = api_mod.shutil.which("gh") or next(
            (
                str(p)
                for p in [Path(os.environ.get("PROGRAMFILES", "")) / "GitHub CLI" / "gh.exe"]
                if p.is_file()
            ),
            None,
        )
        if not gh:
            return {"durum": "gh_yok", "komut": "winget install --id GitHub.cli -e"}

        def _token() -> str:
            res = subprocess.run(
                [gh, "auth", "token", "-h", "github.com"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return res.stdout.strip() if res.returncode == 0 else ""

        token = await asyncio.to_thread(_token)
        if not token and kontrol:
            return {"durum": "giris_bekliyor"}
        if not token:
            subprocess.Popen(
                [
                    gh,
                    "auth",
                    "login",
                    "-h",
                    "github.com",
                    "-p",
                    "https",
                    "-w",
                    "-s",
                    "repo,read:org,gist",
                ],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            return {"durum": "giris_bekliyor"}
        veri = {
            "ad": "github",
            "url": "https://api.githubcopilot.com/mcp/",
            "aktif": True,
            "basliklar": {"Authorization": f"Bearer {token}"},
        }
        if any(x.ad == "github" for x in b.mcp.liste()):
            b.mcp.guncelle("github", veri)
        else:
            b.mcp.ekle(veri)
        return {"durum": "bagli"}

    @r.post("/api/mcp")
    async def mcp_ekle(veri: dict) -> dict:
        return b.mcp.ekle(veri)

    @r.put("/api/mcp/{ad}")
    async def mcp_guncelle(ad: str, veri: dict) -> dict:
        return b.mcp.guncelle(ad, veri)

    @r.delete("/api/mcp/{ad}")
    async def mcp_sil(ad: str) -> dict:
        b.mcp.sil(ad)
        return {"silindi": ad}

    @r.post("/api/mcp/{ad}/test")
    async def mcp_test(ad: str) -> dict:
        return await asyncio.to_thread(b.mcp.test, ad)

    @r.get("/api/composio")
    async def composio_durum() -> dict:
        return b.composio.durum()

    @r.post("/api/composio/anahtar")
    async def composio_anahtar(veri: dict) -> dict:
        return await asyncio.to_thread(b.composio.anahtar_kaydet, str(veri.get("anahtar", "")))

    @r.delete("/api/composio/anahtar")
    async def composio_anahtar_sil() -> dict:
        return b.composio.anahtar_sil()

    @r.get("/api/composio/uygulamalar")
    async def composio_uygulamalar(
        arama: str = "", bagli: bool | None = None, imlec: str = ""
    ) -> dict:
        return await asyncio.to_thread(b.composio.uygulamalar, arama, bagli, imlec)

    @r.post("/api/composio/baglan/{toolkit}")
    async def composio_baglan(toolkit: str) -> dict:
        sonuc = await asyncio.to_thread(b.composio.baglan, toolkit)
        await asyncio.to_thread(webbrowser.open, sonuc["adres"])
        return sonuc

    @r.delete("/api/composio/baglanti/{baglanti_id}")
    async def composio_baglanti_kes(baglanti_id: str) -> dict:
        return await asyncio.to_thread(b.composio.baglanti_kes, baglanti_id)

    # ---- Hook'lar ----
    @r.get("/api/hooks")
    async def hook_listesi() -> dict:
        return {
            "hooks": [h.model_dump() for h in b.hooklar.liste()],
            "olaylar": list(HOOK_OLAYLARI),
        }

    @r.post("/api/hooks")
    async def hook_ekle(veri: dict) -> dict:
        return b.hooklar.ekle(veri).model_dump()

    @r.put("/api/hooks/{hook_id}")
    async def hook_guncelle(hook_id: str, veri: dict) -> dict:
        return b.hooklar.guncelle(hook_id, veri).model_dump()

    @r.delete("/api/hooks/{hook_id}")
    async def hook_sil(hook_id: str) -> dict:
        b.hooklar.sil(hook_id)
        return {"silindi": hook_id}

    @r.post("/api/hooks/{hook_id}/test")
    async def hook_test(hook_id: str) -> dict:
        return await asyncio.to_thread(b.hooklar.test_et, hook_id)

    # ---- Talimatlar ve Skill'ler ----
    @r.get("/api/talimatlar")
    async def talimat_oku() -> dict:
        a = b.ayarlar.oku()
        kaynaklar = b.talimatlar.kaynaklar(claude=True, uygulama=True)

        def kisa(tur: str) -> list[dict]:
            return [{**k, "metin": k["metin"][:4000]} for k in kaynaklar if k["tur"] == tur]

        return {
            "kairo": kisa("uygulama"),
            "claude": kisa("claude"),
            "claude_acik": a.claude_talimatlari,
            "uygulama": b.talimatlar.uygulama_oku(),
            "uygulama_acik": a.uygulama_talimati,
            "uygulama_yol": str(b.talimatlar.uygulama_yolu),
            "baglam_token": a.baglam_token,
        }

    @r.put("/api/talimatlar")
    async def talimat_yaz(istek: TalimatIstegi) -> dict:
        return {"uygulama": b.talimatlar.uygulama_yaz(istek.metin)}

    @r.get("/api/skiller")
    async def skill_liste() -> dict:
        kapali = set(b.ayarlar.oku().kapali_skiller)
        liste = [{**s.ozet(), "acik": s.ad not in kapali} for s in b.skiller.kesfet()]
        return {
            "skiller": liste,
            "kaynaklar": [
                {"kaynak": k, "yol": str(p), "var": p.is_dir()} for k, p in b.skiller.kaynak_listesi
            ],
        }

    @r.post("/api/skill-ice")
    async def skill_ice_indir(istek: SkillIceIstegi) -> dict:
        return b.skill_ice.disari(await asyncio.to_thread(b.skill_ice.indir, istek.url))

    @r.post("/api/skill-ice/{iid}/denetle")
    async def skill_ice_denetle(iid: str, istek: SkillIceAdIstegi) -> dict:
        return await asyncio.to_thread(b.skill_ice.denetle, iid, istek.ad)

    @r.post("/api/skill-ice/{iid}/kur")
    async def skill_ice_kur(iid: str, istek: SkillIceKurIstegi) -> dict:
        return await asyncio.to_thread(
            b.skill_ice.kur, iid, istek.adlar, istek.riskli_onay, istek.yeni_adlar
        )

    @r.delete("/api/skill-ice/{iid}")
    async def skill_ice_iptal(iid: str) -> dict:
        return await asyncio.to_thread(b.skill_ice.iptal, iid)

    @r.get("/api/skiller/{ad}/revizyonlar")
    async def skill_revizyonlari(ad: str) -> dict:
        return {"simdiki": b.skiller.revizyon(ad), "revizyonlar": b.skiller.revizyonlar(ad)}

    @r.post("/api/skiller/{ad}/geri-al")
    async def skill_geri_al(ad: str, veri: dict) -> dict:
        s = b.skiller.geri_al(ad, int(veri.get("revizyon") or 0))
        return {"ad": s.ad, "simdiki": b.skiller.revizyon(s.ad)}

    @r.get("/api/skiller/{ad}")
    async def skill_getir(ad: str) -> dict:
        s = b.skiller.getir(ad)
        return {**s.ozet(), "icerik": s.dosya.read_text(encoding="utf-8", errors="replace")[:20000]}

    @r.post("/api/skiller")
    async def skill_ekle(istek: SkillIstegi) -> dict:
        return b.skiller.olustur(
            istek.ad, istek.aciklama, istek.icerik, istek.surum, istek.gereken_araclar
        ).ozet()

    @r.put("/api/skiller/{ad}")
    async def skill_guncelle(ad: str, istek: SkillIstegi) -> dict:
        return b.skiller.guncelle(
            ad, istek.aciklama, istek.icerik, istek.surum, istek.gereken_araclar
        ).ozet()

    @r.get("/api/skiller/{ad}/test")
    async def skill_test(ad: str) -> dict:
        a = b.ayarlar.oku()
        _, araclar_, _, _ = b.sohbet.baglam_hazirla(a, "", [])
        mevcut = {x["function"]["name"] for x in araclar_}
        isl = skl.arac_isleyicileri(b.skiller, set(a.kapali_skiller), lambda: mevcut)
        return {"skill": b.skiller.getir(ad).ozet(), "model_gorur": isl["skill_kullan"](ad)}

    @r.delete("/api/skiller/{ad}")
    async def skill_sil(ad: str) -> dict:
        b.skiller.sil(ad)
        return {"silindi": ad}

    @r.put("/api/skiller/{ad}/durum")
    async def skill_durum(ad: str, istek: SkillDurumIstegi) -> dict:
        b.skiller.getir(ad)
        kapali = set(b.ayarlar.oku().kapali_skiller)
        kapali = kapali - {ad} if istek.acik else kapali | {ad}
        b.ayarlar.guncelle({"kapali_skiller": sorted(kapali)})
        return {"ad": ad, "acik": istek.acik}

    return r
