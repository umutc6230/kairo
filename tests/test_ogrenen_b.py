"""Ogrenen sistem B: A-B-A-B dongusu, ayni hata farkli arguman ve yazma sonrasi koc notlari."""

from __future__ import annotations

from app.agent.runner import AYNI_HATA_KOC, Adim, AdimDurum, AgentRunner, Run


def _adim(no: int, arac: str, durum=AdimDurum.tamam, **arg) -> Adim:
    return Adim(no=no, arac=arac, argumanlar=arg, durum=durum)


def test_periyot_iki_ve_uc_dongu():
    run = Run(hedef="x")
    for i in range(4):  # A B A B A B A B
        run.adimlar += [_adim(2 * i, "oku", yol="a"), _adim(2 * i + 1, "ara", q="b")]
    assert AgentRunner._periyot_tekrari(run, _adim(99, "oku", yol="a")) >= 3
    run3 = Run(hedef="x")
    for i in range(2):
        run3.adimlar += [_adim(i, "a"), _adim(i, "b"), _adim(i, "c")]
    run3.adimlar += [_adim(9, "a"), _adim(9, "b")]
    assert AgentRunner._periyot_tekrari(run3, _adim(10, "c")) == 3


def test_periyot_yok_ilerleyen_ve_hatali():
    run = Run(hedef="x")
    run.adimlar = [_adim(i, "oku", yol=f"{i}.py") for i in range(6)]
    assert AgentRunner._periyot_tekrari(run, _adim(7, "oku", yol="7.py")) == 0
    run.adimlar = [_adim(0, "oku", yol="a"), _adim(1, "ara", AdimDurum.hata, q="b")] * 3
    assert AgentRunner._periyot_tekrari(run, _adim(9, "oku", yol="a")) == 0


def test_koc_ayni_hata_farkli_arguman_ve_yazma():
    run = Run(hedef="x")
    notlar = []
    for i in range(AYNI_HATA_KOC):
        a = _adim(i, "komut", AdimDurum.hata, k=f"pip install paket{i}")
        notlar.append(AgentRunner._koc(run, a, {"hata": f"No module named 'x{i}'"}).get("koc"))
    assert notlar[:-1] == [None] * (AYNI_HATA_KOC - 1) and "farkli argumanlarla" in notlar[-1]
    y = AgentRunner._koc(run, _adim(9, "proje_dosya_yaz", yol="a.py"), {"tamam": True})
    assert "dogrula" in y["koc"]
    assert "koc" not in AgentRunner._koc(run, _adim(10, "proje_dosya_oku"), {"metin": "x"})
