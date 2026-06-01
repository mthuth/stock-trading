"""Deterministic model debate packets for shadow-model review."""

from __future__ import annotations

import copy
from typing import Iterable, Mapping


REVIEW_ONLY_INSTRUCTIONS = (
    "Shadow-only model debate packet. Do not change the official recommendation, "
    "do not place trades, do not preview orders, and explain only."
)
BULLISH_ACTIONS = {
    "strong_buy",
    "buy",
    "add",
    "tactical_buy_review",
    "review_for_add_after_earnings",
    "consider_small_review_only_add",
}
BEARISH_ACTIONS = {
    "avoid",
    "trim",
    "sell",
    "tactical_sell_review",
    "avoid_for_now",
    "hold_buy_capacity",
    "wait_until_after_report",
}
TACTICAL_MODES = {"tactical_trade", "tactical", "intraday_signal", "same_day", "same_week", "same_month"}
EARNINGS_MODES = {"earnings_event", "pre_earnings", "post_earnings", "earnings"}


def as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return copy.deepcopy(list(value))
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def symbol_for(row: Mapping[str, object]) -> str:
    return text(row.get("symbol") or row.get("Symbol")).upper()


def model_name(row: Mapping[str, object], fallback: str = "unknown_model") -> str:
    return text(row.get("model_name") or row.get("model") or row.get("name"), fallback)


def model_version(row: Mapping[str, object]) -> str:
    return text(row.get("model_version") or row.get("version"))


def model_action(row: Mapping[str, object]) -> str:
    return text(row.get("action") or row.get("recommendation") or row.get("review_action") or row.get("stance"))


def model_score(row: Mapping[str, object]) -> float:
    return number(row.get("score") or row.get("priority_score") or row.get("conviction_score"))


def decision_mode(row: Mapping[str, object]) -> str:
    return token(row.get("decision_mode") or row.get("mode"))


def horizon(row: Mapping[str, object]) -> str:
    return token(row.get("horizon") or row.get("tactical_horizon") or row.get("recommendation_horizon"))


def stance_for(row: Mapping[str, object]) -> str:
    stance = token(row.get("stance") or row.get("model_stance"))
    action = token(model_action(row))
    if stance in {"bullish", "bearish", "skeptical", "neutral", "tactical", "earnings"}:
        return stance
    if action in BULLISH_ACTIONS:
        return "bullish"
    if action in BEARISH_ACTIONS:
        return "bearish"
    if action in {"hold", "watch", "wait", "wait_for_confirmation"}:
        return "neutral"
    return "neutral"


def compact_recommendation(row: Mapping[str, object]) -> dict[str, object]:
    data = as_dict(row)
    return {
        "symbol": symbol_for(data),
        "model_name": model_name(data),
        "model_version": model_version(data),
        "action": model_action(data),
        "stance": stance_for(data),
        "score": data.get("score") if "score" in data else data.get("priority_score"),
        "target_price": data.get("target_price"),
        "target_confidence": text(data.get("target_confidence") or data.get("confidence")),
        "decision_mode": decision_mode(data),
        "horizon": horizon(data),
        "rationale": text(data.get("rationale") or data.get("why") or data.get("summary")),
        "risk_summary": text(data.get("risk_summary") or data.get("risk") or data.get("bear_case")),
        "bull_case": text(data.get("bull_case")),
        "bear_case": text(data.get("bear_case")),
        "review_only": True,
        "shadow_only": token(data.get("source_type") or data.get("role")) != "official",
    }


def rows_for_symbol(rows: Iterable[Mapping[str, object]], symbol: str) -> list[dict[str, object]]:
    selected = []
    for row in rows:
        data = as_dict(row)
        row_symbol = symbol_for(data)
        if not row_symbol or row_symbol == symbol:
            selected.append(data)
    return selected


