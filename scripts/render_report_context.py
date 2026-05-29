#!/usr/bin/env python3
"""Render UX artifacts from a saved report-context JSON file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from presentation import load_report_context, render_report_context  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render dashboard/report artifacts from report context.")
    parser.add_argument("--fixture", required=True, help="Path to report-context JSON.")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "reports" / "context-render"),
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


if __name__ == "__main__":
    sys.exit(main())

