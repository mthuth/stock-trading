#!/usr/bin/env python3
"""Generate the daily what-to-buy-next report.

This first version combines local research inputs, the latest E*TRADE snapshot
when available, and manual positions from config/portfolio_targets.json.
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
import subprocess
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import stdev
from typing import Dict, Iterable, List, Set


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

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    init_db,
    latest_successful_provider_refresh,
    record_blended_targets,
    record_recommendation_run,
    record_recommendation_scores,
    record_score_signals,
    record_target_sources,
)


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
    speculative_config = targets.get("speculative_ai", {})
    speculative_allows_buys = (
        isinstance(speculative_config, dict)
        and speculative_config.get("allow_buy_recommendations") is True
    )
    if item.sleeve == "speculative_ai" and not speculative_allows_buys:
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
) -> str:
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
    return target.confidence.title() if target else item.confidence


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
    peer_groups = model_config.get("peer_groups", {})
    if isinstance(peer_groups, dict):
        for name, config in peer_groups.items():
            if symbol in [str(item).upper() for item in config.get("symbols", [])]:
                return str(name), config
    return "unknown", {}


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

    peer_group, peer_config = peer_group_for_symbol(item.symbol, model_config)
    if item.sleeve == "etf":
        peer_group = "etf_ballast"
        peer_config = model_config.get("peer_groups", {}).get("etf_ballast", {})
    defaults = model_config.get("target_return_defaults", {})
    group_defaults = defaults.get(peer_group, {}) if isinstance(defaults, dict) else {}
    base_upside = to_float(group_defaults.get("base_upside_pct"), 12)
    min_upside = to_float(group_defaults.get("min_upside_pct"), -15)
    max_upside = to_float(group_defaults.get("max_upside_pct"), 30)

    quality_config = model_config.get("quality_adjustment", {})
    catalyst_config = model_config.get("catalyst_adjustment", {})
    risk_config = model_config.get("risk_adjustment", {})
    margin_config = model_config.get("margin_adjustment", {})

    quality_adj = adjustment_from_score(
        item.quality_score,
        to_float(quality_config.get("basis_score"), 80),
        to_float(quality_config.get("pct_per_score_point"), 0.2),
        to_float(quality_config.get("max_adjustment_pct"), 6),
    )
    catalyst_adj = adjustment_from_score(
        item.catalyst_score,
        to_float(catalyst_config.get("basis_score"), 75),
        to_float(catalyst_config.get("pct_per_score_point"), 0.15),
        to_float(catalyst_config.get("max_adjustment_pct"), 6),
    )
    risk_penalty = max(
        0,
        min(
            to_float(risk_config.get("max_penalty_pct"), 8),
            (to_float(risk_config.get("basis_score"), 75) - item.risk_score)
            * to_float(risk_config.get("pct_per_score_point_below_basis"), 0.2),
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
    strong_margin_bonus = to_float(margin_config.get("strong_margin_bonus_pct"), 4)
    negative_margin_penalty = to_float(margin_config.get("negative_margin_penalty_pct"), 8)
    if operating_margin is not None and operating_margin < 0:
        margin_adj -= negative_margin_penalty
    elif cash_flow_margin is not None and cash_flow_margin < 0:
        margin_adj -= negative_margin_penalty / 2
    elif (
        operating_margin is not None
        and cash_flow_margin is not None
        and operating_margin >= to_float(margin_config.get("strong_operating_margin"), 0.25)
        and cash_flow_margin >= to_float(margin_config.get("strong_cash_flow_margin"), 0.20)
    ):
        margin_adj += strong_margin_bonus

    thin_input_penalty = 4 if not revenue else 0
    if not (operating_income or operating_cash_flow or diluted_eps):
        thin_input_penalty += 3

    modeled_upside = max(
        min_upside,
        min(
            max_upside,
            base_upside + quality_adj + catalyst_adj + margin_adj - risk_penalty - thin_input_penalty,
        ),
    )
    target_price = item.current_price * (1 + modeled_upside / 100)

    confidence = "medium" if revenue and (operating_income or operating_cash_flow or diluted_eps) else "low"
    if item.sleeve == "speculative_ai":
        confidence = "low"

    range_widths = model_config.get("range_width_pct", {})
    range_width = to_float(
        range_widths.get(confidence),
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
        metric_notes.append("thin fundamentals; target relies on score-based proxy assumptions")

    notes = (
        f"Peer group {peer_group}; base upside {base_upside:.1f}%; "
        f"quality adj {quality_adj:+.1f}%; catalyst adj {catalyst_adj:+.1f}%; "
        f"margin adj {margin_adj:+.1f}%; risk/data penalty -{risk_penalty + thin_input_penalty:.1f}%. "
        + "; ".join(metric_notes)
        + f". Peer notes: {peer_config.get('notes', '')}"
    )

    return {
        "run_id": run_id,
        "symbol": item.symbol,
        "target_type": "fundamental",
        "source_name": "Internal fundamental model",
        "source_type": "model",
        "target_price": round(target_price, 4),
        "target_low": round(target_low, 4),
        "target_high": round(target_high, 4),
        "current_price": item.current_price,
        "upside_pct": round(modeled_upside, 4),
        "as_of_date": as_of_date,
        "freshness_days": 0,
        "confidence": confidence,
        "provider_endpoint": "SEC companyfacts + configured V1.2 assumptions",
        "raw_payload_ref": "",
        "notes": notes,
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
    if item.current_price <= 0:
        return None

    history = price_history.get(item.symbol, [])
    windows = model_config.get("windows", {}) if isinstance(model_config, dict) else {}
    buffers = model_config.get("buffers", {}) if isinstance(model_config, dict) else {}
    short_days = int(to_float(windows.get("short_trend_days"), 20))
    medium_days = int(to_float(windows.get("medium_trend_days"), 50))
    long_days = int(to_float(windows.get("long_trend_days"), 200))
    support_days = int(to_float(windows.get("support_lookback_days"), 60))
    resistance_days = int(to_float(windows.get("resistance_lookback_days"), 60))
    breakout_buffer = to_float(buffers.get("breakout_buffer_pct"), 0.03)
    stop_buffer = to_float(buffers.get("stop_review_buffer_below_support_pct"), 0.05)

    if len(history) < short_days:
        return None

    closes = [row["close"] for row in history if row["close"] > 0]
    highs = [row["high"] for row in history if row["high"] > 0]
    lows = [row["low"] for row in history if row["low"] > 0]
    if len(closes) < short_days:
        return None

    current = item.current_price
    ma20 = average(closes[-short_days:])
    ma50 = average(closes[-medium_days:]) if len(closes) >= medium_days else 0.0
    ma200 = average(closes[-long_days:]) if len(closes) >= long_days else 0.0
    support = min(lows[-support_days:]) if len(lows) >= min(support_days, len(lows)) else min(lows)
    resistance = max(highs[-resistance_days:]) if len(highs) >= min(resistance_days, len(highs)) else max(highs)

    returns = [
        (closes[index] - closes[index - 1]) / closes[index - 1]
        for index in range(1, len(closes[-21:]))
        if closes[index - 1] > 0
    ]
    daily_volatility = stdev(returns) if len(returns) >= 2 else 0.0

    if ma50 and current > ma20 > ma50:
        trend_state = "bullish"
        target_price = max(resistance * (1 + breakout_buffer), current * 1.04)
    elif ma50 and current > ma50 and ma20 >= ma50 * 0.98:
        trend_state = "constructive"
        target_price = max((current + resistance) / 2, current * 1.02)
    elif current < ma20 and ma50 and ma20 < ma50:
        trend_state = "weak"
        target_price = min(resistance, current * 1.02)
    else:
        trend_state = "mixed"
        target_price = max((current + resistance) / 2, current * 1.01)

    target_low = max(support, current * (1 - min(daily_volatility * 2, 0.12)))
    target_high = max(target_price, resistance)
    stop_review = support * (1 - stop_buffer)
    upside = ((target_price - current) / current) * 100 if current > 0 else 0.0

    confidence = "medium" if len(closes) >= support_days and daily_volatility <= 0.04 else "low"
    if len(closes) < medium_days:
        confidence = "low"
    if item.sleeve == "speculative_ai":
        confidence = "low"

    notes = (
        f"Trend {trend_state}; {len(closes)} daily bars; "
        f"MA{short_days} {ma20:.2f}; "
        + (f"MA{medium_days} {ma50:.2f}; " if ma50 else f"MA{medium_days} unavailable; ")
        + (f"MA{long_days} {ma200:.2f}; " if ma200 else f"MA{long_days} unavailable; ")
        + f"support {support:.2f}; resistance {resistance:.2f}; "
        f"entry zone {target_low:.2f}-{min(current, target_price):.2f}; "
        f"stop/review {stop_review:.2f}; 20-day daily volatility {daily_volatility * 100:.1f}%."
    )

    return {
        "run_id": run_id,
        "symbol": item.symbol,
        "target_type": "technical",
        "source_name": "Internal technical model",
        "source_type": "model",
        "target_price": round(target_price, 4),
        "target_low": round(target_low, 4),
        "target_high": round(target_high, 4),
        "current_price": current,
        "upside_pct": round(upside, 4),
        "as_of_date": as_of_date,
        "freshness_days": 0,
        "confidence": confidence,
        "provider_endpoint": "price_history + configured V1.3 technical assumptions",
        "raw_payload_ref": "",
        "notes": notes,
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
            confidence = "low"
        else:
            blend_status = "Single-source"
            confidence = "low"

        if len(types) >= 2 and target_low and target_high and current_price > 0:
            spread_pct = ((target_high - target_low) / current_price) * 100
            if spread_pct > 45:
                confidence = "low"
                blend_status += "; wide target range"
        if item and "stale" in (item.price_source or "").lower():
            confidence = "low"
            if "stale price" not in blend_status:
                blend_status += "; stale price"

        weight_parts = {
            str(row.get("target_type")): round(weight / total_weight, 4)
            for row, weight in source_weights
        }
        source_names = sorted({str(row.get("source_name") or row.get("target_type")) for row in usable})
        notes = (
            f"{blend_status}; sources: {', '.join(source_names)}; "
            f"weights: {', '.join(f'{name} {weight:.0%}' for name, weight in weight_parts.items())}."
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
               NULL AS matched_text, NULL AS tag_match_type, NULL AS tag_confidence
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
               t.confidence AS tag_confidence
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
    match_note = f"; matched {matched}" if matched else ""
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
    target_sources: Dict[str, List[Dict[str, object]]],
    evidence: Dict[str, List[Dict[str, object]]],
) -> str:
    target_rows = target_sources.get(symbol, [])
    evidence_rows = [row for row in evidence.get(symbol, []) if evidence_mentions_item(row, item)]
    target_items = []
    for row in target_rows:
        upside = row.get("upside_pct")
        upside_text = fmt_pct(float(upside)) if upside not in (None, "") else "n/a"
        low = row.get("target_low")
        high = row.get("target_high")
        range_text = ""
        if low not in (None, "") and high not in (None, ""):
            range_text = f" range {fmt_money(float(low))}-{fmt_money(float(high))};"
        notes = str(row.get("notes") or "").strip()
        target_items.append(
            [
                row.get("target_type", "target"),
                row.get("source_name", "Unknown"),
                fmt_money(float(row.get("target_price") or 0)),
                range_text.replace(" range ", "").replace(";", "") or "n/a",
                upside_text,
                row.get("confidence") or "unknown",
                row.get("as_of_date") or "unknown",
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
            ["Type", "Source", "Target", "Range", "Upside", "Confidence", "Date", "How calculated / published"],
            target_items,
            "target-source-table",
        )
        if target_items
        else "<p>No stored target-source rows yet.</p>"
    )
    evidence_block = (
        "<ul>" + "".join(evidence_items) + "</ul>"
        if evidence_items
        else "<p>No captured evidence yet.</p>"
    )
    return f"""
      <div class="source-drilldown">
        <h4>Target Sources</h4>
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
        if endpoint == "public_feed" and is_public_feed_source(provider):
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
        if endpoint in {"public_feed", "public_feed_body"} and is_public_feed_source(provider):
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
        if field == "public_feed" and is_public_feed_source(provider):
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
        filters[source] = [(source, "public_feed"), (source, "public_feed_body")]
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


