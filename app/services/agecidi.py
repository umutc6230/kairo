"""Yerel sunucu (Ollama gibi): Studio'daki modelleri diger uygulamalara sunar.

Ayni portta (varsayilan 11434, Ollama'nin portu) iki dil konusur:
- Ollama API: GET /api/tags, POST /api/show, POST /api/chat, POST /api/generate, GET /api/ps,
  GET /api/version. Ollama destegi olan uygulamalar (GridMind "Local model (Ollama)") kod
  degistirmeden Studio'nun modellerini kullanir.
- OpenAI API: GET /v1/models, POST /v1/chat/completions (OpenRouter/OpenAI kullanan uygulamalar
  icin yalniz adres degisir, anahtar gerekmez).
Istenen model kapaliysa Studio acar ya da degistirir (ayni anda tek model; istekler sirayla).
Yalniz 127.0.0.1'e baglanir.
"""

from __future__ import annotations

import asyncio
import json
import socket
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from loguru import logger

from app import __version__
from app.exceptions import YerelLLMHatasi
from app.services.ayarlar import AyarDeposu
from app.services.model_yonetici import ModelYonetici
from app.services.yerel_llm import MODELLER

OLLAMA_SURUMU = "0.12.0"  # istemciler surum kontrol ederse uyumlu gorunsun
ZAMAN_ASIMI = httpx.Timeout(1800, connect=10)


def simdi_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def model_coz(ad: str | None, varsayilan: str) -> str | None:
    """'gemma4-e4b-heretic:latest' -> 'gemma4-e4b-heretic'; bos: varsayilan; bilinmeyen: None."""
    if not ad:
        return varsayilan
    temiz = ad.strip().split(":", 1)[0]
    return temiz if temiz in MODELLER else None


def _mime(b64: str) -> str:
    if b64.startswith("/9j/"):
        return "image/jpeg"
    if b64.startswith("UklGR"):
        return "image/webp"
    if b64.startswith("R0lGOD"):
        return "image/gif"
    return "image/png"


# ---------------- Ollama -> OpenAI ----------------
def ollama_mesajlari(mesajlar: list[dict]) -> list[dict]:
    """Ollama mesajlari (images: base64 listesi, tool_calls arguments nesne, kimliksiz) ->
    OpenAI mesajlari (image_url parcalari, arguments metin, tool_call_id eslesmesi)."""
    sonuc: list[dict] = []
    bekleyen: list[
        str
    ] = []  # son asistan mesajinin cagri kimlikleri (tool cevaplari sirayla eslesir)
    for n, m in enumerate(mesajlar):
        rol = m.get("role", "user")
        icerik: Any = m.get("content") or ""
        if m.get("images"):
            parcalar: list[dict] = [{"type": "text", "text": icerik}] if icerik else []
            for b64 in m["images"]:
                url = f"data:{_mime(b64)};base64,{b64}"
                parcalar.append({"type": "image_url", "image_url": {"url": url}})
            icerik = parcalar
        cikti: dict[str, Any] = {"role": rol, "content": icerik}
        if m.get("tool_calls"):
            cagrilar = []
            for i, c in enumerate(m["tool_calls"]):
                f = c.get("function") or {}
                arg = f.get("arguments", {})
                kimlik = c.get("id") or f"call_{n}_{i}"
                cagrilar.append(
                    {
                        "id": kimlik,
                        "type": "function",
                        "function": {
                            "name": f.get("name", ""),
                            "arguments": arg if isinstance(arg, str) else json.dumps(arg),
                        },
                    }
                )
            cikti["tool_calls"] = cagrilar
            bekleyen = [c["id"] for c in cagrilar]
        if rol == "tool":
            cikti["tool_call_id"] = m.get("tool_call_id") or (
                bekleyen.pop(0) if bekleyen else "call"
            )
        sonuc.append(cikti)
    return sonuc


