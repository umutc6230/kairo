"""Komut calistirma: zaman asimi, cikti siniri, process-tree iptali, arka plan isi (A1.7, A2.4).

Windows Job Object SUREC YASAM DONGUSU icindir: is nesnesi kapaninca tum alt surecler olur
(yetim `npm`/`pytest` kalmaz). DOSYA ya da AG SANDBOX'I DEGILDIR; komut, kullanicinin tum
yetkileriyle calisir. Bu nedenle komut calistirma izin motoruna baglidir ve UI izolasyonun
olmadigini acikca gosterir (`/api/izinler` -> `izolasyon: "yok"`).

Ortam degiskenleri allowlist ile verilir: sir tasiyan degiskenler alt surece gecmez.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import subprocess
import sys
import uuid
import weakref
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.agent.dosyalar import ortam_allowlist
from app.agent.izolasyon import IzolasyonAdaptoru, YokAdaptoru
from app.exceptions import Bulunamadi, UygulamaHatasi
from app.services import sirlar

# A13: ajanin baslattigi komut hangi gorevin? Runner arac cagrisindan once ayarlar
# (asyncio.to_thread baglami kopyalar); iptal o gorevin surec agaclarini hemen kapatir.
AKTIF_RUN: contextvars.ContextVar[str] = contextvars.ContextVar("aktif_run", default="")
_SERVISLER: weakref.WeakSet = weakref.WeakSet()


async def run_komutlarini_durdur(run_id: str) -> int:
    """Gorevin calisan tum komutlarini (on plan + arka plan) process-tree olarak durdurur."""
    if not run_id:
        return 0
    sayi = 0
    for servis in list(_SERVISLER):
        for is_id, is_ in list(servis.isler.items()):
            if is_.durum.sahip == run_id and is_.durum.durum == "calisiyor":
                with contextlib.suppress(Bulunamadi, OSError):
                    await servis.durdur(is_id)
                    sayi += 1
    return sayi


VARSAYILAN_TIMEOUT = 120
MAX_TIMEOUT = 900
MAX_CIKTI_KARAKTER = 30000  # modele verilen
MAX_GIRDI = 10000
SPOOL_SATIR = 2000  # arka plan isinde saklanan son satir sayisi
OLDURME_BEKLEME = 5.0  # A13: yonetilen cocuk surecler 5 sn icinde sonlanmali


def windows_bash() -> str | None:
    """Windows'ta Git Bash yolu (WSL'nin System32\\bash.exe'si DEGIL); yoksa None (cmd.exe)."""
    if sys.platform != "win32":
        return None
    import os
    import shutil

    adaylar = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "bin" / "bash.exe",
    ]
    if git := shutil.which("git"):
        adaylar.append(Path(git).resolve().parent.parent / "bin" / "bash.exe")
    for a in adaylar:
        if a.is_file() and "system32" not in str(a).lower():
            return str(a)
    return None


