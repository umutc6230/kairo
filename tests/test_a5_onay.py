"""A5 E2E'de bulunan izin aciklari: tek seferlik onay tekrar kullaniliyordu; yazma onayi
yalniz yola bagliydi (onaylanan yamadan FARKLI bir degisiklik de geciyordu)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.araclar import AjanAracKaydi
from app.agent.checkpoints import CheckpointDeposu, dosya_hashi
from app.agent.policy import PolitikaMotoru
from app.agent.terminal import KomutServisi
from app.agent.workspaces import CalismaAlani, Guven, Mod
from app.exceptions import OnayGerekli


@pytest.fixture
def onayli(tmp_path: Path):
    kok = tmp_path / "proje"
    kok.mkdir()
    (kok / "a.py").write_bytes(b"x = 1\ny = 2\n")
    veri = tmp_path / "veri"
    veri.mkdir()
    alan = CalismaAlani(id="e" * 12, kokler=[str(kok)], guven=Guven.guvenilir, mod=Mod.onayli)
    politika = PolitikaMotoru(veri)
    kayit = AjanAracKaydi(alan, politika, CheckpointDeposu(veri), KomutServisi())
    return kok, politika, kayit


def _onayla(politika: PolitikaMotoru, fonk, *a, **kw):
    with pytest.raises(OnayGerekli) as bilgi:
        fonk(*a, **kw)
    politika.onaylar.karar_ver(bilgi.value.onay["id"], True)
    return fonk(*a, **kw)


def test_tek_seferlik_onay_ikinci_kez_kullanilamaz(onayli) -> None:
    kok, politika, kayit = onayli
    h = dosya_hashi(kok / "a.py")
    _onayla(politika, kayit.yazma.dosya_yama, "a.py", "x = 1", "x = 5", beklenen_hash=h)
    # AYNI islem tekrar (geri alinip yeniden denense bile) yeni onay ister
    (kok / "a.py").write_bytes(b"x = 1\ny = 2\n")
    with pytest.raises(OnayGerekli):
        kayit.yazma.dosya_yama("a.py", "x = 1", "x = 5", beklenen_hash=h)
    gecmis = {o["karar"] for o in politika.onaylar.gecmis()}
    assert "kullanildi" in gecmis


def test_yama_onayi_icerige_baglidir(onayli) -> None:
    kok, politika, kayit = onayli
    h = dosya_hashi(kok / "a.py")
    with pytest.raises(OnayGerekli) as bilgi:
        kayit.yazma.dosya_yama("a.py", "x = 1", "x = 5", beklenen_hash=h)
    politika.onaylar.karar_ver(bilgi.value.onay["id"], True)
    # ayni dosyaya FARKLI degisiklik: onaylanan yama bunu kapsamaz
    with pytest.raises(OnayGerekli):
        kayit.yazma.dosya_yama("a.py", "y = 2", "y = 999", beklenen_hash=h)
    assert (kok / "a.py").read_bytes() == b"x = 1\ny = 2\n"
    # onaylanan yamanin kendisi gecer
    kayit.yazma.dosya_yama("a.py", "x = 1", "x = 5", beklenen_hash=h)
    assert b"x = 5" in (kok / "a.py").read_bytes()


def test_yazma_onayi_icerige_baglidir(onayli) -> None:
    kok, politika, kayit = onayli
    with pytest.raises(OnayGerekli) as bilgi:
        kayit.yazma.dosya_yaz("yeni.txt", "zararsiz")
    politika.onaylar.karar_ver(bilgi.value.onay["id"], True)
    with pytest.raises(OnayGerekli):
        kayit.yazma.dosya_yaz("yeni.txt", "BASKA ICERIK")
    assert not (kok / "yeni.txt").exists()


def test_ayni_komut_her_seferinde_onay_ister(onayli) -> None:
    _, politika, kayit = onayli
    isl = kayit.isleyiciler()
    s = isl["komut_calistir"](komut="echo bir")
    assert s["karar"] == "onay_bekliyor"
    politika.onaylar.karar_ver(s["onay"]["id"], True)
    assert isl["komut_calistir"](komut="echo bir").get("cikis_kodu") == 0
    assert isl["komut_calistir"](komut="echo bir")["karar"] == "onay_bekliyor"


async def test_gorev_ekrani_dosyalari_sunulur(istemci) -> None:
    js = await istemci.get("/web/gorevler.js")
    assert js.status_code == 200 and "kacir" in js.text
    html = (await istemci.get("/")).text
    assert 'id="g-gorevler"' in html and 'data-git="gorevler"' in html


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node yok")
def test_arayuz_js_modul_olarak_ayristirilir() -> None:
    """Python yamalari JS dizesine gercek satir sonu sokmustu; node --check (CommonJS) kacirdi."""
    import subprocess

    web = Path(__file__).parent.parent / "app" / "web"
    for js in web.glob("*.js"):
        r = subprocess.run(
            ["node", "--input-type=module", "--check"],
            input=js.read_bytes(),
            capture_output=True,
            check=False,
        )
        assert r.returncode == 0, f"{js.name}: {r.stderr.decode(errors='replace')[:300]}"
