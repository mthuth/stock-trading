#!/usr/bin/env python3
"""Daily stock research workflow orchestration."""

from __future__ import annotations

import sys
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional, Union

from stock_trading.storage import finish_workflow_run, start_workflow_run
from stock_trading.workflows import steps


WorkflowStarter = Callable[[str, Union[list[str], str]], int]
WorkflowFinisher = Callable[..., None]
PackageStepRunner = Callable[[Optional[int], bool], int]


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    required: bool
    reason: str
    command: tuple[str, ...] = ()
    callable_name: str = ""


FLAG_LABELS = {
    "skip_refresh": "--skip-refresh",
    "show_gaps": "--show-gaps",
    "ingest_evidence": "--ingest-evidence",
    "ingest_free_data": "--ingest-free-data",
    "ingest_finnhub": "--ingest-finnhub",
    "ingest_sec": "--ingest-sec",
    "ingest_ir": "--ingest-ir",
    "ingest_public_feeds": "--ingest-public-feeds",
    "ingest_public_sources": "--ingest-public-sources",
    "tag_evidence": "--tag-evidence",
    "score_source_quality": "--score-source-quality",
    "curate_source_depth": "--curate-source-depth",
    "plan_ingestion": "--plan-ingestion",
    "cluster_evidence": "--cluster-evidence",
    "prepare_synthesis": "--prepare-synthesis",
    "ingest_price_history": "--ingest-price-history",
    "curate_score_signals": "--curate-score-signals",
    "score_shadow": "--score-shadow",
    "verify_insights": "--verify-insights",
}


EVIDENCE_TRIGGER_FLAGS = (
    "ingest_evidence",
    "ingest_free_data",
    "ingest_finnhub",
    "ingest_sec",
    "ingest_ir",
    "ingest_public_feeds",
    "ingest_public_sources",
    "tag_evidence",
    "score_source_quality",
    "curate_source_depth",
    "plan_ingestion",
    "cluster_evidence",
    "prepare_synthesis",
    "curate_score_signals",
    "score_shadow",
)


def _enabled(args: Namespace, name: str) -> bool:
    return bool(getattr(args, name, False))


def _reason_for(args: Namespace, flag_names: tuple[str, ...], fallback: str) -> str:
    labels = [FLAG_LABELS[name] for name in flag_names if _enabled(args, name)]
    if labels:
        return "enabled by " + ", ".join(labels)
    return fallback


