"""Review-only catalyst follow-through analysis."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Iterable, Mapping

from stock_trading.storage.connection import init_db
from stock_trading.storage.provider_repository import price_history_for_symbols
from stock_trading.storage.recommendation_repository import recommendation_score_history


OUTCOME_WINDOWS = (1, 5, 20)
RECOMMENDATION_RANK = {
    "Avoid": 0,
    "Trim": 1,
    "Watch": 2,
    "Hold": 3,
    "Add": 4,
    "Buy": 5,
    "Strong Buy": 6,
}
REVIEW_ONLY_NOTE = (
    "Review-only catalyst follow-through. These metrics must not automatically change scores, "
    "actions, source weights, target prices, target confidence, decision safety, allocations, "
    "broker behavior, or trading."
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
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


def normalized_price_history(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen_dates: set[str] = set()
    for row in rows:
        price_date = text(row.get("price_date") or row.get("date"))
        close = to_float(row.get("adjusted_close")) or to_float(row.get("close"))
        if not price_date or close <= 0 or price_date in seen_dates:
            continue
        seen_dates.add(price_date)
        normalized.append(
            {
                "price_date": price_date,
                "close": close,
                "provider": text(row.get("provider")),
            }
        )
    normalized.sort(key=lambda row: text(row["price_date"]))
    return normalized


def source_mix_for_event(event: Mapping[str, object]) -> dict[str, object]:
    independent = to_int(event.get("independent_source_count"))
    primary = to_int(event.get("primary_source_count"))
    company = to_int(event.get("company_source_count"))
    opinion = to_int(event.get("opinion_source_count"))
    source_count = to_int(event.get("source_count"))

    if independent > 0 and primary > 0:
        label = "primary_and_independent"
    elif independent > 0:
        label = "independent_confirmed"
    elif primary > 0:
        label = "primary_source"
    elif company > 0 and source_count == company:
        label = "company_only"
    elif opinion > 0 and source_count == opinion:
        label = "opinion_context_only"
    elif source_count <= 1:
        label = "single_source"
    else:
        label = "mixed"

    return {
        "label": label,
        "source_count": source_count,
        "evidence_count": to_int(event.get("evidence_count")),
        "independent_source_count": independent,
        "primary_source_count": primary,
        "company_source_count": company,
        "opinion_source_count": opinion,
    }


def price_window_moves(
    event_date: str,
    history_rows: Iterable[Mapping[str, object]],
    windows: Iterable[int] = OUTCOME_WINDOWS,
) -> dict[str, dict[str, object]]:
    history = normalized_price_history(history_rows)
    parsed_event_date = parse_date(event_date)
    moves: dict[str, dict[str, object]] = {}
    if not parsed_event_date or not history:
        for window in windows:
            moves[f"{int(window)}d"] = {
                "window_trading_days": int(window),
                "status": "missing_price_history",
                "start_price_date": "",
                "start_price": None,
                "later_price_date": "",
                "later_price": None,
                "percent_change": None,
            }
        return moves

    start_index = next(
        (
            index
            for index, row in enumerate(history)
            if (parse_date(row.get("price_date")) or date.min) >= parsed_event_date
        ),
        None,
    )
    if start_index is None:
        for window in windows:
            moves[f"{int(window)}d"] = {
                "window_trading_days": int(window),
                "status": "missing_price_history",
                "start_price_date": "",
                "start_price": None,
                "later_price_date": "",
                "later_price": None,
                "percent_change": None,
            }
        return moves

    start_row = history[start_index]
    start_price = to_float(start_row.get("close"))
    for window in windows:
        window_days = int(window)
        target_index = start_index + window_days
        later_row = history[target_index] if target_index < len(history) else None
        later_price = to_float(later_row.get("close")) if later_row else None
        percent_change = (
            ((later_price - start_price) / start_price) * 100
            if later_price is not None and start_price > 0
            else None
        )
        moves[f"{window_days}d"] = {
            "window_trading_days": window_days,
            "status": "available" if later_row else "insufficient_future_price_history",
            "start_price_date": text(start_row.get("price_date")),
            "start_price": start_price,
            "later_price_date": text(later_row.get("price_date")) if later_row else "",
            "later_price": later_price,
            "percent_change": round(percent_change, 4) if percent_change is not None else None,
        }
    return moves


def recommendation_change_after_event(
    symbol: str,
    event_date: str,
    recommendation_rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    parsed_event_date = parse_date(event_date)
    normalized: list[dict[str, object]] = []
    for row in recommendation_rows:
        if text(row.get("symbol")).upper() != symbol.upper():
            continue
        report_date = parse_date(row.get("report_date") or row.get("created_at"))
        if not report_date:
            continue
        normalized.append(
            {
                "report_date": report_date.isoformat(),
                "action": text(row.get("action")),
                "score": to_float(row.get("score")),
            }
        )
    normalized.sort(key=lambda row: text(row["report_date"]))
    if not parsed_event_date:
        return {
            "status": "missing_event_date",
            "changed": False,
            "before_action": "",
            "before_report_date": "",
            "after_action": "",
            "after_report_date": "",
            "direction": "unknown",
        }

    before = [
        row
        for row in normalized
        if (parse_date(row.get("report_date")) or date.min) <= parsed_event_date
    ]
    after = [
        row
        for row in normalized
        if (parse_date(row.get("report_date")) or date.min) > parsed_event_date
    ]
    before_row = before[-1] if before else None
    after_row = after[0] if after else None
    before_action = text(before_row.get("action")) if before_row else ""
    after_action = text(after_row.get("action")) if after_row else ""
    changed = bool(before_action and after_action and before_action != after_action)
    before_rank = RECOMMENDATION_RANK.get(before_action)
    after_rank = RECOMMENDATION_RANK.get(after_action)
    if before_rank is None or after_rank is None or not changed:
        direction = "unchanged" if before_action and after_action else "unknown"
    elif after_rank > before_rank:
        direction = "stronger"
    elif after_rank < before_rank:
        direction = "weaker"
    else:
        direction = "unchanged"
    return {
        "status": "available" if before_row and after_row else "not_enough_recommendation_history",
        "changed": changed,
        "before_action": before_action,
        "before_report_date": text(before_row.get("report_date")) if before_row else "",
        "after_action": after_action,
        "after_report_date": text(after_row.get("report_date")) if after_row else "",
        "direction": direction,
    }


def primary_percent_change(price_moves: Mapping[str, Mapping[str, object]]) -> float | None:
    for key in ("20d", "5d", "1d"):
        value = price_moves.get(key, {}).get("percent_change")
        if value is not None:
            return to_float(value)
    return None


def catalyst_outcome_label(
    event: Mapping[str, object],
    price_moves: Mapping[str, Mapping[str, object]],
    recommendation_change: Mapping[str, object],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    source_mix = source_mix_for_event(event)
    source_label = text(source_mix.get("label"))
    percent_change = primary_percent_change(price_moves)
    direction = text(recommendation_change.get("direction"))

    if percent_change is None:
        return "neutral", ["missing_price_history"]
    if source_label == "company_only":
        reasons.append("company_only_needs_independent_review")
        if percent_change <= -5:
            return "likely_noisy", reasons + ["negative_follow_through"]
        return "neutral", reasons
    if source_label == "opinion_context_only":
        reasons.append("opinion_context_only")
        if percent_change >= 8 and direction == "stronger":
            return "neutral", reasons + ["positive_but_uncorroborated"]
        return "likely_noisy", reasons
    if percent_change >= 3 and source_label in {"independent_confirmed", "primary_and_independent", "primary_source"}:
        return "likely_useful", ["positive_follow_through", source_label]
    if direction == "stronger" and source_label in {"independent_confirmed", "primary_and_independent", "primary_source"}:
        return "likely_useful", ["recommendation_strengthened_after_event", source_label]
    if percent_change <= -3:
        return "likely_noisy", ["negative_follow_through"]
    return "neutral", ["limited_follow_through"]


def catalyst_follow_through_rows(
    events: Iterable[Mapping[str, object]],
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]],
    recommendation_history: Iterable[Mapping[str, object]] = (),
    windows: Iterable[int] = OUTCOME_WINDOWS,
) -> list[dict[str, object]]:
    """Calculate deterministic review-only catalyst outcomes for event clusters."""

    rows: list[dict[str, object]] = []
    recommendations = list(recommendation_history)
    for event in events:
        symbol = text(event.get("symbol")).upper()
        event_date = text(event.get("event_date") or event.get("latest_evidence_at"))
        price_moves = price_window_moves(event_date, price_history_by_symbol.get(symbol, []), windows)
        recommendation_change = recommendation_change_after_event(symbol, event_date, recommendations)
        label, reasons = catalyst_outcome_label(event, price_moves, recommendation_change)
        rows.append(
            {
                "symbol": symbol,
                "event_date": event_date,
                "event_type": text(event.get("event_type")),
                "headline": text(event.get("headline")),
                "summary": text(event.get("summary")),
                "source_mix": source_mix_for_event(event),
                "corroboration_label": text(event.get("corroboration_label")),
                "confidence": to_float(event.get("confidence")),
                "price_moves": price_moves,
                "recommendation_change": recommendation_change,
                "outcome_label": label,
                "outcome_reasons": reasons,
                "review_only": True,
                "notes": REVIEW_ONLY_NOTE,
            }
        )
    rows.sort(key=lambda row: (text(row["event_date"]), text(row["symbol"]), text(row["event_type"])))
    return rows


def evidence_event_cluster_history(limit: int = 500) -> list[dict[str, object]]:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, event_date, symbol, event_key, event_type, headline, summary,
               corroboration_label, source_count, evidence_count,
               independent_source_count, primary_source_count, company_source_count,
               opinion_source_count, latest_evidence_at, confidence, notes
        FROM evidence_event_clusters
        ORDER BY event_date ASC, id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def build_catalyst_follow_through_review(
    limit: int = 500,
    windows: Iterable[int] = OUTCOME_WINDOWS,
) -> dict[str, object]:
    events = evidence_event_cluster_history(limit=limit)
    symbols = sorted({text(row.get("symbol")).upper() for row in events if row.get("symbol")})
    price_history = price_history_for_symbols(symbols)
    recommendation_history = recommendation_score_history(limit=limit)
    rows = catalyst_follow_through_rows(events, price_history, recommendation_history, windows)
    return {
        "metadata": {
            "review_only": True,
            "windows": [int(window) for window in windows],
            "event_count": len(events),
            "outcome_count": len(rows),
            "notes": REVIEW_ONLY_NOTE,
        },
        "outcomes": rows,
    }
