"""OpenTelemetry izleme (Claude Code OTel karsiligi), ek bagimlilik olmadan.

`OTEL_EXPORTER_OTLP_ENDPOINT` tanimliysa span'ler OTLP/HTTP JSON olarak `{endpoint}/v1/traces`
adresine arka plan is parcaciginda gonderilir; tanimli degilse `span()` hicbir sey yapmaz.
Baglanti: runner model cagrisi ve arac adimini `with span("kairo.model", ...)` ile sarar.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import re
import secrets
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
from loguru import logger

GIZLI = re.compile(r"key|token|secret|sifre|parola|password|anahtar", re.I)
_UST: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar("otel", default=None)


def _gonder_http(url: str, govde: dict, basliklar: dict) -> None:
    try:
        httpx.post(url, json=govde, headers=basliklar, timeout=5.0)
    except httpx.HTTPError as e:  # izleme asla ana akisi bozmaz
        logger.debug("OTel gonderilemedi: {}", e)


# testler degistirir: (url, govde, basliklar) -> None
gonderici: Callable[[str, dict, dict], None] = _gonder_http


def _basliklar() -> dict:
    ham = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
    return {k.strip(): v.strip() for k, _, v in (p.partition("=") for p in ham.split(",")) if k}


def _deger(v: Any) -> dict:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)[:1000]}


def _oznitelikler(oz: dict) -> list[dict]:
    return [
        {"key": k, "value": _deger("***" if GIZLI.search(k) else v)}
        for k, v in oz.items()
        if v is not None
    ]


@contextlib.contextmanager
def span(ad: str, **oznitelik: Any) -> Iterator[dict]:
    """Bir islemi izler. Donen sozluge sonradan oznitelik eklenebilir (or. token sayisi)."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
    if not endpoint:
        yield oznitelik  # no-op: env yoksa sifir maliyet
        return
    ust = _UST.get()
    trace_id = ust[0] if ust else secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    belirtec = _UST.set((trace_id, span_id))
    bas = time.time_ns()
    hata = ""
    try:
        yield oznitelik
    except BaseException as e:
        hata = f"{type(e).__name__}: {e}"[:300]
        raise
    finally:
        _UST.reset(belirtec)
        kayit = {
            "traceId": trace_id,
            "spanId": span_id,
            "name": ad,
            "kind": 1,
            "startTimeUnixNano": str(bas),
            "endTimeUnixNano": str(time.time_ns()),
            "attributes": _oznitelikler(oznitelik),
            "status": {"code": 2, "message": hata} if hata else {"code": 1},
        }
        if ust:
            kayit["parentSpanId"] = ust[1]
        govde = {"resourceSpans": [{
            "resource": {"attributes": _oznitelikler({"service.name": "kairo"})},
            "scopeSpans": [{"scope": {"name": "kairo"}, "spans": [kayit]}],
        }]}  # fmt: skip
        threading.Thread(
            target=gonderici, args=(f"{endpoint}/v1/traces", govde, _basliklar()), daemon=True
        ).start()
