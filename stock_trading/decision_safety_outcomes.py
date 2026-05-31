"""Review-only decision-safety effectiveness analysis."""

from __future__ import annotations

from typing import Iterable, Mapping

from stock_trading.recommendation_outcomes import (
    OUTCOME_WINDOWS,
    REVIEW_ONLY_NOTE,
    BUY_ACTIONS,
    recommendation_outcome_rows,
    text,
    to_float,
)
from stock_trading.storage.provider_repository import price_history_for_symbols
from stock_trading.storage.recommendation_repository import recommendation_score_history


EFFECTIVENESS_NOTE = (
    "Review-only decision-safety effectiveness metrics. These results must not "
    "automatically change scores, actions, recommendation labels, targets, "
    "decision-safety rules, allocation, source weights, broker behavior, or trading."
)


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value else []
    return []


def boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return text(value).lower() in {"1", "true", "yes", "ready", "safe"}


def blocked_reasons(rec: Mapping[str, object], outcome: Mapping[str, object]) -> list[str]:
    raw = (
        rec.get("blocked_reasons")
        or rec.get("decision_gate_reasons")
        or rec.get("decision_safety_reasons")
        or outcome.get("decision_gate_reasons")
        or []
    )
    return [text(reason) for reason in as_list(raw) if text(reason)]


def decision_gate_status(rec: Mapping[str, object], outcome: Mapping[str, object]) -> str:
    raw = (
        rec.get("decision_gate_status")
        or rec.get("decision_safety_status")
        or outcome.get("decision_gate_status")
        or ""
    )
    if boolish(rec.get("safe_to_buy")):
        return "Ready"
    return text(raw)


def candidate_action(rec: Mapping[str, object], outcome: Mapping[str, object]) -> str:
    return text(
        rec.get("candidate_action")
        or rec.get("decision_candidate_action")
        or outcome.get("original_action")
        or rec.get("action")
    )


def is_top_ranked(rec: Mapping[str, object]) -> bool:
    if boolish(rec.get("top_ranked")) or boolish(rec.get("is_top_ranked")):
        return True
    rank = to_float(rec.get("rank") or rec.get("priority_rank"), 0)
    return rank == 1


def is_watchlist_block(rec: Mapping[str, object], reasons: Iterable[str]) -> bool:
    if boolish(rec.get("watchlist_only_blocked")):
        return True
    policy = rec.get("watchlist_policy")
    if isinstance(policy, Mapping) and boolish(policy.get("blocked")):
        return True
    reason_text = " ".join(reasons).lower()
    return "watchlist" in reason_text or "watchlist-only" in reason_text


def review_bucket(
    rec: Mapping[str, object],
    status: str,
    action: str,
    reasons: list[str],
) -> str:
    if is_watchlist_block(rec, reasons):
        return "watchlist_only_blocked"
    if status.lower() == "blocked" and is_top_ranked(rec):
        return "top_ranked_blocked"
    if status.lower() == "blocked" and action in BUY_ACTIONS:
        return "blocked_buy_candidate"
    if status.lower() == "ready":
        return "decision_safe_candidate"
    if status.lower() == "blocked":
        return "blocked_candidate"
    return "unclassified"


def later_price_assessment(
    status: str,
    percent_change: float | None,
    outcome_status: str,
) -> tuple[bool, bool, bool, str]:
    if percent_change is None or outcome_status == "not_enough_history":
        return False, False, True, "Not enough price history to judge decision-safety outcome."
    blocked = status.lower() == "blocked"
    if blocked and (percent_change < -1 or outcome_status in {"negative_follow_through", "drawdown_warning"}):
        return True, False, False, "Block likely avoided downside risk."
    if blocked and (percent_change > 1 or outcome_status == "target_progress"):
        return False, True, False, "Block may have missed upside."
    if not blocked and (percent_change > 1 or outcome_status == "target_progress"):
        return False, False, False, "Ready candidate later rose."
    if not blocked and (percent_change < -1 or outcome_status in {"negative_follow_through", "drawdown_warning"}):
        return False, False, False, "Ready candidate later declined."
    return False, False, False, "Later price movement was flat or inconclusive."


