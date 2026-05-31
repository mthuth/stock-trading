"""Review-only recommendation backtest summaries."""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Iterable, Mapping

from stock_trading.recommendation_outcomes import (
    BUY_ACTIONS,
    normalized_history,
    outcome_status,
    prices_after_report,
    target_progress,
    text,
    to_float,
)


WINDOWS = {
    "1_day": 1,
    "5_trading_days": 5,
    "20_trading_days": 20,
    "60_trading_days": 60,
    "12_months": 252,
}
POSITIVE_OUTCOMES = {"positive_follow_through", "target_progress"}
NEGATIVE_OUTCOMES = {"negative_follow_through", "drawdown_warning"}
REVIEW_ONLY_NOTE = (
    "Review-only recommendation backtest. Results must not automatically change "
    "scores, actions, recommendation labels, targets, decision-safety rules, "
    "allocation, source weights, broker behavior, or trading."
)
BIAS_WARNING_NOTE = (
    "Backtest uses stored recommendation snapshots and stored later prices only. "
    "Review for survivorship bias, missing benchmark data, insufficient samples, "
    "and any possibility of future data leaking into historical decisions."
)


def normalize_window(value: object) -> tuple[str, int]:
    if isinstance(value, int):
        label = next((name for name, days in WINDOWS.items() if days == value), f"{value}_trading_days")
        return label, int(value)
    token = text(value).lower().replace("-", "_").replace(" ", "_")
    if token in WINDOWS:
        return token, WINDOWS[token]
    try:
        days = int(token)
    except ValueError:
        return "20_trading_days", 20
    label = next((name for name, known_days in WINDOWS.items() if known_days == days), f"{days}_trading_days")
    return label, days


def normalized_windows(windows: Iterable[object]) -> list[tuple[str, int]]:
    values = [normalize_window(window) for window in windows]
    return values or [("20_trading_days", 20)]


def benchmark_rows_for(
    benchmark_price_history: Mapping[str, Iterable[Mapping[str, object]]] | Iterable[Mapping[str, object]] | None,
    rec: Mapping[str, object],
    default_benchmark_symbol: str,
) -> tuple[str, Iterable[Mapping[str, object]]]:
    if benchmark_price_history is None:
        return default_benchmark_symbol, []
    benchmark_symbol = text(rec.get("benchmark_symbol") or rec.get("benchmark") or default_benchmark_symbol).upper()
    if isinstance(benchmark_price_history, Mapping):
        rows = (
            benchmark_price_history.get(benchmark_symbol)
            or benchmark_price_history.get(default_benchmark_symbol)
            or benchmark_price_history.get("BENCHMARK")
            or benchmark_price_history.get("benchmark")
            or []
        )
        return benchmark_symbol, rows
    return benchmark_symbol, benchmark_price_history


def percent_change(start_price: float, later_price: float | None) -> float | None:
    if later_price is None or start_price <= 0:
        return None
    return ((later_price - start_price) / start_price) * 100


def benchmark_return_for(
    benchmark_history: Iterable[Mapping[str, object]],
    report_date: str,
    window_days: int,
) -> tuple[float | None, str]:
    history = normalized_history(benchmark_history)
    anchor_row, later_rows = prices_after_report(history, report_date)
    if not anchor_row:
        return None, ""
    later_row = later_rows[window_days - 1] if len(later_rows) >= window_days else None
    later_price = to_float(later_row.get("close")) if later_row else None
    benchmark_return = percent_change(to_float(anchor_row.get("close")), later_price)
    return (round(benchmark_return, 4) if benchmark_return is not None else None), text(later_row.get("price_date")) if later_row else ""


def recommendation_success(action: str, percent_return: float | None, status: str) -> bool | None:
    if percent_return is None or status == "not_enough_history":
        return None
    if status in POSITIVE_OUTCOMES:
        return True
    if action in {"Trim", "Avoid"} and percent_return <= 0:
        return True
    if action in {"Hold", "Watch"} and status not in {"drawdown_warning", "negative_follow_through"}:
        return True
    return False


