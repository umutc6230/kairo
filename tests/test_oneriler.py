"""Proaktif oneriler: DURUM.md maddeleri, insan bekleyen thread'ler, yaklasan rutinler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agent.workspaces import CalismaAlani
from app.agent.zamanlayici import Zamanlama
from app.services.oneriler import durum_maddeleri, oneriler


def test_durum_maddeleri_once_yarim(tmp_path):
    (tmp_path / "DURUM.md").write_text(
        "# D\n- [x] bitti\n- [ ] acik **is**\n  - [~] yarim `is`\n* [ ] ikinci\n", encoding="utf-8"
    )
    assert durum_maddeleri(str(tmp_path), 3) == ["yarim is", "acik is", "ikinci"]
    assert durum_maddeleri(str(tmp_path / "yok")) == []


def test_oneriler_sirasi_ve_suzme(tmp_path):
    (tmp_path / "DURUM.md").write_text("- [ ] testleri yaz\n", encoding="utf-8")
    simdi = datetime(2026, 11, 14, 12, tzinfo=UTC)
    alan = CalismaAlani(ad="Kairo", kokler=[str(tmp_path)])
    bos = CalismaAlani(ad="Bos", kokler=[])
    isler = [
        {"asama": "insan_bekliyor", "baslik": "Soru var", "proje_kok": str(tmp_path)},
        {"asama": "calisiyor", "baslik": "Arka planda"},
    ]
    yakin = Zamanlama(ad="Gunluk rapor", hedef="x", proje_kok=str(tmp_path), tur="aralik",
                      aralik_dk=60, baslangic=simdi.isoformat())  # fmt: skip
    uzak = Zamanlama(ad="Seneye", hedef="x", proje_kok=str(tmp_path), tur="bir_kez",
                     baslangic=(simdi + timedelta(days=30)).isoformat())  # fmt: skip
    kapali = yakin.model_copy(update={"ad": "Kapali", "aktif": False})
    r = oneriler([alan, bos], isler, [yakin, uzak, kapali], simdi)
    assert [(x["tur"], x["metin"]) for x in r] == [
        ("thread", "Soru var"),
        ("rutin", "Gunluk rapor"),
        ("durum", "testleri yaz"),
    ]
    assert r[2]["proje_id"] == alan.id


@pytest.mark.asyncio
async def test_oneriler_api(istemci):
    v = (await istemci.get("/api/oneriler")).json()
    assert isinstance(v["oneriler"], list)
