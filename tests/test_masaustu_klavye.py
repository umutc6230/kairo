import sys

import pytest

from app.agent.masaustu import TUR, _pano_oku, _pano_yaz


def test_belge_turu_listede():
    assert TUR[50030] == "belge"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows panosu")
def test_pano_gidis_donus():
    eski = _pano_oku()
    try:
        assert _pano_yaz("Kairo şğüİ 😀")
        assert _pano_oku() == "Kairo şğüİ 😀"
    finally:
        if eski is not None:
            _pano_yaz(eski)
