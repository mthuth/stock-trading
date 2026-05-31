#!/usr/bin/env python3
"""Transparent technical target calculations for analysis."""

from __future__ import annotations

from datetime import date, datetime
from statistics import stdev
from typing import Any


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: object, default: int) -> int:
    number = _to_float(value, float(default))
    return int(number) if number > 0 else default


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _age_days(latest_date: object, as_of_date: str) -> int | None:
    latest = _parse_date(latest_date)
    as_of = _parse_date(as_of_date)
    if not latest or not as_of:
        return None
    return max(0, (as_of - latest).days)


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return _average(values[-window:])


def _recent_returns(closes: list[float], lookback: int = 21) -> list[float]:
    recent = closes[-lookback:]
    return [
        (recent[index] - recent[index - 1]) / recent[index - 1]
        for index in range(1, len(recent))
        if recent[index - 1] > 0
    ]


def _support_level(lows: list[float], closes: list[float], current: float, support_days: int) -> float:
    recent_lows = lows[-min(support_days, len(lows)) :]
    swing_low = min(recent_lows) if recent_lows else current
    ma_candidates = [
        ma
        for ma in (
            _moving_average(closes, 20),
            _moving_average(closes, 50),
            _moving_average(closes, 200),
        )
        if ma and ma <= current * 1.02
    ]
    candidates = [swing_low, *ma_candidates]
    return max(candidate for candidate in candidates if candidate > 0)


def _resistance_level(highs: list[float], current: float, resistance_days: int) -> float:
    recent_highs = highs[-min(resistance_days, len(highs)) :]
    resistance = max(recent_highs) if recent_highs else current
    return max(resistance, current)


def _trend_state(current: float, ma20: float | None, ma50: float | None, ma200: float | None) -> str:
    if ma20 and ma50 and current > ma20 > ma50 and (ma200 is None or ma50 >= ma200 * 0.98):
        return "clear uptrend"
    if ma20 and ma50 and current > ma50 and ma20 >= ma50 * 0.98:
        return "constructive"
    if ma20 and ma50 and current < ma20 and ma20 < ma50:
        return "weak"
    return "mixed"


def _target_range(
    current: float,
    support: float,
    resistance: float,
    breakout_buffer: float,
    stop_buffer: float,
    daily_volatility: float,
    trend_state: str,
) -> tuple[float, float, float, float]:
    volatility_width = min(max(daily_volatility * 2, 0.03), 0.15)
    review_floor = current * (1 - volatility_width)
    if trend_state == "clear uptrend":
        target_low = max(support, review_floor)
        target_high = max(resistance * (1 + breakout_buffer), current * 1.06)
        target_price = max((current + target_high) / 2, current * 1.04)
    elif trend_state == "constructive":
        target_low = max(support, current * (1 - max(volatility_width, 0.04)))
        target_high = max(resistance * (1 + breakout_buffer / 2), current * 1.035)
        target_price = max((current + target_high) / 2, current * 1.02)
    elif trend_state == "weak":
        target_low = min(support, current * (1 - max(volatility_width, stop_buffer)))
        target_high = max(resistance, current * 1.01)
        target_price = min((current + target_high) / 2, current * 1.02)
    else:
        target_low = min(support, current * (1 - max(volatility_width, 0.04)))
        target_high = max(resistance * (1 + breakout_buffer / 2), current * 1.025)
        target_price = (target_low + target_high) / 2
    return target_price, target_low, max(target_high, target_price), support * (1 - stop_buffer)


def _confidence_label(score: float) -> str:
    return "medium" if score >= 0.6 else "low"


