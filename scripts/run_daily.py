#!/usr/bin/env python3
"""Compatibility wrapper for stock_trading.cli.daily."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.cli import daily as _daily  # noqa: E402

finish_workflow_run = _daily.finish_workflow_run
generate_daily_report_step = _daily.generate_daily_report_step
has_any_core_price_data = _daily.has_any_core_price_data
cluster_evidence_events_step = _daily.cluster_evidence_events_step
curate_source_depth_step = _daily.curate_source_depth_step
ingest_price_history_step = _daily.ingest_price_history_step
ingest_public_research_feeds_step = _daily.ingest_public_research_feeds_step
plan_ingestion_runs_step = _daily.plan_ingestion_runs_step
prepare_synthesis_packets_step = _daily.prepare_synthesis_packets_step
run = _daily.run
score_source_quality_step = _daily.score_source_quality_step
start_workflow_run = _daily.start_workflow_run
tag_research_evidence_step = _daily.tag_research_evidence_step


def main() -> int:
    _daily.cluster_evidence_events_step = cluster_evidence_events_step
    _daily.curate_source_depth_step = curate_source_depth_step
    _daily.finish_workflow_run = finish_workflow_run
    _daily.generate_daily_report_step = generate_daily_report_step
    _daily.has_any_core_price_data = has_any_core_price_data
    _daily.ingest_price_history_step = ingest_price_history_step
    _daily.ingest_public_research_feeds_step = ingest_public_research_feeds_step
    _daily.plan_ingestion_runs_step = plan_ingestion_runs_step
    _daily.prepare_synthesis_packets_step = prepare_synthesis_packets_step
    _daily.run = run
    _daily.score_source_quality_step = score_source_quality_step
    _daily.start_workflow_run = start_workflow_run
    _daily.tag_research_evidence_step = tag_research_evidence_step
    return _daily.main()


if __name__ == "__main__":
    sys.exit(main())