def ollama_istegi(govde: dict, model: str) -> dict:
    """/api/chat govdesini llama-server'in OpenAI govdesine cevirir."""
    istek: dict[str, Any] = {
        "model": model,
        "messages": ollama_mesajlari(govde.get("messages", [])),
    }
    secenek = govde.get("options") or {}
    if (n := secenek.get("num_predict")) and n > 0:
        istek["max_tokens"] = n
    for anahtar in ("temperature", "top_p", "top_k", "seed", "stop"):
        if anahtar in secenek:
            istek[anahtar] = secenek[anahtar]
    bicim = govde.get("format")
    if isinstance(bicim, dict):
        istek["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "cikti", "schema": bicim},
        }
    elif bicim == "json":
        istek["response_format"] = {"type": "json_object"}
    if govde.get("tools"):
        istek["tools"] = govde["tools"]
    # Ollama'da dusunme istege bagli ("think"); verilmezse kapali (hizli cevap)
    istek["chat_template_kwargs"] = {"enable_thinking": bool(govde.get("think"))}
    return istek


def _cagrilari_ollama(cagrilar: list[dict]) -> list[dict]:
    sonuc = []
    for c in cagrilar or []:
        f = c.get("function") or {}
        arg = f.get("arguments") or "{}"
        try:
            arg = json.loads(arg) if isinstance(arg, str) else arg
        except json.JSONDecodeError:
            arg = {"_ham": arg}
        sonuc.append({"function": {"name": f.get("name", ""), "arguments": arg}})
    return sonuc


def openai_cevabi_ollama(cevap: dict, model: str, bas: float, alan: str = "message") -> dict:
    """llama-server cevabi -> Ollama /api/chat (alan='message') ya da /api/generate ('response')."""
    secim = (cevap.get("choices") or [{}])[0]
    m = secim.get("message") or {}
    z = cevap.get("timings") or {}
    u = cevap.get("usage") or {}
    sonuc: dict[str, Any] = {"model": f"{model}:latest", "created_at": simdi_iso()}
    if alan == "message":
        mesaj: dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
        if m.get("reasoning_content"):
            mesaj["thinking"] = m["reasoning_content"]
        if m.get("tool_calls"):
            mesaj["tool_calls"] = _cagrilari_ollama(m["tool_calls"])
        sonuc["message"] = mesaj
    else:
        sonuc["response"] = m.get("content") or ""
        if m.get("reasoning_content"):
            sonuc["thinking"] = m["reasoning_content"]
    sonuc |= {
        "done": True,
        "done_reason": "length" if secim.get("finish_reason") == "length" else "stop",
        "total_duration": int((time.perf_counter() - bas) * 1e9),
        "prompt_eval_count": u.get("prompt_tokens") or z.get("prompt_n") or 0,
        "eval_count": u.get("completion_tokens") or z.get("predicted_n") or 0,
        "eval_duration": int((z.get("predicted_ms") or 0) * 1e6),
    }
    return sonuc


def _sse_satirlari(metin: str) -> list[dict]:
    olaylar = []
    for satir in metin.splitlines():
        if satir.startswith("data: ") and satir != "data: [DONE]":
            try:
                olaylar.append(json.loads(satir[6:]))
            except json.JSONDecodeError:
                continue
    return olaylar


