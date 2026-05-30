#!/usr/bin/env python3
"""Public Application + AI analysis facade."""

from __future__ import annotations

from stock_trading import analysis_engine
from stock_trading.analysis_context import (
    MODEL_VERSION,
    AnalysisResult,
    build_report_context,
)
from stock_trading.analysis_models import (
    BlendedTarget,
    DecisionInsight,
    InsightSignal,
    ResearchInput,
    ScoreBreakdown,
)
from stock_trading.analysis_scoring import score_recommendations
from stock_trading.analysis_snapshot import AnalysisSnapshot, load_analysis_snapshot
from stock_trading.analysis_targets import blend_targets, compute_target_sources


def run_analysis(
    persist: bool = True,
    write_context: bool = True,
    report_date: str | None = None,
) -> dict[str, object]:
    return analysis_engine.run_analysis(
        persist=persist,
        write_context=write_context,
        report_date=report_date,
    )


def latest_analysis_summary() -> dict[str, object]:
    return analysis_engine.latest_analysis_summary()


__all__ = [
    "MODEL_VERSION",
    "AnalysisResult",
    "AnalysisSnapshot",
    "BlendedTarget",
    "DecisionInsight",
    "InsightSignal",
    "ResearchInput",
    "ScoreBreakdown",
    "blend_targets",
    "build_report_context",
    "compute_target_sources",
    "latest_analysis_summary",
    "load_analysis_snapshot",
    "run_analysis",
    "score_recommendations",
]
