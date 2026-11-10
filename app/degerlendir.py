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


def gizli_kontrol(gorev: dict, proje: Path, korunan: dict[str, str]) -> dict:
    """Kosudan SONRA: korunan dosya kontrolu + gizli dosyalar + kontrol adimlari."""
    degisen = [y for y, h in korunan.items() if _hash(proje / y) != h]
    if degisen:
        return {"basari": False, "neden": f"korunan dosya degisti: {degisen}"}
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
            studio.islem(rid, "devam")
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
    return {
        "gorev": gorev["id"], "kategori": gorev["kategori"], "dil": gorev["dil"],
        "run_id": rid, "ajan_durumu": durum, "basari": kontrol["basari"],
        "ajan_hatasi": (son.get("hata") or "")[:300],
        "kontrol_nedeni": kontrol["neden"][:600],
        "yanlis_basari_beyani": durum == "basarili" and not kontrol["basari"],
        "mudahale": mudahale + (1 if durum == "karar_bekliyor" else 0),
        "arac_hatasi": sum(1 for a in adimlar if a.get("durum") in ("hata", "reddedildi")),
        "adim": (son.get("kullanim") or {}).get("adim", len(adimlar)),
        "token": (son.get("kullanim") or {}).get("token", 0),
        "sure_sn": sure, "ilk_adim_sn": ilk_adim,
    }  # fmt: skip


def ozet_tablo(kosular: list[dict]) -> dict:
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
        "kategori": {c: {"kosu": len(v), "basari_yuzde": oran(v)} for c, v in kategoriler.items()},
        "yanlis_basari_beyani": sum(k["yanlis_basari_beyani"] for k in kosular),
        "mudahale_toplam": sum(k["mudahale"] for k in kosular),
        "arac_hatasi_toplam": sum(k["arac_hatasi"] for k in kosular),
        "zaman_asimi": sum(k["ajan_durumu"] == "zaman_asimi" for k in kosular),
        "toplam_sure_sn": round(sum(k["sure_sn"] for k in kosular), 1),
        "toplam_token": sum(k["token"] or 0 for k in kosular),
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
             f"{o['zaman_asimi']}", "",
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
    args = p.parse_args(argv)

    surum, gorevler = gorevleri_yukle()
    if args.gorev:
        gorevler = [g for g in gorevler if g["id"] in args.gorev]
    if args.kategori:
        gorevler = [g for g in gorevler if g["kategori"] in args.kategori]
    calisma = Path(tempfile.mkdtemp(prefix="yas-deg-"))
    os.environ["YAS_VERI_DIZINI"] = str(calisma / "veri")
    from app.config import veri_dizini
    from app.services.ayarlar import AyarDeposu

    ayar = AyarDeposu(veri_dizini())
    gercek = AyarDeposu(KOK / "data").oku() if (KOK / "data" / "ayarlar.json").exists() else None
    degisiklik: dict[str, Any] = {"sunucu_acik": False}
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
    sil(calisma / "projeler") if (calisma / "projeler").exists() else None
    return 0