# ---------------- uygulama ----------------
def agecidi_uygulamasi(
    yonetici: ModelYonetici, ayarlar: AyarDeposu, kapat: Callable[[], None] | None = None
) -> FastAPI:
    app = FastAPI(title="Kairo sunucusu", version=__version__, docs_url=None, redoc_url=None)
    istatistik = {"istek": 0, "son": []}  # arayuzde "son istekler"

    def kaydet(yol: str, model: str | None, istemci: str) -> None:
        istatistik["istek"] += 1
        yeni = {"zaman": simdi_iso(), "yol": yol, "model": model, "istemci": istemci}
        istatistik["son"] = [yeni, *istatistik["son"]][:20]

    app.state.istatistik = istatistik

    def klasor() -> Path:
        return Path(ayarlar.oku().llm_dizin) / "models"

    def yuklu_modeller() -> list:
        return [p for p in MODELLER.values() if (klasor() / p.dosya).exists()]

    def yetenekler(p) -> list[str]:
        y = ["completion", "tools", "thinking"]
        if p.mmproj and (klasor() / p.mmproj).exists():
            y.append("vision")
        if p.ses:
            y.append("audio")
        return y

    def bulunamadi(ad: str | None) -> JSONResponse:
        return JSONResponse({"error": f"model '{ad}' not found"}, status_code=404)

    async def ileri(istek: dict, model: str) -> dict:
        """Modeli hazirlar (gerekirse acar/degistirir) ve llama-server'a akissiz istek atar."""
        async with yonetici.kullan(model) as llm:
            istek["model"] = model
            r = await llm._istemci.post(
                f"{llm.adres}/chat/completions", json=istek, timeout=ZAMAN_ASIMI
            )
            if r.status_code >= 400:
                raise YerelLLMHatasi(f"Yerel model hata dondu ({r.status_code}): {r.text[:300]}")
            return r.json()

    async def ileri_akis(istek: dict, model: str) -> AsyncIterator[dict]:
        istek |= {"model": model, "stream": True}
        async with (
            yonetici.kullan(model) as llm,
            llm._istemci.stream(
                "POST", f"{llm.adres}/chat/completions", json=istek, timeout=ZAMAN_ASIMI
            ) as r,
        ):
            if r.status_code >= 400:
                await r.aread()
                raise YerelLLMHatasi(f"Yerel model hata dondu ({r.status_code}): {r.text[:300]}")
            async for satir in r.aiter_lines():
                for olay in _sse_satirlari(satir):
                    yield olay

    # ---- genel ----
    @app.get("/")
    @app.head("/")
    async def kok() -> PlainTextResponse:
        return PlainTextResponse("Ollama is running (Kairo)")

    @app.get("/api/version")
    async def surum() -> dict:
        return {"version": OLLAMA_SURUMU, "yerel_ai_studio": __version__}

    @app.get("/api/tags")
    async def etiketler(request: Request) -> dict:
        kaydet("/api/tags", None, request.headers.get("user-agent", ""))
        liste = []
        for p in yuklu_modeller():
            dosyalar = [klasor() / d for d in (p.dosya, p.mmproj) if d and (klasor() / d).exists()]
            liste.append(
                {
                    "name": f"{p.anahtar}:latest",
                    "model": f"{p.anahtar}:latest",
                    "modified_at": datetime.fromtimestamp(
                        dosyalar[0].stat().st_mtime, UTC
                    ).isoformat(),
                    "size": sum(d.stat().st_size for d in dosyalar),
                    "digest": p.anahtar,
                    "details": {"format": "gguf", "family": p.ad, "quantization_level": "Q4"},
                }
            )
        return {"models": liste}

    @app.post("/api/show")
    async def goster(request: Request) -> Response:
        govde = await request.json()
        ad = govde.get("model") or govde.get("name")
        anahtar = model_coz(ad, ayarlar.oku().model)
        if not anahtar or not (klasor() / MODELLER[anahtar].dosya).exists():
            return bulunamadi(ad)
        p = MODELLER[anahtar]
        return JSONResponse(
            {
                "capabilities": yetenekler(p),
                "details": {"format": "gguf", "family": p.ad},
                "model_info": {
                    "general.name": p.ad,
                    "llama.context_length": ayarlar.oku().baglam_token,
                },
                "modelfile": f"# Kairo: {p.ad}",
            }
        )

    @app.get("/api/ps")
    async def calisanlar() -> dict:
        if not yonetici.yuklenen_model or yonetici.durum != "hazir":
            return {"models": []}
        return {
            "models": [
                {
                    "name": f"{yonetici.yuklenen_model}:latest",
                    "model": f"{yonetici.yuklenen_model}:latest",
                }
            ]
        }

    @app.post("/api/pull")
    @app.post("/api/delete")
    @app.post("/api/create")
    async def desteklenmiyor() -> JSONResponse:
        return JSONResponse(
            {"error": "Model indirme/silme Kairo'nun Modeller sayfasindan yapilir."},
            status_code=400,
        )

    async def ollama_sohbet(request: Request, alan: str) -> Response:
        govde = await request.json()
        ad = govde.get("model")
        anahtar = model_coz(ad, ayarlar.oku().model)
        kaydet(request.url.path, anahtar or ad, request.headers.get("user-agent", ""))
        if not anahtar:
            return bulunamadi(ad)
        if alan == "response":  # /api/generate: prompt + system + images -> mesajlar
            mesajlar = (
                [{"role": "system", "content": govde["system"]}] if govde.get("system") else []
            ) + [
                {
                    "role": "user",
                    "content": govde.get("prompt", ""),
                    "images": govde.get("images") or [],
                }
            ]
            govde = {**govde, "messages": mesajlar}
        istek = ollama_istegi(govde, anahtar)
        bas = time.perf_counter()
        if govde.get("stream", True) is False:
            try:
                cevap = await ileri(istek, anahtar)
            except YerelLLMHatasi as e:
                return JSONResponse({"error": str(e)}, status_code=503)
            return JSONResponse(openai_cevabi_ollama(cevap, anahtar, bas, alan))

        async def akis() -> AsyncIterator[bytes]:
            cagrilar: dict[int, dict] = {}
            son: dict = {}
            try:
                async for olay in ileri_akis(istek, anahtar):
                    if olay.get("timings"):
                        son = olay
                    for c in olay.get("choices", []):
                        d = c.get("delta") or {}
                        for tc in d.get("tool_calls") or []:
                            k = cagrilar.setdefault(
                                tc.get("index", 0), {"function": {"name": "", "arguments": ""}}
                            )
                            f = tc.get("function") or {}
                            k["function"]["name"] += f.get("name") or ""
                            k["function"]["arguments"] += f.get("arguments") or ""
                        parca: dict[str, Any] = {
                            "model": f"{anahtar}:latest",
                            "created_at": simdi_iso(),
                            "done": False,
                        }
                        if d.get("content") or d.get("reasoning_content"):
                            if alan == "message":
                                parca["message"] = {
                                    "role": "assistant",
                                    "content": d.get("content") or "",
                                }
                                if d.get("reasoning_content"):
                                    parca["message"]["thinking"] = d["reasoning_content"]
                            else:
                                parca["response"] = d.get("content") or ""
                            yield (json.dumps(parca, ensure_ascii=False) + "\n").encode()
                        if c.get("finish_reason"):
                            son["finish_reason"] = c["finish_reason"]
            except YerelLLMHatasi as e:
                yield (json.dumps({"error": str(e)}, ensure_ascii=False) + "\n").encode()
                return
            sahte_mesaj = {"content": "", "tool_calls": list(cagrilar.values())}
            sahte = {
                "choices": [{"message": sahte_mesaj, "finish_reason": son.get("finish_reason")}],
                "timings": son.get("timings") or {},
            }
            bitis = openai_cevabi_ollama(sahte, anahtar, bas, alan)
            if alan == "message" and not cagrilar:
                bitis["message"].pop("tool_calls", None)
            yield (json.dumps(bitis, ensure_ascii=False) + "\n").encode()

        return StreamingResponse(akis(), media_type="application/x-ndjson")

    @app.post("/api/chat")
    async def sohbet(request: Request) -> Response:
        return await ollama_sohbet(request, "message")

    @app.post("/api/generate")
    async def uret(request: Request) -> Response:
        return await ollama_sohbet(request, "response")

    # ---- OpenAI uyumlu ----
    @app.get("/v1/models")
    async def v1_modeller() -> dict:
        return {
            "object": "list",
            "data": [
                {
                    "id": p.anahtar,
                    "object": "model",
                    "owned_by": "yerel-ai-studio",
                    "type": "model",  # Anthropic /v1/models bicimi (Claude Code model kesfi)
                    "display_name": p.ad,
                    "name": p.ad,
                    "yetenekler": yetenekler(p),
                    "context_length": ayarlar.oku().baglam_token,
                }
                for p in yuklu_modeller()
            ],
        }

    @app.post("/v1/chat/completions")
    async def v1_sohbet(request: Request) -> Response:
        istek = await request.json()
        ad = istek.get("model")
        anahtar = model_coz(ad, ayarlar.oku().model)
        kaydet("/v1/chat/completions", anahtar or ad, request.headers.get("user-agent", ""))
        if not anahtar:
            return JSONResponse({"error": {"message": f"model '{ad}' not found"}}, status_code=404)
        # istemci dusunmeyi belirtmediyse kapali (Ollama/OpenAI istemcileri hizli cevap bekler)
        if "chat_template_kwargs" not in istek and "reasoning_effort" not in istek:
            istek["chat_template_kwargs"] = {"enable_thinking": False}
        if not istek.get("stream"):
            try:
                return JSONResponse(await ileri(istek, anahtar))
            except YerelLLMHatasi as e:
                return JSONResponse({"error": {"message": str(e)}}, status_code=503)

        async def akis() -> AsyncIterator[bytes]:
            try:
                async for olay in ileri_akis(istek, anahtar):
                    yield f"data: {json.dumps(olay, ensure_ascii=False)}\n\n".encode()
            except YerelLLMHatasi as e:
                hata = json.dumps({"error": {"message": str(e)}}, ensure_ascii=False)
                yield f"data: {hata}\n\n".encode()
            yield b"data: [DONE]\n\n"

        return StreamingResponse(akis(), media_type="text/event-stream")

    # ---- Anthropic uyumlu (Claude Code: ANTHROPIC_BASE_URL) ----
    def anthropic_hata(mesaj: str, tur: str, durum: int) -> JSONResponse:
        return JSONResponse(
            {"type": "error", "error": {"type": tur, "message": mesaj}}, status_code=durum
        )

    def anthropic_model(ad: str | None) -> str | None:
        """Claude Code arka plan isleri icin 'claude-...' adlari da gonderebilir: bilinmeyen ad
        acik modele (yoksa secili modele) gider; boylece gereksiz model degisimi olmaz."""
        if anahtar := model_coz(ad, ayarlar.oku().model):
            return anahtar
        if ad and ad.lower().startswith("claude"):
            return yonetici.yuklenen_model or ayarlar.oku().model
        return None

    def anthropic_duzenle(govde: dict) -> None:
        """Claude Code isteklerini yerel modele uygun hale getirir.
        - Dusunme yalniz acikca `enabled` istenirse acilir: Claude Code her istekte `adaptive`
          gonderir; kucuk yerel modelde dusunme cevabi dakikalarca uzatir.
        - Sistem mesajinin basindaki `x-anthropic-billing-header` blogu atilir: bazi surumlerde
          her istekte degisen `cch=` ozeti tasir ve llama-server'in onek onbellegini bozar
          (her tur ~5K token bastan islenir)."""
        if govde.get("thinking", {}).get("type") != "enabled":
            govde.pop("thinking", None)
            govde.setdefault("chat_template_kwargs", {"enable_thinking": False})
        sistem = govde.get("system")
        if isinstance(sistem, list):
            govde["system"] = [
                b
                for b in sistem
                if not str(b.get("text", "")).startswith("x-anthropic-billing-header")
            ]
        elif isinstance(sistem, str) and sistem.startswith("x-anthropic-billing-header"):
            govde["system"] = sistem.split("\n", 1)[1] if "\n" in sistem else ""

    async def anthropic_ileri(request: Request, yol: str) -> Response:
        govde = await request.json()
        ad = govde.get("model")
        anahtar = anthropic_model(ad)
        kaydet(yol, anahtar or ad, request.headers.get("user-agent", ""))
        if not anahtar:
            return anthropic_hata(f"model '{ad}' not found", "not_found_error", 404)
        govde["model"] = anahtar
        anthropic_duzenle(govde)
        if not govde.get("stream"):
            try:
                async with yonetici.kullan(anahtar) as llm:
                    r = await llm._istemci.post(f"{llm.kok}{yol}", json=govde, timeout=ZAMAN_ASIMI)
            except YerelLLMHatasi as e:
                return anthropic_hata(str(e), "api_error", 503)
            return Response(r.content, status_code=r.status_code, media_type="application/json")

        async def akis() -> AsyncIterator[bytes]:
            try:
                async with (
                    yonetici.kullan(anahtar) as llm,
                    llm._istemci.stream(
                        "POST", f"{llm.kok}{yol}", json=govde, timeout=ZAMAN_ASIMI
                    ) as r,
                ):
                    async for parca in r.aiter_bytes():  # Anthropic SSE olaylari aynen gecer
                        yield parca
            except YerelLLMHatasi as e:
                hata = json.dumps(
                    {"type": "error", "error": {"type": "api_error", "message": str(e)}}
                )
                yield f"event: error\ndata: {hata}\n\n".encode()

        return StreamingResponse(akis(), media_type="text/event-stream")

    @app.post("/v1/messages")
    async def anthropic_mesaj(request: Request) -> Response:
        return await anthropic_ileri(request, "/v1/messages")

    @app.post("/v1/messages/count_tokens")
    async def anthropic_say(request: Request) -> Response:
        return await anthropic_ileri(request, "/v1/messages/count_tokens")

    @app.post("/api/yerel/kapat")
    async def yerel_kapat() -> dict:
        """Arka plan (--sunucu) modunu kapatir; yalniz 127.0.0.1'den erisilir."""
        if kapat is None:
            return {"kapat": False, "neden": "Studio penceresi acik; pencereden kapatin."}
        asyncio.get_running_loop().call_later(0.3, kapat)
        return {"kapat": True}

    return app


