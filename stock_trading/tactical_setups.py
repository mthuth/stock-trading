"""Deterministic, review-only tactical setup classifier."""

from __future__ import annotations

import copy
from datetime import date, datetime
from statistics import stdev
from typing import Iterable, Mapping


SETUP_LABELS = {
    "breakout_review",
    "pullback_review",
    "momentum_review",
    "reversal_review",
    "post_earnings_reaction_review",
    "pre_earnings_setup_review",
    "news_catalyst_review",
    "no_tactical_setup",
    "data_insufficient",
}
REVIEW_ACTIONS = {
    "tactical_buy_review",
    "tactical_sell_review",
    "wait_for_confirmation",
    "watch_intraday",
    "avoid_for_now",
    "hold_existing",
    "data_gap_review",
}
RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only tactical setup review. This classifier is review-only: it does not "
    "place trades, preview orders, write to brokers, change official recommendation actions, "
    "change scores, change targets, change target confidence, change decision-safety rules, "
    "change allocation, tune the model, or override long-term buy/add queues."
)

BLOCKING_PROVIDER_STATUSES = {
    "blocked",
    "rate_limited",
    "missing",
    "stale",
    "parser_gap",
    "not_implemented",
    "needs_refresh",
    "needs_review",
    "error",
}
WEAK_SOURCE_LABELS = {"noisy", "stale_or_blocked", "needs_more_history", "not_enough_data"}
POSITIVE_CATALYST_TOKENS = {
    "beat",
    "raise",
    "raised",
    "strong",
    "breakout",
    "guidance",
    "contract",
    "partnership",
    "upgrade",
    "launch",
    "momentum",
    "thesis_improved",
    "market_confirmation",
}
NEGATIVE_CATALYST_TOKENS = {
    "miss",
    "weak",
    "downgrade",
    "risk",
    "cut",
    "lowered",
    "thesis_weakened",
    "negative",
}


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


def as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value else []
    return []


def parse_date(value: object) -> date | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw[:10], raw.replace("Z", "+00:00"), raw):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def _row_symbol(row: Mapping[str, object]) -> str:
    return text(row.get("symbol") or row.get("Symbol")).upper()


def _price_date(row: Mapping[str, object]) -> date | None:
    return parse_date(row.get("price_date") or row.get("date") or row.get("as_of_date"))


def _price_close(row: Mapping[str, object]) -> float:
    return to_float(row.get("adjusted_close")) or to_float(row.get("close")) or to_float(row.get("price"))


