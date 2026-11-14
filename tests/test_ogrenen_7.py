"""Ogrenen sistem 7: arastirma ozeti sozlesmesi ajan ve sohbet talimatinda."""

from app.agent.runner import SISTEM
from app.services.sohbet_araclari import AJAN_NOTU


def test_arastirma_sozlesmesi():
    for metin in (SISTEM, AJAN_NOTU):
        for parca in ("kaynak URL", "API", "surum", "uydurma"):
            assert parca in metin, parca
