"""A13 gercek model degerlendirmesi.

Kullanim: `python -m app degerlendir [--openrouter-model M] [--tekrar 3]`.

Her gorev x tekrar icin TEMIZ fixture kurulur, ajan ayni motorla (SDK/API) calistirilir, sonra
modelin gormedigi gizli kontroller kopyalanip calistirilir. Korunan (gorunur test) dosyalari
degistirilmisse kosu BASARISIZ sayilir (test silerek/degistirerek basari engellenir).

Kullanici mudahalesi: degerlendirmede onay isteyen adimlar (yalniz gecici fixture klasorunde)
harness tarafindan onaylanir ve SAYILIR; karar isteyen adimda kosu durur. Basarisiz ve zaman
asimina ugrayan kosular dahil HER kosu rapora yazilir. Surumler (model, saglayici, kuantizasyon,
baglam, donanim, uygulama, gorev seti, sistem istemi hash'i) kaydedilir.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parent.parent
GOREV_DOSYASI = KOK / "degerlendirme" / "gorevler.py"
KOSU_SURESI = 15 * 60


def gorevleri_yukle(yol: Path = GOREV_DOSYASI) -> tuple[str, list[dict]]:
    spec = importlib.util.spec_from_file_location("yas_gorevler", yol)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.SURUM, mod.G


def _yaz(kok: Path, dosyalar: dict[str, str]) -> None:
    for yol, icerik in dosyalar.items():
        p = kok / yol
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(icerik.encode("utf-8"))  # satir sonlari aynen (CRLF gorevi icin)


def kur(gorev: dict, hedef: Path) -> dict[str, str]:
    """Temiz fixture + git deposu; korunan dosyalarin hash'lerini dondurur."""
    if hedef.exists():
        sil(hedef)
    hedef.mkdir(parents=True)
    _yaz(hedef, gorev["dosyalar"])
    git = shutil.which("git")
    if git:
        ortam = {**os.environ, "GIT_AUTHOR_NAME": "deg", "GIT_AUTHOR_EMAIL": "deg@yerel",
                 "GIT_COMMITTER_NAME": "deg", "GIT_COMMITTER_EMAIL": "deg@yerel"}  # fmt: skip
        for argv in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "baslangic"]):
            subprocess.run([git, *argv], cwd=hedef, env=ortam, capture_output=True, check=False)
    return {y: _hash(hedef / y) for y in gorev["korunan"]}


def sil(p: Path) -> None:
    """git nesneleri salt okunur: Windows'ta once yazilabilir yapilir."""
    import stat

    def _yazilabilir(fonk, yol, _hata):
        os.chmod(yol, stat.S_IWRITE)
        fonk(yol)

    shutil.rmtree(p, onexc=_yazilabilir)


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "YOK"


def _argv(a: list[str]) -> list[str]:
    yerine = {"{py}": sys.executable, "{node}": shutil.which("node") or "node",
              "{dotnet}": shutil.which("dotnet") or "dotnet"}  # fmt: skip
    return [yerine.get(x, x) for x in a]


def test_dosyasi_mi(yol: str) -> bool:
    ad = Path(yol).name.lower()
    return ad.startswith("test_") or ".test." in ad or ad.endswith("_test.py")


