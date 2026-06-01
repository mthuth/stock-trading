"""Deterministic Top 5 opportunity view built from existing recommendation output."""

from __future__ import annotations

import copy
from typing import Iterable, Mapping


BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}
READY_STATUSES = {"ready", "safe", "allowed", "pass", "passed", "decision_safe"}
BLOCKED_STATUSES = {"blocked", "not_ready", "not ready", "failed", "fail"}
CORE_MEGA_CAP_SYMBOLS = {"AAPL", "AMZN", "AVGO", "GOOG", "GOOGL", "META", "MSFT", "NVDA", "TSM"}
ETF_SYMBOLS = {"QQQ", "QQQM", "SMH", "VGT", "XLK", "SPY", "VOO"}
RELIABILITY_BLOCKER_NOTE = (
    "Missing price/provider data lowers confidence or readiness; it is not a bearish thesis by itself."
)
RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only Top 5 opportunity view. It selects from existing recommendation, "
    "decision-safety, target-confidence, allocation, provider-gap, and review-only context "
    "but does not change official rankings, scores, actions, targets, decision gates, "
    "suggested amounts, allocation rules, broker behavior, or trading."
)


def _as_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _optional_number(value: object) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "ready", "safe", "allowed"}
    return bool(value)


def _source_rank(row: Mapping[str, object], index: int) -> tuple[int, int]:
    rank = _number(row.get("rank") or row.get("source_rank"), 0)
    return (int(rank) if rank > 0 else index + 1, index)


def _normalized_symbol(row: Mapping[str, object]) -> str:
    return _text(row.get("symbol")).upper()


