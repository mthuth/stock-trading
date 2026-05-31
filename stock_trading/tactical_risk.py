"""Review-only tactical risk zones and invalidation conditions."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable, Mapping


RISK_ZONE_LABELS = {
    "favorable_review_zone",
    "extended_chase_risk",
    "support_break_risk",
    "high_volatility_event_risk",
    "data_insufficient",
    "neutral",
}
TACTICAL_HORIZONS = {"same_day", "same_week", "same_month"}
REVIEW_ONLY_NOTE = (
    "Review-only tactical risk context. This output must not change scores, targets, "
    "recommendations, decision safety, allocation, source weights, broker behavior, or trading."
)
NO_ORDER_PREVIEW_NOTE = (
    "No order preview is provided. Review zones are decision-support "
    "context only and require a human decision outside the app."
)
HIGH_VOLATILITY_PCT = 6.0
ELEVATED_VOLATILITY_PCT = 4.0
NEAR_EVENT_DAYS = 3
SUPPORT_NEAR_PCT = 3.0
EXTENDED_ABOVE_RESISTANCE_PCT = 3.0
EXTENDED_ABOVE_SUPPORT_PCT = 12.0


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def normalized_token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def pct_distance(current: float, reference: float) -> float | None:
    if current <= 0 or reference <= 0:
        return None
    return ((current - reference) / reference) * 100


def normalized_volatility_pct(value: object) -> float:
    number = to_float(value)
    if 0 < number <= 1:
        return number * 100
    return max(0.0, number)


def as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def build_moving_average_context(value: Mapping[str, object] | None) -> dict[str, object]:
    data = dict(value or {})
    current = to_float(data.get("current_price"))
    ma20 = to_float(data.get("ma20") or data.get("short_ma"))
    ma50 = to_float(data.get("ma50") or data.get("medium_ma"))
    ma200 = to_float(data.get("ma200") or data.get("long_ma"))
    if current <= 0:
        trend = normalized_token(data.get("trend") or data.get("trend_state")) or "unknown"
    elif ma20 and ma50 and current > ma20 >= ma50:
        trend = "constructive"
    elif ma20 and ma50 and current < ma20 < ma50:
        trend = "weak"
    elif ma20 and current >= ma20:
        trend = "mixed_positive"
    elif ma20 and current < ma20:
        trend = "mixed_weak"
    else:
        trend = normalized_token(data.get("trend") or data.get("trend_state")) or "unknown"
    return {
        "ma20": ma20 if ma20 > 0 else None,
        "ma50": ma50 if ma50 > 0 else None,
        "ma200": ma200 if ma200 > 0 else None,
        "trend": trend,
    }


def price_history_status(value: object) -> tuple[str, list[str]]:
    if isinstance(value, Mapping):
        status = normalized_token(value.get("status") or value.get("quality") or value.get("data_quality"))
        history_days = to_int(value.get("history_days") or value.get("price_history_days"))
        confidence = normalized_token(value.get("confidence"))
        notes: list[str] = []
        if status in {"missing", "insufficient", "thin", "stale"}:
            notes.append(f"Price history status is {status}.")
        if 0 < history_days < 20:
            notes.append(f"Price history has only {history_days} day(s).")
        if confidence in {"low", "weak"}:
            notes.append("Price history confidence is weak.")
        if notes:
            return "insufficient", notes
        return status or "available", []
    status = normalized_token(value)
    if status in {"missing", "insufficient", "thin", "stale"}:
        return "insufficient", [f"Price history status is {status}."]
    return status or "available", []


def event_risk_context(value: object) -> tuple[bool, str]:
    if isinstance(value, Mapping):
        event_type = normalized_token(value.get("event_type") or value.get("type") or value.get("label"))
        days = to_int(value.get("days_to_event") or value.get("days_until_event") or value.get("days_since_event"), 999)
        if event_type in {"earnings", "guidance", "post_earnings", "pre_earnings"} and abs(days) <= NEAR_EVENT_DAYS:
            return True, f"{event_type.replace('_', ' ')} within {abs(days)} day(s)"
        if normalized_token(value.get("status")) in {"high_risk", "event_risk"}:
            return True, text(value.get("notes") or "High event risk.")
        return False, text(value.get("notes"))
    token = normalized_token(value)
    if token in {"earnings", "guidance", "post_earnings", "pre_earnings", "event_risk"}:
        return True, token.replace("_", " ")
    return False, text(value)


def risk_label_and_condition(
    *,
    current_price: float,
    support: float,
    resistance: float,
    volatility_pct: float,
    has_event_risk: bool,
    setup_label: str,
    data_quality: str,
    history_notes: list[str],
) -> tuple[str, str, list[str]]:
    notes: list[str] = []
    distance_from_support = pct_distance(current_price, support)
    distance_from_resistance = pct_distance(current_price, resistance)

    if current_price <= 0 or support <= 0 or resistance <= 0 or data_quality == "insufficient":
        return "data_insufficient", "Provider data insufficient for tactical risk review.", history_notes

    if has_event_risk or volatility_pct >= HIGH_VOLATILITY_PCT:
        if volatility_pct >= HIGH_VOLATILITY_PCT:
            notes.append(f"Recent volatility is high at {volatility_pct:.1f}%.")
        return (
            "high_volatility_event_risk",
            "Earnings/guidance or volatility invalidates the review setup until the event risk settles.",
            notes,
        )

    if current_price < support:
        return "support_break_risk", "Closes below support reference or support fails to recover.", notes

    if distance_from_resistance is not None and distance_from_resistance > EXTENDED_ABOVE_RESISTANCE_PCT:
        return (
            "extended_chase_risk",
            "Fails breakout confirmation or reverses back under resistance reference.",
            notes,
        )
    if (
        setup_label in {"momentum", "breakout", "post_earnings_reaction", "news_catalyst", "news/catalyst"}
        and distance_from_support is not None
        and distance_from_support > EXTENDED_ABOVE_SUPPORT_PCT
    ):
        return (
            "extended_chase_risk",
            "Fails breakout confirmation or momentum fades back toward support reference.",
            notes,
        )

    if distance_from_support is not None and 0 <= distance_from_support <= SUPPORT_NEAR_PCT:
        return "favorable_review_zone", "Closes below support reference invalidates the setup review.", notes

    if volatility_pct >= ELEVATED_VOLATILITY_PCT:
        notes.append(f"Recent volatility is elevated at {volatility_pct:.1f}%.")
    return "neutral", "Setup remains review-only unless price confirms trend and support remains intact.", notes


def tactical_risk_zone(
    *,
    symbol: str,
    tactical_horizon: str = "same_week",
    current_price: object = None,
    support_estimate: object = None,
    resistance_estimate: object = None,
    moving_average: Mapping[str, object] | None = None,
    moving_average_context: Mapping[str, object] | None = None,
    recent_volatility: object = None,
    recent_volatility_pct: object = None,
    earnings_event: object = None,
    setup_label: str = "",
    price_history_quality: object = None,
    notes: Iterable[object] = (),
) -> dict[str, object]:
    """Build a deterministic tactical risk-zone row for review only."""

    horizon = normalized_token(tactical_horizon)
    if horizon not in TACTICAL_HORIZONS:
        horizon = "same_week"
    setup = normalized_token(setup_label) or "unspecified"
    current = to_float(current_price)
    support = to_float(support_estimate)
    resistance = to_float(resistance_estimate)
    ma_input = moving_average if moving_average is not None else moving_average_context
    ma_context = build_moving_average_context({"current_price": current, **dict(ma_input or {})})
    volatility_pct = normalized_volatility_pct(recent_volatility if recent_volatility is not None else recent_volatility_pct)
    data_quality, history_notes = price_history_status(price_history_quality)
    has_event_risk, event_note = event_risk_context(earnings_event)

    label, invalidation, label_notes = risk_label_and_condition(
        current_price=current,
        support=support,
        resistance=resistance,
        volatility_pct=volatility_pct,
        has_event_risk=has_event_risk,
        setup_label=setup,
        data_quality=data_quality,
        history_notes=history_notes,
    )
    combined_notes = [text(note) for note in notes if text(note)]
    if event_note:
        combined_notes.append(event_note)
    combined_notes.extend(label_notes)
    if not combined_notes:
        combined_notes.append("Tactical risk zone is for review only and does not override long-term recommendations.")

    return {
        "symbol": text(symbol).upper(),
        "tactical_horizon": horizon,
        "setup_label": setup,
        "risk_zone_label": label,
        "support_reference": support if support > 0 else None,
        "resistance_reference": resistance if resistance > 0 else None,
        "invalidation_condition": invalidation,
        "volatility_context": {
            "recent_volatility_pct": round(volatility_pct, 4),
            "label": "high" if volatility_pct >= HIGH_VOLATILITY_PCT else "elevated" if volatility_pct >= ELEVATED_VOLATILITY_PCT else "normal",
        },
        "moving_average_context": ma_context,
        "data_quality": data_quality,
        "notes": combined_notes,
        "review_only": True,
        "no_order_preview_note": NO_ORDER_PREVIEW_NOTE,
        "recommendation_only_note": REVIEW_ONLY_NOTE,
    }


def tactical_risk_zones(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Build tactical risk-zone rows without mutating caller-owned inputs."""

    results: list[dict[str, object]] = []
    for raw_row in rows:
        row = deepcopy(dict(raw_row))
        results.append(
            tactical_risk_zone(
                symbol=text(row.get("symbol")),
                tactical_horizon=text(row.get("tactical_horizon") or row.get("horizon") or "same_week"),
                current_price=row.get("current_price"),
                support_estimate=row.get("support_estimate") or row.get("support_reference"),
                resistance_estimate=row.get("resistance_estimate") or row.get("resistance_reference"),
                moving_average=row.get("moving_average_context") if isinstance(row.get("moving_average_context"), Mapping) else None,
                recent_volatility=row.get("recent_volatility") or row.get("recent_volatility_pct"),
                earnings_event=row.get("earnings_event") or row.get("event_context"),
                setup_label=text(row.get("setup_label") or row.get("setup_type")),
                price_history_quality=row.get("price_history_quality") or row.get("data_quality"),
                notes=as_list(row.get("notes")),
            )
        )
    results.sort(key=lambda item: (text(item["symbol"]), text(item["tactical_horizon"]), text(item["setup_label"])))
    return results
