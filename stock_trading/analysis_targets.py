#!/usr/bin/env python3
"""Target-source generation and blending for analysis."""

from __future__ import annotations

from stock_trading import analysis_engine as engine
from stock_trading.analysis_models import BlendedTarget
from stock_trading.analysis_snapshot import AnalysisSnapshot


def compute_target_sources(
    snapshot: AnalysisSnapshot,
    recommendation_run_id: int,
) -> list[dict[str, object]]:
    return engine.target_source_rows(
        snapshot.research,
        recommendation_run_id,
        snapshot.report_date,
        snapshot.targets,
    )


def blend_targets(
    target_rows: list[dict[str, object]],
    recommendation_run_id: int,
    snapshot: AnalysisSnapshot,
) -> tuple[dict[str, BlendedTarget], list[dict[str, object]]]:
    return engine.blended_target_rows(
        target_rows,
        recommendation_run_id,
        snapshot.targets,
        snapshot.research_by_symbol,
    )


__all__ = ["blend_targets", "compute_target_sources"]
