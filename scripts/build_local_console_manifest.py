#!/usr/bin/env python3
"""Build the read-only local decision-console manifest JSON."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.local_console_manifest import write_local_console_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory containing existing report artifacts. Defaults to reports/.",
    )
    parser.add_argument(
        "--report-context",
        default="",
        help="Optional report-context JSON path. Defaults to latest reports/report-context-*.json.",
    )
    parser.add_argument(
        "--output",
        default="reports/local-console-manifest.json",
        help="Manifest output path. Defaults to reports/local-console-manifest.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = write_local_console_manifest(
        Path(args.output),
        reports_dir=Path(args.reports_dir),
        report_context_path=Path(args.report_context) if args.report_context else None,
    )
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
