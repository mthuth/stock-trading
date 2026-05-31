"""Review-only prediction record helpers for model evaluation."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from typing import Iterable, Mapping

from stock_trading.model_registry import DECISION_MODES, HORIZONS, MODEL_ROLES, validation_result


EXPECTED_DIRECTIONS = {"up", "down", "flat", "mixed", "unknown"}
REQUIRED_PREDICTION_FIELDS = (
    "prediction_id",
    "created_at",
    "report_date",
    "symbol",
    "model_name",
    "model_version",
    "model_role",
    "decision_mode",
    "horizon",
    "expected_direction",
    "confidence",
    "thesis",
    "risks",
    "invalidation_conditions",
    "source_refs",
    "review_only",
)
REVIEW_ONLY_NOTE = (
    "Review-only prediction record. This record captures what a model expected at the time; "
    "it must not automatically change scores, targets, recommendation actions, target "
    "confidence, decision-safety gates, source weights, allocation, broker behavior, or trading."
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def normalize_token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def number_or_none(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value else []
    return []


def generated_at_text(value: str | None = None) -> str:
    return value or datetime.utcnow().isoformat(timespec="seconds")


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def stable_prediction_id(record: Mapping[str, object]) -> str:
    """Build a deterministic id from immutable prediction fields."""

    payload = {
        key: record.get(key)
        for key in (
            "created_at",
            "recommendation_run_id",
            "report_date",
            "symbol",
            "model_name",
            "model_version",
            "model_role",
            "decision_mode",
            "horizon",
            "expected_direction",
            "expected_return_low",
            "expected_return_high",
            "confidence",
            "thesis",
            "risks",
            "invalidation_conditions",
            "source_refs",
        )
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"pred_{digest[:16]}"


def normalize_prediction_record(record: Mapping[str, object], *, created_at: str | None = None) -> dict[str, object]:
    """Return a prediction row with canonical field names and review-only defaults."""

    row = copy.deepcopy(dict(record))
    row["created_at"] = text(row.get("created_at")) or generated_at_text(created_at)
    row["recommendation_run_id"] = row.get("recommendation_run_id")
    row["report_date"] = text(row.get("report_date"))
    row["symbol"] = text(row.get("symbol")).upper()
    row["company"] = text(row.get("company"))
    row["model_name"] = text(row.get("model_name"))
    row["model_version"] = text(row.get("model_version"))
    row["model_role"] = normalize_token(row.get("model_role"))
    row["decision_mode"] = normalize_token(row.get("decision_mode"))
    row["horizon"] = normalize_token(row.get("horizon"))
    row["expected_direction"] = normalize_token(row.get("expected_direction"))
    row["expected_return_low"] = number_or_none(row.get("expected_return_low"))
    row["expected_return_high"] = number_or_none(row.get("expected_return_high"))
    row["confidence"] = text(row.get("confidence"))
    row["thesis"] = text(row.get("thesis"))
    row["risks"] = [text(item) for item in as_list(row.get("risks")) if text(item)]
    row["invalidation_conditions"] = [
        text(item) for item in as_list(row.get("invalidation_conditions")) if text(item)
    ]
    row["source_refs"] = [copy.deepcopy(item) for item in as_list(row.get("source_refs"))]
    row["decision_gate_status"] = text(row.get("decision_gate_status"))
    row["target_confidence"] = text(row.get("target_confidence"))
    row["review_only"] = True
    row["recommendation_only_note"] = text(row.get("recommendation_only_note") or REVIEW_ONLY_NOTE)
    row["prediction_id"] = text(row.get("prediction_id")) or stable_prediction_id(row)
    return row


def validate_prediction_record(record: Mapping[str, object]) -> dict[str, object]:
    """Validate a prediction record without allowing model-impact behavior."""

    row = normalize_prediction_record(record)
    errors: list[dict[str, str]] = []
    for field in REQUIRED_PREDICTION_FIELDS:
        value = row.get(field)
        if value in ("", [], None):
            errors.append(_error(field, f"Missing required prediction field: {field}."))

    if row.get("review_only") is not True:
        errors.append(_error("review_only", "Prediction records must be review_only: true."))
    if text(row.get("model_role")) not in MODEL_ROLES:
        errors.append(_error("model_role", f"Unknown model_role: {row.get('model_role')}."))
    if text(row.get("decision_mode")) not in DECISION_MODES:
        errors.append(_error("decision_mode", f"Unknown decision_mode: {row.get('decision_mode')}."))
    if text(row.get("horizon")) not in HORIZONS:
        errors.append(_error("horizon", f"Unknown horizon: {row.get('horizon')}."))
    if text(row.get("expected_direction")) not in EXPECTED_DIRECTIONS:
        errors.append(_error("expected_direction", f"Unknown expected_direction: {row.get('expected_direction')}."))

    low = number_or_none(row.get("expected_return_low"))
    high = number_or_none(row.get("expected_return_high"))
    if low is not None and high is not None and low > high:
        errors.append(_error("expected_return_low", "expected_return_low must not exceed expected_return_high."))

    if "place trade" in text(row.get("thesis")).lower() or "order preview" in text(row.get("thesis")).lower():
        errors.append(_error("thesis", "Prediction thesis must not contain execution/order-preview language."))

    return validation_result(errors)


def prediction_from_recommendation(
    recommendation: Mapping[str, object],
    *,
    model_name: str,
    model_version: str,
    created_at: str,
    report_date: str | None = None,
    recommendation_run_id: int | None = None,
    decision_mode: str = "long_term_buy_add",
    horizon: str = "12_months",
) -> dict[str, object]:
    """Create a deterministic long-term prediction from a recommendation row."""

    rec = copy.deepcopy(dict(recommendation))
    current = number_or_none(rec.get("current_price"))
    target = number_or_none(rec.get("target_price"))
    upside = number_or_none(rec.get("upside_pct"))
    if upside is None and current and target:
        upside = ((target - current) / current) * 100
    expected_direction = "up" if upside is not None and upside > 1 else "down" if upside is not None and upside < -1 else "flat"
    risk_items = [
        text(item.get("label") if isinstance(item, Mapping) else item)
        for item in as_list(rec.get("top_risks") or rec.get("risks"))
        if text(item.get("label") if isinstance(item, Mapping) else item)
    ]
    if not risk_items:
        risk_items = [text(rec.get("risk_or_uncertainty") or "Outcome may differ if thesis, target, or data quality weakens.")]
    record = {
        "created_at": created_at,
        "recommendation_run_id": recommendation_run_id if recommendation_run_id is not None else rec.get("recommendation_run_id"),
        "report_date": report_date or text(rec.get("report_date")),
        "symbol": rec.get("symbol"),
        "company": rec.get("company"),
        "model_name": model_name,
        "model_version": model_version,
        "model_role": "official",
        "decision_mode": decision_mode,
        "horizon": horizon,
        "expected_direction": expected_direction,
        "expected_return_low": min(0.0, float(upside or 0.0) * 0.25),
        "expected_return_high": float(upside or 0.0),
        "confidence": text(rec.get("confidence") or rec.get("target_confidence")),
        "thesis": text(rec.get("rationale") or rec.get("notes") or rec.get("score_breakdown")),
        "risks": risk_items,
        "invalidation_conditions": as_list(
            rec.get("invalidation_conditions")
            or rec.get("what_would_change_the_view")
            or "Fresh evidence, target confidence, or decision-safety deterioration would invalidate the view."
        ),
        "source_refs": as_list(rec.get("source_refs"))
        or [
            {
                "source_table": "recommendations",
                "symbol": text(rec.get("symbol")).upper(),
                "report_date": report_date or text(rec.get("report_date")),
            }
        ],
        "decision_gate_status": text(rec.get("decision_gate_status") or rec.get("decision_safety_status")),
        "target_confidence": text(rec.get("target_confidence") or rec.get("confidence")),
    }
    return normalize_prediction_record(record)


def prediction_from_ai_packet(
    packet: Mapping[str, object],
    *,
    model_name: str,
    model_version: str,
    created_at: str,
    horizon: str = "12_months",
) -> dict[str, object]:
    """Create an AI-thesis prediction record from an approved prompt packet."""

    data = copy.deepcopy(dict(packet))
    target = data.get("target_context") if isinstance(data.get("target_context"), Mapping) else {}
    decision_safety = data.get("decision_safety") if isinstance(data.get("decision_safety"), Mapping) else {}
    source_refs = data.get("source_attribution") or data.get("source_refs") or []
    record = {
        "created_at": created_at,
        "recommendation_run_id": data.get("recommendation_run_id"),
        "report_date": data.get("report_date"),
        "symbol": data.get("symbol"),
        "company": data.get("company"),
        "model_name": model_name,
        "model_version": model_version,
        "model_role": "ai_brief",
        "decision_mode": "long_term_buy_add",
        "horizon": horizon,
        "expected_direction": "up" if number_or_none(target.get("upside_pct")) and number_or_none(target.get("upside_pct")) > 1 else "mixed",
        "expected_return_low": 0.0,
        "expected_return_high": number_or_none(target.get("upside_pct")),
        "confidence": text(target.get("confidence") or data.get("confidence")),
        "thesis": text(data.get("what_would_change_the_view") or data.get("summary") or "AI thesis packet prepared for future evaluation."),
        "risks": [
            text(row.get("summary") or row.get("headline") or row.get("field") or row.get("latest_detail"))
            for row in [item for item in as_list(data.get("bear_risk_evidence") or data.get("provider_source_gaps")) if isinstance(item, Mapping)]
            if text(row.get("summary") or row.get("headline") or row.get("field") or row.get("latest_detail"))
        ] or ["AI thesis quality depends on source-backed evidence and provider gap status."],
        "invalidation_conditions": as_list(data.get("what_would_change_the_view")),
        "source_refs": source_refs,
        "decision_gate_status": text(decision_safety.get("status")),
        "target_confidence": text(target.get("confidence")),
    }
    return normalize_prediction_record(record)


def build_prediction_record_set(records: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Build a deterministic, review-only prediction record collection."""

    rows = [normalize_prediction_record(record) for record in records]
    rows.sort(key=lambda row: (text(row.get("report_date")), text(row.get("symbol")), text(row.get("horizon")), text(row.get("model_name"))))
    validations = [validate_prediction_record(row) for row in rows]
    errors = [
        {"index": index, **error}
        for index, result in enumerate(validations)
        for error in result.get("errors", [])
        if isinstance(error, dict)
    ]
    return {
        "review_only": True,
        "prediction_record_version": "prediction-records-v1",
        "prediction_count": len(rows),
        "predictions": rows,
        "validation": validation_result(errors),
        "notes": REVIEW_ONLY_NOTE,
    }


__all__ = [
    "EXPECTED_DIRECTIONS",
    "REQUIRED_PREDICTION_FIELDS",
    "REVIEW_ONLY_NOTE",
    "build_prediction_record_set",
    "normalize_prediction_record",
    "prediction_from_ai_packet",
    "prediction_from_recommendation",
    "stable_prediction_id",
    "validate_prediction_record",
]
