"""Python SDK (A10.4): calisan Yerel AI Studio'ya (ya da ayni surecteki uygulamaya) baglanir.

Ayri bir ajan motoru YOKTUR: tum cagrilar ayni /api uclarina gider; izin motoru, butce, onay ve
checkpoint kurallari arayuzdekiyle birebir aynidir. Oturum anahtari olmadan API kullanilamaz.

    with Studio("http://127.0.0.1:8765", anahtar) as s:
        s.proje_ac("C:/projem", guven="guvenilir", mod="onayli")
        run = s.gorev("testleri gecir", kabul=["pytest gecsin"])
        for olay in s.izle(run["id"]):
            print(olay["durum"])
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

API_SURUMU = 1
BITMIS = {"basarili", "dogrulanmadi", "basarisiz", "iptal"}
DURAN = BITMIS | {"onay_bekliyor", "karar_bekliyor", "duraklatildi"}


class StudioHatasi(Exception):
    pass


class Studio:
    def __init__(self, adres: str, anahtar: str, transport: Any = None, zaman: float = 60) -> None:
        self._c = httpx.Client(
            base_url=adres.rstrip("/"),
            headers={"X-YAS-Oturum": anahtar},
            transport=transport,
            timeout=zaman,
        )

    def __enter__(self) -> Studio:
        return self

    def __exit__(self, *_: object) -> None:
        self.kapat()

    def kapat(self) -> None:
        self._c.close()

    def _istek(self, yontem: str, yol: str, **kw: Any) -> Any:
        r = self._c.request(yontem, f"/api{yol}", **kw)
        try:
            veri = r.json()
        except ValueError:
            veri = {}
        if r.status_code >= 400:
            raise StudioHatasi(veri.get("hata") or f"HTTP {r.status_code}")
        return veri

    # ---- proje / ayar ----
    def bilgi(self) -> dict:
        return self._istek("GET", "/bilgi")

    def proje_ac(self, yol: str, guven: str = "sinirli", mod: str | None = None) -> dict:
        p = self._istek("POST", "/projeler", json={"yol": yol, "guven": guven})
        if mod:
            self._istek("PUT", f"/projeler/{p['id']}/mod", json={"mod": mod})
        return p

    # ---- Run API ----
    def gorev(self, hedef: str, kabul: list[str] | None = None, max_adim: int | None = None,
              izole: bool = False) -> dict:  # fmt: skip
        govde: dict[str, Any] = {"hedef": hedef, "kabul": kabul or [], "izole": izole}
        if max_adim:
            govde["butce"] = {"max_adim": max_adim}
        return self._istek("POST", "/gorevler", json=govde)

    def durum(self, run_id: str) -> dict:
        return self._istek("GET", f"/gorevler/{run_id}")

    def islem(self, run_id: str, islem: str) -> dict:
        """islem: duraklat | devam | iptal | tekrar"""
        return self._istek("POST", f"/gorevler/{run_id}/{islem}")

    def mesaj(self, run_id: str, metin: str) -> dict:
        return self._istek("POST", f"/gorevler/{run_id}/mesaj", json={"metin": metin})

    def onay(self, onay_id: str, onayla: bool) -> dict:
        return self._istek("POST", f"/onaylar/{onay_id}", json={"onayla": onayla})

    def izle(
        self, run_id: str, aralik: float = 1.0, en_fazla_sn: float = 24 * 3600
    ) -> Iterator[dict]:
        """Durum degistikce olay verir; gorev bitince ya da onay/karar beklerken DURUR
        (headless kullanim sonsuza kadar beklemez)."""
        son = ""
        bas = time.monotonic()
        while True:
            r = self.durum(run_id)
            imza = f"{r['durum']}|{len(r['adimlar'])}|{r.get('guncelleme')}"
            if imza != son:
                son = imza
                yield r
            if r["durum"] in DURAN:
                return
            if time.monotonic() - bas > en_fazla_sn:
                raise StudioHatasi("Izleme suresi doldu.")
            time.sleep(aralik)