def feedback_record_count(source_operations: Dict[str, Dict[str, object]]) -> int:
    return int(source_operations.get("Manual user notes", {}).get("records") or 0)


def pre_market_readiness_items(
    top_row: Dict[str, object] | None,
    holdings_rows: List[List[object]],
    health_summary: Dict[str, object],
    health_alert_rows: List[List[object]],
    feedback_count: int,
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

    return items


def readiness_class(status: str) -> str:
    return status.lower().replace(" ", "-")


def pre_market_readiness_html(items: List[Dict[str, str]]) -> str:
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


def maybe_refresh_market_data(argv: List[str]) -> None:
    if "--refresh" not in argv:
        return
    result = subprocess.run(
        [sys.executable, str(REFRESH_SCRIPT)],
        cwd=ROOT,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit("Market-data refresh failed; report was not generated.")


def generate_report() -> List[Path]:
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
    account_value = float(targets.get("account_value", 50000))
    monthly_contribution = float(targets.get("monthly_contribution", 1000))
    default_buy_amount = min(monthly_contribution, account_value * 0.05)

    now = datetime.now()
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"daily-recommendation-{now:%Y-%m-%d}.md"
    dashboard_path = REPORTS_DIR / f"dashboard-{now:%Y-%m-%d}.html"
    csv_path = REPORTS_DIR / f"daily-recommendation-{now:%Y-%m-%d}.csv"
    email_path = REPORTS_DIR / f"email-summary-{now:%Y-%m-%d}.txt"
    end_of_day_path = REPORTS_DIR / f"end-of-day-{now:%Y-%m-%d}.md"
    watchlist_path = REPORTS_DIR / f"next-day-watchlist-{now:%Y-%m-%d}.md"
    report_context_path = REPORTS_DIR / f"report-context-{now:%Y-%m-%d}.json"
    db_run_id = record_recommendation_run(
        report_date=f"{now:%Y-%m-%d}",
        report_path=report_path,
        dashboard_path=dashboard_path,
        csv_path=csv_path,
        email_path=email_path,
        account_value=account_value,
        monthly_contribution=monthly_contribution,
        notes=f"Daily report generation with target-source capture. Reliability: {reliability_status}.",
        workflow_run_id=workflow_run_id_from_env(),
    )
    generated_target_rows = target_source_rows(research, db_run_id, f"{now:%Y-%m-%d}", targets)
    stored_target_sources = record_target_sources(
        db_run_id,
        generated_target_rows,
    )
    blended_by_symbol, blended_db_rows = blended_target_rows(
        generated_target_rows,
        db_run_id,
        targets,
        research_by_symbol,
    )
    stored_blended_targets = record_blended_targets(db_run_id, blended_db_rows)
    stored_targets_by_symbol = latest_target_sources_by_symbol()
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
    report_date = f"{now:%Y-%m-%d}"
    score_signal_rows = score_signal_storage_rows(db_run_id, report_date, ranked)
    stored_score_signals = record_score_signals(score_signal_rows)
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
                ),
            }
        )
    stored_scores = record_recommendation_scores(db_run_id, score_db_rows)
    score_history_by_symbol = latest_score_history_by_symbol()
    decision_insights = decision_insights_by_symbol(
        ranked,
        stored_evidence_by_symbol,
        target_counts,
    )
    score_trend_table = html_table(
        ["Symbol", "Company/Fund", "Latest", "Change", "Action", "Trend", "Data Status"],
        score_history_rows(ranked, score_history_by_symbol),
        "score-trend-table",
        raw_columns={5},
    )
    buy_candidates = [
        row for row in ranked if row["action"] in {"Buy", "Add"} and row["input"].sleeve != "etf"
    ]
    next_buy = buy_candidates[0] if buy_candidates else ranked[0]

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
                ),
                target_confidence_text(item, target),
            ]
        )

    next_item = next_buy["input"]
    next_target = next_buy.get("target")
    suggested_amount = default_buy_amount
    next_action = str(next_buy["action"])
    actionable_next = next_action in {"Strong Buy", "Buy", "Add"}
    next_recommendation_label = "Recommended next buy" if actionable_next else "Top-ranked candidate"
    next_amount_label = "Suggested buy amount" if actionable_next else "Monthly buy capacity"
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
                      {source_drilldown_html(item.symbol, item, stored_targets_by_symbol, stored_evidence_by_symbol)}
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
    source_drilldown_rows = []
    for row in ranked:
        item = row["input"]
        counts = target_counts.get(item.symbol, {"analyst": 0, "all": 0})
        source_drilldown_rows.append(
            [
                item.symbol,
                counts["analyst"],
                counts["all"],
                len(stored_evidence_by_symbol.get(item.symbol, [])),
                len(stored_score_signals_by_symbol.get(item.symbol, [])),
                evidence_summary(item.symbol, stored_evidence_by_symbol, item),
            ]
        )
    source_drilldown_table = html_table(
        ["Symbol", "Analyst Targets", "All Targets", "Evidence Items", "Insight Signals", "Latest Evidence"],
        source_drilldown_rows,
        "compact-table",
    )

    source_rows = []
    source_options = []
    for source in research_sources:
        source_name = source.get("source_name", "")
        operations = operations_for_source(source_name, source_operations)
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
    readiness_items = pre_market_readiness_items(
        action_queue_items[0] if action_queue_items else next_buy,
        holdings_rows,
        health_summary,
        health_alert_rows,
        feedback_record_count(source_operations),
    )
    pre_market_readiness = pre_market_readiness_html(readiness_items)
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
    for rank, row in enumerate(action_queue_items[:8], start=1):
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
                action_rationale(item, row["action"], row["breakdown"], row["position_after_buy_pct"], target),
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
                action_rationale(item, row["action"], row["breakdown"], row["position_after_buy_pct"], target),
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

    report_context = {
        "metadata": {
            "report_date": f"{now:%Y-%m-%d}",
            "generated_at": now.isoformat(timespec="seconds"),
            "model_version": "daily-report-rules-v1",
            "recommendation_run_id": db_run_id,
            "workflow_run_id": workflow_run_id_from_env(),
            "recommendation_only": True,
        },
        "summary": {
            "top_symbol": next_item.symbol,
            "top_action": next_action,
            "top_score": round(float(next_buy["score"]), 2),
        },
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
        "recommendations": [
            {
                "rank": rank,
                "symbol": row["input"].symbol,
                "company": row["input"].company,
                "sleeve": row["input"].sleeve,
                "trade_type": row["input"].trade_type,
                "action": row["action"],
                "score": round(float(row["score"]), 2),
                "current_price": row["input"].current_price,
                "target_price": row["target"].target_price if row.get("target") else row["input"].target_price,
                "upside_pct": row["target"].upside_pct if row.get("target") else row["input"].upside_pct,
                "confidence": target_confidence_text(row["input"], row.get("target")),
                "data_status": data_status_for_target(row["input"], row.get("target")),
                "rationale": action_rationale(
                    row["input"],
                    row["action"],
                    row["breakdown"],
                    row["position_after_buy_pct"],
                    row.get("target"),
                ),
                "notes": row["input"].notes,
            }
            for rank, row in enumerate(ranked, start=1)
        ],
    }
    report_context_path.write_text(json.dumps(report_context, indent=2))

    report = f"""# Daily What-To-Buy-Next Report

Generated: {now:%Y-%m-%d %H:%M}

## Summary

{next_recommendation_label}: **{next_item.symbol} - {next_item.company}**

- Action: **{next_action}**
- Score: **{next_buy['score']:.1f}/100**
- {next_amount_label}: **{fmt_money(suggested_amount)}**
- Current price: **{fmt_money(next_item.current_price) if next_item.current_price else 'Needs refresh'}**
- Blended target: **{target_price_text(next_item, next_target)}**
- One-year upside: **{target_upside_text(next_item, next_target)}**
- Confidence: **{target_confidence_text(next_item, next_target)}**
- Source health: **{health_summary['healthy']} healthy / {health_summary['needs_attention']} needs attention / {health_summary['stale']} stale**
- Report reliability: **{reliability_status}**
- Latest successful provider refresh: **{latest_refresh}**
- Active insight signals: **{signal_counts['signals']} signals across {signal_counts['symbols']} symbols**

Reason: {next_item.notes}

## Report Reliability

- Workflow run: **{workflow_run_id_from_env() or 'direct report run'}**
- Recommendation run: **{db_run_id}**
- Fresh prices: **{price_counts['fresh']}**
- Price-history fallback prices: **{price_counts['fallback']}**
- Stale prices: **{price_counts['stale']}**
- Manual prices: **{price_counts['manual']}**
- Missing prices: **{price_counts['missing']}**
- Source-health blocker: **{top_health_alert[1] if top_health_alert else 'None'}**

## Current Holdings Used

{markdown_table(['Symbol', 'Source', 'Qty', 'Last', 'Market Value', 'Portfolio %'], holdings_rows) if holdings_rows else 'No holdings found. Add an E*TRADE snapshot or manual positions.'}

## Next-Day Watchlist

{markdown_table(['Rank', 'Symbol', 'Action', 'Score', 'Current', 'Target', 'Upside', 'Data Status', 'Why'], next_day_watchlist_rows) if next_day_watchlist_rows else 'No watchlist candidates available.'}

## Top Decision Briefs

{markdown_table(['Symbol', 'Type', 'Headline', 'Why It Matters', 'Next Check'], top_decision_brief_rows) if top_decision_brief_rows else 'No decision briefs available.'}

## Source Health Alerts

{markdown_table(['Severity', 'Source', 'Status', 'Records', 'Last Run', 'Latest Issue', 'Next Action'], health_alert_rows) if health_alert_rows else 'No source health alerts.'}

## Source Health Snapshot

- Healthy implemented sources: **{health_summary['healthy']}**
- Implemented but needs attention: **{health_summary['needs_attention']}**
- Implemented but stale: **{health_summary['stale']}**
- Not implemented yet: **{health_summary['not_implemented']}**

## Insight Themes

{markdown_table(['Theme', 'Symbols', 'Why It Matters', 'Next Check'], insight_theme_table_rows) if insight_theme_table_rows else 'No insight themes found.'}

## Insight Drivers

{markdown_table(['Symbol', 'Base', 'Evidence', 'Trend', 'Targets', 'Gaps', 'Final', 'Action', 'Top Driver'], score_movement_rows(ranked, limit=12))}

## What To Verify Next

{markdown_table(['Symbol', 'Type', 'Risk Or Uncertainty', 'Next Check', 'What Would Change The View'], verify_next_rows) if verify_next_rows else 'No high-priority verification checks found.'}

## Ranked Data Gap Queue

{markdown_table(['Rank', 'Symbol', 'Data Gap', 'Impact', 'Best Pull', 'Next Action'], visible_data_gap_rows) if visible_data_gap_rows else 'No high-impact data gaps found.'}

## Trend Insights

{markdown_table(['Symbol', 'Overlay', 'Trend Insight', 'Score Movement'], trend_insight_rows(ranked, limit=12))}

## Score Changes Since Previous Run

{markdown_table(['Symbol', 'Previous', 'Latest', 'Change', 'Previous Action', 'Latest Action', 'Data Status'], score_change_rows[:12]) if score_change_rows else 'No score changes of 1 point or more since the previous stored run.'}

## Ranked V1 Universe

{markdown_table(['Rank', 'Symbol', 'Sleeve', 'Trade Type', 'Action', 'Score', 'Current', 'Target', '1Y Upside', 'Data Status', 'Sources', 'Score Breakdown', 'Why', 'Confidence'], score_rows)}

## Notes

- This report is decision support, not automated trading.
- Rows marked `Needs refresh` require updated market data and target-price inputs before acting.
- E*TRADE holdings use the latest production read-only snapshot when available; otherwise manual positions are used.
- Rows with missing price or target data are tracked in provider-gap history for later paid-provider decisions.
- Target-source storage captured {stored_target_sources} analyst, fundamental, and technical target inputs for run {db_run_id}.
- Blended target storage captured {stored_blended_targets} blended targets for run {db_run_id}.
- Recommendation score storage captured {stored_scores} score rows for trend tracking.
- Insight signal storage captured {stored_score_signals} active signal rows for run {db_run_id}.
"""
    report_path.write_text(report)
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "symbol",
                "company",
                "sleeve",
                "trade_type",
                "action",
                "score",
                "current_price",
                "target_price",
                "upside_pct",
                "data_status",
                "sources",
                "score_breakdown",
                "why",
                "confidence",
                "notes",
            ]
        )
        for rank, row in enumerate(ranked, start=1):
            item = row["input"]
            target = row.get("target")
            writer.writerow(
                [
                    rank,
                    item.symbol,
                    item.company,
                    item.sleeve,
                    trade_type_label(item.trade_type),
                    row["action"],
                    f"{row['score']:.1f}",
                    f"{item.current_price:.4f}" if item.current_price else "",
                    f"{target.target_price:.4f}" if target else f"{item.target_price:.4f}" if item.target_price else "",
                    f"{target.upside_pct:.2f}" if target else f"{item.upside_pct:.2f}" if item.upside_pct else "",
                    data_status_for_target(item, target),
                    target_source_label(item, target),
                    score_summary_with_insight(row["breakdown"], row["insight"]),
                    action_rationale(
                        item,
                        row["action"],
                        row["breakdown"],
                        row["position_after_buy_pct"],
                        target,
                    ),
                    target_confidence_text(item, target),
                    item.notes,
                ]
            )
    end_of_day_report = f"""# End-of-Day Review - {now:%Y-%m-%d}

Generated: {now:%Y-%m-%d %H:%M}

## Top Recommendation

- {next_recommendation_label}: **{next_item.symbol} - {next_item.company}**
- Action: **{next_action}**
- Score: **{next_buy['score']:.1f}/100**
- Current price: **{fmt_money(next_item.current_price) if next_item.current_price else 'Needs refresh'}**
- Blended target: **{target_price_text(next_item, next_target)}**
- Upside: **{target_upside_text(next_item, next_target)}**

## Score Changes Since Previous Run

{markdown_table(['Symbol', 'Previous', 'Latest', 'Change', 'Previous Action', 'Latest Action', 'Data Status'], score_change_rows[:12]) if score_change_rows else 'No score changes of 1 point or more since the previous stored run.'}

## Top Decision Briefs

{markdown_table(['Symbol', 'Type', 'Headline', 'Why It Matters', 'Next Check'], top_decision_brief_rows[:5]) if top_decision_brief_rows else 'No decision briefs available.'}

## What To Verify Next

{markdown_table(['Symbol', 'Type', 'Risk Or Uncertainty', 'Next Check', 'What Would Change The View'], verify_next_rows[:6]) if verify_next_rows else 'No high-priority verification checks found.'}

## Insight Drivers

{markdown_table(['Symbol', 'Base', 'Evidence', 'Trend', 'Targets', 'Gaps', 'Final', 'Action', 'Top Driver'], score_movement_rows(ranked, limit=8))}

## Insight Themes

{markdown_table(['Theme', 'Symbols', 'Why It Matters', 'Next Check'], insight_theme_table_rows) if insight_theme_table_rows else 'No insight themes found.'}

## Source Health Alerts

{markdown_table(['Severity', 'Source', 'Status', 'Records', 'Last Run', 'Latest Issue', 'Next Action'], health_alert_rows) if health_alert_rows else 'No source health alerts.'}

## Ranked Data Gap Queue

{markdown_table(['Rank', 'Symbol', 'Data Gap', 'Impact', 'Best Pull', 'Next Action'], visible_data_gap_rows) if visible_data_gap_rows else 'No high-impact data gaps found.'}
"""
    end_of_day_path.write_text(end_of_day_report)

    next_day_watchlist = f"""# Next-Day Watchlist - {now:%Y-%m-%d}

Generated: {now:%Y-%m-%d %H:%M}

Review these before the next market session. This is recommendation support only and does not place or preview trades.

{markdown_table(['Rank', 'Symbol', 'Action', 'Score', 'Current', 'Target', 'Upside', 'Data Status', 'Why'], next_day_watchlist_rows) if next_day_watchlist_rows else 'No watchlist candidates available.'}

## Top Decision Briefs

{markdown_table(['Symbol', 'Type', 'Headline', 'Why It Matters', 'Next Check'], top_decision_brief_rows[:5]) if top_decision_brief_rows else 'No decision briefs available.'}

## Trend Insights

{markdown_table(['Symbol', 'Overlay', 'Trend Insight', 'Score Movement'], trend_insight_rows(ranked, limit=8))}

## Insight Themes

{markdown_table(['Theme', 'Symbols', 'Why It Matters', 'Next Check'], insight_theme_table_rows) if insight_theme_table_rows else 'No insight themes found.'}

## What To Verify Next

{markdown_table(['Symbol', 'Type', 'Risk Or Uncertainty', 'Next Check', 'What Would Change The View'], verify_next_rows[:6]) if verify_next_rows else 'No high-priority verification checks found.'}

## Ranked Data Gap Queue

{markdown_table(['Rank', 'Symbol', 'Data Gap', 'Impact', 'Best Pull', 'Next Action'], visible_data_gap_rows) if visible_data_gap_rows else 'No high-impact data gaps found.'}

## Open Provider Checks

{markdown_table(['Severity', 'Source', 'Status', 'Records', 'Last Run', 'Latest Issue', 'Next Action'], health_alert_rows[:8]) if health_alert_rows else 'No source health alerts.'}
"""
    watchlist_path.write_text(next_day_watchlist)

    dashboard = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Trading Dashboard - {now:%Y-%m-%d}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #18202a;
      --muted: #5e6a78;
      --line: #d8dde5;
      --blue: #1d5fd0;
      --green: #137a49;
      --amber: #9a6100;
      --red: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    header {{
      background: #111827;
      color: white;
      padding: 18px 24px;
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 16px 20px 24px;
    }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: 24px; }}
    h2 {{ font-size: 17px; margin-bottom: 10px; }}
    h3 {{ font-size: 15px; }}
    p {{ margin: 8px 0; }}
    .subtle {{ color: #cbd5e1; margin-top: 6px; }}
    .summary {{
      display: grid;
      grid-template-columns: minmax(300px, 1.6fr) repeat(5, minmax(112px, 1fr));
      gap: 10px;
      margin: 14px 0;
    }}
    .metric, section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .metric strong {{
      display: block;
      font-size: 22px;
      margin-top: 4px;
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .04em;
      text-transform: uppercase;
    }}
    .thesis {{ color: var(--muted); margin-top: 10px; }}
    .tab-nav {{
      display: flex;
      gap: 8px;
      margin: 0 0 14px;
      border-bottom: 1px solid var(--line);
    }}
    .tab-button {{
      border: 1px solid transparent;
      border-bottom: 0;
      border-radius: 8px 8px 0 0;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font-weight: 800;
      padding: 10px 14px;
    }}
    .tab-button[aria-selected="true"] {{
      background: var(--panel);
      border-color: var(--line);
      color: var(--blue);
      margin-bottom: -1px;
    }}
    .tab-panel[hidden] {{
      display: none !important;
    }}
    .subtab-nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 14px;
    }}
    .subtab-button {{
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--muted);
      cursor: pointer;
      font-weight: 800;
      padding: 7px 10px;
    }}
    .subtab-button[aria-selected="true"] {{
      background: #eef4ff;
      border-color: #b7cdf8;
      color: var(--blue);
    }}
    .recommendation-subtab[hidden] {{
      display: none !important;
    }}
    section {{ margin-bottom: 14px; overflow-x: auto; }}
    .two-column {{
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(340px, .9fr);
      gap: 14px;
      align-items: start;
    }}
    .table-pair {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      align-items: start;
    }}
    .section-title {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 10px;
      margin-bottom: 10px;
    }}
    .section-title h2 {{ margin-bottom: 0; }}
    .section-note {{
      color: var(--muted);
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 7px;
      text-align: left;
      white-space: nowrap;
      font-size: 13px;
    }}
    tbody tr[hidden] {{ display: none; }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .compact-table {{
      min-width: 0;
      table-layout: auto;
    }}
    .decision-table {{
      min-width: 0;
      table-layout: fixed;
    }}
    .decision-table th:nth-child(1), .decision-table td:nth-child(1) {{ width: 42px; }}
    .decision-table th:nth-child(2), .decision-table td:nth-child(2) {{ width: 60px; }}
    .decision-table th:nth-child(3), .decision-table td:nth-child(3) {{ width: 72px; }}
    .decision-table th:nth-child(4), .decision-table td:nth-child(4) {{ width: 52px; }}
    .decision-table th:nth-child(5), .decision-table td:nth-child(5) {{ width: 112px; }}
    .decision-table th:nth-child(6), .decision-table td:nth-child(6) {{ width: 82px; }}
    .decision-table th:nth-child(7), .decision-table td:nth-child(7) {{ width: 82px; }}
    .decision-table th:nth-child(8), .decision-table td:nth-child(8) {{ width: 66px; }}
    .decision-table th:nth-child(9), .decision-table td:nth-child(9) {{ width: 78px; }}
    .decision-table th:nth-child(10), .decision-table td:nth-child(10) {{ width: 96px; }}
    .decision-table th:nth-child(11), .decision-table td:nth-child(11) {{ width: 104px; }}
    .decision-table td:last-child {{
      white-space: normal;
      color: var(--muted);
      line-height: 1.35;
    }}
    .change-badge {{
      display: inline-block;
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.15;
      white-space: normal;
    }}
    .change-new {{
      background: #eef4ff;
      border-color: #b7cdf8;
      color: var(--blue);
    }}
    .change-action {{
      background: #fff2cf;
      border-color: #e6c76f;
      color: var(--amber);
    }}
    .change-up {{
      background: #dff7ea;
      border-color: #a8dfbd;
      color: var(--green);
    }}
    .change-down {{
      background: #fde3df;
      border-color: #f4b4aa;
      color: var(--red);
    }}
    .change-none {{
      background: #f8fafc;
      color: var(--muted);
    }}
    .expandable-action-row {{
      cursor: pointer;
    }}
    .expandable-action-row:hover {{
      background: #f8fbff;
    }}
    .expandable-action-row:focus {{
      outline: 2px solid rgba(29, 95, 208, .35);
      outline-offset: -2px;
    }}
    .expandable-action-row[aria-expanded="true"] {{
      background: #f8fbff;
    }}
    .action-detail-row td {{
      white-space: normal;
      background: #f8fbff;
      padding: 0 7px 12px;
    }}
    .action-detail-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
      margin-left: 44px;
    }}
    .action-detail-card p {{
      color: var(--muted);
    }}
    .action-detail-card strong {{
      color: var(--text);
    }}
    .action-hover {{
      position: relative;
      display: inline-block;
    }}
    .action-hover:focus {{
      outline: none;
    }}
    .action-tooltip {{
      display: none;
      position: absolute;
      z-index: 10;
      top: calc(100% + 8px);
      left: 0;
      width: min(420px, 70vw);
      white-space: normal;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 16px 38px rgba(15, 23, 42, .16);
      color: var(--muted);
      padding: 10px;
      line-height: 1.35;
      text-align: left;
    }}
    .action-tooltip strong {{
      display: block;
      color: var(--text);
      margin-bottom: 5px;
    }}
    .action-tooltip span {{
      display: block;
      margin-top: 5px;
    }}
    .action-hover:hover .action-tooltip,
    .action-hover:focus .action-tooltip,
    .action-hover:focus-within .action-tooltip {{
      display: block;
    }}
    .readiness-section {{
      background: transparent;
      border: 0;
      padding: 0;
      overflow: visible;
    }}
    .readiness-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 10px;
    }}
    .readiness-card {{
      min-height: 112px;
      border: 1px solid var(--line);
      border-left-width: 4px;
      border-radius: 8px;
      background: var(--panel);
      padding: 11px;
    }}
    .readiness-card-head {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;
    }}
    .readiness-status {{
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .readiness-card strong {{
      display: block;
      font-size: 14px;
      line-height: 1.3;
    }}
    .readiness-next {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 8px;
    }}
    .readiness-ready {{
      border-left-color: var(--green);
    }}
    .readiness-ready .readiness-status {{
      background: #dff7ea;
      color: var(--green);
    }}
    .readiness-review {{
      border-left-color: var(--amber);
    }}
    .readiness-review .readiness-status {{
      background: #fff2cf;
      color: var(--amber);
    }}
    .readiness-needs-attention {{
      border-left-color: var(--red);
    }}
    .readiness-needs-attention .readiness-status {{
      background: #fde3df;
      color: var(--red);
    }}
    .score-explanation {{
      border-top: 1px solid var(--line);
      margin-top: 12px;
      padding-top: 10px;
    }}
    .score-driver-table,
    .score-signal-table,
    .target-source-table,
    .source-status-table,
    .source-issue-group-table,
    .source-health-table,
    .score-trend-table {{
      min-width: 0;
      table-layout: auto;
      margin-top: 8px;
    }}
    .score-driver-table td:last-child,
    .score-signal-table td:last-child,
    .target-source-table td:last-child,
    .source-status-table td:nth-child(5),
    .source-status-table td:nth-child(6),
    .source-status-table td:nth-child(8),
    .source-status-table td:nth-child(12),
    .source-status-table td:last-child,
    .source-issue-group-table td:nth-child(4),
    .source-issue-group-table td:last-child,
    .source-health-table td:nth-child(6),
    .source-health-table td:last-child,
    .score-trend-table td:nth-child(2),
    .score-trend-table td:last-child {{
      white-space: normal;
      color: var(--muted);
    }}
    .source-issue-group-table th:nth-child(3),
    .source-issue-group-table td:nth-child(3) {{
      text-align: right;
    }}
    .source-status-table th:nth-child(3),
    .source-status-table td:nth-child(3),
    .source-status-table th:nth-child(9),
    .source-status-table td:nth-child(9),
    .source-status-table th:nth-child(10),
    .source-status-table td:nth-child(10) {{
      text-align: right;
    }}
    .expandable-source-row {{
      cursor: pointer;
    }}
    .expandable-source-row:hover {{
      background: #f8fbff;
    }}
    .expandable-source-row:focus {{
      outline: 2px solid rgba(29, 95, 208, .35);
      outline-offset: -2px;
    }}
    .source-detail-row td {{
      white-space: normal;
      background: #f8fbff;
      padding: 0 7px 12px;
    }}
    .source-detail-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
      margin-left: 0;
    }}
    .source-record-table {{
      min-width: 0;
      table-layout: auto;
      margin-top: 8px;
    }}
    .source-record-table td:nth-child(4),
    .source-record-table td:nth-child(5),
    .source-record-table td:last-child {{
      white-space: normal;
      color: var(--muted);
    }}
    .score-signal-block {{
      border-top: 1px solid var(--line);
      margin-top: 12px;
      padding-top: 10px;
    }}
    .score-signal-block h4 {{
      margin: 0 0 8px;
      font-size: 13px;
    }}
    .signal-positive {{ color: var(--green); font-weight: 800; }}
    .signal-negative {{ color: var(--red); font-weight: 800; }}
    .signal-neutral {{ color: var(--muted); font-weight: 800; }}
    .sparkline {{
      display: inline-flex;
      align-items: flex-end;
      gap: 3px;
      min-width: 96px;
      height: 44px;
      padding: 4px 6px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
    }}
    .spark-bar {{
      display: inline-block;
      width: 8px;
      min-height: 6px;
      border-radius: 3px 3px 0 0;
      background: var(--blue);
    }}
    .sparkline-empty {{
      color: var(--muted);
      font-size: 12px;
    }}
    .research-brief {{
      border-top: 1px solid var(--line);
      margin-top: 12px;
      padding-top: 10px;
    }}
    .research-brief h4 {{
      margin: 0 0 8px;
      font-size: 13px;
    }}
    .brief-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .brief-grid div {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #fbfcfe;
    }}
    .brief-grid ul {{
      margin: 6px 0 0;
      padding-left: 18px;
    }}
    .brief-grid li {{
      color: var(--muted);
      margin-bottom: 5px;
      line-height: 1.35;
    }}
    .decision-briefs {{
      margin-bottom: 14px;
    }}
    .decision-brief-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(180px, 1fr));
      gap: 10px;
    }}
    .decision-brief-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      padding: 12px;
      min-height: 190px;
    }}
    .decision-brief-top {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;
    }}
    .decision-brief-card h3 {{
      margin: 0 0 8px;
      font-size: 15px;
      line-height: 1.25;
    }}
    .decision-brief-card p {{
      margin: 0 0 8px;
      color: var(--muted);
      line-height: 1.35;
    }}
    .insight-badge {{
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 8px;
      background: #eef4ff;
      color: var(--blue);
      font-size: 11px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .decision-insight-block {{
      border-top: 1px solid var(--line);
      margin-top: 12px;
      padding-top: 10px;
    }}
    .decision-insight-block h4 {{
      margin: 0 0 8px;
      font-size: 13px;
    }}
    .decision-insight-head {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .decision-insight-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }}
    .decision-insight-grid div {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #fbfcfe;
      color: var(--muted);
      line-height: 1.35;
    }}
    .decision-insight-grid span {{
      display: block;
      color: var(--text);
      font-weight: 800;
      margin-bottom: 4px;
    }}
    .source-drilldown {{
      border-top: 1px solid var(--line);
      margin-top: 12px;
      padding-top: 10px;
    }}
    .source-drilldown h4 {{
      margin: 10px 0 6px;
      font-size: 13px;
    }}
    .source-drilldown ul {{
      margin: 0 0 8px;
      padding-left: 18px;
    }}
    .source-drilldown li {{
      margin-bottom: 8px;
    }}
    .source-summary {{
      color: var(--muted);
      margin-top: 2px;
    }}
    .compact-table td:last-child {{
      white-space: normal;
      color: var(--muted);
    }}
    .pill {{
      display: inline-block;
      min-width: 54px;
      text-align: center;
      border-radius: 999px;
      padding: 3px 8px;
      font-weight: 700;
      font-size: 12px;
    }}
    .add, .buy, .strong-buy {{ background: #dff7ea; color: var(--green); }}
    .watch, .hold {{ background: #fff2cf; color: var(--amber); }}
    .avoid, .trim {{ background: #fde3df; color: var(--red); }}
    .notes {{
      color: var(--muted);
      padding-left: 18px;
    }}
    .allocation-row {{
      margin-bottom: 12px;
    }}
    .allocation-label {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 5px;
      color: var(--muted);
    }}
    .allocation-label strong {{ color: var(--text); }}
    .allocation-track {{
      height: 10px;
      background: #edf0f5;
      border-radius: 999px;
      overflow: hidden;
    }}
    .allocation-fill {{
      height: 100%;
      border-radius: 999px;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
      align-items: center;
    }}
    .toolbar input, .toolbar select {{
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      background: white;
      color: var(--text);
    }}
    .toolbar button {{
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 10px;
      background: #eef4ff;
      color: var(--blue);
      font-weight: 700;
      cursor: pointer;
    }}
    details {{
      max-width: none;
    }}
    summary {{
      cursor: pointer;
      color: var(--blue);
      font-weight: 700;
      list-style-position: inside;
    }}
    .full-universe {{
      padding: 0;
      border: 0;
      background: transparent;
      margin-bottom: 14px;
    }}
    .full-universe summary {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .full-universe .full-body {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-top: 0;
      border-radius: 0 0 8px 8px;
      padding: 14px;
      overflow-x: auto;
    }}
    .why-text {{
      white-space: normal;
      min-width: 240px;
      max-width: 420px;
      color: var(--muted);
    }}
    .feedback-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }}
    .feedback-grid label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .04em;
      text-transform: uppercase;
    }}
    [hidden] {{ display: none !important; }}
    .feedback-grid input, .feedback-grid select, .feedback-grid textarea {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      color: var(--text);
      font: inherit;
      font-weight: 400;
      letter-spacing: 0;
      text-transform: none;
    }}
    .feedback-grid textarea {{
      grid-column: 1 / -1;
      resize: vertical;
    }}
    .feedback-buttons {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .feedback-buttons button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #eef4ff;
      color: var(--blue);
      font-weight: 700;
      padding: 8px 10px;
      cursor: pointer;
    }}
    #feedbackCommand {{
      white-space: pre-wrap;
      background: #111827;
      color: #e5e7eb;
      border-radius: 8px;
      padding: 12px;
      overflow-x: auto;
    }}
    @media (max-width: 860px) {{
      header {{ padding: 18px; }}
      main {{ padding: 16px; }}
      .summary {{ grid-template-columns: 1fr 1fr; }}
      .summary .metric:first-child {{ grid-column: 1 / -1; }}
      .two-column, .table-pair {{ grid-template-columns: 1fr; }}
      .readiness-grid {{ grid-template-columns: 1fr; }}
      .brief-grid {{ grid-template-columns: 1fr; }}
      .decision-table th:nth-child(11), .decision-table td:nth-child(11) {{ display: none; }}
      .tab-nav {{ overflow-x: auto; }}
      .tab-button {{ white-space: nowrap; }}
      .subtab-nav {{ flex-wrap: nowrap; overflow-x: auto; }}
      .subtab-button {{ white-space: nowrap; }}
      .feedback-grid {{ grid-template-columns: 1fr; }}
      .decision-brief-grid, .decision-insight-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Stock Trading Dashboard</h1>
    <div class="subtle">Generated {now:%Y-%m-%d %H:%M} · Recommendation-only · No automated trading</div>
  </header>
  <main>
    <div class="summary">
      <div class="metric">
        <span class="label">{html.escape(next_recommendation_label.title())}</span>
        <strong>{html.escape(next_item.symbol)} · {html.escape(next_action)}</strong>
        <div class="thesis">{html.escape(next_item.company)} · {html.escape(next_item.notes)}</div>
      </div>
      <div class="metric"><span class="label">Score</span><strong>{next_buy['score']:.1f}</strong></div>
      <div class="metric"><span class="label">{html.escape(next_amount_label)}</span><strong>{fmt_money(suggested_amount)}</strong></div>
      <div class="metric"><span class="label">Blended Target</span><strong>{target_price_text(next_item, next_target)}</strong><div class="thesis">{html.escape(target_confidence_text(next_item, next_target))} confidence</div></div>
      <div class="metric"><span class="label">1Y Upside</span><strong>{target_upside_text(next_item, next_target)}</strong><div class="thesis">{html.escape(data_status_for_target(next_item, next_target))}</div></div>
      <div class="metric"><span class="label">Reliability</span><strong>{html.escape(reliability_status)}</strong><div class="thesis">Fresh {price_counts['fresh']} · fallback {price_counts['fallback']} · missing {price_counts['missing']}</div></div>
      <div class="metric"><span class="label">Source Health</span><strong>{health_summary['needs_attention']}</strong><div class="thesis">{health_summary['healthy']} healthy · {health_summary['stale']} stale · {health_summary['not_implemented']} not implemented</div></div>
      <div class="metric"><span class="label">Insight Signals</span><strong>{signal_counts['signals']}</strong><div class="thesis">{signal_counts['symbols']} symbols · active score overlay</div></div>
    </div>

    <nav class="tab-nav" aria-label="Dashboard sections">
      <button class="tab-button" type="button" role="tab" aria-selected="true" aria-controls="recommendationsTab" id="recommendationsTabButton" data-tab-target="recommendationsTab">Recommendations</button>
      <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="holdingsTab" id="holdingsTabButton" data-tab-target="holdingsTab">Current Holdings</button>
      <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="healthTrendsTab" id="healthTrendsTabButton" data-tab-target="healthTrendsTab">Health & Trends</button>
      <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="dataIngestionTab" id="dataIngestionTabButton" data-tab-target="dataIngestionTab">Data Ingestion</button>
      <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="researchSourcesTab" id="researchSourcesTabButton" data-tab-target="researchSourcesTab">Research Sources</button>
      <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="feedbackTab" id="feedbackTabButton" data-tab-target="feedbackTab">Feedback</button>
    </nav>

    <div id="recommendationsTab" class="tab-panel" role="tabpanel" aria-labelledby="recommendationsTabButton">
    <nav class="subtab-nav" aria-label="Recommendation sections">
      <button class="subtab-button" type="button" role="tab" aria-selected="true" aria-controls="actionQueueSubtab" id="actionQueueSubtabButton" data-rec-tab-target="actionQueueSubtab">Action Queue</button>
      <button class="subtab-button" type="button" role="tab" aria-selected="false" aria-controls="longTermSubtab" id="longTermSubtabButton" data-rec-tab-target="longTermSubtab">Long-Term Queue</button>
      <button class="subtab-button" type="button" role="tab" aria-selected="false" aria-controls="shortTermSubtab" id="shortTermSubtabButton" data-rec-tab-target="shortTermSubtab">Short-Term Queue</button>
      <button class="subtab-button" type="button" role="tab" aria-selected="false" aria-controls="nextDaySubtab" id="nextDaySubtabButton" data-rec-tab-target="nextDaySubtab">Next-Day Watchlist</button>
      <button class="subtab-button" type="button" role="tab" aria-selected="false" aria-controls="speculativeSubtab" id="speculativeSubtabButton" data-rec-tab-target="speculativeSubtab">Speculative AI Watchlist</button>
      <button class="subtab-button" type="button" role="tab" aria-selected="false" aria-controls="dataGapsSubtab" id="dataGapsSubtabButton" data-rec-tab-target="dataGapsSubtab">Data Gaps</button>
    </nav>

    <div id="actionQueueSubtab" class="recommendation-subtab" role="tabpanel" aria-labelledby="actionQueueSubtabButton">
      {pre_market_readiness}
      {decision_brief_cards}
      <section>
        <div class="section-title">
          <h2>Action Queue</h2>
          <span class="section-note">Hover action for quick context; click a row for score and target detail</span>
        </div>
        {action_queue_table if action_queue_rows else '<p>No Add, Watch, or Hold candidates available.</p>'}
      </section>
    </div>

    <div id="longTermSubtab" class="recommendation-subtab" role="tabpanel" aria-labelledby="longTermSubtabButton" hidden>
      <section>
        <div class="section-title">
          <h2>Long-Term Queue</h2>
          <span class="section-note">75% sleeve</span>
        </div>
        {long_term_table if long_term_rows else '<p>No long-term candidates configured.</p>'}
      </section>
    </div>

    <div id="shortTermSubtab" class="recommendation-subtab" role="tabpanel" aria-labelledby="shortTermSubtabButton" hidden>
      <section>
        <div class="section-title">
          <h2>Short-Term Queue</h2>
          <span class="section-note">Day, week, or 2-4 week trades</span>
        </div>
        {short_term_decision_table if short_term_decision_rows else '<p>No short-term candidates configured.</p>'}
      </section>
    </div>

    <div id="nextDaySubtab" class="recommendation-subtab" role="tabpanel" aria-labelledby="nextDaySubtabButton" hidden>
      <section>
        <div class="section-title">
          <h2>Next-Day Watchlist</h2>
          <span class="section-note">Top candidates to review before the next session</span>
        </div>
        {html_table(['Rank', 'Symbol', 'Action', 'Score', 'Change', 'Current', 'Target', 'Upside', 'Data Status', 'Why'], next_day_watchlist_html_rows, 'decision-table', raw_columns={4}) if next_day_watchlist_html_rows else '<p>No next-day watchlist candidates available.</p>'}
      </section>
    </div>

    <div id="speculativeSubtab" class="recommendation-subtab" role="tabpanel" aria-labelledby="speculativeSubtabButton" hidden>
      <section>
        <div class="section-title">
          <h2>Speculative AI Watchlist</h2>
          <span class="section-note">Observation only</span>
        </div>
        {speculative_table if speculative_rows else '<p>No speculative AI watchlist names configured.</p>'}
      </section>
    </div>

    <div id="dataGapsSubtab" class="recommendation-subtab" role="tabpanel" aria-labelledby="dataGapsSubtabButton" hidden>
      <section>
        <div class="section-title">
          <h2>Ranked Data Gap Queue</h2>
          <span class="section-note">{html.escape(data_gap_note)}</span>
        </div>
        {data_gap_table if data_gap_rows else '<p>No high-impact data gaps found.</p>'}
      </section>
      <section>
        <div class="section-title">
          <h2>Source Drilldowns</h2>
          <span class="section-note">Target-source and evidence counts</span>
        </div>
        {source_drilldown_table}
      </section>
    </div>

    <details class="full-universe">
      <summary>Open full ranked V1 universe and filters</summary>
      <div class="full-body">
        <div class="toolbar">
          <input id="tickerFilter" type="search" placeholder="Filter ticker or company">
          <select id="sleeveFilter">
            <option value="">All sleeves</option>
            <option value="long_term">Long term</option>
            <option value="short_term">Short term</option>
            <option value="speculative_ai">Speculative AI</option>
            <option value="etf">ETF</option>
          </select>
          <select id="actionFilter">
            <option value="">All actions</option>
            <option value="Add">Add</option>
            <option value="Watch">Watch</option>
            <option value="Avoid">Avoid</option>
            <option value="Hold">Hold</option>
          </select>
          <button type="button" id="sortScore">Sort by score</button>
        </div>
        {html_score_table}
      </div>
    </details>

    <section>
      <h2>Notes</h2>
      <ul class="notes">
        <li>This dashboard is decision support, not automated trading.</li>
        <li>Rows marked Needs refresh require updated market data and target-price inputs before acting.</li>
        <li>The 10% single-stock cap is applied to the suggested purchase amount.</li>
      </ul>
    </section>
    </div>

    <div id="holdingsTab" class="tab-panel" role="tabpanel" aria-labelledby="holdingsTabButton" hidden>
      <div class="two-column">
        <section>
          <div class="section-title">
            <h2>Current Holdings Used</h2>
            <span class="section-note">Latest E*TRADE snapshot or manual fallback</span>
          </div>
          {html_table(['Symbol', 'Source', 'Qty', 'Last', 'Market Value', 'Portfolio %'], holdings_rows, 'compact-table') if holdings_rows else '<p>No holdings found. Add an E*TRADE snapshot or manual positions.</p>'}
        </section>

        <section>
          <div class="section-title">
            <h2>Holdings Allocation</h2>
            <span class="section-note">10% cap check</span>
          </div>
          {''.join(allocation_bars) if allocation_bars else '<p>No allocation data available yet.</p>'}
        </section>
      </div>
    </div>

    <div id="healthTrendsTab" class="tab-panel" role="tabpanel" aria-labelledby="healthTrendsTabButton" hidden>
      <section>
        <div class="section-title">
          <h2>Report Reliability</h2>
          <span class="section-note">Run {workflow_run_id_from_env() or 'direct'} · recommendation run {db_run_id}</span>
        </div>
        <p><strong>Status:</strong> {html.escape(reliability_status)}. <strong>Latest successful provider refresh:</strong> {html.escape(latest_refresh)}.</p>
        {html_table(['Fresh Prices', 'Fallback Prices', 'Stale Prices', 'Manual Prices', 'Missing Prices', 'Top Blocker'], [[price_counts['fresh'], price_counts['fallback'], price_counts['stale'], price_counts['manual'], price_counts['missing'], top_health_alert[1] if top_health_alert else 'None']], 'compact-table')}
      </section>
      <section>
        <div class="section-title">
          <h2>Source Issue Groups</h2>
          <span class="section-note">Grouped root causes; detailed alerts remain below</span>
        </div>
        {source_issue_group_table if health_alert_rows else '<p>No source issue groups.</p>'}
      </section>
      <section>
        <div class="section-title">
          <h2>Insight Themes</h2>
          <span class="section-note">Common decision patterns across the ranked universe</span>
        </div>
        {insight_theme_table if insight_theme_table_rows else '<p>No insight themes found.</p>'}
      </section>
      <div class="table-pair">
        <section>
          <div class="section-title">
            <h2>Source Health Alerts</h2>
            <span class="section-note">{len(health_alert_rows)} active alert(s)</span>
          </div>
          {f'<p><strong>Top blocker:</strong> {html.escape(str(top_health_alert[1]))} - {html.escape(str(top_health_alert[5]))}</p>' if top_health_alert else '<p>No active source blockers.</p>'}
          {health_alert_table if health_alert_rows else '<p>No source health alerts.</p>'}
        </section>

        <section>
          <div class="section-title">
            <h2>Score Changes</h2>
            <span class="section-note">Changes of 1 point or more</span>
          </div>
          {html_table(['Symbol', 'Previous', 'Latest', 'Change', 'Previous Action', 'Latest Action', 'Data Status'], score_change_rows[:12], 'compact-table') if score_change_rows else '<p>No score changes of 1 point or more since the previous stored run.</p>'}
        </section>
      </div>
      <section>
        <div class="section-title">
          <h2>Score Movement</h2>
          <span class="section-note">Base score plus transparent V1.6 signal overlay</span>
        </div>
        {score_movement_table}
      </section>
      <section>
        <div class="section-title">
          <h2>Trend Insights</h2>
          <span class="section-note">Score, price trend, and data-gap context</span>
        </div>
        {trend_insight_table}
      </section>
      <section>
        <div class="section-title">
          <h2>Historical Score Trend</h2>
          <span class="section-note">Stored from each generated report run</span>
        </div>
        {score_trend_table}
      </section>
    </div>

    <div id="dataIngestionTab" class="tab-panel" role="tabpanel" aria-labelledby="dataIngestionTabButton" hidden>
      <section>
        <div class="section-title">
          <h2>Data Ingestion & Signal Health</h2>
          <span class="section-note">Free-first raw + curated ingestion status</span>
        </div>
        <p class="section-note">Raw payload rows are retained for audit and future synthesis. Curated records are normalized into evidence, targets, prices, and active insight signals.</p>
        {html_table(['Source', 'Tier', 'Category', 'Free/Paid', 'Status', 'Raw Payloads', 'Curated Records', 'Last Run', 'Latest Issue', 'Next Action'], data_ingestion_rows, 'source-status-table')}
      </section>
      <section>
        <div class="section-title">
          <h2>Paid Provider Watchlist</h2>
          <span class="section-note">Track cost before buying anything</span>
        </div>
        {html_table(['Provider', 'Known Pricing', 'What It Unlocks', 'V1.6 Decision'], paid_provider_rows, 'compact-table')}
      </section>
      <section>
        <div class="section-title">
          <h2>Insight Signal Health</h2>
          <span class="section-note">Active deterministic scoring overlay</span>
        </div>
        {html_table(['Signal Type', 'Signals', 'Symbols', 'Total Delta', 'Latest Update', 'Mode'], signal_health_rows, 'compact-table') if signal_health_rows else '<p>No active insight signals captured yet.</p>'}
      </section>
    </div>

    <div id="feedbackTab" class="tab-panel" role="tabpanel" aria-labelledby="feedbackTabButton" hidden>
    <section>
      <h2>Feedback</h2>
      <div class="feedback-grid">
        <label>
          Feedback target
          <select id="feedbackKind">
            <option value="recommendation">Recommendation</option>
            <option value="source">Research source</option>
          </select>
        </label>
        <label id="feedbackSymbolWrap">
          Symbol
          <input id="feedbackSymbol" type="text" placeholder="{html.escape(next_item.symbol)}">
        </label>
        <label id="feedbackSourceWrap" hidden>
          Source
          <select id="feedbackSource">
            {''.join(source_options)}
          </select>
        </label>
        <label>
          Details
          <textarea id="feedbackNotes" rows="4" placeholder="What should the engine learn from your review?"></textarea>
        </label>
      </div>
      <div class="feedback-buttons">
        <button type="button" data-kind="recommendation" data-feedback="agree">Agree</button>
        <button type="button" data-kind="recommendation" data-feedback="disagree">Disagree</button>
        <button type="button" data-kind="recommendation" data-feedback="too_risky">Too risky</button>
        <button type="button" data-kind="source" data-feedback="useful_source" hidden>Useful source</button>
        <button type="button" data-kind="source" data-feedback="noisy_source" hidden>Noisy source</button>
      </div>
      <pre id="feedbackCommand">Choose feedback to generate a local save command.</pre>
    </section>
    </div>

    <div id="researchSourcesTab" class="tab-panel" role="tabpanel" aria-labelledby="researchSourcesTabButton" hidden>
      <section>
        <div class="section-title">
          <h2>Research Sources</h2>
          <span class="section-note">Implementation, health, and weighting</span>
        </div>
        <p class="section-note">This table shows which sources are actually wired into the engine, how much data has been captured, when they last ran, and what to build next.</p>
        {expandable_source_table(source_rows) if source_rows else '<p>No research sources configured.</p>'}
      </section>
    </div>
  </main>
  <script>
    const tabButtons = document.querySelectorAll('[data-tab-target]');
    const tabPanels = document.querySelectorAll('.tab-panel');

    function activateTab(targetId) {{
      tabButtons.forEach(button => {{
        button.setAttribute('aria-selected', String(button.dataset.tabTarget === targetId));
      }});
      tabPanels.forEach(panel => {{
        panel.hidden = panel.id !== targetId;
      }});
    }}

    tabButtons.forEach(button => {{
      button.addEventListener('click', () => activateTab(button.dataset.tabTarget));
    }});

    const recommendationTabButtons = document.querySelectorAll('[data-rec-tab-target]');
    const recommendationTabPanels = document.querySelectorAll('.recommendation-subtab');

    function activateRecommendationTab(targetId) {{
      recommendationTabButtons.forEach(button => {{
        button.setAttribute('aria-selected', String(button.dataset.recTabTarget === targetId));
      }});
      recommendationTabPanels.forEach(panel => {{
        panel.hidden = panel.id !== targetId;
      }});
    }}

    recommendationTabButtons.forEach(button => {{
      button.addEventListener('click', () => activateRecommendationTab(button.dataset.recTabTarget));
    }});

    function toggleActionRow(row) {{
      const detailId = row.getAttribute('aria-controls');
      const detailRow = document.getElementById(detailId);
      if (!detailRow) return;
      const expanded = row.getAttribute('aria-expanded') === 'true';
      row.setAttribute('aria-expanded', String(!expanded));
      detailRow.hidden = expanded;
    }}

    document.querySelectorAll('.expandable-action-row').forEach(row => {{
      row.addEventListener('click', () => toggleActionRow(row));
      row.addEventListener('keydown', event => {{
        if (event.key === 'Enter' || event.key === ' ') {{
          event.preventDefault();
          toggleActionRow(row);
        }}
      }});
    }});

    document.querySelectorAll('.expandable-source-row').forEach(row => {{
      row.addEventListener('click', () => toggleActionRow(row));
      row.addEventListener('keydown', event => {{
        if (event.key === 'Enter' || event.key === ' ') {{
          event.preventDefault();
          toggleActionRow(row);
        }}
      }});
    }});

    const table = document.querySelector('.rank-table tbody');
    const tickerFilter = document.getElementById('tickerFilter');
    const sleeveFilter = document.getElementById('sleeveFilter');
    const actionFilter = document.getElementById('actionFilter');
    const sortScore = document.getElementById('sortScore');

    function cellText(row, index) {{
      return row.children[index]?.textContent.trim() || '';
    }}

    function applyFilters() {{
      const query = tickerFilter.value.trim().toLowerCase();
      const sleeve = sleeveFilter.value;
      const action = actionFilter.value;
      for (const row of table.rows) {{
        const haystack = `${{cellText(row, 1)}} ${{cellText(row, 2)}}`.toLowerCase();
        const rowSleeve = cellText(row, 3);
        const rowAction = cellText(row, 5);
        const visible = (!query || haystack.includes(query))
          && (!sleeve || rowSleeve === sleeve)
          && (!action || rowAction === action);
        row.hidden = !visible;
      }}
    }}

    function renumberVisibleRows() {{
      let rank = 1;
      for (const row of table.rows) {{
        if (!row.hidden) {{
          row.children[0].textContent = rank;
          rank += 1;
        }}
      }}
    }}

    tickerFilter.addEventListener('input', () => {{ applyFilters(); renumberVisibleRows(); }});
    sleeveFilter.addEventListener('change', () => {{ applyFilters(); renumberVisibleRows(); }});
    actionFilter.addEventListener('change', () => {{ applyFilters(); renumberVisibleRows(); }});
    sortScore.addEventListener('click', () => {{
      const rows = Array.from(table.rows);
      rows.sort((a, b) => Number(cellText(b, 6)) - Number(cellText(a, 6)));
      rows.forEach(row => table.appendChild(row));
      applyFilters();
      renumberVisibleRows();
    }});

    const feedbackKind = document.getElementById('feedbackKind');
    const feedbackSymbolWrap = document.getElementById('feedbackSymbolWrap');
    const feedbackSourceWrap = document.getElementById('feedbackSourceWrap');
    const feedbackSymbol = document.getElementById('feedbackSymbol');
    const feedbackSource = document.getElementById('feedbackSource');
    const feedbackNotes = document.getElementById('feedbackNotes');
    const feedbackCommand = document.getElementById('feedbackCommand');

    function shellQuote(value) {{
      return `'${{String(value).replaceAll("'", "'\\\\''")}}'`;
    }}

    function updateFeedbackMode() {{
      const isSource = feedbackKind.value === 'source';
      feedbackSymbolWrap.hidden = isSource;
      feedbackSourceWrap.hidden = !isSource;
      document.querySelectorAll('[data-feedback]').forEach(button => {{
        button.hidden = button.dataset.kind !== feedbackKind.value;
      }});
    }}

    function buildFeedbackCommand(type) {{
      const notes = feedbackNotes.value.trim();
      if (feedbackKind.value === 'source') {{
        const delta = type === 'useful_source' ? '0.1' : type === 'noisy_source' ? '-0.1' : '0';
        return `python3 scripts/add_feedback.py source ${{shellQuote(feedbackSource.value)}} --type ${{shellQuote(type)}} --delta ${{delta}} --notes ${{shellQuote(notes)}}`;
      }}
      const symbol = feedbackSymbol.value.trim().toUpperCase() || '{html.escape(next_item.symbol)}';
      return `python3 scripts/add_feedback.py recommendation ${{shellQuote(symbol)}} --report-date {now:%Y-%m-%d} --type ${{shellQuote(type)}} --notes ${{shellQuote(notes)}}`;
    }}

    feedbackKind.addEventListener('change', updateFeedbackMode);
    updateFeedbackMode();
    document.querySelectorAll('[data-feedback]').forEach(button => {{
      button.addEventListener('click', () => {{
        feedbackCommand.textContent = buildFeedbackCommand(button.dataset.feedback);
      }});
    }});
  </script>
</body>
</html>
"""
    dashboard_path.write_text(dashboard)
    email_config = targets.get("email_reports", {})
    recipient = email_config.get("recipient", "") if isinstance(email_config, dict) else ""
    subject = f"Stock Trading Daily Report - {now:%Y-%m-%d}"
    email_summary = f"""To: {recipient}
Subject: {subject}

Daily stock trading summary for {now:%Y-%m-%d}

{next_recommendation_label}: {next_item.symbol} - {next_item.company}
Action: {next_action}
Score: {next_buy['score']:.1f}/100
{next_amount_label}: {fmt_money(suggested_amount)}
Current price: {fmt_money(next_item.current_price) if next_item.current_price else 'Needs refresh'}
Blended target: {target_price_text(next_item, next_target)}
One-year upside: {target_upside_text(next_item, next_target)}
Confidence: {target_confidence_text(next_item, next_target)}
Source health: {health_summary['healthy']} healthy / {health_summary['needs_attention']} needs attention / {health_summary['stale']} stale
Report reliability: {reliability_status}
Latest successful provider refresh: {latest_refresh}
Workflow run: {workflow_run_id_from_env() or 'direct report run'}
Recommendation run: {db_run_id}

Reason:
{next_item.notes}

Top source blocker:
{f"{top_health_alert[1]} ({top_health_alert[2]}): {top_health_alert[5]}" if top_health_alert else "No active source blockers."}

Dashboard:
{dashboard_path}

CSV export:
{csv_path}

End-of-day review:
{end_of_day_path}

Next-day watchlist:
{watchlist_path}

Report context:
{report_context_path}

Note: This is a generated decision-support summary. It does not place trades.
"""
    email_path.write_text(email_summary)
    return [report_path, dashboard_path, csv_path, email_path, end_of_day_path, watchlist_path, report_context_path]


def main() -> int:
    maybe_refresh_market_data(sys.argv[1:])
    for report_path in generate_report():
        print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