def _daily_step_flags(args: Namespace) -> dict[str, bool]:
    should_ingest_research_depth = (
        _enabled(args, "ingest_evidence") or _enabled(args, "ingest_free_data") or _enabled(args, "ingest_finnhub")
    )
    should_ingest_finnhub = _enabled(args, "ingest_evidence") or _enabled(args, "ingest_finnhub")
    should_ingest_sec = (
        _enabled(args, "ingest_evidence") or _enabled(args, "ingest_free_data") or _enabled(args, "ingest_sec")
    )
    should_ingest_ir = (
        _enabled(args, "ingest_evidence") or _enabled(args, "ingest_free_data") or _enabled(args, "ingest_ir")
    )
    should_ingest_public_feeds = (
        _enabled(args, "ingest_evidence")
        or _enabled(args, "ingest_free_data")
        or _enabled(args, "ingest_public_feeds")
        or _enabled(args, "ingest_public_sources")
    )
    should_tag_evidence = (
        _enabled(args, "ingest_evidence")
        or _enabled(args, "ingest_free_data")
        or _enabled(args, "ingest_public_sources")
        or _enabled(args, "tag_evidence")
    )
    should_curate_score_signals = (
        _enabled(args, "ingest_evidence")
        or _enabled(args, "ingest_free_data")
        or _enabled(args, "ingest_public_sources")
        or _enabled(args, "curate_score_signals")
        or _enabled(args, "score_shadow")
    )
    should_curate_source_depth = (
        _enabled(args, "ingest_evidence")
        or _enabled(args, "ingest_free_data")
        or _enabled(args, "ingest_public_sources")
        or _enabled(args, "curate_source_depth")
    )
    should_score_source_quality = (
        _enabled(args, "ingest_evidence")
        or _enabled(args, "ingest_free_data")
        or _enabled(args, "ingest_public_sources")
        or _enabled(args, "score_source_quality")
    )
    should_plan_ingestion = (
        _enabled(args, "ingest_evidence")
        or _enabled(args, "ingest_free_data")
        or _enabled(args, "ingest_public_sources")
        or _enabled(args, "plan_ingestion")
    )
    should_cluster_evidence = (
        _enabled(args, "ingest_evidence")
        or _enabled(args, "ingest_free_data")
        or _enabled(args, "ingest_public_sources")
        or _enabled(args, "cluster_evidence")
    )
    should_prepare_synthesis = (
        _enabled(args, "ingest_evidence")
        or _enabled(args, "ingest_free_data")
        or _enabled(args, "ingest_public_sources")
        or _enabled(args, "prepare_synthesis")
    )
    should_ingest_price_history = _enabled(args, "ingest_price_history") or _enabled(args, "ingest_free_data")
    should_ingest_any_evidence = (
        should_ingest_finnhub
        or should_ingest_research_depth
        or should_ingest_sec
        or should_ingest_ir
        or should_ingest_public_feeds
        or should_tag_evidence
        or should_curate_source_depth
        or should_curate_score_signals
        or should_score_source_quality
        or should_plan_ingestion
        or should_cluster_evidence
        or should_prepare_synthesis
    )
    should_refresh_market_data = (
        should_ingest_any_evidence
        and not _enabled(args, "skip_refresh")
        and not _enabled(args, "ingest_free_data")
        and not _enabled(args, "ingest_public_sources")
    )
    return {
        "should_ingest_research_depth": should_ingest_research_depth,
        "should_ingest_finnhub": should_ingest_finnhub,
        "should_ingest_sec": should_ingest_sec,
        "should_ingest_ir": should_ingest_ir,
        "should_ingest_public_feeds": should_ingest_public_feeds,
        "should_tag_evidence": should_tag_evidence,
        "should_curate_score_signals": should_curate_score_signals,
        "should_curate_source_depth": should_curate_source_depth,
        "should_score_source_quality": should_score_source_quality,
        "should_plan_ingestion": should_plan_ingestion,
        "should_cluster_evidence": should_cluster_evidence,
        "should_prepare_synthesis": should_prepare_synthesis,
        "should_ingest_price_history": should_ingest_price_history,
        "should_ingest_any_evidence": should_ingest_any_evidence,
        "should_refresh_market_data": should_refresh_market_data,
    }


def _command(script_path: str, *extra_args: str) -> tuple[str, ...]:
    return (sys.executable, script_path, *extra_args)


def _planned_report_refresh(args: Namespace, step_flags: dict[str, bool]) -> bool:
    return not _enabled(args, "skip_refresh") and not step_flags["should_refresh_market_data"]


