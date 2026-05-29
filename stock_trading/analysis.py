#!/usr/bin/env python3
"""Application and AI-analysis boundary for recommendation generation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"

from scripts import generate_daily_report as report_engine
from stock_trading.storage import (
    latest_analysis_run,
    record_analysis_run,
    record_blended_targets,
    record_recommendation_run,
    record_recommendation_scores,
    record_target_sources,
)


MODEL_VERSION = "rules-v1"


@dataclass
class AnalysisSnapshot:
    report_date: str
    research: list[report_engine.ResearchInput]
    targets: dict[str, object]
    positions: dict[str, dict[str, float]]
    research_by_symbol: dict[str, report_engine.ResearchInput]
    account_value: float
    monthly_contribution: float
    default_buy_amount: float
    reliability: dict[str, object]


def load_analysis_snapshot(report_date: str | None = None) -> AnalysisSnapshot:
    research = report_engine.load_research_inputs()
    targets = report_engine.load_targets()
    price_history = report_engine.latest_price_history_by_symbol()
    report_engine.apply_price_history_fallback(research, price_history)
    research_by_symbol = {item.symbol: item for item in research}
    positions = report_engine.merged_positions(
        report_engine.latest_etrade_positions(),
        report_engine.manual_positions(targets, research_by_symbol),
    )
    account_value = float(targets.get("account_value", 50000))
    monthly_contribution = float(targets.get("monthly_contribution", 1000))
    price_counts = report_engine.price_reliability_counts(research)
    return AnalysisSnapshot(
        report_date=report_date or datetime.now().date().isoformat(),
        research=research,
        targets=targets,
        positions=positions,
        research_by_symbol=research_by_symbol,
        account_value=account_value,
        monthly_contribution=monthly_contribution,
        default_buy_amount=min(monthly_contribution, account_value * 0.05),
        reliability={
            "mode": report_engine.reliability_mode(price_counts),
            "price_counts": price_counts,
            "latest_provider_refresh": report_engine.latest_provider_refresh_text(),
        },
    )


def compute_target_sources(
    snapshot: AnalysisSnapshot,
    recommendation_run_id: int,
) -> list[dict[str, object]]:
    return report_engine.target_source_rows(
        snapshot.research,
        recommendation_run_id,
        snapshot.report_date,
        snapshot.targets,
    )


def blend_targets(
    target_rows: list[dict[str, object]],
    recommendation_run_id: int,
    snapshot: AnalysisSnapshot,
) -> tuple[dict[str, report_engine.BlendedTarget], list[dict[str, object]]]:
    return report_engine.blended_target_rows(
        target_rows,
        recommendation_run_id,
        snapshot.targets,
        snapshot.research_by_symbol,
    )


def score_recommendations(
    snapshot: AnalysisSnapshot,
    blended_by_symbol: dict[str, report_engine.BlendedTarget],
) -> tuple[list[dict[str, Any]], list[dict[str, object]]]:
    scored: list[dict[str, Any]] = []
    score_rows: list[dict[str, object]] = []
    for item in snapshot.research:
        blended = blended_by_symbol.get(item.symbol)
        breakdown = report_engine.score_stock(item, snapshot.positions, blended)
        market_value = float(snapshot.positions.get(item.symbol, {}).get("market_value", 0) or 0)
        position_after_buy_pct = (
            ((market_value + snapshot.default_buy_amount) / snapshot.account_value) * 100
            if snapshot.account_value
            else 0
        )
        action = report_engine.action_for(item, breakdown.total, position_after_buy_pct, snapshot.targets)
        rationale = report_engine.action_rationale(
            item,
            action,
            breakdown,
            position_after_buy_pct,
            blended,
        )
        scored_row = {
            "input": item,
            "target": blended,
            "score": breakdown.total,
            "breakdown": breakdown,
            "action": action,
            "market_value": market_value,
            "position_after_buy_pct": position_after_buy_pct,
            "rationale": rationale,
        }
        scored.append(scored_row)
        score_rows.append(
            {
                "run_id": 0,
                "report_date": snapshot.report_date,
                "symbol": item.symbol,
                "company": item.company,
                "sleeve": item.sleeve,
                "trade_type": item.trade_type,
                "action": action,
                "score": round(float(breakdown.total), 4),
                "current_price": item.current_price,
                "target_price": blended.target_price if blended else item.target_price,
                "upside_pct": blended.upside_pct if blended else item.upside_pct,
                "target_confidence": report_engine.target_confidence_text(item, blended),
                "data_status": report_engine.data_status_for_target(item, blended),
                "score_breakdown": report_engine.score_summary(breakdown),
                "rationale": rationale,
            }
        )
    ranked = sorted(scored, key=lambda row: row["score"], reverse=True)
    return ranked, score_rows


def build_report_context(
    snapshot: AnalysisSnapshot,
    ranked: list[dict[str, Any]],
    recommendation_run_id: int | None = None,
    analysis_run_id: int | None = None,
) -> dict[str, object]:
    recommendations = []
    for rank, row in enumerate(ranked, start=1):
        item = row["input"]
        target = row.get("target")
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
                "confidence": report_engine.target_confidence_text(item, target),
                "data_status": report_engine.data_status_for_target(item, target),
                "rationale": row["rationale"],
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


def run_analysis(
    persist: bool = True,
    write_context: bool = True,
    report_date: str | None = None,
) -> dict[str, object]:
    snapshot = load_analysis_snapshot(report_date)
    recommendation_run_id: int | None = None
    context_path = ""
    if persist:
        recommendation_run_id = record_recommendation_run(
            snapshot.report_date,
            REPORTS_DIR / f"analysis-context-{snapshot.report_date}.json",
            Path(""),
            Path(""),
            Path(""),
            snapshot.account_value,
            snapshot.monthly_contribution,
            notes="Analysis-only recommendation run; no presentation artifacts generated.",
            workflow_run_id=_workflow_run_id_from_env(),
        )
    target_rows = compute_target_sources(snapshot, recommendation_run_id or 0)
    blended_by_symbol, blended_rows = blend_targets(target_rows, recommendation_run_id or 0, snapshot)
    ranked, score_rows = score_recommendations(snapshot, blended_by_symbol)
    if recommendation_run_id:
        for row in score_rows:
            row["run_id"] = recommendation_run_id
        record_target_sources(recommendation_run_id, target_rows)
        record_blended_targets(recommendation_run_id, blended_rows)
        record_recommendation_scores(recommendation_run_id, score_rows)
    output_counts = {
        "symbols": len(snapshot.research),
        "target_sources": len(target_rows),
        "blended_targets": len(blended_rows),
        "recommendations": len(score_rows),
    }
    context = build_report_context(snapshot, ranked, recommendation_run_id)
    if write_context:
        REPORTS_DIR.mkdir(exist_ok=True)
        context_path = str(REPORTS_DIR / f"analysis-context-{snapshot.report_date}.json")
        Path(context_path).write_text(json.dumps(context, indent=2))
    if persist:
        analysis_run_id = record_analysis_run(
            recommendation_run_id,
            MODEL_VERSION,
            config_version="portfolio_targets.json",
            input_snapshot={
                "symbols": [item.symbol for item in snapshot.research],
                "report_date": snapshot.report_date,
            },
            output_counts=output_counts,
            context_path=context_path,
        )
        context["metadata"]["analysis_run_id"] = analysis_run_id
    if write_context and context_path:
        Path(context_path).write_text(json.dumps(context, indent=2))
    return context


def latest_analysis_summary() -> dict[str, object]:
    row = latest_analysis_run()
    return dict(row) if row else {}


def _workflow_run_id_from_env() -> int | None:
    try:
        value = int(os.environ.get("STOCK_ENGINE_WORKFLOW_RUN_ID", ""))
    except ValueError:
        return None
    return value if value > 0 else None
