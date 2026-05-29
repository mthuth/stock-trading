"""CLI implementation for analysis-only runs."""

from __future__ import annotations

import argparse
import json

from stock_trading.analysis import run_analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run recommendation analysis only.")
    parser.add_argument("--no-persist", action="store_true", help="Compute context without writing analysis/recommendation rows.")
    parser.add_argument("--no-context", action="store_true", help="Do not write the analysis context JSON artifact.")
    parser.add_argument("--report-date", help="Override report date.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = run_analysis(
        persist=not args.no_persist,
        write_context=not args.no_context,
        report_date=args.report_date,
    )
    print(
        json.dumps(
            {
                "analysis_run_id": context["metadata"].get("analysis_run_id"),
                "recommendation_run_id": context["metadata"].get("recommendation_run_id"),
                "recommendations": len(context.get("recommendations", [])),
                "top_symbol": context.get("summary", {}).get("top_symbol"),
            },
            indent=2,
        )
    )
    return 0

