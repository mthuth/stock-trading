#!/usr/bin/env python3
"""Record a manual decision/trade journal entry.

This script records user-entered decisions made outside the app. It does not
place trades, preview orders, or call broker APIs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.manual_trade_journal import ACTION_TAKEN_VALUES, record_manual_journal_entry  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a manual stock decision/trade journal entry.")
    parser.add_argument("symbol", help="Ticker symbol reviewed or acted on outside the app.")
    parser.add_argument("action_taken", choices=sorted(ACTION_TAKEN_VALUES))
    parser.add_argument("--decision-date", default=date.today().isoformat())
    parser.add_argument("--amount", type=float)
    parser.add_argument("--shares", type=float)
    parser.add_argument("--price", type=float)
    parser.add_argument("--rationale", default="")
    parser.add_argument("--recommendation-run-id", type=int)
    parser.add_argument("--report-date", default="")
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def main() -> int:
    result = record_manual_journal_entry(vars(parse_args()))
    print(result["message"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
