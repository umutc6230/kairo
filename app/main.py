"""Masaustu baslatici: FastAPI'yi arka planda acar, arayuzu cercevesiz pywebview penceresinde
gosterir. --tarayici ile pencere yerine varsayilan tarayicida acar."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from loguru import logger

from app import URUN_ADI, URUN_SAHIBI, URUN_SAHIBI_GITHUB, URUN_SAHIBI_X, __version__
from app.api import uygulama_olustur
from app.config import OrtamAyarlari, veri_dizini
from app.services.ayarlar import AyarDeposu
from app.services.depo import json_yaz

YARDIM_SONU = f"Urun sahibi: {URUN_SAHIBI}  |  X: {URUN_SAHIBI_X}  |  GitHub: {URUN_SAHIBI_GITHUB}"


def bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _baglanti_yaz(dizin: Path, port: int, anahtar: str) -> Path:
    """VS Code / yerel araclarin calisan Kairo portunu ve oturum anahtarini bulmasi icin."""
    yol = dizin / "baglanti.json"
    json_yaz(
        yol,
        {
            "url": f"http://127.0.0.1:{port}",
            "port": port,
            "pid": os.getpid(),
            "oturum_anahtari": anahtar,
        },
    )
    return yol


def _baglanti_sil(yol: Path) -> None:
    with contextlib.suppress(OSError):
        yol.unlink(missing_ok=True)


class PencereApi:
    """Arayuzdeki ozel baslik cubugu butonlari (window.pywebview.api.*)."""

    def __init__(self) -> None:
        # Alt cizgili: pywebview js_api'yi tararken pencere nesnesine (.NET) girmesin; yoksa
        # sonsuz ozyinelemeye girip GIL'i tutar ve arka uc sunucusu yanit veremez.
        self._pencere = None
        self._buyuk = False
        self._tepside = False  # True: kapat dugmesi pencereyi gizler, uygulama tepside surer

    def kucult(self) -> None:
        self._pencere.minimize()

    def buyut(self) -> bool:
        if not self._calisma_alanina_sigdir():
            # yedek: native maximize (cercevesiz pencerede gorev cubugunu da kaplar)
            if self._buyuk:
                self._pencere.restore()
            else:
                self._pencere.maximize()
        self._buyuk = not self._buyuk
        return self._buyuk

    def _calisma_alanina_sigdir(self) -> bool:
        """Cercevesiz pencereyi bulundugu ekranin calisma alanina (gorev cubugu haric) oturtur;
        ikinci cagrida eski boyutuna doner."""
        try:
            from System import Action
            from System.Drawing import Rectangle
            from System.Windows.Forms import Screen

            form = self._pencere.native

            def uygula() -> None:
                alan = Screen.FromControl(form).WorkingArea
                # durum bayraktan degil gercek sinirdan: pencere zaten alani kapliyorsa geri al
                if form.Bounds.Equals(alan):
                    eski = getattr(self, "_eski_sinir", None)
                    if eski is None or eski.Equals(alan):
                        g, y = int(alan.Width * 0.75), int(alan.Height * 0.8)
                        eski = Rectangle(
                            alan.X + (alan.Width - g) // 2, alan.Y + (alan.Height - y) // 2, g, y
                        )
                    form.Bounds = eski
                    self._buyuk = True  # buyut() tersine cevirir -> False
                else:
                    self._eski_sinir = form.Bounds
                    form.Bounds = alan
                    self._buyuk = False

            form.Invoke(Action(uygula))
            return True
        except Exception as e:  # noqa: BLE001 - WinForms yoksa native maximize
            logger.debug("Calisma alanina sigdirilamadi: {}", e)
            return False

    def tarayici_ac(self, adres: str) -> bool:
        """Dis siteyi AYRI pencerede acar: cogu site iframe icinde gosterilmeyi yasaklar
        (X-Frame-Options). Yeni pencereye js_api VERILMEZ; site Kairo'ya erisemez."""
        from urllib.parse import urlsplit

        import webview

        u = urlsplit(str(adres).strip())
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        webview.create_window(f"Kairo - {u.hostname}", u.geturl(), width=1200, height=820)
        return True

    def klasor_sec(self) -> str:
        """Windows klasor secme penceresi; iptalde bos metin."""
        import webview

        tur = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        sonuc = self._pencere.create_file_dialog(tur if tur is not None else webview.FOLDER_DIALOG)
        return sonuc[0] if sonuc else ""

    def dosya_kaydet(self, ad: str, icerik: str) -> str:
        """Windows 'Farkli kaydet' penceresi; secilen yola UTF-8 yazar. Iptalde bos metin."""
        import webview

        tur = getattr(getattr(webview, "FileDialog", None), "SAVE", None)
        sonuc = self._pencere.create_file_dialog(
            tur if tur is not None else webview.SAVE_DIALOG,
            save_filename=Path(str(ad)).name or "sohbet.md",
            file_types=("Markdown (*.md)", "Tum dosyalar (*.*)"),
        )
        if not sonuc:
            return ""
        yol = Path(sonuc if isinstance(sonuc, str) else sonuc[0])
        yol.write_text(str(icerik), encoding="utf-8")
        return str(yol)

    def kapat(self) -> None:
        if self._tepside:
            self._pencere.hide()
        else:
            self._pencere.destroy()


