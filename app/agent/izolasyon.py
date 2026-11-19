"""Komut izolasyon adaptorleri (A1.8).

- `YokAdaptoru`: komut kullanicinin tum yetkileriyle calisir; yalniz surec yasam dongusu
  (Job Object) vardir. DOSYA/AG SANDBOX'I DEGILDIR. Bu durumda politika otomatik modu daraltir:
  komutlar onay ister.
- `KonteynerAdaptoru`: Podman/Docker ile `--network none`, yalniz proje koku bagli, tum
  capability'ler dusurulmus, yeni yetki kazanimi kapali. Imaj indirilmez (`--pull=never`);
  yoksa kullanilamaz raporlanir. Bu gercek dosya + ag izolasyonudur (konteyner kacisi haric).

Hicbir adaptor komut metnine regex uygulayarak "sandbox" iddia etmez.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Protocol

KONTEYNER_KOK = "/w"
DURUM_ONBELLEK_SN = 30.0


class IzolasyonAdaptoru(Protocol):
    ad: str

    def durum(self) -> dict: ...

    @property
    def izole(self) -> bool: ...

    def sar(self, komut: str, cwd: Path, kok: Path) -> list[str] | None:
        """Calistirilacak argv; None ise komut normal kabukta calisir."""


class YokAdaptoru:
    ad = "yok"
    izole = False

    def durum(self) -> dict:
        return {
            "ad": self.ad,
            "izole": False,
            "kullanilabilir": True,
            "not": (
                "Komutlar icin isletim sistemi duzeyinde dosya/ag izolasyonu yok; yalniz yol "
                "kapsami, izin motoru ve surec yasam dongusu (Job Object) uygulanir. Bu yuzden "
                "otomatik modda da komutlar onay ister."
            ),
        }

    def sar(self, komut: str, cwd: Path, kok: Path) -> list[str] | None:
        return None


class KonteynerAdaptoru:
    ad = "konteyner"

    def __init__(self, imaj: str, motor: str | None = None) -> None:
        self.imaj = imaj
        self.motor = motor or next((m for m in ("podman", "docker") if shutil.which(m)), "")
        self._onbellek: tuple[float, dict] | None = None

    def _calistir(self, *a: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - sabit argumanlar, kabuk yok
            [shutil.which(self.motor) or self.motor, *a],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    def _yokla(self) -> dict:
        temel = {"ad": self.ad, "motor": self.motor, "imaj": self.imaj}
        if not self.motor:
            return temel | {"izole": False, "kullanilabilir": False, "not": "Podman/Docker yok."}
        try:
            if self._calistir("info").returncode != 0:
                return temel | {
                    "izole": False,
                    "kullanilabilir": False,
                    "not": f"{self.motor} calismiyor (or. `podman machine start`).",
                }
            if (
                self._calistir(
                    "image", "exists" if self.motor == "podman" else "inspect", self.imaj
                ).returncode
                != 0
            ):
                return temel | {
                    "izole": False,
                    "kullanilabilir": False,
                    "not": f"Imaj yerelde yok; once elle indirin: {self.motor} pull {self.imaj}",
                }
        except (OSError, subprocess.TimeoutExpired) as e:
            return temel | {"izole": False, "kullanilabilir": False, "not": f"Yoklanamadi: {e}"}
        return temel | {
            "izole": True,
            "kullanilabilir": True,
            "not": "Ag kapali, yalniz proje klasoru bagli, capability'ler dusuruldu.",
        }

    def durum(self) -> dict:
        simdi = time.monotonic()
        if self._onbellek is None or simdi - self._onbellek[0] > DURUM_ONBELLEK_SN:
            self._onbellek = (simdi, self._yokla())
        return self._onbellek[1]

    @property
    def izole(self) -> bool:
        return bool(self.durum()["izole"])

    def sar(self, komut: str, cwd: Path, kok: Path) -> list[str] | None:
        if not self.izole:  # kullanilamiyorsa sessizce izolasyonsuz calistirma: REDDET
            from app.exceptions import UygulamaHatasi

            raise UygulamaHatasi(f"Konteyner izolasyonu kullanilamiyor: {self.durum()['not']}")
        ic = (Path(KONTEYNER_KOK) / cwd.relative_to(kok)).as_posix()
        return [
            shutil.which(self.motor) or self.motor,
            "run", "--rm", "-i", "--pull=never",
            "--network", "none",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "256",
            "--memory", "2g",
            "-v", f"{kok}:{KONTEYNER_KOK}",
            "-w", ic,
            self.imaj, "sh", "-c", komut,
        ]  # fmt: skip


class KumAdaptoru:
    """Docker'siz Windows kum havuzu (AppContainer): ag kapali, yalniz proje koku yazilir."""

    ad = "kum"

    def durum(self) -> dict:
        from app.agent import kum

        ok = kum.destekli()
        return {
            "ad": self.ad,
            "izole": ok,
            "kullanilabilir": ok,
            "not": (
                "Windows AppContainer: ag kapali, yalniz proje klasorune yazilir, kullanici "
                "profili kapali. Kullanici klasorune kurulu araclar calismayabilir. "
                "`dir`/PowerShell surucu kokunu okuyamazsa bir kez yonetici olarak: "
                "Kairo.exe --kum-kur <proje klasoru>"
                if ok
                else "Windows AppContainer yalniz Windows 8+ uzerinde var."
            ),
        }

    @property
    def izole(self) -> bool:
        return bool(self.durum()["izole"])

    def sar(self, komut: str, cwd: Path, kok: Path) -> list[str] | None:
        from app.agent import kum

        if not self.izole:  # kullanilamiyorsa sessizce izolasyonsuz calistirma: REDDET
            from app.exceptions import UygulamaHatasi

            raise UygulamaHatasi(self.durum()["not"])
        return kum.argv(kok, cwd, komut)


def adaptor_olustur(ad: str, imaj: str) -> IzolasyonAdaptoru:
    if ad == "kum":
        return KumAdaptoru()
    return KonteynerAdaptoru(imaj) if ad == "konteyner" else YokAdaptoru()