def evidence_context_by_model(evidence_rows: Iterable[Mapping[str, object]], models: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    names = {text(model.get("model_name")) for model in models if text(model.get("model_name"))}
    grouped = {name: [] for name in sorted(names)}
    unassigned: list[dict[str, object]] = []
    for row in evidence_rows:
        data = as_dict(row)
        model = text(data.get("model_name") or data.get("model"))
        payload = {
            "source_name": text(data.get("source_name") or data.get("source") or data.get("provider")),
            "evidence_id": text(data.get("evidence_id") or data.get("id")),
            "headline": text(data.get("headline") or data.get("title") or data.get("summary")),
            "summary": text(data.get("summary") or data.get("detail")),
            "corroboration": text(data.get("corroboration") or data.get("corroboration_label")),
            "confidence": text(data.get("confidence")),
        }
        if model:
            grouped.setdefault(model, []).append(payload)
        else:
            unassigned.append(payload)
    if unassigned:
        for name in grouped:
            grouped[name].extend(copy.deepcopy(unassigned))
    return grouped


def source_quality_notes(source_context: object, evidence_rows: Iterable[Mapping[str, object]]) -> list[str]:
    notes: list[str] = []
    data = as_dict(source_context)
    if data:
        for key in ("summary", "quality_label", "source_quality_label", "latest_issue"):
            value = text(data.get(key))
            if value:
                notes.append(value)
    for row in evidence_rows:
        confidence = token(as_dict(row).get("confidence"))
        corroboration = token(as_dict(row).get("corroboration") or as_dict(row).get("corroboration_label"))
        if confidence in {"low", "weak", "needs_review"}:
            notes.append("Some model evidence has weak confidence.")
        if corroboration in {"company_only", "single_source", "opinion_only", "uncorroborated"}:
            notes.append(f"Evidence includes weak corroboration: {corroboration}.")
    return list(dict.fromkeys(note for note in notes if note))


def provider_gap_notes(gaps: Iterable[Mapping[str, object]]) -> list[str]:
    notes: list[str] = []
    for row in gaps:
        data = as_dict(row)
        provider = text(data.get("provider") or data.get("source"))
        field = text(data.get("field") or data.get("endpoint") or data.get("dataset"))
        status = text(data.get("status"))
        issue = text(data.get("latest_issue") or data.get("message") or data.get("summary"))
        note = " ".join(part for part in (provider, field, status, issue) if part)
        if note:
            notes.append(note)
    return notes


def competition_context(rows: Iterable[Mapping[str, object]], symbol: str) -> dict[str, object]:
    selected = rows_for_symbol(rows, symbol)
    if not selected:
        return {"rows": [], "summary": "No model competition rows supplied."}
    sorted_rows = sorted(
        selected,
        key=lambda row: (
            -number(row.get("rank_score") or row.get("trust_score") or row.get("excess_return_vs_benchmark_pct")),
            model_name(row),
        ),
    )
    leader = sorted_rows[0]
    return {
        "rows": sorted_rows,
        "leader_model": model_name(leader),
        "summary": text(leader.get("summary") or f"{model_name(leader)} has the strongest supplied competition row."),
    }


def consensus_view(models: list[dict[str, object]]) -> dict[str, object]:
    if not models:
        return {
            "status": "missing_shadow_models",
            "summary": "No shadow models were supplied for debate.",
            "dominant_stance": "none",
        }
    counts: dict[str, int] = {}
    actions: dict[str, int] = {}
    for model in models:
        counts[str(model["stance"])] = counts.get(str(model["stance"]), 0) + 1
        actions[str(model["action"])] = actions.get(str(model["action"]), 0) + 1
    dominant_stance = sorted(counts, key=lambda key: (-counts[key], key))[0]
    dominant_action = sorted(actions, key=lambda key: (-actions[key], key))[0]
    status = "models_agree" if len(counts) == 1 and len(actions) == 1 else "models_disagree"
    return {
        "status": status,
        "dominant_stance": dominant_stance,
        "dominant_action": dominant_action,
        "stance_counts": dict(sorted(counts.items())),
        "action_counts": dict(sorted(actions.items())),
        "summary": (
            f"All shadow models align on {dominant_action}."
            if status == "models_agree"
            else f"Shadow models disagree; dominant stance is {dominant_stance}."
        ),
    }


def strongest_case(models: list[dict[str, object]], stance: str) -> dict[str, object]:
    candidates = [model for model in models if str(model.get("stance")) == stance or (stance == "bearish" and str(model.get("stance")) == "skeptical")]
    if not candidates:
        return {"model_name": "", "summary": f"No {stance} model case supplied."}
    candidates.sort(key=lambda model: (-model_score(model), text(model.get("model_name"))))
    chosen = candidates[0]
    summary = text(chosen.get("bull_case") if stance == "bullish" else chosen.get("bear_case"))
    if not summary:
        summary = text(chosen.get("rationale") or chosen.get("risk_summary") or f"{chosen.get('model_name')} has the strongest {stance} supplied score.")
    return {
        "model_name": chosen.get("model_name"),
        "action": chosen.get("action"),
        "score": chosen.get("score"),
        "summary": summary,
    }


def key_disagreements(models: list[dict[str, object]], official: Mapping[str, object]) -> list[dict[str, object]]:
    disagreements: list[dict[str, object]] = []
    official_action = text(official.get("action"))
    official_mode = token(official.get("decision_mode"))
    official_horizon = token(official.get("horizon") or official.get("recommendation_horizon"))
    actions = {text(model.get("action")) for model in models if text(model.get("action"))}
    modes = {text(model.get("decision_mode")) for model in models if text(model.get("decision_mode"))}
    horizons = {text(model.get("horizon")) for model in models if text(model.get("horizon"))}
    stances = {text(model.get("stance")) for model in models if text(model.get("stance"))}
    target_confidences = {text(model.get("target_confidence")) for model in models if text(model.get("target_confidence"))}
    if len(actions) > 1 or (official_action and official_action not in actions):
        disagreements.append({"type": "action", "official": official_action, "shadow_values": sorted(actions)})
    if len(stances) > 1:
        disagreements.append({"type": "stance", "shadow_values": sorted(stances)})
    if len(modes) > 1 or (official_mode and official_mode not in {token(mode) for mode in modes}):
        disagreements.append({"type": "decision_mode", "official": official_mode, "shadow_values": sorted(modes)})
    if len(horizons) > 1 or (official_horizon and official_horizon not in {token(item) for item in horizons}):
        disagreements.append({"type": "horizon", "official": official_horizon, "shadow_values": sorted(horizons)})
    if len(target_confidences) > 1:
        disagreements.append({"type": "target_confidence", "shadow_values": sorted(target_confidences)})
    return disagreements


def disagreement_summary(disagreements: list[Mapping[str, object]], models: list[dict[str, object]]) -> dict[str, object]:
    if not models:
        return {"status": "missing_shadow_models", "summary": "No model debate is possible without shadow models."}
    if not disagreements:
        return {"status": "agreement", "summary": "Models broadly agree with no major normalized disagreement fields."}
    labels = ", ".join(text(row.get("type")) for row in disagreements)
    return {"status": "disagreement", "summary": f"Models disagree on: {labels}.", "disagreement_count": len(disagreements)}


def resolution_prompts(disagreements: list[Mapping[str, object]], gaps: list[str], source_notes: list[str]) -> list[str]:
    prompts: list[str] = []
    for row in disagreements:
        kind = text(row.get("type"))
        if kind == "action":
            prompts.append("Compare decision-time evidence and later outcomes for models with different actions.")
        elif kind == "decision_mode":
            prompts.append("Separate long-term, tactical, and earnings assumptions before judging the model disagreement.")
        elif kind == "horizon":
            prompts.append("Evaluate each model on the horizon it was designed to forecast.")
        elif kind == "target_confidence":
            prompts.append("Review target-source breadth and confidence assumptions.")
        elif kind == "stance":
            prompts.append("Identify which risks or catalysts drive the stance split.")
    if gaps:
        prompts.append("Resolve provider/data gaps that could be driving model disagreement.")
    if source_notes:
        prompts.append("Review source quality and corroboration before trusting the debate outcome.")
    if not prompts:
        prompts.append("Track future outcomes to confirm whether model agreement was useful.")
    return list(dict.fromkeys(prompts))


def build_model_debate_packet(
    *,
    official_recommendation: Mapping[str, object],
    shadow_recommendations: Iterable[Mapping[str, object]],
    model_competition_rows: Iterable[Mapping[str, object]] = (),
    evidence_context: Iterable[Mapping[str, object]] = (),
    ai_brief_context: Mapping[str, object] | None = None,
    provider_gaps: Iterable[Mapping[str, object]] = (),
    target_context: Mapping[str, object] | None = None,
    decision_safety_context: Mapping[str, object] | None = None,
    report_date: str | None = None,
) -> dict[str, object]:
    """Build a JSON-serializable, shadow-only model debate packet without LLM calls."""

    official = compact_recommendation({**as_dict(official_recommendation), "role": "official"})
    symbol = symbol_for(official) or symbol_for(official_recommendation)
    shadows = [
        compact_recommendation(row)
        for row in rows_for_symbol(shadow_recommendations, symbol)
    ]
    shadows.sort(key=lambda row: (text(row.get("model_name")), text(row.get("model_version")), text(row.get("action"))))
    evidence_rows = rows_for_symbol(evidence_context, symbol)
    gap_rows = rows_for_symbol(provider_gaps, symbol)
    gap_notes = provider_gap_notes(gap_rows)
    source_notes = source_quality_notes(as_dict(ai_brief_context).get("source_quality") if ai_brief_context else {}, evidence_rows)
    disagreements = key_disagreements(shadows, official)
    tactical = [
        model
        for model in shadows
        if decision_mode(model) in TACTICAL_MODES or horizon(model) in {"1_day", "5_trading_days", "20_trading_days"}
    ]
    earnings = [
        model
        for model in shadows
        if decision_mode(model) in EARNINGS_MODES or "earnings" in text(model.get("rationale")).lower()
    ]
    packet = {
        "symbol": symbol,
        "report_date": report_date or text(official_recommendation.get("report_date")),
        "official_recommendation": official,
        "competing_models": shadows,
        "consensus_view": consensus_view(shadows),
        "disagreement_summary": disagreement_summary(disagreements, shadows),
        "bullish_models": [model for model in shadows if model.get("stance") == "bullish"],
        "bearish_or_skeptical_models": [
            model for model in shadows if model.get("stance") in {"bearish", "skeptical"} or token(model.get("action")) in BEARISH_ACTIONS
        ],
        "tactical_models": tactical,
        "earnings_models": earnings,
        "strongest_bull_case": strongest_case(shadows, "bullish"),
        "strongest_bear_case": strongest_case(shadows, "bearish"),
        "key_disagreements": disagreements,
        "evidence_each_model_used": evidence_context_by_model(evidence_rows, shadows),
        "source_quality_notes": source_notes or ["No source-quality notes supplied."],
        "provider_gap_notes": gap_notes or ["No provider-gap notes supplied."],
        "target_context": as_dict(target_context),
        "decision_safety_context": as_dict(decision_safety_context),
        "ai_brief_context": as_dict(ai_brief_context),
        "model_competition": competition_context(model_competition_rows, symbol),
        "what_would_resolve_disagreement": resolution_prompts(disagreements, gap_notes, source_notes),
        "llm_instructions": {
            "do_not_change_official_recommendation": True,
            "do_not_place_trades": True,
            "do_not_preview_orders": True,
            "explain_only": True,
            "instruction_text": REVIEW_ONLY_INSTRUCTIONS,
        },
        "review_only": True,
        "shadow_only": True,
        "no_official_change": True,
    }
    return packet


def build_model_debate_packets(
    official_recommendations: Iterable[Mapping[str, object]],
    shadow_recommendations: Iterable[Mapping[str, object]],
    **context: object,
) -> list[dict[str, object]]:
    """Build debate packets for multiple official recommendation rows."""

    shadows = [as_dict(row) for row in shadow_recommendations]
    return [
        build_model_debate_packet(
            official_recommendation=row,
            shadow_recommendations=shadows,
            model_competition_rows=context.get("model_competition_rows", ()),
            evidence_context=context.get("evidence_context", ()),
            ai_brief_context=as_dict(context.get("ai_brief_context")),
            provider_gaps=context.get("provider_gaps", ()),
            target_context=as_dict(context.get("target_context")),
            decision_safety_context=as_dict(context.get("decision_safety_context")),
            report_date=text(context.get("report_date")),
        )
        for row in official_recommendations
    ]


__all__ = [
    "REVIEW_ONLY_INSTRUCTIONS",
    "build_model_debate_packet",
    "build_model_debate_packets",
]
