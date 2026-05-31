"""Presentation helpers for review-only model evaluation context."""

from __future__ import annotations

from typing import Any


DISPLAY_NOTE = (
    "Recommendation-only model evaluation; review-only learning context does not "
    "change official recommendations or promote models."
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def text(value: object, default: str = "") -> str:
    if value is None or value == "":
        return default
    return str(value)


def number(value: object) -> str:
    try:
        return f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return "n/a"


def percent(value: object) -> str:
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def display_label(value: object) -> str:
    labels = {
        "long_term_buy_add": "Long-term buy/add",
        "portfolio_review": "Portfolio review",
        "tactical_trade": "Tactical review",
        "earnings_event": "Earnings review",
        "12_months": "12 months",
        "multi_year": "Multi-year",
        "20_trading_days": "20 days",
        "60_trading_days": "60 days",
        "5_trading_days": "5 days",
        "1_day": "1 day",
        "up": "Up",
        "down": "Down",
        "flat": "Flat",
        "mixed": "Mixed",
        "unknown": "Unknown",
        "not_enough_history": "Not enough history",
        "positive_follow_through": "Positive follow-through",
        "negative_follow_through": "Negative follow-through",
        "target_progress": "Target progress",
        "drawdown_warning": "Drawdown warning",
        "observe": "Observe",
        "assist": "Assist",
        "lean_in": "Lean in",
        "aggressive_candidate": "Aggressive candidate",
    }
    raw = text(value)
    return labels.get(raw, raw.replace("_", " ").title() if raw else "Not available")


def table(headers: list[str], rows: list[list[object]], empty_state: str) -> dict[str, object]:
    return {"headers": headers, "rows": rows, "empty_state": empty_state}


def prediction_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        row.get("model_name", ""),
        row.get("model_version", "") or "Missing",
        display_label(row.get("decision_mode")),
        display_label(row.get("horizon")),
        display_label(row.get("expected_direction")),
        row.get("confidence", ""),
    ]


def registry_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("model_name", ""),
        row.get("model_version", "") or "Missing",
        display_label(row.get("model_role")),
        display_label(row.get("official_or_shadow")),
        display_label(row.get("recommendation_impact")),
        display_label(row.get("score_impact")),
    ]


def backtest_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        display_label(row.get("window")),
        row.get("action", ""),
        display_label(row.get("outcome_status")),
        percent(row.get("return_pct")),
        percent(row.get("excess_return_pct")),
        row.get("model_version", "") or "Missing",
    ]


def benchmark_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        row.get("benchmark_symbol", ""),
        display_label(row.get("data_status")),
        percent(row.get("symbol_return_pct")),
        percent(row.get("benchmark_return_pct")),
        percent(row.get("excess_return_pct")),
    ]


def ai_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        display_label(row.get("thesis_evaluation_label")),
        row.get("confidence", ""),
        display_label(row.get("outcome_alignment")),
    ]


def warning_rows(warnings: list[Any]) -> list[list[object]]:
    return [[text(item)] for item in warnings if text(item)]


