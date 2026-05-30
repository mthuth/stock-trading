#!/usr/bin/env python3
"""Show recent provider coverage gaps."""

from __future__ import annotations

import sys
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import latest_provider_gaps  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Show recent provider coverage gaps.")
    parser.add_argument("--symbol", help="Restrict output to one ticker.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum provider gap rows to read.")
    args = parser.parse_args()

    rows = latest_provider_gaps(args.limit)
    if args.symbol:
        symbol = args.symbol.upper()
        rows = [row for row in rows if str(row["symbol"] or "").upper() == symbol]
    if not rows:
        print("No provider gaps recorded yet.")
        return 0

    headers = ["Refreshed", "Symbol", "Provider", "Field", "Status", "Message"]
    table = [
        [
            row["refreshed_at"],
            row["symbol"],
            row["provider"],
            row["field_name"],
            row["status"],
            row["message"][:90],
        ]
        for row in rows
    ]
    widths = [
        max(len(str(row[index])) for row in [headers] + table)
        for index in range(len(headers))
    ]

    print("Recent Provider Gaps")
    print()
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in table:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
