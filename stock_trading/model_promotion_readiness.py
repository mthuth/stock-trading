"""Review-only model promotion readiness helpers.

This module evaluates whether a shadow model has enough evidence to be
considered for a future human promotion review. It does not promote models,
change registry status, update scoring, alter recommendations, or write state.
"""

from __future__ import annotations

import copy
from typing import Iterable, Mapping


READINESS_LABELS = {
    "not_enough_data",
    "keep_shadow",
    "promising_shadow",
    "ready_for_human_review",
    "reject_or_rework",
}
DEFAULT_MINIMUM_SAMPLE_SIZE = 30
DEFAULT_MAX_ACCEPTABLE_DRAWDOWN_PCT = 18.0
DEFAULT_READY_SCORE = 75.0
MAJOR_GUARDRAIL_WARNINGS = {
    "guardrail_failed",
    "major_guardrail_failure",
    "order_or_execution_language",
    "broker_write_risk",
    "automatic_promotion_risk",
}
HIGH_SEVERITY_BIAS_WARNINGS = {
    "look_ahead_bias",
    "survivorship_bias",
    "benchmark_look_ahead_bias",
    "future_data_used",
    "unresolved_high_severity_bias",
}
MISSING_BENCHMARK_STATUSES = {"", "missing", "unavailable", "blocked", "benchmark_missing"}
REVIEW_ONLY_NOTE = (
    "Review-only model promotion readiness. This artifact must not automatically promote models, "
    "change registry status, alter scoring, change targets, change decision-safety rules, alter "
    "allocation, change source weights, change official recommendations, preview orders, write to "
    "brokers, or trade."
)


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
    result = str(value).strip()
    return result if result else default


def token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def rate(value: object) -> float | None:
    if value is None:
        return None
    result = number(value)
    if result > 1:
        result = result / 100
    return max(0.0, min(1.0, result))


def first_value(*values: object) -> object:
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def collect_warnings(*sources: Mapping[str, object]) -> list[str]:
    warnings: list[str] = []
    for source in sources:
        for key in ("warning_flags", "warnings", "bias_warnings", "guardrail_warnings"):
            for item in as_list(source.get(key)):
                warning = text(item)
                if warning:
                    warnings.append(warning)
    return list(dict.fromkeys(warnings))


def model_identity(
    trust_row: Mapping[str, object],
    competition_row: Mapping[str, object],
    context: Mapping[str, object],
) -> tuple[str, str, str]:
    model_name = text(first_value(context.get("model_name"), trust_row.get("model_name"), competition_row.get("model_name")), "unknown_model")
    model_version = text(first_value(context.get("model_version"), trust_row.get("model_version"), competition_row.get("model_version")), "")
    current_status = token(
        first_value(
            context.get("current_status"),
            trust_row.get("current_status"),
            competition_row.get("current_status"),
            competition_row.get("official_or_shadow"),
            trust_row.get("official_or_shadow"),
            "shadow",
        )
    )
    return model_name, model_version, current_status


def sample_size_for(
    trust_row: Mapping[str, object],
    competition_row: Mapping[str, object],
    context: Mapping[str, object],
) -> int:
    raw = first_value(
        context.get("sample_size"),
        trust_row.get("sample_size"),
        competition_row.get("sample_size"),
        competition_row.get("prediction_count"),
        competition_row.get("evaluation_count"),
    )
    return int(max(0, number(raw)))


def benchmark_summary(
    benchmark_row: Mapping[str, object],
    trust_row: Mapping[str, object],
    competition_row: Mapping[str, object],
) -> tuple[bool, float | None]:
    benchmark = as_dict(benchmark_row)
    if not benchmark:
        benchmark = as_dict(trust_row.get("benchmark_comparison_summary")) or as_dict(competition_row.get("benchmark_comparison_summary"))
    status = token(first_value(benchmark.get("status"), benchmark.get("benchmark_data_status"), competition_row.get("benchmark_data_status")))
    excess_raw = first_value(
        benchmark.get("average_excess_return_pct"),
        benchmark.get("excess_return_vs_benchmark_pct"),
        benchmark.get("excess_return_pct"),
        trust_row.get("average_excess_return_pct"),
        competition_row.get("average_excess_return_pct"),
        competition_row.get("excess_return_vs_official_pct"),
    )
    available = status not in MISSING_BENCHMARK_STATUSES and excess_raw is not None
    return available, None if excess_raw is None else number(excess_raw)