def _first_text(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _decision_gate(row: Mapping[str, object]) -> dict[str, object]:
    gate = _as_dict(row.get("decision_gate"))
    if gate:
        return gate
    status = _first_text(row, "decision_gate_status", "decision_status", "gate_status")
    safe = row.get("safe_to_buy")
    if safe is None:
        safe_to_buy = status.lower() in READY_STATUSES
    else:
        safe_to_buy = _truthy(safe)
    return {
        "safe_to_buy": safe_to_buy,
        "status": status or ("Ready" if safe_to_buy else "Blocked"),
        "reasons": _as_list(row.get("blocked_reasons") or row.get("decision_gate_reasons")),
        "summary": _first_text(row, "decision_gate_summary", "summary"),
    }


def _watchlist_blocker(row: Mapping[str, object]) -> str:
    policy = _as_dict(row.get("watchlist_policy"))
    if policy.get("blocked") is not None and _truthy(policy.get("blocked")):
        return _text(policy.get("reason")) or "Watchlist-only policy blocks buy-readiness."
    if _truthy(row.get("watchlist_only_blocked")):
        return _text(row.get("watchlist_only_reason")) or "Watchlist-only policy blocks buy-readiness."
    return ""


def _list_texts(*values: object) -> list[str]:
    items: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            items.extend(_text(item) for item in value if _text(item))
        elif _text(value):
            items.append(_text(value))
    return list(dict.fromkeys(item for item in items if item))


def _provider_gap_lookup(provider_gap_rows: Iterable[Mapping[str, object]] | None) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    for row in provider_gap_rows or []:
        item = _as_dict(row)
        symbol = _text(item.get("symbol")).upper()
        if not symbol:
            continue
        detail = _first_text(
            item,
            "decision_context",
            "latest_detail",
            "likely_cause",
            "next_action",
            "provider",
            "field",
        )
        if detail:
            lookup.setdefault(symbol, []).append(detail)
    return lookup


def _data_gap_summary(row: Mapping[str, object], provider_gaps: Mapping[str, list[str]]) -> str:
    symbol = _normalized_symbol(row)
    explicit = _list_texts(
        row.get("data_gap_summary"),
        row.get("provider_gap_summary"),
        row.get("provider_gaps"),
        row.get("data_gaps"),
        row.get("data_blockers"),
        row.get("provider_blockers"),
    )
    explicit.extend(provider_gaps.get(symbol, []))
    data_status = _first_text(row, "data_status", "target_status")
    if data_status and _is_data_gap_status(data_status):
        explicit.append(data_status)
    if explicit:
        return "; ".join(list(dict.fromkeys(explicit)))
    return "No major data gaps found."


def _is_data_gap_status(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in ("missing", "needs", "stale", "gap", "blocked", "unavailable"))


def _blocked_reasons(
    row: Mapping[str, object],
    gate: Mapping[str, object],
    data_gap_summary: str,
) -> list[str]:
    reasons = _list_texts(
        gate.get("reasons"),
        row.get("blocked_reasons"),
        row.get("key_blockers"),
        row.get("key_risks_blockers"),
        row.get("provider_data_blockers"),
    )
    watchlist = _watchlist_blocker(row)
    if watchlist:
        reasons.append(watchlist)
    action = _text(row.get("action"))
    if action and action not in BUY_ACTIONS:
        reasons.append(f"{action} action is not buy-ready.")
    confidence = _first_text(row, "target_confidence", "confidence")
    if confidence.lower() in {"low", "needs review", "unavailable"}:
        reasons.append(f"Target confidence is {confidence}.")
    if data_gap_summary and data_gap_summary != "No major data gaps found.":
        reasons.append(data_gap_summary)
    return list(dict.fromkeys(reason for reason in reasons if reason))


def _opportunity_bucket(row: Mapping[str, object]) -> str:
    symbol = _normalized_symbol(row)
    mode = _text(row.get("decision_mode")).lower()
    sleeve = _text(row.get("sleeve")).lower()
    trade_type = _text(row.get("trade_type")).lower()
    category = _text(row.get("category")).lower()

    if symbol in ETF_SYMBOLS or sleeve in {"etf", "etf_context"} or "etf" in category:
        return "etf_context"
    if "earnings" in mode or "earnings" in trade_type or row.get("earnings_event"):
        return "earnings_review"
    if "tactical" in mode or "tactical" in sleeve or "tactical" in trade_type:
        return "tactical_review"
    if "speculative" in mode or "speculative" in sleeve or _watchlist_blocker(row):
        return "speculative_watchlist"
    if "higher_upside" in category or "high upside" in category:
        return "higher_upside"
    if symbol in CORE_MEGA_CAP_SYMBOLS:
        return "core_mega_cap"
    if sleeve in {"long_term", "long_term_core"} or mode == "long_term_buy_add":
        return "long_term_core"
    return "unknown"


def _is_core_bucket(bucket: str) -> bool:
    return bucket in {"core_mega_cap", "long_term_core"}


def _is_higher_upside_bucket(bucket: str) -> bool:
    return bucket in {"higher_upside", "speculative_watchlist"}


def _capital_action(
    *,
    action: str,
    safe_to_buy: bool,
    suggested_amount: float | None,
    blocked_reasons: list[str],
) -> str:
    if blocked_reasons or not safe_to_buy or action not in BUY_ACTIONS:
        return "blocked"
    if suggested_amount is not None and suggested_amount > 0:
        return "deploy"
    if suggested_amount == 0:
        return "hold_capacity"
    return "review_only"


def _top_reason(row: Mapping[str, object], bucket: str, safe_to_buy: bool) -> str:
    explicit = _first_text(
        row,
        "top_reason",
        "why_this",
        "why_now",
        "why_this_is_in_queue",
        "rationale",
        "why",
        "notes",
    )
    if explicit:
        return explicit
    if safe_to_buy:
        return "Decision-safe candidate from the existing ranked recommendation output."
    if bucket == "core_mega_cap":
        return "Core mega-cap candidate from the existing ranked recommendation output."
    if bucket in {"higher_upside", "speculative_watchlist"}:
        return "Higher-upside candidate surfaced for review with strict readiness gates."
    return "Existing ranked recommendation candidate kept visible for review."


def _top_blocker(blocked_reasons: list[str], data_gap_summary: str) -> str:
    if data_gap_summary != "No major data gaps found." and _is_data_gap_status(data_gap_summary):
        return RELIABILITY_BLOCKER_NOTE
    return blocked_reasons[0] if blocked_reasons else ""


def _top5_row(
    row: Mapping[str, object],
    *,
    display_rank: int,
    source_rank: int,
    provider_gaps: Mapping[str, list[str]],
) -> dict[str, object]:
    gate = _decision_gate(row)
    action = _text(row.get("action"))
    data_gap = _data_gap_summary(row, provider_gaps)
    blocked_reasons = _blocked_reasons(row, gate, data_gap)
    safe_to_buy = bool(gate.get("safe_to_buy")) and not blocked_reasons and action in BUY_ACTIONS
    status = _text(gate.get("status")) or ("Ready" if safe_to_buy else "Blocked")
    if status.lower() in BLOCKED_STATUSES:
        safe_to_buy = False
    allocation = _as_dict(row.get("allocation_safety"))
    suggested_amount = _optional_number(row.get("suggested_amount"))
    if suggested_amount is None:
        suggested_amount = _optional_number(allocation.get("suggested_amount"))
    bucket = _opportunity_bucket(row)
    top_blocker = _top_blocker(blocked_reasons, data_gap)
    return {
        "rank": display_rank,
        "source_rank": source_rank,
        "symbol": _normalized_symbol(row),
        "company": _text(row.get("company")),
        "opportunity_bucket": bucket,
        "action": action,
        "score": row.get("score"),
        "decision_gate_status": status,
        "safe_to_buy": safe_to_buy,
        "blocked_reasons": blocked_reasons,
        "target_confidence": _first_text(row, "target_confidence", "confidence"),
        "data_status": _first_text(row, "data_status", "target_status") or ("Needs review" if data_gap else ""),
        "suggested_amount": suggested_amount,
        "capital_action": _capital_action(
            action=action,
            safe_to_buy=safe_to_buy,
            suggested_amount=suggested_amount,
            blocked_reasons=blocked_reasons,
        ),
        "top_reason": _top_reason(row, bucket, safe_to_buy),
        "top_blocker": top_blocker,
        "data_gap_summary": data_gap,
        "why_now": _text(row.get("why_now")),
        "why_this": _text(row.get("why_this")),
        "review_only": True,
        "recommendation_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


def _unique_ranked_rows(candidates: Iterable[Mapping[str, object]]) -> list[tuple[int, Mapping[str, object]]]:
    copied = [copy.deepcopy(dict(row)) for row in candidates if isinstance(row, Mapping)]
    sorted_rows = sorted(enumerate(copied), key=lambda indexed: _source_rank(indexed[1], indexed[0]))
    seen: set[str] = set()
    unique: list[tuple[int, Mapping[str, object]]] = []
    for original_index, row in sorted_rows:
        symbol = _normalized_symbol(row)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        source_rank = int(_number(row.get("rank") or row.get("source_rank"), original_index + 1))
        unique.append((source_rank, row))
    return unique


def _include_category(
    selected: list[tuple[int, Mapping[str, object]]],
    all_rows: list[tuple[int, Mapping[str, object]]],
    predicate,
    *,
    limit: int,
) -> list[tuple[int, Mapping[str, object]]]:
    if any(predicate(_opportunity_bucket(row)) for _, row in selected):
        return selected
    candidate = next(((rank, row) for rank, row in all_rows if predicate(_opportunity_bucket(row))), None)
    if candidate is None or candidate in selected:
        return selected
    if len(selected) < limit:
        selected.append(candidate)
    else:
        replace_index = next(
            (
                index
                for index in range(len(selected) - 1, -1, -1)
                if not _is_core_bucket(_opportunity_bucket(selected[index][1]))
                and not _is_higher_upside_bucket(_opportunity_bucket(selected[index][1]))
            ),
            len(selected) - 1,
        )
        selected[replace_index] = candidate
    return sorted(selected, key=lambda item: item[0])


def build_top5_opportunities(
    candidates: Iterable[Mapping[str, object]],
    *,
    provider_gap_rows: Iterable[Mapping[str, object]] | None = None,
    limit: int = 5,
) -> dict[str, object]:
    """Build a review-only Top 5 opportunity view from already-computed candidates."""

    limit = max(1, limit)
    ranked_rows = _unique_ranked_rows(candidates)
    selected = ranked_rows[:limit]
    selected = _include_category(selected, ranked_rows, _is_core_bucket, limit=limit)
    selected = _include_category(selected, ranked_rows, _is_higher_upside_bucket, limit=limit)
    selected = sorted(selected, key=lambda item: item[0])[:limit]
    provider_gaps = _provider_gap_lookup(provider_gap_rows)
    rows = [
        _top5_row(row, display_rank=index, source_rank=source_rank, provider_gaps=provider_gaps)
        for index, (source_rank, row) in enumerate(selected, start=1)
    ]
    safe_rows = [row for row in rows if row.get("safe_to_buy")]
    deploy_rows = [row for row in rows if row.get("capital_action") == "deploy"]
    blocked_rows = [row for row in rows if row.get("capital_action") == "blocked"]
    missing_data_rows = [
        row
        for row in rows
        if _is_data_gap_status(_text(row.get("data_status")))
        or _text(row.get("data_gap_summary")) != "No major data gaps found."
    ]
    summary_capital_action = "deploy" if deploy_rows else "hold_capacity" if not safe_rows else "review_only"
    return {
        "review_only": True,
        "recommendation_only": True,
        "question": "What are the top 5 ranked opportunities today?",
        "result": "top5_available" if rows else "no_ranked_opportunities",
        "capital_action": summary_capital_action,
        "hold_capacity_message": ""
        if safe_rows
        else "Hold buy capacity: no decision-safe Top 5 opportunity is available from existing outputs.",
        "rows": rows,
        "summary": {
            "count": len(rows),
            "safe_to_buy_count": len(safe_rows),
            "blocked_count": len(blocked_rows),
            "missing_data_count": len(missing_data_rows),
            "has_core_mega_cap": any(_is_core_bucket(_text(row.get("opportunity_bucket"))) for row in rows),
            "has_higher_upside": any(_is_higher_upside_bucket(_text(row.get("opportunity_bucket"))) for row in rows),
            "capital_action": summary_capital_action,
        },
        "note": RECOMMENDATION_ONLY_NOTE,
    }


__all__ = [
    "BUY_ACTIONS",
    "CORE_MEGA_CAP_SYMBOLS",
    "RECOMMENDATION_ONLY_NOTE",
    "RELIABILITY_BLOCKER_NOTE",
    "build_top5_opportunities",
]
