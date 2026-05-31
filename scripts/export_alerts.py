#!/usr/bin/env python3
"""Export fixture/local alert rows to review-only JSON and Markdown artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.alert_artifacts import write_alert_artifacts  # noqa: E402


def parser() -> argparse.ArgumentParser:
    arg_parser = argparse.ArgumentParser(
        description="Export local review-only alert artifacts from a fixture JSON file."
    )
    arg_parser.add_argument("--fixture", required=True, help="Path to local alert fixture JSON.")
    arg_parser.add_argument("--output-dir", required=True, help="Directory for alert JSON/Markdown artifacts.")
    arg_parser.add_argument("--basename", default="alerts", help="Output basename without extension.")
    arg_parser.add_argument("--report-date", default=None, help="Optional report date metadata override.")
    arg_parser.add_argument("--generated-at", default=None, help="Optional generated timestamp metadata override.")
    return arg_parser


def main() -> int:
    args = parser().parse_args()
    fixture_path = Path(args.fixture)
    source = json.loads(fixture_path.read_text())
    result = write_alert_artifacts(
        source,
        args.output_dir,
        basename=args.basename,
        report_date=args.report_date,
        generated_at=args.generated_at,
    )
    print(result["json_path"])
    print(result["markdown_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
