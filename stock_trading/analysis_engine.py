#!/usr/bin/env python3
"""Rules-based application analysis for stock recommendations.

This module owns target-source generation, scoring, confidence/risk logic,
decision insights, verification queues, and JSON-native report context assembly.
It does not render report artifacts or call provider/network clients.
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set

from stock_trading.alert_inbox import build_alert_inbox
from stock_trading.alerts import build_alert, build_review_alerts
from stock_trading.allocation_safety import (
    allocation_safety_for_candidate,
    sleeve_market_values_for_ranked,
)
from stock_trading.ai_thesis_evaluation import evaluate_ai_theses
from stock_trading.benchmark_comparison import benchmark_comparison_rows
from stock_trading.best_add_fallback import build_best_add_fallback_review
from stock_trading.capital_deployment import capital_deployment_context
from stock_trading.catalyst_outcomes import build_catalyst_follow_through_review
from stock_trading.decision_safety_outcomes import build_decision_safety_effectiveness_review
from stock_trading.earnings_events import build_earnings_event_queue
from stock_trading.earnings_signals import extract_earnings_signals, summarize_earnings_signals
from stock_trading.fundamental_target_config import (
    assumptions_for_symbol,
    peer_group_for_symbol as configured_peer_group_for_symbol,
    source_config as fundamental_source_config,
)
from stock_trading.long_term_add_queue import build_long_term_add_queue
from stock_trading.long_term_holding_health import build_holding_health_review
from stock_trading.manual_trade_journal import list_manual_journal_entries
from stock_trading.model_registry import build_model_registry
from stock_trading.model_trust import build_model_trust_score
from stock_trading.post_earnings_review import build_post_earnings_reviews
from stock_trading.prediction_records import build_prediction_record_set, prediction_from_recommendation
from stock_trading.pre_earnings_review import review_pre_earnings_setup
from stock_trading.provider_gap_summary import build_provider_gap_review
from stock_trading.recommendation_outcomes import build_recommendation_outcome_review
from stock_trading.recommendation_backtests import recommendation_backtest
from stock_trading.source_usefulness import build_source_usefulness, summarize_source_usefulness
from stock_trading.tactical_outcomes import summarize_tactical_outcomes, tactical_outcome_rows
from stock_trading.tactical_risk import tactical_risk_zones
from stock_trading.tactical_setups import classify_tactical_setup
from stock_trading.tactical_watchlist import build_tactical_watchlist_queue
from stock_trading.target_confidence import calibrate_target_confidence
from stock_trading.technical_targets import calculate_technical_target
from stock_trading.watchlist_policy import evaluate_watchlist_policy


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
REPORTS_DIR = ROOT / "reports"
DB_FILE = ROOT / "data" / "stock_trading.sqlite"
RESEARCH_FILE = CONFIG_DIR / "research_inputs.csv"
MANUAL_ANALYST_TARGETS_FILE = CONFIG_DIR / "manual_analyst_targets.csv"
TARGETS_FILE = CONFIG_DIR / "portfolio_targets.json"
SOURCES_FILE = CONFIG_DIR / "research_sources.csv"
SOURCE_INTEGRATIONS_FILE = CONFIG_DIR / "research_source_integrations.csv"
REFRESH_SCRIPT = ROOT / "scripts" / "refresh_market_data.py"
REPORT_SECTION_LABELS = (
    "Insight Drivers",
    "Score Movement",
    "Trend Insights",
    "Ranked Data Gap Queue",
    "Decision Briefs",
    "Decision Insight",
    "Insight Themes",
    "What To Verify Next",
    "Verification Queue",
    "Provider Blocker Review",
    "Decision Insight History",
    "AI Analysis Context Ready",
)

from stock_trading.storage import (
    init_db,
    latest_decision_insights_by_symbol,
    latest_provider_gaps,
    latest_verification_queue,
    latest_successful_provider_refresh,
    latest_analysis_run,
    record_analysis_run,
    record_blended_targets,
    record_decision_insights,
    record_recommendation_run,
    record_recommendation_scores,
    record_score_signals,
    record_target_sources,
    record_verification_queue_items,
)
from stock_trading.feedback import recent_feedback


MODEL_VERSION = "daily-report-rules-v1"


@dataclass
class ResearchInput:
    symbol: str
    company: str
    category: str
    sleeve: str
    trade_type: str
    current_price: float
    target_price: float
    quality_score: float
    momentum_score: float
    catalyst_score: float
    risk_score: float
    confidence: str
    notes: str
    price_source: str
    target_source: str
    estimate_source: str
    sentiment_source: str
    eps_estimate: str
    revenue_estimate: str
    news_sentiment: str
    provider_notes: str

    @property
    def upside_pct(self) -> float:
        if self.current_price <= 0 or self.target_price <= 0:
            return 0.0
        return ((self.target_price - self.current_price) / self.current_price) * 100


@dataclass
class ScoreBreakdown:
    total: float
    upside: float
    quality: float
    momentum: float
    catalyst: float
    risk: float
    owned_penalty: float
    speculative_penalty: float
    model: str


@dataclass
class BlendedTarget:
    symbol: str
    target_price: float
    target_low: float | None
    target_high: float | None
    current_price: float
    upside_pct: float
    confidence: str
    source_count: int
    blend_status: str
    sources_label: str
    notes: str
    confidence_reasons: tuple[str, ...] = ()


@dataclass
class InsightSignal:
    symbol: str
    base_score: float
    final_score: float
    evidence_delta: float
    trend_delta: float
    target_delta: float
    data_gap_delta: float
    drivers: List[str]
    data_gaps: List[Dict[str, object]]
    trend_insight: str

    @property
    def total_delta(self) -> float:
        return self.evidence_delta + self.trend_delta + self.target_delta + self.data_gap_delta

    @property
    def score_movement(self) -> str:
        return (
            f"{self.base_score:.1f} base "
            f"{self.total_delta:+.1f} signal overlay = {self.final_score:.1f}"
        )


@dataclass
class DecisionInsight:
    symbol: str
    headline: str
    insight_type: str
    why_it_matters: str
    supporting_data: str
    risk_or_uncertainty: str
    next_check: str
    what_would_change_the_view: str


def load_research_inputs() -> List[ResearchInput]:
    with RESEARCH_FILE.open(newline="") as handle:
        rows = csv.DictReader(handle)
        return [
            ResearchInput(
                symbol=row["symbol"].strip().upper(),
                company=row["company"].strip(),
                category=row["category"].strip(),
                sleeve=row["sleeve"].strip(),
                trade_type=row.get("trade_type", row["sleeve"]).strip(),
                current_price=float(row["current_price"] or 0),
                target_price=float(row["target_price"] or 0),
                quality_score=float(row["quality_score"] or 0),
                momentum_score=float(row["momentum_score"] or 0),
                catalyst_score=float(row["catalyst_score"] or 0),
                risk_score=float(row["risk_score"] or 0),
                confidence=row["confidence"].strip(),
                notes=row["notes"].strip(),
                price_source=row.get("price_source", "").strip(),
                target_source=row.get("target_source", "").strip(),
                estimate_source=row.get("estimate_source", "").strip(),
                sentiment_source=row.get("sentiment_source", "").strip(),
                eps_estimate=row.get("eps_estimate", "").strip(),
                revenue_estimate=row.get("revenue_estimate", "").strip(),
                news_sentiment=row.get("news_sentiment", "").strip(),
                provider_notes=row.get("provider_notes", "").strip(),
            )
            for row in rows
        ]


def load_manual_analyst_targets() -> Dict[str, List[Dict[str, object]]]:
    """Load optional one-row-per-analyst-target overrides from config."""
    if not MANUAL_ANALYST_TARGETS_FILE.exists():
        return {}

    grouped: Dict[str, List[Dict[str, object]]] = {}
    with MANUAL_ANALYST_TARGETS_FILE.open(newline="") as handle:
        rows = csv.DictReader(handle)
        for row in rows:
            symbol = str(row.get("symbol") or "").strip().upper()
            target_price = to_float(row.get("target_price"))
            if not symbol or target_price <= 0:
                continue
            grouped.setdefault(symbol, []).append(
                {
                    "source_name": str(row.get("source_name") or "Manual analyst target").strip(),
                    "target_price": target_price,
                    "target_low": to_float(row.get("target_low"), None),
                    "target_high": to_float(row.get("target_high"), None),
                    "as_of_date": str(row.get("as_of_date") or "").strip(),
                    "confidence": str(row.get("confidence") or "low").strip(),
                    "provider_endpoint": str(row.get("provider_endpoint") or "manual_analyst_targets.csv").strip(),
                    "notes": str(row.get("notes") or "").strip(),
                }
            )
    return grouped


def load_research_sources() -> List[Dict[str, str]]:
    if not SOURCES_FILE.exists():
        return []
    with SOURCES_FILE.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.pop(None, None)
    return rows


def load_source_integrations() -> Dict[str, Dict[str, str]]:
    if not SOURCE_INTEGRATIONS_FILE.exists():
        return {}
    with SOURCE_INTEGRATIONS_FILE.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    integrations = {}
    for row in rows:
        row.pop(None, None)
        source_name = row.get("source_name", "").strip()
        if source_name:
            integrations[source_name] = row
    return integrations


def load_targets() -> Dict[str, object]:
    return json.loads(TARGETS_FILE.read_text())


def latest_etrade_positions() -> Dict[str, Dict[str, float]]:
    if not DB_FILE.exists():
        return {}

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    run = conn.execute(
        """
        SELECT id
        FROM etrade_sync_runs
        WHERE environment IN ('production', 'prod', 'live')
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not run:
        return {}

    positions = conn.execute(
        """
        SELECT symbol, quantity, market_value, last_price
        FROM etrade_positions
        WHERE run_id = ?
        """,
        (run["id"],),
    ).fetchall()
    return {
        row["symbol"].upper(): {
            "quantity": float(row["quantity"] or 0),
            "market_value": float(row["market_value"] or 0),
            "last_price": float(row["last_price"] or 0),
            "source": "etrade_production",
        }
        for row in positions
    }


def manual_positions(
    targets: Dict[str, object],
    research_by_symbol: Dict[str, ResearchInput],
) -> Dict[str, Dict[str, float]]:
    positions: Dict[str, Dict[str, float]] = {}
    for item in targets.get("manual_positions", []):
        symbol = str(item.get("symbol", "")).upper()
        quantity = float(item.get("quantity", 0) or 0)
        research = research_by_symbol.get(symbol)
        price = research.current_price if research else 0.0
        positions[symbol] = {
            "quantity": quantity,
            "market_value": quantity * price,
            "last_price": price,
            "source": "manual",
        }
    return positions


def merged_positions(
    etrade: Dict[str, Dict[str, float]],
    manual: Dict[str, Dict[str, float]],
) -> Dict[str, Dict[str, float]]:
    positions = dict(manual)
    positions.update(etrade)
    return positions


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def score_stock(
    item: ResearchInput,
    positions: Dict[str, Dict[str, float]],
    target: BlendedTarget | None = None,
) -> ScoreBreakdown:
    upside_pct = target.upside_pct if target else item.upside_pct
    upside_score = clamp(upside_pct * 1.8)
    owned_penalty = 5 if item.symbol in positions else 0
    speculative_penalty = 8 if item.sleeve == "speculative_ai" else 0
    if item.trade_type == "day_trade":
        model = "Day trade"
        weights = {"upside": 0.05, "quality": 0.10, "momentum": 0.40, "catalyst": 0.25, "risk": 0.20}
    elif item.trade_type == "weekly_swing":
        model = "Weekly swing"
        weights = {"upside": 0.15, "quality": 0.15, "momentum": 0.35, "catalyst": 0.20, "risk": 0.15}
    elif item.trade_type == "tactical_2_4_week":
        model = "2-4 week tactical"
        weights = {"upside": 0.20, "quality": 0.20, "momentum": 0.25, "catalyst": 0.25, "risk": 0.10}
    else:
        model = "Long-term"
        weights = {"upside": 0.25, "quality": 0.25, "momentum": 0.20, "catalyst": 0.15, "risk": 0.15}

    upside_component = upside_score * weights["upside"]
    quality_component = item.quality_score * weights["quality"]
    momentum_component = item.momentum_score * weights["momentum"]
    catalyst_component = item.catalyst_score * weights["catalyst"]
    risk_component = item.risk_score * weights["risk"]
    total = clamp(
        upside_component
        + quality_component
        + momentum_component
        + catalyst_component
        + risk_component
        - owned_penalty
        - speculative_penalty
    )
    return ScoreBreakdown(
        total=total,
        upside=upside_component,
        quality=quality_component,
        momentum=momentum_component,
        catalyst=catalyst_component,
        risk=risk_component,
        owned_penalty=owned_penalty,
        speculative_penalty=speculative_penalty,
        model=model,
    )


def action_for(
    item: ResearchInput,
    score: float,
    position_after_buy_pct: float,
    targets: Dict[str, object],
) -> str:
    watchlist_policy = evaluate_watchlist_policy(item.symbol, item.sleeve, targets)
    if watchlist_policy.get("blocked"):
        return "Watch" if score >= 55 else "Avoid"
    if item.sleeve == "etf":
        return "Add" if score >= 78 else "Watch"
    if position_after_buy_pct > 10:
        return "Hold" if score >= 60 else "Avoid"
    if score >= 80:
        return "Add"
    if score >= 72:
        return "Watch"
    if score >= 60:
        return "Watch"
    return "Avoid"


def score_summary(breakdown: ScoreBreakdown) -> str:
    penalties = []
    if breakdown.owned_penalty:
        penalties.append(f"owned -{breakdown.owned_penalty:.0f}")
    if breakdown.speculative_penalty:
        penalties.append(f"speculative -{breakdown.speculative_penalty:.0f}")
    penalty_text = f"; penalties: {', '.join(penalties)}" if penalties else ""
    return (
        f"{breakdown.model}: upside {breakdown.upside:.1f}, "
        f"quality {breakdown.quality:.1f}, momentum {breakdown.momentum:.1f}, "
        f"catalyst {breakdown.catalyst:.1f}, risk {breakdown.risk:.1f}{penalty_text}"
    )


def score_explanation(
    item: ResearchInput,
    breakdown: ScoreBreakdown,
    target: BlendedTarget | None = None,
    insight: InsightSignal | None = None,
    rationale: str = "",
) -> Dict[str, object]:
    """Build JSON-native score explainability without changing score math."""

    target_upside = target.upside_pct if target else item.upside_pct
    upside_raw = clamp(target_upside * 1.8)
    component_specs = [
        (
            "upside",
            "Upside",
            upside_raw,
            breakdown.upside,
            "Estimated upside from current price to blended target.",
            50.0,
        ),
        (
            "quality",
            "Quality",
            item.quality_score,
            breakdown.quality,
            "Business quality, margins, balance sheet, moat, and durability.",
            60.0,
        ),
        (
            "momentum",
            "Momentum",
            item.momentum_score,
            breakdown.momentum,
            "Trend, relative strength, price action, and market confirmation.",
            60.0,
        ),
        (
            "catalyst",
            "Catalyst",
            item.catalyst_score,
            breakdown.catalyst,
            "Earnings, guidance, product cycle, analyst revisions, sector momentum, or news.",
            60.0,
        ),
        (
            "risk",
            "Risk",
            item.risk_score,
            breakdown.risk,
            "Risk-adjusted setup. Higher is better; lower means more valuation, volatility, or thesis risk.",
            65.0,
        ),
    ]
    components: Dict[str, float] = {
        "upside": round(float(breakdown.upside), 4),
        "quality": round(float(breakdown.quality), 4),
        "momentum": round(float(breakdown.momentum), 4),
        "catalyst": round(float(breakdown.catalyst), 4),
        "risk": round(float(breakdown.risk), 4),
        "owned_penalty": -round(float(breakdown.owned_penalty), 4),
        "speculative_penalty": -round(float(breakdown.speculative_penalty), 4),
    }
    component_details: List[Dict[str, object]] = []
    driver_candidates: List[Dict[str, object]] = []
    risk_candidates: List[Dict[str, object]] = []
    for key, label, raw_value, points, description, risk_threshold in component_specs:
        detail = {
            "key": key,
            "label": label,
            "raw": round(float(raw_value), 4),
            "points": round(float(points), 4),
            "description": description,
        }
        component_details.append(detail)
        if points > 0:
            driver_candidates.append(
                {
                    "key": key,
                    "label": label,
                    "points": round(float(points), 4),
                    "description": description,
                }
            )
        if raw_value < risk_threshold:
            risk_candidates.append(
                {
                    "key": key,
                    "label": label,
                    "points": round(float(points), 4),
                    "severity": round(float(risk_threshold - raw_value), 4),
                    "description": f"{label} raw score is below the explainability threshold.",
                }
            )

    if breakdown.owned_penalty:
        risk_candidates.append(
            {
                "key": "owned_penalty",
                "label": "Owned penalty",
                "points": -round(float(breakdown.owned_penalty), 4),
                "severity": round(float(breakdown.owned_penalty), 4),
                "description": "Existing position reduces add attractiveness.",
            }
        )
    if breakdown.speculative_penalty:
        risk_candidates.append(
            {
                "key": "speculative_penalty",
                "label": "Speculative penalty",
                "points": -round(float(breakdown.speculative_penalty), 4),
                "severity": round(float(breakdown.speculative_penalty), 4),
                "description": "Speculative AI guardrail keeps the name review-only.",
            }
        )

    signal_overlay: Dict[str, object] | None = None
    if insight:
        overlay_parts = [
            ("evidence", insight.evidence_delta, insight.drivers[0] if len(insight.drivers) > 0 else ""),
            ("price_trend", insight.trend_delta, insight.drivers[1] if len(insight.drivers) > 1 else ""),
            ("target_confidence", insight.target_delta, insight.drivers[2] if len(insight.drivers) > 2 else ""),
            ("data_gap", insight.data_gap_delta, insight.drivers[3] if len(insight.drivers) > 3 else ""),
        ]
        signal_overlay = {
            "total_delta": round(float(insight.total_delta), 4),
            "final_score": round(float(insight.final_score), 4),
            "score_movement": insight.score_movement,
            "components": {
                key: {
                    "delta": round(float(delta), 4),
                    "description": description,
                }
                for key, delta, description in overlay_parts
            },
        }
        components["signal_overlay"] = round(float(insight.total_delta), 4)
        if insight.total_delta > 0:
            driver_candidates.append(
                {
                    "key": "signal_overlay",
                    "label": "Signal overlay",
                    "points": round(float(insight.total_delta), 4),
                    "description": insight.score_movement,
                }
            )
        for key, delta, description in overlay_parts:
            if delta < 0:
                risk_candidates.append(
                    {
                        "key": key,
                        "label": key.replace("_", " ").title(),
                        "points": round(float(delta), 4),
                        "severity": abs(round(float(delta), 4)),
                        "description": description,
                    }
                )

    top_drivers = sorted(
        driver_candidates,
        key=lambda candidate: float(candidate.get("points", 0)),
        reverse=True,
    )[:3]
    top_risks = sorted(
        risk_candidates,
        key=lambda candidate: float(candidate.get("severity", abs(float(candidate.get("points", 0))))),
        reverse=True,
    )[:3]
    return {
        "model": breakdown.model,
        "base_score": round(float(breakdown.total), 4),
        "final_score": round(float(insight.final_score if insight else breakdown.total), 4),
        "components": components,
        "component_details": component_details,
        "signal_overlay": signal_overlay,
        "top_drivers": top_drivers,
        "top_risks": top_risks,
        "rationale": rationale,
    }


def score_driver_rows(item: ResearchInput, breakdown: ScoreBreakdown, target: BlendedTarget | None) -> List[List[object]]:
    if breakdown.model == "Day trade":
        weights = {"upside": 0.05, "quality": 0.10, "momentum": 0.40, "catalyst": 0.25, "risk": 0.20}
    elif breakdown.model == "Weekly swing":
        weights = {"upside": 0.15, "quality": 0.15, "momentum": 0.35, "catalyst": 0.20, "risk": 0.15}
    elif breakdown.model == "2-4 week tactical":
        weights = {"upside": 0.20, "quality": 0.20, "momentum": 0.25, "catalyst": 0.25, "risk": 0.10}
    else:
        weights = {"upside": 0.25, "quality": 0.25, "momentum": 0.20, "catalyst": 0.15, "risk": 0.15}
    upside_pct = target.upside_pct if target else item.upside_pct
    upside_raw = clamp(upside_pct * 1.8)
    return [
        [
            "Upside",
            f"{upside_raw:.1f}",
            f"{weights['upside'] * 100:.0f}%",
            f"{breakdown.upside:.1f}",
            "Estimated upside from today's price to the blended target.",
        ],
        [
            "Quality",
            f"{item.quality_score:.1f}",
            f"{weights['quality'] * 100:.0f}%",
            f"{breakdown.quality:.1f}",
            "Business quality: growth durability, margins, cash flow, moat, and balance-sheet strength.",
        ],
        [
            "Momentum",
            f"{item.momentum_score:.1f}",
            f"{weights['momentum'] * 100:.0f}%",
            f"{breakdown.momentum:.1f}",
            "Market confirmation: trend, relative strength, price action, and demand for the stock.",
        ],
        [
            "Catalyst",
            f"{item.catalyst_score:.1f}",
            f"{weights['catalyst'] * 100:.0f}%",
            f"{breakdown.catalyst:.1f}",
            "Near-term drivers such as earnings, guidance, product cycle, analyst revisions, sector momentum, or news.",
        ],
        [
            "Risk",
            f"{item.risk_score:.1f}",
            f"{weights['risk'] * 100:.0f}%",
            f"{breakdown.risk:.1f}",
            "Risk-adjusted setup. Higher is better; lower reflects valuation, volatility, earnings, balance-sheet, or thesis risk.",
        ],
    ]


def score_explanation_html(
    item: ResearchInput,
    breakdown: ScoreBreakdown,
    target: BlendedTarget | None,
    insight: InsightSignal | None = None,
) -> str:
    penalty_items = []
    if breakdown.owned_penalty:
        penalty_items.append(f"Owned-position diversification penalty: -{breakdown.owned_penalty:.0f}")
    if breakdown.speculative_penalty:
        penalty_items.append(f"Speculative AI watchlist penalty: -{breakdown.speculative_penalty:.0f}")
    penalty_text = "; ".join(penalty_items) if penalty_items else "No score penalties applied."
    return f"""
      <div class="score-explanation">
        <h4>Score Explanation</h4>
        <p>{html.escape(breakdown.model)} scoring uses different weights based on the expected holding period. V1.6 adds a conservative transparent overlay for evidence, price trend, target confidence, and data gaps.</p>
        {html_table(["Driver", "Raw", "Weight", "Points", "Meaning"], score_driver_rows(item, breakdown, target), "score-driver-table")}
        <p><strong>Penalties:</strong> {html.escape(penalty_text)}</p>
        {insight_drivers_html(insight) if insight else ""}
      </div>
    """


def action_hover_html(
    action: str,
    rationale: str,
    item: ResearchInput,
    breakdown: ScoreBreakdown,
    target: BlendedTarget | None,
) -> str:
    tooltip = (
        f"<strong>{html.escape(action)} rationale</strong>"
        f"<span>{html.escape(rationale)}</span>"
        f"<span>Today: {html.escape(fmt_money(item.current_price) if item.current_price else 'Needs refresh')} · "
        f"Target: {html.escape(target_price_text(item, target))} · Upside: {html.escape(target_upside_text(item, target))}</span>"
        f"<span>Score: {html.escape(score_summary(breakdown))}</span>"
    )
    return (
        f'<span class="action-hover" tabindex="0">'
        f'<span class="pill {action_class(action)}">{html.escape(action)}</span>'
        f'<span class="action-tooltip" role="tooltip">{tooltip}</span>'
        f"</span>"
    )


def action_rationale(
    item: ResearchInput,
    action: str,
    breakdown: ScoreBreakdown,
    position_after_buy_pct: float,
    target: BlendedTarget | None = None,
    targets: Dict[str, object] | None = None,
) -> str:
    watchlist_policy = evaluate_watchlist_policy(item.symbol, item.sleeve, targets or {})
    if watchlist_policy.get("blocked"):
        return str(watchlist_policy.get("reason") or "Watchlist-only policy blocks buy-readiness.")
    if item.sleeve == "speculative_ai":
        return "Speculative AI is watchlist-only during the 2-3 week observation period."
    if position_after_buy_pct > 10:
        return "Adding would push the position above the 10% single-stock cap."
    if action == "Add":
        return "Score is high enough to add and the proposed buy stays within position caps."
    if action == "Watch":
        if item.current_price <= 0 or (item.target_price <= 0 and not target):
            return "Keep watching because price or target data needs refresh before acting."
        return "Score is not strong enough for an add, but the setup remains worth monitoring."
    if action == "Avoid":
        target_upside = target.upside_pct if target else item.upside_pct
        if target_upside < 0:
            return "Avoid for now because target upside is negative using current inputs."
        return "Avoid for now because the risk-adjusted score is too low."
    if action == "Hold":
        return "Hold because current ownership or risk limits make adding unattractive."
    return f"{action} based on the current score model."


BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}
DECISION_BLOCKING_INSIGHT_TYPES = {"Verification Needed", "Data Gap"}


def decision_safety_gate(
    row: Dict[str, object],
    decision_insight: DecisionInsight | None = None,
    targets: Dict[str, object] | None = None,
) -> Dict[str, object]:
    item = row.get("input")
    if not isinstance(item, ResearchInput):
        return {
            "safe_to_buy": False,
            "status": "Blocked",
            "candidate_action": str(row.get("action") or ""),
            "reasons": ["Missing recommendation input context"],
            "summary": "Missing recommendation input context.",
        }

    target = row.get("target")
    action = str(row.get("action") or "")
    target_status = data_status_for_target(item, target if isinstance(target, BlendedTarget) else None)
    confidence = target_confidence_text(item, target if isinstance(target, BlendedTarget) else None)
    reasons: List[str] = []
    watchlist_policy = evaluate_watchlist_policy(item.symbol, item.sleeve, targets or {})

    if action not in BUY_ACTIONS:
        reasons.append(f"{action or 'Current'} action is not a buy action")
    if watchlist_policy.get("blocked"):
        reasons.append(str(watchlist_policy.get("reason") or "Watchlist-only policy blocks buy-readiness."))
    if item.current_price <= 0:
        reasons.append("Missing current price")
    if target_status.startswith("Needs"):
        reasons.append(target_status)
    elif target_status == "Wide range":
        reasons.append("Wide target range")
    elif target_status == "Partial blend":
        reasons.append("Partial target blend")
    if confidence.lower() not in {"medium", "high"}:
        reasons.append(f"{confidence.title()} target confidence")

    if decision_insight and decision_insight.insight_type in DECISION_BLOCKING_INSIGHT_TYPES:
        if decision_insight.insight_type == "Verification Needed":
            reasons.append("Verification check is still open")
        else:
            reasons.append("Required data gap is still open")
    elif "blocked" in item.provider_notes.lower() or "failed" in item.provider_notes.lower():
        reasons.append("Provider verification is blocked")

    unique_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    safe_to_buy = not unique_reasons
    summary = "Decision-safe buy candidate." if safe_to_buy else "; ".join(unique_reasons)
    return {
        "safe_to_buy": safe_to_buy,
        "status": "Ready" if safe_to_buy else "Blocked",
        "candidate_action": action,
        "reasons": unique_reasons,
        "summary": summary,
        "watchlist_policy": watchlist_policy,
    }


def decision_summary_candidate(
    ranked: List[Dict[str, object]],
    decision_insights: Dict[str, DecisionInsight],
    targets: Dict[str, object] | None = None,
) -> tuple[Dict[str, object], Dict[str, object]]:
    buy_candidates = [
        row for row in ranked if str(row.get("action") or "") in BUY_ACTIONS and row["input"].sleeve != "etf"
    ]
    for row in buy_candidates:
        symbol = row["input"].symbol
        gate = decision_safety_gate(row, decision_insights.get(symbol), targets)
        if gate["safe_to_buy"]:
            return row, gate

    if buy_candidates:
        row = buy_candidates[0]
        return row, decision_safety_gate(row, decision_insights.get(row["input"].symbol), targets)
    if ranked:
        row = ranked[0]
        return row, decision_safety_gate(row, decision_insights.get(row["input"].symbol), targets)
    return {}, {
        "safe_to_buy": False,
        "status": "Blocked",
        "candidate_action": "",
        "reasons": ["No ranked candidates available"],
        "summary": "No ranked candidates available.",
    }


def fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def fmt_pct(value: float) -> str:
    return f"{value:,.1f}%"


def markdown_table(headers: List[str], rows: Iterable[List[object]]) -> str:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(output)


def html_table(
    headers: List[str],
    rows: Iterable[List[object]],
    css_class: str = "",
    raw_columns: Set[int] | None = None,
) -> str:
    raw_columns = raw_columns or set()
    class_attr = f' class="{css_class}"' if css_class else ""
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body = []
    for row in rows:
        body.append(
            "<tr>"
            + "".join(
                f"<td>{value if index in raw_columns else html.escape(str(value))}</td>"
                for index, value in enumerate(row)
            )
            + "</tr>"
        )
    return f"<table{class_attr}><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def action_class(action: str) -> str:
    return action.lower().replace(" ", "-")


def trade_type_label(value: str) -> str:
    labels = {
        "long_term": "Long term",
        "day_trade": "Day trade",
        "weekly_swing": "Weekly swing",
        "tactical_2_4_week": "2-4 week tactical",
        "etf": "ETF",
        "speculative_ai": "Speculative AI",
    }
    return labels.get(value, value.replace("_", " ").title())


def source_label(item: ResearchInput) -> str:
    price = item.price_source or "manual/stale"
    target = item.target_source or "manual/stale"
    return f"Price: {price}; Target: {target}"


def target_price_text(item: ResearchInput, target: BlendedTarget | None) -> str:
    if target:
        return fmt_money(target.target_price)
    return fmt_money(item.target_price) if item.target_price else "Needs refresh"


def target_upside_text(item: ResearchInput, target: BlendedTarget | None) -> str:
    if target:
        return fmt_pct(target.upside_pct)
    return fmt_pct(item.upside_pct) if item.upside_pct else "Needs refresh"


def target_confidence_text(item: ResearchInput, target: BlendedTarget | None) -> str:
    if target is None and item.current_price <= 0:
        return "Needs Review"
    return target.confidence.replace("_", " ").title() if target else item.confidence


def target_source_label(item: ResearchInput, target: BlendedTarget | None) -> str:
    if target:
        return f"Price: {item.price_source or 'manual/stale'}; Target: {target.blend_status}"
    return source_label(item)


def data_status_for_target(item: ResearchInput, target: BlendedTarget | None) -> str:
    if item.current_price <= 0:
        return "Needs price"
    if target:
        if target.blend_status.startswith("Single-source"):
            return "Partial blend"
        if "wide target range" in target.blend_status:
            return "Wide range"
        return "Blended"
    return data_status(item)


def data_status(item: ResearchInput) -> str:
    missing = []
    if item.current_price <= 0:
        missing.append("price")
    if item.target_price <= 0:
        missing.append("target")
    if missing:
        return "Needs " + "/".join(missing)
    if "Needs paid" in item.target_source:
        return "Needs paid target provider"
    return "OK"