def calculate_technical_target(
    *,
    symbol: str,
    current_price: float,
    sleeve: str,
    as_of_date: str,
    model_config: dict[str, object],
    history: list[dict[str, object]],
) -> dict[str, object] | None:
    """Calculate a reviewable technical target input from daily price history."""

    if current_price <= 0:
        return None

    windows = model_config.get("windows", {}) if isinstance(model_config, dict) else {}
    buffers = model_config.get("buffers", {}) if isinstance(model_config, dict) else {}
    thresholds = model_config.get("quality_thresholds", {}) if isinstance(model_config, dict) else {}

    short_days = _to_int(windows.get("short_trend_days"), 20)
    medium_days = _to_int(windows.get("medium_trend_days"), 50)
    long_days = _to_int(windows.get("long_trend_days"), 200)
    support_days = _to_int(windows.get("support_lookback_days"), 60)
    resistance_days = _to_int(windows.get("resistance_lookback_days"), 60)
    minimum_days = _to_int(thresholds.get("minimum_history_days"), short_days)
    stale_days = _to_int(thresholds.get("stale_history_days"), 5)
    volatile_daily_pct = _to_float(thresholds.get("volatile_daily_move_pct"), 0.04)

    breakout_buffer = _to_float(buffers.get("breakout_buffer_pct"), 0.03)
    stop_buffer = _to_float(buffers.get("stop_review_buffer_below_support_pct"), 0.05)
    volatility_haircut = _to_float(buffers.get("high_volatility_confidence_haircut"), 0.20)
    thin_history_haircut = _to_float(buffers.get("thin_history_confidence_haircut"), 0.25)

    clean_history = [row for row in history if _to_float(row.get("close")) > 0]
    if len(clean_history) < minimum_days:
        return None

    closes = [_to_float(row.get("close")) for row in clean_history]
    highs = [
        _to_float(row.get("high"), _to_float(row.get("close"))) or _to_float(row.get("close"))
        for row in clean_history
    ]
    lows = [
        _to_float(row.get("low"), _to_float(row.get("close"))) or _to_float(row.get("close"))
        for row in clean_history
    ]
    latest_date = clean_history[-1].get("date")
    freshness_days = _age_days(latest_date, as_of_date)

    ma20 = _moving_average(closes, short_days)
    ma50 = _moving_average(closes, medium_days)
    ma200 = _moving_average(closes, long_days)
    support = _support_level(lows, closes, current_price, support_days)
    resistance = _resistance_level(highs, current_price, resistance_days)
    returns = _recent_returns(closes)
    daily_volatility = stdev(returns) if len(returns) >= 2 else 0.0
    trend = _trend_state(current_price, ma20, ma50, ma200)
    target_price, target_low, target_high, stop_review = _target_range(
        current_price,
        support,
        resistance,
        breakout_buffer,
        stop_buffer,
        daily_volatility,
        trend,
    )
    upside = ((target_price - current_price) / current_price) * 100

    confidence_score = 0.75
    notes: list[str] = [f"trend {trend}"]
    if len(clean_history) < medium_days:
        confidence_score -= thin_history_haircut
        notes.append(f"thin history: {len(clean_history)} bars")
    if freshness_days is None:
        confidence_score -= 0.10
        notes.append("freshness unknown")
    elif freshness_days > stale_days:
        confidence_score -= 0.25
        notes.append(f"stale price history: latest bar {freshness_days} days old")
    if daily_volatility > volatile_daily_pct:
        confidence_score -= volatility_haircut
        notes.append(f"volatile tape: 20-day daily volatility {daily_volatility * 100:.1f}%")
    if ma50 is None:
        confidence_score -= 0.10
        notes.append(f"MA{medium_days} unavailable")
    if ma200 is None:
        confidence_score -= 0.05
        notes.append(f"MA{long_days} unavailable")
    if trend == "mixed":
        confidence_score -= 0.10
        notes.append("mixed trend signals; use range rather than point precision")
    if sleeve == "speculative_ai":
        confidence_score -= 0.10
        notes.append("speculative/watchlist sleeve lowers technical confidence")

    confidence = _confidence_label(confidence_score)
    assumption_note = (
        f"inputs: current {current_price:.2f}; {len(clean_history)} daily bars; "
        f"MA{short_days} {ma20:.2f}" if ma20 else f"inputs: current {current_price:.2f}; {len(clean_history)} daily bars; MA{short_days} unavailable"
    )
    assumption_note += (
        f"; MA{medium_days} {ma50:.2f}" if ma50 else f"; MA{medium_days} unavailable"
    )
    assumption_note += f"; MA{long_days} {ma200:.2f}" if ma200 else f"; MA{long_days} unavailable"
    assumption_note += (
        f"; support {support:.2f}; resistance {resistance:.2f}; "
        f"breakout buffer {breakout_buffer * 100:.1f}%; review buffer {stop_buffer * 100:.1f}%; "
        f"target range {target_low:.2f}-{target_high:.2f}; stop/review {stop_review:.2f}; "
        f"confidence score {max(0.0, confidence_score):.2f}. "
        "Technical target is a review input only and does not change blending weights."
    )

    return {
        "symbol": symbol,
        "target_price": round(target_price, 4),
        "target_low": round(target_low, 4),
        "target_high": round(target_high, 4),
        "current_price": current_price,
        "upside_pct": round(upside, 4),
        "freshness_days": freshness_days if freshness_days is not None else None,
        "confidence": confidence,
        "provider_endpoint": "price_history + configured technical target v2 assumptions",
        "notes": f"{'; '.join(notes)}. {assumption_note}",
    }
