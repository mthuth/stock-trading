"""Review-only tactical setup outcome tracking.

The functions in this module evaluate tactical setup rows against later price
history. They do not change recommendations, tune models, call providers,
write broker data, preview orders, or execute trades.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping


OUTCOME_WINDOWS = (1, 5, 20, 60)
OUTCOME_STATUSES = {
    "not_enough_history",
    "positive_follow_through",
    "negative_follow_through",
    "flat",
    "invalidated",
    "volatile_inconclusive",
    "favorable_but_choppy",
}
TACTICAL_SELL_REVIEW_ACTIONS = {"tactical_sell_review", "sell_review", "tactical sell review"}
REVIEW_ONLY_NOTE = (
    "Review-only tactical outcome tracking. These metrics must not automatically "
    "change scores, actions, targets, decision safety, allocations, source weights, "
    "provider behavior, broker behavior, or trading."
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    seen: set[str] = set()
    for row in rows:
        price_date = text(row.get("price_date") or row.get("date"))
        close = to_float(row.get("adjusted_close")) or to_float(row.get("close"))
        if not price_date or close <= 0 or price_date in seen:
            continue
        high = to_float(row.get("high"), close) or close
        low = to_float(row.get("low"), close) or close
        normalized.append(
            {
                "price_date": price_date,
                "close": close,
                "high": max(high, close),
                "low": min(low, close),
                "provider": text(row.get("provider")),
            }
        )
        seen.add(price_date)
    normalized.sort(key=lambda row: text(row["price_date"]))
    return normalized


def setup_date(setup: Mapping[str, object]) -> str:
    return text(setup.get("setup_date") or setup.get("report_date") or setup.get("date"))


def prices_after_setup(
    history: list[dict[str, object]],
    raw_setup_date: str,
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    anchor = parse_date(raw_setup_date)
    if not anchor:
        return None, []
    anchor_rows = [row for row in history if (parse_date(row.get("price_date")) or date.min) <= anchor]
    later_rows = [row for row in history if (parse_date(row.get("price_date")) or date.min) > anchor]
    return (anchor_rows[-1] if anchor_rows else None), later_rows


def review_direction(review_action: object) -> int:
    """Return 1 for upside-favorable setups and -1 for tactical sell reviews."""

    normalized = text(review_action).lower().replace("-", "_").replace(" ", "_")
    return -1 if normalized in TACTICAL_SELL_REVIEW_ACTIONS else 1


def percent_change(original_price: float, later_price: float | None) -> float | None:
    if later_price is None or original_price <= 0:
        return None
    return ((later_price - original_price) / original_price) * 100


def movement_extremes(
    rows: list[dict[str, object]],
    original_price: float,
    direction: int,
) -> tuple[float | None, float | None]:
    if not rows or original_price <= 0:
        return None, None
    if direction >= 0:
        favorable = max(((to_float(row.get("high")) - original_price) / original_price) * 100 for row in rows)
        adverse = min(((to_float(row.get("low")) - original_price) / original_price) * 100 for row in rows)
    else:
        favorable = max(((original_price - to_float(row.get("low"))) / original_price) * 100 for row in rows)
        adverse = min(((original_price - to_float(row.get("high"))) / original_price) * 100 for row in rows)
    return round(favorable, 4), round(adverse, 4)


def invalidation_hit(
    rows: list[dict[str, object]],
    invalidation_price: float,
    direction: int,
) -> bool:
    if not rows or invalidation_price <= 0:
        return False
    if direction >= 0:
        return any(to_float(row.get("low")) <= invalidation_price for row in rows)
    return any(to_float(row.get("high")) >= invalidation_price for row in rows)


def outcome_status(
    directional_return_pct: float | None,
    max_favorable_move_pct: float | None,
    max_adverse_move_pct: float | None,
    invalidated: bool,
    *,
    flat_threshold_pct: float = 1.0,
    follow_through_threshold_pct: float = 2.0,
    volatility_threshold_pct: float = 3.0,
) -> str:
    if directional_return_pct is None:
        return "not_enough_history"
    if invalidated:
        return "invalidated"
    favorable = max_favorable_move_pct or 0.0
    adverse = max_adverse_move_pct or 0.0
    choppy = favorable >= volatility_threshold_pct and adverse <= -volatility_threshold_pct
    if choppy and directional_return_pct >= follow_through_threshold_pct:
        return "favorable_but_choppy"
    if choppy:
        return "volatile_inconclusive"
    if abs(directional_return_pct) < flat_threshold_pct:
        return "flat"
    if directional_return_pct >= follow_through_threshold_pct:
        return "positive_follow_through"
    if directional_return_pct <= -follow_through_threshold_pct:
        return "negative_follow_through"
    return "flat"


def tactical_outcome_rows(
    setups: Iterable[Mapping[str, object]],
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]],
    windows: Iterable[int] = OUTCOME_WINDOWS,
) -> list[dict[str, object]]:
    """Calculate deterministic review-only outcomes for tactical setup rows."""

    rows: list[dict[str, object]] = []
    for setup in setups:
        symbol = text(setup.get("symbol")).upper()
        raw_setup_date = setup_date(setup)
        setup_label = text(setup.get("setup_label"))
        tactical_horizon = text(setup.get("tactical_horizon"))
        review_action = text(setup.get("review_action"))
        setup_confidence = text(setup.get("setup_confidence") or setup.get("confidence"))
        direction = review_direction(review_action)
        history = normalized_history(price_history_by_symbol.get(symbol, []))
        anchor_row, later_rows = prices_after_setup(history, raw_setup_date)
        original_price = to_float(setup.get("original_price") or setup.get("current_price"))
        if original_price <= 0 and anchor_row:
            original_price = to_float(anchor_row.get("close"))
        invalidation_price = to_float(setup.get("invalidation_price") or setup.get("risk_zone_price"))

        for window in windows:
            window_int = int(window)
            window_rows = later_rows[:window_int]
            later_row = later_rows[window_int - 1] if len(later_rows) >= window_int else None
            later_price = to_float(later_row.get("close")) if later_row else None
            raw_return = percent_change(original_price, later_price)
            directional_return = raw_return * direction if raw_return is not None else None
            max_favorable, max_adverse = movement_extremes(window_rows, original_price, direction)
            invalidated = invalidation_hit(window_rows, invalidation_price, direction)
            status = outcome_status(directional_return, max_favorable, max_adverse, invalidated)
            rows.append(
                {
                    "symbol": symbol,
                    "setup_date": raw_setup_date,
                    "report_date": text(setup.get("report_date") or raw_setup_date),
                    "window_trading_days": window_int,
                    "setup_label": setup_label,
                    "tactical_horizon": tactical_horizon,
                    "review_action": review_action,
                    "setup_confidence": setup_confidence,
                    "original_price": round(original_price, 4) if original_price > 0 else 0.0,
                    "later_price_date": text(later_row.get("price_date")) if later_row else "",
                    "later_price": round(later_price, 4) if later_price is not None else None,
                    "percent_change": round(raw_return, 4) if raw_return is not None else None,
                    "directional_return_pct": round(directional_return, 4) if directional_return is not None else None,
                    "max_favorable_move_pct": max_favorable,
                    "max_adverse_move_pct": max_adverse,
                    "invalidation_price": round(invalidation_price, 4) if invalidation_price > 0 else None,
                    "invalidation_hit": invalidated,
                    "outcome_status": status,
                    "review_only": True,
                    "model_tuning_impact": "none",
                    "recommendation_impact": "none",
                    "notes": REVIEW_ONLY_NOTE,
                }
            )
    rows.sort(
        key=lambda row: (
            text(row["setup_date"]),
            text(row["symbol"]),
            int(row["window_trading_days"]),
        )
    )
    return rows


def summarize_tactical_outcomes(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    outcomes = [dict(row) for row in rows]
    counts: dict[str, int] = {status: 0 for status in sorted(OUTCOME_STATUSES)}
    for row in outcomes:
        status = text(row.get("outcome_status"))
        if status:
            counts[status] = counts.get(status, 0) + 1
    return {
        "review_only": True,
        "windows": list(OUTCOME_WINDOWS),
        "outcome_count": len(outcomes),
        "status_counts": counts,
        "model_tuning_impact": "none",
        "recommendation_impact": "none",
        "notes": REVIEW_ONLY_NOTE,
    }
