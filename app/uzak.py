"""Remote Control (A12.1-3). VARSAYILAN KAPALI; yerel ozelliklerden bagimsiz.

- Ayri sunucu, ayri port, YALNIZ TLS (kendinden imzali sertifika; parmak izi eslesme ekraninda
  gosterilir, telefon kullanicisi dogrular). Loopback API internete ACILMAZ: uzak uygulama sabit bir
  beyaz liste uzerinden ayni surecteki yerel API'yi cagirir; politika tek yerde kalir.
- Eslesme: yerel arayuzde uretilen 8 karakterlik, 5 dk gecerli, TEK KULLANIMLIK kod + rol.
- Token: rastgele 256 bit, yalniz SHA-256 ozeti saklanir; 12 saat gecerli, /yenile ile dondurulur
  (eski gecersiz), cihaz omru en fazla 30 gun; yerelden aninda iptal (revoke).
- Roller: izleyici (gorev izle) < operator (+ mesaj, duraklat/devam/iptal) < onaylayici (+ onay).
  Uzak istemci mod, izin, proje, dosya, ayar, model, MCP... DEGISTIREMEZ: bu uclar yok.
- Rate limit: eslesme IP basina 5/dk; cihaz basina 120 istek/dk.
- Denetim: her uzak istek (cihaz, ip, yol, sonuc) kaydedilir; govde/token yazilmaz.
- Baglanti kopmasi: yerel gorevler etkilenmez; uzak sunucu kapatilinca tum tokenlar gecerli kalir
  ama sunucu yoktur; iptal edilen cihaz bir sonraki istekte 401 alir.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import secrets
import socket
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.services.depo import json_oku, json_yaz

Rol = Literal["izleyici", "operator", "onaylayici"]
ROL_SIRA = {"izleyici": 0, "operator": 1, "onaylayici": 2}
KOD_OMRU = 300
TOKEN_OMRU = 12 * 3600
CIHAZ_OMRU = 30 * 24 * 3600
KOD_ALFABE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # karisan 0/O, 1/I yok


def _ozet(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


class Cihaz(BaseModel):
    id: str
    ad: str
    rol: Rol
    token_ozet: str
    eslesme: float
    son_kullanma: float
    son_gorulme: float = 0
    iptal: bool = False


class UzakHata(Exception):
    def __init__(self, mesaj: str, kod: int) -> None:
        super().__init__(mesaj)
        self.mesaj, self.kod = mesaj, kod


class HizSiniri:
    def __init__(self, sayi: int, pencere: float = 60.0) -> None:
        self.sayi, self.pencere = sayi, pencere
        self._k: dict[str, deque] = defaultdict(deque)
        self._kilit = threading.Lock()

    def izin(self, anahtar: str, simdi: float | None = None) -> bool:
        simdi = time.monotonic() if simdi is None else simdi
        with self._kilit:
            q = self._k[anahtar]
            while q and simdi - q[0] > self.pencere:
                q.popleft()
            if len(q) >= self.sayi:
                return False
            q.append(simdi)
            return True


class UzakDeposu:
    def __init__(self, veri_dizini: Path, saat: Callable[[], float] = time.time) -> None:
        self.yol = veri_dizini / "uzak.json"
        self.denetim_yolu = veri_dizini / "uzak-denetim.jsonl"
        self.saat = saat
        self._kilit = threading.Lock()

    def _oku(self) -> dict:
        v = json_oku(self.yol, {}) or {}
        return {"cihazlar": v.get("cihazlar", []), "kodlar": v.get("kodlar", [])}

    def _yaz(self, v: dict) -> None:
        simdi = self.saat()
        v["kodlar"] = [k for k in v["kodlar"] if k["son"] > simdi]
        json_yaz(self.yol, v)

    def kod_olustur(self, rol: Rol) -> dict:
        if rol not in ROL_SIRA:
            raise UzakHata("Gecersiz rol.", 400)
        kod = "".join(secrets.choice(KOD_ALFABE) for _ in range(8))
        with self._kilit:
            v = self._oku()
            v["kodlar"].append({"ozet": _ozet(kod), "rol": rol, "son": self.saat() + KOD_OMRU})
            self._yaz(v)
        return {"kod": kod, "rol": rol, "gecerlilik_sn": KOD_OMRU}

    def esles(self, kod: str, ad: str) -> dict:
        kod = (kod or "").strip().upper().replace("-", "")
        with self._kilit:
            v = self._oku()
            simdi = self.saat()
            k = next((k for k in v["kodlar"] if k["ozet"] == _ozet(kod) and k["son"] > simdi), None)
            if k is None:
                raise UzakHata("Kod gecersiz ya da suresi dolmus.", 401)
            v["kodlar"].remove(k)  # tek kullanimlik
            token = secrets.token_urlsafe(32)
            c = Cihaz(id=uuid.uuid4().hex[:10], ad=(ad or "cihaz")[:40], rol=k["rol"],
                      token_ozet=_ozet(token), eslesme=simdi,
                      son_kullanma=simdi + TOKEN_OMRU)  # fmt: skip
            v["cihazlar"].append(c.model_dump())
            self._yaz(v)
        return {"token": token, "cihaz_id": c.id, "rol": c.rol, "son_kullanma": c.son_kullanma}

    def dogrula(self, token: str) -> Cihaz:
        ozet = _ozet(token or "")
        simdi = self.saat()
        with self._kilit:
            v = self._oku()
            for i, ham in enumerate(v["cihazlar"]):
                if secrets.compare_digest(ham["token_ozet"], ozet):
                    c = Cihaz(**ham)
                    if c.iptal:
                        raise UzakHata("Bu cihazin eslesmesi iptal edildi.", 401)
                    if c.son_kullanma <= simdi:
                        raise UzakHata("Oturum suresi doldu; yeniden eslestirin.", 401)
                    c.son_gorulme = simdi
                    v["cihazlar"][i] = c.model_dump()
                    self._yaz(v)
                    return c
        raise UzakHata("Gecersiz token.", 401)

    def yenile(self, token: str) -> dict:
        c = self.dogrula(token)
        simdi = self.saat()
        if simdi - c.eslesme >= CIHAZ_OMRU:
            raise UzakHata("Cihaz omru doldu; yeniden eslestirin.", 401)
        yeni = secrets.token_urlsafe(32)
        with self._kilit:
            v = self._oku()
            for i, ham in enumerate(v["cihazlar"]):
                if ham["id"] == c.id:
                    ham["token_ozet"] = _ozet(yeni)  # eski token artik gecersiz
                    ham["son_kullanma"] = min(simdi + TOKEN_OMRU, c.eslesme + CIHAZ_OMRU)
                    v["cihazlar"][i] = ham
            self._yaz(v)
        return {"token": yeni, "cihaz_id": c.id, "rol": c.rol}

    def iptal(self, cihaz_id: str) -> None:
        with self._kilit:
            v = self._oku()
            bulundu = False
            for ham in v["cihazlar"]:
                if ham["id"] == cihaz_id:
                    ham["iptal"], bulundu = True, True
            if not bulundu:
                raise UzakHata("Cihaz bulunamadi.", 404)
            self._yaz(v)

    def liste(self) -> list[dict]:
        return [{k: x for k, x in c.items() if k != "token_ozet"} for c in self._oku()["cihazlar"]]

    def denetle(self, cihaz: str, ip: str, yol: str, sonuc: int) -> None:
        kayit = {"zaman": self.saat(), "cihaz": cihaz, "ip": ip, "yol": yol[:200], "sonuc": sonuc}
        with self._kilit, self.denetim_yolu.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")

    def denetim(self, son: int = 100) -> list[dict]:
        if not self.denetim_yolu.exists():
            return []
        satirlar = self.denetim_yolu.read_text(encoding="utf-8").splitlines()[-son:]
        return [json.loads(s) for s in satirlar if s.strip()]


# ---- TLS: kendinden imzali sertifika (yerel ag; parmak izi ile dogrulanir) ----
def yerel_ipler() -> list[str]:
    ipler = {"127.0.0.1"}
    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ipler.add(bilgi[4][0])
    except OSError:
        pass
    return sorted(ipler)


def sertifika(dizin: Path) -> tuple[Path, Path, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    dizin.mkdir(parents=True, exist_ok=True)
    cert_yol, key_yol = dizin / "sertifika.pem", dizin / "anahtar.pem"
    if not (cert_yol.exists() and key_yol.exists()):
        anahtar = ec.generate_private_key(ec.SECP256R1())
        ad = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Yerel AI Studio Uzak")])
        simdi = dt.datetime.now(dt.UTC)
        san = [x509.DNSName("localhost")] + [
            x509.IPAddress(ipaddress.ip_address(i)) for i in yerel_ipler()]  # fmt: skip
        c = (x509.CertificateBuilder().subject_name(ad).issuer_name(ad)
             .public_key(anahtar.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(simdi - dt.timedelta(minutes=5))
             .not_valid_after(simdi + dt.timedelta(days=365))
             .add_extension(x509.SubjectAlternativeName(san), critical=False)
             .sign(anahtar, hashes.SHA256()))  # fmt: skip
        key_yol.write_bytes(anahtar.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))  # fmt: skip
        cert_yol.write_bytes(c.public_bytes(serialization.Encoding.PEM))
    der = x509.load_pem_x509_certificate(cert_yol.read_bytes()).public_bytes(
        serialization.Encoding.DER
    )
    parmak = hashlib.sha256(der).hexdigest().upper()
    return cert_yol, key_yol, ":".join(parmak[i : i + 4] for i in range(0, 32, 4))


# ---- uzak uygulama: sabit beyaz liste ----
IcCagri = Callable[[str, str, Any], Awaitable[tuple[int, Any]]]
# (metod, uzak yol deseni) -> (gereken rol, ic yol sablonu)
ROTALAR: list[tuple[str, str, Rol, str]] = [
    ("GET", "/uzak/api/gorevler", "izleyici", "/api/gorevler"),
    ("GET", "/uzak/api/gorevler/{id}", "izleyici", "/api/gorevler/{id}"),
    ("POST", "/uzak/api/gorevler/{id}/mesaj", "operator", "/api/gorevler/{id}/mesaj"),
    ("POST", "/uzak/api/gorevler/{id}/duraklat", "operator", "/api/gorevler/{id}/duraklat"),
    ("POST", "/uzak/api/gorevler/{id}/devam", "operator", "/api/gorevler/{id}/devam"),
    ("POST", "/uzak/api/gorevler/{id}/iptal", "operator", "/api/gorevler/{id}/iptal"),
    ("POST", "/uzak/api/onaylar/{id}", "onaylayici", "/api/onaylar/{id}"),
]


def _eslestir(metod: str, yol: str) -> tuple[Rol, str] | None:
    parca = yol.rstrip("/").split("/")
    for m, desen, rol, ic in ROTALAR:
        d = desen.split("/")
        if m != metod or len(d) != len(parca):
            continue
        degisken = {}
        for a, b in zip(d, parca, strict=True):
            if a == "{id}":
                if not b or not all(c.isalnum() or c in "-_" for c in b) or len(b) > 64:
                    break
                degisken["id"] = b
            elif a != b:
                break
        else:
            return rol, ic.format(**degisken)
    return None


def uzak_uygulamasi(depo: UzakDeposu, ic_cagri: IcCagri, parmak_izi: str = "") -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    esles_siniri, cihaz_siniri = HizSiniri(5), HizSiniri(120)

    def ip(istek: Request) -> str:
        return istek.client.host if istek.client else "?"

    @app.middleware("http")
    async def _guvenlik(istek: Request, sonraki):
        cevap = await sonraki(istek)
        cevap.headers["Cache-Control"] = "no-store"
        cevap.headers["X-Content-Type-Options"] = "nosniff"
        cevap.headers["Referrer-Policy"] = "no-referrer"
        cevap.headers["Strict-Transport-Security"] = "max-age=31536000"
        return cevap

    @app.get("/uzak/")
    @app.get("/uzak")
    async def sayfa() -> HTMLResponse:
        html = (Path(__file__).parent / "web" / "uzak.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Content-Security-Policy": (
            "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'")})  # fmt: skip

    @app.post("/uzak/esles")
    async def esles(istek: Request) -> JSONResponse:
        if not esles_siniri.izin(ip(istek)):
            depo.denetle("-", ip(istek), "/uzak/esles", 429)
            return JSONResponse({"hata": "Cok fazla deneme; 1 dk bekleyin."}, status_code=429)
        try:
            veri = await istek.json()
            sonuc = depo.esles(str(veri.get("kod", "")), str(veri.get("cihaz", "")))
        except UzakHata as e:
            depo.denetle("-", ip(istek), "/uzak/esles", e.kod)
            return JSONResponse({"hata": e.mesaj}, status_code=e.kod)
        except ValueError:
            return JSONResponse({"hata": "Gecersiz istek."}, status_code=400)
        depo.denetle(sonuc["cihaz_id"], ip(istek), "/uzak/esles", 200)
        return JSONResponse(sonuc)

    def _token(istek: Request) -> str:
        b = istek.headers.get("authorization", "")
        return b[7:] if b.lower().startswith("bearer ") else ""

    @app.post("/uzak/yenile")
    async def yenile(istek: Request) -> JSONResponse:
        try:
            s = depo.yenile(_token(istek))
        except UzakHata as e:
            depo.denetle("-", ip(istek), "/uzak/yenile", e.kod)
            return JSONResponse({"hata": e.mesaj}, status_code=e.kod)
        depo.denetle(s["cihaz_id"], ip(istek), "/uzak/yenile", 200)
        return JSONResponse(s)

    @app.get("/uzak/ben")
    async def ben(istek: Request) -> JSONResponse:
        try:
            c = depo.dogrula(_token(istek))
        except UzakHata as e:
            return JSONResponse({"hata": e.mesaj}, status_code=e.kod)
        return JSONResponse({"cihaz_id": c.id, "ad": c.ad, "rol": c.rol,
                             "son_kullanma": c.son_kullanma, "parmak_izi": parmak_izi})  # fmt: skip

    @app.api_route("/uzak/api/{yol:path}", methods=["GET", "POST"])
    async def gecit(istek: Request, yol: str) -> JSONResponse:
        tam = f"/uzak/api/{yol}"
        try:
            c = depo.dogrula(_token(istek))
        except UzakHata as e:
            depo.denetle("-", ip(istek), tam, e.kod)
            return JSONResponse({"hata": e.mesaj}, status_code=e.kod)
        if not cihaz_siniri.izin(c.id):
            depo.denetle(c.id, ip(istek), tam, 429)
            return JSONResponse({"hata": "Istek siniri asildi."}, status_code=429)
        e = _eslestir(istek.method, tam)
        if e is None:
            depo.denetle(c.id, ip(istek), tam, 404)
            return JSONResponse({"hata": "Uzak erisimde bu islem yok."}, status_code=404)
        rol, ic = e
        if ROL_SIRA[c.rol] < ROL_SIRA[rol]:
            depo.denetle(c.id, ip(istek), tam, 403)
            return JSONResponse({"hata": f"Bu islem icin '{rol}' rolu gerekir."}, status_code=403)
        govde = None
        if istek.method == "POST":
            try:
                ham = await istek.json() if await istek.body() else {}
            except ValueError:
                return JSONResponse({"hata": "Gecersiz JSON."}, status_code=400)
            # yalniz beklenen alanlar gecer; uzak istemci baska parametre enjekte edemez
            if ic.endswith("/mesaj"):
                govde = {"metin": str(ham.get("metin", ""))[:4000]}
            elif ic.startswith("/api/onaylar/"):
                govde = {"onayla": bool(ham.get("onayla", False))}
        durum, veri = await ic_cagri(istek.method, ic, govde)
        depo.denetle(c.id, ip(istek), tam, durum)
        return JSONResponse(veri, status_code=durum)

    return app


class UzakSunucu:
    """Uzak sunucuyu ayri thread'de TLS ile calistirir; yerel API'den ac/kapat."""

    def __init__(self) -> None:
        self.sunucu: Any = None
        self.adres = ""

    def acik_mi(self) -> bool:
        return self.sunucu is not None and not self.sunucu.should_exit

    def ac(self, app: FastAPI, port: int, cert: Path, key: Path, host: str = "0.0.0.0") -> None:  # noqa: S104
        import uvicorn

        if self.acik_mi():
            return
        cfg = uvicorn.Config(app, host=host, port=port, ssl_certfile=str(cert),
                             ssl_keyfile=str(key), log_level="warning")  # fmt: skip
        self.sunucu = uvicorn.Server(cfg)
        threading.Thread(target=self.sunucu.run, daemon=True).start()
        for _ in range(100):
            if self.sunucu.started:
                break
            time.sleep(0.05)
        self.adres = f"https://{host}:{port}/uzak/"

    def kapat(self) -> None:
        if self.sunucu is not None:
            self.sunucu.should_exit = True
        self.sunucu = None
