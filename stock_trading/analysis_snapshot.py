#!/usr/bin/env python3
"""Snapshot loading for recommendation analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from stock_trading import analysis_engine as engine
from stock_trading.analysis_models import ResearchInput


@dataclass
class AnalysisSnapshot:
    report_date: str
    research: list[ResearchInput]
    targets: dict[str, object]
    positions: dict[str, dict[str, float]]
    research_by_symbol: dict[str, ResearchInput]
    account_value: float
    monthly_contribution: float
    default_buy_amount: float
    reliability: dict[str, object]


def load_analysis_snapshot(report_date: str | None = None) -> AnalysisSnapshot:
    research = engine.load_research_inputs()
    targets = engine.load_targets()
    price_history = engine.latest_price_history_by_symbol()
    engine.apply_price_history_fallback(research, price_history)
    research_by_symbol = {item.symbol: item for item in research}
    positions = engine.merged_positions(
        engine.latest_etrade_positions(),
        engine.manual_positions(targets, research_by_symbol),
    )
    account_value = float(targets.get("account_value", 50000))
    monthly_contribution = float(targets.get("monthly_contribution", 1000))
    price_counts = engine.price_reliability_counts(research)
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
            "mode": engine.reliability_mode(price_counts),
            "price_counts": price_counts,
            "latest_provider_refresh": engine.latest_provider_refresh_text(),
        },
    )


__all__ = ["AnalysisSnapshot", "load_analysis_snapshot"]
