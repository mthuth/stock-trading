#!/usr/bin/env python3
"""Record user feedback for sources or recommendations."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import init_db  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record stock-engine feedback.")
    subparsers = parser.add_subparsers(dest="kind", required=True)

    source = subparsers.add_parser("source", help="Feedback on a research source")
    source.add_argument("source_name")
    source.add_argument("--symbol", default="")
    source.add_argument("--type", default="useful")
    source.add_argument("--delta", type=float, default=0.0)
    source.add_argument("--notes", default="")

    reco = subparsers.add_parser("recommendation", help="Feedback on a recommendation")
    reco.add_argument("symbol")
    reco.add_argument("--report-date", default="")
    reco.add_argument("--type", default="agree")
    reco.add_argument("--notes", default="")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = init_db()
    with conn:
        if args.kind == "source":
            conn.execute(
                """
                INSERT INTO source_feedback (
                    source_name, symbol, feedback_type, rating_delta, notes
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (args.source_name, args.symbol, args.type, args.delta, args.notes),
            )
            print(f"Recorded source feedback for {args.source_name}")
        else:
            conn.execute(
                """
                INSERT INTO recommendation_feedback (
                    report_date, symbol, feedback_type, notes
                )
                VALUES (?, ?, ?, ?)
                """,
                (args.report_date, args.symbol.upper(), args.type, args.notes),
            )
            print(f"Recorded recommendation feedback for {args.symbol.upper()}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

