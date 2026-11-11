"""Bilgisayari uyanik tut (Claude Desktop 'Keep computer awake'): yalniz uygulama acikken.

Windows'ta SetThreadExecutionState cagran is parcacigina baglidir; bu yuzden ayri bir is
parcacigi durumu tutar ve kapatilinca birakir. Diger platformlarda islem yapmaz.
"""

from __future__ import annotations

import sys
import threading

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


class Uyanik:
    def __init__(self) -> None:
        self._dur: threading.Event | None = None

    @property
    def acik(self) -> bool:
        return self._dur is not None

    def ayarla(self, acik: bool) -> bool:
        if acik and self._dur is None and sys.platform == "win32":
            self._dur = threading.Event()
            threading.Thread(target=self._tut, args=(self._dur,), daemon=True).start()
        elif not acik and self._dur is not None:
            self._dur.set()
            self._dur = None
        return self.acik

    @staticmethod
    def _tut(dur: threading.Event) -> None:
        import ctypes

        k = ctypes.windll.kernel32
        k.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        dur.wait()
        k.SetThreadExecutionState(ES_CONTINUOUS)