def drawdown_pct_for(
    drawdown_row: Mapping[str, object],
    trust_row: Mapping[str, object],
    competition_row: Mapping[str, object],
) -> float | None:
    drawdown = as_dict(drawdown_row)
    backtest = as_dict(trust_row.get("recommendation_backtest_summary") or trust_row.get("backtest_summary"))
    raw = first_value(
        drawdown.get("max_drawdown_pct"),
        drawdown.get("drawdown_pct"),
        trust_row.get("max_drawdown_pct"),
        competition_row.get("max_drawdown_pct"),
        backtest.get("max_drawdown_pct"),
    )
    return None if raw is None else abs(number(raw))


def ai_thesis_rate_for(ai_thesis_row: Mapping[str, object], trust_row: Mapping[str, object]) -> float | None:
    ai = as_dict(ai_thesis_row) or as_dict(trust_row.get("ai_thesis_evaluation_summary") or trust_row.get("ai_thesis_summary"))
    explicit = first_value(ai.get("accuracy"), ai.get("thesis_accuracy"), ai.get("useful_thesis_rate"))
    if explicit is not None:
        return rate(explicit)
    supported = number(ai.get("thesis_supported") or ai.get("supported") or ai.get("useful_theses"))
    contradicted = number(ai.get("thesis_contradicted") or ai.get("contradicted") or ai.get("weak_theses"))
    total = supported + contradicted
    return supported / total if total > 0 else None


def risk_control_signal(competition_row: Mapping[str, object], trust_row: Mapping[str, object]) -> float | None:
    raw = first_value(
        competition_row.get("downside_avoidance_rate"),
        competition_row.get("risk_control_rate"),
        competition_row.get("drawdown_control_rate"),
        trust_row.get("risk_control_rate"),
    )
    return rate(raw)


def outperformance_signal(
    competition_row: Mapping[str, object],
    excess_return_pct: float | None,
) -> tuple[bool, str]:
    win_rate = rate(first_value(competition_row.get("win_rate_vs_official"), competition_row.get("hit_rate"), competition_row.get("wins_rate")))
    competition_excess = first_value(competition_row.get("average_excess_return_pct"), competition_row.get("excess_return_vs_official_pct"))
    excess = number(competition_excess) if competition_excess is not None else excess_return_pct
    if excess is not None and excess >= 3:
        return True, f"Benchmark/competition excess return is {excess:.1f}%."
    if win_rate is not None and win_rate >= 0.58:
        return True, f"Competition win rate is {win_rate:.0%}."
    return False, ""


def readiness_score(
    *,
    sample_size: int,
    minimum_sample_size: int,
    benchmark_available: bool,
    excess_return_pct: float | None,
    drawdown_pct: float | None,
    max_acceptable_drawdown_pct: float,
    risk_control_rate: float | None,
    ai_thesis_rate: float | None,
    warning_count: int,
) -> float:
    sample_points = min(25.0, (sample_size / max(1, minimum_sample_size)) * 25.0)
    benchmark_points = 15.0 if benchmark_available else 0.0
    excess_points = 0.0
    if excess_return_pct is not None:
        excess_points = max(0.0, min(20.0, (excess_return_pct + 2.0) / 12.0 * 20.0))
    drawdown_points = 6.0 if drawdown_pct is None else max(0.0, min(15.0, (max_acceptable_drawdown_pct - drawdown_pct) / max_acceptable_drawdown_pct * 15.0))
    risk_points = (risk_control_rate or 0.0) * 10.0
    thesis_points = (ai_thesis_rate or 0.0) * 10.0
    penalty = min(20.0, warning_count * 4.0)
    return round(max(0.0, min(100.0, sample_points + benchmark_points + excess_points + drawdown_points + risk_points + thesis_points - penalty)), 2)


