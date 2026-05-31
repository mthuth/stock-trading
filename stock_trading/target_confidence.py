#!/usr/bin/env python3
"""Target confidence calibration rules.

The calibrator labels target trust without changing target-blending math. It is
kept separate from the analysis engine so confidence changes can be reviewed as
their own product contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


CONFIDENCE_LABELS = ("high", "medium", "low", "needs_review")
SEVERE_PROVIDER_STATUSES = {"blocked", "rate_limited", "error", "parser_gap"}
STALE_TARGET_DAYS = 90
SEVERE_STALE_TARGET_DAYS = 180
WIDE_RANGE_PCT = 45.0


@dataclass(frozen=True)
class TargetConfidenceResult:
    label: str
    reason_codes: tuple[str, ...]


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: object) -> str:
    return str(value or "").strip()


def _gap_value(row: object, key: str) -> str:
    if isinstance(row, Mapping):
        return _text(row.get(key))
    try:
        return _text(row[key])  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return ""


def _is_target_relevant_gap(row: object) -> bool:
    field = _gap_value(row, "field_name").lower()
    provider = _gap_value(row, "provider").lower()
    message = _gap_value(row, "message").lower()
    text = " ".join([field, provider, message])
    keywords = (
        "target",
        "price",
        "quote",
        "fundamental",
        "estimate",
        "eps",
        "revenue",
        "companyfacts",
        "sec",
        "price_history",
        "history",
        "technical",
    )
    return any(keyword in text for keyword in keywords)


def _source_types(rows: Iterable[Mapping[str, object]]) -> set[str]:
    return {
        _text(row.get("target_type")).lower()
        for row in rows
        if _text(row.get("target_type"))
    }


def _source_names(rows: Iterable[Mapping[str, object]]) -> set[str]:
    return {
        _text(row.get("source_name")).lower()
        for row in rows
        if _text(row.get("source_name"))
    }


def _has_supporting_context(item: object | None) -> bool:
    if item is None:
        return False
    support_fields = (
        "estimate_source",
        "eps_estimate",
        "revenue_estimate",
        "sentiment_source",
        "news_sentiment",
    )
    return any(bool(_text(getattr(item, field, ""))) for field in support_fields)


def _is_speculative(item: object | None) -> bool:
    if item is None:
        return False
    values = (
        getattr(item, "sleeve", ""),
        getattr(item, "trade_type", ""),
        getattr(item, "category", ""),
    )
    text = " ".join(_text(value).lower() for value in values)
    return "speculative" in text


def calibrate_target_confidence(
    target_rows: Iterable[Mapping[str, object]],
    *,
    current_price: float,
    item: object | None = None,
    provider_gaps: Iterable[object] = (),
    technical_target_needed_for_high: bool = True,
    wide_range_downgrades_confidence: bool = True,
) -> TargetConfidenceResult:
    """Return a calibrated target-confidence label and reason codes."""

    rows = [
        row
        for row in target_rows
        if _to_float(row.get("target_price")) > 0
    ]
    reason_codes: list[str] = []

    if current_price <= 0:
        reason_codes.append("missing_current_price")
        return TargetConfidenceResult("needs_review", tuple(reason_codes))
    if not rows:
        reason_codes.append("missing_target_input")
        return TargetConfidenceResult("needs_review", tuple(reason_codes))

    target_types = _source_types(rows)
    source_names = _source_names(rows)
    manual_rows = [
        row
        for row in rows
        if "manual" in _text(row.get("source_type")).lower()
        or "manual" in _text(row.get("source_name")).lower()
    ]
    manual_only = len(manual_rows) == len(rows)
    has_stale_price = "stale" in _text(getattr(item, "price_source", "")).lower()
    stale_days = max((_to_float(row.get("freshness_days")) for row in rows), default=0.0)
    has_stale_target = stale_days > STALE_TARGET_DAYS
    has_severe_stale_target = stale_days > SEVERE_STALE_TARGET_DAYS
    has_wide_range = False
    if wide_range_downgrades_confidence:
        lows = [_to_float(row.get("target_low")) for row in rows if _to_float(row.get("target_low")) > 0]
        highs = [_to_float(row.get("target_high")) for row in rows if _to_float(row.get("target_high")) > 0]
        prices = [_to_float(row.get("target_price")) for row in rows if _to_float(row.get("target_price")) > 0]
        if lows and highs:
            has_wide_range = ((max(highs + prices) - min(lows + prices)) / current_price) * 100 > WIDE_RANGE_PCT

    same_symbol_gaps = list(provider_gaps)
    target_relevant_gaps = [row for row in same_symbol_gaps if _is_target_relevant_gap(row)]
    severe_target_gaps = [
        row
        for row in target_relevant_gaps
        if _gap_value(row, "status").lower().replace(" ", "_") in SEVERE_PROVIDER_STATUSES
    ]

    if manual_only:
        reason_codes.append("manual_only_target")
    if len(target_types) <= 1:
        reason_codes.append("single_source_target")
    if "fundamental" not in target_types:
        reason_codes.append("missing_fundamental_target")
    if "technical" not in target_types:
        reason_codes.append("missing_price_history_target")
    if has_stale_target:
        reason_codes.append("stale_target")
    if has_stale_price:
        reason_codes.append("stale_current_price")
    if has_wide_range:
        reason_codes.append("wide_range_disagreement")
    if target_relevant_gaps:
        reason_codes.append("provider_gap_affects_target")
    if _is_speculative(item):
        reason_codes.append("speculative_watchlist_conservative")

    if severe_target_gaps or has_severe_stale_target:
        return TargetConfidenceResult("needs_review", tuple(dict.fromkeys(reason_codes)))

    source_confidences = {_text(row.get("confidence")).lower() for row in rows}
    strong_single_source = (
        len(rows) == 1
        and next(iter(source_confidences or {"low"})) in {"high", "medium"}
        and _has_supporting_context(item)
        and not (manual_only or has_stale_target or has_stale_price or has_wide_range or target_relevant_gaps)
    )
    full_fresh_breadth = (
        len(target_types) >= 3
        and len(source_names) >= 2
        and not (manual_only or has_stale_target or has_stale_price or has_wide_range or target_relevant_gaps)
    )
    sufficient_high_breadth = len(target_types) >= 2 and len(source_names) >= 2
    if technical_target_needed_for_high:
        sufficient_high_breadth = sufficient_high_breadth and "technical" in target_types

    if full_fresh_breadth and sufficient_high_breadth and "fundamental" in target_types:
        label = "high"
        reason_codes.append("multi_source_fresh_breadth")
    elif (len(target_types) >= 2 and not (has_stale_target or has_stale_price or has_wide_range or target_relevant_gaps)) or strong_single_source:
        label = "medium"
        if strong_single_source:
            reason_codes.append("strong_single_source_with_support")
        else:
            reason_codes.append("partial_fresh_blend")
    else:
        label = "low"
        reason_codes.append("conservative_confidence")

    if _is_speculative(item) and label == "high":
        label = "medium"
        reason_codes.append("speculative_cap")

    return TargetConfidenceResult(label, tuple(dict.fromkeys(reason_codes)))


__all__ = [
    "CONFIDENCE_LABELS",
    "TargetConfidenceResult",
    "calibrate_target_confidence",
]
