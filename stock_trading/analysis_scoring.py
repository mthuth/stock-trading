#!/usr/bin/env python3
"""Recommendation scoring and controlled action labels."""

from __future__ import annotations

from typing import Any

from stock_trading import analysis_engine as engine
from stock_trading.analysis_models import BlendedTarget
from stock_trading.analysis_snapshot import AnalysisSnapshot


def score_recommendations(
    snapshot: AnalysisSnapshot,
    blended_by_symbol: dict[str, BlendedTarget],
) -> tuple[list[dict[str, Any]], list[dict[str, object]]]:
    scored: list[dict[str, Any]] = []
    score_rows: list[dict[str, object]] = []
    for item in snapshot.research:
        blended = blended_by_symbol.get(item.symbol)
        breakdown = engine.score_stock(item, snapshot.positions, blended)
        market_value = float(snapshot.positions.get(item.symbol, {}).get("market_value", 0) or 0)
        position_after_buy_pct = (
            ((market_value + snapshot.default_buy_amount) / snapshot.account_value) * 100
            if snapshot.account_value
            else 0
        )
        action = engine.action_for(item, breakdown.total, position_after_buy_pct, snapshot.targets)
        rationale = engine.action_rationale(
            item,
            action,
            breakdown,
            position_after_buy_pct,
            blended,
        )
        explanation = engine.score_explanation(item, breakdown, blended, rationale=rationale)
        scored.append(
            {
                "input": item,
                "target": blended,
                "score": breakdown.total,
                "breakdown": breakdown,
                "action": action,
                "market_value": market_value,
                "position_after_buy_pct": position_after_buy_pct,
                "rationale": rationale,
                "score_explanation": explanation,
            }
        )
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
                "target_confidence": engine.target_confidence_text(item, blended),
                "data_status": engine.data_status_for_target(item, blended),
                "score_breakdown": engine.score_summary(breakdown),
                "rationale": rationale,
            }
        )
    ranked = sorted(scored, key=lambda row: row["score"], reverse=True)
    return ranked, score_rows


__all__ = ["score_recommendations"]
