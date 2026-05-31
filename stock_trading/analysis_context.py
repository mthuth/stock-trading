#!/usr/bin/env python3
"""JSON-native report-context assembly for analysis outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from stock_trading import analysis_engine as engine
from stock_trading.analysis_snapshot import AnalysisSnapshot


MODEL_VERSION = "rules-v1"
AnalysisResult = dict[str, object]


def build_report_context(
    snapshot: AnalysisSnapshot | AnalysisResult,
    ranked: list[dict[str, Any]] | None = None,
    recommendation_run_id: int | None = None,
    analysis_run_id: int | None = None,
) -> dict[str, object]:
    if ranked is None and isinstance(snapshot, dict):
        return engine.build_report_context(snapshot)
    assert isinstance(snapshot, AnalysisSnapshot)
    assert ranked is not None
    recommendations = []
    for rank, row in enumerate(ranked, start=1):
        item = row["input"]
        target = row.get("target")
        explanation = row.get("score_explanation") or engine.score_explanation(
            item,
            row["breakdown"],
            target,
            rationale=row["rationale"],
        )
        recommendations.append(
            {
                "rank": rank,
                "symbol": item.symbol,
                "company": item.company,
                "sleeve": item.sleeve,
                "trade_type": item.trade_type,
                "action": row["action"],
                "score": round(float(row["score"]), 2),
                "current_price": item.current_price,
                "target_price": target.target_price if target else item.target_price,
                "upside_pct": target.upside_pct if target else item.upside_pct,
                "confidence": engine.target_confidence_text(item, target),
                "data_status": engine.data_status_for_target(item, target),
                "rationale": row["rationale"],
                "score_explanation": explanation,
                "notes": item.notes,
            }
        )
    top = recommendations[0] if recommendations else {}
    return {
        "metadata": {
            "report_date": snapshot.report_date,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "model_version": MODEL_VERSION,
            "recommendation_run_id": recommendation_run_id,
            "analysis_run_id": analysis_run_id,
            "recommendation_only": True,
        },
        "summary": {
            "top_symbol": top.get("symbol", ""),
            "top_action": top.get("action", ""),
            "top_score": top.get("score", 0),
        },
        "reliability": snapshot.reliability,
        "recommendations": recommendations,
    }


__all__ = ["AnalysisResult", "MODEL_VERSION", "build_report_context"]