def build_model_evaluation_view(context: dict[str, object]) -> dict[str, object]:
    section = as_dict(context.get("model_evaluation"))
    if not section:
        return {
            "available": False,
            "note": DISPLAY_NOTE,
            "cards": [
                {
                    "label": "Model evaluation",
                    "value": "Not available",
                    "detail": "No model evaluation context is available yet.",
                }
            ],
            "predictions": table(["Symbol", "Model", "Version", "Mode", "Horizon", "Direction", "Confidence"], [], "No prediction records are available yet."),
            "registry": table(["Model", "Version", "Role", "Status", "Recommendation Impact", "Score Impact"], [], "No model registry rows are available yet."),
            "backtest": table(["Symbol", "Window", "Action", "Outcome", "Return", "Excess", "Version"], [], "No recommendation backtest rows are available yet."),
            "benchmark": table(["Symbol", "Benchmark", "Status", "Symbol Return", "Benchmark Return", "Excess"], [], "No benchmark comparison rows are available yet."),
            "ai": table(["Symbol", "Evaluation", "Confidence", "Outcome"], [], "No AI thesis evaluation rows are available yet."),
            "warnings": table(["Warning"], [], "No model-evaluation warnings are visible."),
        }

    predictions = as_dict(section.get("prediction_records"))
    registry = as_dict(section.get("model_registry"))
    backtest = as_dict(section.get("recommendation_backtest"))
    benchmark = as_dict(section.get("benchmark_comparison"))
    benchmark_summary = as_dict(benchmark.get("summary"))
    trust = as_dict(section.get("model_trust_score_v1"))
    ai = as_dict(section.get("ai_thesis_evaluation"))
    warnings = as_list(section.get("warnings")) or as_list(trust.get("warnings"))
    prediction_rows = [prediction_row(as_dict(row)) for row in as_list(predictions.get("rows"))]
    registry_rows = [registry_row(as_dict(row)) for row in as_list(registry.get("rows"))]
    backtest_rows = [backtest_row(as_dict(row)) for row in as_list(backtest.get("rows"))]
    benchmark_rows = [benchmark_row(as_dict(row)) for row in as_list(benchmark.get("rows"))]
    ai_rows = [ai_row(as_dict(row)) for row in as_list(ai.get("rows"))]
    cards = [
        {
            "label": "Prediction records",
            "value": text(predictions.get("prediction_count"), "0"),
            "detail": "Immutable review records for what the model expected.",
        },
        {
            "label": "Backtest rows",
            "value": text(as_dict(backtest.get("summary")).get("row_count"), "0"),
            "detail": f"Evaluable rows: {text(as_dict(backtest.get('summary')).get('enough_history_count'), '0')}.",
        },
        {
            "label": "Benchmark status",
            "value": display_label(benchmark_summary.get("status")),
            "detail": f"Average excess return: {percent(benchmark_summary.get('average_excess_return_pct'))}.",
        },
        {
            "label": "Model trust score v1",
            "value": number(trust.get("trust_score")),
            "detail": f"{display_label(trust.get('trust_level'))}; {text(trust.get('confidence'), 'low')} confidence; review-only.",
        },
        {
            "label": "No model promotion",
            "value": "True" if section.get("no_model_promotion", True) else "False",
            "detail": "Trust and backtests are visible for review only.",
        },
    ]
    return {
        "available": True,
        "note": text(section.get("note"), DISPLAY_NOTE),
        "cards": cards,
        "trust": trust,
        "predictions": table(
            ["Symbol", "Model", "Version", "Mode", "Horizon", "Direction", "Confidence"],
            prediction_rows,
            text(predictions.get("empty_state"), "No prediction records are available yet."),
        ),
        "registry": table(
            ["Model", "Version", "Role", "Status", "Recommendation Impact", "Score Impact"],
            registry_rows,
            text(registry.get("empty_state"), "No model registry rows are available yet."),
        ),
        "backtest": table(
            ["Symbol", "Window", "Action", "Outcome", "Return", "Excess", "Version"],
            backtest_rows,
            text(backtest.get("empty_state"), "No recommendation backtest rows are available yet."),
        ),
        "benchmark": table(
            ["Symbol", "Benchmark", "Status", "Symbol Return", "Benchmark Return", "Excess"],
            benchmark_rows,
            text(benchmark.get("empty_state"), "No benchmark comparison rows are available yet."),
        ),
        "ai": table(
            ["Symbol", "Evaluation", "Confidence", "Outcome"],
            ai_rows,
            text(ai.get("empty_state"), "No AI thesis evaluation rows are available yet."),
        ),
        "warnings": table(
            ["Warning"],
            warning_rows(warnings),
            "No model-evaluation warnings are visible.",
        ),
    }


__all__ = ["DISPLAY_NOTE", "build_model_evaluation_view", "display_label"]
