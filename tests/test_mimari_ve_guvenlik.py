"""Mimari ve guvenlik iyilestirmeleri testleri (M1-M5):
- Sabit/uygulayici model baglam penceresi (runner._baglam)
- Ic ice git deposu ve surucu sertlestirmesi (kum.git_komut_sertlestir)
- Codex ve Antigravity CLI izin koprusu (cc_izin + cli_ajan)
- Gunluk maliyet mtime onbellegi (yonlendirici.gunluk_maliyet_usd)
- Router modulerlestirmesi sonrasi API uc sayisi dogrulamasi
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.routing import APIRoute

from app.agent import cc_izin, cli_ajan, kum
from app.agent.policy import YanEtki
from app.agent.runner import AgentRunner, Run, RunDeposu
from app.agent.yetenek import ModelYetenegi
from app.services.oturumlar import Mesaj, OturumDeposu
from app.services.yonlendirici import _GUNLUK_ONBELLEK, gunluk_maliyet_usd


def _yet(model: str, saglayici: str, baglam: int) -> ModelYetenegi:
    return ModelYetenegi(
        model=model,
        saglayici=saglayici,
        araclar=True,
        json_cikti=True,
        goruntu=False,
        baglam=baglam,
        dusunme=False,
        tokenizer="tahmin",
    )


def test_sabit_model_baglami_aktif_modelden_ayri_hesaplanir(tmp_path: Path) -> None:
    depo = RunDeposu(tmp_path)
    runner = AgentRunner(
        depo,
        lambda _h: ("", [], {}),
        lambda _m=None: MagicMock(),
        yetenek=lambda: _yet("yerel-kucuk", "yerel", 8192),
    )
    runner.profil_yetenegi = lambda m: _yet(m, "openrouter", 131072 if "uygulayici" in m else 8192)
    normal = Run(hedef="test")
    sabit = Run(hedef="test", model="openrouter/uygulayici", model_sabit=True)
    kalici = Run(hedef="test", model="openrouter/uygulayici", ajan_id="aj1")
    assert runner._baglam(normal) == 8192
    assert runner._baglam(sabit) == 131072
    assert runner._baglam(kalici) == 131072
    assert runner._baglam(normal, "openrouter/uygulayici") == 131072


def test_git_komut_sertlestir_tum_protokol_ve_suruculeri_kapatir() -> None:
    ortam: dict[str, str] = {}
    kum.git_komut_sertlestir(ortam)
    sayac = int(ortam["GIT_CONFIG_COUNT"])
    ciftler = {ortam[f"GIT_CONFIG_KEY_{i}"]: ortam[f"GIT_CONFIG_VALUE_{i}"] for i in range(sayac)}
    assert ciftler["core.hooksPath"] in ("NUL", "/dev/null")
    assert ciftler["core.fsmonitor"] == "false"
    assert ciftler["core.sshCommand"] == "false"
    assert ciftler["core.gitProxy"] == "false"
    assert ciftler["core.editor"] == "false"
    assert ciftler["diff.external"] == ""
    assert ciftler["protocol.ext.allow"] == "never"
    assert ciftler["protocol.file.allow"] == "user"


def test_cli_izin_koprusu_codex_ve_antigravity(tmp_path: Path, monkeypatch) -> None:
    # Antigravity ve Codex arac adlarinin Kairo yan etkilerine cevrimi
    assert cc_izin.istek_cevir("read_file", {"Path": "C:/a.py"}).yan_etki is YanEtki.oku
    assert cc_izin.istek_cevir("apply_patch", {"path": "C:/a.py"}).yan_etki is YanEtki.yaz
    k1 = cc_izin.istek_cevir("run_command", {"CommandLine": "pytest -q"})
    assert (k1.yan_etki, k1.komut) == (YanEtki.komut, "pytest -q")
    k2 = cc_izin.istek_cevir("exec_command", {"cmd": ["npm", "test"]})
    assert (k2.yan_etki, k2.komut) == (YanEtki.komut, "npm test")
    assert cc_izin.istek_cevir("search_web", {"query": "kairo"}).yan_etki is YanEtki.ag

    # hook_cikti hem standart decision hem hookSpecificOutput doner
    cikti = cc_izin.hook_cikti(False, "engellendi")
    assert cikti["decision"] == "deny"
    assert cikti["hookSpecificOutput"]["permissionDecision"] == "deny"

    # Antigravity CLI tam yetki kapaliyken --settings alir
    monkeypatch.setattr(cli_ajan, "agy_yolu", lambda: "agy")
    komut = cli_ajan.komut_kur("antigravity", "merhaba", tmp_path, izin_koprusu=True)
    assert "--settings" in komut
    komut_tam = cli_ajan.komut_kur(
        "antigravity", "merhaba", tmp_path, izin_koprusu=True, tam_yetki=True
    )
    assert "--settings" not in komut_tam

    # Codex gecici CODEX_HOME hazirlama: auth/config kopyalanir, hooks.json birlestirilir
    kaynak = tmp_path / "kaynak_codex"
    kaynak.mkdir()
    (kaynak / "auth.json").write_text('{"token":"x"}', encoding="utf-8")
    (kaynak / "hooks.json").write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "echo 1"}]}]}}
        ),
        encoding="utf-8",
    )
    hedef = tmp_path / "hedef_codex"
    cc_izin.codex_home_hazirla(hedef, kaynak)
    assert (hedef / "auth.json").is_file()
    hooks = json.loads((hedef / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert len(hooks) == 2
    assert "cc_izin" in hooks[-1]["hooks"][0]["command"]


def test_gunluk_maliyet_onbellegi_degisince_yenilenir(tmp_path: Path, monkeypatch) -> None:
    _GUNLUK_ONBELLEK.clear()
    run_depo = RunDeposu(tmp_path)
    ot_depo = OturumDeposu(tmp_path)

    r1 = Run(hedef="g1")
    r1.kullanim.maliyet_usd = 0.25
    run_depo.kaydet(r1)

    ot = ot_depo.olustur()
    ot.mesajlar.append(Mesaj(rol="asistan", metin="ok", istatistik={"maliyet_usd": 0.15}))
    ot_depo.kaydet(ot)

    assert gunluk_maliyet_usd(run_depo, ot_depo) == 0.4

    # Dosyalar degismediginde liste() cagrilmadan onbellekten doner
    cagri_sayisi = 0
    orijinal_liste = run_depo.liste

    def sayan_liste():
        nonlocal cagri_sayisi
        cagri_sayisi += 1
        return orijinal_liste()

    monkeypatch.setattr(run_depo, "liste", sayan_liste)
    assert gunluk_maliyet_usd(run_depo, ot_depo) == 0.4
    assert cagri_sayisi == 0

    # Yeni gorev eklenince dizin imzasi degisir ve yeni toplam hesaplanir
    r2 = Run(hedef="g2")
    r2.kullanim.maliyet_usd = 0.35
    run_depo.kaydet(r2)
    assert gunluk_maliyet_usd(run_depo, ot_depo) == 0.75
    assert cagri_sayisi == 1


def test_router_modulerlestirme_uc_sayisi(app) -> None:
    api_rotalari = [r for r in app.routes if isinstance(r, APIRoute)]
    assert len(api_rotalari) >= 252
