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
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.services.depo import json_oku, json_yaz

# tam: telefondan masaustu uygulamanin TAM arayuzu (ince istemci; tum mantik bilgisayarda)
Rol = Literal["izleyici", "operator", "onaylayici", "tam"]
ROL_SIRA = {"izleyici": 0, "operator": 1, "onaylayici": 2, "tam": 3}
TAILSCALE_AGLARI = [
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),
]
CEREZ = "yas_uzak"
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


def sertifika(dizin: Path, hostlar: list[str] | None = None) -> tuple[Path, Path, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    dizin.mkdir(parents=True, exist_ok=True)
    cert_yol, key_yol = dizin / "sertifika.pem", dizin / "anahtar.pem"
    istenen = set(hostlar or [])
    if cert_yol.exists() and istenen:  # adres (or. Tailscale IP) degistiyse yeniden uret
        mevcut = x509.load_pem_x509_certificate(cert_yol.read_bytes())
        try:
            san_ = mevcut.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            kapsanan = {str(i) for i in san_.get_values_for_type(x509.IPAddress)}
        except x509.ExtensionNotFound:
            kapsanan = set()
        if not istenen <= kapsanan:
            cert_yol.unlink()
    if not (cert_yol.exists() and key_yol.exists()):
        anahtar = ec.generate_private_key(ec.SECP256R1())
        ad = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Kairo Uzak")])
        simdi = dt.datetime.now(dt.UTC)
        san = [x509.DNSName("localhost")] + [
            x509.IPAddress(ipaddress.ip_address(i))
            for i in sorted(set(yerel_ipler()) | istenen)]  # fmt: skip
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
        return _cerezli(sonuc)

    def _token(istek: Request) -> str:
        return token_al(istek.headers.get("authorization", ""), istek.headers.get("cookie", ""))

    def _cerezli(sonuc: dict) -> JSONResponse:
        cevap = JSONResponse(sonuc)
        cevap.headers["Set-Cookie"] = cerez(sonuc["token"])
        return cevap

    @app.post("/uzak/yenile")
    async def yenile(istek: Request) -> JSONResponse:
        try:
            s = depo.yenile(_token(istek))
        except UzakHata as e:
            depo.denetle("-", ip(istek), "/uzak/yenile", e.kod)
            return JSONResponse({"hata": e.mesaj}, status_code=e.kod)
        depo.denetle(s["cihaz_id"], ip(istek), "/uzak/yenile", 200)
        return _cerezli(s)

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


def token_al(yetki: str, cerezler: str) -> str:
    if yetki.lower().startswith("bearer "):
        return yetki[7:].strip()
    for parca in cerezler.split(";"):
        ad, _, deger = parca.strip().partition("=")
        if ad == CEREZ:
            return deger
    return ""


def cerez(token: str) -> str:
    return f"{CEREZ}={token}; Path=/; Max-Age={CIHAZ_OMRU}; HttpOnly; Secure; SameSite=Strict"


def tailscale_ip() -> str:
    """Bu bilgisayarin Tailscale IPv4 adresi; Tailscale yok/bagli degilse bos."""
    import shutil
    import subprocess

    exe = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    try:
        r = subprocess.run(  # noqa: S603 - sabit arguman
            [exe, "ip", "-4"], capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return ""
    satirlar = (r.stdout or "").strip().splitlines() if r.returncode == 0 else []
    try:
        ip = satirlar[0].strip() if satirlar else ""
        return ip if ip and ipaddress.ip_address(ip) in TAILSCALE_AGLARI[0] else ""
    except ValueError:
        return ""


def _yanit(durum: int, govde: dict | None = None, yonlendir: str = "") -> tuple[dict, bytes]:
    basliklar = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
    if yonlendir:
        basliklar.append((b"location", yonlendir.encode()))
    bas = {"type": "http.response.start", "status": durum, "headers": basliklar}
    return bas, json.dumps(govde or {}, ensure_ascii=False).encode()


def tam_erisim_asgi(
    depo: UzakDeposu, uzak_app: FastAPI, ana_app: Any, oturum_anahtari: str,
    izinli_aglar: list | None = None,
) -> Callable:  # fmt: skip
    """Uzak sunucunun ASGI giris noktasi.

    /uzak/* -> eslesme sayfasi + sinirli API. Diger her sey -> YALNIZ 'tam' rollu, gecerli tokenli
    cihaz icin ayni surecteki ana uygulama (arayuz + API, akislar dahil). Istek yeniden yazilir:
    yetki/cerez/origin basliklari silinir, Host loopback olur, oturum anahtarini SUNUCU ekler
    (telefona gonderilmez). izinli_aglar verilirse (Tailscale) disindaki IP'ler reddedilir.
    """
    sinir = HizSiniri(900)
    atla = {"authorization", "cookie", "origin", "referer", "host", "x-yas-oturum",
            "x-yas-uzak-cihaz"}  # fmt: skip

    async def yaz(send: Callable, durum: int, govde: dict | None = None, git: str = "") -> None:
        bas, gov = _yanit(durum, govde, git)
        await send(bas)
        await send({"type": "http.response.body", "body": gov})

    async def uygulama(scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return None
        ip_ = (scope.get("client") or ("?", 0))[0]
        if izinli_aglar is not None:
            try:
                icinde = any(ipaddress.ip_address(ip_) in a for a in izinli_aglar)
            except ValueError:
                icinde = False
            if not icinde:
                depo.denetle("-", ip_, scope.get("path", ""), 403)
                return await yaz(send, 403, {"hata": "Yalniz Tailscale aginizdan erisilir."})
        yol = scope.get("path", "")
        if yol == "/uzak" or yol.startswith("/uzak/"):
            return await uzak_app(scope, receive, send)
        basliklar = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        token = token_al(basliklar.get("authorization", ""), basliklar.get("cookie", ""))
        sayfa = scope["method"] == "GET" and not yol.startswith("/api")

        async def red(durum: int, mesaj: str) -> None:
            depo.denetle("-", ip_, yol, durum)
            if sayfa:  # tarayici: eslesme sayfasina
                return await yaz(send, 302, {}, "/uzak/")
            return await yaz(send, durum, {"hata": mesaj})

        try:
            c = depo.dogrula(token)
        except UzakHata as e:
            return await red(e.kod, e.mesaj)
        if c.rol != "tam":
            return await red(403, "Bu cihazin rolu tam arayuze erisemez.")
        if not sinir.izin(c.id):
            return await red(429, "Istek siniri asildi.")
        kaynak = basliklar.get("origin") or ""
        if kaynak and urlsplit(kaynak).netloc != basliklar.get("host", ""):
            return await red(403, "Dis kaynakli istek reddedildi.")  # CSRF
        yeni_token = ""
        if c.son_kullanma - depo.saat() < 3 * 3600:  # sessiz yeniden baglanma: token dondur
            try:
                yeni_token = depo.yenile(token)["token"]
            except UzakHata:
                yeni_token = ""
        yeni = [(k, v) for k, v in scope["headers"] if k.decode("latin-1").lower() not in atla]
        yeni += [(b"host", b"127.0.0.1"), (b"x-yas-oturum", oturum_anahtari.encode()),
                 (b"x-yas-uzak-cihaz", c.id.encode())]  # fmt: skip
        ic = dict(scope, headers=yeni, client=("127.0.0.1", 0), scheme="http",
                  server=("127.0.0.1", 80))  # fmt: skip
        if yol.startswith("/api") or scope["method"] != "GET":
            depo.denetle(c.id, ip_, f"{scope['method']} {yol}", 0)

        async def gonder(mesaj: dict) -> None:
            if mesaj["type"] == "http.response.start" and yeni_token:
                h = [*mesaj.get("headers", []), (b"set-cookie", cerez(yeni_token).encode())]
                mesaj = dict(mesaj, headers=h)
            await send(mesaj)

        return await ana_app(ic, receive, gonder)

    return uygulama


class UzakSunucu:
    """Uzak sunucuyu ANA event loop'ta calistirir: ana uygulamanin asyncio nesneleri
    (gorevler, kilitler, akislar) baska bir loop'tan kullanilmaz."""

    def __init__(self) -> None:
        self.sunucu: Any = None
        self.gorev: Any = None
        self.adres = ""

    def acik_mi(self) -> bool:
        s = self.sunucu
        return s is not None and s.started and not s.should_exit

    async def ac(self, asgi: Any, port: int, cert: Path, key: Path, host: str) -> None:
        import asyncio
        import contextlib

        import uvicorn

        class _Sunucu(uvicorn.Server):
            @contextlib.contextmanager
            def capture_signals(self):  # Ctrl+C/sinyaller ana uygulamada kalir
                yield

        if self.acik_mi():
            return
        cfg = uvicorn.Config(asgi, host=host, port=port, ssl_certfile=str(cert),
                             ssl_keyfile=str(key), log_level="warning", lifespan="off")  # fmt: skip
        sunucu = self.sunucu = _Sunucu(cfg)

        async def _guvenli_serve() -> None:
            # uvicorn port alamayinca sys.exit(1) cagirir; asyncio SystemExit'i loop'tan disari
            # firlatip TUM uygulamayi kapatiyordu. Burada yutulur, ac() Turkce hata dondurur.
            with contextlib.suppress(SystemExit):
                await sunucu.serve()

        self.gorev = asyncio.create_task(_guvenli_serve())
        for _ in range(100):
            if self.sunucu.started or self.gorev.done():
                break
            await asyncio.sleep(0.05)
        if not self.sunucu.started:
            self.sunucu = None
            raise OSError(
                f"{host}:{port} dinlenemedi: port baska bir program (ya da acik baska bir Kairo)"
                " tarafindan kullaniliyor. Ayarlar'dan uzak erisim portunu degistirin."
            )
        self.adres = f"https://{host}:{port}/"

    async def kapat(self) -> None:
        import asyncio
        import contextlib

        if self.sunucu is not None:
            self.sunucu.should_exit = True
            if self.gorev is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self.gorev, 5)
        self.sunucu = None
