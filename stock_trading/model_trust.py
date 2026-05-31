"""Review-only Model Trust Score v1 helpers."""

from __future__ import annotations

import copy
from typing import Mapping


TRUST_LEVELS = {"observe", "assist", "lean_in", "aggressive_candidate"}
REVIEW_ONLY_NOTE = (
    "Review-only Model Trust Score v1. This score does not automatically tune models, "
    "promote models, change official recommendations, change scores, change targets, "
    "change decision-safety rules, alter allocation, change source weights, write to "
    "brokers, preview orders, or trade."
)
GUARDRAILS = (
    "trust_score_does_not_change_official_recommendations",
    "trust_score_does_not_promote_models_automatically",
    "trust_score_does_not_alter_allocation_automatically",
    "trust_score_is_review_only",
)
DEFAULT_ENOUGH_SAMPLE_SIZE = 30
AGGRESSIVE_SAMPLE_SIZE = 100
AGGRESSIVE_TIME_COVERAGE_DAYS = 365
SEVERE_WARNING_TOKENS = {"look_ahead_bias", "survivorship_bias", "benchmark_look_ahead_bias", "high_drawdown"}


def _as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return copy.deepcopy(list(value))
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _token(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _rate(value: object) -> float | None:
    if value is None:
        return None
    number = _number(value)
    if number > 1:
        number = number / 100
    return _clamp(number, 0.0, 1.0)


def _sample_size(context: Mapping[str, object], backtest: Mapping[str, object]) -> int:
    raw = (
        context.get("sample_size")
        or backtest.get("sample_size")
        or backtest.get("recommendation_count")
        or backtest.get("outcome_count")
        or backtest.get("row_count")
        or 0
    )
    return int(max(0, _number(raw)))


def _time_coverage_days(context: Mapping[str, object], backtest: Mapping[str, object]) -> int:
    raw = context.get("time_coverage_days") or backtest.get("time_coverage_days") or backtest.get("coverage_days") or 0
    return int(max(0, _number(raw)))


def _sample_points(sample_size: int) -> float:
    if sample_size <= 0:
        return 0.0
    if sample_size < 10:
        return 2.0
    if sample_size < DEFAULT_ENOUGH_SAMPLE_SIZE:
        return 6.0
    if sample_size < 60:
        return 10.0
    if sample_size < AGGRESSIVE_SAMPLE_SIZE:
        return 13.0
    return 15.0


def _hit_rate_points(hit_rate: float | None) -> tuple[float, str | None, str | None]:
    if hit_rate is None:
        return 0.0, None, "Hit rate is missing."
    points = _clamp((hit_rate - 0.4) / 0.25, 0.0, 1.0) * 18
    strength = f"Hit rate is {hit_rate:.0%}." if hit_rate >= 0.58 else None
    weakness = f"Hit rate is only {hit_rate:.0%}." if hit_rate < 0.5 else None
    return points, strength, weakness


def _excess_return_points(excess_return_pct: float | None) -> tuple[float, str | None, str | None]:
    if excess_return_pct is None:
        return 0.0, None, "Benchmark comparison is missing."
    points = _clamp((excess_return_pct + 2.0) / 14.0, 0.0, 1.0) * 18
    strength = f"Average excess return is {excess_return_pct:.1f}%." if excess_return_pct >= 3 else None
    weakness = f"Average excess return trails benchmark by {abs(excess_return_pct):.1f}%." if excess_return_pct < 0 else None
    return points, strength, weakness


def _drawdown_points(drawdown_pct: float | None) -> tuple[float, str | None, str | None, bool]:
    if drawdown_pct is None:
        return 6.0, None, "Drawdown data is missing.", False
    drawdown = abs(drawdown_pct)
    if drawdown <= 8:
        return 15.0, f"Max drawdown is controlled at {drawdown:.1f}%.", None, False
    if drawdown <= 15:
        return 10.0, None, f"Max drawdown reached {drawdown:.1f}%.", False
    if drawdown <= 25:
        return 4.0, None, f"Max drawdown is elevated at {drawdown:.1f}%.", False
    return 0.0, None, f"Max drawdown is high at {drawdown:.1f}%.", True


def _target_progress_points(value: object) -> tuple[float, str | None, str | None]:
    if value is None:
        return 0.0, None, "Target-progress data is missing."
    progress = _number(value)
    points = _clamp(progress / 60.0, 0.0, 1.0) * 8
    strength = f"Average target progress is {progress:.1f}%." if progress >= 35 else None
    weakness = f"Average target progress is low at {progress:.1f}%." if progress < 10 else None
    return points, strength, weakness


def _decision_safety_points(summary: Mapping[str, object]) -> tuple[float, str | None, str | None]:
    data = _as_dict(summary)
    if not data:
        return 0.0, None, "Decision-safety effectiveness data is missing."
    explicit = data.get("effectiveness_rate") or data.get("success_rate")
    if explicit is not None:
        rate = _rate(explicit) or 0.0
    else:
        avoided = _number(data.get("blocks_likely_avoided_risk"))
        missed = _number(data.get("blocks_may_have_missed_upside"))
        ready = _number(data.get("decision_safe_candidates"))
        denominator = avoided + missed + ready
        rate = avoided / denominator if denominator > 0 else 0.0
    points = _clamp(rate / 0.6, 0.0, 1.0) * 12
    strength = f"Decision-safety evidence is useful ({rate:.0%})." if rate >= 0.45 else None
    weakness = f"Decision-safety evidence is weak or mixed ({rate:.0%})." if rate < 0.25 else None
    return points, strength, weakness


def _source_usefulness_points(summary: Mapping[str, object]) -> tuple[float, str | None, str | None]:
    data = _as_dict(summary)
    if not data:
        return 0.0, None, "Source-usefulness data is missing."
    explicit = data.get("useful_source_rate") or data.get("usefulness_rate")
    if explicit is not None:
        rate = _rate(explicit) or 0.0
    else:
        useful = _number(data.get("consistently_useful") or data.get("useful_sources"))
        noisy = _number(data.get("noisy") or data.get("noisy_sources"))
        total = useful + noisy + _number(data.get("useful_but_sparse") or 0)
        rate = useful / total if total > 0 else 0.0
    points = _clamp(rate / 0.75, 0.0, 1.0) * 8
    strength = f"Source usefulness is supportive ({rate:.0%})." if rate >= 0.6 else None
    weakness = f"Source usefulness is limited ({rate:.0%})." if rate < 0.35 else None
    return points, strength, weakness


def _ai_thesis_points(summary: Mapping[str, object]) -> tuple[float, str | None, str | None]:
    data = _as_dict(summary)
    if not data:
        return 0.0, None, "AI thesis evaluation data is missing."
    explicit = data.get("accuracy") or data.get("thesis_accuracy") or data.get("useful_thesis_rate")
    if explicit is not None:
        rate = _rate(explicit) or 0.0
    else:
        useful = _number(data.get("useful_theses"))
        weak = _number(data.get("weak_theses"))
        total = useful + weak
        rate = useful / total if total > 0 else 0.0
    points = _clamp(rate / 0.75, 0.0, 1.0) * 6
    strength = f"AI thesis accuracy is supportive ({rate:.0%})." if rate >= 0.6 else None
    weakness = f"AI thesis evidence is weak ({rate:.0%})." if rate < 0.35 else None
    return points, strength, weakness


def _warning_flags(context: Mapping[str, object]) -> list[str]:
    flags = [_text(flag) for flag in _as_list(context.get("warning_flags") or context.get("warnings")) if _text(flag)]
    return list(dict.fromkeys(flags))


def _benchmark_available(benchmark: Mapping[str, object], backtest: Mapping[str, object]) -> bool:
    if benchmark:
        status = _token(benchmark.get("status"))
        return status not in {"missing", "unavailable", "blocked"}
    return backtest.get("excess_return_vs_benchmark_pct") is not None or backtest.get("average_excess_return_pct") is not None


def _confidence(sample_size: int, time_coverage_days: int, benchmark_available: bool, warnings: list[str]) -> str:
    severe = any(_token(warning) in SEVERE_WARNING_TOKENS for warning in warnings)
    if sample_size >= AGGRESSIVE_SAMPLE_SIZE and time_coverage_days >= AGGRESSIVE_TIME_COVERAGE_DAYS and benchmark_available and not severe:
        return "high"
    if sample_size >= DEFAULT_ENOUGH_SAMPLE_SIZE and benchmark_available and not severe:
        return "medium"
    return "low"


def _trust_level(
    trust_score: float,
    *,
    sample_size: int,
    time_coverage_days: int,
    benchmark_available: bool,
    warnings: list[str],
) -> str:
    severe = any(_token(warning) in SEVERE_WARNING_TOKENS for warning in warnings)
    if (
        trust_score >= 85
        and sample_size >= AGGRESSIVE_SAMPLE_SIZE
        and time_coverage_days >= AGGRESSIVE_TIME_COVERAGE_DAYS
        and benchmark_available
        and not severe
    ):
        return "aggressive_candidate"
    if trust_score >= 70 and sample_size >= 50 and benchmark_available and not severe:
        return "lean_in"
    if trust_score >= 50 and sample_size >= DEFAULT_ENOUGH_SAMPLE_SIZE and benchmark_available:
        return "assist"
    return "observe"


def _recommended_action(trust_level: str, enough_sample_size: bool) -> str:
    if not enough_sample_size:
        return "collect_more_outcomes"
    if trust_level == "aggressive_candidate":
        return "review_for_future_model_promotion"
    if trust_level == "lean_in":
        return "prepare_model_impact_review"
    if trust_level == "assist":
        return "use_for_review_prioritization"
    return "continue_observing"


def _component(
    name: str,
    points: float,
    max_points: float,
    strengths: list[str],
    weaknesses: list[str],
    strength: str | None,
    weakness: str | None,
) -> dict[str, object]:
    if strength:
        strengths.append(strength)
    if weakness:
        weaknesses.append(weakness)
    return {"name": name, "points": round(points, 4), "max_points": max_points}


def build_model_trust_score(context: Mapping[str, object]) -> dict[str, object]:
    """Build a deterministic, review-only Model Trust Score v1 summary."""

    data = _as_dict(context)
    backtest = _as_dict(data.get("recommendation_backtest_summary") or data.get("backtest_summary"))
    benchmark = _as_dict(data.get("benchmark_comparison_summary") or data.get("benchmark_summary"))
    safety = _as_dict(data.get("decision_safety_effectiveness_summary") or data.get("decision_safety_summary"))
    sources = _as_dict(data.get("source_usefulness_summary"))
    ai_thesis = _as_dict(data.get("ai_thesis_evaluation_summary") or data.get("ai_thesis_summary"))
    sample_size = _sample_size(data, backtest)
    time_coverage_days = _time_coverage_days(data, backtest)
    enough_sample_size = sample_size >= int(_number(data.get("minimum_sample_size"), DEFAULT_ENOUGH_SAMPLE_SIZE))
    benchmark_available = _benchmark_available(benchmark, backtest)
    warnings = _warning_flags(data)
    strengths: list[str] = []
    weaknesses: list[str] = []
    components: list[dict[str, object]] = []

    hit_rate = _rate(backtest.get("hit_rate") or backtest.get("win_rate"))
    excess_return = data.get("excess_return_vs_benchmark_pct")
    if excess_return is None:
        excess_return = benchmark.get("average_excess_return_pct") or benchmark.get("excess_return_vs_benchmark_pct")
    if excess_return is None:
        excess_return = backtest.get("average_excess_return_pct") or backtest.get("excess_return_vs_benchmark_pct")
    max_drawdown = backtest.get("max_drawdown_pct")
    if max_drawdown is None:
        max_drawdown = benchmark.get("max_drawdown_pct")

    hit_points, hit_strength, hit_weakness = _hit_rate_points(hit_rate)
    excess_points, excess_strength, excess_weakness = _excess_return_points(
        None if excess_return is None else _number(excess_return)
    )
    drawdown_points, drawdown_strength, drawdown_weakness, high_drawdown = _drawdown_points(
        None if max_drawdown is None else _number(max_drawdown)
    )
    target_points, target_strength, target_weakness = _target_progress_points(
        backtest.get("average_target_progress_pct") or backtest.get("target_progress_pct")
    )
    safety_points, safety_strength, safety_weakness = _decision_safety_points(safety)
    source_points, source_strength, source_weakness = _source_usefulness_points(sources)
    ai_points, ai_strength, ai_weakness = _ai_thesis_points(ai_thesis)

    components.append(_component("sample_size", _sample_points(sample_size), 15, strengths, weaknesses, None, None))
    components.append(_component("hit_rate", hit_points, 18, strengths, weaknesses, hit_strength, hit_weakness))
    components.append(
        _component("excess_return_vs_benchmark", excess_points, 18, strengths, weaknesses, excess_strength, excess_weakness)
    )
    components.append(_component("drawdown_control", drawdown_points, 15, strengths, weaknesses, drawdown_strength, drawdown_weakness))
    components.append(_component("target_progress", target_points, 8, strengths, weaknesses, target_strength, target_weakness))
    components.append(_component("decision_safety_effectiveness", safety_points, 12, strengths, weaknesses, safety_strength, safety_weakness))
    components.append(_component("source_usefulness", source_points, 8, strengths, weaknesses, source_strength, source_weakness))
    components.append(_component("ai_thesis_accuracy", ai_points, 6, strengths, weaknesses, ai_strength, ai_weakness))

    if not enough_sample_size:
        warnings.append(f"Sample size {sample_size} is below the minimum evidence threshold.")
        weaknesses.append("Sample size is not large enough to trust the model.")
    if not benchmark_available:
        warnings.append("Benchmark comparison is missing; trust confidence is reduced.")
    if high_drawdown:
        warnings.append("High drawdown requires review before increasing model trust.")
    warning_penalty = min(20.0, 5.0 * len(warnings))
    raw_score = sum(_number(component["points"]) for component in components)
    trust_score = round(_clamp(raw_score - warning_penalty, 0.0, 100.0), 2)
    if not enough_sample_size:
        trust_score = min(trust_score, 34.0)
    if high_drawdown:
        trust_score = min(trust_score, 55.0)
    confidence = _confidence(sample_size, time_coverage_days, benchmark_available, warnings)
    trust_level = _trust_level(
        trust_score,
        sample_size=sample_size,
        time_coverage_days=time_coverage_days,
        benchmark_available=benchmark_available,
        warnings=warnings,
    )
    return {
        "model_name": _text(data.get("model_name"), "unknown_model"),
        "model_version": _text(data.get("model_version"), "unknown"),
        "trust_score": trust_score,
        "trust_level": trust_level,
        "sample_size": sample_size,
        "enough_sample_size": enough_sample_size,
        "confidence": confidence,
        "strengths": list(dict.fromkeys(strengths)),
        "weaknesses": list(dict.fromkeys(weaknesses)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_review_action": _recommended_action(trust_level, enough_sample_size),
        "review_only": True,
        "no_model_promotion": True,
        "components": components,
        "guardrails": list(GUARDRAILS),
        "notes": REVIEW_ONLY_NOTE,
    }


__all__ = [
    "AGGRESSIVE_SAMPLE_SIZE",
    "DEFAULT_ENOUGH_SAMPLE_SIZE",
    "GUARDRAILS",
    "REVIEW_ONLY_NOTE",
    "TRUST_LEVELS",
    "build_model_trust_score",
]