IKON = Path(__file__).resolve().parent / "web" / "kairo.ico"


def gorev_cubugu_kimligi() -> None:
    """python.exe ile acilinca gorev cubugunda Python ikonu/grubu yerine Kairo kullanilsin."""
    if sys.platform == "win32":
        with contextlib.suppress(OSError, AttributeError):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("UmutCelik.Kairo")


def pencere_ikonu(pencere) -> None:
    """WinForms penceresine Kairo ikonunu verir (pywebview 'icon' Windows'ta desteklemiyor)."""
    if sys.platform != "win32" or not IKON.is_file():
        return
    try:
        from System import Action  # pythonnet, pywebview winforms ile gelir
        from System.Drawing import Icon

        form = pencere.native
        ikon = Icon(str(IKON))
        form.Invoke(Action(lambda: setattr(form, "Icon", ikon)))  # form UI is parcaciginda
    except Exception as e:  # noqa: BLE001 - ikon yoksa uygulama yine acilir
        logger.debug("Pencere ikonu ayarlanamadi: {}", e)


def pencere_boyutu(ekranlar: list) -> tuple[int, int]:
    """Ekranin ~%90'i, en fazla 1440x920 (kucuk/olcekli ekranda pencere tasmasin)."""
    if not ekranlar:
        return 1280, 820
    e = ekranlar[0]
    return min(1440, int(e.width * 0.9)), min(920, int(e.height * 0.88))


def arg_ayristir(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="Kairo",
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
    if ham[:1] == ["--kum"]:  # AppContainer yardimcisi (izolasyon "kum")
        from app.agent import kum

        return kum.main(ham[1:])
    if ham[:1] == ["--cc-izin"]:  # Claude Code PreToolUse hook'u -> Kairo izin motoru
        from app.agent import cc_izin

        return cc_izin.main()
    if ham[:1] == ["--kum-arac-kur"]:  # bir kerelik, yonetici: arac klasorlerine RX
        from app.agent import kum

        return kum.arac_kur()
    if ham[:1] == ["--kum-kur"]:  # bir kerelik, yonetici: surucu kokune listele izni
        from app.agent import kum

        return kum.kok_kur(ham[1] if len(ham) > 1 else ".")
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

    fastapi_app = uygulama_olustur(dizin, kapat=kapat if args.sunucu else None)
    fastapi_app.state.izin_adresi = f"http://127.0.0.1:{port}/api/cc-izin"  # Claude Code hook'u
    sunucu = uvicorn.Server(
        uvicorn.Config(
            fastapi_app,
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
    baglanti_yolu = _baglanti_yaz(dizin, port, fastapi_app.state.oturum_anahtari)
    logger.info("{} {} acildi: {} (veri: {})", URUN_ADI, __version__, adres, dizin)

    try:
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

            gorev_cubugu_kimligi()
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
                text_select=True,  # varsayilan False: mesajda secim/kopyalama calismiyordu
                background_color="#1f1f1e",
                js_api=api,
            )
            api._pencere.events.shown += lambda: pencere_ikonu(api._pencere)

            def one_getir() -> None:  # genel kisayol: pencere one gelsin
                api._pencere.restore()
                api._pencere.show()
                with contextlib.suppress(Exception):
                    api._pencere.native.Invoke(
                        __import__("System").Action(api._pencere.native.Activate)
                    )

            fastapi_app.state.one_getir = one_getir
            if AyarDeposu(dizin).oku().sistem_tepsisi:
                from app.services.tepsi import Tepsi

                tepsi = Tepsi(URUN_ADI, IKON, one_getir, api._pencere.destroy)
                api._tepside = tepsi.baslat()
            webview.start(private_mode=False, storage_path=str(dizin / "webview"))
    finally:
        _baglanti_sil(baglanti_yolu)
    if "tepsi" in locals():
        tepsi.kapat()
    sunucu.should_exit = True  # lifespan kapanisi: kendi baslattigimiz model sunucusunu durdurur
    is_parcacigi.join(timeout=15)
    return 0


if __name__ == "__main__":
    sys.exit(main())
