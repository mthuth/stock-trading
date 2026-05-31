"""Deterministic review-only earnings signal extraction.

This module turns stored earnings-related evidence text into structured
review signals. It does not call providers or models, and it does not change
scores, actions, targets, decision safety, allocation, or recommendations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping


SIGNAL_DIRECTIONS = {"positive", "negative", "mixed", "neutral", "unknown"}

SIGNAL_TYPES = {
    "eps_beat",
    "eps_miss",
    "revenue_beat",
    "revenue_miss",
    "guidance_raise",
    "guidance_cut",
    "margin_expansion",
    "margin_pressure",
    "ai_demand_strength",
    "capex_risk",
    "customer_growth",
    "churn_or_demand_risk",
    "cybersecurity_or_operational_risk",
    "valuation_risk",
    "data_insufficient",
}

REVIEW_ONLY_NOTE = (
    "Review-only earnings signal. No scoring, recommendation, target, "
    "decision-safety, allocation, provider, broker, or trading behavior is changed."
)

NO_IMPACT_FIELDS = {
    "score_impact": "none",
    "recommendation_impact": "none",
    "target_impact": "none",
    "decision_safety_impact": "none",
    "allocation_impact": "none",
}

TEXT_FIELDS = (
    "title",
    "headline",
    "summary",
    "raw_text",
    "text",
    "content",
    "notes",
    "event_summary",
    "matched_text",
    "detail",
    "description",
)

EARNINGS_CONTEXT_RE = re.compile(
    r"\b("
    r"earnings|quarter|quarterly|q[1-4]|eps|revenue|sales|guidance|outlook|forecast|"
    r"margin|call|transcript|results|earnings release|investor presentation"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SignalRule:
    signal_type: str
    signal_direction: str
    patterns: tuple[re.Pattern[str], ...]


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.DOTALL)


_POSITIVE_SURPRISE = r"beat(?:s)?|above|exceed(?:ed|s|ing)?|topp(?:ed|s|ing)?|better than|ahead of"
_NEGATIVE_SURPRISE = r"miss(?:ed|es)?|below|short of|weaker than|fell short|underperformed"
_GUIDANCE_UP = r"rais(?:ed|es|e)|lift(?:ed|s)?|boost(?:ed|s)?|increas(?:ed|es|ing)?|above|stronger"
_GUIDANCE_DOWN = r"cut(?:s)?|lower(?:ed|s|ing)?|reduc(?:ed|es|ing)?|slash(?:ed|es)?|below|weaker|down"

SIGNAL_RULES: tuple[SignalRule, ...] = (
    SignalRule(
        "eps_beat",
        "positive",
        (
            _rx(rf"\b(eps|earnings per share)\b.{{0,90}}\b({_POSITIVE_SURPRISE})\b"),
            _rx(rf"\b({_POSITIVE_SURPRISE})\b.{{0,90}}\b(eps|earnings per share)\b"),
        ),
    ),
    SignalRule(
        "eps_miss",
        "negative",
        (
            _rx(rf"\b(eps|earnings per share)\b.{{0,90}}\b({_NEGATIVE_SURPRISE})\b"),
            _rx(rf"\b({_NEGATIVE_SURPRISE})\b.{{0,90}}\b(eps|earnings per share)\b"),
        ),
    ),
    SignalRule(
        "revenue_beat",
        "positive",
        (
            _rx(rf"\b(revenue|sales)\b.{{0,90}}\b({_POSITIVE_SURPRISE})\b"),
            _rx(rf"\b({_POSITIVE_SURPRISE})\b.{{0,90}}\b(revenue|sales)\b"),
        ),
    ),
    SignalRule(
        "revenue_miss",
        "negative",
        (
            _rx(rf"\b(revenue|sales)\b.{{0,90}}\b({_NEGATIVE_SURPRISE})\b"),
            _rx(rf"\b({_NEGATIVE_SURPRISE})\b.{{0,90}}\b(revenue|sales)\b"),
        ),
    ),
    SignalRule(
        "guidance_raise",
        "positive",
        (
            _rx(rf"\b(guidance|outlook|forecast)\b.{{0,100}}\b({_GUIDANCE_UP})\b"),
            _rx(rf"\b({_GUIDANCE_UP})\b.{{0,100}}\b(guidance|outlook|forecast)\b"),
            _rx(r"\bguid(?:ed|ance)\b.{0,80}\babove\b"),
        ),
    ),
    SignalRule(
        "guidance_cut",
        "negative",
        (
            _rx(rf"\b(guidance|outlook|forecast)\b.{{0,100}}\b({_GUIDANCE_DOWN})\b"),
            _rx(rf"\b({_GUIDANCE_DOWN})\b.{{0,100}}\b(guidance|outlook|forecast)\b"),
            _rx(r"\bguid(?:ed|ance)\b.{0,80}\bbelow\b"),
        ),
    ),
    SignalRule(
        "margin_expansion",
        "positive",
        (
            _rx(r"\b(gross |operating |profit )?margin[s]?\b.{0,90}\b(expand(?:ed|s|ing)?|improv(?:ed|es|ing)?|up|widen(?:ed|s|ing)?)\b"),
            _rx(r"\b(expand(?:ed|s|ing)?|improv(?:ed|es|ing)?|widen(?:ed|s|ing)?)\b.{0,90}\b(gross |operating |profit )?margin[s]?\b"),
        ),
    ),
    SignalRule(
        "margin_pressure",
        "negative",
        (
            _rx(r"\b(gross |operating |profit )?margin[s]?\b.{0,90}\b(pressure|compress(?:ed|es|ion)?|declin(?:ed|es|ing)?|contract(?:ed|s|ing)?|down|weaker)\b"),
            _rx(r"\b(pressure|compress(?:ed|es|ion)?|declin(?:ed|es|ing)?|contract(?:ed|s|ing)?|weaker)\b.{0,90}\b(gross |operating |profit )?margin[s]?\b"),
        ),
    ),
    SignalRule(
        "ai_demand_strength",
        "positive",
        (
            _rx(r"\b(ai|accelerator|gpu|data ?center|cloud)\b.{0,90}\b(demand|orders|bookings|workloads)\b.{0,90}\b(strong|robust|surge|accelerat(?:ed|es|ing)?|record|healthy)\b"),
            _rx(r"\b(strong|robust|surging|record|healthy)\b.{0,90}\b(ai|accelerator|gpu|data ?center|cloud)\b.{0,90}\b(demand|orders|bookings|workloads)\b"),
        ),
    ),
    SignalRule(
        "capex_risk",
        "negative",
        (
            _rx(r"\b(capex|capital expenditures|capital spending)\b.{0,100}\b(risk|pressure|elevated|rising|higher|heavy|burden|weigh(?:ed|s|ing)?)\b"),
            _rx(r"\b(elevated|rising|higher|heavy)\b.{0,100}\b(capex|capital expenditures|capital spending)\b"),
        ),
    ),
    SignalRule(
        "customer_growth",
        "positive",
        (
            _rx(r"\b(customer|customers|net new customers|customer additions|rpo|bookings)\b.{0,100}\b(grew|growth|added|record|accelerat(?:ed|es|ing)?|expanded)\b"),
            _rx(r"\b(grew|growth|added|record|accelerat(?:ed|es|ing)?|expanded)\b.{0,100}\b(customer|customers|net new customers|customer additions|rpo|bookings)\b"),
        ),
    ),
    SignalRule(
        "churn_or_demand_risk",
        "negative",
        (
            _rx(r"\b(churn|demand weakness|weaker demand|demand softened|slowdown|elongated sales cycles|customer contraction|retention declined)\b"),
        ),
    ),
    SignalRule(
        "cybersecurity_or_operational_risk",
        "negative",
        (
            _rx(r"\b(breach|cyberattack|security incident|ransomware|outage|operational disruption|supply constraint|production issue)\b"),
        ),
    ),
    SignalRule(
        "valuation_risk",
        "negative",
        (
            _rx(r"\b(valuation|multiple|premium)\b.{0,90}\b(risk|expensive|stretched|elevated|priced for perfection|high)\b"),
            _rx(r"\b(expensive|stretched|priced for perfection|high multiple)\b"),
        ),
    ),
)


def text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def row_value(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = text(row.get(key))
        if value:
            return value
    return ""


def evidence_text(row: Mapping[str, object]) -> str:
    parts = [text(row.get(field)) for field in TEXT_FIELDS]
    return " ".join(part for part in parts if part)


def source_name(row: Mapping[str, object]) -> str:
    return row_value(row, "source_name", "Source", "source", "provider", "provider_name")


def source_type(row: Mapping[str, object]) -> str:
    return row_value(row, "source_type", "Source Type", "source_family", "provider_endpoint", "evidence_type")


def symbol_for_row(row: Mapping[str, object]) -> str:
    return row_value(row, "symbol", "Symbol", "ticker", "Ticker").upper()


def confidence_value(value: object) -> float:
    raw = text(value).lower()
    if not raw:
        return 0.55
    labels = {
        "high": 0.85,
        "medium_high": 0.75,
        "medium": 0.65,
        "medium_low": 0.5,
        "low": 0.35,
        "needs_review": 0.25,
        "weak": 0.25,
    }
    if raw in labels:
        return labels[raw]
    try:
        parsed = float(raw)
    except ValueError:
        return 0.55
    if parsed > 1:
        parsed = parsed / 100.0
    return max(0.0, min(1.0, parsed))


def is_earnings_related(row: Mapping[str, object]) -> bool:
    haystack = " ".join(
        text(row.get(key))
        for key in (
            "evidence_type",
            "source_type",
            "event_type",
            "title",
            "headline",
            "summary",
            "raw_text",
            "text",
            "content",
        )
    )
    return bool(EARNINGS_CONTEXT_RE.search(haystack))


def excerpt_for_match(full_text: str, match: re.Match[str] | None, max_chars: int = 180) -> str:
    compact = " ".join(text(full_text).split())
    if not compact:
        return ""
    if not match:
        return compact[:max_chars]
    start = max(0, match.start() - 45)
    end = min(len(full_text), match.end() + 45)
    excerpt = " ".join(full_text[start:end].split())
    if len(excerpt) <= max_chars:
        return excerpt
    return excerpt[: max_chars - 1].rstrip() + "..."


def confidence_for_row(row: Mapping[str, object], match_count: int, mixed: bool = False) -> float:
    confidence = confidence_value(row.get("confidence") or row.get("Confidence"))
    corroboration = text(row.get("corroboration_status") or row.get("corroboration_label") or row.get("Corroboration")).lower()
    if corroboration in {"primary_plus_confirmed", "independent_confirmed", "multi_source_confirmed"}:
        confidence += 0.08
    elif corroboration in {"single_source", "company_only", "opinion_only", "uncorroborated"}:
        confidence -= 0.08
    confidence += min(0.07, max(0, match_count - 1) * 0.02)
    if mixed:
        confidence -= 0.05
    return round(max(0.05, min(0.95, confidence)), 3)


def _base_signal(row: Mapping[str, object], signal_type: str, direction: str, confidence: float, excerpt: str, notes: str) -> dict[str, object]:
    return {
        "symbol": symbol_for_row(row),
        "signal_type": signal_type,
        "signal_direction": direction,
        "confidence": confidence,
        "source_name": source_name(row),
        "source_type": source_type(row),
        "evidence_excerpt": excerpt,
        "notes": notes,
        "review_only": True,
        **NO_IMPACT_FIELDS,
    }


def extract_earnings_signals_for_row(row: Mapping[str, object]) -> list[dict[str, object]]:
    """Extract deterministic review-only earnings signals from one evidence row."""

    full_text = evidence_text(row)
    signals: list[dict[str, object]] = []
    matched_directions: set[str] = set()
    matched_types: set[str] = set()

    for rule in SIGNAL_RULES:
        matches = [match for pattern in rule.patterns for match in pattern.finditer(full_text)]
        if not matches or rule.signal_type in matched_types:
            continue
        matched_types.add(rule.signal_type)
        matched_directions.add(rule.signal_direction)
        signals.append(
            _base_signal(
                row,
                rule.signal_type,
                rule.signal_direction,
                confidence_for_row(row, len(matches)),
                excerpt_for_match(full_text, matches[0]),
                f"{REVIEW_ONLY_NOTE} Matched deterministic rule: {rule.signal_type}.",
            )
        )

    if signals:
        mixed = len({direction for direction in matched_directions if direction in {"positive", "negative"}}) > 1
        if mixed:
            for signal in signals:
                signal["notes"] = f"{signal['notes']} Mixed positive and negative earnings evidence is present in this row."
        return signals

    if is_earnings_related(row):
        return [
            _base_signal(
                row,
                "data_insufficient",
                "unknown",
                0.1,
                excerpt_for_match(full_text, None),
                f"{REVIEW_ONLY_NOTE} Earnings-related text was present, but no supported signal pattern matched.",
            )
        ]
    return []


def extract_earnings_signals(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Extract review-only earnings signals from stored evidence or event rows."""

    signals: list[dict[str, object]] = []
    for row in rows:
        signals.extend(extract_earnings_signals_for_row(row))
    if signals:
        return signals
    return [
        {
            "symbol": "",
            "signal_type": "data_insufficient",
            "signal_direction": "unknown",
            "confidence": 0.0,
            "source_name": "",
            "source_type": "",
            "evidence_excerpt": "",
            "notes": f"{REVIEW_ONLY_NOTE} No earnings-related evidence rows were available.",
            "review_only": True,
            **NO_IMPACT_FIELDS,
        }
    ]


def summarize_earnings_signals(signals: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Summarize extracted signals without changing any recommendation output."""

    rows = [dict(signal) for signal in signals]
    positive = sum(1 for row in rows if text(row.get("signal_direction")) == "positive")
    negative = sum(1 for row in rows if text(row.get("signal_direction")) == "negative")
    unknown = sum(1 for row in rows if text(row.get("signal_direction")) == "unknown")
    if positive and negative:
        overall = "mixed"
    elif positive:
        overall = "positive"
    elif negative:
        overall = "negative"
    elif unknown:
        overall = "unknown"
    else:
        overall = "neutral"
    return {
        "overall_direction": overall,
        "positive_count": positive,
        "negative_count": negative,
        "unknown_count": unknown,
        "signal_count": len(rows),
        "review_only": True,
        "notes": REVIEW_ONLY_NOTE,
        **NO_IMPACT_FIELDS,
    }