def build_daily_workflow_plan(args: Namespace) -> list[WorkflowStep]:
    step_flags = _daily_step_flags(args)
    plan: list[WorkflowStep] = []

    if step_flags["should_ingest_price_history"]:
        plan.append(
            WorkflowStep(
                name="ingest_price_history",
                callable_name="ingest_price_history_step",
                command=_command("scripts/ingest_price_history.py"),
                required=False,
                reason=_reason_for(args, ("ingest_price_history", "ingest_free_data"), "price history requested"),
            )
        )

    if step_flags["should_refresh_market_data"]:
        plan.append(
            WorkflowStep(
                name="refresh_market_data",
                command=_command("scripts/refresh_market_data.py"),
                required=True,
                reason=_reason_for(args, EVIDENCE_TRIGGER_FLAGS, "evidence ingestion needs fresh market data"),
            )
        )

    if step_flags["should_ingest_finnhub"]:
        plan.append(
            WorkflowStep(
                name="ingest_finnhub",
                command=_command("scripts/ingest_finnhub.py"),
                required=False,
                reason=_reason_for(args, ("ingest_evidence", "ingest_finnhub"), "Finnhub ingestion requested"),
            )
        )

    if step_flags["should_ingest_research_depth"]:
        plan.append(
            WorkflowStep(
                name="ingest_research_depth",
                command=_command("scripts/ingest_research_depth.py"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_finnhub"),
                    "research depth ingestion requested",
                ),
            )
        )

    if step_flags["should_ingest_sec"]:
        plan.append(
            WorkflowStep(
                name="ingest_sec",
                command=_command("scripts/ingest_sec.py"),
                required=False,
                reason=_reason_for(args, ("ingest_evidence", "ingest_free_data", "ingest_sec"), "SEC ingestion requested"),
            )
        )

    if step_flags["should_ingest_ir"]:
        plan.append(
            WorkflowStep(
                name="ingest_official_ir",
                command=_command("scripts/ingest_official_ir.py"),
                required=False,
                reason=_reason_for(args, ("ingest_evidence", "ingest_free_data", "ingest_ir"), "IR ingestion requested"),
            )
        )

    if step_flags["should_ingest_public_feeds"]:
        plan.append(
            WorkflowStep(
                name="ingest_public_research_feeds",
                callable_name="ingest_public_research_feeds_step",
                command=_command("scripts/ingest_public_research_feeds.py"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_public_feeds", "ingest_public_sources"),
                    "public feed ingestion requested",
                ),
            )
        )

    if step_flags["should_tag_evidence"]:
        plan.append(
            WorkflowStep(
                name="tag_research_evidence",
                callable_name="tag_research_evidence_step",
                command=_command("scripts/tag_research_evidence.py"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_public_sources", "tag_evidence"),
                    "evidence tagging requested",
                ),
            )
        )

    if step_flags["should_curate_source_depth"]:
        plan.append(
            WorkflowStep(
                name="curate_source_depth",
                callable_name="curate_source_depth_step",
                command=_command("scripts/curate_source_depth.py"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_public_sources", "curate_source_depth"),
                    "source depth curation requested",
                ),
            )
        )

    if step_flags["should_cluster_evidence"]:
        plan.append(
            WorkflowStep(
                name="cluster_evidence_events",
                callable_name="cluster_evidence_events_step",
                command=_command("scripts/cluster_evidence_events.py", "--rebuild"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_public_sources", "cluster_evidence"),
                    "evidence event clustering requested",
                ),
            )
        )

    if step_flags["should_prepare_synthesis"]:
        plan.append(
            WorkflowStep(
                name="prepare_synthesis_packets",
                callable_name="prepare_synthesis_packets_step",
                command=_command("scripts/prepare_synthesis_packets.py", "--rebuild"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_public_sources", "prepare_synthesis"),
                    "synthesis packet preparation requested",
                ),
            )
        )

    if step_flags["should_score_source_quality"]:
        plan.append(
            WorkflowStep(
                name="score_source_quality",
                callable_name="score_source_quality_step",
                command=_command("scripts/score_source_quality.py", "--rebuild"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_public_sources", "score_source_quality"),
                    "source quality scoring requested",
                ),
            )
        )

    if step_flags["should_plan_ingestion"]:
        plan.append(
            WorkflowStep(
                name="plan_ingestion_runs",
                callable_name="plan_ingestion_runs_step",
                command=_command("scripts/plan_ingestion_runs.py", "--rebuild"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_public_sources", "plan_ingestion"),
                    "ingestion planning requested",
                ),
            )
        )

    if step_flags["should_curate_score_signals"]:
        plan.append(
            WorkflowStep(
                name="curate_score_signals",
                command=_command("scripts/curate_score_signals.py", "--rebuild"),
                required=False,
                reason=_reason_for(
                    args,
                    ("ingest_evidence", "ingest_free_data", "ingest_public_sources", "curate_score_signals", "score_shadow"),
                    "score signal curation requested",
                ),
            )
        )

    if _enabled(args, "verify_insights"):
        plan.append(
            WorkflowStep(
                name="run_verification_queue",
                command=_command("scripts/run_verification_queue.py", "--execute"),
                required=False,
                reason=_reason_for(args, ("verify_insights",), "verification requested"),
            )
        )

    report_command = list(_command("scripts/generate_daily_report.py"))
    if _planned_report_refresh(args, step_flags):
        report_command.append("--refresh")
        report_reason = "always enabled; report refresh planned"
    elif _enabled(args, "skip_refresh"):
        report_reason = "always enabled; refresh disabled by --skip-refresh"
    else:
        report_reason = "always enabled; prior market refresh step supplies fresh data"
    plan.append(
        WorkflowStep(
            name="generate_daily_report",
            callable_name="generate_daily_report_step",
            command=tuple(report_command),
            required=True,
            reason=report_reason,
        )
    )

    if _enabled(args, "show_gaps"):
        plan.append(
            WorkflowStep(
                name="show_provider_gaps",
                command=_command("scripts/show_provider_gaps.py"),
                required=False,
                reason=_reason_for(args, ("show_gaps",), "provider gaps requested"),
            )
        )

    return plan


