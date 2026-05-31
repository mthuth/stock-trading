#!/usr/bin/env python3
"""CLI parser for the daily stock research workflow."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from stock_trading.storage import finish_workflow_run, start_workflow_run
from stock_trading.workflows import steps as workflow_steps
from stock_trading.workflows.daily import run_daily
from stock_trading.workflows.steps import (
    cluster_evidence_events_step,
    curate_source_depth_step,
    generate_daily_report_step,
    has_any_core_price_data,
    ingest_price_history_step,
    ingest_public_research_feeds_step,
    plan_ingestion_runs_step,
    prepare_synthesis_packets_step,
    run,
    score_source_quality_step,
    step_name_for,
    tag_research_evidence_step,
)


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
        "--ingest-public-sources",
        action="store_true",
        help="Run all configured free public RSS/archive/page-link source ingestion before report generation.",
    )
    parser.add_argument(
        "--tag-evidence",
        action="store_true",
        help="Tag broad research evidence to stock symbols before report generation.",
    )
    parser.add_argument(
        "--score-source-quality",
        action="store_true",
        help="Roll up ingestion quality and source relevance metrics before report generation.",
    )
    parser.add_argument(
        "--curate-source-depth",
        action="store_true",
        help="Curate normalized source-depth evidence from SEC, IR, and official company-source rows.",
    )
    parser.add_argument(
        "--plan-ingestion",
        action="store_true",
        help="Refresh the source freshness, cooldown, and backfill plan before report generation.",
    )
    parser.add_argument(
        "--cluster-evidence",
        action="store_true",
        help="Cluster related evidence rows into corroborated event groups before report generation.",
    )
    parser.add_argument(
        "--prepare-synthesis",
        action="store_true",
        help="Prepare deterministic evidence review queue and per-symbol synthesis packets.",
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
    parser.add_argument(
        "--verify-insights",
        action="store_true",
        help="Run the latest open V1.8 verification queue before generating the report.",
    )
    return parser.parse_args()


def main() -> int:
    return run_daily(
        parse_args(),
        sys.argv[1:],
        step_runner=run,
        report_step_runner=run_report_step,
        price_history_step_runner=run_price_history_step,
        public_feeds_step_runner=run_public_feeds_step,
        tag_evidence_step_runner=run_tag_evidence_step,
        source_depth_step_runner=run_source_depth_step,
        cluster_evidence_step_runner=run_cluster_evidence_step,
        prepare_synthesis_step_runner=run_prepare_synthesis_step,
        source_quality_step_runner=run_source_quality_step,
        ingestion_plan_step_runner=run_ingestion_plan_step,
        workflow_starter=start_workflow_run,
        workflow_finisher=finish_workflow_run,
        core_price_check=has_any_core_price_data,
    )


def run_package_or_command_step(
    command: list[str],
    package_step: Callable[[int | None, bool], int],
    workflow_run_id: int | None,
    required: bool,
) -> int:
    if run is not workflow_steps.run:
        return run(command, workflow_run_id, required)
    return package_step(workflow_run_id, required)


def run_price_history_step(workflow_run_id: int | None, required: bool) -> int:
    return run_package_or_command_step(
        [sys.executable, "scripts/ingest_price_history.py"],
        ingest_price_history_step,
        workflow_run_id,
        required,
    )


def run_public_feeds_step(workflow_run_id: int | None, required: bool) -> int:
    return run_package_or_command_step(
        [sys.executable, "scripts/ingest_public_research_feeds.py"],
        ingest_public_research_feeds_step,
        workflow_run_id,
        required,
    )


def run_tag_evidence_step(workflow_run_id: int | None, required: bool) -> int:
    return run_package_or_command_step(
        [sys.executable, "scripts/tag_research_evidence.py"],
        tag_research_evidence_step,
        workflow_run_id,
        required,
    )


def run_source_depth_step(workflow_run_id: int | None, required: bool) -> int:
    return run_package_or_command_step(
        [sys.executable, "scripts/curate_source_depth.py"],
        curate_source_depth_step,
        workflow_run_id,
        required,
    )


def run_cluster_evidence_step(workflow_run_id: int | None, required: bool) -> int:
    return run_package_or_command_step(
        [sys.executable, "scripts/cluster_evidence_events.py", "--rebuild"],
        cluster_evidence_events_step,
        workflow_run_id,
        required,
    )


def run_prepare_synthesis_step(workflow_run_id: int | None, required: bool) -> int:
    return run_package_or_command_step(
        [sys.executable, "scripts/prepare_synthesis_packets.py", "--rebuild"],
        prepare_synthesis_packets_step,
        workflow_run_id,
        required,
    )


def run_source_quality_step(workflow_run_id: int | None, required: bool) -> int:
    return run_package_or_command_step(
        [sys.executable, "scripts/score_source_quality.py", "--rebuild"],
        score_source_quality_step,
        workflow_run_id,
        required,
    )


def run_ingestion_plan_step(workflow_run_id: int | None, required: bool) -> int:
    return run_package_or_command_step(
        [sys.executable, "scripts/plan_ingestion_runs.py", "--rebuild"],
        plan_ingestion_runs_step,
        workflow_run_id,
        required,
    )


def run_report_step(workflow_run_id: int | None, required: bool, *, refresh: bool = False) -> int:
    if run is not workflow_steps.run:
        command = [sys.executable, "scripts/generate_daily_report.py"]
        if refresh:
            command.append("--refresh")
        return run(command, workflow_run_id, required)
    return generate_daily_report_step(workflow_run_id, required, refresh=refresh)


if __name__ == "__main__":
    sys.exit(main())