class KomutDurumu(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    komut: str
    cwd: str
    durum: str = "calisiyor"  # calisiyor | bitti | zaman_asimi | durduruldu | hata
    cikis_kodu: int | None = None
    baslangic: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    sure_sn: float | None = None
    arka_plan: bool = False
    izolasyon: str = "yok"
    sahip: str = ""  # ajan gorevi (run) kimligi


def _kirp(metin: str, sinir: int = MAX_CIKTI_KARAKTER) -> tuple[str, bool]:
    """Uzun ciktinin BASI ve SONU korunur: hata genelde sonda, komut ozeti basta olur."""
    if len(metin) <= sinir:
        return metin, False
    yari = sinir // 2
    return f"{metin[:yari]}\n[... {len(metin) - sinir} karakter atlandi ...]\n{metin[-yari:]}", True


class KomutIsi:
    """Tek bir calisan komut: process-tree'si bir Job Object'e baglidir."""

    def __init__(self, durum: KomutDurumu) -> None:
        self.durum = durum
        self.surec: asyncio.subprocess.Process | None = None
        self.satirlar: deque[str] = deque(maxlen=SPOOL_SATIR)
        self._is_nesnesi: int | None = None
        self._gorev: asyncio.Task | None = None
        self._bitti = asyncio.Event()

    def cikti(self) -> str:
        return "\n".join(self.satirlar)

    async def durdur(self) -> bool:
        """Tum process-tree'yi sonlandirir. 5 sn icinde olmezse zorla oldurur."""
        if self.surec is None or self.surec.returncode is not None:
            return False
        self._job_kapat()  # Windows: is nesnesi kapaninca tum agac oluyor
        with contextlib.suppress(ProcessLookupError, OSError):
            self.surec.terminate()
        try:
            await asyncio.wait_for(self.surec.wait(), timeout=OLDURME_BEKLEME)
        except TimeoutError:
            try:
                self.surec.kill()
                await asyncio.wait_for(self.surec.wait(), timeout=OLDURME_BEKLEME)
            except (ProcessLookupError, OSError, TimeoutError):
                return False
        return True

    def _job_bagla(self) -> None:
        if sys.platform != "win32" or self.surec is None:
            return
        from app.services.yerel_llm import _handle_kapat, cokunce_kapanacak_yap

        class _Sarmal:  # cokunce_kapanacak_yap Popen benzeri `_handle` bekler
            def __init__(self, pid: int) -> None:
                import ctypes

                k32 = ctypes.WinDLL("kernel32", use_last_error=True)
                k32.OpenProcess.restype = ctypes.c_void_p
                # PROCESS_SET_QUOTA | PROCESS_TERMINATE
                self._handle = k32.OpenProcess(0x0100 | 0x0001, False, pid) or 0

        sarmal = None
        try:
            sarmal = _Sarmal(self.surec.pid)
            if sarmal._handle:
                self._is_nesnesi = cokunce_kapanacak_yap(sarmal)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001 - job baglanamazsa komut yine calisir
            self._is_nesnesi = None
        finally:
            if sarmal is not None and sarmal._handle:
                _handle_kapat(sarmal._handle)

    def _job_kapat(self) -> None:
        if self._is_nesnesi is None:
            return
        try:
            from app.services.yerel_llm import _handle_kapat

            _handle_kapat(self._is_nesnesi)
        except Exception:  # noqa: BLE001
            pass
        self._is_nesnesi = None


class KomutServisi:
    """Calisan ve biten komutlari tutar; uzun isler sohbeti bloklamaz (A2.5)."""

    def __init__(
        self, en_fazla_is: int = 20, izolasyon: Callable[[], IzolasyonAdaptoru] = YokAdaptoru
    ) -> None:
        self.isler: dict[str, KomutIsi] = {}
        self.en_fazla_is = en_fazla_is
        self.izolasyon = izolasyon  # her cagrida guncel ayardan uretilir
        # uygulamanin loop'u (acilista atanir): arac kaydi is parcaciginda kurulunca loop'u
        # yakalayamiyor, arka plan komutu gecici loop'ta baslayip loop kapaninca oluyordu
        self.loop: asyncio.AbstractEventLoop | None = None
        _SERVISLER.add(self)

    def _yer_ac(self) -> None:
        bitmis = [i for i in self.isler.values() if i.durum.durum != "calisiyor"]
        while len(self.isler) >= self.en_fazla_is and bitmis:
            self.isler.pop(bitmis.pop(0).durum.id, None)

    def getir(self, is_id: str) -> KomutIsi:
        if is_id not in self.isler:
            raise Bulunamadi("Komut isi bulunamadi.")
        return self.isler[is_id]

    async def baslat(
        self,
        komut: str,
        cwd: Path,
        *,
        timeout: int = VARSAYILAN_TIMEOUT,
        arka_plan: bool = False,
        kok: Path | None = None,
        sahip: str = "",
        bash: bool = True,
    ) -> KomutIsi:
        if not komut.strip():
            raise UygulamaHatasi("Bos komut calistirilamaz.")
        if not cwd.is_dir():
            raise UygulamaHatasi(f"Calisma klasoru yok: {cwd}")
        adaptor = self.izolasyon()
        argv = adaptor.sar(
            komut, cwd, kok or cwd
        )  # kullanilamazsa UygulamaHatasi (sessiz dusus yok)
        self._yer_ac()
        timeout = max(1, min(int(timeout), MAX_TIMEOUT))
        is_ = KomutIsi(
            KomutDurumu(
                komut=komut, cwd=str(cwd), arka_plan=arka_plan, izolasyon=adaptor.ad, sahip=sahip
            )  # fmt: skip
        )
        ortak = {
            "cwd": str(cwd),
            # on plan isi girdi beklerse asili kalmasin; arka plan isine girdi_gonder yazar
            "stdin": subprocess.PIPE if arka_plan else subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "env": {**ortam_allowlist(), **sirlar.ortam()},  # kasa: kullanicinin verdigi anahtarlar
            "creationflags": subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        }
        try:
            if argv:  # konteyner: argv dogrudan exe'ye gider, cmd.exe tirnak sorunu yok
                is_.surec = await asyncio.create_subprocess_exec(*argv, **ortak)
            elif bash and (bash_yolu := windows_bash()):
                # Git Bash: ; && | heredoc ve cok satirli `python -c` calisir. cmd.exe'de satir
                # sonu komutu bitiriyor, `;` ayirici degil: canli testte cikti bos donuyordu.
                is_.surec = await asyncio.create_subprocess_exec(bash_yolu, "-c", komut, **ortak)
            else:  # shell: Windows'ta exec+liste tirnaklari \" diye kacirir, cmd yolu taniyamaz
                is_.surec = await asyncio.create_subprocess_shell(komut, **ortak)
        except (OSError, ValueError) as e:
            raise UygulamaHatasi(f"Komut baslatilamadi: {e}") from e
        is_._job_bagla()
        self.isler[is_.durum.id] = is_
        is_._gorev = asyncio.create_task(self._surdur(is_, timeout))
        return is_

    async def _surdur(self, is_: KomutIsi, timeout: int) -> None:
        bas = asyncio.get_running_loop().time()
        try:
            await asyncio.wait_for(self._oku(is_), timeout=timeout)
            kod = await is_.surec.wait() if is_.surec else None
            is_.durum.cikis_kodu = kod
            is_.durum.durum = "bitti"
        except TimeoutError:
            await is_.durdur()
            is_.durum.durum = "zaman_asimi"
            is_.satirlar.append(f"[{timeout} sn zaman asimi: surec ve alt surecleri durduruldu]")
        except asyncio.CancelledError:
            await is_.durdur()
            is_.durum.durum = "durduruldu"
            raise
        except OSError as e:
            is_.durum.durum = "hata"
            is_.satirlar.append(f"[okuma hatasi: {e}]")
        finally:
            is_._job_kapat()
            is_.durum.sure_sn = round(asyncio.get_running_loop().time() - bas, 2)
            is_._bitti.set()

    @staticmethod
    async def _oku(is_: KomutIsi) -> None:
        if is_.surec is None or is_.surec.stdout is None:
            return
        tampon = b""
        while True:
            parca = await is_.surec.stdout.read(8192)
            if not parca:
                break
            tampon += parca
            while b"\n" in tampon:
                satir, tampon = tampon.split(b"\n", 1)
                is_.satirlar.append(satir.decode("utf-8", errors="replace").rstrip("\r"))
        if tampon:
            is_.satirlar.append(tampon.decode("utf-8", errors="replace").rstrip("\r"))

    async def girdi_gonder(self, is_id: str, metin: str) -> dict:
        """Calisan arka plan isinin stdin'ine yazar (satir sonu yoksa eklenir)."""
        is_ = self.getir(is_id)
        s = is_.surec
        if s is None or s.returncode is not None or is_.durum.durum != "calisiyor":
            raise UygulamaHatasi("Komut calismiyor; girdi gonderilemez.")
        if s.stdin is None:
            raise UygulamaHatasi("Yalniz arka planda baslatilan komuta girdi gonderilebilir.")
        if len(metin) > MAX_GIRDI:
            raise UygulamaHatasi(f"Girdi en fazla {MAX_GIRDI} karakter olabilir.")
        try:
            s.stdin.write((metin if metin.endswith("\n") else metin + "\n").encode("utf-8"))
            await s.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            raise UygulamaHatasi(f"Girdi gonderilemedi: {e}") from e
        return {"gonderildi": len(metin), **self.ozet(is_)}

    async def bekle(self, is_: KomutIsi) -> KomutIsi:
        await is_._bitti.wait()
        return is_

    async def durdur(self, is_id: str) -> dict:
        is_ = self.getir(is_id)
        if is_._gorev and not is_._gorev.done():
            is_._gorev.cancel()
            await asyncio.gather(is_._gorev, return_exceptions=True)
        await is_.durdur()  # gorev iptali sureci oldurmez; agac her durumda kapatilir
        is_.durum.durum = "durduruldu"
        return self.ozet(is_)

    def ozet(self, is_: KomutIsi, tam: bool = False) -> dict:
        cikti, kesildi = _kirp(
            sirlar.maskele(is_.cikti()), MAX_CIKTI_KARAKTER if not tam else 10**9
        )
        return {
            **is_.durum.model_dump(mode="json"),
            "cikti": cikti,
            "truncated": kesildi,
            "satir_sayisi": len(is_.satirlar),
        }

    async def hepsini_durdur(self) -> None:
        for is_id in list(self.isler):
            try:
                await self.durdur(is_id)
            except (Bulunamadi, OSError):
                continue