def readiness_result(
    *,
    model_name: str,
    model_version: str,
    current_status: str,
    sample_size: int,
    minimum_sample_size: int,
    benchmark_available: bool,
    excess_return_pct: float | None,
    drawdown_pct: float | None,
    max_acceptable_drawdown_pct: float,
    score: float,
    strengths: list[str],
    blockers: list[str],
    required_next_evidence: list[str],
    warning_flags: list[str],
    major_guardrail_failure: bool,
    high_severity_bias_warning: bool,
    outperformance: bool,
    useful_risk_control: bool,
) -> dict[str, object]:
    minimum_sample_met = sample_size >= minimum_sample_size
    if major_guardrail_failure:
        label = "reject_or_rework"
        action = "rework_model_before_any_promotion_review"
    elif high_severity_bias_warning:
        label = "keep_shadow"
        action = "resolve_bias_warnings_before_review"
    elif sample_size == 0 or (sample_size < max(5, minimum_sample_size // 3) and not strengths):
        label = "not_enough_data"
        action = "collect_more_shadow_outcomes"
    elif not minimum_sample_met:
        label = "promising_shadow" if strengths else "not_enough_data"
        action = "collect_more_shadow_outcomes"
    elif not benchmark_available:
        label = "keep_shadow"
        action = "add_benchmark_comparison_before_review"
    elif drawdown_pct is not None and drawdown_pct > max_acceptable_drawdown_pct:
        label = "keep_shadow"
        action = "review_drawdown_before_promotion_review"
    elif any(
        blocker.startswith("Model version is missing") or blocker.startswith("Current status is not explicitly shadow-only")
        for blocker in blockers
    ):
        label = "keep_shadow"
        action = "complete_shadow_model_metadata_before_review"
    elif score >= DEFAULT_READY_SCORE and (outperformance or useful_risk_control):
        label = "ready_for_human_review"
        action = "queue_human_promotion_review"
    elif score < 35 and minimum_sample_met:
        label = "reject_or_rework"
        action = "reject_or_rework_shadow_model"
    else:
        label = "promising_shadow" if strengths and score >= 55 else "keep_shadow"
        action = "keep_shadow_and_collect_more_evidence"

    return {
        "model_name": model_name,
        "model_version": model_version,
        "current_status": current_status,
        "promotion_readiness_label": label,
        "readiness_score": score,
        "sample_size": sample_size,
        "minimum_sample_met": minimum_sample_met,
        "strengths": list(dict.fromkeys(strengths)),
        "blockers": list(dict.fromkeys(blockers)),
        "required_next_evidence": list(dict.fromkeys(required_next_evidence)),
        "recommended_human_review_action": action,
        "warning_flags": warning_flags,
        "review_only": True,
        "no_auto_promotion": True,
        "notes": REVIEW_ONLY_NOTE,
    }


def build_model_promotion_readiness(
    context: Mapping[str, object],
    *,
    minimum_sample_size: int = DEFAULT_MINIMUM_SAMPLE_SIZE,
    max_acceptable_drawdown_pct: float = DEFAULT_MAX_ACCEPTABLE_DRAWDOWN_PCT,
) -> dict[str, object]:
    """Build a deterministic shadow-model promotion readiness review."""

    data = as_dict(context)
    trust_row = as_dict(data.get("model_trust_row") or data.get("model_trust") or data.get("model_trust_score"))
    competition_row = as_dict(data.get("model_competition_row") or data.get("model_competition") or data.get("competition_summary"))
    benchmark_row = as_dict(data.get("benchmark_comparison") or data.get("benchmark_comparison_summary"))
    drawdown_row = as_dict(data.get("drawdown_metrics") or data.get("drawdown_summary"))
    ai_thesis_row = as_dict(data.get("ai_thesis_evaluation") or data.get("ai_thesis_evaluation_summary"))

    model_name, model_version, current_status = model_identity(trust_row, competition_row, data)
    sample_size = sample_size_for(trust_row, competition_row, data)
    benchmark_available, excess_return_pct = benchmark_summary(benchmark_row, trust_row, competition_row)
    drawdown_pct = drawdown_pct_for(drawdown_row, trust_row, competition_row)
    ai_thesis_rate = ai_thesis_rate_for(ai_thesis_row, trust_row)
    risk_control_rate = risk_control_signal(competition_row, trust_row)
    warning_flags = collect_warnings(data, trust_row, competition_row, benchmark_row, drawdown_row, ai_thesis_row)
    warning_tokens = {token(flag) for flag in warning_flags}
    major_guardrail_failure = bool(warning_tokens & MAJOR_GUARDRAIL_WARNINGS) or bool(data.get("guardrail_failed") or competition_row.get("guardrail_failed"))
    high_severity_bias_warning = bool(warning_tokens & HIGH_SEVERITY_BIAS_WARNINGS)
    outperformance, outperformance_text = outperformance_signal(competition_row, excess_return_pct)
    useful_risk_control = risk_control_rate is not None and risk_control_rate >= 0.6

    strengths: list[str] = []
    blockers: list[str] = []
    required_next_evidence: list[str] = []
    if outperformance_text:
        strengths.append(outperformance_text)
    if useful_risk_control:
        strengths.append(f"Risk-control evidence is useful at {risk_control_rate:.0%}.")
    if ai_thesis_rate is not None and ai_thesis_rate >= 0.6:
        strengths.append(f"AI thesis evaluation is supportive at {ai_thesis_rate:.0%}.")
    if text(model_version) == "":
        blockers.append("Model version is missing.")
        required_next_evidence.append("Record a model_version before any promotion review.")
    if current_status not in {"shadow", "shadow_only"}:
        blockers.append("Current status is not explicitly shadow-only.")
        required_next_evidence.append("Confirm the candidate is shadow-only before promotion review.")
    if sample_size < minimum_sample_size:
        blockers.append(f"Sample size {sample_size} is below minimum {minimum_sample_size}.")
        required_next_evidence.append("Collect more shadow-model outcomes across horizons and market conditions.")
    if not benchmark_available:
        blockers.append("Benchmark comparison is missing.")
        required_next_evidence.append("Add benchmark comparison over the same evaluation windows.")
    if drawdown_pct is None:
        blockers.append("Drawdown metrics are missing.")
        required_next_evidence.append("Add drawdown metrics before promotion review.")
    elif drawdown_pct > max_acceptable_drawdown_pct:
        blockers.append(f"Max drawdown {drawdown_pct:.1f}% exceeds acceptable threshold {max_acceptable_drawdown_pct:.1f}%.")
        required_next_evidence.append("Review downside behavior and risk explanations before promotion review.")
    if major_guardrail_failure:
        blockers.append("Major guardrail failure blocks promotion readiness.")
        required_next_evidence.append("Resolve guardrail failures and rerun shadow evaluation.")
    if high_severity_bias_warning:
        blockers.append("Unresolved high-severity bias warning blocks promotion readiness.")
        required_next_evidence.append("Resolve look-ahead/survivorship/benchmark-bias warnings before review.")
    if not outperformance and not useful_risk_control:
        blockers.append("No consistent outperformance or useful risk-control signal is available.")
        required_next_evidence.append("Collect evidence of outperformance or downside control versus official/benchmark models.")

    score = readiness_score(
        sample_size=sample_size,
        minimum_sample_size=minimum_sample_size,
        benchmark_available=benchmark_available,
        excess_return_pct=excess_return_pct,
        drawdown_pct=drawdown_pct,
        max_acceptable_drawdown_pct=max_acceptable_drawdown_pct,
        risk_control_rate=risk_control_rate,
        ai_thesis_rate=ai_thesis_rate,
        warning_count=len(warning_flags),
    )
    return readiness_result(
        model_name=model_name,
        model_version=model_version,
        current_status=current_status,
        sample_size=sample_size,
        minimum_sample_size=minimum_sample_size,
        benchmark_available=benchmark_available,
        excess_return_pct=excess_return_pct,
        drawdown_pct=drawdown_pct,
        max_acceptable_drawdown_pct=max_acceptable_drawdown_pct,
        score=score,
        strengths=strengths,
        blockers=blockers,
        required_next_evidence=required_next_evidence,
        warning_flags=warning_flags,
        major_guardrail_failure=major_guardrail_failure,
        high_severity_bias_warning=high_severity_bias_warning,
        outperformance=outperformance,
        useful_risk_control=useful_risk_control,
    )


def build_model_promotion_readiness_review(
    contexts: Iterable[Mapping[str, object]],
    *,
    minimum_sample_size: int = DEFAULT_MINIMUM_SAMPLE_SIZE,
    max_acceptable_drawdown_pct: float = DEFAULT_MAX_ACCEPTABLE_DRAWDOWN_PCT,
) -> dict[str, object]:
    """Build a review-only readiness document for multiple shadow models."""

    rows = [
        build_model_promotion_readiness(
            context,
            minimum_sample_size=minimum_sample_size,
            max_acceptable_drawdown_pct=max_acceptable_drawdown_pct,
        )
        for context in contexts
    ]
    rows.sort(key=lambda row: (text(row.get("model_name")), text(row.get("model_version"))))
    label_counts: dict[str, int] = {}
    for row in rows:
        label = text(row.get("promotion_readiness_label"))
        label_counts[label] = label_counts.get(label, 0) + 1
    return {
        "metadata": {
            "review_only": True,
            "no_auto_promotion": True,
            "labels": sorted(READINESS_LABELS),
            "model_count": len(rows),
            "label_counts": label_counts,
            "notes": REVIEW_ONLY_NOTE,
        },
        "models": rows,
    }


__all__ = [
    "DEFAULT_MAX_ACCEPTABLE_DRAWDOWN_PCT",
    "DEFAULT_MINIMUM_SAMPLE_SIZE",
    "READINESS_LABELS",
    "REVIEW_ONLY_NOTE",
    "build_model_promotion_readiness",
    "build_model_promotion_readiness_review",
]
