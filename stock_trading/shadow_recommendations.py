"""Deterministic shadow recommendation runner helpers.

Shadow outputs are non-authoritative model-comparison artifacts. They read
already-computed recommendation/context rows and must never change official
recommendations, scores, targets, decision gates, allocations, broker behavior,
or trading.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Iterable, Mapping


SHADOW_ACTIONS = {
    "shadow_add",
    "shadow_watch",
    "shadow_avoid",
    "shadow_hold",
    "shadow_tactical_review",
    "shadow_earnings_review",
}
POLICIES = {
    "conservative_long_term",
    "aggressive_growth",
    "risk_skeptic",
    "source_quality_weighted",
    "tactical_momentum",
    "earnings_event",
}
CONFIDENCE_POINTS = {
    "high": 14.0,
    "medium": 5.0,
    "low": -14.0,
    "needs_review": -28.0,
    "not_applicable": -8.0,
}
REVIEW_ONLY_NOTE = (
    "Shadow-only review output. This row must not change official scores, "
    "recommendation labels, targets, target confidence, decision-safety rules, "
    "allocation, source weights, broker behavior, order previews, or trading."
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def token(value: object, default: str = "") -> str:
    return text(value, default).lower().replace("-", "_").replace(" ", "_")


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return token(value) in {"1", "true", "yes", "ready", "safe", "passed", "ok"}


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return copy.deepcopy(list(value))
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def normalized_model_definition(model_definition: Mapping[str, object] | str) -> dict[str, object]:
    if isinstance(model_definition, str):
        model = {"model_name": model_definition, "policy": model_definition}
    else:
        model = copy.deepcopy(dict(model_definition))
    policy = token(model.get("policy") or model.get("model_name") or "conservative_long_term")
    if policy not in POLICIES:
        policy = "conservative_long_term"
    return {
        "model_name": text(model.get("model_name") or policy),
        "model_version": text(model.get("model_version") or model.get("version") or "shadow-v1"),
        "model_role": token(model.get("model_role") or "shadow"),
        "policy": policy,
    }


def recommendation_rows(official_recommendations_or_context: object) -> list[dict[str, object]]:
    if isinstance(official_recommendations_or_context, Mapping):
        for key in ("recommendations", "ranked_rows", "candidates", "rows", "results"):
            value = official_recommendations_or_context.get(key)
            if isinstance(value, list):
                return [copy.deepcopy(dict(row)) for row in value if isinstance(row, Mapping)]
        top = official_recommendations_or_context.get("top_candidate")
        if isinstance(top, Mapping):
            return [copy.deepcopy(dict(top))]
        return []
    if isinstance(official_recommendations_or_context, Iterable) and not isinstance(
        official_recommendations_or_context,
        (str, bytes),
    ):
        return [copy.deepcopy(dict(row)) for row in official_recommendations_or_context if isinstance(row, Mapping)]
    return []


def symbol_key(row: Mapping[str, object]) -> str:
    return text(row.get("symbol")).upper()


def context_by_symbol(context: object, *, row_key: str = "rows") -> dict[str, dict[str, object]]:
    if isinstance(context, Mapping):
        rows = context.get(row_key) if isinstance(context.get(row_key), list) else context.get("items")
        if rows is None and context.get("symbol"):
            rows = [context]
        if rows is None:
            rows = []
    elif isinstance(context, Iterable) and not isinstance(context, (str, bytes)):
        rows = context
    else:
        rows = []
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        if isinstance(row, Mapping):
            symbol = symbol_key(row)
            if symbol:
                result[symbol] = copy.deepcopy(dict(row))
    return result


def source_context_by_symbol(context: object) -> dict[str, dict[str, object]]:
    rows = context_by_symbol(context)
    if rows:
        return rows
    if isinstance(context, Mapping):
        result = {}
        for key, value in context.items():
            if isinstance(value, Mapping):
                result[text(key).upper()] = copy.deepcopy(dict(value))
        return result
    return {}


def provider_gap_count(row: Mapping[str, object]) -> int:
    count = 0
    for key in ("provider_gaps", "provider_blockers", "data_gaps", "data_blockers"):
        value = row.get(key)
        if isinstance(value, list):
            count += len(value)
        elif text(value):
            count += 1
    data_status = token(row.get("data_status") or row.get("target_status"))
    if data_status in {"missing", "stale", "blocked", "needs_review", "provider_gap", "data_gap"}:
        count += 1
    return count


def target_confidence(row: Mapping[str, object]) -> str:
    return token(row.get("target_confidence") or row.get("confidence") or "medium")


def confidence_adjustment(row: Mapping[str, object]) -> float:
    return CONFIDENCE_POINTS.get(target_confidence(row), 0.0)


def decision_blocked(row: Mapping[str, object]) -> bool:
    gate = as_dict(row.get("decision_gate"))
    if gate:
        if gate.get("safe_to_buy") is not None:
            return not boolish(gate.get("safe_to_buy"))
        status = token(gate.get("status"))
        if status:
            return status in {"blocked", "failed", "not_ready", "needs_review"}
    if row.get("safe_to_buy") is not None:
        return not boolish(row.get("safe_to_buy"))
    status = token(row.get("decision_gate_status") or row.get("decision_safety_status"))
    return status in {"blocked", "failed", "not_ready", "needs_review"}


def watchlist_blocked(row: Mapping[str, object]) -> bool:
    policy = as_dict(row.get("watchlist_policy"))
    return boolish(policy.get("blocked")) or boolish(row.get("watchlist_only_blocked"))


def risk_count(row: Mapping[str, object]) -> int:
    count = 0
    for key in ("risk_notes", "risks", "top_risks", "key_risks", "blocked_reasons"):
        value = row.get(key)
        if isinstance(value, list):
            count += len(value)
        elif text(value):
            count += 1
    if token(row.get("risk_level")) in {"high", "extreme"}:
        count += 2
    return count


def upside(row: Mapping[str, object]) -> float:
    raw = row.get("upside_pct")
    if raw is not None:
        return number(raw)
    current = number(row.get("current_price"))
    target = number(row.get("target_price"))
    if current > 0 and target > 0:
        return ((target - current) / current) * 100
    return 0.0


def growth_score(row: Mapping[str, object]) -> float:
    for key in ("growth_score", "revenue_growth_score", "growth_quality", "revenue_growth"):
        if row.get(key) is not None:
            return number(row.get(key))
    return max(0.0, min(30.0, upside(row) * 0.5))


def source_quality_score(row: Mapping[str, object], source_context: Mapping[str, object]) -> tuple[float, list[str]]:
    useful = number(source_context.get("useful_score") or source_context.get("source_usefulness_score"))
    noisy = number(source_context.get("noisy_score") or source_context.get("noise_score"))
    label = token(source_context.get("usefulness_label") or source_context.get("quality_label"))
    notes: list[str] = []
    if label in {"consistently_useful", "useful_context", "useful_but_sparse"}:
        useful += 16
        notes.append(f"Useful source context: {label}.")
    if label in {"noisy", "stale_or_blocked"}:
        noisy += 22
        notes.append(f"Source quality penalty: {label}.")
    return useful - noisy, notes


def tactical_score(context: Mapping[str, object]) -> tuple[float, list[str]]:
    if not context:
        return -8.0, ["No tactical context supplied."]
    label = token(context.get("setup_label") or context.get("setup_type"))
    review_action = token(context.get("review_action") or context.get("recommended_review_action"))
    score = number(context.get("setup_score") or context.get("tactical_score"))
    notes: list[str] = []
    if label in {"momentum", "breakout", "pullback", "post_earnings_reaction", "news_catalyst"}:
        score += 26
        notes.append(f"Tactical setup context: {label}.")
    if review_action in {"tactical_buy_review", "watch_intraday", "wait_for_confirmation"}:
        score += 14
        notes.append(f"Tactical review action: {review_action}.")
    if token(context.get("risk_zone_label")) in {"extended_chase_risk", "high_volatility_event_risk", "data_insufficient"}:
        score -= 18
        notes.append("Tactical risk zone reduces shadow confidence.")
    return score, notes


def earnings_score(context: Mapping[str, object]) -> tuple[float, list[str]]:
    if not context:
        return -8.0, ["No earnings context supplied."]
    label = token(context.get("reaction_label") or context.get("event_type") or context.get("review_window"))
    action = token(context.get("recommended_review_action") or context.get("review_action"))
    score = number(context.get("earnings_score") or context.get("priority_score"))
    notes: list[str] = []
    if label in {"thesis_improved", "market_overreaction_possible", "upcoming_earnings", "recent_earnings", "post_earnings"}:
        score += 26
        notes.append(f"Earnings context: {label}.")
    if label in {"thesis_weakened", "data_insufficient"}:
        score -= 20
        notes.append(f"Earnings risk context: {label}.")
    if action in {"review_for_add_after_earnings", "review_pre_earnings", "review_post_earnings", "monitor_reaction"}:
        score += 14
        notes.append(f"Earnings review action: {action}.")
    return score, notes


def action_for_score(policy: str, score: float, row: Mapping[str, object]) -> str:
    if policy == "tactical_momentum":
        return "shadow_tactical_review" if score >= 45 else "shadow_watch" if score >= 20 else "shadow_avoid"
    if policy == "earnings_event":
        return "shadow_earnings_review" if score >= 45 else "shadow_watch" if score >= 20 else "shadow_avoid"
    if policy == "risk_skeptic" and (decision_blocked(row) or provider_gap_count(row) > 0 or score < 45):
        return "shadow_avoid"
    if score >= 72:
        return "shadow_add"
    if score >= 52:
        return "shadow_hold"
    if score >= 30:
        return "shadow_watch"
    return "shadow_avoid"


def confidence_for_score(score: float, row: Mapping[str, object]) -> str:
    if target_confidence(row) == "needs_review" or decision_blocked(row):
        return "low"
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def expected_direction_for(action: str, score: float) -> str:
    if action in {"shadow_add", "shadow_tactical_review", "shadow_earnings_review"} and score >= 45:
        return "up"
    if action == "shadow_avoid":
        return "down"
    return "mixed"


def stable_id(prefix: str, payload: Mapping[str, object]) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def risk_notes_for(
    row: Mapping[str, object],
    *,
    source_notes: Iterable[str] = (),
    tactical_notes: Iterable[str] = (),
    earnings_notes: Iterable[str] = (),
) -> list[str]:
    notes = [text(item) for item in as_list(row.get("risk_notes") or row.get("risks") or row.get("top_risks")) if text(item)]
    if decision_blocked(row):
        notes.append("Official decision-safety context is blocked or not ready.")
    if watchlist_blocked(row):
        notes.append("Watchlist-only policy remains a blocker.")
    gaps = provider_gap_count(row)
    if gaps:
        notes.append(f"{gaps} provider/data gap(s) affect shadow confidence.")
    notes.extend(text(item) for item in source_notes if text(item))
    notes.extend(text(item) for item in tactical_notes if text(item))
    notes.extend(text(item) for item in earnings_notes if text(item))
    return list(dict.fromkeys(notes)) or ["Review risk, data quality, and thesis evidence before relying on this shadow output."]


def rationale_for(policy: str, row: Mapping[str, object], score: float, action: str, extra_notes: Iterable[str]) -> str:
    base = {
        "conservative_long_term": "Conservative shadow policy discounts weak confidence, provider gaps, and unresolved risk.",
        "aggressive_growth": "Aggressive growth shadow policy emphasizes upside and growth context while remaining shadow-only.",
        "risk_skeptic": "Risk-skeptic shadow policy emphasizes downside, blockers, and decision-safety concerns.",
        "source_quality_weighted": "Source-quality shadow policy rewards useful source context and penalizes noisy or stale sources.",
        "tactical_momentum": "Tactical momentum shadow policy reads tactical setup context without affecting long-term recommendations.",
        "earnings_event": "Earnings-event shadow policy reads earnings review context without changing official output.",
    }[policy]
    details = "; ".join(text(note) for note in extra_notes if text(note))
    if details:
        return f"{base} Shadow action {action} with score {round(score, 2)}. {details}"
    return f"{base} Shadow action {action} with score {round(score, 2)}."


def differences_from_official(row: Mapping[str, object], shadow_action: str, score: float) -> list[str]:
    differences = [f"Official action remains {text(row.get('action')) or 'unknown'}; shadow action is {shadow_action}."]
    official_score = number(row.get("score"))
    if official_score or score:
        differences.append(f"Official score {round(official_score, 2)} was read-only; shadow score is {round(score, 2)}.")
    if decision_blocked(row):
        differences.append("Official decision-safety blocker was preserved as context, not changed.")
    if target_confidence(row) in {"low", "needs_review"}:
        differences.append(f"Official target confidence context is {target_confidence(row)}.")
    return differences


def prediction_record_for(
    *,
    row: Mapping[str, object],
    model: Mapping[str, object],
    report_date: str,
    horizon: str,
    shadow_action: str,
    confidence: str,
) -> dict[str, object]:
    existing = row.get("prediction_record")
    if isinstance(existing, Mapping):
        record = copy.deepcopy(dict(existing))
        record["shadow_only"] = True
        record["review_only"] = True
        return record
    payload = {
        "report_date": report_date,
        "symbol": symbol_key(row),
        "model_name": model["model_name"],
        "model_version": model["model_version"],
        "model_role": model["model_role"],
        "decision_mode": text(row.get("decision_mode") or "long_term_buy_add"),
        "horizon": horizon,
        "shadow_action": shadow_action,
        "confidence": confidence,
    }
    return {
        "prediction_id": stable_id("shadow_pred", payload),
        **payload,
        "official_action": text(row.get("action")),
        "expected_direction": expected_direction_for(shadow_action, number(row.get("score"))),
        "review_only": True,
        "shadow_only": True,
        "does_not_change_official": True,
    }


def score_row(
    row: Mapping[str, object],
    *,
    model: Mapping[str, object],
    source_context: Mapping[str, object],
    tactical_context: Mapping[str, object],
    earnings_context: Mapping[str, object],
) -> tuple[float, list[str], list[str]]:
    policy = text(model["policy"])
    official_score = number(row.get("score"))
    row_upside = upside(row)
    gaps = provider_gap_count(row)
    risks = risk_count(row)
    blocked_penalty = 26.0 if decision_blocked(row) else 0.0
    watchlist_penalty = 18.0 if watchlist_blocked(row) else 0.0
    source_delta, source_notes = source_quality_score(row, source_context)
    tactical_delta, tactical_notes = tactical_score(tactical_context)
    earnings_delta, earnings_notes = earnings_score(earnings_context)
    extra_notes: list[str] = []

    if policy == "conservative_long_term":
        score = official_score + confidence_adjustment(row) - (gaps * 9.0) - (risks * 3.0) - blocked_penalty - watchlist_penalty
        extra_notes.append(f"Applied conservative gap/risk penalty: gaps={gaps}, risks={risks}.")
    elif policy == "aggressive_growth":
        score = official_score + (row_upside * 0.45) + (growth_score(row) * 0.35) - (gaps * 3.0) - (blocked_penalty * 0.5)
        extra_notes.append(f"Prioritized upside {round(row_upside, 2)} and growth context.")
    elif policy == "risk_skeptic":
        score = official_score + confidence_adjustment(row) - (gaps * 13.0) - (risks * 6.0) - (blocked_penalty * 1.4) - watchlist_penalty
        extra_notes.append(f"Applied risk-skeptic penalties: gaps={gaps}, risks={risks}.")
    elif policy == "source_quality_weighted":
        score = official_score + source_delta + confidence_adjustment(row) - (gaps * 5.0)
        extra_notes.extend(source_notes or ["No source-quality context supplied."])
    elif policy == "tactical_momentum":
        score = (official_score * 0.45) + tactical_delta + (row_upside * 0.15) - (gaps * 4.0) - (blocked_penalty * 0.4)
        extra_notes.extend(tactical_notes)
    else:
        score = (official_score * 0.5) + earnings_delta + (row_upside * 0.1) - (gaps * 4.0) - (blocked_penalty * 0.4)
        extra_notes.extend(earnings_notes)
    bounded_score = max(0.0, min(100.0, score))
    risk_notes = risk_notes_for(
        row,
        source_notes=source_notes if policy == "source_quality_weighted" else (),
        tactical_notes=tactical_notes if policy == "tactical_momentum" else (),
        earnings_notes=earnings_notes if policy == "earnings_event" else (),
    )
    return bounded_score, extra_notes, risk_notes


def shadow_run_id_for(model: Mapping[str, object], report_date: str, horizon: str, rows: Iterable[Mapping[str, object]]) -> str:
    payload = {
        "model_name": model["model_name"],
        "model_version": model["model_version"],
        "policy": model["policy"],
        "report_date": report_date,
        "horizon": horizon,
        "symbols": sorted(symbol_key(row) for row in rows),
    }
    return stable_id("shadow_run", payload)


def run_shadow_recommendations(
    model_definition: Mapping[str, object] | str,
    official_recommendations_or_context: object,
    *,
    long_term_add_queue: object = None,
    tactical_context: object = None,
    earnings_context: object = None,
    source_context: object = None,
    ai_context: object = None,
    report_date: str = "",
    evaluation_horizon: str = "12_months",
) -> dict[str, object]:
    """Run one deterministic shadow policy over existing recommendation/context rows."""

    model = normalized_model_definition(model_definition)
    rows = recommendation_rows(official_recommendations_or_context)
    if not report_date:
        report_date = next((text(row.get("report_date")) for row in rows if text(row.get("report_date"))), "")
    source_by_symbol = source_context_by_symbol(source_context)
    tactical_by_symbol = context_by_symbol(tactical_context)
    earnings_by_symbol = context_by_symbol(earnings_context)
    queue_by_symbol = context_by_symbol(long_term_add_queue)
    ai_by_symbol = context_by_symbol(ai_context)
    run_id = shadow_run_id_for(model, report_date, evaluation_horizon, rows)

    outputs: list[dict[str, object]] = []
    for row in rows:
        symbol = symbol_key(row)
        source_row = source_by_symbol.get(symbol, {})
        tactical_row = tactical_by_symbol.get(symbol, {})
        earnings_row = earnings_by_symbol.get(symbol, {})
        queue_row = queue_by_symbol.get(symbol, {})
        ai_row = ai_by_symbol.get(symbol, {})
        score, extra_notes, risk_notes = score_row(
            row,
            model=model,
            source_context=source_row,
            tactical_context=tactical_row,
            earnings_context=earnings_row,
        )
        shadow_action = action_for_score(text(model["policy"]), score, row)
        confidence = confidence_for_score(score, row)
        decision_mode = text(row.get("decision_mode") or queue_row.get("decision_mode") or "long_term_buy_add")
        output = {
            "shadow_run_id": run_id,
            "model_name": model["model_name"],
            "model_version": model["model_version"],
            "model_role": model["model_role"],
            "model_policy": model["policy"],
            "report_date": report_date,
            "symbol": symbol,
            "official_action": text(row.get("action")),
            "shadow_action": shadow_action,
            "shadow_rank": 0,
            "shadow_score": round(score, 4),
            "confidence": confidence,
            "decision_mode": decision_mode,
            "horizon": evaluation_horizon,
            "rationale": rationale_for(text(model["policy"]), row, score, shadow_action, extra_notes),
            "risk_notes": risk_notes,
            "differences_from_official": differences_from_official(row, shadow_action, score),
            "prediction_record": prediction_record_for(
                row=row,
                model=model,
                report_date=report_date,
                horizon=evaluation_horizon,
                shadow_action=shadow_action,
                confidence=confidence,
            ),
            "context_refs": {
                "long_term_add_queue": bool(queue_row),
                "tactical_context": bool(tactical_row),
                "earnings_context": bool(earnings_row),
                "source_context": bool(source_row),
                "ai_context": bool(ai_row),
            },
            "review_only": True,
            "shadow_only": True,
            "does_not_change_official": True,
            "notes": REVIEW_ONLY_NOTE,
        }
        outputs.append(output)

    outputs.sort(key=lambda item: (-number(item.get("shadow_score")), text(item.get("symbol"))))
    for rank, item in enumerate(outputs, start=1):
        item["shadow_rank"] = rank

    warnings: list[str] = []
    if not rows:
        warnings.append("No official recommendation/context rows supplied for shadow review.")
    if any(not text(row.get("action")) for row in rows):
        warnings.append("Some official rows are missing official action labels.")
    if any(not text(row.get("score")) for row in rows):
        warnings.append("Some official rows are missing official score context.")
    return {
        "shadow_run_id": run_id,
        "model_name": model["model_name"],
        "model_version": model["model_version"],
        "model_role": model["model_role"],
        "model_policy": model["policy"],
        "report_date": report_date,
        "horizon": evaluation_horizon,
        "rows": outputs,
        "warnings": warnings,
        "review_only": True,
        "shadow_only": True,
        "does_not_change_official": True,
        "notes": REVIEW_ONLY_NOTE,
    }


def run_shadow_model_suite(
    model_definitions: Iterable[Mapping[str, object] | str],
    official_recommendations_or_context: object,
    **kwargs: object,
) -> dict[str, object]:
    """Run multiple shadow policies without mutating official inputs."""

    runs = [
        run_shadow_recommendations(model_definition, official_recommendations_or_context, **kwargs)
        for model_definition in model_definitions
    ]
    return {
        "runs": runs,
        "run_count": len(runs),
        "review_only": True,
        "shadow_only": True,
        "does_not_change_official": True,
        "notes": REVIEW_ONLY_NOTE,
    }


__all__ = [
    "POLICIES",
    "REVIEW_ONLY_NOTE",
    "SHADOW_ACTIONS",
    "run_shadow_model_suite",
    "run_shadow_recommendations",
]