def gizli_kontrol(gorev: dict, proje: Path, korunan: dict[str, str]) -> dict:
    """Kosudan SONRA. Korunan TEST dosyalari orijinaline geri yuklenir (zayiflatilmis test ise
    yaramaz; modelin EKLEDIGI testler cezalandirilmaz). Korunan diger dosyalar (or. kesif
    gorevinde kaynak kod) degismisse kosu basarisiz."""
    degisen = [y for y, h in korunan.items() if not test_dosyasi_mi(y) and _hash(proje / y) != h]
    if degisen:
        return {"basari": False, "neden": f"korunan dosya degisti: {degisen}"}
    _yaz(proje, {y: gorev["dosyalar"][y] for y in korunan if test_dosyasi_mi(y)})
    _yaz(proje, gorev.get("gizli", {}))
    for i, k in enumerate(gorev["kontroller"]):
        if k.get("once_yaz"):
            _yaz(proje, k["once_yaz"])
        try:
            r = subprocess.run(_argv(k["argv"]), cwd=proje, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=300,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                                    "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                                    "DOTNET_NOLOGO": "1"})  # fmt: skip
        except subprocess.TimeoutExpired:
            return {"basari": False, "neden": f"kontrol {i} zaman asimi"}
        beklenen_sifir = k.get("beklenen", "sifir") == "sifir"
        if (r.returncode == 0) != beklenen_sifir:
            cikti = (r.stdout + r.stderr)[-600:]
            return {"basari": False, "neden": f"kontrol {i} (kod {r.returncode}): {cikti}"}
    return {"basari": True, "neden": ""}


def ortam_bilgisi() -> dict:
    bilgi = {"os": platform.platform(), "python": platform.python_version(),
             "cpu": platform.processor(), "cekirdek": os.cpu_count()}  # fmt: skip
    try:
        import psutil

        bilgi["ram_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "(Get-CimInstance Win32_Processor).Name;"
                                "(Get-CimInstance Win32_VideoController).Name"],
                               capture_output=True, text=True, timeout=20)  # fmt: skip
            satirlar = [s.strip() for s in r.stdout.splitlines() if s.strip()]
            if satirlar:
                bilgi["cpu"], bilgi["gpu"] = satirlar[0], ", ".join(satirlar[1:])
        except (OSError, subprocess.TimeoutExpired):
            pass
    return bilgi


def kos(studio: Any, gorev: dict, proje: Path, sure_siniri: int = KOSU_SURESI) -> dict:
    """Tek kosu: ajan calisir; onaylar sayilarak onaylanir; zaman siniri asilirsa iptal."""
    korunan = kur(gorev, proje)
    studio.proje_ac(str(proje), guven="guvenilir", mod="otomatik")
    bas = time.monotonic()
    run = studio.gorev(gorev["hedef"], kabul=gorev["kabul"], max_adim=gorev["max_adim"])
    rid, mudahale, ilk_adim, son = run["id"], 0, None, run
    onaylanan: list[str] = []  # onay kirilimi: hangi arac/komut kullaniciyi durdurdu
    durum = "zaman_asimi"
    while time.monotonic() - bas < sure_siniri:
        son = studio.durum(rid)
        if ilk_adim is None and son.get("adimlar"):
            ilk_adim = round(time.monotonic() - bas, 1)
        d = son["durum"]
        if d == "onay_bekliyor":
            for a in son["adimlar"]:
                if a["durum"] == "onay_bekliyor" and a.get("onay_id"):
                    studio.onay(a["onay_id"], True)
                    mudahale += 1
                    arg = a.get("argumanlar") or {}
                    onaylanan.append(f"{a.get('arac')}: {str(arg.get('komut') or '')[:60]}")
            # onay ucu bekleyen gorevi kendisi surdurur; ayrica 'devam' yarisa yol acar
        elif d in (
            "karar_bekliyor",
            "duraklatildi",
            "basarili",
            "dogrulanmadi",
            "basarisiz",
            "iptal",
        ):
            durum = d
            break
        time.sleep(1.0)
    if durum == "zaman_asimi":
        with contextlib.suppress(Exception):
            son = studio.islem(rid, "iptal")
    sure = round(time.monotonic() - bas, 1)
    kontrol = gizli_kontrol(gorev, proje, korunan)
    adimlar = son.get("adimlar") or []
    hata = son.get("hata") or ""
    if durum == "basarisiz" and ("istek siniri" in hata or "429" in hata):
        durum = "saglayici_limiti"  # model yetenegi degil: olculemedi, ayri raporlanir
    return {
        "gorev": gorev["id"], "kategori": gorev["kategori"], "dil": gorev["dil"],
        "run_id": rid, "ajan_durumu": durum, "basari": kontrol["basari"],
        "ajan_hatasi": (son.get("hata") or "")[:300],
        "kontrol_nedeni": kontrol["neden"][:600],
        "yanlis_basari_beyani": durum == "basarili" and not kontrol["basari"],
        "mudahale": mudahale + (1 if durum == "karar_bekliyor" else 0),
        "onaylanan": onaylanan,
        "arac_hatasi": sum(1 for a in adimlar if a.get("durum") in ("hata", "reddedildi")),
        "adim": (son.get("kullanim") or {}).get("adim", len(adimlar)),
        "token": (son.get("kullanim") or {}).get("token", 0),
        "maliyet_usd": (son.get("kullanim") or {}).get("maliyet_usd", 0),
        "sure_sn": sure, "ilk_adim_sn": ilk_adim,
    }  # fmt: skip


