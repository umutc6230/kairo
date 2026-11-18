"""OpenTelemetry: env yokken no-op, varken OTLP/HTTP JSON span; ic ice, hata, gizli maske."""

from __future__ import annotations

import time

import pytest

from app.agent import telemetri


@pytest.fixture
def giden(monkeypatch):
    kayitlar: list = []
    monkeypatch.setattr(telemetri, "gonderici", lambda u, g, b: kayitlar.append((u, g, b)))
    return kayitlar


def _bekle(kayitlar: list, n: int) -> None:
    son = time.time() + 3
    while len(kayitlar) < n and time.time() < son:
        time.sleep(0.02)


def _span(kayit) -> dict:
    return kayit[1]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


def test_env_yoksa_hicbir_sey_gonderilmez(monkeypatch, giden) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    with telemetri.span("kairo.model", run="r1") as iz:
        iz["x"] = 1
    time.sleep(0.1)
    assert giden == []


def test_ic_ice_span_hata_ve_gizli_maske(monkeypatch, giden) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel:4318/")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "authorization=Bearer x, ekip=k")
    with (
        pytest.raises(ValueError),
        telemetri.span("kairo.model", run="r1", api_key="sk-gizli") as iz,
    ):
        iz["usage.cost"] = 0.25
        with telemetri.span("kairo.arac", arac="komut_calistir"):
            pass
        raise ValueError("bozuk")
    _bekle(giden, 2)
    url, _, basliklar = giden[0]
    assert url == "http://otel:4318/v1/traces"
    assert basliklar == {"authorization": "Bearer x", "ekip": "k"}
    ic, dis = sorted((_span(k) for k in giden), key=lambda s: s["name"])
    assert ic["name"] == "kairo.arac" and ic["parentSpanId"] == dis["spanId"]
    assert ic["traceId"] == dis["traceId"] and "parentSpanId" not in dis
    assert dis["status"]["code"] == 2 and "bozuk" in dis["status"]["message"]
    oz = {a["key"]: a["value"] for a in dis["attributes"]}
    assert oz["api_key"] == {"stringValue": "***"} and oz["usage.cost"] == {"doubleValue": 0.25}
    kaynak = giden[0][1]["resourceSpans"][0]["resource"]["attributes"][0]
    assert kaynak == {"key": "service.name", "value": {"stringValue": "kairo"}}
