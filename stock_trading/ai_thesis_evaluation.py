"""Review-only AI thesis evaluation helpers.

The helpers in this module compare already-generated AI brief content against
later evidence and outcome rows. They do not call an AI model, mutate
recommendations, update storage, or promote model behavior.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


THESIS_EVALUATION_LABELS = {
    "thesis_supported",
    "thesis_partially_supported",
    "thesis_contradicted",
    "too_early_to_judge",
    "insufficient_evidence",
    "guardrail_failed",
}
SUPPORT_RELATIONS = {"support", "supported", "supports", "aligned", "confirmed", "confirm"}
CONTRADICT_RELATIONS = {"contradict", "contradicted", "contradicts", "weakened", "negative", "missed"}
RISK_RELATIONS = {"risk_materialized", "materialized", "triggered"}
INSUFFICIENT_RELATIONS = {
    "insufficient",
    "insufficient_evidence",
    "missing",
    "stale",
    "unsupported",
    "unresolved",
    "too_early",
    "not_enough_history",
}
LOW_READINESS_VALUES = {
    "not_ready",
    "not ready",
    "not enough data",
    "not_enough_data",
    "insufficient evidence",
    "insufficient_evidence",
    "needs more data",
    "needs_more_data",
}
REVIEW_ONLY_NOTE = (
    "Review-only AI thesis evaluation. These metrics must not automatically change AI generation, "
    "scores, actions, targets, target confidence, decision safety, source weights, model trust, "
    "broker behavior, or recommendations."
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def lower(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def symbol_for(payload: Mapping[str, object]) -> str:
    return text(payload.get("symbol") or payload.get("Symbol")).upper()


def normalize_claims(brief: Mapping[str, object]) -> list[dict[str, object]]:
    claims: list[dict[str, object]] = []
    claim_fields = (
        ("bull_case", "bull_case"),
        ("bear_case", "bear_case"),
        ("risk_or_uncertainty", "risk"),
        ("what_would_change_the_view", "view_change"),
        ("summary", "summary"),
        ("brief", "summary"),
    )
    for field, claim_type in claim_fields:
        for value in as_list(brief.get(field)):
            claim = text(value)
            if claim:
                claims.append({"claim_type": claim_type, "claim": claim})

    for field in ("key_evidence", "supporting_data"):
        for value in as_list(brief.get(field)):
            claim = text(value)
            if claim:
                claims.append({"claim_type": "key_evidence", "claim": claim})
    return claims


def normalize_later_evidence(rows: Iterable[Mapping[str, object]] | None) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows or []:
        claim_type = lower(row.get("claim_type") or row.get("category") or row.get("evidence_type") or "general")
        relation = lower(row.get("relation") or row.get("assessment") or row.get("status") or "unresolved")
        normalized.append(
            {
                "claim_type": claim_type,
                "relation": relation,
                "summary": text(row.get("summary") or row.get("headline") or row.get("evidence") or row.get("claim")),
                "source": text(row.get("source") or row.get("source_name") or row.get("source_ref")),
                "as_of": text(row.get("as_of") or row.get("event_date") or row.get("date")),
            }
        )
    return normalized


def guardrail_status(
    brief: Mapping[str, object],
    guardrail_result: Mapping[str, object] | None = None,
) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
    result = as_dict(guardrail_result) or as_dict(brief.get("guardrails"))
    if not result:
        return "not_provided", [], []
    failures = [as_dict(item) for item in as_list(result.get("failures"))]
    warnings = [as_dict(item) for item in as_list(result.get("warnings"))]
    recommended_action = lower(result.get("recommended_action"))
    if result.get("passed") is False or failures or recommended_action == "reject":
        return "failed", failures, warnings
    if warnings or recommended_action == "needs_review":
        return "warnings", failures, warnings
    return "passed", failures, warnings


def readiness_status(
    brief: Mapping[str, object],
    prompt_packet: Mapping[str, object] | None = None,
) -> str:
    packet = as_dict(prompt_packet)
    readiness = as_dict(packet.get("synthesis_readiness")) or as_dict(brief.get("synthesis_readiness"))
    return lower(
        readiness.get("status")
        or readiness.get("readiness_status")
        or brief.get("readiness_status")
        or brief.get("readiness")
    )


def has_source_warning(
    brief: Mapping[str, object],
    prompt_packet: Mapping[str, object] | None = None,
    source_usefulness: Iterable[Mapping[str, object]] | None = None,
) -> bool:
    source_refs = as_list(brief.get("source_references")) or as_list(brief.get("audit_refs")) or as_list(brief.get("citations"))
    gaps = [
        text(brief.get("data_gaps")),
        *[text(item) for item in as_list(brief.get("open_data_gaps"))],
        *[text(item) for item in as_list(as_dict(prompt_packet).get("provider_source_gaps"))],
    ]
    haystack = " ".join(gaps).lower()
    if not source_refs:
        return True
    if any(term in haystack for term in ("stale", "missing", "provider gap", "blocked", "insufficient", "not enough")):
        return True
    for row in source_usefulness or []:
        label = lower(row.get("label") or row.get("usefulness_label") or row.get("source_usefulness_label"))
        if label in {"stale_or_blocked", "noisy", "needs_more_history"}:
            return True
    return False


def outcome_alignment(recommendation_outcomes: Iterable[Mapping[str, object]] | None) -> str:
    statuses = [lower(row.get("outcome_status") or row.get("status")) for row in recommendation_outcomes or []]
    statuses = [status for status in statuses if status]
    if not statuses:
        return "unknown"
    if all(status in {"not_enough_history", "pending", "too_early"} for status in statuses):
        return "pending"
    aligned = any(status in {"positive_follow_through", "target_progress", "beat_benchmark", "aligned"} for status in statuses)
    contradicted = any(status in {"negative_follow_through", "drawdown_warning", "missed_benchmark", "contradicted"} for status in statuses)
    if aligned and contradicted:
        return "mixed"
    if aligned:
        return "aligned"
    if contradicted:
        return "contradicted"
    return "neutral"


def catalyst_alignment(catalyst_outcomes: Iterable[Mapping[str, object]] | None) -> str:
    labels = [lower(row.get("outcome_label") or row.get("label") or row.get("catalyst_outcome_label")) for row in catalyst_outcomes or []]
    if any(label in {"likely_useful", "useful", "positive_follow_through"} for label in labels):
        return "aligned"
    if any(label in {"likely_noisy", "noisy", "negative_follow_through"} for label in labels):
        return "contradicted"
    return "unknown"


def matching_evidence(claim_type: str, evidence_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    matches = [row for row in evidence_rows if row.get("claim_type") in {claim_type, "general"}]
    if claim_type == "risk":
        matches.extend(row for row in evidence_rows if row.get("claim_type") in {"bear_case", "bear", "risk_language"})
    if claim_type == "view_change":
        matches.extend(row for row in evidence_rows if row.get("claim_type") in {"invalidation", "what_would_change_the_view"})
    return matches


def assessed_claims(
    claims: list[dict[str, object]],
    evidence_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, bool]]:
    supported: list[dict[str, object]] = []
    contradicted: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    flags = {
        "bull_case_supported": False,
        "bear_case_supported": False,
        "key_risk_materialized": False,
        "view_change_triggered": False,
        "unsupported_claim_present": False,
    }

    for claim in claims:
        claim_type = text(claim.get("claim_type"))
        matches = matching_evidence(claim_type, evidence_rows)
        if not matches:
            unresolved.append({**claim, "assessment": "unresolved", "reason": "No later evidence was provided for this claim."})
            continue
        relations = {text(row.get("relation")) for row in matches}
        evidence_summary = "; ".join(text(row.get("summary")) for row in matches if text(row.get("summary")))
        relation_key = "_".join(sorted(relations))
        assessed = {**claim, "evidence_summary": evidence_summary, "assessment": relation_key}

        if relations & SUPPORT_RELATIONS:
            supported.append(assessed)
            if claim_type == "bull_case":
                flags["bull_case_supported"] = True
            if claim_type in {"bear_case", "risk"}:
                flags["bear_case_supported"] = True
        if relations & (CONTRADICT_RELATIONS | RISK_RELATIONS):
            contradicted.append(assessed)
            if claim_type in {"risk", "bear_case"} or relations & RISK_RELATIONS:
                flags["key_risk_materialized"] = True
            if claim_type == "view_change" or "triggered" in relations:
                flags["view_change_triggered"] = True
        if relations & INSUFFICIENT_RELATIONS:
            unresolved.append(assessed)
            if "unsupported" in relations:
                flags["unsupported_claim_present"] = True

    return supported, contradicted, unresolved, flags


def thesis_label(
    *,
    guardrails: str,
    alignment: str,
    catalyst: str,
    readiness: str,
    source_warning: bool,
    supported_count: int,
    contradicted_count: int,
    unresolved_count: int,
    flags: Mapping[str, bool],
) -> str:
    if guardrails == "failed":
        return "guardrail_failed"
    if readiness in LOW_READINESS_VALUES or (source_warning and supported_count == 0 and contradicted_count == 0):
        return "insufficient_evidence"
    if alignment == "pending" and supported_count == 0 and contradicted_count == 0:
        return "too_early_to_judge"
    if alignment == "contradicted" or catalyst == "contradicted" or contradicted_count > supported_count:
        return "thesis_contradicted"
    if (
        alignment == "mixed"
        or catalyst == "aligned" and contradicted_count
        or (supported_count and contradicted_count)
        or flags.get("key_risk_materialized")
        or flags.get("view_change_triggered")
    ):
        return "thesis_partially_supported"
    if alignment == "aligned" or supported_count > 0:
        return "thesis_supported"
    if unresolved_count:
        return "insufficient_evidence"
    return "too_early_to_judge"


def confidence_for(label: str, alignment: str, supported_count: int, contradicted_count: int) -> str:
    if label in {"guardrail_failed", "insufficient_evidence", "too_early_to_judge"}:
        return "low"
    if alignment in {"aligned", "contradicted"} and supported_count + contradicted_count >= 2:
        return "high"
    return "medium"


def evaluate_ai_thesis(
    brief_payload: Mapping[str, object],
    *,
    prompt_packet: Mapping[str, object] | None = None,
    guardrail_result: Mapping[str, object] | None = None,
    recommendation_outcomes: Iterable[Mapping[str, object]] | None = None,
    catalyst_outcomes: Iterable[Mapping[str, object]] | None = None,
    later_evidence: Iterable[Mapping[str, object]] | None = None,
    source_usefulness: Iterable[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Evaluate one AI thesis artifact against later review-only evidence."""

    claims = normalize_claims(brief_payload)
    evidence_rows = normalize_later_evidence(later_evidence)
    supported, contradicted, unresolved, flags = assessed_claims(claims, evidence_rows)
    guardrails, failures, warnings = guardrail_status(brief_payload, guardrail_result)
    readiness = readiness_status(brief_payload, prompt_packet)
    source_warning = has_source_warning(brief_payload, prompt_packet, source_usefulness)
    alignment = outcome_alignment(recommendation_outcomes)
    catalyst = catalyst_alignment(catalyst_outcomes)
    if alignment == "unknown" and catalyst != "unknown":
        alignment = catalyst

    label = thesis_label(
        guardrails=guardrails,
        alignment=alignment,
        catalyst=catalyst,
        readiness=readiness,
        source_warning=source_warning,
        supported_count=len(supported),
        contradicted_count=len(contradicted),
        unresolved_count=len(unresolved),
        flags=flags,
    )
    return {
        "symbol": symbol_for(brief_payload),
        "report_date": text(brief_payload.get("report_date") or as_dict(prompt_packet).get("report_date")),
        "brief_id": text(brief_payload.get("brief_id")),
        "artifact_ref": text(brief_payload.get("artifact_ref") or brief_payload.get("source_context")),
        "thesis_evaluation_label": label,
        "supported_claims": supported,
        "contradicted_claims": contradicted,
        "unresolved_claims": unresolved,
        "outcome_alignment": alignment,
        "guardrail_status": guardrails,
        "guardrail_failures": failures,
        "guardrail_warnings": warnings,
        "confidence": confidence_for(label, alignment, len(supported), len(contradicted)),
        "evaluations": {
            **flags,
            "stale_or_missing_source_warning": source_warning,
            "outcome_aligned_with_thesis": alignment == "aligned",
            "outcome_contradicted_thesis": alignment == "contradicted",
            "catalyst_alignment": catalyst,
            "synthesis_readiness_status": readiness,
        },
        "review_only": True,
        "no_model_change": True,
        "notes": REVIEW_ONLY_NOTE,
    }


