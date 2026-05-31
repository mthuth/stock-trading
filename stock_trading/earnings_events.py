"""Review-only earnings event queue helpers."""

from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Iterable, Mapping

from stock_trading.provider_gap_status import EXPECTED, NON_OPERATING_COMPANY, normalize_provider_status


RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only earnings event review. This queue reads approved-universe, "
    "stored evidence, fixture, and provider-gap context without live provider calls and "
    "does not change scores, actions, targets, target confidence, decision safety, "
    "allocation, source weights, broker behavior, or trading."
)

EVENT_TYPES = {
    "upcoming_earnings",
    "recent_earnings",
    "unknown_earnings_date",
    "earnings_data_gap",
}
REVIEW_ACTIONS = {
    "review_pre_earnings",
    "review_post_earnings",
    "wait_for_date_confirmation",
    "monitor_after_report",
    "ignore_for_now",
    "data_gap_review",
}


def _as_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _parse_date(value: object) -> date | None:
    text = _text(value)
    if not text:
        return None
    for candidate in (text[:10], text):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def _report_date(value: date | str | None) -> date:
    if isinstance(value, date):
        return value
    parsed = _parse_date(value)
    return parsed or date.today()


def _symbol(row: Mapping[str, object]) -> str:
    return _text(row.get("symbol")).upper()


def _is_etf(row: Mapping[str, object]) -> bool:
    category = _text(row.get("category")).lower()
    sleeve = _text(row.get("sleeve")).lower()
    trade_type = _text(row.get("trade_type")).lower()
    return sleeve in {"etf", "etf_context"} or trade_type == "etf" or "etf" in category


def _is_foreign_issuer(row: Mapping[str, object]) -> bool:
    symbol = _symbol(row)
    company = _text(row.get("company")).lower()
    notes = _text(row.get("notes")).lower()
    category = _text(row.get("category")).lower()
    return symbol in {"TSM", "ASML"} or any(term in f"{company} {notes} {category}" for term in ("foreign", "adr", "taiwan", "netherlands"))


def _event_date(event: Mapping[str, object]) -> date | None:
    return _parse_date(event.get("earnings_date") or event.get("date") or event.get("source_timestamp"))


def _event_source(event: Mapping[str, object]) -> str:
    return _text(event.get("source") or event.get("source_name") or "stored earnings evidence")


def _event_confidence(event: Mapping[str, object]) -> str:
    return _text(event.get("source_confidence") or event.get("confidence") or "medium")


def _event_status(event: Mapping[str, object]) -> str:
    status = _text(event.get("source_status") or event.get("status") or "ok")
    message = _text(event.get("message"))
    return normalize_provider_status(status, message)


def _stored_event_from_evidence(row: Mapping[str, object]) -> dict[str, object] | None:
    evidence_type = _text(row.get("evidence_type")).lower()
    provider_endpoint = _text(row.get("provider_endpoint")).lower()
    if "earnings" not in evidence_type and "earnings" not in provider_endpoint:
        return None
    event_date = _parse_date(row.get("source_timestamp"))
    if not event_date:
        return None
    return {
        "symbol": _symbol(row),
        "earnings_date": event_date.isoformat(),
        "source": _text(row.get("source_name") or "stored earnings evidence"),
        "source_confidence": _text(row.get("confidence") or "medium"),
        "source_status": "ok",
    }


def earnings_events_by_symbol(
    stored_evidence_rows: Iterable[Mapping[str, object]] = (),
    fixture_events: Iterable[Mapping[str, object]] = (),
) -> dict[str, list[dict[str, object]]]:
    events: dict[str, list[dict[str, object]]] = {}
    for event in fixture_events:
        item = copy.deepcopy(dict(event))
        symbol = _symbol(item)
        if symbol:
            events.setdefault(symbol, []).append(item)
    for row in stored_evidence_rows:
        item = _stored_event_from_evidence(row)
        if item:
            events.setdefault(str(item["symbol"]), []).append(item)
    for symbol_rows in events.values():
        symbol_rows.sort(key=lambda row: _event_date(row) or date.max)
    return events


def provider_gaps_by_symbol(provider_gap_rows: Iterable[Mapping[str, object]]) -> dict[str, list[dict[str, object]]]:
    gaps: dict[str, list[dict[str, object]]] = {}
    for gap in provider_gap_rows:
        symbol = _symbol(gap)
        field = _text(gap.get("field_name") or gap.get("endpoint") or gap.get("provider_endpoint")).lower()
        provider = _text(gap.get("provider"))
        message = _text(gap.get("message"))
        if "earnings" not in field and "earnings" not in provider.lower() and "earnings" not in message.lower():
            continue
        item = dict(gap)
        item["status"] = normalize_provider_status(item.get("status"), item.get("message"))
        if symbol:
            gaps.setdefault(symbol, []).append(item)
    return gaps


def _nearest_event(events: list[dict[str, object]], report_date: date) -> dict[str, object] | None:
    dated = [(event, _event_date(event)) for event in events]
    dated = [(event, event_date) for event, event_date in dated if event_date is not None]
    if not dated:
        return None
    dated.sort(key=lambda pair: (abs((pair[1] - report_date).days), pair[1]))
    return dated[0][0]


def _event_timing(event_date: date | None, report_date: date) -> tuple[str, int | None, int | None]:
    if event_date is None:
        return "unknown_earnings_date", None, None
    delta = (event_date - report_date).days
    if delta >= 0:
        return "upcoming_earnings", delta, None
    return "recent_earnings", None, abs(delta)


