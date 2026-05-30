#!/usr/bin/env python3
"""Serve generated reports with a local feedback-save endpoint."""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.feedback import recent_feedback, record_feedback  # noqa: E402


def handle_feedback_payload(payload: dict[str, object]) -> dict[str, object]:
    saved = record_feedback(payload)
    return {"ok": True, "feedback": saved, "recent": recent_feedback()}


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, directory: str | None = None, **kwargs: object) -> None:
        super().__init__(*args, directory=directory or str(ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/feedback/recent":
            self.write_json({"ok": True, "records": recent_feedback()})
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/feedback":
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return
        try:
            self.write_json(handle_feedback_payload(self.read_json()))
        except Exception as exc:  # noqa: BLE001 - endpoint returns a user-facing failure.
            self.write_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        if length > 20_000:
            raise ValueError("Feedback payload is too large.")
        raw = self.rfile.read(length).decode("utf-8")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Feedback payload must be a JSON object.")
        return value

    def write_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the stock dashboard with local feedback saving.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8892)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), lambda *handler_args, **kwargs: DashboardRequestHandler(*handler_args, directory=str(ROOT), **kwargs))
    print(f"Serving dashboard reports at http://{args.host}:{args.port}/reports/")
    print("Feedback endpoint: POST /feedback")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