def run_daily(
    args: Namespace,
    argv: list[str] | None = None,
    *,
    step_runner: steps.StepRunner = steps.run,
    report_step_runner: Callable[..., int] = steps.generate_daily_report_step,
    price_history_step_runner: PackageStepRunner = steps.ingest_price_history_step,
    public_feeds_step_runner: PackageStepRunner = steps.ingest_public_research_feeds_step,
    tag_evidence_step_runner: PackageStepRunner = steps.tag_research_evidence_step,
    source_depth_step_runner: PackageStepRunner = steps.curate_source_depth_step,
    cluster_evidence_step_runner: PackageStepRunner = steps.cluster_evidence_events_step,
    prepare_synthesis_step_runner: PackageStepRunner = steps.prepare_synthesis_packets_step,
    source_quality_step_runner: PackageStepRunner = steps.score_source_quality_step,
    ingestion_plan_step_runner: PackageStepRunner = steps.plan_ingestion_runs_step,
    workflow_starter: WorkflowStarter = start_workflow_run,
    workflow_finisher: WorkflowFinisher = finish_workflow_run,
    core_price_check: Callable[[], bool] = steps.has_any_core_price_data,
) -> int:
    workflow_run_id = workflow_starter("daily", [sys.executable, "scripts/run_daily.py", *(argv or [])])
    refreshed_market_data = False
    warnings: list[str] = []
    final_status = 1

    try:
        step_flags = _daily_step_flags(args)
        should_ingest_research_depth = step_flags["should_ingest_research_depth"]
        should_ingest_finnhub = step_flags["should_ingest_finnhub"]
        should_ingest_sec = step_flags["should_ingest_sec"]
        should_ingest_ir = step_flags["should_ingest_ir"]
        should_ingest_public_feeds = step_flags["should_ingest_public_feeds"]
        should_tag_evidence = step_flags["should_tag_evidence"]
        should_curate_score_signals = step_flags["should_curate_score_signals"]
        should_curate_source_depth = step_flags["should_curate_source_depth"]
        should_score_source_quality = step_flags["should_score_source_quality"]
        should_plan_ingestion = step_flags["should_plan_ingestion"]
        should_cluster_evidence = step_flags["should_cluster_evidence"]
        should_prepare_synthesis = step_flags["should_prepare_synthesis"]
        should_refresh_market_data = step_flags["should_refresh_market_data"]

        if step_flags["should_ingest_price_history"]:
            status = price_history_step_runner(workflow_run_id, False)
            if status != 0:
                warnings.append("Price-history ingestion failed; continuing with existing history.")

        if should_refresh_market_data:
            status = step_runner([sys.executable, "scripts/refresh_market_data.py"], workflow_run_id, True)
            if status != 0:
                if steps.should_continue_after_refresh_failure(status, core_price_check):
                    warnings.append(
                        "Market-data refresh failed; continuing with existing price data and recorded gaps."
                    )
                else:
                    final_status = status
                    workflow_finisher(
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
            status = step_runner([sys.executable, "scripts/ingest_finnhub.py"], workflow_run_id, False)
            if status != 0:
                warnings.append("Finnhub ingestion failed; report will show source-health gaps.")
        if should_ingest_research_depth:
            status = step_runner(
                [sys.executable, "scripts/ingest_research_depth.py"],
                workflow_run_id,
                False,
            )
            if status != 0:
                warnings.append("Research-depth ingestion failed; report will use stored evidence.")

        if should_ingest_sec:
            status = step_runner([sys.executable, "scripts/ingest_sec.py"], workflow_run_id, False)
            if status != 0:
                warnings.append("SEC ingestion failed; report will use stored filings/facts.")

        if should_ingest_ir:
            status = step_runner(
                [sys.executable, "scripts/ingest_official_ir.py"],
                workflow_run_id,
                False,
            )
            if status != 0:
                warnings.append("Official IR ingestion failed; report will use stored IR evidence.")

        if should_ingest_public_feeds:
            status = public_feeds_step_runner(workflow_run_id, False)
            if status != 0:
                warnings.append("Public-feed ingestion failed; report will use stored feed evidence.")

        if should_tag_evidence:
            status = tag_evidence_step_runner(workflow_run_id, False)
            if status != 0:
                warnings.append("Evidence tagging failed; report will use direct symbol evidence.")

        if should_curate_source_depth:
            status = source_depth_step_runner(workflow_run_id, False)
            if status != 0:
                warnings.append("Source-depth curation failed; report will use prior curated depth rows.")

        if should_cluster_evidence:
            status = cluster_evidence_step_runner(workflow_run_id, False)
            if status != 0:
                warnings.append("Evidence event clustering failed; report will use prior event clusters.")

        if should_prepare_synthesis:
            status = prepare_synthesis_step_runner(workflow_run_id, False)
            if status != 0:
                warnings.append("Synthesis readiness preparation failed; report will use prior synthesis packets.")

        if should_score_source_quality:
            status = source_quality_step_runner(workflow_run_id, False)
            if status != 0:
                warnings.append("Source-quality scoring failed; report will use prior source metrics.")

        if should_plan_ingestion:
            status = ingestion_plan_step_runner(workflow_run_id, False)
            if status != 0:
                warnings.append("Ingestion planning failed; report will use prior freshness/backfill plan.")

        if should_curate_score_signals:
            status = step_runner(
                [sys.executable, "scripts/curate_score_signals.py", "--rebuild"],
                workflow_run_id,
                False,
            )
            if status != 0:
                warnings.append("Score-signal curation failed; report will use stored shadow signals.")

        if args.verify_insights:
            status = step_runner(
                [sys.executable, "scripts/run_verification_queue.py", "--execute"],
                workflow_run_id,
                False,
            )
            if status != 0:
                warnings.append("Verification queue failed or has failed items; report will show queue status.")

        should_refresh_report = not args.skip_refresh and not refreshed_market_data and not warnings
        status = report_step_runner(workflow_run_id, True, refresh=should_refresh_report)
        if status != 0:
            final_status = status
            workflow_finisher(
                workflow_run_id,
                "failed",
                message="Report generation failed.",
                summary="; ".join(warnings),
                error_class="report_generation_failed",
            )
            return status

        if args.show_gaps:
            status = step_runner(
                [sys.executable, "scripts/show_provider_gaps.py"],
                workflow_run_id,
                False,
            )
            if status != 0:
                warnings.append("Provider gap display failed after report generation.")
        final_status = 0
        workflow_finisher(
            workflow_run_id,
            "ok" if not warnings else "ok_with_warnings",
            summary="; ".join(warnings),
        )
        return final_status
    except Exception as exc:  # noqa: BLE001 - keep workflow manifests recoverable.
        workflow_finisher(
            workflow_run_id,
            "failed",
            message=str(exc),
            summary="; ".join(warnings),
            error_class=exc.__class__.__name__,
        )
        raise
