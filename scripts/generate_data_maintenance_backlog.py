#!/usr/bin/env python3
"""Generate review-only data maintenance backlog docs from local artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_trading.data_maintenance import (  # noqa: E402
    generate_data_maintenance_backlog,
    read_csv_rows,
    write_backlog_docs,
)


def read_text(path: str | Path) -> str:
    text_path = Path(path)
    if not text_path.exists():
        return ""
    return text_path.read_text(encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate docs-only data maintenance backlog work requests from local provider/source gap artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs",
        help="Directory where DATA_MAINTENANCE_BACKLOG.md and DATA_GAP_WORK_REQUESTS.md should be written.",
    )
    parser.add_argument(
        "--provider-gap-action-plan",
        default="reports/provider-gap-action-plan.md",
        help="Local provider gap action plan markdown to summarize, if present.",
    )
    parser.add_argument(
        "--provider-coverage-audit",
        default="reports/provider-coverage-audit.csv",
        help="Local provider coverage audit CSV to summarize, if present.",
    )
    parser.add_argument(
        "--research-source-integrations",
        default="config/research_source_integrations.csv",
        help="Configured research source integration CSV to inspect for not-implemented or missing-feed sources.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    action_plan_path = ROOT / args.provider_gap_action_plan
    coverage_path = ROOT / args.provider_coverage_audit
    integrations_path = ROOT / args.research_source_integrations

    backlog = generate_data_maintenance_backlog(
        provider_gap_action_plan_text=read_text(action_plan_path),
        provider_coverage_audit_rows=read_csv_rows(coverage_path),
        research_source_rows=read_csv_rows(integrations_path),
    )
    backlog_path, requests_path = write_backlog_docs(backlog, ROOT / args.output_dir)

    summary = backlog.get("summary", {}) if isinstance(backlog.get("summary"), dict) else {}
    print(f"Wrote {backlog_path}")
    print(f"Wrote {requests_path}")
    print(f"Work requests: {summary.get('total_work_requests', 0)}")
    print("GitHub issues created: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