CC_ORTAM_SIL = ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID",
                "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_ENTRYPOINT")  # fmt: skip


def claude_exe() -> str:
    """npm'in claude.cmd sarmalayicisi subprocess'te tirnaklamayi bozuyor: exe dogrudan."""
    npm = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@anthropic-ai"
    exe = npm / "claude-code" / "bin" / "claude.exe"
    return str(exe) if exe.exists() else (shutil.which("claude") or "claude")


def kos_claude_code(gorev: dict, proje: Path, sure_siniri: int, butce_usd: float,
                    model: str = "") -> dict:  # fmt: skip
    """Referans olcum: ayni gorev/fixture/gizli kontrol, Claude Code headless (`claude -p`).

    Esit kosullar: ayni hedef+kabul metni, ayni adim siniri (--max-turns), ayni sure siniri,
    ayni arac turleri (dosya oku/yaz/duzenle/ara + komut) on-izinli (bizim ajanda da onaylar
    harness tarafindan veriliyor). Kullanici CLAUDE.md'si/MCP'si yuklenmez (proje ayarlari).
    """
    korunan = kur(gorev, proje)
    exe = claude_exe()
    kabul = "; ".join(gorev["kabul"])
    istem = gorev["hedef"] + (f"\nKabul: {kabul}" if kabul else "")
    argv = [exe, "-p", istem, "--output-format", "json", "--max-turns", str(gorev["max_adim"]),
            "--permission-mode", "acceptEdits", "--allowedTools",
            "Bash Read Edit Write Glob Grep", "--setting-sources", "project",
            "--strict-mcp-config", "--no-session-persistence",
            "--max-budget-usd", str(butce_usd)]  # fmt: skip
    if model:
        argv += ["--model", model]
    ortam = {k: v for k, v in os.environ.items() if k not in CC_ORTAM_SIL}
    bas = time.monotonic()
    veri: dict = {}
    durum = "basarisiz"
    try:
        r = subprocess.run(argv, cwd=proje, env=ortam, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=sure_siniri,
                           stdin=subprocess.DEVNULL)  # fmt: skip
        try:
            veri = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        except ValueError:
            veri = {}
        if veri.get("subtype") == "success" and not veri.get("is_error"):
            durum = "basarili"
        elif veri.get("subtype"):
            durum = str(veri["subtype"])  # error_max_turns, error_max_budget_usd ...
    except subprocess.TimeoutExpired:
        durum = "zaman_asimi"
    sure = round(time.monotonic() - bas, 1)
    kontrol = gizli_kontrol(gorev, proje, korunan)
    u = veri.get("usage") or {}
    return {
        "gorev": gorev["id"], "kategori": gorev["kategori"], "dil": gorev["dil"],
        "run_id": veri.get("session_id", ""), "ajan_durumu": durum, "basari": kontrol["basari"],
        "ajan_hatasi": "" if durum == "basarili" else str(veri.get("result", ""))[:300],
        "kontrol_nedeni": kontrol["neden"][:600],
        "yanlis_basari_beyani": durum == "basarili" and not kontrol["basari"],
        "mudahale": 0, "arac_hatasi": 0, "adim": veri.get("num_turns", 0),
        "token": sum(u.get(k, 0) or 0 for k in ("input_tokens", "output_tokens",
                                                "cache_read_input_tokens",
                                                "cache_creation_input_tokens")),
        "maliyet_usd": veri.get("total_cost_usd", 0),
        "model": ",".join(veri.get("modelUsage") or {}),
        "sure_sn": sure, "ilk_adim_sn": None,
    }  # fmt: skip


