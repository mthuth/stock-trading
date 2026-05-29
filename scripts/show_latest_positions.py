#!/usr/bin/env python3
"""Show the latest saved E*TRADE position snapshot."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_FILE = ROOT / "data" / "stock_trading.sqlite"


def money(value: object) -> str:
    if value is None:
        return "-"
    return f"${float(value):,.2f}"


def number(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.4g}"


def percent(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.2f}%"


def main() -> int:
    if not DB_FILE.exists():
        print(f"No database found at {DB_FILE}")
        return 1

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    run = conn.execute(
        """
        SELECT id, synced_at, environment, account_type, institution_type
        FROM etrade_sync_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not run:
        print("No E*TRADE sync runs saved yet.")
        return 1

    positions = conn.execute(
        """
        SELECT symbol, quantity, last_price, market_value, price_paid,
               total_gain, total_gain_pct, pct_of_portfolio
        FROM etrade_positions
        WHERE run_id = ?
        ORDER BY market_value DESC
        """,
        (run["id"],),
    ).fetchall()

    print(
        f"Latest run {run['id']} | {run['synced_at']} | "
        f"{run['environment']} | {run['account_type']} / {run['institution_type']}"
    )

    rows = [
        [
            row["symbol"],
            number(row["quantity"]),
            money(row["last_price"]),
            money(row["market_value"]),
            money(row["price_paid"]),
            money(row["total_gain"]),
            percent(row["total_gain_pct"]),
            percent(row["pct_of_portfolio"]),
        ]
        for row in positions
    ]
    headers = [
        "Symbol",
        "Qty",
        "Last",
        "Market Value",
        "Price Paid",
        "Total Gain",
        "Gain %",
        "Portfolio %",
    ]
    widths = [
        max(len(str(row[index])) for row in [headers] + rows)
        for index in range(len(headers))
    ]

    print()
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

