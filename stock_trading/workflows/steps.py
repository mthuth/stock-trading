#!/usr/bin/env python3
"""Reusable workflow step execution helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Callable, Optional

from stock_trading import analysis_engine
from stock_trading import ingestion_workflows
from stock_trading.analysis import run_analysis
from stock_trading.presentation import load_report_context, render_report_context
from stock_trading.storage import (
    RESEARCH_FILE,
    finish_workflow_step,
    read_csv,
    start_workflow_step,
)


ROOT = Path(__file__).resolve().parents[2]
StepRunner = Callable[[list[str], Optional[int], bool], int]


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


@contextmanager
def workflow_env(workflow_run_id: int | None) -> Any:
    previous = os.environ.get("STOCK_ENGINE_WORKFLOW_RUN_ID")
    if workflow_run_id is not None:
        os.environ["STOCK_ENGINE_WORKFLOW_RUN_ID"] = str(workflow_run_id)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("STOCK_ENGINE_WORKFLOW_RUN_ID", None)
        else:
            os.environ["STOCK_ENGINE_WORKFLOW_RUN_ID"] = previous


def run_callable_step(
    step_name: str,
    display_command: list[str],
    workflow_run_id: int | None,
    required: bool,
    callback: Callable[[], None],
) -> int:
    print(f"\n$ {' '.join(display_command)}")
    step_run_id = start_workflow_step(
        workflow_run_id,
        step_name,
        display_command,
        required=required,
    )
    try:
        with workflow_env(workflow_run_id):
            callback()
    except SystemExit as exc:
        status = exc.code if isinstance(exc.code, int) else 1
        finish_workflow_step(
            step_run_id,
            "ok" if status == 0 else "failed",
            exit_code=status,
            message="" if status == 0 else str(exc),
        )
        return status
    except Exception as exc:  # noqa: BLE001 - match script subprocess failure behavior.
        finish_workflow_step(
            step_run_id,
            "failed",
            exit_code=1,
            message=str(exc),
            error_class=exc.__class__.__name__,
        )
        return 1
    finish_workflow_step(step_run_id, "ok", exit_code=0)
    return 0


def _run_ingestion_callable_step(
    display_command: list[str],
    workflow_run_id: int | None,
    required: bool,
    callback: Callable[[], int],
) -> int:
    def checked_callback() -> None:
        status = callback()
        if status != 0:
            raise SystemExit(status)

    return run_callable_step(
        step_name_for(display_command),
        display_command,
        workflow_run_id,
        required,
        checked_callback,
    )


def ingest_price_history_step(workflow_run_id: int | None = None, required: bool = False) -> int:
    return _run_ingestion_callable_step(
        [sys.executable, "scripts/ingest_price_history.py"],
        workflow_run_id,
        required,
        ingestion_workflows.ingest_price_history,
    )


def ingest_public_research_feeds_step(workflow_run_id: int | None = None, required: bool = False) -> int:
    return _run_ingestion_callable_step(
        [sys.executable, "scripts/ingest_public_research_feeds.py"],
        workflow_run_id,
        required,
        ingestion_workflows.ingest_public_research_feeds,
    )


def tag_research_evidence_step(workflow_run_id: int | None = None, required: bool = False) -> int:
    return _run_ingestion_callable_step(
        [sys.executable, "scripts/tag_research_evidence.py"],
        workflow_run_id,
        required,
        ingestion_workflows.tag_research_evidence,
    )


def curate_source_depth_step(workflow_run_id: int | None = None, required: bool = False) -> int:
    return _run_ingestion_callable_step(
        [sys.executable, "scripts/curate_source_depth.py"],
        workflow_run_id,
        required,
        ingestion_workflows.curate_source_depth,
    )


def cluster_evidence_events_step(workflow_run_id: int | None = None, required: bool = False) -> int:
    return _run_ingestion_callable_step(
        [sys.executable, "scripts/cluster_evidence_events.py", "--rebuild"],
        workflow_run_id,
        required,
        ingestion_workflows.cluster_evidence_events,
    )


def prepare_synthesis_packets_step(workflow_run_id: int | None = None, required: bool = False) -> int:
    return _run_ingestion_callable_step(
        [sys.executable, "scripts/prepare_synthesis_packets.py", "--rebuild"],
        workflow_run_id,
        required,
        ingestion_workflows.prepare_synthesis_packets,
    )


def score_source_quality_step(workflow_run_id: int | None = None, required: bool = False) -> int:
    return _run_ingestion_callable_step(
        [sys.executable, "scripts/score_source_quality.py", "--rebuild"],
        workflow_run_id,
        required,
        ingestion_workflows.score_source_quality,
    )


def plan_ingestion_runs_step(workflow_run_id: int | None = None, required: bool = False) -> int:
    return _run_ingestion_callable_step(
        [sys.executable, "scripts/plan_ingestion_runs.py", "--rebuild"],
        workflow_run_id,
        required,
        ingestion_workflows.plan_ingestion_runs,
    )


def _refresh_market_data_for_report() -> None:
    result = subprocess.run(
        [sys.executable, str(analysis_engine.REFRESH_SCRIPT)],
        cwd=ROOT,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit("Market-data refresh failed; report was not generated.")


def run_analysis_step(
    workflow_run_id: int | None = None,
    required: bool = True,
    *,
    persist: bool = True,
    write_context: bool = True,
    report_date: str | None = None,
) -> int:
    def callback() -> None:
        context = run_analysis(
            persist=persist,
            write_context=write_context,
            report_date=report_date,
        )
        print(
            json.dumps(
                {
                "analysis_run_id": context["metadata"].get("analysis_run_id"),
                "recommendation_run_id": context["metadata"].get("recommendation_run_id"),
                "recommendations": len(context.get("recommendations", [])),
                "top_symbol": context.get("summary", {}).get("top_symbol"),
                },
                indent=2,
            )
        )

    return run_callable_step(
        "run_analysis",
        [sys.executable, "scripts/run_analysis.py"],
        workflow_run_id,
        required,
        callback,
    )


def generate_daily_report_step(
    workflow_run_id: int | None = None,
    required: bool = True,
    *,
    refresh: bool = False,
) -> int:
    display_command = [sys.executable, "scripts/generate_daily_report.py"]
    if refresh:
        display_command.append("--refresh")

    def callback() -> None:
        if refresh:
            _refresh_market_data_for_report()
        context = analysis_engine.run_analysis(persist=True, write_context=True)
        rendered_paths = render_report_context(context, analysis_engine.REPORTS_DIR)
        ai_context = context.get("artifacts", {}).get("ai_context", "")
        ai_context_path = analysis_engine.REPORTS_DIR / str(ai_context) if ai_context else None
        for report_path in [*rendered_paths, *([ai_context_path] if ai_context_path else [])]:
            print(f"Wrote {report_path}")

    return run_callable_step(
        "generate_daily_report",
        display_command,
        workflow_run_id,
        required,
        callback,
    )


def render_report_context_step(
    fixture: Path,
    output_dir: Path,
    workflow_run_id: int | None = None,
    required: bool = True,
) -> int:
    def callback() -> None:
        context = load_report_context(fixture)
        paths = render_report_context(context, output_dir)
        for path in paths:
            print(f"Wrote {path}")

    return run_callable_step(
        "render_report_context",
        [sys.executable, "scripts/render_report_context.py", "--fixture", str(fixture), "--output-dir", str(output_dir)],
        workflow_run_id,
        required,
        callback,
    )


def should_continue_after_refresh_failure(
    status: int,
    core_price_check: Callable[[], bool] = has_any_core_price_data,
) -> bool:
    if status == 0:
        return True
    return core_price_check()
