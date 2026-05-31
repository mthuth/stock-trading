"""Review-only post-earnings reaction analysis."""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping


POST_EARNINGS_WINDOW_DAYS = 10
POSITIVE_REACTION_THRESHOLD = 3.0
STRONG_POSITIVE_REACTION_THRESHOLD = 6.0
NEGATIVE_REACTION_THRESHOLD = -3.0
RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only post-earnings review. These signals must not automatically "
    "change scores, actions, targets, target confidence, decision safety, suggested "
    "amounts, allocation rules, broker behavior, or trading."
)


POSITIVE_TERMS = {
    "beat",
    "beats",
    "raise",
    "raised",
    "raises",
    "raising",
    "strong",
    "strength",
    "accelerate",
    "accelerated",
    "acceleration",
    "margin expansion",
    "revenue growth",
    "eps beat",
    "guidance raise",
    "ai demand",
    "capex efficiency",
    "backlog",
    "thesis intact",
    "thesis improved",
    "improved",
}
NEGATIVE_TERMS = {
    "miss",
    "missed",
    "misses",
    "cut guidance",
    "lowered guidance",
    "weak guidance",
    "weak",
    "weakened",
    "slowdown",
    "deceleration",
    "margin pressure",
    "margin compression",
    "risk",
    "risks",
    "headwind",
    "headwinds",
    "demand softening",
    "revenue miss",
    "eps miss",
    "capex risk",
    "thesis weakened",
}
POSITIVE_TOKENS = {"positive", "bullish", "improved", "improve", "beat", "strong", "raise", "raised"}
NEGATIVE_TOKENS = {"negative", "bearish", "weakened", "weaken", "miss", "weak", "risk", "lowered", "cut"}
BLOCKING_GAP_STATUSES = {"blocked", "rate_limited", "missing", "stale", "parser_gap", "error"}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def normalized_token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_date(value: object) -> date | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw, raw.replace("Z", "+00:00"), raw[:10]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def row_symbol(row: Mapping[str, object]) -> str:
    return text(row.get("symbol") or row.get("Symbol")).upper()


def row_date(row: Mapping[str, object]) -> date | None:
    return parse_date(
        row.get("event_date")
        or row.get("earnings_date")
        or row.get("published_at")
        or row.get("latest_evidence_at")
        or row.get("source_timestamp")
        or row.get("created_at")
        or row.get("date")
    )


def row_headline(row: Mapping[str, object]) -> str:
    return text(row.get("headline") or row.get("title") or row.get("summary") or row.get("notes"))


def row_summary(row: Mapping[str, object]) -> str:
    return text(row.get("summary") or row.get("detail") or row.get("notes") or row.get("headline") or row.get("title"))


