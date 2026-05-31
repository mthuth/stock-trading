"""Review-only best-add fallback selection for long-term deployment."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping


BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}
LONG_TERM_SLEEVES = {"long_term", "long_term_core"}
ACCEPTABLE_TARGET_CONFIDENCE = {"medium", "high"}
REVIEW_ONLY_NOTE = (
    "Review-only best-add fallback context. This helper chooses from existing "
    "recommendation outputs and must not change scores, action labels, targets, "
    "target confidence, decision-safety rules, allocation formulas, broker behavior, "
    "or trading behavior."
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


def boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return text(value).lower() in {"1", "true", "yes", "ready", "safe"}


def as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def row_value(row: Mapping[str, object], key: str) -> object:
    if key in row:
        return row.get(key)
    item = row.get("input")
    return getattr(item, key, "")


def symbol_for_row(row: Mapping[str, object]) -> str:
    return text(row_value(row, "symbol")).upper()


def candidate_context(row: Mapping[str, object], rank: int) -> dict[str, object]:
    allocation = as_mapping(row.get("allocation_safety"))
    suggested_amount = row.get("suggested_amount")
    if suggested_amount is None:
        suggested_amount = allocation.get("suggested_amount")
    return {
        "rank": int(to_float(row.get("rank") or rank, rank)),
        "symbol": symbol_for_row(row),
        "company": text(row_value(row, "company")),
        "sleeve": text(row_value(row, "sleeve")),
        "trade_type": text(row_value(row, "trade_type")),
        "action": text(row.get("action")),
        "score": to_float(row.get("score")),
        "target_confidence": text(row.get("target_confidence") or row.get("confidence")),
        "data_status": text(row.get("data_status")),
        "suggested_amount": round(to_float(suggested_amount), 2) if suggested_amount is not None else None,
        "rationale": text(row.get("rationale") or row.get("why")),
    }


def decision_gate_for_row(
    row: Mapping[str, object],
    decision_gates_by_symbol: Mapping[str, Mapping[str, object]],
) -> Mapping[str, object]:
    gate = row.get("decision_gate") or row.get("decision_safety")
    if isinstance(gate, Mapping):
        return gate
    return decision_gates_by_symbol.get(symbol_for_row(row), {})


def provider_blockers_by_symbol(provider_gaps: Iterable[Mapping[str, object]]) -> dict[str, list[str]]:
    blockers: dict[str, list[str]] = defaultdict(list)
    for gap in provider_gaps:
        if bool(gap.get("expected_gap")):
            continue
        symbol = text(gap.get("symbol")).upper()
        if not symbol or symbol == "GLOBAL":
            continue
        status = text(gap.get("status")).lower()
        severity = text(gap.get("severity")).lower()
        issue_type = text(gap.get("issue_type")).lower()
        if status not in {"blocked", "rate_limited"} and severity != "blocker" and "blocked" not in issue_type:
            continue
        provider = text(gap.get("provider"), "Provider")
        field_name = text(gap.get("field_name") or gap.get("endpoint"), "field")
        latest_issue = text(gap.get("latest_issue") or gap.get("message") or status)
        blockers[symbol].append(f"{provider} {field_name}: {latest_issue}")
    return blockers


def gate_reasons(gate: Mapping[str, object]) -> list[str]:
    raw = gate.get("reasons") or gate.get("decision_gate_reasons") or []
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, Iterable):
        return [text(reason) for reason in raw if text(reason)]
    return []


def watchlist_policy_for_row(row: Mapping[str, object], gate: Mapping[str, object]) -> Mapping[str, object]:
    row_policy = row.get("watchlist_policy")
    if isinstance(row_policy, Mapping):
        return row_policy
    gate_policy = gate.get("watchlist_policy")
    return gate_policy if isinstance(gate_policy, Mapping) else {}


def allocation_reasons(row: Mapping[str, object]) -> list[str]:
    allocation = as_mapping(row.get("allocation_safety"))
    reasons = allocation.get("reduction_reasons") or []
    if isinstance(reasons, str):
        return [reasons] if reasons else []
    if isinstance(reasons, Iterable):
        return [text(reason) for reason in reasons if text(reason)]
    return []


def review_reasons_for_candidate(
    row: Mapping[str, object],
    *,
    rank: int,
    gate: Mapping[str, object],
    provider_blockers: Mapping[str, list[str]],
) -> list[str]:
    context = candidate_context(row, rank)
    reasons: list[str] = []
    action = text(context.get("action"))
    sleeve = text(context.get("sleeve"))
    confidence = text(context.get("target_confidence")).lower().replace(" ", "_")
    data_status = text(context.get("data_status"))
    symbol = text(context.get("symbol")).upper()

    if sleeve not in LONG_TERM_SLEEVES:
        reasons.append(f"{sleeve or 'unknown'} sleeve is not a long-term add sleeve")
    if action not in BUY_ACTIONS:
        reasons.append(f"{action or 'Current'} action is not a buy/add action")
    if not bool(gate.get("safe_to_buy")):
        reasons.extend(gate_reasons(gate) or [text(gate.get("summary"), "Decision safety is not ready")])
    watchlist_policy = watchlist_policy_for_row(row, gate)
    if boolish(watchlist_policy.get("blocked")):
        reasons.append(text(watchlist_policy.get("reason"), "Watchlist-only policy blocks buy-readiness."))
    if confidence and confidence not in ACCEPTABLE_TARGET_CONFIDENCE:
        reasons.append(f"{text(context.get('target_confidence')).title()} target confidence")
    if data_status.startswith("Needs"):
        reasons.append(data_status)
    elif data_status in {"Wide range", "Partial blend"}:
        reasons.append(data_status)

    suggested_amount = context.get("suggested_amount")
    if isinstance(suggested_amount, (int, float)) and suggested_amount <= 0:
        reasons.extend(allocation_reasons(row) or ["No allocation capacity available"])

    for blocker in provider_blockers.get(symbol, []):
        reasons.append(f"Provider blocker: {blocker}")

    return list(dict.fromkeys(reason for reason in reasons if reason))


def candidate_review(
    row: Mapping[str, object],
    *,
    rank: int,
    gate: Mapping[str, object],
    provider_blockers: Mapping[str, list[str]],
) -> dict[str, object]:
    context = candidate_context(row, rank)
    reasons = review_reasons_for_candidate(row, rank=rank, gate=gate, provider_blockers=provider_blockers)
    context.update(
        {
            "decision_safe": bool(gate.get("safe_to_buy")) and not reasons,
            "decision_gate_status": text(gate.get("status"), "Ready" if bool(gate.get("safe_to_buy")) else "Blocked"),
            "blocked_reasons": reasons,
        }
    )
    return context


def long_term_add_candidates(rows: Iterable[Mapping[str, object]]) -> list[tuple[int, Mapping[str, object]]]:
    candidates: list[tuple[int, Mapping[str, object]]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            continue
        sleeve = text(row_value(row, "sleeve"))
        action = text(row.get("action"))
        if sleeve in LONG_TERM_SLEEVES and action in BUY_ACTIONS:
            candidates.append((index, row))
    return candidates


def build_best_add_fallback_review(
    ranked_rows: Iterable[Mapping[str, object]],
    *,
    decision_gates_by_symbol: Mapping[str, Mapping[str, object]] | None = None,
    provider_gap_records: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Select a review-only primary/fallback long-term add from existing rows."""

    decision_gates = decision_gates_by_symbol or {}
    provider_blockers = provider_blockers_by_symbol(provider_gap_records)
    candidates = long_term_add_candidates(ranked_rows)
    skipped: list[dict[str, object]] = []
    primary: dict[str, object] | None = None
    fallback: dict[str, object] | None = None
    blocked_top: dict[str, object] | None = None

    for index, (rank, row) in enumerate(candidates):
        gate = decision_gate_for_row(row, decision_gates)
        review = candidate_review(row, rank=rank, gate=gate, provider_blockers=provider_blockers)
        if index == 0:
            if review["decision_safe"]:
                primary = review
                break
            blocked_top = review
            skipped.append(review)
            continue
        if review["decision_safe"]:
            fallback = review
            break
        skipped.append(review)

    if primary:
        mode = "primary_add"
        hold_reason = "Top-ranked long-term add is decision-safe."
        hold_capacity = False
    elif fallback:
        mode = "fallback_add"
        hold_reason = "Top-ranked long-term add is blocked; fallback candidate is decision-safe."
        hold_capacity = False
    else:
        mode = "hold_capacity"
        hold_capacity = True
        if blocked_top:
            hold_reason = "No decision-safe fallback add is available; hold buy capacity for review."
        else:
            hold_reason = "No long-term buy/add candidates are available; hold buy capacity for review."

    return {
        "review_only": True,
        "mode": mode,
        "primary_add": primary,
        "fallback_add": fallback,
        "hold_capacity": {
            "recommended": hold_capacity,
            "reason": hold_reason,
        },
        "blocked_top_candidate": blocked_top,
        "skipped_candidates": skipped,
        "candidate_count": len(candidates),
        "notes": REVIEW_ONLY_NOTE,
    }


__all__ = [
    "BUY_ACTIONS",
    "LONG_TERM_SLEEVES",
    "build_best_add_fallback_review",
    "long_term_add_candidates",
]
