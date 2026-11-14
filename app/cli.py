"""Headless CLI (A10.3): python -m app agent "<hedef>" --proje <klasor> [secenekler]

Ayni ajan motoru: uygulama yalniz 127.0.0.1'de gecici bir portta acilir, SDK ile konusulur.
Onay gerektiren adimda SONSUZA KADAR BEKLEMEZ: durumu yazar ve cikis kodu 3 ile cikar;
onay verip kaldigi yerden: --onayla <onay_id> --devam <run_id>.

Cikis kodlari: 0 basarili | 1 basarisiz/iptal | 2 dogrulanmadi | 3 onay/karar bekliyor | 4 hata
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time

from app.sdk import BITMIS, Studio, StudioHatasi

CIKIS = {"basarili": 0, "basarisiz": 1, "iptal": 1, "dogrulanmadi": 2, "duraklatildi": 3,
         "onay_bekliyor": 3, "karar_bekliyor": 3, "cevap_bekliyor": 3}  # fmt: skip


def arg_ayristir(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="Kairo agent", description=__doc__.split("\n")[0])
    p.add_argument("hedef", nargs="?", default="", help="Gorev hedefi")
    p.add_argument("--proje", help="Proje klasoru")
    p.add_argument("--guven", default="sinirli", choices=["guvenilmeyen", "sinirli", "guvenilir"])
    p.add_argument("--mod", default="onayli", choices=["sohbet", "planla", "onayli", "otomatik"])
    p.add_argument("--kabul", action="append", default=[], help="Kabul kosulu (tekrarlanabilir)")
    p.add_argument("--max-adim", type=int)
    p.add_argument("--izole", action="store_true", help="Ayri git dalinda (worktree) calis")
    p.add_argument("--devam", metavar="RUN_ID", help="Duran gorevi surdur")
    p.add_argument("--onayla", metavar="ONAY_ID", action="append", default=[])
    p.add_argument("--reddet", metavar="ONAY_ID", action="append", default=[])
    p.add_argument("--json", action="store_true", help="Satir basina JSON olay")
    p.add_argument(
        "--openrouter-model",
        metavar="MODEL",
        help="OpenRouter modeli (anahtar: YAS_OPENROUTER_ANAHTARI ortam degiskeni)",
    )
    return p.parse_args(argv)


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _sunucu_baslat():
    import uvicorn

    from app.api import uygulama_olustur
    from app.config import veri_dizini

    app = uygulama_olustur(veri_dizini(), gecit=False)  # CLI'de Ollama uyumlu sunucu acilmaz
    port = _bos_port()
    sunucu = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=sunucu.run, daemon=True).start()
    for _ in range(100):
        if sunucu.started:
            break
        time.sleep(0.05)
    return sunucu, f"http://127.0.0.1:{port}", app.state.oturum_anahtari


def _yaz(args: argparse.Namespace, r: dict) -> None:
    if args.json:
        print(json.dumps({"tur": "run", "run": r}, ensure_ascii=False), flush=True)
        return
    son = r["adimlar"][-1] if r["adimlar"] else None
    print(f"[{r['durum']}] adim {r['kullanim']['adim']}"
          + (f" | son: {son['arac']} {son['durum']}" if son else ""), flush=True)  # fmt: skip


def calistir(args: argparse.Namespace, s: Studio) -> int:
    for oid in args.onayla:
        s.onay(oid, True)
    for oid in args.reddet:
        s.onay(oid, False)
    if args.devam:
        run_id = args.devam
        if s.durum(run_id)["durum"] not in BITMIS:
            s.islem(run_id, "devam")
    else:
        if not args.hedef or not args.proje:
            print("Hata: hedef ve --proje gerekli (ya da --devam RUN_ID).", file=sys.stderr)
            return 4
        s.proje_ac(args.proje, guven=args.guven, mod=args.mod)
        run_id = s.gorev(args.hedef, args.kabul, args.max_adim, args.izole)["id"]
    son: dict = {}
    for r in s.izle(run_id, aralik=0.5):
        son = r
        _yaz(args, r)
    bekleyen = [{"adim": a["no"], "arac": a["arac"], "onay_id": a["onay_id"]}
                for a in son["adimlar"] if a["durum"] == "onay_bekliyor"]  # fmt: skip
    ozet = {"tur": "sonuc", "run_id": run_id, "durum": son["durum"], "ozet": son["sonuc"]["ozet"],
            "kanit": son["sonuc"]["kanit"], "hata": son["hata"],
            "bekleyen_onaylar": bekleyen}  # fmt: skip
    if args.json:
        print(json.dumps(ozet, ensure_ascii=False), flush=True)
    else:
        print(f"Sonuc: {son['durum']} - {son['sonuc']['ozet'] or son['hata']}")
        for b in bekleyen:
            print(f"Onay bekliyor: adim {b['adim']} {b['arac']}  ->  --onayla {b['onay_id']} "
                  f"--devam {run_id}")  # fmt: skip
    return CIKIS.get(son["durum"], 4)


def main(argv: list[str]) -> int:
    # Windows konsolu cp1254: --json ciktisindaki '✓' gibi karakterde print cokuyordu (canli)
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    args = arg_ayristir(argv)
    if args.openrouter_model:  # CI: gecici veri klasorunde saglayici secimi
        from app.config import veri_dizini
        from app.services.ayarlar import AyarDeposu

        AyarDeposu(veri_dizini()).guncelle(
            {"saglayici": "openrouter", "or_model": args.openrouter_model}
        )
    sunucu, adres, anahtar = _sunucu_baslat()
    try:
        with Studio(adres, anahtar) as s:
            if args.openrouter_model:  # bos onbellekte model 'aracsiz' sayilmasin
                s.openrouter_listesi_yenile()
            return calistir(args, s)
    except StudioHatasi as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 4
    finally:
        sunucu.should_exit = True
