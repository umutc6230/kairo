"""Ogrenen sistem E: Antigravity CLI saglayicisi (komut + stream-json olaylari)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent import cli_ajan as ca


def test_agy_komutu_yetki_ve_oturum(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "agy_yolu", lambda: "agy.exe")
    k = ca.komut_kur("antigravity", "testleri duzelt", tmp_path, ek_sistem="KURAL")
    assert k[:2] == ["agy.exe", "-p"] and k[2].startswith("KURAL") and "accept-edits" in k
    assert "--dangerously-skip-permissions" not in k and "--conversation" not in k
    k = ca.komut_kur("antigravity", "devam", tmp_path, oturum="c1", tam_yetki=True, model="m")
    assert k[2] == "devam" and "--dangerously-skip-permissions" in k
    assert k[k.index("--conversation") + 1] == "c1" and k[k.index("--model") + 1] == "m"
    monkeypatch.setattr(ca, "agy_yolu", lambda: None)
    with pytest.raises(RuntimeError, match="agy"):
        ca.komut_kur("antigravity", "x", Path("."))


def test_agy_olaylari():
    s = ca.CliSonuc()
    for e in [
        {"event": "init", "conversation_id": "c9"},
        {"event": "step_update", "step_update": {"step_type": "tool", "state": "DONE",
         "tool_name": "read_file", "tool_info": {"parameters": {"Path": "a.py"}}}},
        {"event": "step_update", "step_update": {"step_type": "tool", "state": "ACTIVE",
         "tool_name": "x"}},
        {"event": "result", "result": {"conversation_id": "c9", "status": "SUCCESS",
         "response": "bitti"}},
    ]:  # fmt: skip
        ca.olay_isle("antigravity", e, s)
    assert (s.oturum, s.durum, s.ozet) == ("c9", "basarili", "bitti")
    assert len(s.log) == 1 and "read_file" in s.log[0]

    r = ca.CliSonuc()
    sonuc = {"status": "SUCCESS", "response": "", "denied_actions": [{"action": "read_file"}]}
    ca.olay_isle("antigravity", {"event": "result", "result": sonuc}, r)
    assert r.durum == "basarisiz" and "read_file" in r.ozet and "Tam yetki" in r.ozet