def decision_safety_effectiveness_rows(
    recommendations: Iterable[Mapping[str, object]],
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]],
    windows: Iterable[int] = (20,),
) -> list[dict[str, object]]:
    """Compare decision-safe and blocked candidates against later price moves."""

    recs = [dict(rec) for rec in recommendations]
    outcome_rows = recommendation_outcome_rows(recs, price_history_by_symbol, windows)
    rec_lookup = {
        (
            text(rec.get("report_date")),
            text(rec.get("symbol")).upper(),
            text(rec.get("action")),
        ): rec
        for rec in recs
    }
    rows: list[dict[str, object]] = []
    for outcome in outcome_rows:
        key = (
            text(outcome.get("report_date")),
            text(outcome.get("symbol")).upper(),
            text(outcome.get("original_action")),
        )
        rec = rec_lookup.get(key, {})
        status = decision_gate_status(rec, outcome)
        reasons = blocked_reasons(rec, outcome)
        action = candidate_action(rec, outcome)
        percent_change = outcome.get("percent_change")
        numeric_change = percent_change if isinstance(percent_change, (int, float)) else None
        avoided_risk, missed_upside, not_enough_history, assessment = later_price_assessment(
            status,
            numeric_change,
            text(outcome.get("outcome_status")),
        )
        rows.append(
            {
                "symbol": text(outcome.get("symbol")).upper(),
                "report_date": text(outcome.get("report_date")),
                "window_trading_days": int(to_float(outcome.get("window_trading_days"), 0)),
                "candidate_action": action,
                "recorded_action": text(outcome.get("original_action")),
                "decision_gate_status": status,
                "blocked_reasons": reasons,
                "review_bucket": review_bucket(rec, status, action, reasons),
                "later_price_date": text(outcome.get("later_price_date")),
                "later_price": outcome.get("later_price"),
                "later_price_movement_pct": numeric_change,
                "outcome_status": text(outcome.get("outcome_status")),
                "block_likely_avoided_risk": avoided_risk,
                "block_may_have_missed_upside": missed_upside,
                "not_enough_history": not_enough_history,
                "assessment": assessment,
                "review_only": True,
                "notes": EFFECTIVENESS_NOTE,
            }
        )
    rows.sort(
        key=lambda row: (
            text(row["report_date"]),
            text(row["symbol"]),
            int(to_float(row["window_trading_days"])),
        )
    )
    return rows


def summarize_effectiveness(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    summary = {
        "review_only": True,
        "row_count": 0,
        "decision_safe_candidates": 0,
        "blocked_buy_candidates": 0,
        "top_ranked_blocked_candidates": 0,
        "watchlist_only_blocked_candidates": 0,
        "blocks_likely_avoided_risk": 0,
        "blocks_may_have_missed_upside": 0,
        "not_enough_history": 0,
        "notes": EFFECTIVENESS_NOTE,
    }
    for row in rows:
        summary["row_count"] += 1
        bucket = text(row.get("review_bucket"))
        if bucket == "decision_safe_candidate":
            summary["decision_safe_candidates"] += 1
        elif bucket == "blocked_buy_candidate":
            summary["blocked_buy_candidates"] += 1
        elif bucket == "top_ranked_blocked":
            summary["top_ranked_blocked_candidates"] += 1
        elif bucket == "watchlist_only_blocked":
            summary["watchlist_only_blocked_candidates"] += 1
        if bool(row.get("block_likely_avoided_risk")):
            summary["blocks_likely_avoided_risk"] += 1
        if bool(row.get("block_may_have_missed_upside")):
            summary["blocks_may_have_missed_upside"] += 1
        if bool(row.get("not_enough_history")):
            summary["not_enough_history"] += 1
    return summary


def build_decision_safety_effectiveness_review(
    limit: int = 500,
    windows: Iterable[int] = OUTCOME_WINDOWS,
) -> dict[str, object]:
    recommendations = recommendation_score_history(limit=limit)
    symbols = sorted({text(row.get("symbol")).upper() for row in recommendations if row.get("symbol")})
    history = price_history_for_symbols(symbols)
    rows = decision_safety_effectiveness_rows(recommendations, history, windows)
    return {
        "metadata": {
            "review_only": True,
            "windows": list(windows),
            "recommendation_count": len(recommendations),
            "effectiveness_row_count": len(rows),
            "notes": f"{EFFECTIVENESS_NOTE} {REVIEW_ONLY_NOTE}",
        },
        "summary": summarize_effectiveness(rows),
        "rows": rows,
    }


__all__ = [
    "EFFECTIVENESS_NOTE",
    "build_decision_safety_effectiveness_review",
    "decision_safety_effectiveness_rows",
    "summarize_effectiveness",
]