OLCULEMEDI = {"saglayici_limiti", "harness_hatasi"}


def ozet_tablo(kosular: list[dict]) -> dict:
    """Basari orani yalniz OLCULEBILEN kosularda; kota/harness hatalari ayri sayilir."""
    olculemeyen = [k for k in kosular if k["ajan_durumu"] in OLCULEMEDI]
    kosular = [k for k in kosular if k["ajan_durumu"] not in OLCULEMEDI]

    def oran(liste: list[dict]) -> float:
        return round(100 * sum(k["basari"] for k in liste) / len(liste), 1) if liste else 0.0

    kategoriler: dict[str, list[dict]] = {}
    for k in kosular:
        kategoriler.setdefault(k["kategori"], []).append(k)
    gorevler: dict[str, list[bool]] = {}
    for k in kosular:
        gorevler.setdefault(k["gorev"], []).append(k["basari"])
    return {
        "kosu": len(kosular), "basari_yuzde": oran(kosular),
        "olculemedi": len(olculemeyen),
        "olculemeyen_gorevler": sorted({k["gorev"] for k in olculemeyen}),
        "kategori": {c: {"kosu": len(v), "basari_yuzde": oran(v)} for c, v in kategoriler.items()},
        "yanlis_basari_beyani": sum(k["yanlis_basari_beyani"] for k in kosular),
        "mudahale_toplam": sum(k["mudahale"] for k in kosular),
        "arac_hatasi_toplam": sum(k["arac_hatasi"] for k in kosular),
        "zaman_asimi": sum(k["ajan_durumu"] == "zaman_asimi" for k in kosular),
        "toplam_sure_sn": round(sum(k["sure_sn"] for k in kosular), 1),
        "toplam_token": sum(k["token"] or 0 for k in kosular),
        "toplam_maliyet_usd": round(sum(k.get("maliyet_usd") or 0 for k in kosular), 4),
        "kararsiz_gorevler": [g for g, s in gorevler.items() if 0 < sum(s) < len(s)],
    }  # fmt: skip