def recommendation_backtest_rows(
    recommendations: Iterable[Mapping[str, object]],
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]],
    *,
    benchmark_price_history: Mapping[str, Iterable[Mapping[str, object]]] | Iterable[Mapping[str, object]] | None = None,
    windows: Iterable[object] = WINDOWS.keys(),
    default_benchmark_symbol: str = "BENCHMARK",
) -> list[dict[str, object]]:
    """Evaluate stored recommendation snapshots against stored later prices."""

    rows: list[dict[str, object]] = []
    for rec in recommendations:
        symbol = text(rec.get("symbol")).upper()
        report_date = text(rec.get("report_date") or rec.get("created_at"))
        action = text(rec.get("action"))
        history = normalized_history(price_history_by_symbol.get(symbol, []))
        anchor_row, later_rows = prices_after_report(history, report_date)
        original_current = to_float(rec.get("current_price"))
        if original_current <= 0 and anchor_row:
            original_current = to_float(anchor_row.get("close"))
        original_target = to_float(rec.get("target_price"))
        decision_gate_status = text(rec.get("decision_gate_status") or rec.get("decision_safety_status"))
        benchmark_symbol, benchmark_rows = benchmark_rows_for(benchmark_price_history, rec, default_benchmark_symbol)
        model_version = text(rec.get("model_version") or rec.get("analysis_model_version"))
        decision_mode = text(rec.get("decision_mode") or rec.get("trade_type") or rec.get("sleeve") or "unknown")

        for window_label, window_days in normalized_windows(windows):
            later_row = later_rows[window_days - 1] if len(later_rows) >= window_days else None
            later_price = to_float(later_row.get("close")) if later_row else None
            return_pct = percent_change(original_current, later_price)
            progress = target_progress(original_current, original_target, later_price) if later_price is not None else None
            status = outcome_status(action, return_pct, progress, decision_gate_status)
            benchmark_return, benchmark_price_date = benchmark_return_for(benchmark_rows, report_date, window_days)
            excess_return = return_pct - benchmark_return if return_pct is not None and benchmark_return is not None else None
            success = recommendation_success(action, return_pct, status)
            rows.append(
                {
                    "symbol": symbol,
                    "report_date": report_date,
                    "window": window_label,
                    "window_trading_days": window_days,
                    "action": action,
                    "score": to_float(rec.get("score")),
                    "decision_mode": decision_mode,
                    "model_version": model_version,
                    "original_current_price": round(original_current, 4) if original_current > 0 else 0.0,
                    "original_target": round(original_target, 4) if original_target > 0 else 0.0,
                    "later_price_date": text(later_row.get("price_date")) if later_row else "",
                    "later_price": round(later_price, 4) if later_price is not None else None,
                    "return_pct": round(return_pct, 4) if return_pct is not None else None,
                    "target_progress": round(progress, 4) if progress is not None else None,
                    "outcome_status": status,
                    "hit": success,
                    "benchmark_symbol": benchmark_symbol,
                    "benchmark_price_date": benchmark_price_date,
                    "benchmark_return_pct": benchmark_return,
                    "excess_return_pct": round(excess_return, 4) if excess_return is not None else None,
                    "review_only": True,
                    "notes": REVIEW_ONLY_NOTE,
                }
            )
    rows.sort(key=lambda row: (text(row["report_date"]), text(row["symbol"]), int(row["window_trading_days"])))
    return rows


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def rate(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round((count / total) * 100, 4)


def numeric_values(rows: Iterable[Mapping[str, object]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def hit_rate_rows(rows: Iterable[Mapping[str, object]], group_key: str) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[text(row.get(group_key)) or "missing"].append(row)
    result: dict[str, dict[str, object]] = {}
    for label, group_rows in grouped.items():
        enough = [row for row in group_rows if row.get("hit") is not None]
        hits = len([row for row in enough if row.get("hit") is True])
        result[label] = {
            "row_count": len(group_rows),
            "enough_history_count": len(enough),
            "hit_count": hits,
            "hit_rate": rate(hits, len(enough)),
        }
    return dict(sorted(result.items()))


def warning_messages(
    recommendations: list[Mapping[str, object]],
    rows: list[Mapping[str, object]],
    *,
    benchmark_requested: bool,
    minimum_sample_size: int,
) -> list[str]:
    warnings: list[str] = []
    if not recommendations:
        warnings.append("Missing historical recommendation snapshots; backtest cannot evaluate stored decisions.")
    if any(row.get("outcome_status") == "not_enough_history" for row in rows):
        warnings.append("Some rows do not have enough later stored price history for the requested windows.")
    missing_symbols = sorted({text(row.get("symbol")) for row in rows if row.get("original_current_price") == 0.0})
    if missing_symbols:
        warnings.append(f"Missing price history for symbols: {', '.join(missing_symbols)}.")
    if benchmark_requested and any(row.get("benchmark_return_pct") is None for row in rows):
        warnings.append("Benchmark data is missing or insufficient for some rows.")
    if any(not text(rec.get("model_version") or rec.get("analysis_model_version")) for rec in recommendations):
        warnings.append("Some historical recommendation rows are missing model_version.")
    enough_count = len([row for row in rows if row.get("return_pct") is not None])
    if enough_count < minimum_sample_size:
        warnings.append(f"Insufficient sample size: {enough_count} evaluable row(s), minimum review threshold is {minimum_sample_size}.")
    unique_symbols = {text(row.get("symbol")) for row in rows if text(row.get("symbol"))}
    if rows and len(unique_symbols) <= 1:
        warnings.append("Possible survivor-only universe: backtest includes one or fewer symbols.")
    warnings.append(BIAS_WARNING_NOTE)
    return list(dict.fromkeys(warnings))


def summarize_recommendation_backtest(
    rows: Iterable[Mapping[str, object]],
    *,
    recommendations: Iterable[Mapping[str, object]] = (),
    benchmark_requested: bool = False,
    minimum_sample_size: int = 5,
) -> dict[str, object]:
    """Summarize review-only backtest rows."""

    row_list = [dict(row) for row in rows]
    recommendation_list = [dict(rec) for rec in recommendations]
    enough_rows = [row for row in row_list if row.get("return_pct") is not None]
    returns = numeric_values(enough_rows, "return_pct")
    excess_returns = numeric_values(enough_rows, "excess_return_pct")
    hits = [row for row in enough_rows if row.get("hit") is True]
    positive = [row for row in enough_rows if text(row.get("outcome_status")) in POSITIVE_OUTCOMES]
    negative = [row for row in enough_rows if text(row.get("outcome_status")) in NEGATIVE_OUTCOMES]
    drawdown = [row for row in enough_rows if row.get("outcome_status") == "drawdown_warning"]
    target_progress_rows = [row for row in enough_rows if row.get("outcome_status") == "target_progress"]
    summary = {
        "review_only": True,
        "row_count": len(row_list),
        "enough_history_count": len(enough_rows),
        "not_enough_history_count": len(row_list) - len(enough_rows),
        "average_return": round(mean(returns), 4) if returns else None,
        "median_return": round(median(returns), 4) if returns else None,
        "win_rate": rate(len(hits), len(enough_rows)),
        "positive_follow_through_rate": rate(len(positive), len(enough_rows)),
        "negative_follow_through_rate": rate(len(negative), len(enough_rows)),
        "drawdown_warning_rate": rate(len(drawdown), len(enough_rows)),
        "target_progress_rate": rate(len(target_progress_rows), len(enough_rows)),
        "average_excess_return_vs_benchmark": round(mean(excess_returns), 4) if excess_returns else None,
        "hit_rate_by_action": hit_rate_rows(row_list, "action"),
        "hit_rate_by_decision_mode": hit_rate_rows(row_list, "decision_mode"),
        "hit_rate_by_model_version": hit_rate_rows(row_list, "model_version"),
        "warnings": warning_messages(
            recommendation_list,
            row_list,
            benchmark_requested=benchmark_requested,
            minimum_sample_size=minimum_sample_size,
        ),
        "notes": REVIEW_ONLY_NOTE,
    }
    return summary


def recommendation_backtest(
    recommendations: Iterable[Mapping[str, object]],
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]],
    *,
    benchmark_price_history: Mapping[str, Iterable[Mapping[str, object]]] | Iterable[Mapping[str, object]] | None = None,
    windows: Iterable[object] = WINDOWS.keys(),
    minimum_sample_size: int = 5,
) -> dict[str, object]:
    """Build a review-only recommendation backtest from stored snapshots."""

    recommendation_list = [dict(rec) for rec in recommendations]
    rows = recommendation_backtest_rows(
        recommendation_list,
        price_history_by_symbol,
        benchmark_price_history=benchmark_price_history,
        windows=windows,
    )
    return {
        "metadata": {
            "review_only": True,
            "recommendation_count": len(recommendation_list),
            "windows": [label for label, _ in normalized_windows(windows)],
            "benchmark_requested": benchmark_price_history is not None,
            "notes": REVIEW_ONLY_NOTE,
        },
        "rows": rows,
        "summary": summarize_recommendation_backtest(
            rows,
            recommendations=recommendation_list,
            benchmark_requested=benchmark_price_history is not None,
            minimum_sample_size=minimum_sample_size,
        ),
        "review_only": True,
    }
