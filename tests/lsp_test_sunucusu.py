"""Testler icin minimal LSP sunucusu (Content-Length cerceveli). argv[1] == 'coz': initialize'dan
sonra ilk istekte coker. Davranis: definition = 'def <kelime>' satiri; references = kelimenin tum
gecisleri; documentSymbol = def/class satirlari; didOpen'da 'HATA' iceren satirlar icin tani."""

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

COZ = len(sys.argv) > 1 and sys.argv[1] == "coz"
giris, cikis = sys.stdin.buffer, sys.stdout.buffer
belgeler: dict[str, str] = {}


def ARALIK(i):  # noqa: N802
    return {"start": {"line": i, "character": 0}, "end": {"line": i, "character": 1}}


def oku():
    uzunluk = 0
    while True:
        s = giris.readline()
        if not s:
            sys.exit(0)
        if s in (b"\r\n", b"\n"):
            break
        if s.lower().startswith(b"content-length:"):
            uzunluk = int(s.split(b":")[1])
    return json.loads(giris.read(uzunluk))


def yaz(m):
    g = json.dumps(m).encode()
    cikis.write(b"Content-Length: %d\r\n\r\n" % len(g) + g)
    cikis.flush()


def kelime(metin, satir, sutun):
    s = metin.splitlines()[satir]
    return next(m.group(0) for m in re.finditer(r"\w+", s) if m.start() <= sutun <= m.end())


def konum(uri, satir, sutun):
    return {
        "uri": uri,
        "range": {
            "start": {"line": satir, "character": sutun},
            "end": {"line": satir, "character": sutun},
        },
    }


while True:
    m = oku()
    yontem, params = m.get("method"), m.get("params") or {}
    if yontem == "initialize":
        yaz({"jsonrpc": "2.0", "id": m["id"], "result": {"capabilities": {}}})
        # sunucudan istemciye istek: istemci cevaplamazsa takilir
        yaz({"jsonrpc": "2.0", "id": 9999, "method": "workspace/configuration", "params": {}})
        continue
    if COZ and "id" in m:
        sys.exit(5)
    if yontem == "textDocument/didOpen":
        d = params["textDocument"]
        belgeler[d["uri"]] = d["text"]
        tanilar = [{"range": ARALIK(i),
                    "message": "HATA bulundu", "severity": 1}
                   for i, s in enumerate(d["text"].splitlines()) if "HATA" in s]  # fmt: skip
        yaz({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
             "params": {"uri": d["uri"], "diagnostics": tanilar}})  # fmt: skip
        continue
    if "id" not in m or not yontem:  # bildirim ya da istemcinin bize cevabi
        continue
    uri = params.get("textDocument", {}).get("uri", "")
    metin = belgeler.get(uri) or Path(url2pathname(unquote(urlsplit(uri).path))).read_text("utf-8")
    sonuc = None
    if yontem in ("textDocument/definition", "textDocument/references"):
        p = params["position"]
        k = kelime(metin, p["line"], p["character"])
        satirlar = metin.splitlines()
        if yontem.endswith("definition"):
            sonuc = [konum(uri, i, s.index(k)) for i, s in enumerate(satirlar) if f"def {k}" in s]
            sonuc.append(konum("file:///C:/proje-disi/gizli.py", 0, 0))  # filtrelenmeli
        else:
            sonuc = [konum(uri, i, mm.start()) for i, s in enumerate(satirlar)
                     for mm in re.finditer(rf"\b{k}\b", s)]  # fmt: skip
    elif yontem == "textDocument/documentSymbol":
        sonuc = [{"name": mm.group(2), "kind": 12 if mm.group(1) == "def" else 5,
                  "range": ARALIK(i)}
                 for i, s in enumerate(metin.splitlines())
                 if (mm := re.match(r"\s*(def|class) (\w+)", s))]  # fmt: skip
    yaz({"jsonrpc": "2.0", "id": m["id"], "result": sonuc})
