"""Shadow-only model contract helpers for multi-model competition.

Wave 13 defines contracts and registry behavior only. These helpers do not run
models, score recommendations, tune weights, promote models, or alter official
recommendation behavior.
"""

from __future__ import annotations

import copy
from typing import Iterable, Mapping

from stock_trading.model_registry import DECISION_MODES, HORIZONS, IMPACT_FIELDS, MODEL_ROLES, PROMOTION_STATUSES


SHADOW_MODEL_CONTRACT_VERSION = "shadow-model-contract-v1"
OUTPUT_SCHEMA_VERSION = "shadow-model-output-v1"
ALLOWED_PROMOTION_STATUSES = {"not_eligible", "review_only"}
REQUIRED_SHADOW_MODEL_FIELDS = (
    "model_name",
    "model_version",
    "model_role",
    "official_or_shadow",
    "description",
    "allowed_decision_modes",
    "allowed_horizons",
    "input_requirements",
    "output_schema_version",
    "score_impact",
    "recommendation_impact",
    "target_impact",
    "decision_safety_impact",
    "allocation_impact",
    "promotion_status",
    "review_only",
)
REVIEW_ONLY_NOTE = (
    "Shadow-only model contract. This definition is for review-only competition and "
    "must not execute models, promote models, change official scores, change targets, "
    "change decision-safety gates, change allocations, change official recommendations, "
    "write to brokers, preview orders, or trade."
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def normalize_token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(copy.deepcopy(value))
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def _warning(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def validation_result(
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]] | None = None,
    normalized_model: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings or [],
        "normalized_model": copy.deepcopy(dict(normalized_model or {})),
    }


def normalize_shadow_model_definition(model: Mapping[str, object]) -> dict[str, object]:
    """Normalize one shadow model definition without mutating input."""

    row = copy.deepcopy(dict(model))
    row["model_name"] = normalize_token(row.get("model_name"))
    row["model_version"] = text(row.get("model_version"))
    row["model_role"] = normalize_token(row.get("model_role") or "shadow")
    row["official_or_shadow"] = normalize_token(row.get("official_or_shadow") or "shadow")
    row["description"] = text(row.get("description"))
    row["allowed_decision_modes"] = [normalize_token(value) for value in as_list(row.get("allowed_decision_modes"))]
    row["allowed_horizons"] = [normalize_token(value) for value in as_list(row.get("allowed_horizons"))]
    row["input_requirements"] = [normalize_token(value) for value in as_list(row.get("input_requirements"))]
    row["output_schema_version"] = text(row.get("output_schema_version") or OUTPUT_SCHEMA_VERSION)
    for field in IMPACT_FIELDS:
        row[field] = normalize_token(row.get(field) or "none")
    row["promotion_status"] = normalize_token(row.get("promotion_status") or "not_eligible")
    if "review_only" not in row:
        row["review_only"] = True
    row["recommendation_only_note"] = text(row.get("recommendation_only_note") or REVIEW_ONLY_NOTE)
    return row


def validate_shadow_model_definition(model: Mapping[str, object]) -> dict[str, object]:
    """Validate a Wave 13 shadow model definition."""

    row = normalize_shadow_model_definition(model)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    for field in REQUIRED_SHADOW_MODEL_FIELDS:
        value = row.get(field)
        if value in ("", [], None):
            errors.append(_error(field, f"Missing required shadow model field: {field}."))

    if row.get("review_only") is not True:
        errors.append(_error("review_only", "Shadow model definitions must be review_only: true."))

    if text(row.get("model_role")) not in MODEL_ROLES:
        errors.append(_error("model_role", f"Unknown model_role: {row.get('model_role')}."))

    if text(row.get("official_or_shadow")) != "shadow":
        errors.append(_error("official_or_shadow", "Wave 13 competing models must be shadow-only."))

    for index, mode in enumerate(row.get("allowed_decision_modes", [])):
        if mode not in DECISION_MODES:
            errors.append(_error(f"allowed_decision_modes[{index}]", f"Unknown decision_mode: {mode}."))

    for index, horizon in enumerate(row.get("allowed_horizons", [])):
        if horizon not in HORIZONS:
            errors.append(_error(f"allowed_horizons[{index}]", f"Unknown horizon: {horizon}."))

    for field in IMPACT_FIELDS:
        if text(row.get(field)) != "none":
            errors.append(_error(field, f"{field} must be none for Wave 13 shadow models."))

    promotion_status = text(row.get("promotion_status"))
    if promotion_status not in PROMOTION_STATUSES:
        errors.append(_error("promotion_status", f"Unknown promotion_status: {promotion_status}."))
    elif promotion_status not in ALLOWED_PROMOTION_STATUSES:
        errors.append(_error("promotion_status", "Wave 13 shadow models must be not_eligible or review_only."))

    if "benchmark" not in row.get("input_requirements", []) and "decision_time_inputs" not in row.get("input_requirements", []):
        warnings.append(
            _warning(
                "input_requirements",
                "Shadow model should declare decision-time inputs or benchmark/evaluation inputs before comparison.",
            )
        )

    return validation_result(errors, warnings, row)


def _starter(
    model_name: str,
    *,
    model_role: str,
    description: str,
    allowed_decision_modes: list[str],
    allowed_horizons: list[str],
    input_requirements: list[str],
) -> dict[str, object]:
    return {
        "model_name": model_name,
        "model_version": "shadow-v1",
        "model_role": model_role,
        "official_or_shadow": "shadow",
        "description": description,
        "allowed_decision_modes": allowed_decision_modes,
        "allowed_horizons": allowed_horizons,
        "input_requirements": input_requirements,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "score_impact": "none",
        "recommendation_impact": "none",
        "target_impact": "none",
        "decision_safety_impact": "none",
        "allocation_impact": "none",
        "promotion_status": "not_eligible",
        "review_only": True,
        "recommendation_only_note": REVIEW_ONLY_NOTE,
    }