def workflow_run_id_from_env() -> int | None:
    try:
        value = int(os.environ.get("STOCK_ENGINE_WORKFLOW_RUN_ID", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def price_reliability_counts(research: Iterable[ResearchInput]) -> Dict[str, int]:
    counts = {"fresh": 0, "fallback": 0, "stale": 0, "manual": 0, "missing": 0}
    for item in research:
        source = (item.price_source or "").lower()
        if item.current_price <= 0:
            counts["missing"] += 1
        elif "history close" in source:
            counts["fallback"] += 1
        elif "stale" in source:
            counts["stale"] += 1
        elif "manual" in source or not source:
            counts["manual"] += 1
        else:
            counts["fresh"] += 1
    return counts


def reliability_mode(counts: Dict[str, int]) -> str:
    if counts["missing"]:
        return "Degraded: missing prices"
    if counts["stale"]:
        return "Degraded: stale prices"
    if counts["fallback"]:
        return "Fallback: price history"
    if counts["manual"]:
        return "Manual price inputs"
    return "Fresh provider data"


def latest_provider_refresh_text() -> str:
    row = latest_successful_provider_refresh()
    if not row:
        return "No successful provider refresh recorded"
    return f"{row['provider']} at {row['refreshed_at']}"


def css_var_for_index(index: int) -> str:
    colors = [
        "#1d5fd0",
        "#137a49",
        "#9a6100",
        "#7c3aed",
        "#b42318",
        "#0f766e",
        "#475569",
    ]
    return colors[index % len(colors)]


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalized_source_name(source: str) -> str:
    labels = {
        "fmp": "Financial Modeling Prep",
        "financial modeling prep": "Financial Modeling Prep",
        "alpha vantage": "Alpha Vantage",
        "manual": "Manual input",
    }
    source_clean = source.strip()
    return labels.get(source_clean.lower(), source_clean or "Unknown")


FACT_VALUE_PATTERN = re.compile(
    r"^(?P<metric>[^:]+): (?P<value>-?[0-9]+(?:\.[0-9]+)?) "
    r"for period ending (?P<period>[0-9]{4}-[0-9]{2}-[0-9]{2}) from (?P<form>[^.]+)"
)


def latest_sec_facts_by_symbol() -> Dict[str, Dict[str, Dict[str, object]]]:
    if not DB_FILE.exists():
        return {}
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT symbol, title, summary, source_timestamp
        FROM research_evidence
        WHERE source_name = 'SEC EDGAR companyfacts API'
        ORDER BY source_timestamp DESC, id DESC
        """
    ).fetchall()
    conn.close()

    facts: Dict[str, Dict[str, Dict[str, object]]] = {}
    for row in rows:
        match = FACT_VALUE_PATTERN.search(str(row["summary"] or ""))
        if not match:
            continue
        symbol = str(row["symbol"]).upper()
        metric = match.group("metric").strip().lower()
        facts.setdefault(symbol, {})
        if metric in facts[symbol]:
            continue
        facts[symbol][metric] = {
            "value": to_float(match.group("value")),
            "period": match.group("period"),
            "form": match.group("form").strip(),
            "title": row["title"],
        }
    return facts


def peer_group_for_symbol(symbol: str, model_config: Dict[str, object]) -> tuple[str, Dict[str, object]]:
    return configured_peer_group_for_symbol(symbol, model_config)


def adjustment_from_score(
    score: float,
    basis: float,
    pct_per_point: float,
    max_abs: float,
) -> float:
    return max(-max_abs, min(max_abs, (score - basis) * pct_per_point))


def fundamental_target_row(
    item: ResearchInput,
    run_id: int,
    as_of_date: str,
    model_config: Dict[str, object],
    sec_facts: Dict[str, Dict[str, Dict[str, object]]],
) -> Dict[str, object] | None:
    if item.current_price <= 0:
        return None

    assumptions = assumptions_for_symbol(item.symbol, item.sleeve, model_config)
    source = fundamental_source_config(model_config)

    quality_adj = adjustment_from_score(
        item.quality_score,
        assumptions.quality_basis_score,
        assumptions.quality_pct_per_score_point,
        assumptions.quality_max_adjustment_pct,
    )
    catalyst_adj = adjustment_from_score(
        item.catalyst_score,
        assumptions.catalyst_basis_score,
        assumptions.catalyst_pct_per_score_point,
        assumptions.catalyst_max_adjustment_pct,
    )
    risk_penalty = max(
        0,
        min(
            assumptions.risk_max_penalty_pct,
            (assumptions.risk_basis_score - item.risk_score)
            * assumptions.risk_pct_per_score_point_below_basis,
        ),
    )

    facts = sec_facts.get(item.symbol, {})
    revenue = facts.get("revenue", {})
    operating_income = facts.get("operating income", {})
    operating_cash_flow = facts.get("operating cash flow", {})
    diluted_eps = facts.get("diluted eps", {})

    revenue_value = to_float(revenue.get("value"))
    operating_margin = (
        to_float(operating_income.get("value")) / revenue_value
        if revenue_value > 0 and operating_income
        else None
    )
    cash_flow_margin = (
        to_float(operating_cash_flow.get("value")) / revenue_value
        if revenue_value > 0 and operating_cash_flow
        else None
    )

    margin_adj = 0.0
    strong_margin_bonus = assumptions.strong_margin_bonus_pct
    negative_margin_penalty = assumptions.negative_margin_penalty_pct
    if operating_margin is not None and operating_margin < 0:
        margin_adj -= negative_margin_penalty
    elif cash_flow_margin is not None and cash_flow_margin < 0:
        margin_adj -= negative_margin_penalty / 2
    elif (
        operating_margin is not None
        and cash_flow_margin is not None
        and operating_margin >= assumptions.strong_operating_margin
        and cash_flow_margin >= assumptions.strong_cash_flow_margin
    ):
        margin_adj += strong_margin_bonus

    thin_input_penalty = assumptions.thin_revenue_penalty_pct if not revenue else 0
    if not (operating_income or operating_cash_flow or diluted_eps):
        thin_input_penalty += assumptions.thin_profitability_penalty_pct

    modeled_upside = max(
        assumptions.min_upside_pct,
        min(
            assumptions.max_upside_pct,
            assumptions.base_upside_pct + quality_adj + catalyst_adj + margin_adj - risk_penalty - thin_input_penalty,
        ),
    )
    target_price = item.current_price * (1 + modeled_upside / 100)

    confidence = (
        assumptions.complete_input_confidence
        if revenue and (operating_income or operating_cash_flow or diluted_eps)
        else assumptions.missing_input_confidence
    )
    if item.sleeve == "speculative_ai":
        confidence = assumptions.speculative_confidence

    range_width = to_float(
        assumptions.range_width_pct.get(confidence),
        0.12 if confidence == "medium" else 0.18,
    )
    target_low = target_price * (1 - range_width)
    target_high = target_price * (1 + range_width)

    metric_notes = []
    if revenue:
        metric_notes.append(
            f"revenue {to_float(revenue.get('value')):,.0f} from {revenue.get('form')} period {revenue.get('period')}"
        )
    if operating_margin is not None:
        metric_notes.append(f"operating margin {operating_margin * 100:.1f}%")
    if cash_flow_margin is not None:
        metric_notes.append(f"operating cash-flow margin {cash_flow_margin * 100:.1f}%")
    if diluted_eps:
        metric_notes.append(f"diluted EPS {to_float(diluted_eps.get('value')):,.2f}")
    if not metric_notes:
        metric_notes.append(assumptions.fallback_note)

    assumption_detail = assumptions.to_dict()
    assumption_detail.update(
        {
            "quality_adjustment_pct": round(quality_adj, 4),
            "catalyst_adjustment_pct": round(catalyst_adj, 4),
            "margin_adjustment_pct": round(margin_adj, 4),
            "risk_penalty_pct": round(risk_penalty, 4),
            "thin_input_penalty_pct": round(thin_input_penalty, 4),
            "modeled_upside_pct": round(modeled_upside, 4),
        }
    )

    notes = (
        f"Peer group {assumptions.peer_group}; "
        f"method {assumptions.primary_valuation_method}; "
        f"multiple {assumptions.primary_multiple}; "
        f"base upside {assumptions.base_upside_pct:.1f}%; "
        f"quality adj {quality_adj:+.1f}%; catalyst adj {catalyst_adj:+.1f}%; "
        f"margin adj {margin_adj:+.1f}%; risk/data penalty -{risk_penalty + thin_input_penalty:.1f}%. "
        + "; ".join(metric_notes)
        + f". Valuation cap: {assumptions.valuation_cap}. Peer notes: {assumptions.peer_notes}"
    )

    return {
        "run_id": run_id,
        "symbol": item.symbol,
        "target_type": "fundamental",
        "source_name": source["source_name"],
        "source_type": source["source_type"],
        "target_price": round(target_price, 4),
        "target_low": round(target_low, 4),
        "target_high": round(target_high, 4),
        "current_price": item.current_price,
        "upside_pct": round(modeled_upside, 4),
        "as_of_date": as_of_date,
        "freshness_days": 0,
        "confidence": confidence,
        "provider_endpoint": source["provider_endpoint"],
        "raw_payload_ref": "",
        "notes": notes,
        "assumptions": assumption_detail,
    }


def latest_price_history_by_symbol(limit_per_symbol: int = 260) -> Dict[str, List[Dict[str, float]]]:
    if not DB_FILE.exists():
        return {}
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT symbol, price_date, high, low, close, adjusted_close, volume, provider
        FROM price_history
        ORDER BY symbol, price_date DESC
        """
    ).fetchall()
    conn.close()

    grouped: Dict[str, List[Dict[str, float]]] = {}
    for row in rows:
        symbol = str(row["symbol"]).upper()
        grouped.setdefault(symbol, [])
        if len(grouped[symbol]) >= limit_per_symbol:
            continue
        close = to_float(row["adjusted_close"]) or to_float(row["close"])
        grouped[symbol].append(
            {
                "date": row["price_date"],
                "high": to_float(row["high"]) or close,
                "low": to_float(row["low"]) or close,
                "close": close,
                "provider": row["provider"],
                "volume": to_float(row["volume"]),
            }
        )
    return {symbol: list(reversed(values)) for symbol, values in grouped.items()}


def apply_price_history_fallback(
    research: List[ResearchInput],
    price_history: Dict[str, List[Dict[str, float]]],
) -> None:
    for item in research:
        if item.current_price > 0:
            continue
        history = price_history.get(item.symbol, [])
        if not history:
            continue
        latest = history[-1]
        close = to_float(latest.get("close"))
        if close <= 0:
            continue
        provider = str(latest.get("provider") or "price history")
        item.current_price = close
        item.price_source = f"{provider} history close"


def average(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def technical_target_row(
    item: ResearchInput,
    run_id: int,
    as_of_date: str,
    model_config: Dict[str, object],
    price_history: Dict[str, List[Dict[str, float]]],
) -> Dict[str, object] | None:
    target = calculate_technical_target(
        symbol=item.symbol,
        current_price=item.current_price,
        sleeve=item.sleeve,
        as_of_date=as_of_date,
        model_config=model_config,
        history=price_history.get(item.symbol, []),
    )
    if not target:
        return None

    return {
        "run_id": run_id,
        "symbol": item.symbol,
        "target_type": "technical",
        "source_name": "Internal technical model",
        "source_type": "model",
        "target_price": target["target_price"],
        "target_low": target["target_low"],
        "target_high": target["target_high"],
        "current_price": target["current_price"],
        "upside_pct": target["upside_pct"],
        "as_of_date": as_of_date,
        "freshness_days": target["freshness_days"],
        "confidence": target["confidence"],
        "provider_endpoint": target["provider_endpoint"],
        "raw_payload_ref": "",
        "notes": target["notes"],
    }


def target_source_rows(
    research: Iterable[ResearchInput],
    run_id: int,
    as_of_date: str,
    targets: Dict[str, object],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    model_config = targets.get("fundamental_target_model", {})
    technical_config = targets.get("technical_target_model", {})
    manual_analyst_targets = load_manual_analyst_targets()
    sec_facts = latest_sec_facts_by_symbol()
    price_history = latest_price_history_by_symbol()
    for item in research:
        if item.target_price > 0:
            source_name = normalized_source_name(item.target_source)
            if source_name == "Financial Modeling Prep":
                current_price = item.current_price if item.current_price > 0 else None
                upside = item.upside_pct if item.current_price > 0 else None
                rows.append(
                    {
                        "run_id": run_id,
                        "symbol": item.symbol,
                        "target_type": "analyst",
                        "source_name": source_name,
                        "source_type": "data_provider",
                        "target_price": item.target_price,
                        "target_low": None,
                        "target_high": None,
                        "current_price": current_price,
                        "upside_pct": upside,
                        "as_of_date": as_of_date,
                        "freshness_days": 0,
                        "confidence": "low",
                        "provider_endpoint": "Financial Modeling Prep price-target-consensus",
                        "raw_payload_ref": "",
                        "notes": "Captured from current research_inputs.csv target_source and used as analyst input in the blended target model.",
                    }
                )
        for target in manual_analyst_targets.get(item.symbol, []):
            target_price = to_float(target.get("target_price"))
            if target_price <= 0:
                continue
            current_price = item.current_price if item.current_price > 0 else None
            upside = (
                ((target_price - item.current_price) / item.current_price) * 100
                if item.current_price > 0
                else None
            )
            rows.append(
                {
                    "run_id": run_id,
                    "symbol": item.symbol,
                    "target_type": "analyst",
                    "source_name": target.get("source_name") or "Manual analyst target",
                    "source_type": "manual_analyst_target",
                    "target_price": target_price,
                    "target_low": target.get("target_low"),
                    "target_high": target.get("target_high"),
                    "current_price": current_price,
                    "upside_pct": upside,
                    "as_of_date": target.get("as_of_date") or as_of_date,
                    "freshness_days": 0,
                    "confidence": target.get("confidence") or "low",
                    "provider_endpoint": target.get("provider_endpoint") or "manual_analyst_targets.csv",
                    "raw_payload_ref": "",
                    "notes": target.get("notes") or "Supplemental analyst target loaded from config/manual_analyst_targets.csv.",
                }
            )
        fundamental_row = fundamental_target_row(item, run_id, as_of_date, model_config, sec_facts)
        if fundamental_row:
            rows.append(fundamental_row)
        technical_row = technical_target_row(
            item,
            run_id,
            as_of_date,
            technical_config,
            price_history,
        )
        if technical_row:
            rows.append(technical_row)
    return rows


def blended_target_rows(
    target_rows: List[Dict[str, object]],
    run_id: int,
    targets: Dict[str, object],
    research_by_symbol: Dict[str, ResearchInput],
    provider_gaps: Iterable[object] = (),
) -> tuple[Dict[str, BlendedTarget], List[Dict[str, object]]]:
    blend_config = targets.get("blended_target_model", {})
    long_term_weights = (
        blend_config.get("long_term_weights", {}) if isinstance(blend_config, dict) else {}
    )
    short_term_weights = (
        blend_config.get("short_term_weights", {}) if isinstance(blend_config, dict) else {}
    )
    fallback_weights = (
        blend_config.get("fallback_weights", {}) if isinstance(blend_config, dict) else {}
    )
    allowed_types = {"analyst", "fundamental", "technical"}
    confidence_rules = blend_config.get("confidence_rules", {}) if isinstance(blend_config, dict) else {}

    def gap_symbol(row: object) -> str:
        if isinstance(row, dict):
            return str(row.get("symbol") or "").upper()
        try:
            return str(row["symbol"] or "").upper()  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            return ""

    provider_gaps_by_symbol: Dict[str, List[object]] = {}
    for gap in provider_gaps:
        symbol = gap_symbol(gap)
        if symbol:
            provider_gaps_by_symbol.setdefault(symbol, []).append(gap)

    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in target_rows:
        target_type = str(row.get("target_type") or "")
        if target_type not in allowed_types:
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(row)

    blended: Dict[str, BlendedTarget] = {}
    db_rows: List[Dict[str, object]] = []
    for symbol, rows in grouped.items():
        usable = [row for row in rows if to_float(row.get("target_price")) > 0 and to_float(row.get("current_price")) > 0]
        if not usable:
            continue

        source_weights = []
        item = research_by_symbol.get(symbol)
        if item and item.sleeve == "short_term":
            configured_weights = short_term_weights
        elif item and item.trade_type in {"day_trade", "weekly_swing", "tactical_2_4_week"}:
            configured_weights = short_term_weights
        else:
            configured_weights = long_term_weights or fallback_weights
        for row in usable:
            target_type = str(row.get("target_type"))
            base_weight = to_float(configured_weights.get(target_type), 0)
            if base_weight <= 0:
                base_weight = to_float(fallback_weights.get(target_type), 0)
            source_weights.append((row, base_weight))
        total_weight = sum(weight for _, weight in source_weights)
        if total_weight <= 0:
            source_weights = [(row, 1.0) for row in usable]
            total_weight = float(len(source_weights))

        weighted_target = sum(to_float(row.get("target_price")) * weight for row, weight in source_weights) / total_weight
        current_price = to_float(usable[0].get("current_price"))
        upside_pct = ((weighted_target - current_price) / current_price) * 100 if current_price > 0 else 0

        lows = [to_float(row.get("target_low")) for row in usable if to_float(row.get("target_low")) > 0]
        highs = [to_float(row.get("target_high")) for row in usable if to_float(row.get("target_high")) > 0]
        raw_targets = [to_float(row.get("target_price")) for row in usable]
        target_low = min(lows + raw_targets) if raw_targets else None
        target_high = max(highs + raw_targets) if raw_targets else None

        types = {str(row.get("target_type")) for row in usable}
        if {"analyst", "fundamental", "technical"}.issubset(types):
            blend_status = "Analyst + fundamental + technical"
            confidence = "medium"
        elif {"analyst", "fundamental"}.issubset(types):
            blend_status = "Analyst + fundamental"
            confidence = "medium"
        elif {"fundamental", "technical"}.issubset(types):
            blend_status = "Fundamental + technical"
            confidence = "medium" if item and item.sleeve == "short_term" else "low"
        elif {"analyst", "technical"}.issubset(types):
            blend_status = "Analyst + technical"
            confidence = "medium"
        elif "fundamental" in types:
            blend_status = "Single-source fundamental"
            confidence = "low"
        elif "analyst" in types:
            blend_status = "Single-source analyst"
            confidence = "low"
        elif "technical" in types:
            blend_status = "Single-source technical"
        else:
            blend_status = "Single-source"

        wide_range = False
        if len(types) >= 2 and target_low and target_high and current_price > 0:
            spread_pct = ((target_high - target_low) / current_price) * 100
            if spread_pct > 45:
                wide_range = True
        if item and "stale" in (item.price_source or "").lower():
            if "stale price" not in blend_status:
                blend_status += "; stale price"
        calibrated = calibrate_target_confidence(
            usable,
            current_price=current_price,
            item=item,
            provider_gaps=provider_gaps_by_symbol.get(symbol, []),
            technical_target_needed_for_high=bool(
                confidence_rules.get("technical_target_needed_for_high", True)
            ),
            wide_range_downgrades_confidence=bool(
                confidence_rules.get("wide_range_downgrades_confidence", True)
            ),
        )
        confidence = calibrated.label
        if wide_range and "wide target range" not in blend_status:
            blend_status += "; wide target range"
        if "provider_gap_affects_target" in calibrated.reason_codes:
            blend_status += "; provider gap affects target confidence"
        if "stale_target" in calibrated.reason_codes and "stale target" not in blend_status:
            blend_status += "; stale target"

        weight_parts = {
            str(row.get("target_type")): round(weight / total_weight, 4)
            for row, weight in source_weights
        }
        source_names = sorted({str(row.get("source_name") or row.get("target_type")) for row in usable})
        confidence_reason_text = ", ".join(calibrated.reason_codes)
        notes = (
            f"{blend_status}; sources: {', '.join(source_names)}; "
            f"weights: {', '.join(f'{name} {weight:.0%}' for name, weight in weight_parts.items())}; "
            f"confidence reasons: {confidence_reason_text}."
        )
        blend = BlendedTarget(
            symbol=symbol,
            target_price=round(weighted_target, 4),
            target_low=round(target_low, 4) if target_low else None,
            target_high=round(target_high, 4) if target_high else None,
            current_price=current_price,
            upside_pct=round(upside_pct, 4),
            confidence=confidence,
            source_count=len(usable),
            blend_status=blend_status,
            sources_label=", ".join(source_names),
            notes=notes,
            confidence_reasons=calibrated.reason_codes,
        )
        blended[symbol] = blend
        db_rows.append(
            {
                "run_id": run_id,
                "symbol": symbol,
                "blended_target": blend.target_price,
                "target_low": blend.target_low,
                "target_high": blend.target_high,
                "current_price": current_price,
                "upside_pct": blend.upside_pct,
                "target_confidence": confidence,
                "source_count": len(usable),
                "blend_status": blend_status,
                "weights_json": json.dumps(weight_parts, sort_keys=True),
                "notes": notes,
            }
        )
    return blended, db_rows


def latest_target_sources_by_symbol(limit_per_symbol: int = 4) -> Dict[str, List[Dict[str, object]]]:
    if not DB_FILE.exists():
        return {}
    conn = init_db()
    conn.row_factory = sqlite3.Row
    latest_run = conn.execute(
        """
        SELECT run_id
        FROM target_sources
        WHERE run_id IS NOT NULL
        ORDER BY run_id DESC
        LIMIT 1
        """
    ).fetchone()
    run_filter = int(latest_run["run_id"]) if latest_run else None
    where_clause = "WHERE run_id = ?" if run_filter is not None else ""
    params = (run_filter,) if run_filter is not None else ()
    rows = conn.execute(
        f"""
        SELECT symbol, target_type, source_name, source_type, target_price, target_low,
               target_high, current_price, upside_pct, confidence, as_of_date, notes
        FROM target_sources
        {where_clause}
        ORDER BY id DESC
        LIMIT 500
        """,
        params,
    ).fetchall()
    conn.close()
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        symbol = row["symbol"]
        grouped.setdefault(symbol, [])
        if len(grouped[symbol]) < limit_per_symbol:
            grouped[symbol].append(dict(row))
    return grouped


def target_counts_by_symbol(target_rows: Iterable[Dict[str, object]]) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {}
    for row in target_rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        counts.setdefault(symbol, {"analyst": 0, "all": 0})
        counts[symbol]["all"] += 1
        if str(row.get("target_type") or "") == "analyst":
            counts[symbol]["analyst"] += 1
    return counts


EXPECTED_TARGET_INPUTS = ("analyst", "fundamental", "technical")


def target_source_display_type(row: Dict[str, object]) -> str:
    source_type = str(row.get("source_type") or "").lower()
    target_type = str(row.get("target_type") or "").lower()
    if "manual" in source_type:
        return "manual"
    if target_type in {"analyst", "fundamental", "technical"}:
        return target_type
    if "provider" in source_type:
        return "provider-derived"
    return target_type or "other"


def target_freshness_label(row: Dict[str, object]) -> str:
    raw_days = row.get("freshness_days")
    if raw_days in (None, ""):
        return "Unknown freshness"
    days = int(to_float(raw_days))
    if days <= 7:
        status = "Fresh"
    elif days <= 30:
        status = "Current"
    elif days <= 90:
        status = "Aging"
    else:
        status = "Stale"
    return f"{status} ({days} days)"


def target_row_has_wide_range(row: Dict[str, object]) -> bool:
    current = to_float(row.get("current_price"))
    low = to_float(row.get("target_low"))
    high = to_float(row.get("target_high"))
    if current <= 0 or low <= 0 or high <= 0:
        return False
    return ((high - low) / current) * 100 > 45


def target_display_confidence(target: BlendedTarget | None, blend_label: str) -> str:
    confidence = target.confidence if target else "needs review"
    if confidence.lower() == "high" and blend_label != "full blend":
        return "medium"
    return confidence


def target_drilldown_for_symbol(
    symbol: str,
    target_rows: List[Dict[str, object]],
    target: BlendedTarget | None,
    item: ResearchInput | None = None,
) -> Dict[str, object]:
    usable_rows = [
        row for row in target_rows
        if str(row.get("symbol") or "").upper() == symbol.upper()
        and to_float(row.get("target_price")) > 0
    ]
    raw_types = {
        str(row.get("target_type") or "").lower()
        for row in usable_rows
        if str(row.get("target_type") or "").lower()
    }
    missing_inputs = [target_type for target_type in EXPECTED_TARGET_INPUTS if target_type not in raw_types]

    if not usable_rows:
        blend_label = "missing input"
    elif len(raw_types) >= len(EXPECTED_TARGET_INPUTS) and not missing_inputs:
        blend_label = "full blend"
    elif len(raw_types) >= 2:
        blend_label = "partial blend"
    else:
        blend_label = "single-source target"

    stale_target = any(target_freshness_label(row).startswith("Stale") for row in usable_rows)
    if item and "stale" in (item.price_source or "").lower():
        stale_target = True
    wide_range = any(target_row_has_wide_range(row) for row in usable_rows)
    if target and "wide target range" in target.blend_status:
        wide_range = True

    labels = [blend_label]
    if stale_target:
        labels.append("stale target")
    if wide_range:
        labels.append("wide range")
    labels.extend(f"missing input: {target_type}" for target_type in missing_inputs)

    source_entries = []
    for row in usable_rows:
        low = row.get("target_low")
        high = row.get("target_high")
        range_text = "n/a"
        if low not in (None, "") and high not in (None, ""):
            range_text = f"{fmt_money(to_float(low))}-{fmt_money(to_float(high))}"
        assumptions = row.get("assumptions")
        assumptions = assumptions if isinstance(assumptions, dict) else {}
        source_entries.append(
            {
                "symbol": symbol.upper(),
                "target_type": target_source_display_type(row),
                "original_target_type": str(row.get("target_type") or "other"),
                "source_name": str(row.get("source_name") or "Unknown"),
                "source_type": str(row.get("source_type") or "other"),
                "target_price": to_float(row.get("target_price")),
                "target_price_text": fmt_money(to_float(row.get("target_price"))),
                "target_low": low,
                "target_high": high,
                "range_text": range_text,
                "as_of_date": str(row.get("as_of_date") or "unknown"),
                "freshness": target_freshness_label(row),
                "confidence": str(row.get("confidence") or "unknown"),
                "notes": str(row.get("notes") or ""),
                "assumptions": assumptions,
                "assumptions_summary": "; ".join(
                    str(part)
                    for part in (
                        assumptions.get("peer_group"),
                        assumptions.get("primary_valuation_method"),
                        assumptions.get("valuation_cap"),
                    )
                    if part
                ),
            }
        )

    target_low = target.target_low if target else None
    target_high = target.target_high if target else None
    blended_range_text = "n/a"
    if target_low is not None and target_high is not None:
        blended_range_text = f"{fmt_money(target_low)}-{fmt_money(target_high)}"
    confidence = target_display_confidence(target, blend_label)

    return {
        "symbol": symbol.upper(),
        "blend_label": blend_label,
        "blend_status": target.blend_status if target else "Missing usable target inputs",
        "labels": labels,
        "target_price": target.target_price if target else None,
        "target_price_text": fmt_money(target.target_price) if target else "Needs target",
        "target_low": target_low,
        "target_high": target_high,
        "range_text": blended_range_text,
        "wide_range": wide_range,
        "stale_target": stale_target,
        "missing_inputs": missing_inputs,
        "confidence": confidence,
        "source_count": len(usable_rows),
        "source_names": [entry["source_name"] for entry in source_entries],
        "sources": source_entries,
    }


def target_drilldowns_by_symbol(
    ranked: List[Dict[str, object]],
    target_rows: List[Dict[str, object]],
) -> Dict[str, Dict[str, object]]:
    drilldowns: Dict[str, Dict[str, object]] = {}
    ranked_symbols = {
        row["input"].symbol
        for row in ranked
        if isinstance(row.get("input"), ResearchInput)
    }
    target_symbols = {
        str(row.get("symbol") or "").upper()
        for row in target_rows
        if str(row.get("symbol") or "").strip()
    }
    for symbol in sorted(ranked_symbols | target_symbols):
        ranked_row = next(
            (
                row for row in ranked
                if isinstance(row.get("input"), ResearchInput)
                and row["input"].symbol == symbol
            ),
            {},
        )
        item = ranked_row.get("input") if isinstance(ranked_row.get("input"), ResearchInput) else None
        target = ranked_row.get("target") if isinstance(ranked_row.get("target"), BlendedTarget) else None
        drilldowns[symbol] = target_drilldown_for_symbol(symbol, target_rows, target, item)
    return drilldowns


def target_drilldown_table_rows(
    ranked: List[Dict[str, object]],
    drilldowns: Dict[str, Dict[str, object]],
) -> List[List[object]]:
    rows: List[List[object]] = []
    for rank, row in enumerate(ranked, start=1):
        item = row["input"]
        drilldown = drilldowns.get(item.symbol, {})
        labels = ", ".join(str(label) for label in drilldown.get("labels", []))
        missing = ", ".join(str(value) for value in drilldown.get("missing_inputs", [])) or "None"
        source_names = ", ".join(str(value) for value in drilldown.get("source_names", [])) or "None"
        rows.append(
            [
                rank,
                item.symbol,
                drilldown.get("blend_label", "missing input"),
                drilldown.get("target_price_text", "Needs target"),
                drilldown.get("range_text", "n/a"),
                drilldown.get("confidence", "needs review"),
                int(drilldown.get("source_count") or 0),
                missing,
                labels,
                source_names,
            ]
        )
    return rows


def latest_score_history_by_symbol(limit_per_symbol: int = 8) -> Dict[str, List[Dict[str, object]]]:
    if not DB_FILE.exists():
        return {}
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT report_date, created_at, symbol, action, score, current_price,
               target_price, upside_pct, target_confidence, data_status
        FROM recommendation_scores
        ORDER BY symbol, run_id DESC, id DESC
        """
    ).fetchall()
    conn.close()
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        symbol = str(row["symbol"]).upper()
        grouped.setdefault(symbol, [])
        if len(grouped[symbol]) >= limit_per_symbol:
            continue
        grouped[symbol].append(dict(row))
    return {symbol: list(reversed(values)) for symbol, values in grouped.items()}


def sparkline_html(values: List[float]) -> str:
    if not values:
        return '<span class="sparkline-empty">No history</span>'
    low = min(values)
    high = max(values)
    spread = high - low
    bars = []
    for value in values:
        height = 28 if spread <= 0 else 8 + ((value - low) / spread) * 32
        bars.append(
            f'<span class="spark-bar" style="height:{height:.1f}px" title="{value:.1f}"></span>'
        )
    return f'<span class="sparkline">{"".join(bars)}</span>'


def score_history_rows(
    ranked: List[Dict[str, object]],
    history_by_symbol: Dict[str, List[Dict[str, object]]],
) -> List[List[object]]:
    rows = []
    for row in ranked:
        item = row["input"]
        history = history_by_symbol.get(item.symbol, [])
        scores = [to_float(point.get("score")) for point in history]
        previous = scores[-2] if len(scores) >= 2 else None
        latest = scores[-1] if scores else float(row["score"])
        change = latest - previous if previous is not None else 0.0
        rows.append(
            [
                item.symbol,
                item.company,
                f"{latest:.1f}",
                f"{change:+.1f}" if previous is not None else "New",
                str(history[-1].get("action") if history else row["action"]),
                sparkline_html(scores),
                str(history[-1].get("data_status") if history else data_status_for_target(item, row.get("target"))),
            ]
        )
    return rows


def change_marker_for_row(
    row: Dict[str, object],
    history_by_symbol: Dict[str, List[Dict[str, object]]],
) -> Dict[str, str]:
    item = row["input"]
    target = row.get("target")
    history = history_by_symbol.get(item.symbol, [])
    if len(history) < 2:
        return {
            "label": "New",
            "note": "No prior stored run for comparison.",
            "class": "change-new",
        }

    previous = history[-2]
    previous_action = str(previous.get("action") or "")
    current_action = str(row.get("action") or "")
    if previous_action and previous_action != current_action:
        return {
            "label": "Action changed",
            "note": f"Action changed from {previous_action} to {current_action}.",
            "class": "change-action",
        }

    previous_score = to_float(previous.get("score"))
    current_score = float(row.get("score") or 0)
    score_delta = current_score - previous_score
    if abs(score_delta) >= 1.0:
        direction_class = "change-up" if score_delta > 0 else "change-down"
        return {
            "label": f"Score {score_delta:+.1f}",
            "note": f"Score moved {score_delta:+.1f} since last run.",
            "class": direction_class,
        }

    previous_target = to_float(previous.get("target_price"))
    current_target = target.target_price if target else item.target_price
    if previous_target > 0 and current_target > 0:
        target_delta_pct = ((current_target - previous_target) / previous_target) * 100
        if abs(target_delta_pct) >= 2.0:
            direction_class = "change-up" if target_delta_pct > 0 else "change-down"
            return {
                "label": f"Target {target_delta_pct:+.1f}%",
                "note": f"Target moved {target_delta_pct:+.1f}% since last run.",
                "class": direction_class,
            }

    return {
        "label": "No material change",
        "note": "No action, score, or target movement crossed the display threshold.",
        "class": "change-none",
    }


def change_marker_html(marker: Dict[str, str]) -> str:
    return (
        f'<span class="change-badge {html.escape(marker["class"])}" '
        f'title="{html.escape(marker["note"])}">'
        f'{html.escape(marker["label"])}</span>'
    )


def latest_evidence_by_symbol(limit_per_symbol: int = 5) -> Dict[str, List[Dict[str, object]]]:
    if not DB_FILE.exists():
        return {}
    conn = init_db()
    conn.row_factory = sqlite3.Row
    direct_rows = conn.execute(
        """
        SELECT id, symbol AS display_symbol, symbol AS original_symbol,
               evidence_type, source_name, source_type, source_url,
               source_timestamp, title, summary, confidence, corroboration_status,
               NULL AS matched_text, NULL AS tag_match_type, NULL AS tag_confidence,
               NULL AS tag_confidence_bucket, NULL AS tag_match_reason
        FROM research_evidence
        ORDER BY id DESC
        LIMIT 1000
        """
    ).fetchall()
    tagged_rows = conn.execute(
        """
        SELECT e.id, t.symbol AS display_symbol, e.symbol AS original_symbol,
               e.evidence_type, e.source_name, e.source_type, e.source_url,
               e.source_timestamp, e.title, e.summary, e.confidence,
               e.corroboration_status, t.matched_text, t.match_type AS tag_match_type,
               t.confidence AS tag_confidence, t.confidence_bucket AS tag_confidence_bucket,
               t.match_reason AS tag_match_reason
        FROM evidence_symbol_tags t
        JOIN research_evidence e ON e.id = t.evidence_id
        ORDER BY e.id DESC, t.confidence DESC
        LIMIT 1000
        """
    ).fetchall()
    conn.close()
    grouped: Dict[str, List[Dict[str, object]]] = {}
    rows = sorted([*direct_rows, *tagged_rows], key=lambda row: int(row["id"]), reverse=True)
    seen: Set[tuple[str, int]] = set()
    for row in rows:
        symbol = row["display_symbol"]
        key = (symbol, int(row["id"]))
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(symbol, [])
        if len(grouped[symbol]) < limit_per_symbol:
            grouped[symbol].append(
                {
                    "id": row["id"],
                    "symbol": row["display_symbol"],
                    "original_symbol": row["original_symbol"],
                    "evidence_type": row["evidence_type"],
                    "source_name": row["source_name"],
                    "source_type": row["source_type"],
                    "source_url": row["source_url"],
                    "source_timestamp": row["source_timestamp"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "confidence": row["confidence"],
                    "corroboration_status": row["corroboration_status"],
                    "matched_text": row["matched_text"],
                    "tag_match_type": row["tag_match_type"],
                    "tag_confidence": row["tag_confidence"],
                    "tag_confidence_bucket": row["tag_confidence_bucket"],
                    "tag_match_reason": row["tag_match_reason"],
                }
            )
    return grouped


def latest_score_signals_by_symbol(limit_per_symbol: int = 5) -> Dict[str, List[Dict[str, object]]]:
    if not DB_FILE.exists():
        return {}
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT symbol, signal_date, signal_type, metric_name, raw_value,
               normalized_delta, confidence, source_name, source_type,
               source_ref, freshness_days, signal_mode, notes
        FROM score_signals
        WHERE signal_mode IN ('active', 'shadow')
        ORDER BY signal_date DESC, CASE signal_mode WHEN 'active' THEN 0 ELSE 1 END, id DESC
        LIMIT 2000
        """
    ).fetchall()
    conn.close()
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        symbol = str(row["symbol"] or "").upper()
        grouped.setdefault(symbol, [])
        if len(grouped[symbol]) < limit_per_symbol:
            grouped[symbol].append(dict(row))
    return grouped


def score_signal_counts(signals_by_symbol: Dict[str, List[Dict[str, object]]]) -> Dict[str, int]:
    if not DB_FILE.exists():
        return {
            "symbols": sum(1 for rows in signals_by_symbol.values() if rows),
            "signals": sum(len(rows) for rows in signals_by_symbol.values()),
        }
    conn = init_db()
    row = conn.execute(
        """
        SELECT COUNT(*) AS signals, COUNT(DISTINCT symbol) AS symbols
        FROM score_signals
        WHERE signal_mode = 'active'
        """
    ).fetchone()
    conn.close()
    return {"signals": int(row[0] or 0), "symbols": int(row[1] or 0)}


def score_signal_health_rows() -> List[List[object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    rows = conn.execute(
        """
        SELECT signal_type, COUNT(*) AS count, COUNT(DISTINCT symbol) AS symbols,
               ROUND(SUM(normalized_delta), 2) AS total_delta,
               MAX(created_at) AS latest
        FROM score_signals
        WHERE signal_mode = 'active'
        GROUP BY signal_type
        ORDER BY count DESC
        """
    ).fetchall()
    conn.close()
    return [
        [
            row[0],
            int(row[1] or 0),
            int(row[2] or 0),
            f"{to_float(row[3]):+.2f}",
            row[4] or "",
            "Active V1.6 score overlay",
        ]
        for row in rows
    ]


def latest_source_quality_rows(limit: int = 80) -> List[Dict[str, object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT q.*
        FROM source_quality_metrics q
        JOIN (
            SELECT source_name, MAX(metric_date) AS latest_metric_date
            FROM source_quality_metrics
            GROUP BY source_name
        ) latest
          ON latest.source_name = q.source_name
         AND latest.latest_metric_date = q.metric_date
        ORDER BY
            CASE q.quality_label
                WHEN 'blocked' THEN 0
                WHEN 'needs_review' THEN 1
                WHEN 'stale' THEN 2
                WHEN 'not_enough_data' THEN 3
                WHEN 'useful_context' THEN 4
                WHEN 'high_signal' THEN 5
                ELSE 9
            END,
            q.source_name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def source_quality_summary(rows: List[Dict[str, object]]) -> Dict[str, int]:
    summary: Dict[str, int] = {
        "high_signal": 0,
        "useful_context": 0,
        "needs_review": 0,
        "blocked": 0,
        "stale": 0,
        "not_enough_data": 0,
    }
    for row in rows:
        label = str(row.get("quality_label") or "")
        summary[label] = summary.get(label, 0) + 1
    return summary


LEARNING_REVIEW_NOTE = (
    "Review-only learning outputs. Manual journal entries, recommendation outcomes, "
    "catalyst follow-through, source usefulness, decision-safety effectiveness, and AI "
    "synthesis review do not change scores, actions, targets, target confidence, "
    "suggested amounts, decision gates, source weights, broker behavior, or trading."
)


def count_by_label(rows: Iterable[Dict[str, object]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


def latest_rows(rows: Iterable[Dict[str, object]], limit: int = 8) -> List[Dict[str, object]]:
    visible = [dict(row) for row in rows]
    return list(reversed(visible[-limit:]))


def learning_section_error(section: str, exc: Exception) -> Dict[str, object]:
    return {
        "review_only": True,
        "available": False,
        "summary": {"error": str(exc)},
        "rows": [],
        "note": f"{section} learning data could not be loaded; current recommendations are unaffected.",
    }


def manual_journal_learning(limit: int = 12) -> Dict[str, object]:
    entries = list_manual_journal_entries(limit=limit)
    return {
        "review_only": True,
        "available": bool(entries),
        "summary": {
            "entry_count": len(entries),
            "actions": count_by_label(entries, "action_taken"),
        },
        "recent_actions": latest_rows(entries, limit),
        "empty_state": "No manual journal entries recorded yet.",
    }


def recommendation_outcome_learning(limit: int = 80) -> Dict[str, object]:
    review = build_recommendation_outcome_review(limit=limit, windows=(20,))
    outcomes = [dict(row) for row in review.get("outcomes", []) if isinstance(row, dict)]
    return {
        "review_only": True,
        "available": bool(outcomes),
        "summary": {
            **dict(review.get("metadata", {}) if isinstance(review.get("metadata"), dict) else {}),
            "outcomes_by_status": count_by_label(outcomes, "outcome_status"),
        },
        "top_outcomes": latest_rows(outcomes),
        "empty_state": "Not enough recommendation outcome history yet.",
    }


def catalyst_learning(limit: int = 80) -> Dict[str, object]:
    review = build_catalyst_follow_through_review(limit=limit, windows=(20,))
    outcomes = [dict(row) for row in review.get("outcomes", []) if isinstance(row, dict)]
    return {
        "review_only": True,
        "available": bool(outcomes),
        "summary": {
            **dict(review.get("metadata", {}) if isinstance(review.get("metadata"), dict) else {}),
            "outcomes_by_label": count_by_label(outcomes, "outcome_label"),
        },
        "top_outcomes": latest_rows(outcomes),
        "empty_state": "No catalyst follow-through rows available yet.",
    }


def source_usefulness_learning(source_quality_rows: List[Dict[str, object]]) -> Dict[str, object]:
    rows = build_source_usefulness(source_quality_rows)
    return {
        "review_only": True,
        "available": bool(rows),
        "summary": summarize_source_usefulness(rows),
        "top_sources": rows[:8],
        "empty_state": "No source usefulness history available yet.",
    }


def decision_safety_learning(limit: int = 80) -> Dict[str, object]:
    review = build_decision_safety_effectiveness_review(limit=limit, windows=(20,))
    rows = [dict(row) for row in review.get("rows", []) if isinstance(row, dict)]
    return {
        "review_only": True,
        "available": bool(rows),
        "summary": review.get("summary", {}),
        "top_rows": latest_rows(rows),
        "empty_state": "No decision-safety effectiveness history available yet.",
    }


def build_learning_review_context(source_quality_rows: List[Dict[str, object]]) -> Dict[str, object]:
    sections = {
        "manual_journal": lambda: manual_journal_learning(),
        "recommendation_outcomes": lambda: recommendation_outcome_learning(),
        "catalyst_follow_through": lambda: catalyst_learning(),
        "source_usefulness": lambda: source_usefulness_learning(source_quality_rows),
        "decision_safety_effectiveness": lambda: decision_safety_learning(),
    }
    review: Dict[str, object] = {
        "review_only": True,
        "title": "Learning Review",
        "note": LEARNING_REVIEW_NOTE,
    }
    for name, builder in sections.items():
        try:
            review[name] = builder()
        except Exception as exc:  # pragma: no cover - defensive report-only fallback
            review[name] = learning_section_error(name, exc)
    return review


def source_quality_table_rows(rows: List[Dict[str, object]], limit: int = 24) -> List[List[object]]:
    visible = rows[:limit]
    return [
        [
            row.get("source_name") or "",
            row.get("source_category") or "",
            row.get("quality_label") or "",
            int(row.get("records_seen") or 0),
            int(row.get("records_inserted") or 0),
            int(row.get("duplicate_records") or 0),
            f"{to_float(row.get('tag_rate')) * 100:.0f}%",
            f"{to_float(row.get('avg_tag_confidence')):.2f}" if row.get("avg_tag_confidence") is not None else "n/a",
            int(row.get("matched_symbol_count") or 0),
            row.get("match_reason_summary") or "",
            row.get("confidence_bucket_summary") or "",
            int(row.get("low_confidence_matches") or 0),
            row.get("latest_success") or "Not run",
            row.get("latest_issue") or "",
            row.get("notes") or "",
        ]
        for row in visible
    ]


def low_relevance_source_rows(rows: List[Dict[str, object]], limit: int = 12) -> List[List[object]]:
    noisy = [
        row
        for row in rows
        if int(row.get("total_evidence") or 0) >= 3
        and (
            str(row.get("quality_label") or "") == "needs_review"
            or to_float(row.get("tag_rate")) < 0.20
        )
    ]
    noisy.sort(key=lambda row: (to_float(row.get("tag_rate")), -int(row.get("total_evidence") or 0)))
    return [
        [
            row.get("source_name") or "",
            row.get("source_category") or "",
            int(row.get("total_evidence") or 0),
            int(row.get("tagged_evidence") or 0),
            f"{to_float(row.get('tag_rate')) * 100:.0f}%",
            row.get("match_reason_summary") or "No symbol matches",
            row.get("confidence_bucket_summary") or "",
            int(row.get("low_confidence_matches") or 0),
            row.get("notes") or "",
        ]
        for row in noisy[:limit]
    ]


def low_confidence_match_rows(limit: int = 20) -> List[List[object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    rows = conn.execute(
        """
        SELECT e.source_name, t.symbol, t.match_reason, t.matched_text,
               t.confidence_bucket, ROUND(t.confidence, 2) AS confidence,
               e.title, e.source_timestamp
        FROM evidence_symbol_tags t
        JOIN research_evidence e ON e.id = t.evidence_id
        WHERE t.confidence_bucket IN ('low', 'needs_review')
           OR t.match_reason = 'sector_context'
        ORDER BY e.id DESC, t.confidence ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        [
            row[0] or "",
            row[1] or "",
            row[2] or "",
            row[3] or "",
            row[4] or "",
            row[5] if row[5] is not None else "",
            row[6] or "",
            row[7] or "",
        ]
        for row in rows
    ]


def source_depth_rows(limit: int = 30) -> List[List[object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    rows = conn.execute(
        """
        SELECT symbol, evidence_type, title, summary, source_url,
               source_timestamp, confidence, corroboration_status
        FROM research_evidence
        WHERE source_name = 'Local source depth curator'
        ORDER BY source_timestamp DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        [
            row[0] or "",
            str(row[1] or "").replace("_depth_signal", "").replace("_", " ").title(),
            row[2] or "",
            row[3] or "",
            row[6] or "",
            row[7] or "",
            row[5] or "",
            row[4] or "",
        ]
        for row in rows
    ]


def ingestion_run_plan_rows(limit: int = 20) -> List[List[object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    rows = conn.execute(
        """
        SELECT priority_rank, source_name, source_category, due_status,
               cadence_days, records, raw_payloads, latest_success,
               next_run_at, cooldown_until, latest_issue, reason, run_command
        FROM ingestion_run_plan
        ORDER BY priority_rank, source_name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        [
            row[0] or "",
            row[1] or "",
            row[2] or "",
            row[3] or "",
            row[4] or "",
            row[5] or 0,
            row[6] or 0,
            row[7] or "Not run",
            row[8] or "",
            row[9] or "",
            row[10] or "",
            row[11] or "",
            row[12] or "",
        ]
        for row in rows
    ]


def ingestion_backfill_rows(limit: int = 20) -> List[List[object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    rows = conn.execute(
        """
        SELECT priority_rank, source_name, symbol, backfill_type, status,
               desired_window_days, covered_since, covered_until, record_count,
               next_action, command, reason
        FROM ingestion_backfill_queue
        ORDER BY priority_rank, source_name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        [
            row[0] or "",
            row[1] or "",
            row[2] or "",
            row[3] or "",
            row[4] or "",
            row[5] or "",
            row[6] or "",
            row[7] or "",
            row[8] or 0,
            row[9] or "",
            row[10] or "",
            row[11] or "",
        ]
        for row in rows
    ]


def evidence_event_rows(limit: int = 24) -> List[List[object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    rows = conn.execute(
        """
        SELECT event_date, symbol, event_type, headline, corroboration_label,
               source_count, evidence_count, independent_source_count,
               primary_source_count, company_source_count, opinion_source_count,
               confidence, latest_evidence_at, summary
        FROM evidence_event_clusters
        ORDER BY
            CASE corroboration_label
                WHEN 'primary_plus_confirmed' THEN 0
                WHEN 'independent_confirmed' THEN 1
                WHEN 'multi_source_confirmed' THEN 2
                WHEN 'company_only' THEN 3
                WHEN 'multi_source_unconfirmed' THEN 4
                WHEN 'single_source' THEN 5
                ELSE 9
            END,
            evidence_count DESC,
            source_count DESC,
            latest_evidence_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        [
            row[0] or "",
            row[1] or "",
            str(row[2] or "").replace("_", " ").title(),
            row[3] or "",
            row[4] or "",
            row[5] or 0,
            row[6] or 0,
            f"primary {row[8] or 0} / company {row[9] or 0} / independent {row[7] or 0} / opinion {row[10] or 0}",
            row[11] or "",
            row[12] or "",
            row[13] or "",
        ]
        for row in rows
    ]


def evidence_review_queue_rows(limit: int = 24) -> List[List[object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    rows = conn.execute(
        """
        SELECT priority_rank, symbol, event_type, review_status, corroboration_label,
               confidence, source_count, evidence_count, latest_evidence_at,
               review_reason, recommended_action
        FROM evidence_review_queue
        ORDER BY priority_rank, symbol
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        [
            row[0] or "",
            row[1] or "",
            str(row[2] or "").replace("_", " ").title(),
            row[3] or "",
            row[4] or "",
            row[5] or "",
            row[6] or 0,
            row[7] or 0,
            row[8] or "",
            row[9] or "",
            row[10] or "",
        ]
        for row in rows
    ]


def synthesis_readiness_rows(limit: int = 30) -> List[List[object]]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    rows = conn.execute(
        """
        SELECT symbol, readiness_status, readiness_score, ready_events,
               needs_review_events, needs_corroboration_events, ignored_events,
               primary_events, independent_confirmed_events, latest_event_at,
               packet_ref, notes
        FROM synthesis_readiness
        ORDER BY readiness_score DESC, ready_events DESC, symbol
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        [
            row[0] or "",
            row[1] or "",
            f"{to_float(row[2]):.2f}",
            row[3] or 0,
            row[4] or 0,
            row[5] or 0,
            row[6] or 0,
            row[7] or 0,
            row[8] or 0,
            row[9] or "",
            row[10] or "",
            row[11] or "",
        ]
        for row in rows
    ]


def score_signal_shadow_html(symbol: str, signals_by_symbol: Dict[str, List[Dict[str, object]]]) -> str:
    rows = signals_by_symbol.get(symbol, [])
    if not rows:
        return """
          <div class="score-signal-block">
            <h4>Score Signals</h4>
            <p>No active score signals captured yet. Generate the daily report to populate the transparent insight overlay.</p>
          </div>
        """
    table_rows = []
    for row in rows:
        delta = to_float(row.get("normalized_delta"))
        delta_class = "signal-positive" if delta > 0 else "signal-negative" if delta < 0 else "signal-neutral"
        table_rows.append(
            [
                row.get("signal_type", ""),
                row.get("metric_name", ""),
                f'<span class="{delta_class}">{delta:+.2f}</span>',
                f"{to_float(row.get('raw_value')):.3g}" if row.get("raw_value") not in (None, "") else "n/a",
                row.get("confidence", ""),
                row.get("source_name", ""),
                row.get("freshness_days") if row.get("freshness_days") not in (None, "") else "n/a",
                row.get("notes", ""),
            ]
        )
    return f"""
      <div class="score-signal-block">
        <h4>Score Signals</h4>
        <p>Active signals explain the V1.6 evidence, trend, target-confidence, and data-gap overlay.</p>
        {html_table(['Type', 'Metric', 'Delta', 'Raw', 'Confidence', 'Source', 'Freshness', 'Notes'], table_rows, 'score-signal-table', raw_columns={2})}
      </div>
    """


def evidence_summary(
    symbol: str,
    evidence_by_symbol: Dict[str, List[Dict[str, object]]],
    item: ResearchInput | None = None,
) -> str:
    rows = evidence_by_symbol.get(symbol, [])
    if item:
        rows = [row for row in rows if evidence_mentions_item(row, item)]
    if not rows:
        return "No evidence captured yet. Run Finnhub/SEC ingestion to populate source drilldowns."
    labels = []
    for row in rows[:3]:
        source = str(row.get("source_name") or row.get("evidence_type") or "source")
        title = str(row.get("title") or row.get("summary") or "").strip()
        if title:
            labels.append(f"{source}: {title}")
    return " | ".join(labels) if labels else f"{len(rows)} evidence items captured."


def parse_evidence_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [
        (text[:19], "%Y-%m-%dT%H:%M:%S"),
        (text[:19], "%Y-%m-%d %H:%M:%S"),
        (text[:10], "%Y-%m-%d"),
        (text[:15], "%Y%m%dT%H%M%S"),
    ]
    for candidate, pattern in candidates:
        try:
            return datetime.strptime(candidate, pattern)
        except ValueError:
            continue
    return None


def evidence_age_days(row: Dict[str, object]) -> int | None:
    parsed = parse_evidence_date(row.get("source_timestamp"))
    if not parsed:
        return None
    return max((datetime.now() - parsed).days, 0)


def evidence_label(row: Dict[str, object]) -> str:
    source = str(row.get("source_name") or row.get("source_type") or "Source")
    title = str(row.get("title") or row.get("summary") or "Untitled evidence").strip()
    age = evidence_age_days(row)
    freshness = f"{age}d old" if age is not None else "date n/a"
    confidence = str(row.get("confidence") or "unknown")
    matched = str(row.get("matched_text") or "").strip()
    if matched:
        reason = str(row.get("tag_match_reason") or row.get("tag_match_type") or "symbol tag")
        bucket = str(row.get("tag_confidence_bucket") or "")
        confidence_note = f", {bucket}" if bucket else ""
        match_note = f"; matched because {reason}: {matched}{confidence_note}"
    else:
        match_note = ""
    return f"{source}: {title} ({freshness}, {confidence}{match_note})"


def pick_evidence(
    rows: List[Dict[str, object]],
    evidence_types: Set[str],
    limit: int = 2,
) -> List[Dict[str, object]]:
    return [row for row in rows if str(row.get("evidence_type") or "") in evidence_types][:limit]


def keyword_hits(rows: List[Dict[str, object]], keywords: Set[str], limit: int = 2) -> List[Dict[str, object]]:
    matches = []
    for row in rows:
        text = f"{row.get('title', '')} {row.get('summary', '')}".lower()
        if any(keyword in text for keyword in keywords):
            matches.append(row)
        if len(matches) >= limit:
            break
    return matches


def company_terms(item: ResearchInput) -> Set[str]:
    terms = {item.symbol.lower()}
    for token in re.split(r"[^A-Za-z0-9]+", item.company.lower()):
        if len(token) >= 4 and token not in {"inc", "corp", "ltd", "holdings", "company"}:
            terms.add(token)
    if item.symbol == "MSFT":
        terms.update({"microsoft", "azure", "windows", "copilot"})
    elif item.symbol == "NVDA":
        terms.update({"nvidia"})
    elif item.symbol == "GOOGL":
        terms.update({"alphabet", "google"})
    elif item.symbol == "AMZN":
        terms.update({"amazon", "aws"})
    elif item.symbol == "META":
        terms.update({"meta", "facebook", "instagram"})
    return terms


def evidence_mentions_item(row: Dict[str, object], item: ResearchInput) -> bool:
    row_symbol = str(row.get("symbol") or "").upper()
    evidence_type = str(row.get("evidence_type") or "").lower()
    if row_symbol == item.symbol and row.get("matched_text"):
        return True
    if row_symbol == item.symbol and evidence_type not in {
        "company_news",
        "stock_news",
        "news_sentiment",
        "podcast_public_feed",
        "newsletter_public_feed",
    }:
        return True
    source_type = str(row.get("source_type") or "").lower()
    if source_type in {"sec filing", "sec xbrl facts", "analyst", "earnings_calendar"}:
        return True
    terms = company_terms(item)
    if evidence_type in {"company_news", "stock_news", "news_sentiment"}:
        # News APIs often tag tickers mentioned in passing. For stock-specific
        # dashboard evidence, require the company/ticker to be a headline topic.
        title = str(row.get("title") or "").lower()
        return any(term in title for term in terms)
    text = f"{row.get('title', '')} {row.get('summary', '')}".lower()
    return any(term in text for term in terms)


def alpha_sentiment_label(row: Dict[str, object]) -> str:
    summary = str(row.get("summary") or "").lower()
    if "somewhat-bearish" in summary or "bearish" in summary:
        return "bearish"
    if "somewhat-bullish" in summary or "bullish" in summary:
        return "bullish"
    return "neutral"


def research_brief_html(
    symbol: str,
    item: ResearchInput,
    evidence: Dict[str, List[Dict[str, object]]],
) -> str:
    rows = evidence.get(symbol, [])
    if not rows:
        return """
          <div class="research-brief">
            <h4>Research Brief</h4>
            <p>No captured research evidence yet. Run V1.4 evidence ingestion to populate bull, bear, catalyst, and source-confidence notes.</p>
          </div>
        """

    direct_rows = [row for row in rows if evidence_mentions_item(row, item)]
    context_rows = [row for row in rows if row not in direct_rows]
    bull_candidates = [
        row
        for row in direct_rows
        if str(row.get("evidence_type") or "")
        not in {"official_ir_page_snapshot", "official_ir_link", "news_sentiment"}
        or (
            str(row.get("evidence_type") or "") == "news_sentiment"
            and alpha_sentiment_label(row) == "bullish"
        )
    ]
    risk_candidates = [
        row
        for row in direct_rows
        if str(row.get("evidence_type") or "")
        not in {"official_ir_page_snapshot", "official_ir_link", "news_sentiment"}
        or (
            str(row.get("evidence_type") or "") == "news_sentiment"
            and alpha_sentiment_label(row) == "bearish"
        )
    ]

    bull_rows = keyword_hits(
        bull_candidates,
        {
            "beat",
            "beats",
            "growth",
            "raise",
            "raised",
            "upgrade",
            "buy",
            "strongbuy",
            "ai",
            "margin",
            "cash flow",
            "guidance",
        },
    )
    risk_rows = keyword_hits(
        risk_candidates,
        {
            "risk",
            "miss",
            "downgrade",
            "sell",
            "lawsuit",
            "investigation",
            "weak",
            "decline",
            "competition",
            "valuation",
            "volatility",
        },
    )
    catalyst_rows = pick_evidence(
        direct_rows,
        {"company_news", "stock_news", "news_sentiment", "earnings_calendar", "sec_filing"},
    )
    durable_rows = pick_evidence(
        direct_rows,
        {
            "sec_filing",
            "sec_company_fact",
            "earnings_transcript",
            "recommendation_trend",
            "official_ir_page_snapshot",
            "official_ir_link",
        },
    )

    fresh_count = sum(
        1
        for row in rows
        if (evidence_age_days(row) if evidence_age_days(row) is not None else 9999) <= 14
    )
    high_confidence_count = sum(1 for row in rows if str(row.get("confidence") or "").lower() == "high")
    source_count = len({str(row.get("source_name") or "") for row in rows if row.get("source_name")})

    def bullet_list(items: List[str]) -> str:
        return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"

    bull_items = [evidence_label(row) for row in bull_rows] or [
        f"Base thesis: {item.notes}",
    ]
    risk_items = [evidence_label(row) for row in risk_rows] or [
        "No fresh negative evidence flagged by keyword rules; continue monitoring valuation, volatility, and provider gaps.",
    ]
    catalyst_items = [evidence_label(row) for row in catalyst_rows] or [
        "No fresh catalyst evidence captured yet.",
    ]
    durable_items = [evidence_label(row) for row in durable_rows] or [
        "No filing, transcript, or analyst-trend evidence captured in the latest evidence set.",
    ]
    source_items = [
        f"{len(direct_rows)} direct evidence item(s) and {len(context_rows)} broader context item(s) from {source_count} source(s); {fresh_count} item(s) are 14 days old or newer; {high_confidence_count} high-confidence primary-source item(s).",
        "V1.6 applies a conservative transparent evidence overlay; score movement is shown in Insight Drivers.",
    ]
    change_items = [
        "Upgrade view if fresh evidence corroborates improving growth, margins, guidance, or analyst trend across multiple trusted sources.",
        "Downgrade view if filings, transcripts, or news show thesis deterioration, major estimate risk, or uncorroborated hype driving the setup.",
    ]

    return f"""
      <div class="research-brief">
        <h4>Research Brief</h4>
        <div class="brief-grid">
          <div><strong>Bull signals</strong>{bullet_list(bull_items)}</div>
          <div><strong>Bear/risk signals</strong>{bullet_list(risk_items)}</div>
          <div><strong>Recent catalysts</strong>{bullet_list(catalyst_items)}</div>
          <div><strong>Filings/transcripts/news</strong>{bullet_list(durable_items)}</div>
          <div><strong>Source confidence and freshness</strong>{bullet_list(source_items)}</div>
          <div><strong>What would change the view</strong>{bullet_list(change_items)}</div>
        </div>
      </div>
    """


def source_drilldown_html(
    symbol: str,
    item: ResearchInput,
    target_sources: Dict[str, object],
    evidence: Dict[str, List[Dict[str, object]]],
) -> str:
    target_drilldown = target_sources.get(symbol, {})
    if not isinstance(target_drilldown, dict):
        target_drilldown = {}
    target_rows = target_drilldown.get("sources", [])
    evidence_rows = [row for row in evidence.get(symbol, []) if evidence_mentions_item(row, item)]
    target_items = []
    for row in target_rows:
        notes = str(row.get("notes") or "").strip()
        target_items.append(
            [
                row.get("target_type", "other"),
                row.get("source_name", "Unknown"),
                row.get("source_type", "other"),
                row.get("target_price_text", "n/a"),
                row.get("range_text", "n/a"),
                row.get("as_of_date") or "unknown",
                row.get("freshness") or "Unknown freshness",
                row.get("confidence") or "unknown",
                notes or "No notes captured.",
            ]
        )
    evidence_items = []
    for row in evidence_rows:
        title = html.escape(str(row.get("title") or row.get("summary") or "Untitled evidence"))
        source = html.escape(str(row.get("source_name") or "Unknown source"))
        timestamp = html.escape(str(row.get("source_timestamp") or ""))
        summary = html.escape(str(row.get("summary") or ""))[:500]
        matched_text = str(row.get("matched_text") or "").strip()
        match_note = ""
        if matched_text:
            match_note = (
                f"<div class=\"source-summary\"><strong>Matched:</strong> "
                f"{html.escape(matched_text)}"
                f" ({html.escape(str(row.get('tag_match_type') or 'symbol tag'))})</div>"
            )
        evidence_items.append(
            "<li>"
            f"<strong>{source}</strong> {timestamp}<br>"
            f"{title}"
            + match_note
            + (f"<div class=\"source-summary\">{summary}</div>" if summary else "")
            + "</li>"
        )
    target_block = (
        html_table(
            ["Type", "Source", "Source Type", "Target", "Range", "As Of", "Freshness", "Confidence", "Notes"],
            target_items,
            "target-source-table",
        )
        if target_items
        else "<p>No stored target-source rows yet.</p>"
    )
    labels = ", ".join(str(label) for label in target_drilldown.get("labels", [])) or "No target labels available"
    blend_summary = (
        f"{target_drilldown.get('blend_label', 'missing input')} · "
        f"{target_drilldown.get('confidence', 'needs review')} confidence · "
        f"{target_drilldown.get('target_price_text', 'Needs target')} · "
        f"range {target_drilldown.get('range_text', 'n/a')}"
    )
    evidence_block = (
        "<ul>" + "".join(evidence_items) + "</ul>"
        if evidence_items
        else "<p>No captured evidence yet.</p>"
    )
    return f"""
      <div class="source-drilldown">
        <h4>Target Sources</h4>
        <p><strong>Target transparency:</strong> {html.escape(blend_summary)}.</p>
        <p><strong>Review labels:</strong> {html.escape(labels)}.</p>
        {target_block}
        <h4>Recent Evidence</h4>
        {evidence_block}
      </div>
    """


POSITIVE_EVIDENCE_KEYWORDS = {
    "beat",
    "beats",
    "growth",
    "raise",
    "raised",
    "upgrade",
    "outperform",
    "bullish",
    "record",
    "margin",
    "cash flow",
    "guidance",
    "partnership",
    "launch",
}

NEGATIVE_EVIDENCE_KEYWORDS = {
    "miss",
    "missed",
    "downgrade",
    "sell",
    "bearish",
    "lawsuit",
    "investigation",
    "decline",
    "weak",
    "cut",
    "risk",
    "competition",
    "valuation",
    "volatility",
}

PRIMARY_SOURCE_NAMES = {
    "SEC EDGAR submissions API",
    "SEC EDGAR companyfacts API",
    "Company investor relations",
}


def bounded_delta(value: float, low: float, high: float) -> float:
    return round(clamp(value, low, high), 4)


def evidence_signal_delta(
    item: ResearchInput,
    evidence: Dict[str, List[Dict[str, object]]],
) -> tuple[float, str, Dict[str, int]]:
    direct_rows = [
        row
        for row in evidence.get(item.symbol, [])
        if evidence_mentions_item(row, item)
    ]
    fresh_rows = [
        row
        for row in direct_rows
        if (evidence_age_days(row) if evidence_age_days(row) is not None else 9999) <= 14
    ]
    primary_rows = [
        row
        for row in direct_rows
        if str(row.get("source_name") or "") in PRIMARY_SOURCE_NAMES
    ]
    positive_hits = 0
    negative_hits = 0
    corroborated = 0
    for row in fresh_rows or direct_rows:
        text = f"{row.get('title', '')} {row.get('summary', '')}".lower()
        sentiment = alpha_sentiment_label(row) if str(row.get("evidence_type") or "") == "news_sentiment" else ""
        if sentiment == "bullish" or any(keyword in text for keyword in POSITIVE_EVIDENCE_KEYWORDS):
            positive_hits += 1
        if sentiment == "bearish" or any(keyword in text for keyword in NEGATIVE_EVIDENCE_KEYWORDS):
            negative_hits += 1
        if str(row.get("corroboration_status") or "").lower() in {"corroborated", "verified"}:
            corroborated += 1
    delta = (
        min(2.0, positive_hits * 0.75)
        - min(3.0, negative_hits * 1.0)
        + min(1.0, len(primary_rows) * 0.35)
        + min(0.75, len(fresh_rows) * 0.15)
        + min(0.75, corroborated * 0.5)
    )
    delta = bounded_delta(delta, -4, 4)
    driver = (
        f"Evidence {delta:+.1f}: {len(fresh_rows)} fresh item(s), "
        f"{len(primary_rows)} primary-source item(s), {positive_hits} positive and {negative_hits} risk keyword hit(s)."
    )
    counts = {
        "direct": len(direct_rows),
        "fresh": len(fresh_rows),
        "primary": len(primary_rows),
        "positive": positive_hits,
        "negative": negative_hits,
    }
    return delta, driver, counts


def price_trend_signal_delta(
    item: ResearchInput,
    price_history: Dict[str, List[Dict[str, float]]],
) -> tuple[float, str, Dict[str, object]]:
    history = price_history.get(item.symbol, [])
    closes = [to_float(row.get("close")) for row in history if to_float(row.get("close")) > 0]
    if len(closes) < 20:
        return 0.0, "Trend +0.0: fewer than 20 daily bars are available.", {"bar_count": len(closes)}

    current = item.current_price if item.current_price > 0 else closes[-1]
    ma20 = average(closes[-20:])
    ma50 = average(closes[-50:]) if len(closes) >= 50 else 0.0
    raw = 0.0
    if current > ma20:
        raw += 1.0
    else:
        raw -= 1.0
    if ma50:
        raw += 1.0 if ma20 >= ma50 else -1.0
    change_20d = ((current - closes[-20]) / closes[-20]) * 100 if closes[-20] > 0 else 0.0
    if change_20d >= 5:
        raw += 1.0
    elif change_20d <= -5:
        raw -= 1.0
    multiplier = 1.25 if item.sleeve == "short_term" or item.trade_type in {"day_trade", "weekly_swing", "tactical_2_4_week"} else 0.75
    delta = bounded_delta(raw * multiplier, -4, 4)
    trend_label = "constructive" if delta > 0 else "weak" if delta < 0 else "mixed"
    driver = (
        f"Trend {delta:+.1f}: {trend_label}; {len(closes)} daily bars, "
        f"MA20 {ma20:.2f}, "
        + (f"MA50 {ma50:.2f}, " if ma50 else "MA50 unavailable, ")
        + f"20-day change {change_20d:+.1f}%."
    )
    details = {
        "bar_count": len(closes),
        "ma20": ma20,
        "ma50": ma50,
        "change_20d": change_20d,
        "trend_label": trend_label,
    }
    return delta, driver, details


def target_signal_delta(
    item: ResearchInput,
    target: BlendedTarget | None,
    target_counts: Dict[str, Dict[str, int]],
) -> tuple[float, str, Dict[str, int]]:
    counts = target_counts.get(item.symbol, {"analyst": 0, "all": 0})
    analyst_count = counts.get("analyst", 0)
    source_count = target.source_count if target else counts.get("all", 0)
    delta = 0.0
    if analyst_count >= 2:
        delta += 1.0
    elif analyst_count == 1:
        delta += 0.25
    elif item.sleeve != "etf":
        delta -= 1.5
    if target:
        confidence = target.confidence.lower()
        if confidence == "high":
            delta += 1.0
        elif confidence == "medium":
            delta += 0.5
        else:
            delta -= 0.5
        if source_count >= 3:
            delta += 0.75
        elif source_count <= 1:
            delta -= 0.5
    else:
        delta -= 1.5
    delta = bounded_delta(delta, -3, 3)
    driver = (
        f"Target confidence {delta:+.1f}: {analyst_count} analyst target(s), "
        f"{source_count} total target source(s), "
        f"{target.confidence if target else 'no blended target'} confidence."
    )
    return delta, driver, {"analyst": analyst_count, "all": counts.get("all", 0), "source_count": source_count}


def gap_row(
    symbol: str,
    gap: str,
    impact: float,
    best_pull: str,
    next_action: str,
) -> Dict[str, object]:
    return {
        "symbol": symbol,
        "gap": gap,
        "impact": round(impact, 2),
        "best_pull": best_pull,
        "next_action": next_action,
    }


def insight_data_gaps(
    item: ResearchInput,
    target: BlendedTarget | None,
    evidence_counts: Dict[str, int],
    trend_details: Dict[str, object],
    target_counts: Dict[str, Dict[str, int]],
    base_score: float,
) -> List[Dict[str, object]]:
    gaps: List[Dict[str, object]] = []
    counts = target_counts.get(item.symbol, {"analyst": 0, "all": 0})
    if item.current_price <= 0:
        gaps.append(
            gap_row(
                item.symbol,
                "Missing current price",
                5.0,
                "scripts/refresh_market_data.py",
                "Refresh FMP/Alpha quote data or use price-history fallback before scoring.",
            )
        )
    if not target:
        gaps.append(
            gap_row(
                item.symbol,
                "Missing blended target",
                3.0,
                "scripts/ingest_price_history.py + scripts/ingest_sec.py",
                "Refresh technical and fundamental target inputs.",
            )
        )
    if counts.get("analyst", 0) == 0 and item.sleeve != "etf":
        gaps.append(
            gap_row(
                item.symbol,
                "No analyst target breadth",
                2.0 if base_score >= 68 else 1.25,
                "scripts/ingest_benzinga_analyst_targets.py or config/manual_analyst_targets.csv",
                "Add a second analyst-target source; do not invent targets.",
            )
        )
    if (item.sleeve == "short_term" or item.trade_type in {"day_trade", "weekly_swing", "tactical_2_4_week"}) and int(trend_details.get("bar_count") or 0) < 50:
        gaps.append(
            gap_row(
                item.symbol,
                "Thin short-term price history",
                2.0,
                "scripts/ingest_price_history.py",
                "Refresh at least 50 daily bars for technical trend confidence.",
            )
        )
    if evidence_counts.get("primary", 0) == 0 and base_score >= 70:
        gaps.append(
            gap_row(
                item.symbol,
                "Top candidate lacks primary-source evidence",
                1.75,
                "scripts/ingest_sec.py + scripts/ingest_official_ir.py",
                "Pull filings/company IR before sharing as a high-conviction insight.",
            )
        )
    if evidence_counts.get("direct", 0) == 0:
        gaps.append(
            gap_row(
                item.symbol,
                "No symbol-specific research evidence",
                1.5,
                "scripts/ingest_research_depth.py / scripts/ingest_finnhub.py",
                "Pull news, earnings calendar, and recommendation-trend context.",
            )
        )
    near_boundary = 68 <= base_score <= 82
    if near_boundary and evidence_counts.get("direct", 0) > 0 and evidence_counts.get("fresh", 0) == 0:
        gaps.append(
            gap_row(
                item.symbol,
                "Near action boundary with stale evidence",
                1.25,
                "scripts/ingest_research_depth.py / scripts/ingest_finnhub.py",
                "Refresh evidence before changing Add/Watch/Avoid stance.",
            )
        )
    if "failed" in item.provider_notes.lower() or "blocked" in item.provider_notes.lower():
        gaps.append(
            gap_row(
                item.symbol,
                "Provider failure/blocked endpoint in latest notes",
                1.0,
                "scripts/show_provider_gaps.py",
                "Review provider gap history and choose the next access fix.",
            )
        )
    return gaps


def compute_insight_signal(
    item: ResearchInput,
    breakdown: ScoreBreakdown,
    target: BlendedTarget | None,
    price_history: Dict[str, List[Dict[str, float]]],
    evidence: Dict[str, List[Dict[str, object]]],
    target_counts: Dict[str, Dict[str, int]],
    previous_scores: Dict[str, List[Dict[str, object]]] | None = None,
) -> InsightSignal:
    evidence_delta, evidence_driver, evidence_counts = evidence_signal_delta(item, evidence)
    trend_delta, trend_driver, trend_details = price_trend_signal_delta(item, price_history)
    target_delta, target_driver, _ = target_signal_delta(item, target, target_counts)
    gaps = insight_data_gaps(
        item,
        target,
        evidence_counts,
        trend_details,
        target_counts,
        breakdown.total,
    )
    data_gap_delta = bounded_delta(-sum(to_float(gap.get("impact")) for gap in gaps), -8, 0)
    final_score = bounded_delta(
        breakdown.total + evidence_delta + trend_delta + target_delta + data_gap_delta,
        0,
        100,
    )
    history = (previous_scores or {}).get(item.symbol, [])
    previous_score = to_float(history[-1].get("score")) if history else None
    score_change = final_score - previous_score if previous_score is not None else 0.0
    trend_label = str(trend_details.get("trend_label") or "unavailable")
    trend_insight = (
        f"{trend_label.title()} price trend; "
        + (f"score changed {score_change:+.1f} from prior run; " if previous_score is not None else "new score history; ")
        + f"{len(gaps)} ranked data gap(s)."
    )
    drivers = [
        evidence_driver,
        trend_driver,
        target_driver,
        f"Data gaps {data_gap_delta:+.1f}: {len(gaps)} gap(s) limit confidence.",
    ]
    return InsightSignal(
        symbol=item.symbol,
        base_score=round(breakdown.total, 4),
        final_score=round(final_score, 4),
        evidence_delta=evidence_delta,
        trend_delta=trend_delta,
        target_delta=target_delta,
        data_gap_delta=data_gap_delta,
        drivers=drivers,
        data_gaps=gaps,
        trend_insight=trend_insight,
    )


def score_summary_with_insight(breakdown: ScoreBreakdown, insight: InsightSignal | None) -> str:
    base = score_summary(breakdown)
    if not insight:
        return base
    return (
        f"{base}; signal overlay evidence {insight.evidence_delta:+.1f}, "
        f"trend {insight.trend_delta:+.1f}, target {insight.target_delta:+.1f}, "
        f"gaps {insight.data_gap_delta:+.1f}; final {insight.final_score:.1f}"
    )


def insight_drivers_html(insight: InsightSignal | None) -> str:
    if not insight:
        return "<p>No insight signal snapshot available.</p>"
    rows = [
        ["Base score", f"{insight.base_score:.1f}", "Existing quality/momentum/catalyst/risk model."],
        ["Evidence", f"{insight.evidence_delta:+.1f}", insight.drivers[0]],
        ["Price trend", f"{insight.trend_delta:+.1f}", insight.drivers[1]],
        ["Targets", f"{insight.target_delta:+.1f}", insight.drivers[2]],
        ["Data gaps", f"{insight.data_gap_delta:+.1f}", insight.drivers[3]],
        ["Final score", f"{insight.final_score:.1f}", insight.score_movement],
    ]
    return (
        '<div class="insight-drivers">'
        "<h4>Insight Drivers</h4>"
        f"{html_table(['Signal', 'Delta', 'Why'], rows, 'score-driver-table')}"
        f"<p><strong>Trend insight:</strong> {html.escape(insight.trend_insight)}</p>"
        "</div>"
    )


def score_signal_storage_rows(
    run_id: int,
    report_date: str,
    rows: Iterable[Dict[str, object]],
) -> List[Dict[str, object]]:
    signal_rows: List[Dict[str, object]] = []
    for row in rows:
        item = row["input"]
        insight: InsightSignal = row["insight"]
        source_ref = f"recommendation_run:{run_id}"
        specs = [
            ("evidence", "evidence_delta", insight.evidence_delta, insight.drivers[0]),
            ("price_trend", "trend_delta", insight.trend_delta, insight.drivers[1]),
            ("target_confidence", "target_delta", insight.target_delta, insight.drivers[2]),
            ("data_gap", "data_gap_delta", insight.data_gap_delta, insight.drivers[3]),
            ("score_snapshot", "final_score", insight.final_score, insight.score_movement),
        ]
        for signal_type, metric_name, value, notes in specs:
            signal_rows.append(
                {
                    "symbol": item.symbol,
                    "signal_date": report_date,
                    "signal_type": signal_type,
                    "metric_name": metric_name,
                    "raw_value": value,
                    "normalized_delta": insight.total_delta if metric_name == "final_score" else value,
                    "confidence": "medium" if not insight.data_gaps else "low",
                    "source_name": "Internal insight engine",
                    "source_type": "model",
                    "source_ref": source_ref,
                    "freshness_days": 0,
                    "signal_mode": "active",
                    "notes": notes,
                }
            )
    return signal_rows


def score_movement_rows(ranked: List[Dict[str, object]], limit: int = 12) -> List[List[object]]:
    rows = []
    for row in ranked[:limit]:
        item = row["input"]
        insight: InsightSignal = row["insight"]
        top_driver = max(
            [
                ("Evidence", insight.evidence_delta),
                ("Trend", insight.trend_delta),
                ("Target", insight.target_delta),
                ("Data gaps", insight.data_gap_delta),
            ],
            key=lambda part: abs(part[1]),
        )
        rows.append(
            [
                item.symbol,
                f"{insight.base_score:.1f}",
                f"{insight.evidence_delta:+.1f}",
                f"{insight.trend_delta:+.1f}",
                f"{insight.target_delta:+.1f}",
                f"{insight.data_gap_delta:+.1f}",
                f"{insight.final_score:.1f}",
                row["action"],
                f"{top_driver[0]} {top_driver[1]:+.1f}",
            ]
        )
    return rows


def trend_insight_rows(ranked: List[Dict[str, object]], limit: int = 12) -> List[List[object]]:
    return [
        [
            row["input"].symbol,
            f"{row['insight'].total_delta:+.1f}",
            row["insight"].trend_insight,
            row["insight"].score_movement,
        ]
        for row in ranked[:limit]
    ]


def ranked_data_gap_queue_rows(ranked: List[Dict[str, object]], limit: int = 15) -> List[List[object]]:
    gaps: List[Dict[str, object]] = []
    for rank, row in enumerate(ranked, start=1):
        insight: InsightSignal = row["insight"]
        for gap in insight.data_gaps:
            impact = to_float(gap.get("impact"))
            priority = impact + max(0, 12 - rank) * 0.15 + max(0, to_float(row["score"]) - 70) * 0.03
            enriched = dict(gap)
            enriched["priority"] = priority
            enriched["rank"] = rank
            gaps.append(enriched)
    gaps.sort(key=lambda gap: to_float(gap.get("priority")), reverse=True)
    return [
        [
            index,
            gap.get("symbol", ""),
            gap.get("gap", ""),
            f"{to_float(gap.get('impact')):.1f}",
            gap.get("best_pull", ""),
            gap.get("next_action", ""),
        ]
        for index, gap in enumerate(gaps[:limit], start=1)
    ]


def row_target_counts(row: Dict[str, object], target_counts: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    item = row["input"]
    target = row.get("target")
    counts = dict(target_counts.get(item.symbol, {"analyst": 0, "all": 0}))
    counts["source_count"] = target.source_count if target else counts.get("all", 0)
    return counts


def decision_gap_match(insight: InsightSignal, needle: str) -> bool:
    needle = needle.lower()
    return any(needle in str(gap.get("gap") or "").lower() for gap in insight.data_gaps)


def top_decision_gap(insight: InsightSignal) -> Dict[str, object] | None:
    if not insight.data_gaps:
        return None
    return sorted(insight.data_gaps, key=lambda gap: to_float(gap.get("impact")), reverse=True)[0]


def concrete_next_check(
    row: Dict[str, object],
    insight_type: str,
    insight: InsightSignal,
) -> str:
    gap = top_decision_gap(insight)
    if gap:
        best_pull = str(gap.get("best_pull") or "").strip()
        next_action = str(gap.get("next_action") or "").strip()
        return f"{best_pull}: {next_action}" if next_action else best_pull
    if insight_type == "Momentum Watch":
        return "scripts/ingest_price_history.py: refresh daily bars and confirm the move still holds."
    if insight_type == "Conviction Builder":
        return "scripts/ingest_sec.py + scripts/ingest_official_ir.py: confirm the thesis against primary-source evidence."
    if insight_type == "Caution":
        return "scripts/ingest_research_depth.py / scripts/ingest_finnhub.py: refresh news, earnings, and recommendation context."
    item = row["input"]
    if item.sleeve != "etf":
        return "config/manual_analyst_targets.csv: add verified analyst targets if provider coverage is thin."
    return "scripts/refresh_market_data.py: refresh price and target inputs before the next report."


def classify_decision_insight(row: Dict[str, object], target_counts: Dict[str, Dict[str, int]]) -> str:
    insight: InsightSignal = row["insight"]
    item = row["input"]
    action = str(row.get("action") or "")
    score = to_float(row.get("score"))
    counts = row_target_counts(row, target_counts)
    analyst_count = counts.get("analyst", 0)
    missing_price = decision_gap_match(insight, "missing current price")
    missing_target = decision_gap_match(insight, "missing blended target")
    missing_analyst = analyst_count == 0 and item.sleeve != "etf"
    primary_gap = decision_gap_match(insight, "primary-source")
    provider_gap = decision_gap_match(insight, "provider failure") or "blocked" in item.provider_notes.lower()
    near_action = action in {"Add", "Buy", "Strong Buy", "Watch", "Hold"} or score >= 65
    negative_evidence = insight.evidence_delta <= -1.0
    negative_signal = negative_evidence or insight.trend_delta <= -2.0 or insight.target_delta <= -1.5
    strong_trend = insight.trend_delta >= 2.0 and insight.trend_delta >= max(insight.evidence_delta, insight.target_delta)
    supportive_signal = insight.evidence_delta >= 0.5 or insight.trend_delta >= 1.0 or insight.target_delta >= 0.5
    major_blocker = missing_price or missing_target or provider_gap or insight.data_gap_delta <= -4

    if major_blocker and score < 68:
        return "Data Gap"
    if near_action and (primary_gap or provider_gap or missing_price or missing_target):
        return "Verification Needed"
    if negative_evidence:
        return "Caution"
    if strong_trend and (item.sleeve == "short_term" or item.trade_type in {"day_trade", "weekly_swing", "tactical_2_4_week"}):
        return "Momentum Watch"
    if strong_trend and missing_analyst:
        return "Momentum Watch"
    if near_action and missing_analyst:
        return "Verification Needed"
    if negative_signal:
        return "Caution"
    if score >= 78 and supportive_signal and insight.data_gap_delta >= -1.5 and not major_blocker:
        return "Conviction Builder"
    if insight.data_gap_delta <= -2:
        return "Data Gap" if score < 65 else "Verification Needed"
    if strong_trend:
        return "Momentum Watch"
    return "Caution" if score >= 70 else "Data Gap"


def decision_headline(row: Dict[str, object], insight_type: str) -> str:
    item = row["input"]
    action = str(row.get("action") or "")
    score = to_float(row.get("score"))
    if insight_type == "Conviction Builder":
        return f"{item.symbol} has decision support for {action} with a {score:.1f} final score."
    if insight_type == "Verification Needed":
        return f"{item.symbol} is near action, but one verification pull should happen before sharing."
    if insight_type == "Momentum Watch":
        return f"{item.symbol} is being carried by price trend; confirm the move before upgrading conviction."
    if insight_type == "Caution":
        return f"{item.symbol} has enough signal to track, but the current evidence mix argues for restraint."
    return f"{item.symbol} needs a data pull before the score can be trusted."


def build_decision_insight(
    row: Dict[str, object],
    evidence_by_symbol: Dict[str, List[Dict[str, object]]],
    target_counts: Dict[str, Dict[str, int]],
) -> DecisionInsight:
    item = row["input"]
    target = row.get("target")
    insight: InsightSignal = row["insight"]
    insight_type = classify_decision_insight(row, target_counts)
    counts = row_target_counts(row, target_counts)
    evidence_rows = [e for e in evidence_by_symbol.get(item.symbol, []) if evidence_mentions_item(e, item)]
    primary_count = sum(1 for e in evidence_rows if str(e.get("source_name") or "") in PRIMARY_SOURCE_NAMES)
    fresh_count = sum(
        1
        for e in evidence_rows
        if (evidence_age_days(e) if evidence_age_days(e) is not None else 9999) <= 14
    )
    target_label = target_price_text(item, target)
    upside_label = target_upside_text(item, target) if target or item.upside_pct else "Refresh"
    holding_pct = to_float(row.get("portfolio_pct"))
    top_driver = max(
        [
            ("evidence", insight.evidence_delta),
            ("price trend", insight.trend_delta),
            ("target confidence", insight.target_delta),
            ("data gaps", insight.data_gap_delta),
        ],
        key=lambda part: abs(part[1]),
    )
    top_gap = top_decision_gap(insight)
    risk = (
        f"{top_gap.get('gap')}: {top_gap.get('next_action')}"
        if top_gap
        else "No major confidence blocker in the current data; keep provider freshness watched."
    )
    if insight.evidence_delta < 0:
        risk = f"Risk evidence is pulling the score down ({insight.evidence_delta:+.1f}); {risk}"
    elif insight.trend_delta < 0:
        risk = f"Weak price trend is pulling the score down ({insight.trend_delta:+.1f}); {risk}"
    why = (
        f"Final score is {insight.final_score:.1f} after a {insight.total_delta:+.1f} overlay; "
        f"action is {row.get('action')} and current holding is {holding_pct:.1f}% of portfolio."
    )
    supporting = (
        f"{insight.score_movement}; top driver is {top_driver[0]} {top_driver[1]:+.1f}. "
        f"Targets: {target_label}, upside {upside_label}, {counts.get('analyst', 0)} analyst source(s), "
        f"{counts.get('all', 0)} total target source(s). Evidence: {fresh_count} fresh, {primary_count} primary."
    )
    if insight_type == "Conviction Builder":
        change_view = "The view weakens if fresh primary evidence turns negative, target breadth falls, or price trend rolls over."
    elif insight_type == "Momentum Watch":
        change_view = "The view improves if target breadth and evidence catch up; it weakens if the price trend loses support."
    elif insight_type == "Verification Needed":
        change_view = "The view improves when the named data pull closes the gap; it weakens if the gap persists into the next run."
    elif insight_type == "Caution":
        change_view = "The view improves with positive corroborated evidence and cleaner trend/target support; it weakens with new risk evidence."
    else:
        change_view = "The view changes only after the missing price, target, evidence, or provider data is refreshed."
    return DecisionInsight(
        symbol=item.symbol,
        headline=decision_headline(row, insight_type),
        insight_type=insight_type,
        why_it_matters=why,
        supporting_data=supporting,
        risk_or_uncertainty=risk,
        next_check=concrete_next_check(row, insight_type, insight),
        what_would_change_the_view=change_view,
    )


def decision_insights_by_symbol(
    ranked: List[Dict[str, object]],
    evidence_by_symbol: Dict[str, List[Dict[str, object]]],
    target_counts: Dict[str, Dict[str, int]],
) -> Dict[str, DecisionInsight]:
    return {
        row["input"].symbol: build_decision_insight(row, evidence_by_symbol, target_counts)
        for row in ranked
    }


def decision_priority(row: Dict[str, object], insight: DecisionInsight) -> float:
    type_weight = {
        "Conviction Builder": 7,
        "Verification Needed": 6,
        "Momentum Watch": 5,
        "Caution": 4,
        "Data Gap": 3,
    }.get(insight.insight_type, 3)
    action_weight = 2 if str(row.get("action") or "") in {"Add", "Buy", "Strong Buy"} else 1
    return to_float(row.get("score")) + type_weight + action_weight


def decision_brief_rows(
    ranked: List[Dict[str, object]],
    decision_insights: Dict[str, DecisionInsight],
    limit: int = 8,
) -> List[List[object]]:
    candidates = sorted(
        ranked,
        key=lambda row: decision_priority(row, decision_insights[row["input"].symbol]),
        reverse=True,
    )
    rows = []
    for row in candidates[:limit]:
        item = row["input"]
        insight = decision_insights[item.symbol]
        rows.append(
            [
                item.symbol,
                insight.insight_type,
                insight.headline,
                insight.why_it_matters,
                insight.next_check,
            ]
        )
    return rows


def what_to_verify_rows(
    ranked: List[Dict[str, object]],
    decision_insights: Dict[str, DecisionInsight],
    limit: int = 10,
) -> List[List[object]]:
    candidates = [
        row
        for row in ranked
        if decision_insights[row["input"].symbol].insight_type
        in {"Verification Needed", "Caution", "Data Gap", "Momentum Watch"}
    ]
    candidates.sort(
        key=lambda row: (
            decision_priority(row, decision_insights[row["input"].symbol]),
            abs(row["insight"].data_gap_delta),
        ),
        reverse=True,
    )
    rows = []
    for row in candidates[:limit]:
        item = row["input"]
        insight = decision_insights[item.symbol]
        rows.append(
            [
                item.symbol,
                insight.insight_type,
                insight.risk_or_uncertainty,
                insight.next_check,
                insight.what_would_change_the_view,
            ]
        )
    return rows


def verification_automation_metadata(next_check: str) -> tuple[str, str, str, str]:
    text = next_check.lower()
    if "show_provider_gaps.py" in text:
        return (
            "blocked_provider",
            "scripts/show_provider_gaps.py",
            "blocked_provider_fix_needed",
            "Provider access/config review is required before this item can resolve.",
        )
    if "ingest_benzinga_analyst_targets.py" in text:
        return (
            "conditional",
            "scripts/ingest_benzinga_analyst_targets.py --symbols {symbol}",
            "queued",
            "Run only when BENZINGA_API_KEY is configured; otherwise use config/manual_analyst_targets.csv.",
        )
    if "config/manual_analyst_targets.csv" in text:
        return (
            "manual",
            "config/manual_analyst_targets.csv",
            "manual_required",
            "Manual analyst target rows are required; the runner never invents target values.",
        )
    if "ingest_sec.py" in text and "ingest_official_ir.py" in text:
        return (
            "auto",
            "scripts/ingest_sec.py {symbol}; scripts/ingest_official_ir.py --symbols {symbol}",
            "queued",
            "Safe primary-source verification pull.",
        )
    if "ingest_price_history.py" in text:
        return (
            "auto",
            "scripts/ingest_price_history.py --symbols {symbol}",
            "queued",
            "Safe price-history verification pull.",
        )
    if "ingest_research_depth.py" in text or "ingest_finnhub.py" in text:
        return (
            "auto_nonfatal",
            "scripts/ingest_research_depth.py --symbols {symbol}; scripts/ingest_finnhub.py {symbol}",
            "queued",
            "Evidence refresh; provider failures are non-fatal and remain visible.",
        )
    return ("manual", "", "manual_required", "No safe automation mapping exists for this next check.")


def decision_insight_storage_rows(
    run_id: int,
    report_date: str,
    ranked: List[Dict[str, object]],
    decision_insights: Dict[str, DecisionInsight],
) -> List[Dict[str, object]]:
    rows = []
    for rank, row in enumerate(ranked, start=1):
        item = row["input"]
        insight = decision_insights[item.symbol]
        rows.append(
            {
                "run_id": run_id,
                "report_date": report_date,
                "rank": rank,
                "symbol": item.symbol,
                "action": row["action"],
                "score": round(to_float(row.get("score")), 4),
                "insight_type": insight.insight_type,
                "headline": insight.headline,
                "why_it_matters": insight.why_it_matters,
                "supporting_data": insight.supporting_data,
                "risk_or_uncertainty": insight.risk_or_uncertainty,
                "next_check": insight.next_check,
                "what_would_change_the_view": insight.what_would_change_the_view,
                "source_ref": f"recommendation_run:{run_id}",
            }
        )
    return rows


def verification_queue_storage_rows(
    run_id: int,
    report_date: str,
    ranked: List[Dict[str, object]],
    decision_insights: Dict[str, DecisionInsight],
    limit: int = 25,
) -> List[Dict[str, object]]:
    candidates = [
        row
        for row in ranked
        if decision_insights[row["input"].symbol].insight_type
        in {"Verification Needed", "Caution", "Data Gap", "Momentum Watch"}
    ]
    candidates.sort(
        key=lambda row: (
            decision_priority(row, decision_insights[row["input"].symbol]),
            abs(row["insight"].data_gap_delta),
        ),
        reverse=True,
    )
    rows = []
    for priority_rank, row in enumerate(candidates[:limit], start=1):
        item = row["input"]
        insight = decision_insights[item.symbol]
        signal: InsightSignal = row["insight"]
        top_gap = top_decision_gap(signal)
        automation_mode, command_mapping, status, result_summary = verification_automation_metadata(insight.next_check)
        rows.append(
            {
                "run_id": run_id,
                "report_date": report_date,
                "symbol": item.symbol,
                "priority_rank": priority_rank,
                "insight_type": insight.insight_type,
                "reason": str(top_gap.get("gap") if top_gap else insight.risk_or_uncertainty),
                "expected_score_impact": to_float(top_gap.get("impact")) if top_gap else abs(signal.data_gap_delta),
                "next_check": insight.next_check,
                "command_mapping": command_mapping.format(symbol=item.symbol) if command_mapping else "",
                "automation_mode": automation_mode,
                "status": status,
                "result_summary": result_summary,
                "workflow_step_id": None,
                "started_at": None,
                "completed_at": None,
            }
        )
    return rows


def verification_queue_table_rows(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[List[object]]:
    table_rows = []
    for row in list(rows)[:limit]:
        table_rows.append(
            [
                row.get("priority_rank", ""),
                row.get("symbol", ""),
                row.get("insight_type", ""),
                row.get("status", ""),
                f"{to_float(row.get('expected_score_impact')):.1f}",
                row.get("reason", ""),
                row.get("command_mapping") or row.get("next_check", ""),
                row.get("result_summary", ""),
            ]
        )
    return table_rows


def decision_insight_change_rows(
    history_by_symbol: Dict[str, List[Dict[str, object]]],
    limit: int = 12,
) -> List[List[object]]:
    rows = []
    for symbol, history in sorted(history_by_symbol.items()):
        if not history:
            continue
        latest = dict(history[0])
        previous = dict(history[1]) if len(history) > 1 else {}
        latest_type = str(latest.get("insight_type") or "")
        previous_type = str(previous.get("insight_type") or "New")
        score_change = to_float(latest.get("score")) - to_float(previous.get("score")) if previous else 0.0
        if previous and previous_type == latest_type and abs(score_change) < 1:
            continue
        rows.append(
            [
                symbol,
                previous_type,
                latest_type,
                f"{score_change:+.1f}" if previous else "New",
                latest.get("headline", ""),
                latest.get("next_check", ""),
            ]
        )
    rows.sort(key=lambda row: (row[1] == row[2], row[0]))
    return rows[:limit]


def decision_insight_html(insight: DecisionInsight) -> str:
    return f"""
      <div class="decision-insight-block">
        <h4>Decision Insight</h4>
        <div class="decision-insight-head">
          <span class="insight-badge">{html.escape(insight.insight_type)}</span>
          <strong>{html.escape(insight.headline)}</strong>
        </div>
        <div class="decision-insight-grid">
          <div><span>Why it matters</span>{html.escape(insight.why_it_matters)}</div>
          <div><span>Supporting data</span>{html.escape(insight.supporting_data)}</div>
          <div><span>Risk or uncertainty</span>{html.escape(insight.risk_or_uncertainty)}</div>
          <div><span>Next check</span>{html.escape(insight.next_check)}</div>
          <div><span>What would change the view</span>{html.escape(insight.what_would_change_the_view)}</div>
        </div>
      </div>
    """


def decision_brief_cards_html(
    ranked: List[Dict[str, object]],
    decision_insights: Dict[str, DecisionInsight],
    limit: int = 5,
) -> str:
    rows = sorted(
        ranked,
        key=lambda row: decision_priority(row, decision_insights[row["input"].symbol]),
        reverse=True,
    )[:limit]
    cards = []
    for row in rows:
        item = row["input"]
        insight = decision_insights[item.symbol]
        cards.append(
            f"""
            <article class="decision-brief-card">
              <div class="decision-brief-top">
                <strong>{html.escape(item.symbol)}</strong>
                <span class="insight-badge">{html.escape(insight.insight_type)}</span>
              </div>
              <h3>{html.escape(insight.headline)}</h3>
              <p>{html.escape(insight.why_it_matters)}</p>
              <p><strong>Next:</strong> {html.escape(insight.next_check)}</p>
            </article>
            """
        )
    return f"""
      <section class="decision-briefs">
        <div class="section-title">
          <h2>Decision Briefs</h2>
          <span class="section-note">Concise deterministic summaries from current data</span>
        </div>
        <div class="decision-brief-grid">
          {''.join(cards) if cards else '<p>No decision briefs available.</p>'}
        </div>
      </section>
    """


def add_insight_theme(
    themes: Dict[str, Dict[str, object]],
    name: str,
    symbol: str,
    why: str,
    next_check: str,
) -> None:
    entry = themes.setdefault(name, {"symbols": [], "why": why, "next_check": next_check})
    if symbol not in entry["symbols"]:
        entry["symbols"].append(symbol)


def insight_theme_rows(
    ranked: List[Dict[str, object]],
    decision_insights: Dict[str, DecisionInsight],
) -> List[List[object]]:
    themes: Dict[str, Dict[str, object]] = {}
    for row in ranked:
        item = row["input"]
        signal: InsightSignal = row["insight"]
        insight = decision_insights[item.symbol]
        if insight.insight_type == "Conviction Builder":
            add_insight_theme(
                themes,
                "Conviction builders",
                item.symbol,
                "High scores with supportive signals and no major confidence blocker.",
                "scripts/ingest_sec.py + scripts/ingest_official_ir.py",
            )
        if insight.insight_type == "Momentum Watch" or signal.trend_delta >= 2:
            add_insight_theme(
                themes,
                "Trend-led candidates",
                item.symbol,
                "Constructive price action is one of the strongest current drivers.",
                "scripts/ingest_price_history.py",
            )
        if decision_gap_match(signal, "No analyst target breadth"):
            add_insight_theme(
                themes,
                "Missing analyst breadth",
                item.symbol,
                "Target confidence is limited by thin analyst coverage.",
                "scripts/ingest_benzinga_analyst_targets.py or config/manual_analyst_targets.csv",
            )
        if decision_gap_match(signal, "primary-source"):
            add_insight_theme(
                themes,
                "Primary-source verification",
                item.symbol,
                "Top or near-action names need SEC/IR support before sharing as conviction.",
                "scripts/ingest_sec.py + scripts/ingest_official_ir.py",
            )
        if signal.evidence_delta < 0:
            add_insight_theme(
                themes,
                "Risk evidence",
                item.symbol,
                "Negative evidence is subtracting from the overlay.",
                "scripts/ingest_research_depth.py / scripts/ingest_finnhub.py",
            )
        if decision_gap_match(signal, "Provider failure") or "blocked" in item.provider_notes.lower():
            add_insight_theme(
                themes,
                "Source blockers",
                item.symbol,
                "Provider access or endpoint failures are blocking confidence fields.",
                "scripts/show_provider_gaps.py",
            )
        if signal.data_gap_delta <= -4:
            add_insight_theme(
                themes,
                "Scores held down by data gaps",
                item.symbol,
                "Missing data is materially lowering final score and confidence.",
                insight.next_check,
            )
    rows = []
    for name, entry in sorted(themes.items(), key=lambda part: len(part[1]["symbols"]), reverse=True):
        symbols = entry["symbols"]
        rows.append(
            [
                name,
                ", ".join(symbols[:10]) + (f" +{len(symbols) - 10} more" if len(symbols) > 10 else ""),
                entry["why"],
                entry["next_check"],
            ]
        )
    return rows


def source_quality(row: Dict[str, str]) -> float:
    reliability = to_float(row.get("reliability_rating")) / 5
    timeliness = to_float(row.get("timeliness_rating")) / 5
    signal = to_float(row.get("signal_rating")) / 5
    return clamp(((reliability * 0.45) + (timeliness * 0.20) + (signal * 0.35)) * 100)


def effective_source_weight(row: Dict[str, str]) -> float:
    quality = source_quality(row) / 100
    base_weight = to_float(row.get("default_weight"), 0)
    corroboration_required = str(row.get("corroboration_required", "")).lower() == "true"
    corroboration_multiplier = 0.85 if corroboration_required else 1.0
    return clamp(quality * base_weight * corroboration_multiplier, 0, 1)


SOURCE_IMPLEMENTATION_PLAN = {
    "SEC EDGAR": "Implemented via SEC submissions and companyfacts; improve readable filing summaries next.",
    "SEC EDGAR submissions API": "Implemented; tune filing-type filters and link filing URLs in detail views.",
    "SEC EDGAR companyfacts API": "Implemented; map facts into score drivers and trend charts next.",
    "Financial Modeling Prep": "Implemented for prices/targets where plan allows; paid endpoints remain visible as gaps.",
    "FMP stock news": "Access check implemented; current key is blocked, revisit paid tier after gap history proves value.",
    "FMP earnings transcripts": "Access check implemented; current key is blocked, evaluate paid tier or alternate transcript provider.",
    "Alpha Vantage": "Implemented with quota-aware rotation; prioritize symbols with oldest successful Alpha refresh.",
    "Alpha Vantage news sentiment": "Implemented with daily symbol budget and oldest-successful-refresh priority; continue relevance filtering.",
    "Finnhub company news sentiment": "Implemented through company news/recommendation/earnings evidence where free key allows.",
    "Finnhub earnings transcripts": "Not implemented as transcript capture yet; verify endpoint access and data quality.",
    "Analyst target consensus": "Partial via FMP target input; add second analyst-target provider if free/low-cost access is available.",
    "E*TRADE account data": "Implemented for read-only holdings; future work is order preview with manual approval.",
    "Company investor relations": "Implemented as official IR page snapshots/link discovery; next add release/deck/transcript detail extraction from discovered official links.",
    "Earnings call transcripts": "Partial through provider checks; need a reliable transcript source and storage strategy.",
    "Market news feeds": "Partial through Alpha Vantage/Finnhub; add stronger company relevance metadata.",
    "Options flow provider": "Not implemented; research provider cost and usefulness for short-term sleeve.",
    "Social sentiment": "Not implemented; treat as lower-trust context with strong noise controls.",
    "Podcasts": "Public feed/archive ingestion and deterministic source-to-symbol tagging are implemented for Hard Fork and AI Daily Brief; next add optional transcript enrichment.",
    "Newsletters": "Approved source category; public/feed ingestion plus deterministic source-to-symbol tagging are active where sources expose public archives. The Information and The Batch still need alternate access.",
    "Manual user notes": "Partial through feedback; connect notes into synthesis and source weighting.",
    "Benzinga news": "Candidate only; evaluate paid/free access if current news quality remains weak.",
    "Hard Fork podcast": "Implemented through verified public podcast RSS; classify as opinion/context until corroborated.",
    "AI Daily Brief podcast": "Implemented through Beehiiv public archive posts; classify as opinion/context until corroborated.",
    "SemiAnalysis newsletter": "Public RSS/archive ingestion added; paid/member-only articles may still require manual or email access.",
    "The Information AI newsletter": "Public RSS/archive ingestion added where discoverable; paid access may still be required for full text.",
    "The Batch newsletter": "Public RSS/archive ingestion added; use as AI context, not stock-specific fact.",
    "Import AI newsletter": "Public RSS/archive ingestion added; use as AI policy/frontier-model context.",
    "TLDR AI newsletter": "Public RSS/archive ingestion added; keep low weight because it is headline-heavy.",
    "Platformer newsletter": "Public RSS/archive ingestion added where discoverable; paid access may still be required for full text.",
    "Benzinga analyst ratings": "Candidate paid API; evaluate for analyst-rating coverage before buying.",
    "Benzinga unusual options": "Candidate paid API; compare against Unusual Whales for short-term sleeve alerts.",
    "Unusual Whales options flow": "Candidate paid API; evaluate token cost, endpoint fit, and noise controls before integration.",
}


SOURCE_ALIASES = {
    "SEC EDGAR": ["SEC EDGAR", "SEC EDGAR submissions API", "SEC EDGAR companyfacts API"],
    "SEC EDGAR submissions API": ["SEC EDGAR", "SEC EDGAR submissions API"],
    "SEC EDGAR companyfacts API": ["SEC EDGAR", "SEC EDGAR companyfacts API"],
    "Company investor relations": ["Company investor relations"],
    "Earnings call transcripts": ["Earnings call transcripts", "FMP earnings transcripts", "Finnhub earnings transcripts"],
    "Analyst target consensus": ["Analyst target consensus", "Financial Modeling Prep"],
    "Financial Modeling Prep": ["Financial Modeling Prep", "FMP"],
    "Alpha Vantage": ["Alpha Vantage", "Alpha Vantage news sentiment"],
    "E*TRADE account data": ["E*TRADE account data", "etrade_production", "etrade_sandbox"],
    "Market news feeds": ["Market news feeds", "Alpha Vantage news sentiment", "Finnhub company news"],
    "Options flow provider": ["Options flow provider"],
    "Social sentiment": ["Social sentiment"],
    "Podcasts": ["Podcasts"],
    "Newsletters": ["Newsletters"],
    "Hard Fork podcast": ["Hard Fork podcast", "Podcasts"],
    "AI Daily Brief podcast": ["AI Daily Brief podcast", "Podcasts"],
    "SemiAnalysis newsletter": ["SemiAnalysis newsletter", "Newsletters"],
    "The Information AI newsletter": ["The Information AI newsletter", "Newsletters"],
    "The Batch newsletter": ["The Batch newsletter", "Newsletters"],
    "Import AI newsletter": ["Import AI newsletter", "Newsletters"],
    "TLDR AI newsletter": ["TLDR AI newsletter", "Newsletters"],
    "Platformer newsletter": ["Platformer newsletter", "Newsletters"],
    "Manual user notes": ["Manual user notes"],
    "FMP earnings transcripts": ["FMP earnings transcripts"],
    "Finnhub earnings transcripts": ["Finnhub earnings transcripts"],
    "Alpha Vantage news sentiment": ["Alpha Vantage news sentiment"],
    "Finnhub company news sentiment": ["Finnhub company news sentiment", "Finnhub company news"],
    "FMP stock news": ["FMP stock news"],
    "Benzinga news": ["Benzinga news"],
    "Benzinga analyst ratings": ["Benzinga analyst ratings"],
    "Benzinga unusual options": ["Benzinga unusual options"],
    "Unusual Whales options flow": ["Unusual Whales options flow"],
}

PUBLIC_FEED_SOURCE_NAMES = {
    "Hard Fork podcast",
    "AI Daily Brief podcast",
    "SemiAnalysis newsletter",
    "The Information AI newsletter",
    "The Batch newsletter",
    "Import AI newsletter",
    "TLDR AI newsletter",
    "Platformer newsletter",
}
PUBLIC_SOURCE_CATEGORIES = {
    "ai_research",
    "company_blog",
    "company_newsroom",
    "newsletter",
    "podcast",
    "press_wire",
    "semiconductor_news",
    "tech_news",
}


def public_feed_source_names() -> set[str]:
    names = set(PUBLIC_FEED_SOURCE_NAMES)
    for source_name, integration in load_source_integrations().items():
        if str(integration.get("source_category", "")).strip() in PUBLIC_SOURCE_CATEGORIES:
            names.add(source_name)
    return names


def is_public_feed_source(source_name: str) -> bool:
    return source_name in public_feed_source_names()


def source_aliases(source_name: str) -> List[str]:
    aliases = SOURCE_ALIASES.get(source_name, [source_name])
    return list(dict.fromkeys([source_name, *aliases]))


def parse_db_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def source_health_status(last_run: str, latest_issue: str, record_count: int, source_name: str) -> str:
    if record_count == 0 and not last_run:
        return "Not implemented"
    if latest_issue:
        return "Needs attention"
    parsed = parse_db_time(last_run)
    if parsed:
        age_hours = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours > 36:
            return "Stale"
    if record_count > 0 or last_run:
        return "Implemented"
    return "Planned"


def source_operations_by_name() -> Dict[str, Dict[str, object]]:
    if not DB_FILE.exists():
        return {}
    conn = init_db()
    conn.row_factory = sqlite3.Row
    target_rows = conn.execute(
        """
        SELECT source_name, COUNT(*) AS count, MAX(created_at) AS latest
        FROM target_sources
        GROUP BY source_name
        """
    ).fetchall()
    evidence_rows = conn.execute(
        """
        SELECT source_name, COUNT(*) AS count, MAX(fetched_at) AS latest
        FROM research_evidence
        GROUP BY source_name
        """
    ).fetchall()
    payload_rows = conn.execute(
        """
        SELECT p.provider, p.endpoint, counts.count AS count, p.created_at AS latest,
               CASE WHEN p.status != 'ok' THEN 1 ELSE 0 END AS issue_count,
               CASE WHEN p.status != 'ok' THEN p.message ELSE '' END AS latest_issue
        FROM provider_payloads p
        JOIN (
            SELECT provider, endpoint, COUNT(*) AS count, MAX(id) AS latest_id
            FROM provider_payloads
            GROUP BY provider, endpoint
        ) counts
          ON counts.latest_id = p.id
        """
    ).fetchall()
    run_rows = conn.execute(
        """
        SELECT p.provider, p.refreshed_at AS latest, p.status, p.message
        FROM provider_refresh_runs p
        JOIN (
            SELECT provider, MAX(id) AS latest_id
            FROM provider_refresh_runs
            GROUP BY provider
        ) latest_runs
          ON latest_runs.latest_id = p.id
        """
    ).fetchall()
    raw_rows = conn.execute(
        """
        SELECT provider, endpoint, COUNT(*) AS count, MAX(created_at) AS latest,
               SUM(payload_size) AS payload_bytes
        FROM raw_ingestion_payloads
        GROUP BY provider, endpoint
        """
    ).fetchall()
    field_rows = conn.execute(
        """
        SELECT f.provider, f.field_name, p.refreshed_at AS latest,
               f.status, f.message
        FROM provider_field_status f
        JOIN provider_refresh_runs p ON p.id = f.run_id
        JOIN (
            SELECT provider, field_name, MAX(id) AS latest_id
            FROM provider_field_status
            GROUP BY provider, field_name
        ) latest_fields
          ON latest_fields.latest_id = f.id
        """
    ).fetchall()
    etrade_row = conn.execute(
        """
        SELECT COUNT(*) AS count, MAX(s.synced_at) AS latest
        FROM etrade_positions p
        JOIN etrade_sync_runs s ON s.id = p.run_id
        """
    ).fetchone()
    feedback_row = conn.execute(
        """
        SELECT COUNT(*) AS count, MAX(created_at) AS latest
        FROM recommendation_feedback
        """
    ).fetchone()
    conn.close()

    operations: Dict[str, Dict[str, object]] = {}

    def ensure(name: str) -> Dict[str, object]:
        return operations.setdefault(
            name,
            {
                "records": 0,
                "raw_records": 0,
                "raw_bytes": 0,
                "last_run": "",
                "latest_issue": "",
                "issues": 0,
                "current_issues": 0,
                "endpoints": set(),
            },
        )

    def update(
        name: str,
        records: int = 0,
        latest: object = "",
        issue: str = "",
        issues: int = 0,
        endpoint: str = "",
        current_issues: int | None = None,
    ) -> None:
        state = ensure(name)
        state["records"] = int(state.get("records") or 0) + int(records or 0)
        if endpoint:
            state["endpoints"].add(endpoint)
        parsed_existing = parse_db_time(state.get("last_run"))
        parsed_new = parse_db_time(latest)
        if parsed_new and (not parsed_existing or parsed_new > parsed_existing):
            state["last_run"] = str(latest)
            state["latest_issue"] = issue
            if current_issues is not None:
                state["current_issues"] = int(current_issues or 0)
        elif issue and not state.get("latest_issue"):
            state["latest_issue"] = issue
        if current_issues is not None and not parsed_new:
            state["current_issues"] = max(int(state.get("current_issues") or 0), int(current_issues or 0))
        state["issues"] = int(state.get("issues") or 0) + int(issues or 0)

    def update_raw(name: str, raw_records: int, raw_bytes: int, latest: object, endpoint: str = "") -> None:
        state = ensure(name)
        state["raw_records"] = int(state.get("raw_records") or 0) + int(raw_records or 0)
        state["raw_bytes"] = int(state.get("raw_bytes") or 0) + int(raw_bytes or 0)
        if endpoint:
            state["endpoints"].add(endpoint)
        parsed_existing = parse_db_time(state.get("last_run"))
        parsed_new = parse_db_time(latest)
        if parsed_new and (not parsed_existing or parsed_new > parsed_existing):
            state["last_run"] = str(latest)

    for row in target_rows:
        update(str(row["source_name"]), int(row["count"] or 0), row["latest"], endpoint="target_sources")
    for row in evidence_rows:
        update(str(row["source_name"]), int(row["count"] or 0), row["latest"], endpoint="research_evidence")
    for row in payload_rows:
        provider = str(row["provider"] or "")
        endpoint = str(row["endpoint"] or "")
        issue = str(row["latest_issue"] or "")
        update(provider, int(row["count"] or 0), row["latest"], issue, int(row["issue_count"] or 0), endpoint)
        if provider == "Alpha Vantage" and endpoint == "NEWS_SENTIMENT":
            update("Alpha Vantage news sentiment", int(row["count"] or 0), row["latest"], issue, int(row["issue_count"] or 0), endpoint)
        if provider == "FMP" and endpoint == "stock_news":
            update("FMP stock news", int(row["count"] or 0), row["latest"], issue, int(row["issue_count"] or 0), endpoint)
        if provider == "FMP" and endpoint in {
            "earnings_transcripts",
            "earning_call_transcript",
            "earning-call-transcript",
            "earning-call-transcript-dates",
            "earning-call-transcript-latest",
        }:
            update("FMP earnings transcripts", int(row["count"] or 0), row["latest"], issue, int(row["issue_count"] or 0), endpoint)
        if provider == "Finnhub" and endpoint == "company-news":
            update("Finnhub company news sentiment", int(row["count"] or 0), row["latest"], issue, int(row["issue_count"] or 0), endpoint)
        if provider == "SEC EDGAR" and endpoint == "submissions":
            update("SEC EDGAR submissions API", int(row["count"] or 0), row["latest"], issue, int(row["issue_count"] or 0), endpoint)
        if provider == "SEC EDGAR" and endpoint == "companyfacts":
            update("SEC EDGAR companyfacts API", int(row["count"] or 0), row["latest"], issue, int(row["issue_count"] or 0), endpoint)
        if endpoint in {"public_feed", "public_page_link"} and is_public_feed_source(provider):
            update(provider, int(row["count"] or 0), row["latest"], issue, int(row["issue_count"] or 0), endpoint)
    for row in raw_rows:
        provider = str(row["provider"] or "")
        endpoint = str(row["endpoint"] or "")
        update_raw(provider, int(row["count"] or 0), int(row["payload_bytes"] or 0), row["latest"], endpoint)
        if provider == "Alpha Vantage" and endpoint == "NEWS_SENTIMENT":
            update_raw("Alpha Vantage news sentiment", int(row["count"] or 0), int(row["payload_bytes"] or 0), row["latest"], endpoint)
        if provider == "FMP" and endpoint == "stock_news":
            update_raw("FMP stock news", int(row["count"] or 0), int(row["payload_bytes"] or 0), row["latest"], endpoint)
        if provider == "SEC EDGAR" and endpoint == "submissions":
            update_raw("SEC EDGAR submissions API", int(row["count"] or 0), int(row["payload_bytes"] or 0), row["latest"], endpoint)
        if provider == "SEC EDGAR" and endpoint == "companyfacts":
            update_raw("SEC EDGAR companyfacts API", int(row["count"] or 0), int(row["payload_bytes"] or 0), row["latest"], endpoint)
        if endpoint in {"public_feed", "public_feed_body", "public_page_body", "public_page_link"} and is_public_feed_source(provider):
            update_raw(provider, int(row["count"] or 0), int(row["payload_bytes"] or 0), row["latest"], endpoint)
    for row in run_rows:
        message = str(row["message"] or "")
        issue = message if str(row["status"] or "") != "ok" else ""
        update(
            str(row["provider"] or ""),
            0,
            row["latest"],
            issue,
            1 if issue else 0,
            "provider_run",
            1 if issue else 0,
        )
    for row in field_rows:
        provider = str(row["provider"] or "")
        field = str(row["field_name"] or "")
        issue = str(row["message"] or "") if str(row["status"] or "") != "ok" else ""
        current_issues = 1 if issue else 0
        update(provider, 0, row["latest"], issue, current_issues, field, current_issues)
        if provider == "Alpha Vantage" and field == "news_sentiment":
            update("Alpha Vantage news sentiment", 0, row["latest"], issue, current_issues, field, current_issues)
        if provider == "Finnhub" and field == "company_news":
            update("Finnhub company news sentiment", 0, row["latest"], issue, current_issues, field, current_issues)
        if provider == "FMP" and field == "stock_news":
            update("FMP stock news", 0, row["latest"], issue, current_issues, field, current_issues)
        if provider == "FMP" and field == "earnings_transcripts":
            update("FMP earnings transcripts", 0, row["latest"], issue, current_issues, field, current_issues)
        if provider == "SEC EDGAR" and field == "submissions":
            update("SEC EDGAR submissions API", 0, row["latest"], issue, current_issues, field, current_issues)
        if provider == "SEC EDGAR" and field == "companyfacts":
            update("SEC EDGAR companyfacts API", 0, row["latest"], issue, current_issues, field, current_issues)
        if field in {"public_feed", "public_page_link"} and is_public_feed_source(provider):
            update(provider, 0, row["latest"], issue, current_issues, field, current_issues)
    if etrade_row and int(etrade_row["count"] or 0):
        update("E*TRADE account data", int(etrade_row["count"] or 0), etrade_row["latest"], endpoint="etrade_positions")
    if feedback_row and int(feedback_row["count"] or 0):
        update("Manual user notes", int(feedback_row["count"] or 0), feedback_row["latest"], endpoint="recommendation_feedback")

    for source_name in list(operations):
        operations[source_name]["endpoints"] = ", ".join(sorted(operations[source_name]["endpoints"]))
    return operations


def operations_for_source(source_name: str, operations: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    merged = {
        "records": 0,
        "raw_records": 0,
        "raw_bytes": 0,
        "last_run": "",
        "latest_issue": "",
        "issues": 0,
        "current_issues": 0,
        "endpoints": set(),
    }
    for alias in source_aliases(source_name):
        state = operations.get(alias)
        if not state:
            continue
        merged["records"] = int(merged["records"] or 0) + int(state.get("records") or 0)
        merged["raw_records"] = int(merged["raw_records"] or 0) + int(state.get("raw_records") or 0)
        merged["raw_bytes"] = int(merged["raw_bytes"] or 0) + int(state.get("raw_bytes") or 0)
        parsed_existing = parse_db_time(merged.get("last_run"))
        parsed_new = parse_db_time(state.get("last_run"))
        if parsed_new and (not parsed_existing or parsed_new > parsed_existing):
            merged["last_run"] = str(state.get("last_run") or "")
        if state.get("latest_issue"):
            merged["latest_issue"] = str(state.get("latest_issue") or "")
        merged["issues"] = int(merged["issues"] or 0) + int(state.get("issues") or 0)
        merged["current_issues"] = int(merged["current_issues"] or 0) + int(state.get("current_issues") or 0)
        for endpoint in str(state.get("endpoints") or "").split(", "):
            if endpoint:
                merged["endpoints"].add(endpoint)
    merged["endpoints"] = ", ".join(sorted(merged["endpoints"]))
    merged["status"] = source_health_status(
        str(merged.get("last_run") or ""),
        str(merged.get("latest_issue") or ""),
        int(merged.get("records") or 0),
        source_name,
    )
    integration = load_source_integrations().get(source_name, {})
    merged["next_action"] = (
        SOURCE_IMPLEMENTATION_PLAN.get(source_name)
        or integration.get("next_step")
        or "Define provider, access method, cost, and evidence format."
    )
    return merged


def provider_filters_for_source(source_name: str) -> List[tuple[str, str | None]]:
    filters = {
        "SEC EDGAR": [("SEC EDGAR", None)],
        "SEC EDGAR submissions API": [("SEC EDGAR", "submissions")],
        "SEC EDGAR companyfacts API": [("SEC EDGAR", "companyfacts")],
        "Company investor relations": [("Company investor relations", "official_ir_page")],
        "Financial Modeling Prep": [("FMP", None), ("Financial Modeling Prep", None)],
        "FMP stock news": [("FMP", "stock_news")],
        "FMP earnings transcripts": [
            ("FMP", "earnings_transcripts"),
            ("FMP", "earning_call_transcript"),
            ("FMP", "earning-call-transcript"),
            ("FMP", "earning-call-transcript-dates"),
            ("FMP", "earning-call-transcript-latest"),
        ],
        "Alpha Vantage": [("Alpha Vantage", None)],
        "Alpha Vantage news sentiment": [("Alpha Vantage", "NEWS_SENTIMENT"), ("Alpha Vantage", "news_sentiment")],
        "Finnhub company news sentiment": [("Finnhub", "company-news"), ("Finnhub", "company_news")],
        "Finnhub earnings transcripts": [("Finnhub", "earnings_transcripts")],
        "Market news feeds": [("Alpha Vantage", "NEWS_SENTIMENT"), ("Finnhub", "company-news")],
        "E*TRADE account data": [("E*TRADE", None)],
    }
    for source in public_feed_source_names():
        filters[source] = [
            (source, "public_feed"),
            (source, "public_feed_body"),
            (source, "public_page_body"),
            (source, "public_page_link"),
        ]
    return filters.get(source_name, [])


def matches_provider_filter(provider: str, endpoint_or_field: str, filters: List[tuple[str, str | None]]) -> bool:
    for expected_provider, expected_endpoint in filters:
        if provider != expected_provider:
            continue
        if expected_endpoint is None or endpoint_or_field == expected_endpoint:
            return True
    return False


def source_record_rows(source_name: str, limit: int = 80) -> List[Dict[str, object]]:
    if not DB_FILE.exists():
        return []
    aliases = source_aliases(source_name)
    provider_filters = provider_filters_for_source(source_name)
    conn = init_db()
    conn.row_factory = sqlite3.Row
    records: List[Dict[str, object]] = []

    placeholders = ",".join("?" for _ in aliases)
    for row in conn.execute(
        f"""
        SELECT created_at, symbol, target_type, source_name, target_price,
               target_low, target_high, current_price, upside_pct, as_of_date,
               confidence, provider_endpoint, notes
        FROM target_sources
        WHERE source_name IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (*aliases, limit),
    ).fetchall():
        records.append(
            {
                "timestamp": row["created_at"],
                "kind": "Target",
                "symbol": row["symbol"],
                "record": f"{row['target_type']} target {fmt_money(float(row['target_price'] or 0))}",
                "value": f"Upside {fmt_pct(float(row['upside_pct'] or 0))}; confidence {row['confidence'] or 'unknown'}",
                "notes": row["notes"] or row["provider_endpoint"] or "",
            }
        )

    for row in conn.execute(
        f"""
        SELECT e.fetched_at, e.symbol, e.evidence_type, e.source_name, e.source_timestamp,
               e.title, e.summary, e.confidence, e.corroboration_status, e.provider_endpoint,
               GROUP_CONCAT(t.symbol || ':' || t.matched_text, ', ') AS matched_symbols
        FROM research_evidence e
        LEFT JOIN evidence_symbol_tags t ON t.evidence_id = e.id
        WHERE e.source_name IN ({placeholders})
        GROUP BY e.id
        ORDER BY e.fetched_at DESC, e.id DESC
        LIMIT ?
        """,
        (*aliases, limit),
    ).fetchall():
        matched_symbols = str(row["matched_symbols"] or "").strip()
        notes = row["summary"] or row["provider_endpoint"] or ""
        if matched_symbols:
            notes = f"Matched symbols: {matched_symbols}. {notes}"
        records.append(
            {
                "timestamp": row["fetched_at"] or row["source_timestamp"],
                "kind": "Evidence",
                "symbol": row["symbol"],
                "record": f"{row['evidence_type']}: {row['title'] or 'Untitled'}",
                "value": f"Confidence {row['confidence'] or 'unknown'}; corroboration {row['corroboration_status'] or 'unknown'}",
                "notes": notes,
            }
        )

    payload_rows = conn.execute(
        """
        SELECT created_at, provider, endpoint, symbol, status, message
        FROM provider_payloads
        ORDER BY created_at DESC, id DESC
        LIMIT 500
        """
    ).fetchall()
    for row in payload_rows:
        if not matches_provider_filter(str(row["provider"]), str(row["endpoint"]), provider_filters):
            continue
        records.append(
            {
                "timestamp": row["created_at"],
                "kind": "Provider payload",
                "symbol": row["symbol"] or "",
                "record": f"{row['provider']} {row['endpoint']}",
                "value": row["status"],
                "notes": row["message"] or "Payload captured",
            }
        )

    raw_rows = conn.execute(
        """
        SELECT created_at, provider, endpoint, symbol, status, content_hash,
               payload_size, payload_ref, message
        FROM raw_ingestion_payloads
        ORDER BY created_at DESC, id DESC
        LIMIT 500
        """
    ).fetchall()
    for row in raw_rows:
        if not matches_provider_filter(str(row["provider"]), str(row["endpoint"]), provider_filters):
            continue
        ref = row["payload_ref"] or (f"hash {str(row['content_hash'] or '')[:12]}" if row["content_hash"] else "")
        records.append(
            {
                "timestamp": row["created_at"],
                "kind": "Raw payload",
                "symbol": row["symbol"] or "",
                "record": f"{row['provider']} {row['endpoint']}",
                "value": f"{row['status']}; {int(row['payload_size'] or 0):,} bytes",
                "notes": ref or row["message"] or "Raw ingestion ledger row",
            }
        )

    status_rows = conn.execute(
        """
        SELECT p.refreshed_at, f.symbol, f.provider, f.field_name, f.status, f.message
        FROM provider_field_status f
        JOIN provider_refresh_runs p ON p.id = f.run_id
        ORDER BY p.refreshed_at DESC, f.id DESC
        LIMIT 500
        """
    ).fetchall()
    for row in status_rows:
        if not matches_provider_filter(str(row["provider"]), str(row["field_name"]), provider_filters):
            continue
        records.append(
            {
                "timestamp": row["refreshed_at"],
                "kind": "Provider status",
                "symbol": row["symbol"] or "",
                "record": f"{row['provider']} {row['field_name']}",
                "value": row["status"],
                "notes": row["message"] or "",
            }
        )

    if source_name == "E*TRADE account data":
        for row in conn.execute(
            """
            SELECT s.synced_at, p.symbol, p.quantity, p.last_price, p.market_value,
                   p.pct_of_portfolio, p.position_type
            FROM etrade_positions p
            JOIN etrade_sync_runs s ON s.id = p.run_id
            ORDER BY s.synced_at DESC, p.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall():
            records.append(
                {
                    "timestamp": row["synced_at"],
                    "kind": "Position",
                    "symbol": row["symbol"],
                    "record": f"{row['quantity']} shares at {fmt_money(float(row['last_price'] or 0))}",
                    "value": f"Market value {fmt_money(float(row['market_value'] or 0))}; portfolio {fmt_pct(float(row['pct_of_portfolio'] or 0))}",
                    "notes": row["position_type"] or "",
                }
            )

    if source_name == "Manual user notes":
        for row in conn.execute(
            """
            SELECT created_at, symbol, feedback_type, notes
            FROM recommendation_feedback
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall():
            records.append(
                {
                    "timestamp": row["created_at"],
                    "kind": "Feedback",
                    "symbol": row["symbol"],
                    "record": row["feedback_type"],
                    "value": "User feedback",
                    "notes": row["notes"] or "",
                }
            )

    conn.close()
    records.sort(key=lambda record: parse_db_time(record.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return records[:limit]


def source_record_detail_html(
    source_name: str,
    operations: Dict[str, object],
    integration: Dict[str, str] | None = None,
) -> str:
    records = source_record_rows(source_name)
    if records:
        rows = [
            [
                record["timestamp"] or "unknown",
                record["kind"],
                record["symbol"],
                record["record"],
                record["value"],
                str(record["notes"] or "")[:500],
            ]
            for record in records
        ]
        record_table = html_table(
            ["Updated", "Kind", "Symbol", "Record", "Value/Status", "Notes"],
            rows,
            "source-record-table",
        )
    else:
        record_table = "<p>No records captured yet for this source.</p>"
    integration = integration or {}
    integration_block = ""
    if integration:
        official_url = integration.get("official_url", "")
        official_link = (
            f'<a href="{html.escape(official_url)}">{html.escape(official_url)}</a>'
            if official_url
            else "n/a"
        )
        integration_block = f"""
          <div class="source-integration-plan">
            <h4>Integration Plan</h4>
            <p><strong>Status:</strong> {html.escape(integration.get("implementation_status", "unknown"))}</p>
            <p><strong>Tier:</strong> {html.escape(str(integration.get("source_tier") or "core"))}</p>
            <p><strong>Access model:</strong> {html.escape(integration.get("access_model", "unknown"))}</p>
            <p><strong>Ingestion method:</strong> {html.escape(str(integration.get("ingestion_method") or "not defined"))}</p>
            <p><strong>Content policy:</strong> {html.escape(str(integration.get("content_policy") or "not defined"))}</p>
            <p><strong>Official URL:</strong> {official_link}</p>
            <p><strong>Planned use:</strong> {html.escape(integration.get("planned_use", ""))}</p>
            <p><strong>Next step:</strong> {html.escape(integration.get("next_step", ""))}</p>
            <p><strong>User action:</strong> {html.escape(integration.get("user_action_needed", ""))}</p>
          </div>
        """
    return f"""
      <div class="source-detail-card">
        <div class="section-title">
          <h3>{html.escape(source_name)} Records</h3>
          <span class="section-note">{html.escape(str(operations.get("status") or "Unknown"))} · {int(operations.get("records") or 0)} record(s)</span>
        </div>
        <p><strong>Last run:</strong> {html.escape(str(operations.get("last_run") or "Not run"))}</p>
        <p><strong>Latest issue:</strong> {html.escape(str(operations.get("latest_issue") or "No current issue"))}</p>
        <p><strong>Next action:</strong> {html.escape(str(operations.get("next_action") or "Define implementation plan."))}</p>
        {integration_block}
        {record_table}
      </div>
    """


def source_health_alert_rows(source_rows: List[Dict[str, object]], limit: int = 12) -> List[List[object]]:
    alerts = []
    for row in source_rows:
        operations = row["operations"]
        status = str(operations.get("status") or "")
        latest_issue = str(operations.get("latest_issue") or "")
        records = int(operations.get("records") or 0)
        if status == "Implemented" and not latest_issue:
            continue
        if latest_issue:
            severity = "High"
        elif status in {"Not implemented", "Stale"}:
            severity = "Medium"
        else:
            severity = "Low"
        alerts.append(
            [
                severity,
                row["source_name"],
                status or "Unknown",
                records,
                str(operations.get("last_run") or "Not run"),
                latest_issue or "No records captured yet",
                str(operations.get("next_action") or ""),
            ]
        )
    severity_rank = {"High": 0, "Medium": 1, "Low": 2}
    alerts.sort(key=lambda item: (severity_rank.get(str(item[0]), 9), str(item[1])))
    return alerts[:limit]


def source_health_summary(source_rows: List[Dict[str, object]]) -> Dict[str, object]:
    summary = {
        "implemented": 0,
        "needs_attention": 0,
        "stale": 0,
        "not_implemented": 0,
        "healthy": 0,
        "top_alerts": [],
    }
    alerts = source_health_alert_rows(source_rows, limit=5)
    summary["top_alerts"] = alerts
    for row in source_rows:
        status = str(row["operations"].get("status") or "")
        if status == "Implemented":
            summary["implemented"] += 1
            summary["healthy"] += 1
        elif status == "Needs attention":
            summary["needs_attention"] += 1
            summary["implemented"] += 1
        elif status == "Stale":
            summary["stale"] += 1
            summary["implemented"] += 1
        elif status == "Not implemented":
            summary["not_implemented"] += 1
    return summary


SOURCE_ISSUE_GROUPS = [
    {
        "label": "Network / DNS",
        "patterns": [
            r"\bdns\b",
            r"name resolution",
            r"nodename nor servname",
            r"urlopen",
            r"connection",
            r"could not resolve",
            r"temporary failure",
        ],
        "reason": "Network or DNS failures affected provider refreshes.",
        "next_action": "Check network/API availability.",
    },
    {
        "label": "Provider error",
        "patterns": [
            r"http\s+5\d\d",
            r"server error",
            r"bad gateway",
            r"service unavailable",
            r"gateway timeout",
        ],
        "reason": "Provider-side errors affected source refreshes.",
        "next_action": "Retry after provider recovery.",
    },
    {
        "label": "Provider access",
        "patterns": [
            r"http\s+40[13]",
            r"\bplan\b",
            r"\bpaid\b",
            r"\bblocked\b",
            r"\bauth",
            r"\bkey\b",
            r"\bquota\b",
            r"rate[- ]?limit",
        ],
        "reason": "Access, plan, credential, or quota limits affected sources.",
        "next_action": "Review provider access.",
    },
    {
        "label": "Missing data",
        "patterns": [
            r"no records",
            r"missing feed",
            r"no parseable items",
            r"\bstale\b",
            r"not implemented",
            r"no rss",
            r"not run",
        ],
        "reason": "Configured sources have missing, stale, or unimplemented data.",
        "next_action": "Review source setup.",
    },
]


def classify_source_issue(alert: List[object]) -> str:
    text = " ".join(str(part or "") for part in alert).lower()
    for group in SOURCE_ISSUE_GROUPS:
        if any(re.search(pattern, text) for pattern in group["patterns"]):
            return str(group["label"])
    return "Other"


def source_issue_group_rows(health_alert_rows: List[List[object]]) -> List[List[object]]:
    grouped: Dict[str, Dict[str, object]] = {}
    for alert in health_alert_rows:
        label = classify_source_issue(alert)
        state = grouped.setdefault(
            label,
            {
                "sources": set(),
                "high": 0,
            },
        )
        if len(alert) > 1:
            state["sources"].add(str(alert[1]))
        if alert and str(alert[0]) == "High":
            state["high"] = int(state.get("high") or 0) + 1

    group_details = {str(group["label"]): group for group in SOURCE_ISSUE_GROUPS}
    group_order = [str(group["label"]) for group in SOURCE_ISSUE_GROUPS] + ["Other"]
    rows = []
    for label in group_order:
        if label not in grouped:
            continue
        state = grouped[label]
        source_count = len(state["sources"])
        high_count = int(state.get("high") or 0)
        if high_count > 0:
            severity = "Needs attention"
        elif label == "Other":
            severity = "Info"
        else:
            severity = "Review"
        details = group_details.get(
            label,
            {
                "reason": "Unclassified source issue needs review.",
                "next_action": "Review detailed source alerts.",
            },
        )
        rows.append(
            [
                label,
                severity,
                source_count,
                str(details["reason"]),
                str(details["next_action"]),
            ]
        )
    return rows


def ranked_symbol_context(ranked: List[Dict[str, object]] | None) -> Dict[str, Dict[str, object]]:
    context: Dict[str, Dict[str, object]] = {}
    for rank, row in enumerate(ranked or [], start=1):
        item = row.get("input")
        symbol = getattr(item, "symbol", "") if item is not None else str(row.get("symbol") or "")
        if not symbol:
            continue
        context[symbol.upper()] = {
            "rank": rank,
            "action": str(row.get("action") or ""),
            "score": float(row.get("score") or 0),
        }
    return context


def provider_gap_value(row: object, key: str) -> str:
    if isinstance(row, dict):
        return str(row.get(key) or "")
    try:
        return str(row[key] or "")  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return ""


def provider_blocker_root_cause(provider: str, field_name: str, status: str, message: str) -> str:
    text = " ".join([provider, field_name, status, message]).lower()
    if re.search(r"429|rate[- ]?limit|quota|too many", text):
        return "Rate or quota limit"
    if re.search(r"401|unauthorized|forbidden|api[-_ ]?key|token|credential|auth", text):
        return "Credential or access issue"
    if re.search(r"403|blocked|paid|premium|upgrade|\bplan\b", text):
        return "Provider plan/access blocker"
    if re.search(r"dns|nodename|name resolution|temporary failure|urlopen|connection|timed out|network", text):
        return "Network / DNS"
    if re.search(r"5\d\d|server error|bad gateway|service unavailable|gateway timeout", text):
        return "Provider error"
    if re.search(r"no records|missing|empty|not found|not run|stale", text):
        return "Missing provider data"
    return "Provider review needed"


def provider_blocked_decision_field(field_name: str, message: str) -> str:
    field_text = field_name.lower()
    text = f"{field_name} {message}".lower()
    if any(term in field_text for term in ["current_price", "quote"]):
        return "Current price reliability"
    if any(term in field_text for term in ["analyst", "target", "pt_consensus"]):
        return "Analyst target breadth"
    if any(term in field_text for term in ["price_history", "technical", "historical", "chart"]):
        return "Price trend confidence"
    if any(term in field_text for term in ["sec", "filing", "companyfacts", "official_ir", "ir_page", "investor"]):
        return "Primary-source evidence"
    if any(term in text for term in ["news", "sentiment", "transcript", "earnings", "recommendation"]):
        return "Research/news verification"
    if any(term in text for term in ["analyst", "target", "price target", "pt_consensus"]):
        return "Analyst target breadth"
    if any(term in text for term in ["price", "quote"]):
        return "Current price reliability"
    if any(term in text for term in ["sec", "filing", "companyfacts", "official_ir", "ir_page", "investor"]):
        return "Primary-source evidence"
    return "Insight confidence"


def provider_blocker_next_action(provider: str, field_name: str, root_cause: str, symbol: str) -> str:
    provider_text = provider.lower()
    field_text = field_name.lower()
    if root_cause == "Network / DNS":
        return f"Retry with network access: scripts/show_provider_gaps.py --symbol {symbol}" if symbol else "Retry with network access."
    if root_cause in {"Credential or access issue", "Provider plan/access blocker", "Rate or quota limit"}:
        if "official" in provider_text or "ir" in field_text:
            return f"Review official IR access/URL, then run scripts/ingest_official_ir.py --symbols {symbol}"
        if "sec" in provider_text or "sec" in field_text:
            return f"Set SEC access/user-agent if needed, then run scripts/ingest_sec.py {symbol}"
        if "benzinga" in provider_text:
            return "Set BENZINGA_API_KEY or add a row to config/manual_analyst_targets.csv"
        if "finnhub" in provider_text:
            return f"Check FINNHUB_API_KEY/access, then run scripts/ingest_finnhub.py {symbol}"
        if "financial modeling prep" in provider_text or provider_text == "fmp":
            return f"Check FMP plan/key, then run scripts/refresh_market_data.py --symbol {symbol}"
        return f"Review provider access, then run scripts/show_provider_gaps.py --symbol {symbol}" if symbol else "Review provider access."
    if root_cause == "Provider error":
        return f"Retry provider pull for {symbol} after provider recovers." if symbol else "Retry after provider recovers."
    if "analyst" in field_text or "target" in field_text:
        return "Run scripts/ingest_benzinga_analyst_targets.py if keyed; otherwise update config/manual_analyst_targets.csv"
    if "price_history" in field_text or "technical" in field_text:
        return f"Run scripts/ingest_price_history.py {symbol}" if symbol else "Run scripts/ingest_price_history.py"
    if "official" in provider_text or "ir" in field_text:
        return f"Run scripts/ingest_official_ir.py --symbols {symbol}"
    if "sec" in provider_text or "sec" in field_text:
        return f"Run scripts/ingest_sec.py {symbol}"
    return f"Run scripts/show_provider_gaps.py --symbol {symbol}" if symbol else "Run scripts/show_provider_gaps.py"


def provider_blocker_review_rows(
    provider_gap_rows: List[object],
    ranked: List[Dict[str, object]] | None = None,
    limit: int = 15,
) -> List[List[object]]:
    symbol_context = ranked_symbol_context(ranked)
    reviewed = []
    seen: Set[tuple[str, str, str, str]] = set()
    for row in provider_gap_rows:
        symbol = provider_gap_value(row, "symbol").upper()
        provider = provider_gap_value(row, "provider")
        field_name = provider_gap_value(row, "field_name")
        status = provider_gap_value(row, "status")
        message = provider_gap_value(row, "message")
        if str(status).lower() in {"ok", "healthy"}:
            continue
        key = (symbol, provider, field_name, status)
        if key in seen:
            continue
        seen.add(key)
        root_cause = provider_blocker_root_cause(provider, field_name, status, message)
        blocked_field = provider_blocked_decision_field(field_name, message)
        ranked_context = symbol_context.get(symbol, {})
        rank = int(ranked_context.get("rank") or 9999)
        score = float(ranked_context.get("score") or 0)
        if root_cause in {"Provider plan/access blocker", "Credential or access issue"}:
            severity = "High"
        elif root_cause in {"Network / DNS", "Rate or quota limit"}:
            severity = "Medium"
        else:
            severity = "Review"
        decision_context = (
            f"Rank {rank} / {ranked_context.get('action')} / {score:.1f}"
            if ranked_context
            else "Unranked or not in current scored list"
        )
        reviewed.append(
            {
                "rank": rank,
                "score": score,
                "severity": severity,
                "row": [
                    severity,
                    symbol or "GLOBAL",
                    provider,
                    field_name,
                    blocked_field,
                    root_cause,
                    decision_context,
                    message[:120] if message else status or "No detail recorded",
                    provider_blocker_next_action(provider, field_name, root_cause, symbol),
                ],
            }
        )

    severity_rank = {"High": 0, "Medium": 1, "Review": 2}
    reviewed.sort(key=lambda item: (severity_rank.get(str(item["severity"]), 9), int(item["rank"]), -float(item["score"]), str(item["row"][1])))
    return [item["row"] for item in reviewed[:limit]]


def feedback_record_count(source_operations: Dict[str, Dict[str, object]]) -> int:
    return int(source_operations.get("Manual user notes", {}).get("records") or 0)


def next_day_readiness(
    watchlist_rows: List[Dict[str, object]],
    health_summary: Dict[str, object],
    health_alert_rows: List[List[object]],
) -> Dict[str, object]:
    if not watchlist_rows:
        return {
            "item": {
                "label": "Next-day setup",
                "status": "Needs attention",
                "reason": "No next-day watchlist candidates are available.",
                "next_action": "Open Next-Day Watchlist",
            },
            "preview": None,
        }

    row = watchlist_rows[0]
    item = row.get("input")
    target = row.get("target")
    if not isinstance(item, ResearchInput):
        return {
            "item": {
                "label": "Next-day setup",
                "status": "Needs attention",
                "reason": "Top next-day candidate is missing input context.",
                "next_action": "Open Next-Day Watchlist",
            },
            "preview": None,
        }

    target_status = data_status_for_target(item, target)
    confidence = target_confidence_text(item, target)
    current_text = fmt_money(item.current_price) if item.current_price else "Needs refresh"
    target_text = target_price_text(item, target)
    upside_text = target_upside_text(item, target)
    rationale = str(row.get("rationale") or "")
    if not rationale and isinstance(row.get("breakdown"), ScoreBreakdown):
        rationale = action_rationale(
            item,
            str(row.get("action") or "Watch"),
            row["breakdown"],
            float(row.get("position_after_buy_pct") or 0.0),
            target if isinstance(target, BlendedTarget) else None,
        )

    missing_reasons = []
    if item.current_price <= 0:
        missing_reasons.append("price")
    if target_text == "Needs refresh" or target_status.startswith("Needs"):
        missing_reasons.append("target")
    if not rationale:
        missing_reasons.append("rationale")

    preview = {
        "symbol": item.symbol,
        "action": str(row.get("action") or "Watch"),
        "score": f"{float(row.get('score') or 0.0):.1f}",
        "current": current_text,
        "target": target_text,
        "upside": upside_text,
        "data_status": target_status,
        "rationale": rationale,
    }

    if missing_reasons:
        return {
            "item": {
                "label": "Next-day setup",
                "status": "Needs attention",
                "reason": f"{item.symbol} needs {', '.join(missing_reasons)} before next-day review.",
                "next_action": "Open Next-Day Watchlist",
            },
            "preview": preview,
        }

    has_review_health = bool(health_alert_rows) or int(health_summary.get("stale") or 0) or int(health_summary.get("not_implemented") or 0)
    weak_target = confidence.lower() not in {"medium", "high"} or target_status in {"Partial blend", "Wide range"}
    if weak_target or has_review_health:
        reason_parts = []
        if weak_target:
            reason_parts.append(f"{confidence.title()} confidence; {target_status}.")
        if has_review_health:
            reason_parts.append("Source health has review items.")
        return {
            "item": {
                "label": "Next-day setup",
                "status": "Review",
                "reason": " ".join(reason_parts),
                "next_action": "Open Next-Day Watchlist",
            },
            "preview": preview,
        }

    return {
        "item": {
            "label": "Next-day setup",
            "status": "Ready",
            "reason": f"{item.symbol} has price, target, and rationale ready.",
            "next_action": "Open Next-Day Watchlist",
        },
        "preview": preview,
    }


def pre_market_readiness_items(
    top_row: Dict[str, object] | None,
    holdings_rows: List[List[object]],
    health_summary: Dict[str, object],
    health_alert_rows: List[List[object]],
    feedback_count: int,
    next_day_item: Dict[str, str] | None = None,
) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    item = top_row.get("input") if top_row else None
    target = top_row.get("target") if top_row else None
    symbol = item.symbol if isinstance(item, ResearchInput) else "top candidate"

    if isinstance(item, ResearchInput) and item.current_price > 0:
        items.append(
            {
                "label": "Price data",
                "status": "Ready",
                "reason": f"{symbol} has a current price.",
                "next_action": "Review Action Queue",
            }
        )
    else:
        items.append(
            {
                "label": "Price data",
                "status": "Needs attention",
                "reason": f"{symbol} is missing current price data.",
                "next_action": "Open Data Gaps",
            }
        )

    target_status = data_status_for_target(item, target) if isinstance(item, ResearchInput) else "Needs target"
    confidence = target_confidence_text(item, target) if isinstance(item, ResearchInput) else "Low"
    if (
        (isinstance(item, ResearchInput) and target is None and item.target_price <= 0)
        or ("target" in target_status.lower() and target_status.startswith("Needs"))
    ):
        target_readiness = "Needs attention"
        target_reason = f"{symbol} needs a usable target before acting."
        target_next_action = "Open Data Gaps"
    elif target_status == "Blended" and confidence.lower() in {"medium", "high"}:
        target_readiness = "Ready"
        target_reason = f"{confidence.title()} confidence blended target is available."
        target_next_action = "Review Action Queue"
    else:
        target_readiness = "Review"
        target_reason = f"{confidence.title()} confidence; {target_status}."
        target_next_action = "Open target detail"
    items.append(
        {
            "label": "Target trust",
            "status": target_readiness,
            "reason": target_reason,
            "next_action": target_next_action,
        }
    )

    high_alerts = [row for row in health_alert_rows if row and row[0] == "High"]
    if high_alerts:
        source_status = "Needs attention"
        source_reason = f"{len(high_alerts)} source issue(s) need review."
        source_next_action = "Open Health & Trends"
    elif int(health_summary.get("stale") or 0) or int(health_summary.get("not_implemented") or 0):
        stale_count = int(health_summary.get("stale") or 0)
        not_implemented = int(health_summary.get("not_implemented") or 0)
        source_status = "Review"
        source_reason = f"{stale_count} stale; {not_implemented} not implemented."
        source_next_action = "Open Research Sources"
    else:
        source_status = "Ready"
        source_reason = "No active source blockers."
        source_next_action = "Review Action Queue"
    items.append(
        {
            "label": "Source health",
            "status": source_status,
            "reason": source_reason,
            "next_action": source_next_action,
        }
    )

    holding_sources = {str(row[1]).lower() for row in holdings_rows if len(row) > 1}
    if holdings_rows and any(source not in {"manual", "-", ""} for source in holding_sources):
        holdings_status = "Ready"
        holdings_reason = "Broker or synced holdings context is available."
        holdings_next_action = "Review Current Holdings"
    elif holdings_rows:
        holdings_status = "Review"
        holdings_reason = "Using manual holdings context."
        holdings_next_action = "Open Current Holdings"
    else:
        holdings_status = "Review"
        holdings_reason = "No holdings context was found."
        holdings_next_action = "Open Current Holdings"
    items.append(
        {
            "label": "Holdings context",
            "status": holdings_status,
            "reason": holdings_reason,
            "next_action": holdings_next_action,
        }
    )

    if feedback_count > 0:
        feedback_status = "Ready"
        feedback_reason = f"{feedback_count} feedback record(s) captured."
        feedback_next_action = "Review Feedback tab"
    else:
        feedback_status = "Review"
        feedback_reason = "No feedback history captured yet."
        feedback_next_action = "Use Feedback tab"
    items.append(
        {
            "label": "Feedback review",
            "status": feedback_status,
            "reason": feedback_reason,
            "next_action": feedback_next_action,
        }
    )

    if next_day_item:
        items.append(next_day_item)

    return items


def readiness_class(status: str) -> str:
    return status.lower().replace(" ", "-")


def next_day_preview_html(preview: Dict[str, str] | None) -> str:
    if not preview:
        return ""
    return f"""
        <div class="next-day-preview">
          <div class="next-day-preview-head">
            <div>
              <span class="label">Top next-day watch</span>
              <strong>{html.escape(preview["symbol"])} · {html.escape(preview["action"])} · {html.escape(preview["score"])}</strong>
            </div>
            <button class="link-button" type="button" data-open-rec-tab="nextDaySubtab">Open Next-Day Watchlist</button>
          </div>
          <div class="next-day-preview-metrics">
            <span>Current <strong>{html.escape(preview["current"])}</strong></span>
            <span>Target <strong>{html.escape(preview["target"])}</strong></span>
            <span>Upside <strong>{html.escape(preview["upside"])}</strong></span>
            <span>Status <strong>{html.escape(preview["data_status"])}</strong></span>
          </div>
          <p>{html.escape(preview["rationale"])}</p>
        </div>
    """


def pre_market_readiness_html(items: List[Dict[str, str]], next_day_preview: Dict[str, str] | None = None) -> str:
    cards = []
    for item in items:
        status = str(item.get("status") or "Review")
        cards.append(
            f"""
            <div class="readiness-card readiness-{readiness_class(status)}">
              <div class="readiness-card-head">
                <span class="label">{html.escape(str(item.get("label") or ""))}</span>
                <span class="readiness-status">{html.escape(status)}</span>
              </div>
              <strong>{html.escape(str(item.get("reason") or ""))}</strong>
              <div class="readiness-next">{html.escape(str(item.get("next_action") or ""))}</div>
            </div>
            """
        )
    return f"""
      <section class="readiness-section" aria-label="Pre-market readiness">
        <div class="section-title">
          <h2>Pre-Market Readiness</h2>
          <span class="section-note">Advisory checks only; recommendations remain visible</span>
        </div>
        <div class="readiness-grid">
          {''.join(cards)}
        </div>
        {next_day_preview_html(next_day_preview)}
      </section>
    """


def expandable_source_table(source_rows: List[Dict[str, object]]) -> str:
    headers = [
        "Source",
        "Tier",
        "Category",
        "Status",
        "Records",
        "Raw",
        "Last Run",
        "Latest Issue",
        "Next Action",
        "Type",
        "Coverage",
        "Quality",
        "Effective Weight",
        "Corroborate",
    ]
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = []
    for index, row in enumerate(source_rows, start=1):
        source_name = str(row["source_name"])
        detail_id = f"source-detail-{index}"
        operations = row["operations"]
        integration = row.get("integration", {})
        body.append(
            f"""
            <tr class="expandable-source-row" tabindex="0" role="button" aria-expanded="false" aria-controls="{detail_id}">
              <td>{html.escape(source_name)}</td>
              <td>{html.escape(str(integration.get("source_tier") or "core"))}</td>
              <td>{html.escape(str(integration.get("source_category") or row["source_type"]))}</td>
              <td>{html.escape(str(operations.get("status") or ""))}</td>
              <td>{int(operations.get("records") or 0)}</td>
              <td>{int(operations.get("raw_records") or 0)}</td>
              <td>{html.escape(str(operations.get("last_run") or "Not run"))}</td>
              <td>{html.escape(str(operations.get("latest_issue") or "No current issue"))}</td>
              <td>{html.escape(str(operations.get("next_action") or ""))}</td>
              <td>{html.escape(str(row["source_type"]))}</td>
              <td>{html.escape(str(row["coverage"]))}</td>
              <td>{html.escape(str(row["quality"]))}</td>
              <td>{html.escape(str(row["effective_weight"]))}</td>
              <td>{html.escape(str(row["corroborate"]))}</td>
            </tr>
            <tr id="{detail_id}" class="source-detail-row" hidden>
              <td colspan="{len(headers)}">
                {source_record_detail_html(source_name, operations, integration)}
              </td>
            </tr>
            """
        )
    return (
        '<table class="source-status-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def run_analysis(
    persist: bool = True,
    write_context: bool = False,
    report_date: str | None = None,
) -> Dict[str, object]:
    research = load_research_inputs()
    research_sources = load_research_sources()
    source_integrations = load_source_integrations()
    source_operations = source_operations_by_name()
    targets = load_targets()
    price_history = latest_price_history_by_symbol()
    apply_price_history_fallback(research, price_history)
    price_counts = price_reliability_counts(research)
    reliability_status = reliability_mode(price_counts)
    latest_refresh = latest_provider_refresh_text()
    research_by_symbol = {item.symbol: item for item in research}
    positions = merged_positions(
        latest_etrade_positions(),
        manual_positions(targets, research_by_symbol),
    )
    stored_evidence_by_symbol = latest_evidence_by_symbol()
    stored_score_signals_by_symbol = latest_score_signals_by_symbol()
    signal_counts = score_signal_counts(stored_score_signals_by_symbol)
    source_quality_rows = latest_source_quality_rows()
    source_quality_lookup = {
        str(row.get("source_name") or ""): row
        for row in source_quality_rows
    }
    account_value = float(targets.get("account_value", 50000))
    monthly_contribution = float(targets.get("monthly_contribution", 1000))
    default_buy_amount = min(monthly_contribution, account_value * 0.05)

    now = datetime.now()
    report_date = report_date or f"{now:%Y-%m-%d}"
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"daily-recommendation-{report_date}.md"
    dashboard_path = REPORTS_DIR / f"dashboard-{report_date}.html"
    csv_path = REPORTS_DIR / f"daily-recommendation-{report_date}.csv"
    email_path = REPORTS_DIR / f"email-summary-{report_date}.txt"
    end_of_day_path = REPORTS_DIR / f"end-of-day-{report_date}.md"
    watchlist_path = REPORTS_DIR / f"next-day-watchlist-{report_date}.md"
    report_context_path = REPORTS_DIR / f"report-context-{report_date}.json"
    ai_context_path = REPORTS_DIR / f"ai-analysis-context-{report_date}.json"
    ai_briefs_markdown_path = REPORTS_DIR / f"ai-insight-briefs-{report_date}.md"
    ai_briefs_json_path = REPORTS_DIR / f"ai-insight-briefs-{report_date}.json"
    ai_briefs_html_path = REPORTS_DIR / f"ai-insight-briefs-{report_date}.html"
    db_run_id = (
        record_recommendation_run(
            report_date=report_date,
            report_path=report_path,
            dashboard_path=dashboard_path,
            csv_path=csv_path,
            email_path=email_path,
            account_value=account_value,
            monthly_contribution=monthly_contribution,
            notes=f"Daily report generation with target-source capture. Reliability: {reliability_status}.",
            workflow_run_id=workflow_run_id_from_env(),
        )
        if persist
        else 0
    )
    generated_target_rows = target_source_rows(research, db_run_id, report_date, targets)
    stored_target_sources = record_target_sources(db_run_id, generated_target_rows) if persist else 0
    provider_gap_rows = latest_provider_gaps()
    blended_by_symbol, blended_db_rows = blended_target_rows(
        generated_target_rows,
        db_run_id,
        targets,
        research_by_symbol,
        provider_gap_rows,
    )
    stored_blended_targets = record_blended_targets(db_run_id, blended_db_rows) if persist else 0
    target_counts = target_counts_by_symbol(generated_target_rows)
    previous_score_history_by_symbol = latest_score_history_by_symbol()

    scored = []
    for item in research:
        blended = blended_by_symbol.get(item.symbol)
        breakdown = score_stock(item, positions, blended)
        insight = compute_insight_signal(
            item,
            breakdown,
            blended,
            price_history,
            stored_evidence_by_symbol,
            target_counts,
            previous_score_history_by_symbol,
        )
        score = insight.final_score
        position = positions.get(item.symbol, {})
        market_value = float(position.get("market_value", 0) or 0)
        portfolio_pct = (market_value / account_value) * 100 if account_value else 0
        position_after_buy_pct = (
            ((market_value + default_buy_amount) / account_value) * 100
            if account_value
            else 0
        )
        action = action_for(item, score, position_after_buy_pct, targets)
        scored.append(
            {
                "input": item,
                "target": blended,
                "base_score": breakdown.total,
                "score": score,
                "breakdown": breakdown,
                "insight": insight,
                "action": action,
                "market_value": market_value,
                "portfolio_pct": portfolio_pct,
                "position_after_buy_pct": position_after_buy_pct,
            }
        )

    ranked = sorted(scored, key=lambda row: row["score"], reverse=True)
    target_drilldowns = target_drilldowns_by_symbol(ranked, generated_target_rows)
    score_signal_rows = score_signal_storage_rows(db_run_id, report_date, ranked)
    stored_score_signals = record_score_signals(score_signal_rows) if persist else 0
    stored_score_signals_by_symbol = latest_score_signals_by_symbol()
    signal_counts = {"signals": stored_score_signals, "symbols": len(ranked)}
    score_db_rows = []
    for row in ranked:
        item = row["input"]
        target = row.get("target")
        insight = row["insight"]
        score_db_rows.append(
            {
                "run_id": db_run_id,
                "report_date": report_date,
                "symbol": item.symbol,
                "company": item.company,
                "sleeve": item.sleeve,
                "trade_type": item.trade_type,
                "action": row["action"],
                "score": round(float(row["score"]), 4),
                "current_price": item.current_price,
                "target_price": target.target_price if target else item.target_price,
                "upside_pct": target.upside_pct if target else item.upside_pct,
                "target_confidence": target_confidence_text(item, target),
                "data_status": data_status_for_target(item, target),
                "score_breakdown": score_summary_with_insight(row["breakdown"], insight),
                "rationale": action_rationale(
                    item,
                    row["action"],
                    row["breakdown"],
                    row["position_after_buy_pct"],
                    target,
                    targets,
                ),
            }
        )
    stored_scores = record_recommendation_scores(db_run_id, score_db_rows) if persist else 0
    score_history_by_symbol = latest_score_history_by_symbol()
    decision_insights = decision_insights_by_symbol(
        ranked,
        stored_evidence_by_symbol,
        target_counts,
    )
    decision_insight_rows_for_storage = decision_insight_storage_rows(
        db_run_id,
        report_date,
        ranked,
        decision_insights,
    )
    stored_decision_insights = record_decision_insights(decision_insight_rows_for_storage) if persist else 0
    verification_queue_rows_for_storage = verification_queue_storage_rows(
        db_run_id,
        report_date,
        ranked,
        decision_insights,
    )
    stored_verification_queue_items = (
        record_verification_queue_items(verification_queue_rows_for_storage) if persist else 0
    )
    persisted_decision_history = latest_decision_insights_by_symbol(limit_per_symbol=2) if persist else {}
    persisted_verification_queue_rows = [dict(row) for row in latest_verification_queue(limit=25)] if persist else []
    visible_verification_queue_rows = verification_queue_table_rows(persisted_verification_queue_rows, limit=12)
    decision_insight_history_rows = decision_insight_change_rows(
        {symbol: [dict(row) for row in rows] for symbol, rows in persisted_decision_history.items()},
        limit=12,
    )
    score_trend_table = html_table(
        ["Symbol", "Company/Fund", "Latest", "Change", "Action", "Trend", "Data Status"],
        score_history_rows(ranked, score_history_by_symbol),
        "score-trend-table",
        raw_columns={5},
    )
    next_buy, decision_gate = decision_summary_candidate(ranked, decision_insights, targets)

    holdings_rows = []
    allocation_segments = []
    for symbol, position in sorted(positions.items()):
        market_value = float(position.get("market_value", 0) or 0)
        allocation_pct = (market_value / account_value) * 100 if account_value else 0
        holdings_rows.append(
            [
                symbol,
                position.get("source", "-"),
                f"{float(position.get('quantity', 0)):,.4g}",
                fmt_money(float(position.get("last_price", 0) or 0)),
                fmt_money(market_value),
                fmt_pct(allocation_pct),
            ]
        )
        if allocation_pct > 0:
            allocation_segments.append((symbol, allocation_pct, market_value))

    score_rows = []
    for rank, row in enumerate(ranked, start=1):
        item = row["input"]
        target = row.get("target")
        score_rows.append(
            [
                rank,
                item.symbol,
                item.sleeve,
                trade_type_label(item.trade_type),
                row["action"],
                f"{row['score']:.1f}",
                fmt_money(item.current_price) if item.current_price else "Needs refresh",
                target_price_text(item, target),
                target_upside_text(item, target),
                data_status_for_target(item, target),
                target_source_label(item, target),
                score_summary_with_insight(row["breakdown"], row["insight"]),
                action_rationale(
                    item,
                    row["action"],
                    row["breakdown"],
                    row["position_after_buy_pct"],
                    target,
                    targets,
                ),
                target_confidence_text(item, target),
            ]
        )

    next_item = next_buy["input"]
    next_target = next_buy.get("target")
    next_action = str(next_buy["action"])
    allocation_safety = allocation_safety_for_candidate(
        next_buy,
        decision_gate,
        positions=positions,
        targets=targets,
        account_value=account_value,
        buy_capacity=default_buy_amount,
        sleeve_market_values=sleeve_market_values_for_ranked(ranked, positions),
    )
    suggested_amount = allocation_safety.suggested_amount
    actionable_next = (
        next_action in BUY_ACTIONS
        and bool(decision_gate.get("safe_to_buy"))
        and suggested_amount > 0
    )
    next_recommendation_label = "Recommended next buy" if actionable_next else "Top-ranked candidate"
    if not actionable_next and next_action in BUY_ACTIONS:
        next_recommendation_label = (
            "Buy capacity held" if decision_gate.get("safe_to_buy") else "No decision-safe buy"
        )
    next_amount_label = "Suggested buy amount" if actionable_next else "Buy capacity held"
    next_display_action = next_action if actionable_next else f"{next_action} blocked" if next_action in BUY_ACTIONS else next_action
    html_score_rows = []
    for rank, row in enumerate(ranked, start=1):
        item = row["input"]
        target = row.get("target")
        action = row["action"]
        html_score_rows.append(
            [
                rank,
                item.symbol,
                item.company,
                item.sleeve,
                trade_type_label(item.trade_type),
                f'<span class="pill {action_class(action)}">{action}</span>',
                f"{row['score']:.1f}",
                fmt_money(item.current_price) if item.current_price else "Needs refresh",
                target_price_text(item, target),
                target_upside_text(item, target),
                data_status_for_target(item, target),
                target_source_label(item, target),
                score_summary_with_insight(row["breakdown"], row["insight"]),
                action_rationale(
                    item,
                    row["action"],
                    row["breakdown"],
                    row["position_after_buy_pct"],
                    target,
                    targets,
                ),
                target_confidence_text(item, target),
            ]
        )
    html_score_table = html_table(
        [
            "Rank",
            "Symbol",
            "Company/Fund",
            "Sleeve",
            "Trade Type",
            "Action",
            "Score",
            "Current",
            "Target",
            "1Y Upside",
            "Data Status",
            "Sources",
            "Score Breakdown",
            "Why",
            "Confidence",
        ],
        html_score_rows,
        "rank-table",
        raw_columns={5, 12, 13},
    )

    def decision_row(rank: int, row: Dict[str, object]) -> List[object]:
        item = row["input"]
        target = row.get("target")
        action = str(row["action"])
        target_confidence = target_confidence_text(item, target)
        target_status = data_status_for_target(item, target)
        change_marker = change_marker_for_row(row, score_history_by_symbol)
        rationale = action_rationale(
            item,
            action,
            row["breakdown"],
            float(row["position_after_buy_pct"]),
            target,
            targets,
        )
        return [
            rank,
            item.symbol,
            action_hover_html(action, rationale, item, row["breakdown"], target),
            f"{float(row['score']):.1f}",
            change_marker_html(change_marker),
            fmt_money(item.current_price) if item.current_price else "Needs refresh",
            target_price_text(item, target),
            target_upside_text(item, target) if target or item.upside_pct else "Refresh",
            target_confidence,
            target_status,
            trade_type_label(item.trade_type),
            rationale,
        ]

    def expandable_action_queue_table(
        headers: List[str],
        ranked_rows: List[Dict[str, object]],
    ) -> str:
        head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
        body = []
        for rank, row in enumerate(ranked_rows, start=1):
            item = row["input"]
            target = row.get("target")
            action = str(row["action"])
            decision_insight = decision_insights[item.symbol]
            target_confidence = target_confidence_text(item, target)
            target_status = data_status_for_target(item, target)
            change_marker = change_marker_for_row(row, score_history_by_symbol)
            detail_id = f"action-detail-{html.escape(item.symbol.lower())}"
            rationale = action_rationale(
                item,
                action,
                row["breakdown"],
                float(row["position_after_buy_pct"]),
                target,
                targets,
            )
            body.append(
                f"""
                <tr class="expandable-action-row" tabindex="0" role="button" aria-expanded="false" aria-controls="{detail_id}">
                  <td>{rank}</td>
                  <td>{html.escape(item.symbol)}</td>
                  <td>{action_hover_html(action, rationale, item, row["breakdown"], target)}</td>
                  <td>{float(row['score']):.1f}</td>
                  <td>{change_marker_html(change_marker)}</td>
                  <td>{html.escape(fmt_money(item.current_price) if item.current_price else "Needs refresh")}</td>
                  <td>{html.escape(target_price_text(item, target))}</td>
                  <td>{target_upside_text(item, target) if target or item.upside_pct else "Refresh"}</td>
                  <td>{html.escape(target_confidence)}</td>
                  <td>{html.escape(target_status)}</td>
                  <td>{html.escape(trade_type_label(item.trade_type))}</td>
                  <td>{html.escape(rationale)}</td>
                </tr>
                <tr id="{detail_id}" class="action-detail-row" hidden>
                  <td colspan="{len(headers)}">
                    <div class="action-detail-card">
                      <div class="section-title">
                        <h3>Action Detail</h3>
                        <span class="section-note">{html.escape(item.symbol)} · {html.escape(action)}</span>
                      </div>
                      <p><strong>Action rationale:</strong> {html.escape(rationale)}</p>
                      <p><strong>Blended target:</strong> {html.escape(target_price_text(item, target))}; upside {html.escape(target_upside_text(item, target))}; confidence {html.escape(target_confidence_text(item, target))}</p>
                      <p><strong>Score movement:</strong> {html.escape(row["insight"].score_movement)}</p>
                      <p><strong>Score breakdown:</strong> {html.escape(score_summary_with_insight(row["breakdown"], row["insight"]))}</p>
                      {decision_insight_html(decision_insight)}
                      {score_explanation_html(item, row["breakdown"], target, row["insight"])}
                      {score_signal_shadow_html(item.symbol, stored_score_signals_by_symbol)}
                      <p><strong>Research note:</strong> {html.escape(item.notes)}</p>
                      {research_brief_html(item.symbol, item, stored_evidence_by_symbol)}
                      {source_drilldown_html(item.symbol, item, target_drilldowns, stored_evidence_by_symbol)}
                    </div>
                  </td>
                </tr>
                """
            )
        return (
            '<table class="decision-table expandable-action-table">'
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
        )

    action_queue_items = [
        row
        for row in ranked
        if row["action"] in {"Add", "Watch", "Hold"} and row["input"].sleeve != "speculative_ai"
    ][:10]
    action_queue_rows = [
        decision_row(rank, row)
        for rank, row in enumerate(action_queue_items, start=1)
    ]
    long_term_rows = [
        decision_row(rank, row)
        for rank, row in enumerate(ranked, start=1)
        if row["input"].sleeve in {"long_term", "etf"}
    ][:10]
    short_term_decision_rows = [
        decision_row(rank, row)
        for rank, row in enumerate(ranked, start=1)
        if row["input"].sleeve == "short_term"
    ][:10]
    speculative_rows = [
        decision_row(rank, row)
        for rank, row in enumerate(ranked, start=1)
        if row["input"].sleeve == "speculative_ai"
    ]
    data_gap_rows = ranked_data_gap_queue_rows(ranked, limit=25)
    visible_data_gap_rows = data_gap_rows[:12]
    top_decision_brief_rows = decision_brief_rows(ranked, decision_insights, limit=8)
    verify_next_rows = what_to_verify_rows(ranked, decision_insights, limit=10)
    insight_theme_table_rows = insight_theme_rows(ranked, decision_insights)
    decision_brief_cards = decision_brief_cards_html(action_queue_items or ranked, decision_insights, limit=5)
    data_gap_note = (
        f"{len(data_gap_rows) - len(visible_data_gap_rows)} more ranked data gaps are in the full universe."
        if len(data_gap_rows) > len(visible_data_gap_rows)
        else "Ranked by expected score and confidence impact"
    )

    decision_headers = [
        "Rank",
        "Symbol",
        "Action",
        "Score",
        "Change",
        "Today",
        "Target",
        "Upside",
        "Confidence",
        "Status",
        "Type",
        "Rationale",
    ]
    action_queue_table = expandable_action_queue_table(decision_headers, action_queue_items)
    long_term_table = html_table(
        decision_headers,
        long_term_rows,
        "decision-table",
        raw_columns={2, 4},
    )
    short_term_decision_table = html_table(
        decision_headers,
        short_term_decision_rows,
        "decision-table",
        raw_columns={2, 4},
    )
    speculative_table = html_table(
        decision_headers,
        speculative_rows,
        "decision-table",
        raw_columns={2, 4},
    )
    data_gap_table = html_table(
        ["Rank", "Symbol", "Data Gap", "Impact", "Best Pull", "Next Action"],
        visible_data_gap_rows,
        "compact-table",
    )
    verification_queue_table = html_table(
        ["Rank", "Symbol", "Type", "Status", "Impact", "Reason", "Command/Next Check", "Result"],
        visible_verification_queue_rows,
        "compact-table",
    )
    decision_insight_history_table = html_table(
        ["Symbol", "Previous", "Latest", "Score Move", "Headline", "Next Check"],
        decision_insight_history_rows,
        "compact-table",
    )
    score_movement_table = html_table(
        ["Symbol", "Base", "Evidence", "Trend", "Targets", "Gaps", "Final", "Action", "Top Driver"],
        score_movement_rows(ranked),
        "compact-table",
    )
    trend_insight_table = html_table(
        ["Symbol", "Overlay", "Trend Insight", "Score Movement"],
        trend_insight_rows(ranked),
        "compact-table",
    )
    insight_theme_table = html_table(
        ["Theme", "Symbols", "Why It Matters", "Next Check"],
        insight_theme_table_rows,
        "compact-table",
    )
    target_drilldown_headers = [
        "Rank",
        "Symbol",
        "Target Quality",
        "Target",
        "Range",
        "Confidence",
        "Sources",
        "Missing Inputs",
        "Labels",
        "Source Names",
    ]
    source_drilldown_rows = target_drilldown_table_rows(ranked, target_drilldowns)
    source_drilldown_table = html_table(
        target_drilldown_headers,
        source_drilldown_rows,
        "compact-table",
    )

    source_rows = []
    source_options = []
    for source in research_sources:
        source_name = source.get("source_name", "")
        operations = operations_for_source(source_name, source_operations)
        quality_metrics = source_quality_lookup.get(source_name, {})
        source_options.append(
            f'<option value="{html.escape(source_name)}">{html.escape(source_name)}</option>'
        )
        source_rows.append(
            {
                "source_name": source_name,
                "operations": operations,
                "access_model": source_integrations.get(source_name, {}).get("access_model", ""),
                "source_type": source.get("source_type", ""),
                "coverage": source.get("coverage", ""),
                "quality": f"{source_quality(source):.1f}",
                "effective_weight": f"{effective_source_weight(source):.2f}",
                "corroborate": source.get("corroboration_required", ""),
                "risk_note": source.get("bias_risk_note", ""),
                "feedback": source.get("user_feedback", ""),
                "integration": source_integrations.get(source_name, {}),
                "source_quality": quality_metrics,
            }
        )
    data_ingestion_rows = []
    for row in source_rows:
        operations = row["operations"]
        access_model = str(row.get("access_model") or "")
        free_paid = (
            "Paid candidate"
            if "paid" in access_model and "free" not in access_model
            else "Free + paid"
            if "free_plus_paid" in access_model
            else "Free/current"
            if access_model
            else "Configured"
        )
        data_ingestion_rows.append(
            [
                row["source_name"],
                str(row.get("integration", {}).get("source_tier") or "core"),
                str(row.get("integration", {}).get("source_category") or row.get("source_type") or ""),
                free_paid,
                operations.get("status") or "",
                int(operations.get("raw_records") or 0),
                int(operations.get("records") or 0),
                operations.get("last_run") or "Not run",
                operations.get("latest_issue") or "No current issue",
                operations.get("next_action") or "",
            ]
        )
    source_quality_table = {
        "headers": [
            "Source",
            "Category",
            "Quality",
            "Seen",
            "Inserted",
            "Duplicates",
            "Tag Rate",
            "Avg Confidence",
            "Matched Symbols",
            "Match Reasons",
            "Confidence Buckets",
            "Low Confidence",
            "Latest Success",
            "Latest Issue",
            "Notes",
        ],
        "rows": source_quality_table_rows(source_quality_rows),
        "raw_columns": [],
    }
    low_relevance_table = {
        "headers": ["Source", "Category", "Evidence", "Tagged", "Tag Rate", "Match Reasons", "Confidence Buckets", "Low Confidence", "Why Review"],
        "rows": low_relevance_source_rows(source_quality_rows),
        "raw_columns": [],
    }
    low_confidence_matches_table = {
        "headers": ["Source", "Symbol", "Reason", "Matched Text", "Bucket", "Confidence", "Title", "Timestamp"],
        "rows": low_confidence_match_rows(),
        "raw_columns": [],
    }
    source_depth_table = {
        "headers": ["Symbol", "Depth Type", "Signal", "Detail", "Confidence", "Corroboration", "As Of", "Source URL"],
        "rows": source_depth_rows(),
        "raw_columns": [],
    }
    ingestion_run_plan_table = {
        "headers": [
            "Rank",
            "Source",
            "Category",
            "Status",
            "Cadence Days",
            "Records",
            "Raw Payloads",
            "Latest Success",
            "Next Run",
            "Cooldown Until",
            "Issue",
            "Reason",
            "Command",
        ],
        "rows": ingestion_run_plan_rows(),
        "raw_columns": [],
    }
    ingestion_backfill_table = {
        "headers": [
            "Rank",
            "Source",
            "Symbol",
            "Backfill Type",
            "Status",
            "Window Days",
            "Covered Since",
            "Covered Until",
            "Records",
            "Next Action",
            "Command",
            "Reason",
        ],
        "rows": ingestion_backfill_rows(),
        "raw_columns": [],
    }
    evidence_events_table = {
        "headers": [
            "Event Date",
            "Symbol",
            "Event Type",
            "Headline",
            "Corroboration",
            "Sources",
            "Evidence",
            "Source Mix",
            "Confidence",
            "Latest Evidence",
            "Summary",
        ],
        "rows": evidence_event_rows(),
        "raw_columns": [],
    }
    evidence_review_queue_table = {
        "headers": [
            "Rank",
            "Symbol",
            "Event Type",
            "Review Status",
            "Corroboration",
            "Confidence",
            "Sources",
            "Evidence",
            "Latest Evidence",
            "Reason",
            "Recommended Action",
        ],
        "rows": evidence_review_queue_rows(),
        "raw_columns": [],
    }
    synthesis_readiness_table = {
        "headers": [
            "Symbol",
            "Readiness",
            "Score",
            "Ready Events",
            "Needs Review",
            "Needs Corroboration",
            "Ignored",
            "Primary Events",
            "Independent Confirmed",
            "Latest Event",
            "Packet",
            "Notes",
        ],
        "rows": synthesis_readiness_rows(),
        "raw_columns": [],
    }
    paid_provider_rows = [
        [
            "Financial Modeling Prep",
            "Free Basic 250 calls/day; Starter $22/mo annual; Premium $59/mo annual; Ultimate $149/mo annual",
            "More targets, fundamentals, news, and Ultimate earnings-call transcripts",
            "Wait until gap history proves need",
        ],
        [
            "Alpha Vantage",
            "Free 25 requests/day; premium starts $49.99/mo",
            "Higher request limits for news/sentiment, prices, and fundamentals",
            "Use oldest-refresh rotation first",
        ],
        [
            "Finnhub",
            "Paid tiers around $49.99/mo, $129.99/mo, $199.99/mo",
            "More calls/minute and potentially broader estimates/news endpoints",
            "Keep free key until blocked endpoints matter",
        ],
        [
            "Benzinga",
            "Public page lists datasets; pricing not clearly published",
            "Stock news, analyst ratings, conference calls, corporate guidance, unusual options",
            "Request pricing/trial later",
        ],
        [
            "Unusual Whales",
            "Public API with pricing/custom tiers",
            "Options flow, dark pool, volatility, technical indicators",
            "Evaluate only when short-term sleeve needs options-flow data",
        ],
    ]
    health_alert_rows = source_health_alert_rows(source_rows)
    health_summary = source_health_summary(source_rows)
    provider_blocker_rows = provider_blocker_review_rows(provider_gap_rows, ranked)
    provider_gap_review = build_provider_gap_review(provider_gap_rows, top_symbol=next_buy["input"].symbol)
    next_day_source_rows = action_queue_items[:8]
    next_day_status = next_day_readiness(next_day_source_rows, health_summary, health_alert_rows)
    readiness_items = pre_market_readiness_items(
        action_queue_items[0] if action_queue_items else next_buy,
        holdings_rows,
        health_summary,
        health_alert_rows,
        feedback_record_count(source_operations),
        next_day_status.get("item"),
    )
    pre_market_readiness = pre_market_readiness_html(readiness_items, next_day_status.get("preview"))
    top_health_alert = health_alert_rows[0] if health_alert_rows else None
    health_alert_table = html_table(
        ["Severity", "Source", "Status", "Records", "Last Run", "Latest Issue", "Next Action"],
        health_alert_rows,
        "source-health-table",
    )
    source_issue_group_table = html_table(
        ["Root Cause", "Severity", "Affected Sources", "Reason", "Next Action"],
        source_issue_group_rows(health_alert_rows),
        "source-issue-group-table",
    )
    signal_health_rows = score_signal_health_rows()
    next_day_watchlist_rows = []
    next_day_watchlist_html_rows = []
    for rank, row in enumerate(next_day_source_rows, start=1):
        item = row["input"]
        target = row.get("target")
        change_marker = change_marker_for_row(row, score_history_by_symbol)
        next_day_watchlist_rows.append(
            [
                rank,
                item.symbol,
                row["action"],
                f"{float(row['score']):.1f}",
                fmt_money(item.current_price) if item.current_price else "Needs refresh",
                target_price_text(item, target),
                target_upside_text(item, target),
                data_status_for_target(item, target),
                action_rationale(item, row["action"], row["breakdown"], row["position_after_buy_pct"], target, targets),
            ]
        )
        next_day_watchlist_html_rows.append(
            [
                rank,
                item.symbol,
                row["action"],
                f"{float(row['score']):.1f}",
                change_marker_html(change_marker),
                fmt_money(item.current_price) if item.current_price else "Needs refresh",
                target_price_text(item, target),
                target_upside_text(item, target),
                data_status_for_target(item, target),
                action_rationale(item, row["action"], row["breakdown"], row["position_after_buy_pct"], target, targets),
            ]
        )
    score_change_rows = []
    for row in ranked:
        item = row["input"]
        history = score_history_by_symbol.get(item.symbol, [])
        if len(history) < 2:
            continue
        previous = to_float(history[-2].get("score"))
        latest = to_float(history[-1].get("score"))
        change = latest - previous
        if abs(change) < 1:
            continue
        score_change_rows.append(
            [
                item.symbol,
                f"{previous:.1f}",
                f"{latest:.1f}",
                f"{change:+.1f}",
                str(history[-2].get("action") or ""),
                str(history[-1].get("action") or ""),
                str(history[-1].get("data_status") or ""),
            ]
        )
    score_change_rows.sort(key=lambda row: abs(to_float(str(row[3]).replace("+", ""))), reverse=True)
    allocation_bars = []
    for index, (symbol, pct, value) in enumerate(allocation_segments):
        allocation_bars.append(
            f"""
            <div class="allocation-row">
              <div class="allocation-label"><strong>{html.escape(symbol)}</strong><span>{fmt_money(value)} · {fmt_pct(pct)}</span></div>
              <div class="allocation-track"><div class="allocation-fill" style="width:{min(pct, 100):.2f}%; background:{css_var_for_index(index)}"></div></div>
            </div>
            """
        )

    def table_context(headers: List[str], rows: List[List[object]], raw_columns: List[int] | None = None) -> Dict[str, object]:
        return {
            "headers": headers,
            "rows": rows,
            "raw_columns": raw_columns or [],
        }

    def safe_json(value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): safe_json(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [safe_json(item) for item in value]
        return str(value)

    def context_dict(value: object) -> Dict[str, object]:
        return value if isinstance(value, dict) else {}

    def context_list(value: object) -> List[object]:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            return [value] if value else []
        return []

    def capital_candidate_context(row: Dict[str, object] | None, review: Dict[str, object] | None, role: str) -> Dict[str, object] | None:
        source = row or review
        if not source:
            return None
        review = review or {}
        blocked_reasons = context_list(source.get("blocked_reasons")) or context_list(review.get("blocked_reasons"))
        rationale_values = [
            source.get("why_this_is_in_queue"),
            source.get("rationale"),
            source.get("why"),
            review.get("rationale"),
        ]
        rationale = [str(value) for value in rationale_values if str(value or "").strip()]
        provider_blockers = context_list(source.get("provider_data_blockers"))
        if provider_blockers:
            blocked_reasons = list(dict.fromkeys([*blocked_reasons, *provider_blockers]))
        suggested = source.get("suggested_amount")
        if suggested is None:
            suggested = review.get("suggested_amount")
        return {
            "candidate_role": role,
            "rank": source.get("rank") or review.get("rank"),
            "symbol": source.get("symbol") or review.get("symbol"),
            "company": source.get("company") or review.get("company"),
            "action": source.get("action") or review.get("action"),
            "score": source.get("score") or review.get("score"),
            "sleeve": source.get("sleeve") or review.get("sleeve"),
            "trade_type": source.get("trade_type") or review.get("trade_type"),
            "decision_safe": bool(source.get("safe_to_buy") if "safe_to_buy" in source else review.get("decision_safe")),
            "decision_gate_status": source.get("decision_gate_status") or review.get("decision_gate_status"),
            "target_confidence": source.get("target_confidence") or source.get("confidence") or review.get("target_confidence"),
            "data_status": source.get("data_status") or review.get("data_status"),
            "suggested_amount": suggested,
            "suggested_amount_text": fmt_money(to_float(suggested)) if suggested is not None else "",
            "key_rationale": rationale[:3],
            "key_blockers": [str(reason) for reason in blocked_reasons if str(reason)],
            "ai_synthesis_readiness": source.get("ai_synthesis_readiness") or {},
        }

    def holding_health_summary_context(review: Dict[str, object]) -> Dict[str, object]:
        metadata = context_dict(review.get("metadata"))
        summary = context_dict(review.get("summary"))
        rows = [row for row in context_list(review.get("holdings")) if isinstance(row, dict)]
        review_rows = [row for row in rows if str(row.get("health_label") or "") not in {"", "healthy"}]
        if not rows:
            message = "No long-term holding health rows are available yet."
        elif review_rows:
            message = f"{len(review_rows)} long-term holding(s) need review; current add decisions are unchanged."
        else:
            message = "Long-term holding health is constructive; continue routine review."
        return {
            "available": bool(rows),
            "holding_count": metadata.get("holding_count", len(rows)),
            "summary": summary,
            "message": message,
            "top_review_rows": review_rows[:3],
            "review_only": True,
        }

    def long_term_capital_deployment_context(
        *,
        add_queue: Dict[str, object],
        fallback_review: Dict[str, object],
        capital_context: Dict[str, object],
        holding_health_review: Dict[str, object],
    ) -> Dict[str, object]:
        queue_rows = [row for row in context_list(add_queue.get("rows")) if isinstance(row, dict)]
        queue_by_symbol = {str(row.get("symbol") or "").upper(): row for row in queue_rows}
        primary_review = context_dict(fallback_review.get("primary_add"))
        fallback_candidate_review = context_dict(fallback_review.get("fallback_add"))
        blocked_top_review = context_dict(fallback_review.get("blocked_top_candidate"))
        top_queue_row = queue_rows[0] if queue_rows else {}
        top_symbol = str(top_queue_row.get("symbol") or blocked_top_review.get("symbol") or primary_review.get("symbol") or "").upper()
        fallback_symbol = str(fallback_candidate_review.get("symbol") or "").upper()
        primary_role = "top_candidate"
        if blocked_top_review:
            primary_role = "blocked_candidate"
        primary_candidate = capital_candidate_context(
            queue_by_symbol.get(top_symbol) or top_queue_row or None,
            blocked_top_review or primary_review or None,
            primary_role,
        )
        fallback_candidate = capital_candidate_context(
            queue_by_symbol.get(fallback_symbol),
            fallback_candidate_review or None,
            "fallback_candidate",
        )
        capital_status = str(capital_context.get("status") or "")
        deployable_amount = capital_context.get("deployable_amount")
        held_amount = capital_context.get("held_amount")
        blockers = []
        if primary_candidate:
            blockers.extend(primary_candidate.get("key_blockers", []))
        if capital_status in {"needs_manual_update", "held_no_safe_add", "held_by_allocation"}:
            blockers.append(str(capital_context.get("reason") or "Capital deployment is held for review."))
        blockers = list(dict.fromkeys(str(item) for item in blockers if str(item)))
        hold_capacity = context_dict(fallback_review.get("hold_capacity"))
        hold_message = ""
        if bool(hold_capacity.get("recommended")):
            hold_message = str(hold_capacity.get("reason") or "Hold buy capacity for review.")
        elif capital_status == "needs_manual_update":
            hold_message = "Buy capacity held until capital availability is configured or refreshed."
        elif capital_status.startswith("held"):
            hold_message = str(capital_context.get("reason") or "Buy capacity held for review.")
        status = "hold_capacity" if hold_message else "fallback_add" if fallback_candidate else capital_status or "review"
        return {
            "review_only": True,
            "recommendation_only": True,
            "decision_mode": "long_term_buy_add",
            "question": "What should I buy/add today for long-term holdings?",
            "status": status,
            "primary_candidate": primary_candidate,
            "decision_safety_status": (
                primary_candidate.get("decision_gate_status") if primary_candidate else "No long-term add candidate"
            ),
            "target_confidence": primary_candidate.get("target_confidence") if primary_candidate else "",
            "key_rationale": context_list(primary_candidate.get("key_rationale")) if primary_candidate else [],
            "key_blockers": blockers,
            "fallback_candidate": fallback_candidate,
            "hold_capacity_message": hold_message,
            "capital_availability": {
                "source": capital_context.get("capital_source") or "not_configured",
                "status": capital_context.get("capital_status") or capital_status,
                "as_of_date": capital_context.get("capital_as_of_date"),
                "freshness": capital_context.get("capital_freshness"),
                "available_capital": capital_context.get("available_capital"),
                "available_capital_text": fmt_money(to_float(capital_context.get("available_capital"))) if capital_context.get("available_capital") is not None else "Needs manual update",
                "monthly_buy_capacity": capital_context.get("monthly_buy_capacity"),
                "manual_available_cash": capital_context.get("manual_available_cash"),
                "deployable_amount": deployable_amount,
                "deployable_amount_text": fmt_money(to_float(deployable_amount)) if deployable_amount is not None else "Needs manual update",
                "held_amount": held_amount,
                "held_amount_text": fmt_money(to_float(held_amount)) if held_amount is not None else "Needs manual update",
                "reason": capital_context.get("reason"),
                "reduction_reasons": capital_context.get("reduction_reasons", []),
                "long_term_core_sleeve": capital_context.get("long_term_core_sleeve", {}),
            },
            "long_term_holding_health_summary": holding_health_summary_context(holding_health_review),
            "ai_synthesis_note": "AI synthesis is explanatory only and does not change the official recommendation.",
            "note": "Review-only and recommendation-only; official recommendations, scores, targets, gates, and allocation rules are unchanged.",
        }

    def earnings_related(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        fields = (
            "provider",
            "source",
            "source_name",
            "field",
            "field_name",
            "endpoint",
            "provider_endpoint",
            "evidence_type",
            "event_type",
            "message",
            "latest_issue",
            "title",
            "summary",
        )
        return "earnings" in " ".join(str(value.get(field) or "").lower() for field in fields)

    def compact_earnings_provider_gap(row: Dict[str, object]) -> Dict[str, object]:
        return {
            "symbol": str(row.get("symbol") or "").upper(),
            "provider": row.get("provider") or row.get("source") or "",
            "field": row.get("field_name") or row.get("field") or row.get("endpoint") or row.get("provider_endpoint") or "",
            "status": row.get("status") or "",
            "latest_issue": row.get("latest_issue") or row.get("message") or row.get("notes") or "",
            "review_only": True,
        }

    def earnings_provider_gaps_for_symbol(rows: List[Dict[str, object]], symbol: str) -> List[Dict[str, object]]:
        wanted = symbol.upper()
        return [
            compact_earnings_provider_gap(row)
            for row in rows
            if earnings_related(row) and str(row.get("symbol") or "").upper() in {"", wanted, "MARKET"}
        ]

    def price_history_summary_for_symbol(symbol: str) -> Dict[str, object]:
        rows = price_history.get(symbol.upper(), [])
        if not rows:
            return {
                "status": "missing",
                "history_days": 0,
                "max_daily_move_pct": None,
            }
        ordered = list(reversed(rows))
        moves = []
        previous_close = None
        for row in ordered:
            close = to_float(row.get("adjusted_close") or row.get("close"))
            if close <= 0:
                continue
            if previous_close and previous_close > 0:
                moves.append(abs(((close - previous_close) / previous_close) * 100))
            previous_close = close
        return {
            "status": "available",
            "history_days": len(rows),
            "max_daily_move_pct": round(max(moves), 4) if moves else 0.0,
            "recent_daily_move_pct": round(moves[-1], 4) if moves else 0.0,
        }

    def scrub_earnings_review_row(row: Dict[str, object]) -> Dict[str, object]:
        cleaned = dict(row)
        cleaned["recommendation_only_note"] = "Recommendation-only earnings review; official recommendation outputs are unchanged."
        return cleaned

    def signal_direction_to_review_label(direction: str) -> str:
        normalized = direction.lower()
        if normalized in {"positive", "improved"}:
            return "improved"
        if normalized in {"negative", "weakened"}:
            return "weakened"
        if normalized == "mixed":
            return "mixed"
        if normalized in {"neutral"}:
            return "neutral"
        return "missing"

    def update_signal_category(categories: Dict[str, str], category: str, direction: str) -> None:
        current = categories.get(category, "missing")
        candidate = signal_direction_to_review_label(direction)
        priority = {"weakened": 4, "mixed": 3, "improved": 2, "neutral": 1, "missing": 0}
        if priority.get(candidate, 0) > priority.get(current, 0):
            categories[category] = candidate

    def earnings_signal_category_summary(signals: List[Dict[str, object]], post_rows: List[Dict[str, object]]) -> Dict[str, object]:
        categories = {
            "guidance": "missing",
            "estimates": "missing",
            "margins": "missing",
            "revenue": "missing",
            "eps": "missing",
            "ai_capex_commentary": "missing",
            "risk_language": "missing",
            "market_reaction": "missing",
            "thesis_impact": "missing",
        }
        mapping = {
            "guidance_raise": "guidance",
            "guidance_cut": "guidance",
            "revenue_beat": "revenue",
            "revenue_miss": "revenue",
            "eps_beat": "eps",
            "eps_miss": "eps",
            "margin_expansion": "margins",
            "margin_pressure": "margins",
            "ai_demand_strength": "ai_capex_commentary",
            "capex_risk": "ai_capex_commentary",
            "customer_growth": "estimates",
            "churn_or_demand_risk": "risk_language",
            "cybersecurity_or_operational_risk": "risk_language",
            "valuation_risk": "risk_language",
        }
        for signal in signals:
            signal_type = str(signal.get("signal_type") or "")
            category = mapping.get(signal_type)
            if category:
                update_signal_category(categories, category, str(signal.get("signal_direction") or "unknown"))
        for row in post_rows:
            thesis = str(row.get("thesis_impact") or "")
            if thesis:
                categories["thesis_impact"] = signal_direction_to_review_label(thesis)
            if row.get("price_reaction_pct") is not None:
                reaction = to_float(row.get("price_reaction_pct"))
                categories["market_reaction"] = "improved" if reaction >= 3 else "weakened" if reaction <= -3 else "neutral"
        return {
            "categories": categories,
            "review_only": True,
            "recommendation_impact": "none",
        }

    def build_earnings_review_context(
        *,
        universe_rows: List[Dict[str, object]],
        recommendations_by_symbol: Dict[str, Dict[str, object]],
        decision_gates_by_symbol: Dict[str, Dict[str, object]],
        provider_gap_rows: List[Dict[str, object]],
        stored_evidence_rows: List[Dict[str, object]],
        source_usefulness_rows: List[Dict[str, object]],
        score_history_rows: List[Dict[str, object]],
        ai_context_by_symbol: Dict[str, Dict[str, object]],
        as_of_date: str,
    ) -> Dict[str, object]:
        event_queue = build_earnings_event_queue(
            universe_rows,
            stored_evidence_rows=stored_evidence_rows,
            provider_gap_rows=provider_gap_rows,
            report_date=as_of_date,
        )
        queue_rows = [dict(row) for row in context_list(event_queue.get("rows")) if isinstance(row, dict)]
        upcoming_rows = [row for row in queue_rows if row.get("event_type") == "upcoming_earnings"]
        recent_rows = [row for row in queue_rows if row.get("event_type") == "recent_earnings"]
        data_gap_rows = [
            row
            for row in queue_rows
            if row.get("event_type") in {"unknown_earnings_date", "earnings_data_gap"}
            or row.get("provider_gap_status") not in {"", "ok", "expected"}
            or row.get("source_status") not in {"", "ok", "unknown", "expected", "non_operating_company"}
        ]
        pre_candidates = [
            row
            for row in queue_rows
            if row.get("review_window") in {"pre_earnings", "unknown"}
            and row.get("recommended_review_action") != "ignore_for_now"
        ][:10]
        pre_rows = []
        for row in pre_candidates:
            symbol = str(row.get("symbol") or "").upper()
            pre_rows.append(
                scrub_earnings_review_row(
                    review_pre_earnings_setup(
                        earnings_event=row,
                        recommendation=recommendations_by_symbol.get(symbol, {}),
                        decision_safety=decision_gates_by_symbol.get(symbol, {}),
                        target_confidence=str(recommendations_by_symbol.get(symbol, {}).get("confidence") or recommendations_by_symbol.get(symbol, {}).get("target_confidence") or ""),
                        price_history_summary=price_history_summary_for_symbol(symbol),
                        provider_gaps=earnings_provider_gaps_for_symbol(provider_gap_rows, symbol),
                        ai_synthesis_readiness=ai_context_by_symbol.get(symbol, {}),
                        as_of_date=as_of_date,
                    )
                )
            )
        post_candidates = [
            row
            for row in queue_rows
            if row.get("event_type") == "recent_earnings"
            and row.get("recommended_review_action") in {"review_post_earnings", "monitor_after_report"}
        ][:10]
        post_rows = [
            scrub_earnings_review_row(row)
            for row in build_post_earnings_reviews(
                post_candidates,
                evidence_rows=stored_evidence_rows,
                price_history_by_symbol=price_history,
                recommendation_rows=score_history_rows,
                ai_context_by_symbol=ai_context_by_symbol,
                provider_gaps=provider_gap_rows,
                source_usefulness=source_usefulness_rows,
                as_of=as_of_date,
            )
        ]
        signals = [
            dict(signal)
            for signal in extract_earnings_signals(stored_evidence_rows)
        ]
        signal_summary = summarize_earnings_signals(signals)
        signal_summary.update(earnings_signal_category_summary(signals, post_rows))
        provider_gap_review_rows = [
            compact_earnings_provider_gap(row)
            for row in provider_gap_rows
            if earnings_related(row)
        ]
        return {
            "review_only": True,
            "recommendation_only": True,
            "decision_mode": "earnings_event",
            "note": "Recommendation-only earnings review; official recommendation outputs are unchanged.",
            "upcoming_earnings_queue": {
                "rows": upcoming_rows[:12],
                "empty_state": "No upcoming earnings dates are available in the review window.",
            },
            "recent_earnings_queue": {
                "rows": recent_rows[:12],
                "empty_state": "No recent earnings events are available for post-earnings review.",
            },
            "pre_earnings_setup_review": {
                "review_only": True,
                "rows": pre_rows,
                "empty_state": "No pre-earnings setup review rows are available.",
            },
            "post_earnings_reaction_review": {
                "review_only": True,
                "rows": post_rows,
                "empty_state": "No post-earnings reaction review rows are available.",
            },
            "earnings_signal_summary": {
                **signal_summary,
                "signals": signals[:12],
                "empty_state": "No earnings evidence signals are available yet.",
            },
            "provider_data_gaps": {
                "rows": provider_gap_review_rows[:12],
                "event_rows": data_gap_rows[:12],
                "empty_state": "No earnings-specific provider/data gaps are visible.",
            },
        }

    def compact_tactical_provider_gap(row: Dict[str, object]) -> Dict[str, object]:
        return {
            "symbol": str(row.get("symbol") or "").upper(),
            "provider": row.get("provider") or row.get("source") or "",
            "field": row.get("field_name") or row.get("field") or row.get("endpoint") or row.get("provider_endpoint") or "",
            "status": row.get("status") or "",
            "latest_issue": row.get("latest_issue") or row.get("message") or row.get("notes") or "",
            "review_only": True,
        }

    def tactical_provider_gaps_for_symbol(rows: List[Dict[str, object]], symbol: str) -> List[Dict[str, object]]:
        wanted = symbol.upper()
        return [
            compact_tactical_provider_gap(row)
            for row in rows
            if str(row.get("symbol") or "").upper() in {"", wanted, "MARKET"}
        ]

    def latest_event_context_for_symbol(rows: List[Dict[str, object]], symbol: str) -> List[Dict[str, object]]:
        wanted = symbol.upper()
        selected = []
        for row in rows:
            if str(row.get("symbol") or "").upper() != wanted:
                continue
            event_text = " ".join(
                str(row.get(field) or "").lower()
                for field in ("event_type", "headline", "title", "summary", "notes")
            )
            if not any(token in event_text for token in ("earnings", "catalyst", "launch", "guidance", "revenue", "ai", "demand", "news")):
                continue
            selected.append(
                {
                    "symbol": wanted,
                    "event_date": row.get("event_date")
                    or row.get("latest_evidence_at")
                    or row.get("published_at")
                    or row.get("source_timestamp")
                    or row.get("created_at")
                    or row.get("date"),
                    "event_type": row.get("event_type") or row.get("evidence_type") or row.get("source_type") or "",
                    "headline": row.get("headline") or row.get("title") or row.get("summary") or "",
                    "corroboration_label": row.get("corroboration_label") or row.get("confidence_bucket") or row.get("confidence") or "",
                    "review_only": True,
                }
            )
        selected.sort(key=lambda item: str(item.get("event_date") or ""), reverse=True)
        return selected[:3]

    def first_symbol_row(section: Dict[str, object]) -> Dict[str, Dict[str, object]]:
        rows = [row for row in context_list(section.get("rows")) if isinstance(row, dict)]
        result: Dict[str, Dict[str, object]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "").upper()
            if symbol and symbol not in result:
                result[symbol] = row
        return result

    def tactical_label_counts(rows: List[Dict[str, object]], field: str) -> List[Dict[str, object]]:
        counts: Dict[str, int] = {}
        for row in rows:
            label = str(row.get(field) or "missing")
            counts[label] = counts.get(label, 0) + 1
        return [
            {"label": label, "count": count, "review_only": True}
            for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def build_tactical_review_context(
        *,
        recommendations: List[Dict[str, object]],
        recommendations_by_symbol: Dict[str, Dict[str, object]],
        earnings_review: Dict[str, object],
        provider_gap_rows: List[Dict[str, object]],
        stored_evidence_rows: List[Dict[str, object]],
        ai_context_by_symbol: Dict[str, Dict[str, object]],
        as_of_date: str,
    ) -> Dict[str, object]:
        upcoming = first_symbol_row(context_dict(earnings_review.get("upcoming_earnings_queue")))
        recent = first_symbol_row(context_dict(earnings_review.get("recent_earnings_queue")))
        pre = first_symbol_row(context_dict(earnings_review.get("pre_earnings_setup_review")))
        post = first_symbol_row(context_dict(earnings_review.get("post_earnings_reaction_review")))
        setup_rows: List[Dict[str, object]] = []
        risk_inputs: List[Dict[str, object]] = []
        provider_gap_review_rows: List[Dict[str, object]] = []
        earnings_event_context_rows: List[Dict[str, object]] = []
        for rec in recommendations:
            symbol = str(rec.get("symbol") or "").upper()
            if not symbol:
                continue
            current_price = to_float(rec.get("current_price"))
            event = upcoming.get(symbol) or recent.get(symbol) or {}
            symbol_provider_gaps = tactical_provider_gaps_for_symbol(provider_gap_rows, symbol)
            provider_gap_review_rows.extend(symbol_provider_gaps)
            symbol_events = latest_event_context_for_symbol(stored_evidence_rows, symbol)
            setup = classify_tactical_setup(
                symbol=symbol,
                current_price=current_price or None,
                price_history=price_history.get(symbol, []),
                technical_context=context_dict(context_dict(rec.get("target_drilldown")).get("technical")),
                earnings_event=event,
                pre_earnings_review=pre.get(symbol, {}),
                post_earnings_review=post.get(symbol, {}),
                catalyst_events=symbol_events,
                provider_gaps=symbol_provider_gaps,
                source_usefulness=(),
                ai_synthesis_readiness=ai_context_by_symbol.get(symbol, {}),
                recommendation=recommendations_by_symbol.get(symbol, {}),
                as_of_date=as_of_date,
            )
            setup = dict(setup)
            technical_summary = context_dict(setup.get("technical_summary"))
            setup_label = str(setup.get("setup_label") or "")
            risk_zone_label = "not_applicable" if setup_label in {"no_tactical_setup", "none"} else "moderate"
            if symbol_provider_gaps or setup_label == "data_insufficient":
                risk_zone_label = "data_gap"
            setup.update(
                {
                    "report_date": as_of_date,
                    "setup_date": as_of_date,
                    "current_price": current_price or technical_summary.get("current_price"),
                    "support_estimate": setup.get("support_level") or technical_summary.get("support_level"),
                    "resistance_estimate": setup.get("resistance_level") or technical_summary.get("resistance_level"),
                    "risk_zone_label": risk_zone_label,
                    "recent_volatility_pct": technical_summary.get("volatility_pct"),
                    "price_history_quality": technical_summary.get("status") or "missing",
                    "earnings_event_context": event,
                    "catalyst_context": {"row_count": len(symbol_events), "latest": symbol_events[0] if symbol_events else {}},
                    "provider_gaps": symbol_provider_gaps,
                    "long_term_context": {
                        "action": rec.get("action"),
                        "decision_gate_status": rec.get("decision_gate_status"),
                        "target_confidence": rec.get("target_confidence") or rec.get("confidence"),
                    },
                    "recommendation_only_note": "Recommendation-only tactical review; official long-term recommendations are unchanged.",
                }
            )
            setup_rows.append(setup)
            risk_inputs.append(
                {
                    "symbol": symbol,
                    "tactical_horizon": setup.get("tactical_horizon"),
                    "setup_label": setup.get("setup_label"),
                    "current_price": setup.get("current_price"),
                    "support_estimate": setup.get("support_estimate"),
                    "resistance_estimate": setup.get("resistance_estimate"),
                    "recent_volatility_pct": setup.get("recent_volatility_pct"),
                    "earnings_event": event,
                    "price_history_quality": setup.get("price_history_quality"),
                    "notes": context_list(setup.get("reasons"))[:2],
                }
            )
            if event:
                earnings_event_context_rows.append(
                    {
                        "symbol": symbol,
                        "event_type": event.get("event_type") or "",
                        "earnings_date": event.get("earnings_date") or event.get("event_date") or "",
                        "recommended_review_action": event.get("recommended_review_action") or "",
                        "review_only": True,
                    }
                )
        watchlist_queue = build_tactical_watchlist_queue(setup_rows, as_of_date=as_of_date, limit=12)
        watchlist_queue["note"] = "Recommendation-only tactical review; it does not override long-term capital deployment or official recommendations."
        for row in context_list(watchlist_queue.get("rows")):
            if isinstance(row, dict):
                row["note"] = "Review-only tactical context."
        risk_rows = tactical_risk_zones(risk_inputs)
        outcome_rows = tactical_outcome_rows(setup_rows, price_history)
        visible_outcomes = [
            row
            for row in outcome_rows
            if row.get("outcome_status") not in {"not_enough_history", ""}
        ]
        return {
            "review_only": True,
            "recommendation_only": True,
            "does_not_override_long_term": True,
            "decision_mode": "tactical_trade",
            "note": "Recommendation-only tactical review; it is separate from and does not override long-term capital deployment or official recommendations.",
            "tactical_watchlist_queue": {
                **watchlist_queue,
                "empty_state": "No tactical review setups are available yet.",
            },
            "setup_labels": {
                "rows": tactical_label_counts(setup_rows, "setup_label"),
                "empty_state": "No tactical setup labels are available yet.",
            },
            "tactical_horizons": {
                "rows": tactical_label_counts(setup_rows, "tactical_horizon"),
                "empty_state": "No tactical horizons are available yet.",
            },
            "review_actions": {
                "rows": tactical_label_counts([row for row in context_list(watchlist_queue.get("rows")) if isinstance(row, dict)], "review_action"),
                "empty_state": "No tactical review actions are available yet.",
            },
            "risk_zones": {
                "rows": risk_rows,
                "empty_state": "No tactical risk-zone rows are available yet.",
            },
            "invalidation_conditions": {
                "rows": [
                    {
                        "symbol": row.get("symbol"),
                        "setup_label": row.get("setup_label"),
                        "tactical_horizon": row.get("tactical_horizon"),
                        "invalidation_condition": row.get("invalidation_condition"),
                        "review_only": True,
                    }
                    for row in context_list(watchlist_queue.get("rows"))
                    if isinstance(row, dict)
                ],
                "empty_state": "No tactical invalidation conditions are available yet.",
            },
            "provider_data_gaps": {
                "rows": provider_gap_review_rows[:20],
                "empty_state": "No tactical provider/data gaps are visible.",
            },
            "earnings_event_context": {
                "rows": earnings_event_context_rows[:12],
                "empty_state": "No earnings/event context is attached to tactical review rows.",
            },
            "tactical_outcome_history": {
                "summary": summarize_tactical_outcomes(visible_outcomes),
                "rows": visible_outcomes[:20],
                "empty_state": "No tactical outcome history is available yet.",
            },
        }

    def compact_model_registry(registry: Dict[str, object]) -> Dict[str, object]:
        rows = [row for row in context_list(registry.get("models")) if isinstance(row, dict)]
        official_count = len([row for row in rows if str(row.get("official_or_shadow") or "") == "official"])
        shadow_count = len([row for row in rows if str(row.get("official_or_shadow") or "") == "shadow"])
        missing_version_count = len([row for row in rows if not str(row.get("model_version") or "")])
        return {
            "review_only": True,
            "registry_version": registry.get("registry_version", "model-registry-v1"),
            "model_count": registry.get("model_count", len(rows)),
            "official_count": official_count,
            "shadow_count": shadow_count,
            "missing_version_count": missing_version_count,
            "rows": rows,
            "validation": registry.get("validation", {}),
            "empty_state": "No model registry rows are available yet.",
        }

    def compact_prediction_summary(records: Dict[str, object]) -> Dict[str, object]:
        rows = [row for row in context_list(records.get("predictions")) if isinstance(row, dict)]
        model_versions = sorted({str(row.get("model_version") or "missing") for row in rows})
        warnings = []
        if not rows:
            warnings.append("No prediction records are available for model evaluation yet.")
        if any(not str(row.get("model_version") or "") for row in rows):
            warnings.append("Some prediction records are missing model version.")
        validation = context_dict(records.get("validation"))
        errors = context_list(validation.get("errors"))
        if errors:
            warnings.append(f"Prediction record validation has {len(errors)} issue(s).")
        return {
            "review_only": True,
            "prediction_record_version": records.get("prediction_record_version", "prediction-records-v1"),
            "prediction_count": records.get("prediction_count", len(rows)),
            "model_versions": model_versions,
            "warnings": warnings,
            "rows": rows[:12],
            "validation": validation,
            "empty_state": "No prediction records are available for model evaluation yet.",
        }

    def benchmark_summary(rows: List[Dict[str, object]]) -> Dict[str, object]:
        values = [
            to_float(row.get("excess_return_pct"))
            for row in rows
            if row.get("excess_return_pct") is not None
        ]
        warnings = [
            str(warning)
            for row in rows
            for warning in context_list(row.get("warnings"))
            if str(warning)
        ]
        return {
            "review_only": True,
            "row_count": len(rows),
            "available_count": len(values),
            "missing_count": len(rows) - len(values),
            "status": "available" if values else "missing",
            "average_excess_return_pct": round(sum(values) / len(values), 4) if values else None,
            "warnings": list(dict.fromkeys(warnings)),
            "empty_state": "No benchmark comparison rows are available yet.",
        }

    def ai_thesis_summary(evaluation: Dict[str, object]) -> Dict[str, object]:
        metadata = context_dict(evaluation.get("metadata"))
        rows = [row for row in context_list(evaluation.get("evaluations")) if isinstance(row, dict)]
        label_counts = context_dict(metadata.get("label_counts"))
        useful = sum(
            int(value or 0)
            for key, value in label_counts.items()
            if key in {"thesis_supported", "thesis_partially_supported"}
        )
        weak = sum(
            int(value or 0)
            for key, value in label_counts.items()
            if key in {"thesis_contradicted", "insufficient_evidence", "guardrail_failed"}
        )
        total = useful + weak
        return {
            "review_only": True,
            "no_model_change": True,
            "evaluation_count": metadata.get("evaluation_count", len(rows)),
            "label_counts": label_counts,
            "useful_theses": useful,
            "weak_theses": weak,
            "accuracy": round(useful / total, 4) if total else None,
            "rows": rows[:12],
            "empty_state": "No AI thesis evaluation rows are available yet.",
        }

    def build_model_evaluation_context(
        *,
        recommendations: List[Dict[str, object]],
        learning_review: Dict[str, object],
        as_of_date: str,
        generated_at: str,
        recommendation_run_id: int | None,
    ) -> Dict[str, object]:
        model_name = "official_recommendation_model"
        model_version = MODEL_VERSION
        registry = build_model_registry(
            [
                {
                    "model_name": model_name,
                    "model_version": model_version,
                    "model_role": "official",
                    "official_or_shadow": "official",
                    "description": "Current rules-based daily recommendation model.",
                    "created_at": generated_at,
                    "allowed_decision_modes": ["long_term_buy_add", "portfolio_review"],
                    "allowed_horizons": ["12_months", "multi_year"],
                    "score_impact": "none",
                    "recommendation_impact": "none",
                    "notes": "Review-only registry row for model evaluation context.",
                }
            ],
            created_at=generated_at,
        )
        prediction_rows = [
            prediction_from_recommendation(
                {
                    **rec,
                    "report_date": as_of_date,
                    "model_version": model_version,
                    "rationale": rec.get("rationale") or rec.get("why") or rec.get("notes"),
                },
                model_name=model_name,
                model_version=model_version,
                created_at=generated_at,
                report_date=as_of_date,
                recommendation_run_id=recommendation_run_id,
            )
            for rec in recommendations
        ]
        prediction_records = build_prediction_record_set(prediction_rows)
        recommendation_snapshots = [
            {
                **rec,
                "report_date": as_of_date,
                "model_version": model_version,
                "benchmark_symbol": "BENCHMARK",
            }
            for rec in recommendations
        ]
        benchmark_history = {
            "BENCHMARK": price_history.get("QQQM") or price_history.get("VGT") or price_history.get("SMH") or []
        }
        backtest = recommendation_backtest(
            recommendation_snapshots,
            price_history,
            benchmark_price_history=benchmark_history,
            windows=["20_trading_days", "60_trading_days", "12_months"],
            minimum_sample_size=5,
        )
        benchmark_rows = benchmark_comparison_rows(
            context_list(backtest.get("rows")),
            price_history,
        )
        benchmark_review = benchmark_summary([row for row in benchmark_rows if isinstance(row, dict)])
        ai_evaluation = evaluate_ai_theses([])
        ai_summary = ai_thesis_summary(ai_evaluation)
        source_summary = context_dict(context_dict(learning_review.get("source_usefulness")).get("summary"))
        safety_summary = context_dict(context_dict(learning_review.get("decision_safety_effectiveness")).get("summary"))
        warnings = []
        warnings.extend(str(item) for item in context_list(context_dict(backtest.get("summary")).get("warnings")) if str(item))
        warnings.extend(str(item) for item in context_list(benchmark_review.get("warnings")) if str(item))
        if benchmark_review.get("status") == "missing":
            warnings.append("Benchmark data is missing or insufficient for model evaluation.")
        if not context_list(ai_evaluation.get("evaluations")):
            warnings.append("No AI thesis evaluation rows are available yet.")
        trust_score = build_model_trust_score(
            {
                "model_name": model_name,
                "model_version": model_version,
                "sample_size": context_dict(backtest.get("summary")).get("enough_history_count", 0),
                "recommendation_backtest_summary": context_dict(backtest.get("summary")),
                "benchmark_comparison_summary": benchmark_review,
                "decision_safety_effectiveness_summary": safety_summary,
                "source_usefulness_summary": source_summary,
                "ai_thesis_evaluation_summary": ai_summary,
                "warning_flags": warnings,
                "minimum_sample_size": 30,
            }
        )
        return {
            "review_only": True,
            "recommendation_only": True,
            "no_model_promotion": True,
            "note": "Recommendation-only model evaluation; review-only learning context does not change official recommendations or promote models.",
            "prediction_records": compact_prediction_summary(prediction_records),
            "model_registry": compact_model_registry(registry),
            "recommendation_backtest": {
                "review_only": True,
                "summary": context_dict(backtest.get("summary")),
                "rows": context_list(backtest.get("rows"))[:20],
                "empty_state": "No recommendation backtest rows are available yet.",
            },
            "benchmark_comparison": {
                "review_only": True,
                "summary": benchmark_review,
                "rows": benchmark_rows[:20],
                "empty_state": "No benchmark comparison rows are available yet.",
            },
            "model_trust_score_v1": {
                **trust_score,
                "notes": "Review-only Model Trust Score v1; no model promotion or recommendation behavior changes are applied.",
            },
            "ai_thesis_evaluation": ai_summary,
            "warnings": list(dict.fromkeys(warnings)),
        }

    ALERT_REVIEW_NOTE = (
        "Review-only alert prompts for manual attention; official recommendations stay unchanged "
        "and no live notifications are sent."
    )

    def alert_display_severity(value: object) -> str:
        token = str(value or "").lower().replace("-", "_").replace(" ", "_")
        return token.removesuffix("_review") or "informational"

    def alert_review_area(alert_type: object) -> str:
        token = str(alert_type or "").lower()
        if "capital" in token or "decision_gate" in token or "watchlist" in token:
            return "capital_deployment"
        if "earning" in token:
            return "earnings_review"
        if "tactical" in token or "setup" in token:
            return "tactical_review"
        if any(part in token for part in ("provider", "gap", "source", "price", "target_confidence")):
            return "provider_data"
        if "ai" in token or "brief" in token:
            return "ai_briefs"
        if "model" in token or "outcome" in token:
            return "model_learning"
        return "local_console"

    def alert_priority(row: Dict[str, object], index: int) -> int:
        severity_rank = {
            "critical_review": 1,
            "high_review": 2,
            "medium_review": 3,
            "low_review": 4,
            "informational": 5,
        }
        return severity_rank.get(str(row.get("severity")), 5) * 100 + index

    def alert_display_row(row: Dict[str, object], *, index: int, company_by_symbol: Dict[str, str]) -> Dict[str, object]:
        symbol = str(row.get("symbol") or "").upper()
        alert_type = str(row.get("alert_type") or "")
        severity = str(row.get("severity") or "informational")
        status = str(row.get("status") or "new")
        return {
            "alert_id": row.get("alert_id") or f"alert-{index}",
            "alert_type": alert_type,
            "status": status,
            "severity": severity,
            "display_severity": alert_display_severity(severity),
            "priority": alert_priority(row, index),
            "created_at": row.get("created_at") or "",
            "symbol": symbol,
            "company": company_by_symbol.get(symbol, ""),
            "decision_mode": "manual_review",
            "review_area": alert_review_area(alert_type),
            "source": ", ".join(str(item) for item in context_list(row.get("source_refs")) if str(item)),
            "event_summary": row.get("summary") or row.get("title") or "",
            "why_review": row.get("title") or row.get("summary") or "",
            "review_action": row.get("recommended_review_action") or "review_manually",
            "prior_state": {},
            "current_state": {
                "severity": severity,
                "status": status,
            },
            "dedupe_key": row.get("dedupe_key") or row.get("alert_id") or "",
            "dedupe_group": f"{alert_type}:{symbol or 'portfolio'}",
            "duplicate_of": row.get("duplicate_of") or "",
            "related_artifacts": context_list(row.get("related_artifacts")),
            "review_only": True,
            "review_only_note": ALERT_REVIEW_NOTE,
        }

    def count_alerts_by(rows: List[Dict[str, object]], key: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in rows:
            value = str(row.get(key) or "unknown")
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    def build_alerts_review_context(
        *,
        long_term_capital_deployment: Dict[str, object],
        earnings_review: Dict[str, object],
        tactical_review: Dict[str, object],
        model_evaluation: Dict[str, object],
        learning_review: Dict[str, object],
        provider_gap_rows: List[Dict[str, object]],
        recommendations: List[Dict[str, object]],
        as_of_date: str,
        generated_at: str,
    ) -> Dict[str, object]:
        company_by_symbol = {
            str(row.get("symbol") or "").upper(): str(row.get("company") or "")
            for row in recommendations
            if isinstance(row, dict)
        }
        signal_rows: Dict[str, object] = {
            "provider_gaps": provider_gap_rows[:40],
            "earnings_events": [
                *context_list(context_dict(earnings_review.get("upcoming_earnings_queue")).get("rows")),
                *context_list(context_dict(earnings_review.get("recent_earnings_queue")).get("rows")),
            ],
            "recommendation_outcomes": context_list(
                context_dict(context_dict(learning_review.get("recommendation_outcomes")).get("top_outcomes")).get("rows")
            )
            or context_list(context_dict(learning_review.get("recommendation_outcomes")).get("top_outcomes")),
            "tactical_setups": context_list(context_dict(tactical_review.get("tactical_watchlist_queue")).get("rows")),
            "model_trust": [
                {
                    "model_name": "official_recommendation_model",
                    "previous_trust_level": "unknown",
                    "current_trust_level": context_dict(model_evaluation.get("model_trust_score_v1")).get("trust_level"),
                    "previous_trust_score": 0,
                    "current_trust_score": context_dict(model_evaluation.get("model_trust_score_v1")).get("trust_score"),
                    "trust_level_changed": bool(context_list(model_evaluation.get("warnings"))),
                }
            ],
        }
        built = build_review_alerts(signal_rows, report_date=as_of_date, created_at=generated_at)
        raw_alerts = [dict(row) for row in context_list(built.get("alerts")) if isinstance(row, dict)]
        deployment_status = str(long_term_capital_deployment.get("status") or "").lower()
        primary = context_dict(long_term_capital_deployment.get("primary_candidate"))
        primary_status = str(primary.get("decision_gate_status") or "").lower()
        if deployment_status and deployment_status not in {"deployable", "ready"}:
            raw_alerts.append(
                build_alert(
                    report_date=as_of_date,
                    created_at=generated_at,
                    symbol=str(primary.get("symbol") or ""),
                    alert_type="capital_deployment_review",
                    severity="high_review" if primary_status == "blocked" else "medium_review",
                    title="Long-term capital deployment needs review",
                    summary=str(
                        long_term_capital_deployment.get("hold_capacity_message")
                        or "Capital deployment context is available for manual review."
                    ),
                    reason_codes=["capital_deployment_review", deployment_status],
                    source_refs=["long_term_capital_deployment"],
                    related_artifacts=["report_context"],
                    recommended_review_action="review_long_term_capital_deployment",
                )
            )
        display_rows = [
            alert_display_row(row, index=index, company_by_symbol=company_by_symbol)
            for index, row in enumerate(raw_alerts, start=1)
        ]
        active_rows = [
            row
            for row in display_rows
            if str(row.get("status") or "").lower() not in {"dismissed", "resolved"}
        ]
        active_rows.sort(
            key=lambda row: (
                int(row.get("priority") or 999),
                str(row.get("created_at") or ""),
                str(row.get("symbol") or ""),
                str(row.get("alert_id") or ""),
            )
        )
        inbox_rows = [
            {
                **row,
                "severity": row.get("display_severity"),
                "message": row.get("event_summary"),
                "title": row.get("why_review"),
            }
            for row in display_rows
        ]
        inbox = build_alert_inbox(inbox_rows, current_date=as_of_date, report_date=as_of_date)
        summary = context_dict(inbox.get("summary"))
        return {
            "review_only": True,
            "recommendation_only": True,
            "no_live_notifications": True,
            "does_not_override_recommendations": True,
            "note": ALERT_REVIEW_NOTE,
            "active_alerts_summary": {
                "total_alerts": len(display_rows),
                "active_alerts": len(active_rows),
                "top_priority_count": min(5, len(active_rows)),
                "by_review_area": count_alerts_by(display_rows, "review_area"),
                "by_severity": count_alerts_by(display_rows, "display_severity"),
                "by_status": count_alerts_by(display_rows, "status"),
                "empty_state": context_dict(summary.get("empty_state")),
            },
            "top_priority_alerts": active_rows[:5],
            "alerts_by_review_area": count_alerts_by(display_rows, "review_area"),
            "alerts_by_severity": count_alerts_by(display_rows, "display_severity"),
            "alerts_by_status": count_alerts_by(display_rows, "status"),
            "alert_lifecycle_metadata": {
                "dismissed_count": context_dict(inbox.get("dismissed_resolved_counts")).get("dismissed", 0),
                "resolved_count": context_dict(inbox.get("dismissed_resolved_counts")).get("resolved", 0),
                "stale_deferred_alerts": len(context_list(inbox.get("stale_deferred_alerts"))),
                "local_review_metadata_only": True,
            },
            "rows": display_rows[:40],
            "empty_state": "No active review alerts. Existing recommendations remain unchanged.",
        }

    def recommendation_context(rank: int, row: Dict[str, object]) -> Dict[str, object]:
        item = row["input"]
        target = row.get("target")
        rationale = action_rationale(
            item,
            row["action"],
            row["breakdown"],
            row["position_after_buy_pct"],
            target,
            targets,
        )
        explanation = score_explanation(item, row["breakdown"], target, row.get("insight"), rationale)
        watchlist_policy = evaluate_watchlist_policy(item.symbol, item.sleeve, targets)
        return {
            "rank": rank,
            "symbol": item.symbol,
            "company": item.company,
            "sleeve": item.sleeve,
            "trade_type": trade_type_label(item.trade_type),
            "action": row["action"],
            "score": round(float(row["score"]), 2),
            "current_price": item.current_price,
            "current_price_text": fmt_money(item.current_price) if item.current_price else "Needs refresh",
            "target_price": target.target_price if target else item.target_price,
            "target_price_text": target_price_text(item, target),
            "upside_pct": target.upside_pct if target else item.upside_pct,
            "upside_text": target_upside_text(item, target),
            "data_status": data_status_for_target(item, target),
            "sources": target_source_label(item, target),
            "score_breakdown": score_summary_with_insight(row["breakdown"], row["insight"]),
            "score_explanation": explanation,
            "watchlist_policy": watchlist_policy,
            "why": rationale,
            "rationale": rationale,
            "confidence": target_confidence_text(item, target),
            "target_drilldown": target_drilldowns.get(item.symbol, {}),
            "notes": item.notes,
        }

    recommendations = [recommendation_context(rank, row) for rank, row in enumerate(ranked, start=1)]
    synthesis_readiness_by_symbol = {
        str(row[0]): {
            "status": row[1],
            "score": row[2],
            "ready_events": row[3],
            "needs_review": row[4],
            "needs_corroboration": row[5],
            "primary_events": row[7],
            "independent_confirmed": row[8],
            "latest_event": row[9],
            "packet": row[10],
            "notes": row[11],
        }
        for row in synthesis_readiness_table["rows"]
        if row
    }
    long_term_queue_candidates = []
    sleeve_market_values = sleeve_market_values_for_ranked(ranked, positions)
    decision_gates_by_symbol: Dict[str, Dict[str, object]] = {}
    allocation_by_symbol: Dict[str, Dict[str, object]] = {}
    ranked_row_by_symbol: Dict[str, Dict[str, object]] = {}
    for rank, row in enumerate(ranked, start=1):
        item = row["input"]
        symbol = item.symbol
        candidate = recommendation_context(rank, row)
        gate = decision_safety_gate(row, decision_insights.get(symbol), targets)
        allocation = allocation_safety_for_candidate(
            row,
            gate,
            positions=positions,
            targets=targets,
            account_value=account_value,
            buy_capacity=default_buy_amount,
            sleeve_market_values=sleeve_market_values,
        )
        decision_gates_by_symbol[symbol.upper()] = gate
        allocation_by_symbol[symbol.upper()] = allocation.to_context()
        ranked_row_by_symbol[symbol.upper()] = row
        candidate.update(
            {
                "decision_mode": "long_term_buy_add" if item.sleeve == "long_term" else "",
                "decision_gate": gate,
                "safe_to_buy": gate.get("safe_to_buy"),
                "decision_gate_status": gate.get("status"),
                "blocked_reasons": gate.get("reasons", []),
                "suggested_amount": allocation.suggested_amount,
                "allocation_safety": allocation.to_context(),
                "ai_synthesis_readiness": synthesis_readiness_by_symbol.get(symbol, {}),
            }
        )
        long_term_queue_candidates.append(candidate)
    long_term_add_queue = build_long_term_add_queue(long_term_queue_candidates)
    top_target_drilldown = target_drilldowns.get(next_item.symbol, {})
    allocation_rows = [
        {
            "symbol": symbol,
            "pct": pct,
            "pct_text": fmt_pct(pct),
            "value": value,
            "value_text": fmt_money(value),
        }
        for symbol, pct, value in allocation_segments
    ]
    source_names = [row["source_name"] for row in source_rows]
    queue_headers = decision_headers
    learning_review = build_learning_review_context(source_quality_rows)
    best_add_fallback_review = build_best_add_fallback_review(
        long_term_queue_candidates,
        decision_gates_by_symbol=decision_gates_by_symbol,
        provider_gap_records=[row for row in provider_gap_rows if isinstance(row, dict)],
    )
    deploy_review = (
        context_dict(best_add_fallback_review.get("primary_add"))
        or context_dict(best_add_fallback_review.get("fallback_add"))
        or context_dict(best_add_fallback_review.get("blocked_top_candidate"))
    )
    deploy_symbol = str(deploy_review.get("symbol") or "").upper()
    deploy_row = ranked_row_by_symbol.get(deploy_symbol)
    if deploy_row is not None:
        deploy_candidate: object = recommendation_context(int(deploy_review.get("rank") or 1), deploy_row)
    else:
        deploy_candidate = deploy_review
    if not deploy_symbol:
        deploy_gate = {
            "safe_to_buy": False,
            "status": "Blocked",
            "reasons": ["No long-term buy/add candidate is available."],
        }
        deploy_allocation = {
            "suggested_amount": 0.0,
            "reduction_reasons": ["No long-term buy/add candidate is available."],
            "reason": "No long-term buy/add candidate is available.",
        }
    else:
        deploy_gate = decision_gates_by_symbol.get(deploy_symbol, {})
        deploy_allocation = allocation_by_symbol.get(deploy_symbol, {})
    capital_context = capital_deployment_context(
        targets,
        candidate=deploy_candidate,
        decision_gate=deploy_gate,
        allocation_safety=deploy_allocation,
        sleeve_market_values=sleeve_market_values,
        account_value=account_value,
    )
    recommendations_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in recommendations
        if isinstance(row, dict)
    }
    holding_health_inputs = []
    for symbol, position in sorted(positions.items()):
        normalized_symbol = symbol.upper()
        recommendation = recommendations_by_symbol.get(normalized_symbol, {})
        research_item = research_by_symbol.get(normalized_symbol)
        sleeve = str(recommendation.get("sleeve") or getattr(research_item, "sleeve", ""))
        if sleeve not in {"long_term", "long_term_core"}:
            continue
        market_value = float(position.get("market_value", 0) or 0)
        holding_health_inputs.append(
            {
                "symbol": normalized_symbol,
                "company": recommendation.get("company") or getattr(research_item, "company", ""),
                "sleeve": sleeve,
                "quantity": position.get("quantity"),
                "market_value": market_value,
                "portfolio_pct": round((market_value / account_value) * 100, 4) if account_value else 0.0,
                "source": position.get("source"),
            }
        )
    holding_health_review = build_holding_health_review(
        holding_health_inputs,
        recommendations_by_symbol=recommendations_by_symbol,
        score_trends_by_symbol=score_history_by_symbol,
        provider_gaps=[row for row in provider_gap_rows if isinstance(row, dict)],
        catalyst_follow_through=context_list(context_dict(learning_review.get("catalyst_follow_through")).get("top_outcomes")),
        recommendation_outcomes=context_list(context_dict(learning_review.get("recommendation_outcomes")).get("top_outcomes")),
        source_usefulness=context_list(context_dict(learning_review.get("source_usefulness")).get("top_sources")),
        ai_status_by_symbol=synthesis_readiness_by_symbol,
        allocation_by_symbol=allocation_by_symbol,
    )
    long_term_capital_deployment = long_term_capital_deployment_context(
        add_queue=long_term_add_queue,
        fallback_review=best_add_fallback_review,
        capital_context=capital_context,
        holding_health_review=holding_health_review,
    )
    earnings_universe_rows = []
    for rec in recommendations:
        symbol = str(rec.get("symbol") or "").upper()
        item = research_by_symbol.get(symbol)
        earnings_universe_rows.append(
            {
                "symbol": symbol,
                "company": rec.get("company") or getattr(item, "company", ""),
                "category": getattr(item, "category", ""),
                "sleeve": rec.get("sleeve") or getattr(item, "sleeve", ""),
                "trade_type": rec.get("trade_type") or getattr(item, "trade_type", ""),
            }
        )
    stored_evidence_rows = [
        dict(row)
        for rows in stored_evidence_by_symbol.values()
        for row in rows
        if isinstance(row, dict)
    ]
    score_history_rows_flat = [
        dict(row)
        for rows in score_history_by_symbol.values()
        for row in rows
        if isinstance(row, dict)
    ]
    earnings_review = build_earnings_review_context(
        universe_rows=earnings_universe_rows,
        recommendations_by_symbol=recommendations_by_symbol,
        decision_gates_by_symbol=decision_gates_by_symbol,
        provider_gap_rows=[row for row in provider_gap_rows if isinstance(row, dict)],
        stored_evidence_rows=stored_evidence_rows,
        source_usefulness_rows=source_quality_rows,
        score_history_rows=score_history_rows_flat,
        ai_context_by_symbol=synthesis_readiness_by_symbol,
        as_of_date=report_date,
    )
    tactical_review = build_tactical_review_context(
        recommendations=recommendations,
        recommendations_by_symbol=recommendations_by_symbol,
        earnings_review=earnings_review,
        provider_gap_rows=[row for row in provider_gap_rows if isinstance(row, dict)],
        stored_evidence_rows=stored_evidence_rows,
        ai_context_by_symbol=synthesis_readiness_by_symbol,
        as_of_date=report_date,
    )
    model_evaluation = build_model_evaluation_context(
        recommendations=recommendations,
        learning_review=learning_review,
        as_of_date=report_date,
        generated_at=now.isoformat(timespec="seconds"),
        recommendation_run_id=db_run_id,
    )
    alerts_review = build_alerts_review_context(
        long_term_capital_deployment=long_term_capital_deployment,
        earnings_review=earnings_review,
        tactical_review=tactical_review,
        model_evaluation=model_evaluation,
        learning_review=learning_review,
        provider_gap_rows=[row for row in provider_gap_rows if isinstance(row, dict)],
        recommendations=recommendations,
        as_of_date=report_date,
        generated_at=now.isoformat(timespec="seconds"),
    )
    report_date = f"{now:%Y-%m-%d}"
    report_context = {
        "metadata": {
            "report_date": report_date,
            "generated_at": now.isoformat(timespec="seconds"),
            "model_version": "daily-report-rules-v1",
            "recommendation_run_id": db_run_id,
            "workflow_run_id": workflow_run_id_from_env(),
            "recommendation_only": True,
        },
        "summary": {
            "top_symbol": next_item.symbol,
            "top_company": next_item.company,
            "top_action": next_display_action,
            "top_score": round(float(next_buy["score"]), 2),
            "recommendation_label": next_recommendation_label,
            "amount_label": next_amount_label,
            "suggested_amount": suggested_amount,
            "suggested_amount_text": fmt_money(suggested_amount),
            "suggested_amount_reason": allocation_safety.reason,
            "allocation_safety": allocation_safety.to_context(),
            "current_price_text": fmt_money(next_item.current_price) if next_item.current_price else "Needs refresh",
            "target_text": target_price_text(next_item, next_target),
            "upside_text": target_upside_text(next_item, next_target),
            "confidence": target_confidence_text(next_item, next_target),
            "data_status": data_status_for_target(next_item, next_target),
            "target_quality": top_target_drilldown.get("blend_label", ""),
            "target_review_labels": top_target_drilldown.get("labels", []),
            "top_notes": next_item.notes,
            "decision_gate": decision_gate,
            "signal_counts": signal_counts,
            "persisted_decision_insights": stored_decision_insights,
            "verification_queue_items": stored_verification_queue_items,
        },
        "decision_safety": decision_gate,
        "long_term_capital_deployment": long_term_capital_deployment,
        "earnings_review": earnings_review,
        "tactical_review": tactical_review,
        "model_evaluation": model_evaluation,
        "alerts_review": alerts_review,
        "long_term_add_queue": long_term_add_queue,
        "reliability": {
            "mode": reliability_status,
            "price_counts": price_counts,
            "latest_provider_refresh": latest_refresh,
            "source_health": {
                "healthy": health_summary["healthy"],
                "needs_attention": health_summary["needs_attention"],
                "stale": health_summary["stale"],
                "not_implemented": health_summary["not_implemented"],
            },
            "top_blocker": top_health_alert[1] if top_health_alert else "",
        },
        "recommendations": recommendations,
        "target_drilldowns": {
            "top_symbol": next_item.symbol,
            "top_candidate": top_target_drilldown,
            "by_symbol": target_drilldowns,
            "table": table_context(target_drilldown_headers, source_drilldown_rows),
        },
        "holdings": {
            "headers": ["Symbol", "Source", "Qty", "Last", "Market Value", "Portfolio %"],
            "rows": holdings_rows,
            "allocation": allocation_rows,
        },
        "queues": {
            "action_queue": table_context(queue_headers, action_queue_rows, [2, 4]),
            "long_term": table_context(queue_headers, long_term_rows, [2, 4]),
            "short_term": table_context(queue_headers, short_term_decision_rows, [2, 4]),
            "next_day": {
                **table_context(["Rank", "Symbol", "Action", "Score", "Current", "Target", "Upside", "Data Status", "Why"], next_day_watchlist_rows),
                "status": next_day_status,
            },
            "speculative": table_context(queue_headers, speculative_rows, [2, 4]),
            "data_gaps": {
                **table_context(["Rank", "Symbol", "Data Gap", "Impact", "Best Pull", "Next Action"], visible_data_gap_rows),
                "note": data_gap_note,
            },
            "verification": table_context(
                ["Rank", "Symbol", "Type", "Status", "Impact", "Reason", "Command/Next Check", "Result"],
                visible_verification_queue_rows,
            ),
            "source_drilldown": table_context(
                target_drilldown_headers,
                source_drilldown_rows,
            ),
            "full_universe": table_context(
                ["Rank", "Symbol", "Sleeve", "Trade Type", "Action", "Score", "Current", "Target", "1Y Upside", "Data Status", "Sources", "Score Breakdown", "Why", "Confidence"],
                score_rows,
            ),
        },
        "readiness": {
            "items": readiness_items,
            "preview": next_day_status.get("preview"),
        },
        "decision_briefs": table_context(["Symbol", "Type", "Headline", "Why It Matters", "Next Check"], top_decision_brief_rows),
        "decision_insight_history": table_context(
            ["Symbol", "Previous", "Latest", "Score Move", "Headline", "Next Check"],
            decision_insight_history_rows,
        ),
        "insight_themes": table_context(["Theme", "Symbols", "Why It Matters", "Next Check"], insight_theme_table_rows),
        "score_movement": table_context(
            ["Symbol", "Base", "Evidence", "Trend", "Targets", "Gaps", "Final", "Action", "Top Driver"],
            score_movement_rows(ranked, limit=12),
        ),
        "trend_insights": table_context(["Symbol", "Overlay", "Trend Insight", "Score Movement"], trend_insight_rows(ranked, limit=12)),
        "data_gaps": table_context(["Rank", "Symbol", "Data Gap", "Impact", "Best Pull", "Next Action"], visible_data_gap_rows),
        "verification": table_context(
            ["Symbol", "Type", "Risk Or Uncertainty", "Next Check", "What Would Change The View"],
            verify_next_rows,
        ),
        "score_changes": table_context(
            ["Symbol", "Previous", "Latest", "Change", "Previous Action", "Latest Action", "Data Status"],
            score_change_rows[:12],
        ),
        "source_health": {
            "summary": health_summary,
            "top_blocker": top_health_alert[1] if top_health_alert else "",
            "alerts": table_context(
                ["Severity", "Source", "Status", "Records", "Last Run", "Latest Issue", "Next Action"],
                health_alert_rows,
            ),
            "issue_groups": table_context(
                ["Root Cause", "Severity", "Affected Sources", "Reason", "Next Action"],
                source_issue_group_rows(health_alert_rows),
            ),
            "provider_blockers": table_context(
                ["Severity", "Symbol", "Provider", "Field", "Blocks", "Likely Cause", "Decision Context", "Latest Detail", "Next Action"],
                provider_blocker_rows,
            ),
        },
        "provider_gap_review": provider_gap_review,
        "data_ingestion": table_context(
            ["Source", "Tier", "Category", "Free/Paid", "Status", "Raw Payloads", "Curated Records", "Last Run", "Latest Issue", "Next Action"],
            data_ingestion_rows,
        ),
        "source_quality": {
            "summary": source_quality_summary(source_quality_rows),
            "table": source_quality_table,
            "low_relevance": low_relevance_table,
            "low_confidence_matches": low_confidence_matches_table,
            "rows": source_quality_rows,
        },
        "learning_review": learning_review,
        "source_depth": source_depth_table,
        "ingestion_run_plan": ingestion_run_plan_table,
        "ingestion_backfill": ingestion_backfill_table,
        "evidence_events": evidence_events_table,
        "evidence_review_queue": evidence_review_queue_table,
        "synthesis_readiness": synthesis_readiness_table,
        "paid_providers": table_context(["Provider", "Known Pricing", "What It Unlocks", "V1.6 Decision"], paid_provider_rows),
        "signal_health": table_context(["Signal Type", "Signals", "Symbols", "Total Delta", "Latest Update", "Mode"], signal_health_rows),
        "research_sources": {
            "rows": source_rows,
        },
        "feedback": {
            "source_options": source_names,
            "default_symbol": next_item.symbol,
            "recent": recent_feedback(),
        },
        "storage_counts": {
            "target_sources": stored_target_sources,
            "blended_targets": stored_blended_targets,
            "scores": stored_scores,
            "score_signals": stored_score_signals,
            "decision_insights": stored_decision_insights,
            "verification_queue_items": stored_verification_queue_items,
        },
        "email": {
            "recipient": (targets.get("email_reports", {}) or {}).get("recipient", "") if isinstance(targets.get("email_reports", {}), dict) else "",
            "subject": f"Stock Trading Daily Report - {report_date}",
        },
        "artifacts": {
            "dashboard": dashboard_path.name,
            "markdown": report_path.name,
            "csv": csv_path.name,
            "email": email_path.name,
            "end_of_day": end_of_day_path.name,
            "watchlist": watchlist_path.name,
            "context": report_context_path.name,
            "ai_context": ai_context_path.name,
            "ai_briefs_markdown": ai_briefs_markdown_path.name,
            "ai_briefs_json": ai_briefs_json_path.name,
            "ai_briefs_html": ai_briefs_html_path.name,
        },
        "ai_analysis": {
            "context_path": ai_context_path.name,
            "briefs_markdown_path": ai_briefs_markdown_path.name,
            "briefs_json_path": ai_briefs_json_path.name,
            "briefs_html_path": ai_briefs_html_path.name,
            "decision_insights": decision_insight_rows_for_storage,
            "verification_queue": persisted_verification_queue_rows,
        },
    }
    report_context = safe_json(report_context)
    ai_analysis_context = {
        "metadata": {
            "report_date": report_date,
            "generated_at": now.isoformat(timespec="seconds"),
            "recommendation_run_id": db_run_id,
            "workflow_run_id": workflow_run_id_from_env(),
            "purpose": "future_ai_analysis_context",
            "llm_generated": False,
        },
        "decision_insights": decision_insight_rows_for_storage,
        "verification_queue": persisted_verification_queue_rows,
        "score_signals": score_signal_rows[:100],
        "source_health": {
            "summary": health_summary,
            "alerts": health_alert_rows,
            "provider_blockers": provider_blocker_rows,
        },
        "data_gaps": data_gap_rows,
        "insight_themes": insight_theme_table_rows,
        "evidence_events": {
            "headers": evidence_events_table["headers"],
            "rows": evidence_events_table["rows"],
        },
        "evidence_review_queue": {
            "headers": evidence_review_queue_table["headers"],
            "rows": evidence_review_queue_table["rows"],
        },
        "synthesis_readiness": {
            "headers": synthesis_readiness_table["headers"],
            "rows": synthesis_readiness_table["rows"],
        },
    }
    if persist:
        analysis_run_id = record_analysis_run(
            db_run_id,
            MODEL_VERSION,
            config_version="portfolio_targets.json",
            input_snapshot={
                "symbols": [item.symbol for item in research],
                "report_date": report_date,
                "price_counts": price_counts,
            },
            output_counts={
                "symbols": len(research),
                "target_sources": len(generated_target_rows),
                "blended_targets": len(blended_db_rows),
                "recommendations": len(recommendations),
                "score_signals": len(score_signal_rows),
                "decision_insights": len(decision_insight_rows_for_storage),
                "verification_queue": len(verification_queue_rows_for_storage),
            },
            context_path=str(ai_context_path) if write_context else "",
        )
        report_context["metadata"]["analysis_run_id"] = analysis_run_id
        ai_analysis_context["metadata"]["analysis_run_id"] = analysis_run_id

    if write_context:
        ai_context_path.write_text(json.dumps(safe_json(ai_analysis_context), indent=2))
    return report_context


AnalysisResult = Dict[str, object]


def build_report_context(result: AnalysisResult) -> Dict[str, object]:
    """Return the JSON-native presentation context for an analysis result."""
    return result


def latest_analysis_summary() -> Dict[str, object]:
    row = latest_analysis_run()
    return dict(row) if row else {}
