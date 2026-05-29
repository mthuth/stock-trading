#!/usr/bin/env python3
"""Run the daily stock research workflow."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    RESEARCH_FILE,
    finish_workflow_run,
    finish_workflow_step,
    read_csv,
    start_workflow_run,
    start_workflow_step,
)


def step_name_for(cmd: list[str]) -> str:
    if len(cmd) > 1 and cmd[1].startswith("scripts/"):
        return Path(cmd[1]).stem
    return Path(cmd[0]).stem


def has_any_core_price_data() -> bool:
    rows, _ = read_csv(RESEARCH_FILE)
    for row in rows:
        try:
            if float(row.get("current_price") or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def run(cmd: list[str], workflow_run_id: int | None = None, required: bool = True) -> int:
    print(f"\n$ {' '.join(cmd)}")
    step_run_id = start_workflow_step(
        workflow_run_id,
        step_name_for(cmd),
        cmd,
        required=required,
    )
    env = {**os.environ}
    if workflow_run_id is not None:
        env["STOCK_ENGINE_WORKFLOW_RUN_ID"] = str(workflow_run_id)
    status = subprocess.call(cmd, cwd=ROOT, env=env)
    finish_workflow_step(
        step_run_id,
        "ok" if status == 0 else "failed",
        exit_code=status,
        message="" if status == 0 else f"exit={status}",
    )
    return status


def should_continue_after_refresh_failure(status: int) -> bool:
    if status == 0:
        return True
    return has_any_core_price_data()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily stock-engine workflow.")
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Generate reports without calling market-data providers.",
    )
    parser.add_argument(
        "--show-gaps",
        action="store_true",
        help="Print provider gaps after report generation.",
    )
    parser.add_argument(
        "--ingest-evidence",
        action="store_true",
        help="Run all configured evidence ingestion before report generation.",
    )
    parser.add_argument(
        "--ingest-free-data",
        action="store_true",
        help="Run the free-first V1.6 ingestion bundle: SEC, IR, Alpha/FMP access checks, public feeds, price history, tagging, and score-signal curation.",
    )
    parser.add_argument(
        "--ingest-finnhub",
        action="store_true",
        help="Run Finnhub evidence ingestion before report generation.",
    )
    parser.add_argument(
        "--ingest-sec",
        action="store_true",
        help="Run SEC evidence ingestion before report generation.",
    )
    parser.add_argument(
        "--ingest-ir",
        action="store_true",
        help="Run official company investor-relations evidence ingestion before report generation.",
    )
    parser.add_argument(
        "--ingest-public-feeds",
        action="store_true",
        help="Run approved public podcast/newsletter RSS/archive ingestion before report generation.",
    )
    parser.add_argument(
        "--tag-evidence",
        action="store_true",
        help="Tag broad research evidence to stock symbols before report generation.",
    )
    parser.add_argument(
        "--ingest-price-history",
        action="store_true",
        help="Run daily price-history ingestion before report generation.",
    )
    parser.add_argument(
        "--curate-score-signals",
        action="store_true",
        help="Curate shadow score signals from stored raw/curated data before report generation.",
    )
    parser.add_argument(
        "--score-shadow",
        action="store_true",
        help="Show shadow score signals in the report without changing official scores.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workflow_run_id = start_workflow_run("daily", [sys.executable, "scripts/run_daily.py", *sys.argv[1:]])
    refreshed_market_data = False
    warnings: list[str] = []
    final_status = 1

    try:
        should_ingest_research_depth = args.ingest_evidence or args.ingest_free_data or args.ingest_finnhub
        should_ingest_finnhub = args.ingest_evidence or args.ingest_finnhub
        should_ingest_sec = args.ingest_evidence or args.ingest_free_data or args.ingest_sec
        should_ingest_ir = args.ingest_evidence or args.ingest_free_data or args.ingest_ir
        should_ingest_public_feeds = args.ingest_evidence or args.ingest_free_data or args.ingest_public_feeds
        should_tag_evidence = args.ingest_evidence or args.ingest_free_data or args.tag_evidence
        should_curate_score_signals = (
            args.ingest_evidence
            or args.ingest_free_data
            or args.curate_score_signals
            or args.score_shadow
        )
        should_ingest_any_evidence = (
            should_ingest_finnhub
            or should_ingest_research_depth
            or should_ingest_sec
            or should_ingest_ir
            or should_ingest_public_feeds
            or should_tag_evidence
            or should_curate_score_signals
        )

        if args.ingest_price_history or args.ingest_free_data:
            status = run(
                [sys.executable, "scripts/ingest_price_history.py"],
                workflow_run_id,
                required=False,
            )
            if status != 0:
                warnings.append("Price-history ingestion failed; continuing with existing history.")

        should_refresh_market_data = should_ingest_any_evidence and not args.skip_refresh and not args.ingest_free_data
        if should_refresh_market_data:
            # Prioritize quote and analyst-target calls before optional FMP
            # news/transcript checks consume the same provider call budget.
            status = run([sys.executable, "scripts/refresh_market_data.py"], workflow_run_id)
            if status != 0:
                if should_continue_after_refresh_failure(status):
                    warnings.append(
                        "Market-data refresh failed; continuing with existing price data and recorded gaps."
                    )
                else:
                    final_status = status
                    finish_workflow_run(
                        workflow_run_id,
                        "failed",
                        message="Market-data refresh failed and no usable price data exists.",
                        summary="; ".join(warnings),
                        error_class="missing_core_price_data",
                    )
                    return status
            else:
                refreshed_market_data = True

        if should_ingest_finnhub:
            status = run([sys.executable, "scripts/ingest_finnhub.py"], workflow_run_id, required=False)
            if status != 0:
                warnings.append("Finnhub ingestion failed; report will show source-health gaps.")
        if should_ingest_research_depth:
            status = run(
                [sys.executable, "scripts/ingest_research_depth.py"],
                workflow_run_id,
                required=False,
            )
            if status != 0:
                warnings.append("Research-depth ingestion failed; report will use stored evidence.")

        if should_ingest_sec:
            status = run([sys.executable, "scripts/ingest_sec.py"], workflow_run_id, required=False)
            if status != 0:
                warnings.append("SEC ingestion failed; report will use stored filings/facts.")

        if should_ingest_ir:
            status = run(
                [sys.executable, "scripts/ingest_official_ir.py"],
                workflow_run_id,
                required=False,
            )
            if status != 0:
                warnings.append("Official IR ingestion failed; report will use stored IR evidence.")

        if should_ingest_public_feeds:
            status = run(
                [sys.executable, "scripts/ingest_public_research_feeds.py"],
                workflow_run_id,
                required=False,
            )
            if status != 0:
                warnings.append("Public-feed ingestion failed; report will use stored feed evidence.")

        if should_tag_evidence:
            status = run(
                [sys.executable, "scripts/tag_research_evidence.py"],
                workflow_run_id,
                required=False,
            )
            if status != 0:
                warnings.append("Evidence tagging failed; report will use direct symbol evidence.")

        if should_curate_score_signals:
            status = run(
                [sys.executable, "scripts/curate_score_signals.py", "--rebuild"],
                workflow_run_id,
                required=False,
            )
            if status != 0:
                warnings.append("Score-signal curation failed; report will use stored shadow signals.")

        report_cmd = [sys.executable, "scripts/generate_daily_report.py"]
        if not args.skip_refresh and not refreshed_market_data and not warnings:
            report_cmd.append("--refresh")

        status = run(report_cmd, workflow_run_id)
        if status != 0:
            final_status = status
            finish_workflow_run(
                workflow_run_id,
                "failed",
                message="Report generation failed.",
                summary="; ".join(warnings),
                error_class="report_generation_failed",
            )
            return status

        if args.show_gaps:
            status = run(
                [sys.executable, "scripts/show_provider_gaps.py"],
                workflow_run_id,
                required=False,
            )
            if status != 0:
                warnings.append("Provider gap display failed after report generation.")
        final_status = 0
        finish_workflow_run(
            workflow_run_id,
            "ok" if not warnings else "ok_with_warnings",
            summary="; ".join(warnings),
        )
        return final_status
    except Exception as exc:  # noqa: BLE001 - keep workflow manifests recoverable.
        finish_workflow_run(
            workflow_run_id,
            "failed",
            message=str(exc),
            summary="; ".join(warnings),
            error_class=exc.__class__.__name__,
        )
        raise


if __name__ == "__main__":
    sys.exit(main())
