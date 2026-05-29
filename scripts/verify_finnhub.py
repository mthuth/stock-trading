#!/usr/bin/env python3
"""Verify which Finnhub endpoints the configured key can access."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import load_env  # noqa: E402


FINNHUB_BASE = "https://finnhub.io/api/v1"


def get_json(path: str, params: Mapping[str, object], api_key: str) -> tuple[str, str]:
    query = urlencode({**params, "token": api_key})
    request = Request(
        f"{FINNHUB_BASE}/{path}?{query}",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode()
            parsed = json.loads(payload) if payload else {}
            if isinstance(parsed, dict) and parsed.get("error"):
                return "blocked", str(parsed.get("error"))
            if parsed in ({}, [], None):
                return "empty", "Endpoint returned no data for this symbol/window"
            return "ok", summarize_payload(parsed)
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")[:240]
        return "blocked", f"HTTP {exc.code}: {body}"
    except (URLError, TimeoutError) as exc:
        return "error", str(exc)
    except json.JSONDecodeError as exc:
        return "error", f"JSON decode failed: {exc}"


def summarize_payload(payload: object) -> str:
    if isinstance(payload, list):
        return f"list rows={len(payload)}"
    if isinstance(payload, dict):
        keys = ", ".join(list(payload.keys())[:8])
        return f"object keys={keys}"
    return type(payload).__name__


def main() -> int:
    load_env()
    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        print("Missing FINNHUB_API_KEY in .env")
        return 1

    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "NVDA"
    today = date.today()
    from_date = today - timedelta(days=30)
    endpoints: Dict[str, tuple[str, Dict[str, object]]] = {
        "quote": ("quote", {"symbol": symbol}),
        "company_profile": ("stock/profile2", {"symbol": symbol}),
        "company_news": (
            "company-news",
            {"symbol": symbol, "from": from_date.isoformat(), "to": today.isoformat()},
        ),
        "news_sentiment": ("news-sentiment", {"symbol": symbol}),
        "recommendation_trends": ("stock/recommendation", {"symbol": symbol}),
        "price_target": ("stock/price-target", {"symbol": symbol}),
        "earnings_calendar": ("calendar/earnings", {"symbol": symbol}),
        "eps_estimates": ("stock/eps-estimate", {"symbol": symbol, "freq": "quarterly"}),
        "revenue_estimates": (
            "stock/revenue-estimate",
            {"symbol": symbol, "freq": "quarterly"},
        ),
        "upgrade_downgrade": ("stock/upgrade-downgrade", {"symbol": symbol}),
        "transcripts_list": ("stock/transcripts/list", {"symbol": symbol}),
    }

    print(f"Finnhub endpoint verification for {symbol}")
    print("Key loaded: yes")
    failures = 0
    for name, (path, params) in endpoints.items():
        status, detail = get_json(path, params, api_key)
        if status in {"blocked", "error"}:
            failures += 1
        print(f"{name}: {status} - {detail}")
    return 0 if failures < len(endpoints) else 1


if __name__ == "__main__":
    sys.exit(main())