STARTER_SHADOW_MODELS = (
    _starter(
        "conservative_long_term",
        model_role="shadow",
        description="Conservative long-term add competitor focused on source breadth and downside avoidance.",
        allowed_decision_modes=["long_term_buy_add", "long_term_hold_health"],
        allowed_horizons=["12_months", "multi_year"],
        input_requirements=["decision_time_inputs", "target_confidence", "decision_safety", "provider_gaps"],
    ),
    _starter(
        "aggressive_growth",
        model_role="shadow",
        description="Growth-oriented long-term competitor for upside review, kept shadow-only.",
        allowed_decision_modes=["long_term_buy_add", "speculative_watchlist"],
        allowed_horizons=["60_trading_days", "12_months", "multi_year"],
        input_requirements=["decision_time_inputs", "growth_metrics", "source_refs", "benchmark"],
    ),
    _starter(
        "tactical_momentum",
        model_role="tactical",
        description="Tactical setup competitor for momentum, breakout, and pullback review.",
        allowed_decision_modes=["tactical_trade"],
        allowed_horizons=["1_day", "5_trading_days", "20_trading_days", "same_day", "same_week", "same_month"],
        input_requirements=["decision_time_inputs", "price_history", "technical_context", "provider_gaps"],
    ),
    _starter(
        "earnings_event",
        model_role="earnings",
        description="Earnings-event competitor for pre/post earnings review outcomes.",
        allowed_decision_modes=["earnings_event"],
        allowed_horizons=["1_day", "5_trading_days", "20_trading_days"],
        input_requirements=["decision_time_inputs", "earnings_events", "provider_gaps", "source_refs"],
    ),
    _starter(
        "risk_skeptic",
        model_role="risk",
        description="Risk-first competitor that highlights downside and invalidation evidence.",
        allowed_decision_modes=["long_term_buy_add", "tactical_trade", "earnings_event", "portfolio_review"],
        allowed_horizons=["5_trading_days", "20_trading_days", "60_trading_days", "12_months"],
        input_requirements=["decision_time_inputs", "decision_safety", "drawdown_history", "provider_gaps"],
    ),
    _starter(
        "ai_thesis",
        model_role="ai_brief",
        description="AI-thesis competitor using source-backed brief expectations after guardrail review.",
        allowed_decision_modes=["long_term_buy_add", "earnings_event"],
        allowed_horizons=["20_trading_days", "60_trading_days", "12_months"],
        input_requirements=["decision_time_inputs", "ai_brief", "source_refs", "guardrails"],
    ),
    _starter(
        "source_quality_weighted",
        model_role="shadow",
        description="Source-quality competitor that emphasizes useful, corroborated evidence.",
        allowed_decision_modes=["long_term_buy_add", "speculative_watchlist", "portfolio_review"],
        allowed_horizons=["60_trading_days", "12_months", "multi_year"],
        input_requirements=["decision_time_inputs", "source_usefulness", "evidence_quality", "provider_gaps"],
    ),
    _starter(
        "decision_safety_strict",
        model_role="risk",
        description="Strict decision-safety competitor for missed-downside review.",
        allowed_decision_modes=["long_term_buy_add", "speculative_watchlist", "portfolio_review"],
        allowed_horizons=["20_trading_days", "60_trading_days", "12_months"],
        input_requirements=["decision_time_inputs", "decision_safety", "watchlist_policy", "provider_gaps"],
    ),
    _starter(
        "decision_safety_loose",
        model_role="risk",
        description="Loose decision-safety competitor for missed-upside review, shadow-only.",
        allowed_decision_modes=["long_term_buy_add", "speculative_watchlist", "portfolio_review"],
        allowed_horizons=["20_trading_days", "60_trading_days", "12_months"],
        input_requirements=["decision_time_inputs", "decision_safety", "outcomes", "benchmark"],
    ),
)


def starter_shadow_models() -> list[dict[str, object]]:
    """Return deep copies of the built-in starter shadow model definitions."""

    return [copy.deepcopy(row) for row in STARTER_SHADOW_MODELS]


def build_shadow_model_registry(models: Iterable[Mapping[str, object]] | None = None) -> dict[str, object]:
    """Build a deterministic shadow-only model registry document."""

    rows = [normalize_shadow_model_definition(model) for model in (models if models is not None else starter_shadow_models())]
    rows.sort(key=lambda row: (text(row.get("model_role")), text(row.get("model_name")), text(row.get("model_version"))))
    validations = [validate_shadow_model_definition(row) for row in rows]
    errors = [
        {"index": index, **error}
        for index, result in enumerate(validations)
        for error in result.get("errors", [])
        if isinstance(error, dict)
    ]
    warnings = [
        {"index": index, **warning}
        for index, result in enumerate(validations)
        for warning in result.get("warnings", [])
        if isinstance(warning, dict)
    ]
    return {
        "review_only": True,
        "shadow_only": True,
        "contract_version": SHADOW_MODEL_CONTRACT_VERSION,
        "model_count": len(rows),
        "models": rows,
        "validation": {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
        },
        "notes": REVIEW_ONLY_NOTE,
    }


__all__ = [
    "ALLOWED_PROMOTION_STATUSES",
    "OUTPUT_SCHEMA_VERSION",
    "REQUIRED_SHADOW_MODEL_FIELDS",
    "REVIEW_ONLY_NOTE",
    "SHADOW_MODEL_CONTRACT_VERSION",
    "STARTER_SHADOW_MODELS",
    "build_shadow_model_registry",
    "normalize_shadow_model_definition",
    "starter_shadow_models",
    "validate_shadow_model_definition",
]