# ---------------- sunucuyu ayni event loop'ta calistirma ----------------
def port_bos(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


async def portu_kim_kullaniyor(port: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get(f"http://127.0.0.1:{port}/api/version")
            v = r.json()
    except (httpx.HTTPError, ValueError):
        return "baska bir program"
    if "yerel_ai_studio" in v:
        return "arka planda calisan baska bir Kairo"
    if "version" in v:
        return f"Ollama (surum {v['version']})"
    return "baska bir program"


class AgGecidi:
    """Yerel sunucuyu UI sunucusuyla AYNI event loop'ta calistirir (ModelYonetici'nin kilidi ve
    HTTP istemcisi loop'a bagli; ayri thread'de calismaz)."""

    def __init__(self, uygulama: FastAPI) -> None:
        self.uygulama = uygulama
        self._sunucu: uvicorn.Server | None = None
        self._gorev: asyncio.Task | None = None
        self.port: int | None = None
        self.hata = ""

    @property
    def acik(self) -> bool:
        return bool(
            self._sunucu and self._sunucu.started and self._gorev and not self._gorev.done()
        )

    async def baslat(self, port: int) -> bool:
        await self.durdur()
        self.port, self.hata = port, ""
        if not port_bos(port):
            self.hata = f"{port} portu dolu: {await portu_kim_kullaniyor(port)}."
            logger.warning("Yerel sunucu baslamadi: {}", self.hata)
            return False
        self._sunucu = uvicorn.Server(
            uvicorn.Config(
                self.uygulama,
                host="127.0.0.1",
                port=port,
                log_level="warning",
                log_config=None,
                ws="none",
            )
        )
        sunucu = self._sunucu

        async def calis() -> None:
            try:
                await sunucu.serve()
            except SystemExit:  # uvicorn baglanamazsa sys.exit cagirir: UI'yi dusurmesin
                self.hata = f"{port} portu acilamadi."

        self._gorev = asyncio.create_task(calis())
        for _ in range(100):
            if sunucu.started or self._gorev.done():
                break
            await asyncio.sleep(0.05)
        if self.acik:
            logger.info("Yerel sunucu acik: http://127.0.0.1:{} (Ollama + OpenAI uyumlu)", port)
        return self.acik

    async def durdur(self) -> None:
        if self._sunucu and self._gorev and not self._gorev.done():
            self._sunucu.should_exit = True
            await asyncio.wait({self._gorev}, timeout=5)
        self._sunucu, self._gorev = None, None

    def durum(self) -> dict:
        adres = f"http://127.0.0.1:{self.port}" if self.port else ""
        return {
            "acik": self.acik,
            "port": self.port,
            "hata": self.hata,
            "ollama_adres": adres,
            "openai_adres": f"{adres}/v1" if adres else "",
            "istek_sayisi": self.uygulama.state.istatistik["istek"],
            "son_istekler": self.uygulama.state.istatistik["son"][:8],
        }
