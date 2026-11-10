"""E2E icin betikli sahte OpenAI uyumlu model sunucusu (yalniz 127.0.0.1).
Kullanim: python sahte_model.py <port> <pytest komutu>"""

import json
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
PYTEST = sys.argv[2]


def cagri(ad, **arg):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": uuid.uuid4().hex[:8],
                "type": "function",
                "function": {"name": ad, "arguments": json.dumps(arg)},
            }
        ],
    }


def sonraki(mesajlar):
    tool = [m for m in mesajlar if m.get("role") == "tool"]
    if not tool:
        return cagri(
            "plan_guncelle", adimlar=[{"baslik": "Hatayi bul"}, {"baslik": "Duzelt ve test et"}]
        )
    son = json.loads(tool[-1]["content"])
    if "adim_sayisi" in son:
        return cagri("proje_dosya_oku", yol="src/hesap.py")
    if "icerik" in son and "hash" in son:
        return cagri(
            "proje_dosya_yama",
            yol="src/hesap.py",
            eski_metin="a - b",
            yeni_metin="a + b",
            beklenen_hash=son["hash"],
        )
    if "yeni_hash" in son or "degisen" in son:
        return cagri("komut_calistir", komut=PYTEST, timeout=120)
    if "cikis_kodu" in son:
        return cagri(
            "gorevi_bitir", ozet="topla duzeltildi; test gecti.", kanit_adimlari=[son["adim"]]
        )
    return {"role": "assistant", "content": f"Beklenmeyen durum: {str(son)[:200]}"}


class H(BaseHTTPRequestHandler):
    def _json(self, veri, kod=200):
        b = json.dumps(veri).encode()
        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            return self._json({"status": "ok"})
        return self._json(
            {"data": [{"id": "deepseek-heretic"}], "models": [{"name": "deepseek-heretic"}]}
        )

    def do_POST(self):  # noqa: N802
        govde = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/tokenize"):
            return self._json({"tokens": [0] * (len(govde.get("content", "")) // 3)})
        mesaj = sonraki(govde.get("messages", []))
        return self._json({"choices": [{"message": mesaj, "finish_reason": "stop"}], "timings": {}})

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
