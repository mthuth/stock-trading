"""Review-only benchmark comparison helpers.

These helpers compare stored recommendation or tactical outcome rows against
stored benchmark price history. They do not fetch live data and do not change
recommendations, scores, targets, gates, allocation, source weights, provider
behavior, broker behavior, or model tuning.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping


SUPPORTED_BENCHMARKS = ("SPY", "QQQ", "SMH", "VGT")
DEFAULT_FALLBACK_BENCHMARK = "SPY"
REVIEW_ONLY_NOTE = (
    "Review-only benchmark comparison. Results must not automatically change "
    "scores, actions, targets, decision safety, allocations, source weights, "
    "provider behavior, broker behavior, or model tuning."
)

SEMICONDUCTOR_SYMBOLS = {"AMD", "ARM", "MU", "TSM", "ASML", "SMH", "NVDA", "AVGO"}
TECH_CORE_SYMBOLS = {"MSFT", "GOOGL", "AMZN", "META", "NET", "DDOG", "SNOW", "MDB", "CRWD", "PANW"}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_date(value: object) -> date | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw, raw[:10]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def normalized_history(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        price_date = text(row.get("price_date") or row.get("date"))
        close = to_float(row.get("adjusted_close")) or to_float(row.get("close")) or to_float(row.get("price"))
        if not price_date or close <= 0 or price_date in seen:
            continue
        normalized.append(
            {
                "price_date": price_date,
                "close": close,
                "provider": text(row.get("provider")),
            }
        )
        seen.add(price_date)
    normalized.sort(key=lambda row: text(row["price_date"]))
    return normalized


def available_symbols(price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]]) -> set[str]:
    return {
        text(symbol).upper()
        for symbol, rows in price_history_by_symbol.items()
        if text(symbol) and normalized_history(rows)
    }


def _first_available(candidates: Iterable[str], available: set[str]) -> str:
    for candidate in candidates:
        if candidate in available:
            return candidate
    return ""


def select_benchmark(
    symbol: str,
    metadata: Mapping[str, object] | None = None,
    *,
    available_benchmarks: Iterable[str] = SUPPORTED_BENCHMARKS,
    explicit_benchmark: str = "",
    fallback_benchmark: str = DEFAULT_FALLBACK_BENCHMARK,
) -> tuple[str, list[str]]:
    """Select a benchmark symbol from available stored benchmark histories."""

    metadata = metadata or {}
    available = {text(item).upper() for item in available_benchmarks if text(item)}
    warnings: list[str] = []
    override = text(explicit_benchmark or metadata.get("benchmark_override")).upper()
    if override:
        if override in available:
            return override, warnings
        return override, [f"benchmark_missing:{override}"]

    normalized_symbol = text(symbol).upper()
    category = text(metadata.get("category")).lower()
    sleeve = text(metadata.get("sleeve")).lower()
    trade_type = text(metadata.get("trade_type") or metadata.get("tactical_horizon")).lower()
    preferred: list[str]
    if normalized_symbol in SEMICONDUCTOR_SYMBOLS or "semiconductor" in category:
        preferred = ["SMH", "QQQ", "VGT", fallback_benchmark]
    elif normalized_symbol in TECH_CORE_SYMBOLS or any(
        token in category
        for token in ("mega-cap", "cloud", "software", "cybersecurity", "ai/platform")
    ):
        preferred = ["QQQ", "VGT", fallback_benchmark]
    elif "etf" in sleeve or "etf" in category:
        preferred = ["QQQ", "SPY", "VGT"]
    elif "tactical" in sleeve or "day" in trade_type or "week" in trade_type:
        preferred = ["QQQ", fallback_benchmark]
    else:
        preferred = [fallback_benchmark, "QQQ", "VGT", "SMH"]
    selected = _first_available(preferred, available)
    if selected:
        return selected, warnings
    fallback = text(fallback_benchmark).upper() or DEFAULT_FALLBACK_BENCHMARK
    return fallback, [f"benchmark_missing:{fallback}"]


def benchmark_window_return(
    history_rows: Iterable[Mapping[str, object]],
    anchor_date: object,
    window: int,
    *,
    stale_after_days: int = 5,
) -> tuple[float | None, dict[str, object], list[str]]:
    """Calculate benchmark return using prices known on/after the outcome anchor."""

    history = normalized_history(history_rows)
    anchor = parse_date(anchor_date)
    if not history or not anchor:
        return None, {}, ["benchmark_missing_history"]
    if window <= 0:
        return None, {}, ["benchmark_missing_window"]
    anchor_rows = [row for row in history if (parse_date(row.get("price_date")) or date.min) <= anchor]
    later_rows = [row for row in history if (parse_date(row.get("price_date")) or date.min) > anchor]
    if not anchor_rows:
        return None, {}, ["benchmark_missing_anchor_price"]
    anchor_row = anchor_rows[-1]
    anchor_price_date = parse_date(anchor_row.get("price_date"))
    warnings: list[str] = []
    if anchor_price_date and (anchor - anchor_price_date).days > stale_after_days:
        warnings.append(f"benchmark_stale:{(anchor - anchor_price_date).days}d")
    if len(later_rows) < int(window):
        warnings.append("benchmark_missing_window_price")
        return None, {"anchor": anchor_row}, warnings
    later_row = later_rows[int(window) - 1]
    anchor_price = to_float(anchor_row.get("close"))
    later_price = to_float(later_row.get("close"))
    if anchor_price <= 0 or later_price <= 0:
        warnings.append("benchmark_invalid_price")
        return None, {"anchor": anchor_row, "later": later_row}, warnings
    return_pct = ((later_price - anchor_price) / anchor_price) * 100
    return (
        round(return_pct, 4),
        {"anchor": anchor_row, "later": later_row},
        warnings,
    )


def outcome_anchor_date(row: Mapping[str, object]) -> str:
    return text(row.get("setup_date") or row.get("report_date") or row.get("date"))


def outcome_window(row: Mapping[str, object]) -> int:
    raw = row.get("window_trading_days") or row.get("window") or row.get("horizon_days")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def outcome_symbol_return(row: Mapping[str, object]) -> float | None:
    if row.get("symbol_return_pct") is not None:
        return to_float(row.get("symbol_return_pct"))
    if row.get("percent_change") is not None:
        return to_float(row.get("percent_change"))
    if row.get("return_pct") is not None:
        return to_float(row.get("return_pct"))
    return None


def compare_outcome_to_benchmark(
    outcome_row: Mapping[str, object],
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]],
    *,
    metadata: Mapping[str, object] | None = None,
    explicit_benchmark: str = "",
    fallback_benchmark: str = DEFAULT_FALLBACK_BENCHMARK,
    stale_after_days: int = 5,
) -> dict[str, object]:
    symbol = text(outcome_row.get("symbol")).upper()
    window = outcome_window(outcome_row)
    anchor = outcome_anchor_date(outcome_row)
    symbol_return = outcome_symbol_return(outcome_row)
    available = available_symbols(price_history_by_symbol)
    benchmark_symbol, selection_warnings = select_benchmark(
        symbol,
        metadata,
        available_benchmarks=(symbol for symbol in SUPPORTED_BENCHMARKS if symbol in available),
        explicit_benchmark=explicit_benchmark,
        fallback_benchmark=fallback_benchmark,
    )
    benchmark_return, price_context, return_warnings = benchmark_window_return(
        price_history_by_symbol.get(benchmark_symbol, []),
        anchor,
        window,
        stale_after_days=stale_after_days,
    )
    warnings = [*selection_warnings, *return_warnings]
    if symbol_return is None:
        warnings.append("symbol_return_missing")
    excess_return = (
        round(symbol_return - benchmark_return, 4)
        if symbol_return is not None and benchmark_return is not None
        else None
    )
    if benchmark_return is None:
        data_status = "benchmark_missing"
    elif any(warning.startswith("benchmark_stale:") for warning in warnings):
        data_status = "benchmark_stale"
    elif symbol_return is None:
        data_status = "symbol_return_missing"
    else:
        data_status = "ok"
    return {
        "symbol": symbol,
        "anchor_date": anchor,
        "window": window,
        "symbol_return_pct": round(symbol_return, 4) if symbol_return is not None else None,
        "benchmark_symbol": benchmark_symbol,
        "benchmark_return_pct": benchmark_return,
        "excess_return_pct": excess_return,
        "beat_benchmark": excess_return is not None and excess_return > 0,
        "data_status": data_status,
        "warnings": warnings,
        "benchmark_anchor_date": text(price_context.get("anchor", {}).get("price_date")) if price_context else "",
        "benchmark_later_date": text(price_context.get("later", {}).get("price_date")) if price_context else "",
        "review_only": True,
        "model_tuning_impact": "none",
        "recommendation_impact": "none",
        "notes": REVIEW_ONLY_NOTE,
    }


def benchmark_comparison_rows(
    outcome_rows: Iterable[Mapping[str, object]],
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]],
    *,
    metadata_by_symbol: Mapping[str, Mapping[str, object]] | None = None,
    explicit_benchmark: str = "",
    fallback_benchmark: str = DEFAULT_FALLBACK_BENCHMARK,
    stale_after_days: int = 5,
) -> list[dict[str, object]]:
    metadata_by_symbol = metadata_by_symbol or {}
    rows = [
        compare_outcome_to_benchmark(
            outcome,
            price_history_by_symbol,
            metadata=metadata_by_symbol.get(text(outcome.get("symbol")).upper(), {}),
            explicit_benchmark=explicit_benchmark,
            fallback_benchmark=fallback_benchmark,
            stale_after_days=stale_after_days,
        )
        for outcome in outcome_rows
    ]
    rows.sort(key=lambda row: (text(row["anchor_date"]), text(row["symbol"]), int(row["window"])))
    return rows