def normalized_price_history(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Normalize daily price rows into deterministic date order."""

    history: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        parsed = _price_date(row)
        close = _price_close(row)
        if not parsed or close <= 0:
            continue
        key = parsed.isoformat()
        if key in seen:
            continue
        seen.add(key)
        high = to_float(row.get("high"), close) or close
        low = to_float(row.get("low"), close) or close
        history.append(
            {
                "date": key,
                "close": close,
                "high": high,
                "low": low,
                "volume": to_float(row.get("volume")),
            }
        )
    history.sort(key=lambda row: text(row["date"]))
    return history


def _moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _pct_change(current: float, prior: float) -> float:
    if prior <= 0:
        return 0.0
    return ((current - prior) / prior) * 100


def _recent_return_volatility(closes: list[float], lookback: int = 21) -> float:
    recent = closes[-lookback:]
    returns = [
        (recent[index] - recent[index - 1]) / recent[index - 1]
        for index in range(1, len(recent))
        if recent[index - 1] > 0
    ]
    return stdev(returns) * 100 if len(returns) >= 2 else 0.0


def technical_context_summary(
    price_history: Iterable[Mapping[str, object]],
    *,
    current_price: float | None = None,
    technical_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Summarize technical inputs without changing target calculations."""

    history = normalized_price_history(price_history)
    technical = as_dict(technical_context)
    if not history and not current_price:
        return {
            "status": "missing_price_history",
            "data_gaps": ["missing_price_history"],
        }

    closes = [to_float(row.get("close")) for row in history]
    highs = [to_float(row.get("high")) for row in history]
    lows = [to_float(row.get("low")) for row in history]
    current = to_float(current_price) or (closes[-1] if closes else to_float(technical.get("current_price")))
    previous_rows = history[:-1] if len(history) > 1 else history
    previous_highs = [to_float(row.get("high")) for row in previous_rows]
    previous_lows = [to_float(row.get("low")) for row in previous_rows]
    recent_highs = previous_highs[-20:] or highs[-20:]
    recent_lows = previous_lows[-20:] or lows[-20:]
    support = (
        to_float(technical.get("support_level"))
        or to_float(technical.get("support"))
        or to_float(technical.get("target_low"))
        or (min(recent_lows) if recent_lows else current)
    )
    resistance = (
        to_float(technical.get("resistance_level"))
        or to_float(technical.get("resistance"))
        or to_float(technical.get("target_high"))
        or (max(recent_highs) if recent_highs else current)
    )
    ma5 = _moving_average(closes, 5)
    ma10 = _moving_average(closes, 10)
    ma20 = _moving_average(closes, 20)
    ma50 = _moving_average(closes, 50)
    one_day = _pct_change(current, closes[-2]) if len(closes) >= 2 else 0.0
    five_day = _pct_change(current, closes[-6]) if len(closes) >= 6 else 0.0
    twenty_day = _pct_change(current, closes[-21]) if len(closes) >= 21 else 0.0
    volatility = _recent_return_volatility(closes)
    pullback_from_high = _pct_change(max(recent_highs), current) if recent_highs else 0.0
    bounce_from_support = _pct_change(current, support)
    near_support_pct = abs(bounce_from_support)
    distance_to_resistance = _pct_change(resistance, current) if resistance else 0.0
    breakout_pct = _pct_change(current, resistance) if resistance else 0.0

    data_gaps: list[str] = []
    if len(history) < 5:
        data_gaps.append("thin_price_history")
    status = "available" if len(history) >= 5 or current > 0 else "missing_price_history"
    return {
        "status": status,
        "history_days": len(history),
        "current_price": round(current, 4) if current else None,
        "latest_price_date": text(history[-1].get("date")) if history else "",
        "ma5": round(ma5, 4) if ma5 is not None else None,
        "ma10": round(ma10, 4) if ma10 is not None else None,
        "ma20": round(ma20, 4) if ma20 is not None else None,
        "ma50": round(ma50, 4) if ma50 is not None else None,
        "support_level": round(support, 4) if support else None,
        "resistance_level": round(resistance, 4) if resistance else None,
        "one_day_change_pct": round(one_day, 4),
        "five_day_change_pct": round(five_day, 4),
        "twenty_day_change_pct": round(twenty_day, 4),
        "volatility_pct": round(volatility, 4),
        "pullback_from_high_pct": round(pullback_from_high, 4),
        "bounce_from_support_pct": round(bounce_from_support, 4),
        "near_support_pct": round(near_support_pct, 4),
        "distance_to_resistance_pct": round(distance_to_resistance, 4),
        "breakout_pct": round(breakout_pct, 4),
        "technical_confidence": text(technical.get("confidence")),
        "data_gaps": data_gaps,
    }


def provider_gap_notes(provider_gaps: Iterable[object] | object | None) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    gaps: list[str] = []
    for gap in as_list(provider_gaps):
        if isinstance(gap, Mapping):
            status = normalized_token(gap.get("status") or gap.get("Status") or gap.get("severity"))
            provider = text(gap.get("provider") or gap.get("Provider") or gap.get("source") or "provider")
            field = text(gap.get("field_name") or gap.get("field") or gap.get("endpoint") or gap.get("data_type") or "data")
            issue = text(gap.get("latest_issue") or gap.get("message") or gap.get("issue") or gap.get("notes"))
            label = f"{provider} {field}"
            if issue:
                label = f"{label}: {issue}"
        else:
            status = normalized_token(gap)
            label = text(gap)
        if label:
            gaps.append(label)
        if status in BLOCKING_PROVIDER_STATUSES:
            blockers.append(label or "Provider gap")
    return list(dict.fromkeys(blockers)), list(dict.fromkeys(gaps))


def source_usefulness_notes(source_usefulness: Mapping[str, object] | Iterable[Mapping[str, object]] | None) -> list[str]:
    rows: list[Mapping[str, object]]
    if isinstance(source_usefulness, Mapping):
        rows = [source_usefulness]
    else:
        rows = [row for row in as_list(source_usefulness) if isinstance(row, Mapping)]
    notes: list[str] = []
    for row in rows:
        label = normalized_token(row.get("label") or row.get("source_quality_label") or row.get("status"))
        if label in WEAK_SOURCE_LABELS:
            source = text(row.get("source_name") or row.get("source") or "source")
            notes.append(f"{source} source usefulness is {label}")
    return notes


def ai_readiness_note(ai_synthesis_readiness: Mapping[str, object] | None) -> str:
    data = as_dict(ai_synthesis_readiness)
    if not data:
        return ""
    status = normalized_token(data.get("status") or data.get("readiness_status"))
    if status in {"", "ready", "ready_for_ai_synthesis", "available"}:
        return ""
    return f"AI synthesis readiness is {status}; use as explanatory context only."


def _row_date(row: Mapping[str, object]) -> date | None:
    return parse_date(
        row.get("event_date")
        or row.get("latest_evidence_at")
        or row.get("published_at")
        or row.get("source_timestamp")
        or row.get("created_at")
        or row.get("date")
    )


def _row_text(row: Mapping[str, object]) -> str:
    parts = [
        text(row.get("event_type")),
        text(row.get("headline")),
        text(row.get("title")),
        text(row.get("summary")),
        text(row.get("notes")),
        text(row.get("corroboration_label")),
        text(row.get("sentiment")),
    ]
    return " ".join(part for part in parts if part).lower()


def catalyst_context(
    symbol: str,
    catalyst_events: Iterable[Mapping[str, object]] | None,
    *,
    as_of_date: date,
    lookback_days: int = 7,
) -> dict[str, object]:
    selected: list[Mapping[str, object]] = []
    for row in catalyst_events or ():
        candidate_symbol = _row_symbol(row)
        if candidate_symbol and candidate_symbol != symbol.upper():
            continue
        event_date = _row_date(row)
        if event_date and (as_of_date - event_date).days > lookback_days:
            continue
        selected.append(row)
    if not selected:
        return {}
    selected.sort(key=lambda row: (_row_date(row) or date.min, text(row.get("headline"))), reverse=True)
    first = selected[0]
    payload = _row_text(first)
    positive = any(token in payload for token in POSITIVE_CATALYST_TOKENS)
    negative = any(token in payload for token in NEGATIVE_CATALYST_TOKENS)
    direction = "negative" if negative and not positive else "positive" if positive and not negative else "mixed"
    return {
        "headline": text(first.get("headline") or first.get("title") or first.get("summary")),
        "event_type": text(first.get("event_type")),
        "event_date": (_row_date(first) or as_of_date).isoformat(),
        "direction": direction,
        "row_count": len(selected),
    }


def _pre_earnings_context(
    earnings_event: Mapping[str, object] | None,
    pre_earnings_review: Mapping[str, object] | None,
    as_of_date: date,
) -> dict[str, object]:
    review = as_dict(pre_earnings_review)
    event = as_dict(earnings_event)
    earnings_date = parse_date(review.get("earnings_date") or event.get("earnings_date") or event.get("event_date"))
    days_until = review.get("days_until_earnings")
    if days_until is None and earnings_date:
        days_until = (earnings_date - as_of_date).days
    return {
        "review": review,
        "earnings_date": earnings_date,
        "days_until": int(days_until) if isinstance(days_until, int) or text(days_until).lstrip("-").isdigit() else None,
    }


def _post_earnings_context(
    earnings_event: Mapping[str, object] | None,
    post_earnings_review: Mapping[str, object] | None,
    as_of_date: date,
) -> dict[str, object]:
    review = as_dict(post_earnings_review)
    event = as_dict(earnings_event)
    earnings_date = parse_date(review.get("earnings_date") or event.get("earnings_date") or event.get("event_date"))
    days_since = review.get("days_since_earnings")
    if days_since is None and earnings_date:
        days_since = (as_of_date - earnings_date).days
    return {
        "review": review,
        "earnings_date": earnings_date,
        "days_since": int(days_since) if isinstance(days_since, int) or text(days_since).lstrip("-").isdigit() else None,
    }


def _confidence(base: int, blockers: list[str], data_gaps: list[str]) -> str:
    score = base - (15 if blockers else 0) - min(20, len(data_gaps) * 8)
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    if score >= 25:
        return "low"
    return "needs_review"


def _risk_zone(summary: Mapping[str, object], label: str) -> str:
    support = to_float(summary.get("support_level"))
    resistance = to_float(summary.get("resistance_level"))
    current = to_float(summary.get("current_price"))
    if support and current:
        lower = support * 0.98
        upper = current if label in {"pullback_review", "reversal_review"} else max(current, support * 1.03)
        return f"{lower:.2f}-{upper:.2f}"
    if current and resistance:
        return f"{current:.2f}-{resistance:.2f}"
    return ""


def _invalidation(summary: Mapping[str, object], label: str) -> str:
    support = to_float(summary.get("support_level"))
    resistance = to_float(summary.get("resistance_level"))
    current = to_float(summary.get("current_price"))
    if support:
        return f"Review is invalidated if price closes below support near {support:.2f}."
    if label == "breakout_review" and resistance:
        return f"Review is invalidated if price falls back below breakout level near {resistance:.2f}."
    if current:
        return f"Review is invalidated if the setup loses current-price support near {current:.2f}."
    return "Review is invalidated if required price history or event evidence is unavailable."


def _base_result(
    *,
    symbol: str,
    setup_label: str,
    tactical_horizon: str,
    review_action: str,
    setup_confidence: str,
    technical_summary: Mapping[str, object],
    reasons: list[str],
    blockers: list[str],
    data_gaps: list[str],
) -> dict[str, object]:
    return {
        "symbol": symbol.upper(),
        "setup_label": setup_label,
        "tactical_horizon": tactical_horizon,
        "review_action": review_action,
        "setup_confidence": setup_confidence,
        "support_level": technical_summary.get("support_level"),
        "resistance_level": technical_summary.get("resistance_level"),
        "risk_zone": _risk_zone(technical_summary, setup_label),
        "invalidation_condition": _invalidation(technical_summary, setup_label),
        "reasons": list(dict.fromkeys(reason for reason in reasons if reason)),
        "blockers": list(dict.fromkeys(blocker for blocker in blockers if blocker)),
        "data_gaps": list(dict.fromkeys(gap for gap in data_gaps if gap)),
        "review_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


def classify_tactical_setup(
    *,
    symbol: str,
    current_price: float | None = None,
    price_history: Iterable[Mapping[str, object]] = (),
    technical_context: Mapping[str, object] | None = None,
    earnings_event: Mapping[str, object] | None = None,
    pre_earnings_review: Mapping[str, object] | None = None,
    post_earnings_review: Mapping[str, object] | None = None,
    catalyst_events: Iterable[Mapping[str, object]] | None = None,
    provider_gaps: Iterable[object] | object | None = None,
    source_usefulness: Mapping[str, object] | Iterable[Mapping[str, object]] | None = None,
    ai_synthesis_readiness: Mapping[str, object] | None = None,
    recommendation: Mapping[str, object] | None = None,
    as_of_date: str | date | None = None,
) -> dict[str, object]:
    """Classify a review-only tactical setup without mutating recommendations."""

    del recommendation  # Recommendation context is accepted for future use, but never mutated or acted on here.
    as_of = as_of_date if isinstance(as_of_date, date) else parse_date(as_of_date)
    as_of = as_of or date.today()
    normalized_symbol = text(symbol).upper()
    technical_summary = technical_context_summary(
        price_history,
        current_price=current_price,
        technical_context=technical_context,
    )
    provider_blockers, gap_notes = provider_gap_notes(provider_gaps)
    data_gaps = [*as_list(technical_summary.get("data_gaps")), *gap_notes]
    blockers = list(provider_blockers)
    reasons: list[str] = []
    source_notes = source_usefulness_notes(source_usefulness)
    ai_note = ai_readiness_note(ai_synthesis_readiness)
    if source_notes:
        reasons.extend(source_notes)
    if ai_note:
        reasons.append(ai_note)

    if technical_summary.get("status") == "missing_price_history":
        return _base_result(
            symbol=normalized_symbol,
            setup_label="data_insufficient",
            tactical_horizon="unknown",
            review_action="data_gap_review",
            setup_confidence="needs_review",
            technical_summary=technical_summary,
            reasons=["Missing stored price history blocks tactical setup review.", *reasons],
            blockers=[*blockers, "Missing stored price history"],
            data_gaps=["missing_price_history", *data_gaps],
        )

    post_context = _post_earnings_context(earnings_event, post_earnings_review, as_of)
    post_review = as_dict(post_context.get("review"))
    days_since = post_context.get("days_since")
    if post_review and isinstance(days_since, int) and 0 <= days_since <= 10:
        label = normalized_token(post_review.get("reaction_label"))
        action = "tactical_sell_review" if label in {"thesis_weakened", "negative_reaction"} else "tactical_buy_review"
        if blockers:
            action = "data_gap_review"
        return _base_result(
            symbol=normalized_symbol,
            setup_label="post_earnings_reaction_review",
            tactical_horizon="same_week" if days_since <= 5 else "same_month",
            review_action=action,
            setup_confidence=_confidence(76, blockers, data_gaps),
            technical_summary=technical_summary,
            reasons=[
                f"Post-earnings reaction is in review window ({days_since} day(s) since earnings).",
                f"Reaction label: {label or 'available'}.",
                *as_list(post_review.get("evidence_summary")),
                *reasons,
            ],
            blockers=blockers,
            data_gaps=[*data_gaps, *as_list(post_review.get("data_gaps"))],
        )

    pre_context = _pre_earnings_context(earnings_event, pre_earnings_review, as_of)
    pre_review = as_dict(pre_context.get("review"))
    days_until = pre_context.get("days_until")
    if pre_review and isinstance(days_until, int) and 0 <= days_until <= 14:
        label = normalized_token(pre_review.get("setup_label"))
        action = "wait_for_confirmation"
        if label == "attractive_pre_earnings_review" and not blockers:
            action = "tactical_buy_review"
        elif label in {"data_insufficient", "avoid_pre_earnings_add"} or blockers:
            action = "data_gap_review" if blockers or label == "data_insufficient" else "avoid_for_now"
        return _base_result(
            symbol=normalized_symbol,
            setup_label="pre_earnings_setup_review",
            tactical_horizon="same_week" if days_until <= 5 else "same_month",
            review_action=action,
            setup_confidence=_confidence(68, blockers, data_gaps),
            technical_summary=technical_summary,
            reasons=[
                f"Pre-earnings setup is in review window ({days_until} day(s) until earnings).",
                f"Pre-earnings label: {label or 'available'}.",
                *as_list(pre_review.get("reasons")),
                *reasons,
            ],
            blockers=[*blockers, *as_list(pre_review.get("blockers"))],
            data_gaps=[*data_gaps, *as_list(pre_review.get("data_gaps"))],
        )

    catalyst = catalyst_context(normalized_symbol, catalyst_events, as_of_date=as_of)
    if catalyst:
        direction = text(catalyst.get("direction"))
        action = "tactical_buy_review" if direction == "positive" and not blockers else "wait_for_confirmation"
        if direction == "negative":
            action = "tactical_sell_review"
        if blockers:
            action = "data_gap_review"
        return _base_result(
            symbol=normalized_symbol,
            setup_label="news_catalyst_review",
            tactical_horizon="same_week",
            review_action=action,
            setup_confidence=_confidence(64, blockers, data_gaps),
            technical_summary=technical_summary,
            reasons=[
                f"Recent catalyst/news event: {catalyst.get('headline') or catalyst.get('event_type')}.",
                f"Catalyst direction: {direction}.",
                *reasons,
            ],
            blockers=blockers,
            data_gaps=data_gaps,
        )

    current = to_float(technical_summary.get("current_price"))
    ma5 = to_float(technical_summary.get("ma5"))
    ma10 = to_float(technical_summary.get("ma10"))
    ma20 = to_float(technical_summary.get("ma20"))
    ma50 = to_float(technical_summary.get("ma50"))
    one_day = to_float(technical_summary.get("one_day_change_pct"))
    five_day = to_float(technical_summary.get("five_day_change_pct"))
    twenty_day = to_float(technical_summary.get("twenty_day_change_pct"))
    breakout_pct = to_float(technical_summary.get("breakout_pct"))
    near_support = to_float(technical_summary.get("near_support_pct"))
    bounce_from_support = to_float(technical_summary.get("bounce_from_support_pct"))
    pullback = to_float(technical_summary.get("pullback_from_high_pct"))

    label = "no_tactical_setup"
    horizon = "same_week"
    action = "hold_existing"
    base_confidence = 45
    if breakout_pct >= 1.0 and five_day >= 1.5:
        label = "breakout_review"
        action = "tactical_buy_review"
        base_confidence = 72
        reasons.append("Price is above recent resistance with positive short-term follow-through.")
    elif current > 0 and ma5 and ma20 and current > ma5 > ma20 and five_day >= 3.0:
        label = "momentum_review"
        action = "watch_intraday" if one_day >= 4.0 else "tactical_buy_review"
        base_confidence = 68
        horizon = "same_day" if one_day >= 4.0 else "same_week"
        reasons.append("Price is in short-term momentum above moving averages.")
    elif ma20 and current >= ma20 and 3.0 <= pullback <= 9.0 and near_support <= 4.0:
        label = "pullback_review"
        action = "wait_for_confirmation" if one_day < 0.5 else "tactical_buy_review"
        base_confidence = 64
        reasons.append("Price pulled back near support while remaining above the 20-day trend.")
    elif ma20 and ma50 and twenty_day <= -5.0 and one_day >= 2.0 and bounce_from_support >= 3.0:
        label = "reversal_review"
        action = "wait_for_confirmation"
        base_confidence = 56
        horizon = "same_month"
        reasons.append("Weak recent trend is showing a possible bounce from support.")
    else:
        reasons.append("No deterministic tactical setup threshold was met.")

    if blockers and label != "no_tactical_setup":
        action = "data_gap_review"
        reasons.append("Provider gaps lower tactical setup confidence.")

    return _base_result(
        symbol=normalized_symbol,
        setup_label=label,
        tactical_horizon=horizon if label != "no_tactical_setup" else "none",
        review_action=action,
        setup_confidence=_confidence(base_confidence, blockers, data_gaps),
        technical_summary=technical_summary,
        reasons=reasons,
        blockers=blockers,
        data_gaps=data_gaps,
    )


def classify_tactical_setups(
    rows: Iterable[Mapping[str, object]],
    *,
    as_of_date: str | date | None = None,
) -> dict[str, object]:
    """Classify multiple tactical setup inputs deterministically."""

    results = [
        classify_tactical_setup(
            symbol=text(row.get("symbol")),
            current_price=to_float(row.get("current_price")) or None,
            price_history=as_list(row.get("price_history")),
            technical_context=as_dict(row.get("technical_context")),
            earnings_event=as_dict(row.get("earnings_event")),
            pre_earnings_review=as_dict(row.get("pre_earnings_review")),
            post_earnings_review=as_dict(row.get("post_earnings_review")),
            catalyst_events=[item for item in as_list(row.get("catalyst_events")) if isinstance(item, Mapping)],
            provider_gaps=row.get("provider_gaps"),
            source_usefulness=row.get("source_usefulness"),
            ai_synthesis_readiness=as_dict(row.get("ai_synthesis_readiness")),
            recommendation=as_dict(row.get("recommendation")),
            as_of_date=as_of_date,
        )
        for row in rows
    ]
    results.sort(key=lambda row: (text(row.get("setup_label")), text(row.get("symbol"))))
    return {
        "review_only": True,
        "recommendation_only": True,
        "row_count": len(results),
        "rows": results,
        "note": RECOMMENDATION_ONLY_NOTE,
    }


__all__ = [
    "RECOMMENDATION_ONLY_NOTE",
    "REVIEW_ACTIONS",
    "SETUP_LABELS",
    "classify_tactical_setup",
    "classify_tactical_setups",
    "normalized_price_history",
    "technical_context_summary",
]
