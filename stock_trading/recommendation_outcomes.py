"""Review-only recommendation outcome tracking."""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping

from stock_trading.storage.provider_repository import price_history_for_symbols
from stock_trading.storage.recommendation_repository import recommendation_score_history


OUTCOME_WINDOWS = (1, 5, 20, 60)
BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}
REVIEW_ONLY_NOTE = (
    "Review-only outcome tracking. These metrics must not automatically change scores, "
    "actions, targets, source weights, decision safety, allocations, broker behavior, or trading."
)


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def parse_date(value: object) -> date | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw, raw[:10]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def normalized_history(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen_dates: set[str] = set()
    for row in rows:
        price_date = text(row.get("price_date") or row.get("date"))
        close = to_float(row.get("adjusted_close")) or to_float(row.get("close"))
        if not price_date or close <= 0 or price_date in seen_dates:
            continue
        seen_dates.add(price_date)
        normalized.append(
            {
                "price_date": price_date,
                "close": close,
                "provider": text(row.get("provider")),
            }
        )
    normalized.sort(key=lambda row: text(row["price_date"]))
    return normalized


def prices_after_report(
    history: list[dict[str, object]],
    report_date: str,
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    anchor = parse_date(report_date)
    if not anchor:
        return None, []
    later = [row for row in history if (parse_date(row.get("price_date")) or date.min) > anchor]
    anchor_rows = [row for row in history if (parse_date(row.get("price_date")) or date.min) <= anchor]
    return (anchor_rows[-1] if anchor_rows else None), later


def target_progress(
    original_current_price: float,
    original_target: float,
    later_price: float,
) -> float | None:
    target_distance = original_target - original_current_price
    if original_current_price <= 0 or original_target <= 0 or abs(target_distance) < 0.000001:
        return None
    return ((later_price - original_current_price) / target_distance) * 100


def outcome_status(
    action: str,
    percent_change: float | None,
    progress: float | None,
    decision_gate_status: str = "",
) -> str:
    if percent_change is None:
        return "not_enough_history"
    if progress is not None and progress >= 50:
        return "target_progress"
    if percent_change <= -8:
        return "drawdown_warning"
    if abs(percent_change) < 1:
        return "flat"
    if action in BUY_ACTIONS:
        return "positive_follow_through" if percent_change > 0 else "negative_follow_through"
    if text(decision_gate_status).lower() == "blocked":
        return "negative_follow_through" if percent_change < -1 else "flat"
    return "positive_follow_through" if percent_change > 1 else "negative_follow_through"


def recommendation_outcome_rows(
    recommendations: Iterable[Mapping[str, object]],
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]],
    windows: Iterable[int] = OUTCOME_WINDOWS,
) -> list[dict[str, object]]:
    """Calculate deterministic review-only outcomes for stored recommendation rows."""

    rows: list[dict[str, object]] = []
    for rec in recommendations:
        symbol = text(rec.get("symbol")).upper()
        report_date = text(rec.get("report_date"))
        action = text(rec.get("action"))
        original_current = to_float(rec.get("current_price"))
        original_target = to_float(rec.get("target_price"))
        history = normalized_history(price_history_by_symbol.get(symbol, []))
        anchor_row, later_rows = prices_after_report(history, report_date)
        if original_current <= 0 and anchor_row:
            original_current = to_float(anchor_row.get("close"))
        decision_gate_status = text(rec.get("decision_gate_status") or rec.get("decision_safety_status"))
        decision_gate_reasons = rec.get("decision_gate_reasons") or rec.get("decision_safety_reasons") or []
        if isinstance(decision_gate_reasons, str):
            decision_gate_reasons = [decision_gate_reasons] if decision_gate_reasons else []
        for window in windows:
            later_row = later_rows[window - 1] if len(later_rows) >= window else None
            later_price = to_float(later_row.get("close")) if later_row else None
            percent_change = (
                ((later_price - original_current) / original_current) * 100
                if later_price is not None and original_current > 0
                else None
            )
            progress = (
                target_progress(original_current, original_target, later_price)
                if later_price is not None
                else None
            )
            rows.append(
                {
                    "symbol": symbol,
                    "report_date": report_date,
                    "window_trading_days": int(window),
                    "original_action": action,
                    "original_score": to_float(rec.get("score")),
                    "original_target": original_target,
                    "original_current_price": original_current,
                    "later_price_date": text(later_row.get("price_date")) if later_row else "",
                    "later_price": later_price,
                    "percent_change": round(percent_change, 4) if percent_change is not None else None,
                    "target_progress": round(progress, 4) if progress is not None else None,
                    "decision_gate_status": decision_gate_status,
                    "decision_gate_reasons": list(decision_gate_reasons) if isinstance(decision_gate_reasons, list) else [],
                    "outcome_status": outcome_status(action, percent_change, progress, decision_gate_status),
                    "review_only": True,
                    "notes": REVIEW_ONLY_NOTE,
                }
            )
    rows.sort(key=lambda row: (text(row["report_date"]), text(row["symbol"]), int(row["window_trading_days"])))
    return rows


def build_recommendation_outcome_review(
    limit: int = 500,
    windows: Iterable[int] = OUTCOME_WINDOWS,
) -> dict[str, object]:
    recommendations = recommendation_score_history(limit=limit)
    symbols = sorted({text(row.get("symbol")).upper() for row in recommendations if row.get("symbol")})
    history = price_history_for_symbols(symbols)
    rows = recommendation_outcome_rows(recommendations, history, windows)
    return {
        "metadata": {
            "review_only": True,
            "windows": list(windows),
            "recommendation_count": len(recommendations),
            "outcome_count": len(rows),
            "notes": REVIEW_ONLY_NOTE,
        },
        "outcomes": rows,
    }
