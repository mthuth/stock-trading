"""CLI implementation for report-context rendering."""

from __future__ import annotations

import argparse
from pathlib import Path

from stock_trading.presentation import load_report_context, render_report_context
from stock_trading.storage import REPORTS_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render dashboard/report artifacts from report context.")
    parser.add_argument("--fixture", required=True, help="Path to report-context JSON.")
    parser.add_argument(
        "--output-dir",
        default=str(REPORTS_DIR / "context-render"),
        help="Directory for rendered artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = load_report_context(Path(args.fixture))
    paths = render_report_context(context, Path(args.output_dir))
    for path in paths:
        print(f"Wrote {path}")
    return 0

