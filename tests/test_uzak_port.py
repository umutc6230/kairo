import asyncio
import socket

from fastapi import FastAPI

from app import uzak


def test_dolu_port_uygulamayi_kapatmaz(tmp_path):
    """uvicorn dolu portta sys.exit(1) cagirir; bu SystemExit uygulamayi oldurmemeli."""
    cert, key, _ = uzak.sertifika(tmp_path, ["127.0.0.1"])
    with socket.socket() as dolu:
        dolu.bind(("127.0.0.1", 0))
        dolu.listen()
        port = dolu.getsockname()[1]

        async def dene():
            s = uzak.UzakSunucu()
            try:
                await s.ac(FastAPI(), port, cert, key, "127.0.0.1")
            except OSError as e:
                return str(e)
            return "acildi"

        sonuc = asyncio.run(dene())
    assert "kullaniliyor" in sonuc


def test_eski_8443_ayari_yeni_porta_tasinir():
    from app.services.ayarlar import UZAK_PORT
    from app.services.ayarlar import KullaniciAyarlari as Ayarlar

    assert Ayarlar().uzak_port == UZAK_PORT != 8443
    assert Ayarlar(uzak_port=8443).uzak_port == UZAK_PORT
    assert Ayarlar(uzak_port=9000).uzak_port == 9000
