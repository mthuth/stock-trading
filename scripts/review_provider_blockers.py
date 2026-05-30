#!/usr/bin/env python3
"""Review provider blockers with decision-impact context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.analysis_engine import provider_blocker_review_rows  # noqa: E402
from stock_trading.storage import latest_provider_gaps  # noqa: E402


def row_value(row: object, key: str) -> str:
    try:
        return str(row[key] or "")  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        if isinstance(row, dict):
            return str(row.get(key) or "")
        return ""


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    widths = [
        max(len(str(row[index])) for row in [headers] + rows)
        for index in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Review active provider blockers and next actions.")
    parser.add_argument("--limit", type=int, default=15, help="Maximum blocker rows to show.")
    parser.add_argument("--symbol", help="Restrict review to one ticker.")
    args = parser.parse_args()

    provider_rows = latest_provider_gaps(limit=max(args.limit * 4, 50))
    if args.symbol:
        symbol = args.symbol.upper()
        provider_rows = [row for row in provider_rows if row_value(row, "symbol").upper() == symbol]

    rows = provider_blocker_review_rows(provider_rows, limit=args.limit)
    if not rows:
        print("No active provider blockers found.")
        return 0

    headers = ["Severity", "Symbol", "Provider", "Field", "Blocks", "Likely Cause", "Decision Context", "Latest Detail", "Next Action"]
    print("Provider Blocker Review")
    print()
    print_table(headers, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
