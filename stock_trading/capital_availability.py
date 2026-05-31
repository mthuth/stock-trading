"""Manual/config-based capital availability foundation.

This module is intentionally review-only. It reads already-provided config
values and explains available buy capacity without broker access, order
preview, trading, or recommendation mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping


RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only capital availability context. This helper does not "
    "connect to brokers, preview orders, place trades, tune scores, change "
    "source weights, or change official recommendations."
)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _optional_amount(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value: object) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    for candidate in (raw, raw[:10]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def _age_days(as_of: str, today: date) -> int | None:
    parsed = _parse_date(as_of)
    if not parsed:
        return None
    return max(0, (today - parsed).days)


@dataclass(frozen=True)
class CapitalAvailability:
    available_amount: float | None
    monthly_buy_capacity: float | None
    manual_available_cash: float | None
    source: str
    as_of_date: str
    freshness: str
    status: str
    notes: str
    review_only: bool = True
    recommendation_only: bool = True
    broker_behavior: str = "none"

    def to_context(self) -> dict[str, object]:
        return {
            "available_amount": self.available_amount,
            "monthly_buy_capacity": self.monthly_buy_capacity,
            "manual_available_cash": self.manual_available_cash,
            "source": self.source,
            "as_of_date": self.as_of_date,
            "freshness": self.freshness,
            "status": self.status,
            "notes": self.notes,
            "review_only": self.review_only,
            "recommendation_only": self.recommendation_only,
            "broker_behavior": self.broker_behavior,
        }


def capital_availability_from_config(
    config: Mapping[str, object],
    *,
    today: date | None = None,
    stale_after_days: int = 45,
) -> CapitalAvailability:
    """Build review-only capital availability from config/manual values.

    Preferred values live under ``capital_availability``. The legacy
    top-level ``monthly_contribution`` remains a read-only fallback so current
    config can be explained without changing recommendation behavior.
    """

    today = today or date.today()
    section = _as_mapping(config.get("capital_availability"))
    monthly = _optional_amount(
        section.get("monthly_buy_capacity", config.get("monthly_buy_capacity", config.get("monthly_contribution")))
    )
    manual_cash = _optional_amount(section.get("manual_available_cash", config.get("manual_available_cash")))
    as_of_date = _text(section.get("as_of_date", config.get("capital_as_of_date")))
    configured_source = _text(section.get("source"))

    if manual_cash is not None and monthly is not None:
        available_amount = min(manual_cash, monthly)
        source = "manual_and_configured"
    elif manual_cash is not None:
        available_amount = manual_cash
        source = "manual"
    elif monthly is not None:
        available_amount = monthly
        source = configured_source or "configured"
    else:
        available_amount = None
        source = "unknown"

    age = _age_days(as_of_date, today)
    if available_amount is None:
        freshness = "unknown"
        status = "needs_manual_update"
        notes = (
            "No manual available cash or monthly buy capacity is configured. "
            "Add a manual/config value before using capital availability for deployment review."
        )
    elif age is None:
        freshness = "unknown"
        status = "available"
        notes = "Capital availability is configured, but no as-of date is set for freshness review."
    elif age > max(0, stale_after_days):
        freshness = "stale"
        status = "stale"
        notes = f"Capital availability is configured, but the as-of date is {age} days old."
    else:
        freshness = "fresh"
        status = "available"
        notes = "Capital availability is configured for manual deployment review."

    if configured_source and source in {"configured", "unknown"}:
        source = configured_source if available_amount is not None else "unknown"

    return CapitalAvailability(
        available_amount=available_amount,
        monthly_buy_capacity=monthly,
        manual_available_cash=manual_cash,
        source=source,
        as_of_date=as_of_date,
        freshness=freshness,
        status=status,
        notes=f"{notes} {RECOMMENDATION_ONLY_NOTE}",
    )


def capital_availability_context(config: Mapping[str, object], **kwargs: object) -> dict[str, object]:
    return capital_availability_from_config(config, **kwargs).to_context()


__all__ = [
    "CapitalAvailability",
    "RECOMMENDATION_ONLY_NOTE",
    "capital_availability_context",
    "capital_availability_from_config",
]
