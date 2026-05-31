"""Review-only model version registry helpers."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Iterable, Mapping


MODEL_ROLES = {"official", "shadow", "ai_brief", "tactical", "earnings", "risk"}
OFFICIAL_OR_SHADOW = {"official", "shadow"}
DECISION_MODES = {
    "long_term_buy_add",
    "long_term_hold_health",
    "tactical_trade",
    "earnings_event",
    "speculative_watchlist",
    "etf_context",
    "future_short_candidate",
    "portfolio_review",
}
HORIZONS = {
    "1_day",
    "5_trading_days",
    "20_trading_days",
    "60_trading_days",
    "12_months",
    "multi_year",
    "same_day",
    "same_week",
    "same_month",
}
REQUIRED_MODEL_FIELDS = (
    "model_name",
    "model_version",
    "model_role",
    "official_or_shadow",
    "description",
    "created_at",
    "allowed_decision_modes",
    "allowed_horizons",
    "score_impact",
    "recommendation_impact",
    "notes",
)
REVIEW_ONLY_NOTE = (
    "Review-only model registry. Registered models do not change scores, targets, "
    "decision-safety gates, source weights, official recommendations, broker behavior, "
    "or trading unless a future explicit model-impact approval is added and tested."
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value else []
    return []


def normalize_token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def generated_at_text(value: str | None = None) -> str:
    return value or datetime.utcnow().isoformat(timespec="seconds")


def validation_result(errors: list[dict[str, str]], warnings: list[dict[str, str]] | None = None) -> dict[str, object]:
    warnings = warnings or []
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def normalize_model_registration(
    model: Mapping[str, object],
    *,
    created_at: str | None = None,
) -> dict[str, object]:
    """Return a deterministic model registry row with safe review-only defaults."""

    row = copy.deepcopy(dict(model))
    row["model_name"] = text(row.get("model_name"))
    row["model_version"] = text(row.get("model_version"))
    row["model_role"] = normalize_token(row.get("model_role"))
    row["official_or_shadow"] = normalize_token(row.get("official_or_shadow"))
    row["description"] = text(row.get("description"))
    row["created_at"] = text(row.get("created_at")) or generated_at_text(created_at)
    row["allowed_decision_modes"] = [normalize_token(value) for value in as_list(row.get("allowed_decision_modes"))]
    row["allowed_horizons"] = [normalize_token(value) for value in as_list(row.get("allowed_horizons"))]
    row["score_impact"] = normalize_token(row.get("score_impact") or "none")
    row["recommendation_impact"] = normalize_token(row.get("recommendation_impact") or "none")
    row["notes"] = text(row.get("notes") or REVIEW_ONLY_NOTE)
    row["review_only"] = True
    row["recommendation_only_note"] = text(row.get("recommendation_only_note") or REVIEW_ONLY_NOTE)
    return row


def validate_model_registration(model: Mapping[str, object]) -> dict[str, object]:
    """Validate a model registry row without authorizing model impact."""

    row = normalize_model_registration(model)
    errors: list[dict[str, str]] = []
    for field in REQUIRED_MODEL_FIELDS:
        value = row.get(field)
        if value in ("", [], None):
            errors.append(_error(field, f"Missing required model registry field: {field}."))

    role = text(row.get("model_role"))
    if role and role not in MODEL_ROLES:
        errors.append(_error("model_role", f"Unknown model_role: {role}."))

    official_or_shadow = text(row.get("official_or_shadow"))
    if official_or_shadow not in OFFICIAL_OR_SHADOW:
        errors.append(_error("official_or_shadow", "official_or_shadow must be explicit: official or shadow."))

    for index, mode in enumerate(row.get("allowed_decision_modes", [])):
        if mode not in DECISION_MODES:
            errors.append(_error(f"allowed_decision_modes[{index}]", f"Unknown decision_mode: {mode}."))

    for index, horizon in enumerate(row.get("allowed_horizons", [])):
        if horizon not in HORIZONS:
            errors.append(_error(f"allowed_horizons[{index}]", f"Unknown horizon: {horizon}."))

    for field in ("score_impact", "recommendation_impact"):
        impact = text(row.get(field) or "none")
        if impact != "none" and not text(row.get("impact_approval_ref")):
            errors.append(
                _error(
                    field,
                    f"{field} must be none unless an explicit impact_approval_ref is present.",
                )
            )

    if official_or_shadow == "shadow" and text(row.get("recommendation_impact")) != "none":
        errors.append(_error("recommendation_impact", "Shadow models must be non-authoritative."))

    return validation_result(errors)


def build_model_registry(
    models: Iterable[Mapping[str, object]],
    *,
    created_at: str | None = None,
) -> dict[str, object]:
    """Build a deterministic registry document from model rows."""

    rows = [normalize_model_registration(model, created_at=created_at) for model in models]
    rows.sort(key=lambda row: (text(row.get("model_role")), text(row.get("model_name")), text(row.get("model_version"))))
    validations = [validate_model_registration(row) for row in rows]
    errors = [
        {"index": index, **error}
        for index, result in enumerate(validations)
        for error in result.get("errors", [])
        if isinstance(error, dict)
    ]
    return {
        "review_only": True,
        "registry_version": "model-registry-v1",
        "model_count": len(rows),
        "models": rows,
        "validation": validation_result(errors),
        "notes": REVIEW_ONLY_NOTE,
    }


__all__ = [
    "DECISION_MODES",
    "HORIZONS",
    "MODEL_ROLES",
    "OFFICIAL_OR_SHADOW",
    "REVIEW_ONLY_NOTE",
    "build_model_registry",
    "normalize_model_registration",
    "validate_model_registration",
]