def _review_window(
    event_type: str,
    days_until: int | None,
    days_since: int | None,
    *,
    pre_window_days: int,
    post_window_days: int,
) -> str:
    if event_type == "upcoming_earnings" and days_until is not None and days_until <= pre_window_days:
        return "pre_earnings"
    if event_type == "recent_earnings" and days_since is not None and days_since <= post_window_days:
        return "post_earnings"
    if event_type in {"unknown_earnings_date", "earnings_data_gap"}:
        return "unknown"
    return "not_in_window"


def _review_action(event_type: str, review_window: str, source_status: str, is_etf: bool) -> str:
    if is_etf:
        return "ignore_for_now"
    if event_type == "earnings_data_gap":
        return "data_gap_review"
    if source_status not in {"", "ok", "unknown", EXPECTED, NON_OPERATING_COMPANY}:
        return "data_gap_review"
    if review_window == "pre_earnings":
        return "review_pre_earnings"
    if review_window == "post_earnings":
        return "review_post_earnings"
    if event_type == "recent_earnings":
        return "monitor_after_report"
    if event_type == "unknown_earnings_date":
        return "wait_for_date_confirmation"
    return "ignore_for_now"


def _priority(action: str, event_type: str, days_until: int | None, days_since: int | None) -> int:
    if action == "data_gap_review":
        return 10
    if action == "review_pre_earnings":
        return 20 + int(days_until or 0)
    if action == "review_post_earnings":
        return 30 + int(days_since or 0)
    if action == "wait_for_date_confirmation":
        return 70
    if action == "monitor_after_report":
        return 80
    if event_type == "upcoming_earnings":
        return 90 + int(days_until or 0)
    return 120


def _gap_summary(gaps: list[dict[str, object]]) -> tuple[str, str, str]:
    if not gaps:
        return "", "ok", "ok"
    first = gaps[0]
    status = normalize_provider_status(first.get("status"), first.get("message"))
    source = _text(first.get("provider") or "provider gap")
    return source, status, status


def earnings_event_queue_row(
    universe_row: Mapping[str, object],
    events: list[dict[str, object]],
    gaps: list[dict[str, object]],
    report_date: date,
    *,
    pre_window_days: int,
    post_window_days: int,
) -> dict[str, object]:
    symbol = _symbol(universe_row)
    company = _text(universe_row.get("company"))
    etf = _is_etf(universe_row)
    foreign = _is_foreign_issuer(universe_row)
    event = _nearest_event(events, report_date)
    event_date = _event_date(event) if event else None
    event_type, days_until, days_since = _event_timing(event_date, report_date)
    source = _event_source(event or {}) if event else ""
    source_confidence = _event_confidence(event or {}) if event else ("low" if foreign else "")
    source_status = _event_status(event or {}) if event else "unknown"
    provider_gap_source, provider_gap_status, gap_status = _gap_summary(gaps)

    if etf:
        event_type = "unknown_earnings_date"
        source = source or "not_applicable"
        source_confidence = "not_applicable"
        source_status = NON_OPERATING_COMPANY
        provider_gap_status = EXPECTED
    elif gaps and not event:
        event_type = "earnings_data_gap"
        source = provider_gap_source
        source_confidence = "low"
        source_status = gap_status
    elif not event:
        source = "unknown"
        if foreign:
            source = "foreign issuer filing pattern review"
            source_confidence = "low"
            source_status = "unknown"

    review_window = _review_window(
        event_type,
        days_until,
        days_since,
        pre_window_days=pre_window_days,
        post_window_days=post_window_days,
    )
    action = _review_action(event_type, review_window, source_status, etf)
    priority = _priority(action, event_type, days_until, days_since)
    if etf:
        priority = 999
    return {
        "symbol": symbol,
        "company": company,
        "event_type": event_type,
        "earnings_date": event_date.isoformat() if event_date else "",
        "days_until_earnings": days_until,
        "days_since_earnings": days_since,
        "source": source,
        "source_confidence": source_confidence,
        "source_status": source_status,
        "provider_gap_status": provider_gap_status,
        "review_window": review_window,
        "review_priority": priority,
        "recommended_review_action": action,
        "review_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


def build_earnings_event_queue(
    approved_universe_rows: Iterable[Mapping[str, object]],
    *,
    stored_evidence_rows: Iterable[Mapping[str, object]] = (),
    provider_gap_rows: Iterable[Mapping[str, object]] = (),
    report_date: date | str | None = None,
    fixture_events: Iterable[Mapping[str, object]] = (),
    pre_window_days: int = 14,
    post_window_days: int = 7,
) -> dict[str, object]:
    """Build a deterministic, review-only earnings event queue."""

    as_of = _report_date(report_date)
    universe = [copy.deepcopy(dict(row)) for row in approved_universe_rows if _symbol(row)]
    events = earnings_events_by_symbol(stored_evidence_rows, fixture_events)
    gaps = provider_gaps_by_symbol(provider_gap_rows)
    rows = [
        earnings_event_queue_row(
            row,
            events.get(_symbol(row), []),
            gaps.get(_symbol(row), []),
            as_of,
            pre_window_days=pre_window_days,
            post_window_days=post_window_days,
        )
        for row in universe
    ]
    rows.sort(key=lambda row: (int(row["review_priority"]), str(row["symbol"])))
    return {
        "review_only": True,
        "recommendation_only": True,
        "decision_mode": "earnings_event",
        "report_date": as_of.isoformat(),
        "pre_window_days": pre_window_days,
        "post_window_days": post_window_days,
        "rows": rows,
        "note": RECOMMENDATION_ONLY_NOTE,
    }


__all__ = [
    "EVENT_TYPES",
    "RECOMMENDATION_ONLY_NOTE",
    "REVIEW_ACTIONS",
    "build_earnings_event_queue",
]
