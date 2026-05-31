"""Review-only tactical watchlist queue helpers."""

from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Iterable, Mapping


RECOMMENDATION_ONLY_NOTE = (
    "Review-only tactical watchlist queue. These rows are short-term review prompts "
    "and do not change official long-term recommendations, scores, targets, target "
    "confidence, decision safety, suggested amounts, allocation rules, broker behavior, "
    "order previews, or trading."
)

TACTICAL_REVIEW_ACTIONS = {
    "tactical_buy_review",
    "tactical_sell_review",
    "watch_intraday",
    "wait_for_confirmation",
    "avoid_for_now",
    "data_gap_review",
}
SETUP_LABELS = {
    "momentum",
    "pullback",
    "breakout",
    "reversal",
    "post_earnings_reaction",
    "pre_earnings_setup",
    "news_catalyst",
    "no_setup",
}
TACTICAL_HORIZONS = {
    "1_day",
    "5_trading_days",
    "20_trading_days",
    "same_day",
    "same_week",
    "same_month",
}
BLOCKING_GAP_STATUSES = {
    "blocked",
    "rate_limited",
    "missing",
    "stale",
    "parser_gap",
    "not_implemented",
    "error",
    "data_gap",
    "needs_review",
}


def _as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return copy.deepcopy(list(value))
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _token(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _parse_date(value: object) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    for candidate in (raw, raw.replace("Z", "+00:00"), raw[:10]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def _as_of_date(value: date | str | None) -> date:
    if isinstance(value, date):
        return value
    return _parse_date(value) or date.today()


def _normalized_horizon(value: object) -> str:
    token = _token(value)
    aliases = {
        "intraday": "1_day",
        "same_day": "1_day",
        "daily": "1_day",
        "week": "5_trading_days",
        "same_week": "5_trading_days",
        "weekly": "5_trading_days",
        "month": "20_trading_days",
        "same_month": "20_trading_days",
        "monthly": "20_trading_days",
    }
    return aliases.get(token, token if token in TACTICAL_HORIZONS else "5_trading_days")


def _setup_label(row: Mapping[str, object]) -> str:
    label = _token(row.get("setup_label") or row.get("setup_type") or row.get("signal_type"))
    if not label:
        label = "no_setup" if _no_setup(row) else "momentum"
    aliases = {
        "post_earnings": "post_earnings_reaction",
        "earnings_reaction": "post_earnings_reaction",
        "pre_earnings": "pre_earnings_setup",
        "news": "news_catalyst",
        "catalyst": "news_catalyst",
    }
    label = aliases.get(label, label)
    return label if label in SETUP_LABELS else "news_catalyst"


def _confidence_score(confidence: object) -> tuple[str, int]:
    token = _token(confidence)
    if token in {"very_high", "strong"}:
        return "high", 55
    if token == "high":
        return "high", 50
    if token in {"medium", "moderate"}:
        return "medium", 32
    if token in {"low", "weak"}:
        return "low", 10
    if token in {"none", "no_setup"}:
        return "none", -35
    return token or "unknown", 15


def _risk_score(risk_zone: object) -> tuple[str, int]:
    token = _token(risk_zone)
    if token in {"low", "controlled"}:
        return "low", 14
    if token in {"medium", "moderate"}:
        return "medium", 8
    if token in {"high", "elevated"}:
        return "high", -12
    if token in {"extreme", "avoid"}:
        return "extreme", -35
    if token in {"data_gap", "unknown", ""}:
        return token or "unknown", -10
    return token, 0


def _data_quality_score(row: Mapping[str, object]) -> tuple[str, int, list[str]]:
    status = _token(
        row.get("data_quality")
        or row.get("data_status")
        or row.get("provider_gap_status")
        or row.get("source_health_status")
    )
    gaps = _provider_gaps(row)
    blocking = [
        _gap_label(gap)
        for gap in gaps
        if _token(gap.get("status") if isinstance(gap, Mapping) else gap) in BLOCKING_GAP_STATUSES
    ]
    if blocking:
        return "data_gap", -55, blocking
    if status in {"ok", "fresh", "complete", "ready", ""}:
        return status or "ok", 12, []
    if status in {"partial", "mixed", "needs_review"}:
        return status, -12, []
    if status in BLOCKING_GAP_STATUSES:
        return status, -45, [_text(row.get("data_status") or status)]
    return status, 0, []


def _provider_gaps(row: Mapping[str, object]) -> list[object]:
    return _as_list(
        row.get("provider_data_gaps")
        or row.get("provider_gaps")
        or row.get("data_gaps")
        or row.get("provider_blockers")
    )


def _gap_label(gap: object) -> str:
    if isinstance(gap, Mapping):
        return " ".join(
            part
            for part in (
                _text(gap.get("provider") or gap.get("source")),
                _text(gap.get("field") or gap.get("endpoint")),
                _text(gap.get("latest_issue") or gap.get("message") or gap.get("status")),
            )
            if part
        ) or "Provider/data gap"
    return _text(gap)


def _event_context(row: Mapping[str, object], as_of: date) -> tuple[dict[str, object], int]:
    context = _as_dict(row.get("earnings_event_context") or row.get("event_context") or row.get("earnings_context"))
    event_date = _parse_date(
        context.get("earnings_date")
        or context.get("event_date")
        or row.get("earnings_date")
        or row.get("event_date")
    )
    explicit_days = row.get("event_proximity_days")
    if explicit_days is not None:
        days = int(_number(explicit_days))
    elif event_date:
        days = (event_date - as_of).days
    else:
        days = 999
    if event_date and "event_date" not in context:
        context["event_date"] = event_date.isoformat()
    if abs(days) <= 2:
        score = 18
    elif abs(days) <= 7:
        score = 12
    elif abs(days) <= 20:
        score = 5
    else:
        score = 0
    context.setdefault("event_proximity_days", days if days != 999 else None)
    return context, score


def _catalyst_context(row: Mapping[str, object]) -> tuple[dict[str, object], int]:
    context = _as_dict(row.get("catalyst_context"))
    strength = _token(context.get("strength") or row.get("catalyst_strength"))
    if not context and strength:
        context["strength"] = strength
    if strength in {"strong", "high"}:
        return context, 18
    if strength in {"medium", "moderate"}:
        return context, 10
    if strength in {"weak", "low"}:
        return context, -8
    return context, 0


def _outcome_score(row: Mapping[str, object]) -> tuple[dict[str, object], int]:
    history = _as_dict(row.get("outcome_history") or row.get("prior_tactical_outcomes"))
    label = _token(history.get("label") or history.get("status"))
    win_rate = _number(history.get("win_rate"))
    sample_size = _number(history.get("sample_size"))
    if label in {"strong", "positive"} or (sample_size >= 3 and win_rate >= 0.6):
        return history, 10
    if label in {"weak", "negative"} or (sample_size >= 3 and 0 < win_rate < 0.4):
        return history, -12
    return history, 0


def _no_setup(row: Mapping[str, object]) -> bool:
    return _token(row.get("setup_label") or row.get("setup_type")) in {"", "none", "no_setup"} and not _text(
        row.get("catalyst_strength") or row.get("setup_confidence")
    )


def _review_action(
    row: Mapping[str, object],
    *,
    setup_label: str,
    confidence_label: str,
    risk_label: str,
    data_blockers: list[str],
) -> str:
    explicit = _token(row.get("review_action"))
    if explicit in TACTICAL_REVIEW_ACTIONS:
        return explicit
    if data_blockers:
        return "data_gap_review"
    if setup_label == "no_setup" or confidence_label in {"none", "unknown"}:
        return "avoid_for_now"
    if risk_label == "extreme":
        return "avoid_for_now"
    if setup_label in {"reversal"} and confidence_label == "low":
        return "wait_for_confirmation"
    side = _token(row.get("side") or row.get("tactical_side") or row.get("setup_side"))
    if side in {"sell", "trim", "exit"}:
        return "tactical_sell_review"
    if _normalized_horizon(row.get("tactical_horizon") or row.get("horizon")) == "1_day" and confidence_label == "medium":
        return "watch_intraday"
    if confidence_label in {"high", "medium"}:
        return "tactical_buy_review"
    return "wait_for_confirmation"


def _priority_components(row: Mapping[str, object], as_of: date) -> dict[str, object]:
    setup_label = _setup_label(row)
    confidence_label, confidence_points = _confidence_score(row.get("setup_confidence") or row.get("confidence"))
    risk_label, risk_points = _risk_score(row.get("risk_zone_label") or row.get("risk_zone"))
    data_quality_label, data_points, data_blockers = _data_quality_score(row)
    event_context, event_points = _event_context(row, as_of)
    catalyst_context, catalyst_points = _catalyst_context(row)
    outcome_history, outcome_points = _outcome_score(row)
    action = _review_action(
        row,
        setup_label=setup_label,
        confidence_label=confidence_label,
        risk_label=risk_label,
        data_blockers=data_blockers,
    )
    horizon = _normalized_horizon(row.get("tactical_horizon") or row.get("horizon"))
    horizon_points = {"1_day": 6, "5_trading_days": 4, "20_trading_days": 2}.get(horizon, 0)
    action_points = {
        "tactical_buy_review": 8,
        "tactical_sell_review": 6,
        "watch_intraday": 4,
        "wait_for_confirmation": -8,
        "data_gap_review": -30,
        "avoid_for_now": -45,
    }[action]
    setup_points = 8 if setup_label in {"momentum", "breakout", "post_earnings_reaction", "pre_earnings_setup", "news_catalyst"} else 0
    score = (
        confidence_points
        + risk_points
        + data_points
        + event_points
        + catalyst_points
        + outcome_points
        + horizon_points
        + action_points
        + setup_points
    )
    return {
        "setup_label": setup_label,
        "tactical_horizon": horizon,
        "setup_confidence": confidence_label,
        "risk_zone_label": risk_label,
        "data_quality_label": data_quality_label,
        "data_blockers": data_blockers,
        "earnings_event_context": event_context,
        "catalyst_context": catalyst_context,
        "outcome_history": outcome_history,
        "review_action": action,
        "priority_score": round(score, 4),
        "priority_components": {
            "setup_confidence": confidence_points,
            "risk_zone": risk_points,
            "data_quality": data_points,
            "event_proximity": event_points,
            "catalyst_strength": catalyst_points,
            "outcome_history": outcome_points,
            "tactical_horizon": horizon_points,
            "review_action": action_points,
            "setup_type": setup_points,
        },
    }


def _invalidation_condition(row: Mapping[str, object], action: str, data_blockers: list[str]) -> str:
    explicit = _text(row.get("invalidation_condition"))
    if explicit:
        return explicit
    if data_blockers:
        return "Do not review tactically until provider/data gaps are resolved."
    if action == "avoid_for_now":
        return "No actionable setup; review again only if trend, event, or catalyst context improves."
    if action == "wait_for_confirmation":
        return "Invalidated if confirmation does not arrive before the tactical horizon expires."
    return "Invalidated if price action, catalyst context, or risk zone moves against the setup."


def _queue_row(row: Mapping[str, object], source_index: int, as_of: date) -> dict[str, object]:
    components = _priority_components(row, as_of)
    action = _text(components["review_action"])
    data_blockers = list(components["data_blockers"]) if isinstance(components["data_blockers"], list) else []
    provider_gaps = [_gap_label(gap) for gap in _provider_gaps(row)]
    return {
        "symbol": _text(row.get("symbol")).upper(),
        "setup_label": components["setup_label"],
        "tactical_horizon": components["tactical_horizon"],
        "review_action": action,
        "setup_confidence": components["setup_confidence"],
        "risk_zone_label": components["risk_zone_label"],
        "invalidation_condition": _invalidation_condition(row, action, data_blockers),
        "earnings_event_context": components["earnings_event_context"],
        "catalyst_context": components["catalyst_context"],
        "provider_data_gaps": provider_gaps,
        "priority_rank": 0,
        "priority_score": components["priority_score"],
        "priority_components": components["priority_components"],
        "outcome_history": components["outcome_history"],
        "long_term_context": _as_dict(row.get("long_term_context")),
        "data_quality_label": components["data_quality_label"],
        "review_only": True,
        "recommendation_only": True,
        "does_not_override_long_term": True,
        "decision_mode": "tactical_trade",
        "source_index": source_index,
        "note": RECOMMENDATION_ONLY_NOTE,
    }


def build_tactical_watchlist_queue(
    setups: Iterable[Mapping[str, object]],
    *,
    as_of_date: date | str | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    """Rank short-term tactical review setups without changing long-term recommendations."""

    as_of = _as_of_date(as_of_date)
    copied = [copy.deepcopy(dict(row)) for row in setups]
    rows = [_queue_row(row, index, as_of) for index, row in enumerate(copied)]
    rows.sort(
        key=lambda row: (
            -_number(row.get("priority_score")),
            int(_number(row.get("source_index"))),
            _text(row.get("symbol")),
        )
    )
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    for rank, row in enumerate(rows, start=1):
        row["priority_rank"] = rank
    return {
        "review_only": True,
        "recommendation_only": True,
        "does_not_override_long_term": True,
        "decision_mode": "tactical_trade",
        "rows": rows,
        "excluded": [],
        "note": RECOMMENDATION_ONLY_NOTE,
    }


__all__ = [
    "RECOMMENDATION_ONLY_NOTE",
    "SETUP_LABELS",
    "TACTICAL_HORIZONS",
    "TACTICAL_REVIEW_ACTIONS",
    "build_tactical_watchlist_queue",
]
