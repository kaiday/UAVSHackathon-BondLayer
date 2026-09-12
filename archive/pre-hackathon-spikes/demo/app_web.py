"""Judge-facing merchant network console.

    python app_web.py  ->  http://127.0.0.1:8080

The page runs the same localhost merchant network in plain and extended UCP
modes. It is deterministic and offline by default; no model key is needed.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agentbridge.evaluation import run_case, run_repeats, scoreboard, visibility
from agentbridge.merchant_network import serve_network, stop_network

INDEX = Path(__file__).resolve().parent / "app" / "index.html"
PORT = 8080
REQUEST = "Find me a good 65W USB-C GaN wall charger under $45"
NETWORK_URLS: dict[str, str] = {}
NETWORK_SERVERS = []


def _record(extended: bool) -> dict:
    return run_case(NETWORK_URLS, REQUEST, extended=extended,
                    run_id="web-after" if extended else "web-before")


def api_state(extended: bool) -> dict:
    record = _record(extended)
    return {
        "request": REQUEST,
        "condition": record["condition"],
        "record": record,
        "visibility": visibility(record, "harbor-tech"),
        "scoreboard": scoreboard(record),
    }


def api_repeats() -> dict:
    records, metrics = run_repeats(NETWORK_URLS, REQUEST, 5)
    return {"records": records, "metrics": metrics}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, value: dict, status: int = 200) -> None:
        self._send(json.dumps(value).encode("utf-8"), "application/json", status)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send(INDEX.read_bytes(), "text/html; charset=utf-8")
            return
        if url.path == "/api/state":
            extended = parse_qs(url.query).get("extended", ["0"])[0] == "1"
            self._json(api_state(extended))
            return
        if url.path == "/api/repeats":
            self._json(api_repeats())
            return
        self._json({"error": "not found"}, 404)


def main() -> None:
    global NETWORK_URLS, NETWORK_SERVERS
    NETWORK_URLS, NETWORK_SERVERS = serve_network()
    print(f"BondLayer console on http://127.0.0.1:{PORT}")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    finally:
        stop_network(NETWORK_SERVERS)


if __name__ == "__main__":
    main()
