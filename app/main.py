"""Masaustu baslatici: FastAPI'yi arka planda acar, arayuzu cercevesiz pywebview penceresinde
gosterir. --tarayici ile pencere yerine varsayilan tarayicida acar."""

from __future__ import annotations

import argparse
import contextlib
import socket
import sys
import threading
import time
import webbrowser

import uvicorn
from loguru import logger

from app import URUN_ADI, URUN_SAHIBI, URUN_SAHIBI_GITHUB, URUN_SAHIBI_X, __version__
from app.api import uygulama_olustur
from app.config import OrtamAyarlari, veri_dizini

YARDIM_SONU = f"Urun sahibi: {URUN_SAHIBI}  |  X: {URUN_SAHIBI_X}  |  GitHub: {URUN_SAHIBI_GITHUB}"


def bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PencereApi:
    """Arayuzdeki ozel baslik cubugu butonlari (window.pywebview.api.*)."""

    def __init__(self) -> None:
        # Alt cizgili: pywebview js_api'yi tararken pencere nesnesine (.NET) girmesin; yoksa
        # sonsuz ozyinelemeye girip GIL'i tutar ve arka uc sunucusu yanit veremez.
        self._pencere = None
        self._buyuk = False

    def kucult(self) -> None:
        self._pencere.minimize()

    def buyut(self) -> bool:
        if self._buyuk:
            self._pencere.restore()
        else:
            self._pencere.maximize()
        self._buyuk = not self._buyuk
        return self._buyuk

    def kapat(self) -> None:
        self._pencere.destroy()


def pencere_boyutu(ekranlar: list) -> tuple[int, int]:
    """Ekranin ~%90'i, en fazla 1440x920 (kucuk/olcekli ekranda pencere tasmasin)."""
    if not ekranlar:
        return 1280, 820
    e = ekranlar[0]
    return min(1440, int(e.width * 0.9)), min(920, int(e.height * 0.88))


def arg_ayristir(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="YerelAIStudio",
        description=f"{URUN_ADI}: yerel (llama.cpp) modelleri sohbet, OCR, arac ve "
        "karsilastirma testleriyle deneme uygulamasi.",
        epilog=YARDIM_SONU,
    )
    p.add_argument(
        "--version", action="version", version=f"{URUN_ADI} {__version__} - {YARDIM_SONU}"
    )
    p.add_argument("--tarayici", action="store_true", help="Pencere yerine tarayicida ac")
    p.add_argument(
        "--sunucu",
        action="store_true",
        help="Pencere acmadan yalniz yerel model sunucusunu calistir (Ollama gibi, arka planda)",
    )
    p.add_argument("--port", type=int, default=0, help="Yerel arayuz portu (0: bos port)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ham = sys.argv[1:] if argv is None else argv
    if ham[:1] == ["degerlendir"]:  # A13 gercek model degerlendirmesi
        from app import degerlendir

        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        return degerlendir.main(ham[1:])
    if ham[:1] == ["agent"]:  # A10.3 headless CLI: ayni ajan motoru
        from app import cli

        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        return cli.main(ham[1:])
    args = arg_ayristir(argv)
    ortam = OrtamAyarlari()
    dizin = veri_dizini(ortam)
    logger.remove()
    if sys.stderr:
        logger.add(sys.stderr, level=ortam.gunluk_seviyesi)
    logger.add(dizin / "uygulama.log", level="INFO", rotation="2 MB", retention=3, encoding="utf-8")

    port = args.port or ortam.port or bos_port()

    def kapat() -> None:  # --sunucu modunda /api/yerel/kapat ile
        sunucu.should_exit = True

    sunucu = uvicorn.Server(
        uvicorn.Config(
            uygulama_olustur(dizin, kapat=kapat if args.sunucu else None),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            log_config=None,
            ws="none",
        )
    )
    is_parcacigi = threading.Thread(target=sunucu.run, daemon=True)
    is_parcacigi.start()
    for _ in range(200):
        if sunucu.started:
            break
        time.sleep(0.05)
    adres = f"http://127.0.0.1:{port}/"
    logger.info("{} {} acildi: {} (veri: {})", URUN_ADI, __version__, adres, dizin)

    if args.sunucu:
        logger.info("Pencere yok; yalniz yerel sunucu calisiyor. Kapatmak: Sunucu-Durdur.bat")
        with contextlib.suppress(KeyboardInterrupt):
            is_parcacigi.join()
    elif args.tarayici:
        webbrowser.open(adres)
        with contextlib.suppress(KeyboardInterrupt):
            is_parcacigi.join()
    else:
        import webview

        api = PencereApi()
        genislik, yukseklik = pencere_boyutu(webview.screens)
        api._pencere = webview.create_window(
            URUN_ADI,
            adres,
            width=genislik,
            height=yukseklik,
            min_size=(960, 640),
            frameless=True,
            easy_drag=False,
            background_color="#1f1f1e",
            js_api=api,
        )
        webview.start(private_mode=False, storage_path=str(dizin / "webview"))
    sunucu.should_exit = True  # lifespan kapanisi: kendi baslattigimiz model sunucusunu durdurur
    is_parcacigi.join(timeout=15)
    return 0


if __name__ == "__main__":
    sys.exit(main())
