#!/usr/bin/env python3
"""Render the static local decision console shell."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.local_console import write_local_console  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a static local decision console from a manifest.")
    parser.add_argument(
        "--manifest",
        default="reports/local-console-manifest.json",
        help="Path to a local console manifest JSON file.",
    )
    parser.add_argument(
        "--report-context",
        help="Optional report-context JSON fallback used only when the manifest is missing.",
    )
    parser.add_argument(
        "--output",
        default="reports/local-console.html",
        help="Path to write the rendered local console HTML.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = write_local_console(
        manifest_path=Path(args.manifest),
        report_context_path=Path(args.report_context) if args.report_context else None,
        output_path=Path(args.output),
    )
    print(f"Rendered local decision console: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