def evaluate_ai_theses(
    brief_payloads: Iterable[Mapping[str, object]],
    *,
    prompt_packets_by_symbol: Mapping[str, Mapping[str, object]] | None = None,
    recommendation_outcomes_by_symbol: Mapping[str, Iterable[Mapping[str, object]]] | None = None,
    catalyst_outcomes_by_symbol: Mapping[str, Iterable[Mapping[str, object]]] | None = None,
    later_evidence_by_symbol: Mapping[str, Iterable[Mapping[str, object]]] | None = None,
    source_usefulness_by_symbol: Mapping[str, Iterable[Mapping[str, object]]] | None = None,
) -> dict[str, object]:
    """Evaluate multiple AI thesis artifacts without mutating inputs."""

    evaluations = []
    for brief in brief_payloads:
        symbol = symbol_for(brief)
        evaluations.append(
            evaluate_ai_thesis(
                brief,
                prompt_packet=as_dict((prompt_packets_by_symbol or {}).get(symbol)),
                recommendation_outcomes=(recommendation_outcomes_by_symbol or {}).get(symbol),
                catalyst_outcomes=(catalyst_outcomes_by_symbol or {}).get(symbol),
                later_evidence=(later_evidence_by_symbol or {}).get(symbol),
                source_usefulness=(source_usefulness_by_symbol or {}).get(symbol),
            )
        )
    label_counts: dict[str, int] = {}
    for row in evaluations:
        label = text(row.get("thesis_evaluation_label"))
        label_counts[label] = label_counts.get(label, 0) + 1
    return {
        "metadata": {
            "review_only": True,
            "no_model_change": True,
            "evaluation_count": len(evaluations),
            "labels": sorted(THESIS_EVALUATION_LABELS),
            "label_counts": label_counts,
            "notes": REVIEW_ONLY_NOTE,
        },
        "evaluations": evaluations,
    }