def markdown(rapor: dict) -> str:
    o, s = rapor["ozet"], rapor["surumler"]
    satir = [f"# Degerlendirme raporu ({rapor['zaman']})", "",
             f"- Model: `{s['model']}` ({s['saglayici']}), gorev seti {s['gorev_seti']}",
             f"- Donanim: {s['ortam'].get('cpu')} / {s['ortam'].get('ram_gb')} GB / "
             f"{s['ortam'].get('gpu', '-')}",
             f"- Kosu: {o['kosu']}, basari %{o['basari_yuzde']}, yanlis basari beyani "
             f"{o['yanlis_basari_beyani']}, mudahale {o['mudahale_toplam']}, zaman asimi "
             f"{o['zaman_asimi']}, olculemedi (kota/harness) {o['olculemedi']}", "",
             "| Kategori | Kosu | Basari % |", "|---|---|---|"]  # fmt: skip
    satir += [f"| {c} | {v['kosu']} | {v['basari_yuzde']} |" for c, v in o["kategori"].items()]
    satir += ["", "| Gorev | Ajan | Gizli | Sure sn | Adim | Mudahale | Neden |",
              "|---|---|---|---|---|---|---|"]  # fmt: skip
    for k in rapor["kosular"]:
        neden = k["kontrol_nedeni"].replace("|", "/").replace("\n", " ")[:120]
        satir.append(f"| {k['gorev']} | {k['ajan_durumu']} | {'GECTI' if k['basari'] else 'KALDI'}"
                     f" | {k['sure_sn']} | {k['adim']} | {k['mudahale']} | {neden} |")  # fmt: skip
    satir += ["", "Not: Kucuk orneklem; kosular arasi fark (kararsiz gorevler: "
              f"{', '.join(o['kararsiz_gorevler']) or 'yok'}) belirsizligi gosterir. Bu sonuc "
              "Claude Code ile esitlik anlamina gelmez; ayni gorevlerle referans olcum yoksa "
              "kalite esitligi DOGRULANMADI."]  # fmt: skip
    return "\n".join(satir) + "\n"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m app degerlendir")
    p.add_argument("--openrouter-model", help="OpenRouter modeli (YAS_OPENROUTER_ANAHTARI)")
    p.add_argument("--yerel-model", default="", help="Yerel model kimligi (varsayilan: ayar)")
    p.add_argument("--tekrar", type=int, default=3)
    p.add_argument("--gorev", action="append", default=[], help="Yalniz bu gorev kimlik(ler)i")
    p.add_argument("--kategori", action="append", default=[])
    p.add_argument("--rapor", default=str(KOK / "degerlendirme" / "raporlar"))
    p.add_argument("--sure", type=int, default=KOSU_SURESI, help="Kosu basina saniye siniri")
    p.add_argument("--sakla", action="store_true", help="Kosu klasorlerini silme (inceleme)")
    p.add_argument("--ajan", choices=["kairo", "claude-code"], default="kairo")
    p.add_argument(
        "--izolasyon",
        choices=["yok", "kum"],
        default="yok",
        help="Kairo komutlari nerede calisir (kum: AppContainer, ag kapali)",
    )
    p.add_argument("--cc-butce-usd", type=float, default=3.0, help="Claude Code kosu basi tavan")
    p.add_argument("--cc-model", default="", help="Claude Code modeli (bos: varsayilan)")
    args = p.parse_args(argv)

    surum, gorevler = gorevleri_yukle()
    if args.gorev or args.kategori:  # birlesim: verilen gorevler + verilen kategoriler
        gorevler = [g for g in gorevler
                    if g["id"] in args.gorev or g["kategori"] in args.kategori]  # fmt: skip
    calisma = Path(tempfile.mkdtemp(prefix="yas-deg-"))
    if args.ajan == "claude-code":
        return _claude_code_degerlendir(args, surum, gorevler, calisma)
    os.environ["YAS_VERI_DIZINI"] = str(calisma / "veri")
    from app.config import veri_dizini
    from app.services.ayarlar import AyarDeposu

    ayar = AyarDeposu(veri_dizini())
    if (KOK / "data" / "openrouter.json").exists():  # kayitli (DPAPI sifreli) anahtar
        shutil.copy2(KOK / "data" / "openrouter.json", veri_dizini() / "openrouter.json")
    gercek = AyarDeposu(KOK / "data").oku() if (KOK / "data" / "ayarlar.json").exists() else None
    degisiklik: dict[str, Any] = {"sunucu_acik": False, "izolasyon": args.izolasyon}
    if gercek is not None:  # yerel model klasoru/adresi kullanicinin ayarindan
        degisiklik |= {"llm_dizin": gercek.llm_dizin, "adres": gercek.adres,
                       "otomatik_baslat": True}  # fmt: skip
    if args.openrouter_model:
        degisiklik |= {"saglayici": "openrouter", "or_model": args.openrouter_model}
    elif args.yerel_model:
        degisiklik |= {"model": args.yerel_model}
    a = ayar.guncelle(degisiklik)

    from app import cli
    from app.sdk import Studio

    sunucu, adres, anahtar = cli._sunucu_baslat()
    kosular: list[dict] = []
    rapor_dizin = Path(args.rapor)
    rapor_dizin.mkdir(parents=True, exist_ok=True)
    damga = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jsonl = rapor_dizin / f"kosular-{damga}.jsonl"
    try:
        with Studio(adres, anahtar, zaman=120) as s:
            bilgi = s.bilgi()
            if args.openrouter_model:  # bos onbellekte model 'aracsiz' sayilmasin
                s.openrouter_listesi_yenile()
            for g in gorevler:
                for t in range(args.tekrar):
                    proje = calisma / "projeler" / f"{g['id']}-{t + 1}"
                    try:
                        k = kos(s, g, proje, args.sure)
                    except Exception as e:  # noqa: BLE001 - kosu hatasi da rapora girer
                        k = {"gorev": g["id"], "kategori": g["kategori"], "dil": g["dil"],
                             "run_id": "", "ajan_durumu": "harness_hatasi", "basari": False,
                             "kontrol_nedeni": str(e)[:600], "yanlis_basari_beyani": False,
                             "mudahale": 0, "arac_hatasi": 0, "adim": 0, "token": 0,
                             "sure_sn": 0, "ilk_adim_sn": None}  # fmt: skip
                    k["tekrar"] = t + 1
                    kosular.append(k)
                    with jsonl.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(k, ensure_ascii=False) + "\n")
                    print(f"[{len(kosular)}] {g['id']} #{t + 1}: "
                          f"{'GECTI' if k['basari'] else 'KALDI'} ({k['ajan_durumu']}, "
                          f"{k['sure_sn']} sn)", flush=True)  # fmt: skip
    finally:
        sunucu.should_exit = True
    from app.agent import runner as runner_mod

    sistem_hash = hashlib.sha256(Path(runner_mod.__file__).read_bytes()).hexdigest()[:12]
    rapor = {
        "zaman": damga,
        "surumler": {
            "uygulama": bilgi.get("surum") or bilgi.get("version"), "gorev_seti": surum,
            "saglayici": a.saglayici, "model": a.aktif_model,
            "kuantizasyon": a.aktif_model if a.saglayici == "yerel" else "saglayici tarafinda",
            "baglam": getattr(a, "baglam", None), "runner_hash": sistem_hash,
            "ortam": ortam_bilgisi(),
        },
        "ozet": ozet_tablo(kosular),
        "kosular": kosular,
    }  # fmt: skip
    (rapor_dizin / f"rapor-{damga}.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (rapor_dizin / f"rapor-{damga}.md").write_text(markdown(rapor), encoding="utf-8")
    print(json.dumps(rapor["ozet"], ensure_ascii=False, indent=1))
    if args.sakla:
        print(f"Kosu klasoru: {calisma}")
    elif (calisma / "projeler").exists():
        sil(calisma / "projeler")
    return 0


def _claude_code_degerlendir(args: Any, surum: str, gorevler: list[dict], calisma: Path) -> int:
    rapor_dizin = Path(args.rapor)
    rapor_dizin.mkdir(parents=True, exist_ok=True)
    damga = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jsonl = rapor_dizin / f"kosular-claude-code-{damga}.jsonl"
    kosular: list[dict] = []
    for g in gorevler:
        for t in range(args.tekrar):
            proje = calisma / "projeler" / f"{g['id']}-{t + 1}"
            k = kos_claude_code(g, proje, args.sure, args.cc_butce_usd, args.cc_model)
            k["tekrar"] = t + 1
            kosular.append(k)
            with jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")
            print(
                f"[{len(kosular)}] {g['id']} #{t + 1}: {'GECTI' if k['basari'] else 'KALDI'} "
                f"({k['ajan_durumu']}, {k['sure_sn']} sn, ${k['maliyet_usd']})",
                flush=True,
            )
    surum_cc = subprocess.run([claude_exe(), "--version"],
                              capture_output=True, text=True).stdout.strip()  # fmt: skip
    rapor = {
        "zaman": damga,
        "surumler": {"uygulama": surum_cc, "gorev_seti": surum, "saglayici": "anthropic",
                     "model": ",".join(sorted({k["model"] for k in kosular if k["model"]})),
                     "kuantizasyon": "saglayici tarafinda", "ortam": ortam_bilgisi()},
        "ozet": ozet_tablo(kosular),
        "kosular": kosular,
    }  # fmt: skip
    (rapor_dizin / f"rapor-claude-code-{damga}.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (rapor_dizin / f"rapor-claude-code-{damga}.md").write_text(markdown(rapor), encoding="utf-8")
    print(json.dumps(rapor["ozet"], ensure_ascii=False, indent=1))
    if (calisma / "projeler").exists():
        sil(calisma / "projeler")
    return 0
    return 0
