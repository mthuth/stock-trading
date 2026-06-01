"""Review-only multi-model competition scoreboard helpers.

These helpers compare official and shadow model outputs from already-stored or
fixture-provided evaluation rows. They do not run models, promote winners,
change official recommendations, tune scores, call providers, or touch broker
behavior.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Iterable, Mapping


DEFAULT_MIN_SAMPLE_SIZE = 30
HIGH_DRAWDOWN_WARNING_RATE = 25.0
REVIEW_ONLY_NOTE = (
    "Review-only shadow model competition. Scoreboard ranks are for manual "
    "review only and do not promote models, change official recommendations, "
    "change scores, change targets, alter decision safety, alter allocation, "
    "change source weights, call providers, preview orders, write to brokers, "
    "or trade."
)
GUARDRAILS = (
    "shadow_models_are_non_authoritative",
    "scoreboard_does_not_promote_models",
    "scoreboard_does_not_change_official_recommendations",
    "scoreboard_does_not_tune_scoring_or_source_weights",
    "scoreboard_is_review_only",
)


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    raw = str(value).strip()
    return raw if raw else default


def _token(value: object, default: str = "unknown") -> str:
    return _text(value, default).lower().replace("-", "_").replace(" ", "_")


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return copy.deepcopy(list(value))
    if value in (None, ""):
        return []
    return [copy.deepcopy(value)]


def _is_positive(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    token = _token(value, "")
    if token in {"true", "yes", "y", "1", "hit", "success", "positive_follow_through", "target_progress", "beat_benchmark"}:
        return True
    if token in {"false", "no", "n", "0", "miss", "failure", "negative_follow_through", "drawdown_warning"}:
        return False
    return None


def _model_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        _text(row.get("model_name"), "unknown_model"),
        _text(row.get("model_version")),
        _token(row.get("decision_mode")),
        _token(row.get("horizon")),
    )


def _base_model(row: Mapping[str, object]) -> dict[str, object]:
    role = _token(row.get("model_role") or row.get("official_or_shadow"), "shadow")
    official_or_shadow = "official" if role == "official" or _token(row.get("official_or_shadow")) == "official" else "shadow"
    return {
        "model_name": _text(row.get("model_name"), "unknown_model"),
        "model_version": _text(row.get("model_version")),
        "model_role": role,
        "official_or_shadow": official_or_shadow,
        "decision_mode": _token(row.get("decision_mode")),
        "horizon": _token(row.get("horizon")),
    }


def _mean(values: Iterable[float]) -> float | None:
    items = [float(value) for value in values]
    if not items:
        return None
    return round(sum(items) / len(items), 4)


def _rate(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round((count / total) * 100, 4)


def _dedupe_warnings(warnings: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(_text(warning) for warning in warnings if _text(warning)))


def _collect_models(
    official_model_results: Iterable[Mapping[str, object]],
    shadow_model_results: Iterable[Mapping[str, object]],
    all_rows: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str, str, str], dict[str, object]]:
    models: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for row in official_model_results:
        base = _base_model({**dict(row), "model_role": "official", "official_or_shadow": "official"})
        models[_model_key(base)] = base
    for row in shadow_model_results:
        base = _base_model({**dict(row), "model_role": _text(row.get("model_role"), "shadow"), "official_or_shadow": "shadow"})
        models[_model_key(base)] = base
    for row in all_rows:
        key = _model_key(row)
        if key not in models and _text(row.get("model_name")):
            models[key] = _base_model(row)
    return models


def _rows_by_key(rows: Iterable[Mapping[str, object]]) -> dict[tuple[str, str, str, str], list[dict[str, object]]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if _text(row.get("model_name")):
            grouped[_model_key(row)].append(copy.deepcopy(dict(row)))
    return grouped


def _trust_by_key(rows: Iterable[Mapping[str, object]]) -> dict[tuple[str, str, str, str], dict[str, object]]:
    result: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for row in rows:
        if _text(row.get("model_name")):
            result[_model_key(row)] = copy.deepcopy(dict(row))
    return result


def _numeric_from_rows(rows: Iterable[Mapping[str, object]], *keys: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        for key in keys:
            if row.get(key) is not None:
                values.append(_number(row.get(key)))
                break
    return values


def _hit_rate(rows: list[Mapping[str, object]]) -> float | None:
    hits = [_is_positive(row.get("hit") if row.get("hit") is not None else row.get("outcome_status")) for row in rows]
    hits = [hit for hit in hits if hit is not None]
    return _rate(len([hit for hit in hits if hit]), len(hits))


def _flag_rate(rows: list[Mapping[str, object]], *keys: str, truthy_tokens: set[str] | None = None) -> float | None:
    if not rows:
        return None
    total = 0
    count = 0
    tokens = truthy_tokens or {"true", "yes", "1"}
    for row in rows:
        matched = False
        for key in keys:
            value = row.get(key)
            if value is None:
                continue
            total += 1
            if isinstance(value, bool):
                matched = value
            else:
                matched = _token(value) in tokens
            break
        if matched:
            count += 1
    return _rate(count, total) if total else None


def _target_progress_rate(rows: list[Mapping[str, object]]) -> float | None:
    values = _numeric_from_rows(rows, "target_progress_rate", "target_progress_pct", "target_progress")
    if values:
        return round(_mean(values) or 0.0, 4)
    return _flag_rate(rows, "target_progress_hit", truthy_tokens={"true", "yes", "1", "target_progress"})


def _ai_alignment(rows: list[Mapping[str, object]]) -> float | None:
    if not rows:
        return None
    values = _numeric_from_rows(rows, "ai_thesis_alignment", "alignment_rate", "accuracy")
    if values:
        return _mean(values)
    positive = {"thesis_supported", "thesis_partially_supported", "aligned", "validated", "useful"}
    negative = {"thesis_contradicted", "contradicted", "guardrail_failed", "insufficient_evidence"}
    scored = []
    for row in rows:
        label = _token(row.get("evaluation_label") or row.get("alignment") or row.get("status"))
        if label in positive:
            scored.append(True)
        elif label in negative:
            scored.append(False)
    return _rate(len([item for item in scored if item]), len(scored)) if scored else None


def _competition_score(row: Mapping[str, object]) -> float:
    hit = _number(row.get("hit_rate"), 50.0)
    excess = _number(row.get("average_excess_return"), 0.0)
    avg_return = _number(row.get("average_return"), 0.0)
    avoided = _number(row.get("avoided_risk_rate"), 0.0)
    missed = _number(row.get("missed_upside_rate"), 0.0)
    drawdown = _number(row.get("drawdown_warning_rate"), 0.0)
    target = _number(row.get("target_progress_rate"), 0.0)
    ai = _number(row.get("ai_thesis_alignment"), 50.0)
    score = (
        hit * 0.25
        + min(max(excess + 10.0, 0.0), 30.0) * 0.9
        + min(max(avg_return + 10.0, 0.0), 30.0) * 0.45
        + avoided * 0.15
        + target * 0.08
        + ai * 0.05
        - drawdown * 0.2
        - missed * 0.15
    )
    if not row.get("enough_sample_size"):
        score -= 25.0
    if row.get("average_excess_return") is None:
        score -= 10.0
    return round(max(0.0, score), 4)


def _warnings_for(
    row: Mapping[str, object],
    *,
    model_result: Mapping[str, object],
    sample_size_threshold: int,
) -> list[str]:
    warnings = [*_as_list(model_result.get("warnings"))]
    if not _text(row.get("model_version")):
        warnings.append("model_version_missing")
    if not row.get("enough_sample_size"):
        warnings.append(f"insufficient_sample_size:{row.get('sample_size')}/{sample_size_threshold}")
    if row.get("average_excess_return") is None:
        warnings.append("benchmark_data_missing")
    if _number(row.get("drawdown_warning_rate")) >= HIGH_DRAWDOWN_WARNING_RATE:
        warnings.append("high_drawdown_warning_rate")
    if _token(model_result.get("universe_scope")) in {"survivor_only", "survivorship_bias"}:
        warnings.append("possible_survivorship_bias")
    if _token(model_result.get("data_window")) in {"future_leak_risk", "look_ahead_bias"}:
        warnings.append("possible_look_ahead_bias")
    return _dedupe_warnings(str(warning) for warning in warnings)


def _row_for_model(
    model: Mapping[str, object],
    key: tuple[str, str, str, str],
    *,
    outcome_rows: list[Mapping[str, object]],
    benchmark_rows: list[Mapping[str, object]],
    trust_row: Mapping[str, object],
    ai_rows: list[Mapping[str, object]],
    model_result: Mapping[str, object],
    sample_size_threshold: int,
) -> dict[str, object]:
    sample_size = int(
        _number(
            model_result.get("sample_size")
            or trust_row.get("sample_size")
            or len(outcome_rows)
        )
    )
    enough_sample_size = sample_size >= sample_size_threshold
    average_excess = _mean(_numeric_from_rows(benchmark_rows or outcome_rows, "excess_return_pct", "excess_return", "average_excess_return"))
    row = {
        **copy.deepcopy(dict(model)),
        "sample_size": sample_size,
        "enough_sample_size": enough_sample_size,
        "hit_rate": _hit_rate(outcome_rows) if outcome_rows else model_result.get("hit_rate"),
        "average_return": _mean(_numeric_from_rows(outcome_rows, "return_pct", "actual_return_pct", "percent_change", "average_return")),
        "average_excess_return": average_excess,
        "drawdown_warning_rate": _flag_rate(outcome_rows, "drawdown_warning", "outcome_status", truthy_tokens={"true", "drawdown_warning", "high_drawdown"}),
        "missed_upside_rate": _flag_rate(outcome_rows, "missed_upside", "decision_safety_outcome", truthy_tokens={"true", "missed_upside", "blocked_later_rose"}),
        "avoided_risk_rate": _flag_rate(outcome_rows, "avoided_risk", "decision_safety_outcome", truthy_tokens={"true", "avoided_risk", "blocked_later_declined"}),
        "target_progress_rate": _target_progress_rate(outcome_rows),
        "ai_thesis_alignment": _ai_alignment(ai_rows),
        "trust_level": _text(trust_row.get("trust_level") or model_result.get("trust_level"), "unknown"),
        "warnings": [],
        "review_only": True,
        "no_model_promotion": True,
        "recommendation_impact": "none",
        "model_promotion": "none",
        "notes": REVIEW_ONLY_NOTE,
    }
    # Allow aggregate model rows to fill sparse fixture metrics without mutating inputs.
    for metric in (
        "hit_rate",
        "average_return",
        "average_excess_return",
        "drawdown_warning_rate",
        "missed_upside_rate",
        "avoided_risk_rate",
        "target_progress_rate",
        "ai_thesis_alignment",
    ):
        if row.get(metric) is None and model_result.get(metric) is not None:
            row[metric] = _number(model_result.get(metric))
    row["competition_score"] = _competition_score(row)
    row["warnings"] = _warnings_for(row, model_result=model_result, sample_size_threshold=sample_size_threshold)
    return row


def _rank_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(_token(row.get("decision_mode")), _token(row.get("horizon")))].append(row)
    ranked: list[dict[str, object]] = []
    for _, group in sorted(grouped.items()):
        group.sort(
            key=lambda row: (
                1 if not row.get("enough_sample_size") else 0,
                -_number(row.get("competition_score")),
                _token(row.get("official_or_shadow")) != "official",
                _text(row.get("model_name")),
            )
        )
        for index, row in enumerate(group, start=1):
            ranked_row = copy.deepcopy(row)
            ranked_row["competition_rank"] = index
            ranked.append(ranked_row)
    ranked.sort(key=lambda row: (_token(row.get("decision_mode")), _token(row.get("horizon")), int(row["competition_rank"])))
    return ranked


def _best_for(rows: list[dict[str, object]], decision_mode: str) -> dict[str, object]:
    eligible = [
        row
        for row in rows
        if _token(row.get("decision_mode")) == decision_mode and row.get("enough_sample_size")
    ]
    if not eligible:
        return {"status": "insufficient_data", "model_name": "", "model_version": "", "competition_score": None}
    best = sorted(eligible, key=lambda row: (-_number(row.get("competition_score")), _text(row.get("model_name"))))[0]
    return {
        "status": "available",
        "model_name": best["model_name"],
        "model_version": best["model_version"],
        "official_or_shadow": best["official_or_shadow"],
        "competition_score": best["competition_score"],
    }


def _best_risk_control(rows: list[dict[str, object]]) -> dict[str, object]:
    eligible = [row for row in rows if row.get("enough_sample_size")]
    if not eligible:
        return {"status": "insufficient_data", "model_name": "", "drawdown_warning_rate": None}
    best = sorted(
        eligible,
        key=lambda row: (
            _number(row.get("drawdown_warning_rate"), 100.0),
            -_number(row.get("avoided_risk_rate")),
            -_number(row.get("competition_score")),
        ),
    )[0]
    return {
        "status": "available",
        "model_name": best["model_name"],
        "model_version": best["model_version"],
        "official_or_shadow": best["official_or_shadow"],
        "drawdown_warning_rate": best["drawdown_warning_rate"],
    }


def build_model_competition_scoreboard(
    official_model_results: Iterable[Mapping[str, object]],
    shadow_model_results: Iterable[Mapping[str, object]],
    *,
    outcome_rows: Iterable[Mapping[str, object]] | None = None,
    benchmark_comparison_rows: Iterable[Mapping[str, object]] | None = None,
    model_trust_rows: Iterable[Mapping[str, object]] | None = None,
    ai_thesis_evaluation_rows: Iterable[Mapping[str, object]] | None = None,
    sample_size_threshold: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> dict[str, object]:
    """Build a deterministic review-only scoreboard for official and shadow models."""

    official = [copy.deepcopy(dict(row)) for row in official_model_results]
    shadows = [copy.deepcopy(dict(row)) for row in shadow_model_results]
    outcomes = [copy.deepcopy(dict(row)) for row in outcome_rows or []]
    benchmarks = [copy.deepcopy(dict(row)) for row in benchmark_comparison_rows or []]
    trust_rows = [copy.deepcopy(dict(row)) for row in model_trust_rows or []]
    ai_rows = [copy.deepcopy(dict(row)) for row in ai_thesis_evaluation_rows or []]

    all_metric_rows = [*official, *shadows, *outcomes, *benchmarks, *trust_rows, *ai_rows]
    models = _collect_models(official, shadows, all_metric_rows)
    outcome_by_key = _rows_by_key(outcomes)
    benchmark_by_key = _rows_by_key(benchmarks)
    trust_by_key = _trust_by_key(trust_rows)
    ai_by_key = _rows_by_key(ai_rows)
    model_result_by_key = {**_rows_by_key(official), **_rows_by_key(shadows)}

    rows = []
    for key, model in models.items():
        result_rows = model_result_by_key.get(key, [{}])
        row = _row_for_model(
            model,
            key,
            outcome_rows=outcome_by_key.get(key, []),
            benchmark_rows=benchmark_by_key.get(key, []),
            trust_row=trust_by_key.get(key, {}),
            ai_rows=ai_by_key.get(key, []),
            model_result=result_rows[0],
            sample_size_threshold=sample_size_threshold,
        )
        rows.append(row)

    ranked_rows = _rank_rows(rows)
    insufficient = [
        {"model_name": row["model_name"], "model_version": row["model_version"], "sample_size": row["sample_size"]}
        for row in ranked_rows
        if not row.get("enough_sample_size")
    ]
    requiring_review = [
        {"model_name": row["model_name"], "model_version": row["model_version"], "warnings": row["warnings"]}
        for row in ranked_rows
        if row.get("warnings")
    ]
    warnings = _dedupe_warnings(warning for row in ranked_rows for warning in row.get("warnings", []))
    return {
        "metadata": {
            "schema_version": 1,
            "sample_size_threshold": sample_size_threshold,
            "model_count": len(ranked_rows),
            "official_model_count": len([row for row in ranked_rows if row["official_or_shadow"] == "official"]),
            "shadow_model_count": len([row for row in ranked_rows if row["official_or_shadow"] == "shadow"]),
            "review_only": True,
            "shadow_only": True,
            "no_model_promotion": True,
            "note": REVIEW_ONLY_NOTE,
            "guardrails": list(GUARDRAILS),
        },
        "scoreboard_rows": ranked_rows,
        "summary": {
            "best_by_long_term": _best_for(ranked_rows, "long_term_buy_add"),
            "best_by_tactical": _best_for(ranked_rows, "tactical_trade"),
            "best_by_earnings": _best_for(ranked_rows, "earnings_event"),
            "best_risk_control": _best_risk_control(ranked_rows),
            "insufficient_data_models": insufficient,
            "models_requiring_review": requiring_review,
            "warnings": warnings,
        },
        "review_only": True,
        "shadow_only": True,
        "no_model_promotion": True,
        "recommendation_impact": "none",
        "notes": REVIEW_ONLY_NOTE,
    }


__all__ = [
    "DEFAULT_MIN_SAMPLE_SIZE",
    "GUARDRAILS",
    "REVIEW_ONLY_NOTE",
    "build_model_competition_scoreboard",
]