def normalized_price_history(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    history: list[dict[str, object]] = []
    seen_dates: set[str] = set()
    for row in rows:
        price_date = text(row.get("price_date") or row.get("date"))
        parsed = parse_date(price_date)
        close = to_float(row.get("adjusted_close")) or to_float(row.get("close"))
        if not parsed or not price_date or close <= 0 or price_date in seen_dates:
            continue
        seen_dates.add(price_date)
        history.append(
            {
                "price_date": parsed.isoformat(),
                "close": close,
                "provider": text(row.get("provider")),
            }
        )
    history.sort(key=lambda row: text(row["price_date"]))
    return history


def price_reaction(
    earnings_date: date | None,
    history_rows: Iterable[Mapping[str, object]],
) -> tuple[float | None, dict[str, object], list[str]]:
    history = normalized_price_history(history_rows)
    if not earnings_date:
        return None, {"status": "missing_earnings_date"}, ["Missing earnings date."]
    if not history:
        return None, {"status": "missing_price_history"}, ["Missing stored price history."]

    baseline_rows = [
        row for row in history if (parse_date(row.get("price_date")) or date.min) <= earnings_date
    ]
    later_rows = [
        row for row in history if (parse_date(row.get("price_date")) or date.min) > earnings_date
    ]
    if not baseline_rows:
        return None, {"status": "missing_baseline_price"}, ["Missing baseline price on or before earnings."]
    if not later_rows:
        return None, {"status": "missing_post_earnings_price"}, ["Missing post-earnings price reaction."]

    baseline = baseline_rows[-1]
    later = later_rows[0]
    baseline_close = to_float(baseline.get("close"))
    later_close = to_float(later.get("close"))
    if baseline_close <= 0 or later_close <= 0:
        return None, {"status": "invalid_price_history"}, ["Stored price history has invalid close values."]

    pct = ((later_close - baseline_close) / baseline_close) * 100
    return (
        round(pct, 4),
        {
            "status": "available",
            "baseline_price_date": text(baseline.get("price_date")),
            "baseline_price": baseline_close,
            "reaction_price_date": text(later.get("price_date")),
            "reaction_price": later_close,
        },
        [],
    )


def rows_for_symbol_in_window(
    symbol: str,
    earnings_date: date | None,
    rows: Iterable[Mapping[str, object]],
    post_window_days: int,
) -> list[Mapping[str, object]]:
    if not earnings_date:
        return []
    selected: list[Mapping[str, object]] = []
    for row in rows:
        candidate_symbol = row_symbol(row)
        if candidate_symbol and candidate_symbol != symbol:
            continue
        parsed = row_date(row)
        if parsed is None or 0 <= (parsed - earnings_date).days <= post_window_days:
            selected.append(row)
    return selected


def evidence_signal(row: Mapping[str, object]) -> str:
    structured = " ".join(
        normalized_token(row.get(key))
        for key in (
            "thesis_signal",
            "thesis_impact",
            "sentiment",
            "sentiment_label",
            "impact",
            "event_type",
            "corroboration_label",
        )
    )
    if any(token in structured for token in NEGATIVE_TOKENS):
        return "negative"
    if any(token in structured for token in POSITIVE_TOKENS):
        return "positive"

    payload = f"{row_headline(row)} {row_summary(row)}".lower()
    positive = any(term in payload for term in POSITIVE_TERMS)
    negative = any(term in payload for term in NEGATIVE_TERMS)
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "neutral"


def evidence_review(
    symbol: str,
    earnings_date: date | None,
    evidence_rows: Iterable[Mapping[str, object]],
    post_window_days: int,
) -> dict[str, object]:
    rows = rows_for_symbol_in_window(symbol, earnings_date, evidence_rows, post_window_days)
    summary: list[str] = []
    risk_summary: list[str] = []
    signals = {"positive": 0, "negative": 0, "mixed": 0, "neutral": 0}
    for row in rows:
        headline = row_headline(row) or row_summary(row)
        if headline and len(summary) < 4:
            summary.append(headline)
        signal = evidence_signal(row)
        signals[signal] = signals.get(signal, 0) + 1
        if signal in {"negative", "mixed"} and headline and len(risk_summary) < 4:
            risk_summary.append(headline)

    if rows and not summary:
        summary.append(f"{len(rows)} post-earnings evidence row(s) reviewed.")
    return {
        "rows": list(rows),
        "summary": summary,
        "risk_summary": risk_summary,
        "positive_count": signals["positive"],
        "negative_count": signals["negative"],
        "mixed_count": signals["mixed"],
        "neutral_count": signals["neutral"],
    }


def provider_gap_messages(
    symbol: str,
    provider_gaps: Iterable[Mapping[str, object]],
) -> list[str]:
    messages: list[str] = []
    for gap in provider_gaps:
        candidate_symbol = row_symbol(gap)
        if candidate_symbol and candidate_symbol != symbol:
            continue
        status = normalized_token(gap.get("status") or gap.get("severity"))
        if status not in BLOCKING_GAP_STATUSES:
            continue
        provider = text(gap.get("provider") or gap.get("source") or "provider")
        field = text(gap.get("field_name") or gap.get("field") or gap.get("data_type") or "data")
        issue = text(gap.get("latest_issue") or gap.get("message") or gap.get("notes"))
        detail = f"{provider} {field} is {status}"
        if issue:
            detail = f"{detail}: {issue}"
        messages.append(detail)
    return messages[:6]


def ai_readiness_gap(ai_context: Mapping[str, object] | None) -> str:
    if not isinstance(ai_context, Mapping):
        return ""
    status = normalized_token(ai_context.get("status") or ai_context.get("readiness_status"))
    if not status or status in {"ready", "ready_for_ai_synthesis", "generated", "available"}:
        return ""
    summary = text(ai_context.get("summary") or ai_context.get("reason") or ai_context.get("readiness_reason"))
    return f"AI synthesis not ready: {status}{f' - {summary}' if summary else ''}"


def source_usefulness_notes(
    symbol: str,
    rows: Iterable[Mapping[str, object]],
) -> list[str]:
    notes: list[str] = []
    for row in rows:
        candidate_symbol = row_symbol(row)
        if candidate_symbol and candidate_symbol != symbol:
            continue
        label = normalized_token(row.get("label") or row.get("usefulness_label") or row.get("quality_label"))
        if label in {"noisy", "stale_or_blocked", "needs_more_history"}:
            source = text(row.get("source_name") or row.get("source") or "source")
            notes.append(f"{source} source usefulness is {label}")
    return notes[:4]


def recommendation_context(
    symbol: str,
    earnings_date: date | None,
    recommendation_rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    if not earnings_date:
        return {
            "status": "missing_earnings_date",
            "changed": False,
            "before_action": "",
            "after_action": "",
        }
    rows: list[dict[str, object]] = []
    for row in recommendation_rows:
        if row_symbol(row) != symbol:
            continue
        parsed = parse_date(row.get("report_date") or row.get("created_at") or row.get("date"))
        if not parsed:
            continue
        rows.append(
            {
                "report_date": parsed.isoformat(),
                "action": text(row.get("action")),
                "score": to_float(row.get("score")),
            }
        )
    rows.sort(key=lambda row: text(row["report_date"]))
    before = [row for row in rows if (parse_date(row.get("report_date")) or date.min) <= earnings_date]
    after = [row for row in rows if (parse_date(row.get("report_date")) or date.min) > earnings_date]
    before_row = before[-1] if before else None
    after_row = after[0] if after else None
    before_action = text(before_row.get("action")) if before_row else ""
    after_action = text(after_row.get("action")) if after_row else ""
    return {
        "status": "available" if before_row or after_row else "not_enough_recommendation_history",
        "changed": bool(before_action and after_action and before_action != after_action),
        "before_action": before_action,
        "before_report_date": text(before_row.get("report_date")) if before_row else "",
        "after_action": after_action,
        "after_report_date": text(after_row.get("report_date")) if after_row else "",
    }


def classify_reaction(
    *,
    days_since_earnings: int | None,
    post_window_days: int,
    price_reaction_pct: float | None,
    evidence: Mapping[str, object],
    data_gaps: list[str],
) -> tuple[str, str, str]:
    if days_since_earnings is None or days_since_earnings < 0 or days_since_earnings > post_window_days:
        return "not_in_post_earnings_window", "not_applicable", "ignore_for_now"

    positive_count = int(evidence.get("positive_count") or 0)
    negative_count = int(evidence.get("negative_count") or 0)
    mixed_count = int(evidence.get("mixed_count") or 0)
    has_evidence = bool(evidence.get("rows"))
    has_positive = positive_count > 0
    has_negative = negative_count > 0

    if not has_evidence or price_reaction_pct is None:
        return "data_insufficient", "unknown", "wait_for_call_or_filing"
    if mixed_count > 0 or (has_positive and has_negative):
        return "mixed_reaction", "mixed", "monitor_reaction"
    if has_negative:
        return "thesis_weakened", "weakened", "review_thesis_risk"
    if price_reaction_pct <= NEGATIVE_REACTION_THRESHOLD and has_positive:
        return "market_overreaction_possible", "intact_but_market_sold_off", "review_for_add_after_earnings"
    if price_reaction_pct >= STRONG_POSITIVE_REACTION_THRESHOLD and has_positive and not data_gaps:
        return "thesis_improved", "improved", "review_for_add_after_earnings"
    if price_reaction_pct >= POSITIVE_REACTION_THRESHOLD and has_positive:
        return "market_confirmation", "improved", "monitor_reaction"
    if has_positive:
        return "mixed_reaction", "evidence_positive_but_market_muted", "monitor_reaction"
    return "data_insufficient", "unknown", "wait_for_call_or_filing"


def build_post_earnings_review(
    earnings_event: Mapping[str, object],
    *,
    evidence_rows: Iterable[Mapping[str, object]] = (),
    price_history: Iterable[Mapping[str, object]] = (),
    recommendation_rows: Iterable[Mapping[str, object]] = (),
    ai_context: Mapping[str, object] | None = None,
    provider_gaps: Iterable[Mapping[str, object]] = (),
    source_usefulness: Iterable[Mapping[str, object]] = (),
    as_of: object | None = None,
    post_window_days: int = POST_EARNINGS_WINDOW_DAYS,
) -> dict[str, object]:
    """Build a deterministic, review-only post-earnings reaction row."""

    symbol = row_symbol(earnings_event)
    company = text(earnings_event.get("company") or earnings_event.get("company_name") or earnings_event.get("name"))
    earnings_date = parse_date(earnings_event.get("earnings_date") or earnings_event.get("event_date") or earnings_event.get("date"))
    as_of_date = parse_date(as_of) or date.today()
    days_since_earnings = (as_of_date - earnings_date).days if earnings_date else None

    price_pct, price_context, price_gaps = price_reaction(earnings_date, price_history)
    evidence = evidence_review(symbol, earnings_date, evidence_rows, post_window_days)
    gaps = list(price_gaps)
    if not evidence.get("rows"):
        gaps.append("Missing post-earnings evidence or call/filing review.")
    gaps.extend(provider_gap_messages(symbol, provider_gaps))
    ai_gap = ai_readiness_gap(ai_context)
    if ai_gap:
        gaps.append(ai_gap)

    source_notes = source_usefulness_notes(symbol, source_usefulness)
    risk_summary = list(evidence.get("risk_summary") or [])
    risk_summary.extend(source_notes)

    reaction_label, thesis_impact, review_action = classify_reaction(
        days_since_earnings=days_since_earnings,
        post_window_days=post_window_days,
        price_reaction_pct=price_pct,
        evidence=evidence,
        data_gaps=gaps,
    )

    return {
        "symbol": symbol,
        "company": company,
        "earnings_date": earnings_date.isoformat() if earnings_date else "",
        "days_since_earnings": days_since_earnings,
        "price_reaction_pct": price_pct,
        "price_reaction": price_context,
        "reaction_label": reaction_label,
        "thesis_impact": thesis_impact,
        "recommended_review_action": review_action,
        "evidence_summary": list(evidence.get("summary") or []),
        "risk_summary": risk_summary,
        "data_gaps": gaps,
        "recommendation_context": recommendation_context(symbol, earnings_date, recommendation_rows),
        "review_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


def build_post_earnings_reviews(
    earnings_events: Iterable[Mapping[str, object]],
    *,
    evidence_rows: Iterable[Mapping[str, object]] = (),
    price_history_by_symbol: Mapping[str, Iterable[Mapping[str, object]]] | None = None,
    recommendation_rows: Iterable[Mapping[str, object]] = (),
    ai_context_by_symbol: Mapping[str, Mapping[str, object]] | None = None,
    provider_gaps: Iterable[Mapping[str, object]] = (),
    source_usefulness: Iterable[Mapping[str, object]] = (),
    as_of: object | None = None,
    post_window_days: int = POST_EARNINGS_WINDOW_DAYS,
) -> list[dict[str, object]]:
    """Build deterministic post-earnings reviews for multiple events."""

    price_history_by_symbol = price_history_by_symbol or {}
    ai_context_by_symbol = ai_context_by_symbol or {}
    rows: list[dict[str, object]] = []
    for event in earnings_events:
        symbol = row_symbol(event)
        rows.append(
            build_post_earnings_review(
                event,
                evidence_rows=evidence_rows,
                price_history=price_history_by_symbol.get(symbol, ()),
                recommendation_rows=recommendation_rows,
                ai_context=ai_context_by_symbol.get(symbol),
                provider_gaps=provider_gaps,
                source_usefulness=source_usefulness,
                as_of=as_of,
                post_window_days=post_window_days,
            )
        )
    rows.sort(key=lambda row: (text(row["earnings_date"]), text(row["symbol"])))
    return rows
