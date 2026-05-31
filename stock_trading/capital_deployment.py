"""Review-only capital deployment context for long-term buy/add decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping

from stock_trading.capital_availability import (
    RECOMMENDATION_ONLY_NOTE as CAPITAL_AVAILABILITY_NOTE,
    CapitalAvailability,
    capital_availability_from_config,
)


RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only capital deployment context. This helper does not connect to brokers, "
    "preview orders, place trades, tune scores, change targets, change decision safety, "
    "change allocation rules, or mutate official recommendations."
)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _amount(value: object, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value if value is not None else default))
    except (TypeError, ValueError):
        return default


def _optional_amount(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value * 100, 2)


def _item_field(value: object, name: str, default: str = "") -> str:
    if isinstance(value, Mapping):
        return _text(value.get(name), default)
    return _text(getattr(value, name, default), default)


def _candidate_field(candidate: object, name: str, default: str = "") -> str:
    if isinstance(candidate, Mapping):
        direct = candidate.get(name)
        if direct not in (None, ""):
            return _text(direct, default)
        return _item_field(candidate.get("input"), name, default)
    return _item_field(candidate, name, default)


def _allocation_context(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if hasattr(value, "to_context") and callable(value.to_context):
        return dict(value.to_context())
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _decision_safe(decision_gate: Mapping[str, object], allocation_context: Mapping[str, object]) -> bool:
    if "safe_to_buy" in decision_gate:
        return bool(decision_gate.get("safe_to_buy"))
    status = _text(allocation_context.get("decision_safety_status") or decision_gate.get("status")).lower()
    if status:
        return status in {"ready", "safe", "allowed"}
    return True


def _sleeve_config(targets: Mapping[str, object], sleeve: str) -> Mapping[str, object]:
    sleeves = _as_mapping(targets.get("sleeves"))
    return _as_mapping(sleeves.get(sleeve))


@dataclass(frozen=True)
class LongTermSleeveContext:
    sleeve: str
    label: str
    target_pct: float | None
    target_pct_text: str
    target_amount: float | None
    current_value: float | None
    current_pct: float | None
    remaining_to_target: float | None
    status: str

    def to_context(self) -> dict[str, object]:
        return {
            "sleeve": self.sleeve,
            "label": self.label,
            "target_pct": _pct(self.target_pct),
            "target_pct_decimal": self.target_pct,
            "target_pct_text": self.target_pct_text,
            "target_amount": self.target_amount,
            "current_value": self.current_value,
            "current_pct": self.current_pct,
            "remaining_to_target": self.remaining_to_target,
            "status": self.status,
        }


@dataclass(frozen=True)
class CapitalDeploymentContext:
    capital_availability: CapitalAvailability
    long_term_sleeve: LongTermSleeveContext
    deployable_amount: float | None
    held_amount: float | None
    status: str
    reason: str
    candidate: dict[str, object] = field(default_factory=dict)
    allocation_safety: dict[str, object] = field(default_factory=dict)
    reduction_reasons: list[str] = field(default_factory=list)
    review_only: bool = True
    recommendation_only: bool = True
    broker_behavior: str = "none"
    order_behavior: str = "none"

    def to_context(self) -> dict[str, object]:
        return {
            "available_capital": self.capital_availability.available_amount,
            "buy_capacity": self.capital_availability.available_amount,
            "capital_source": self.capital_availability.source,
            "capital_as_of_date": self.capital_availability.as_of_date,
            "capital_freshness": self.capital_availability.freshness,
            "capital_status": self.capital_availability.status,
            "monthly_buy_capacity": self.capital_availability.monthly_buy_capacity,
            "manual_available_cash": self.capital_availability.manual_available_cash,
            "long_term_core_sleeve": self.long_term_sleeve.to_context(),
            "candidate": dict(self.candidate),
            "allocation_safety": dict(self.allocation_safety),
            "deployable_amount": self.deployable_amount,
            "held_amount": self.held_amount,
            "status": self.status,
            "reason": self.reason,
            "reduction_reasons": list(self.reduction_reasons),
            "review_only": self.review_only,
            "recommendation_only": self.recommendation_only,
            "broker_behavior": self.broker_behavior,
            "order_behavior": self.order_behavior,
            "notes": f"{RECOMMENDATION_ONLY_NOTE} {CAPITAL_AVAILABILITY_NOTE}",
        }


def long_term_sleeve_context(
    targets: Mapping[str, object],
    *,
    account_value: float | None = None,
    sleeve_market_values: Mapping[str, object] | None = None,
    sleeve: str = "long_term",
) -> LongTermSleeveContext:
    account = _amount(account_value if account_value is not None else targets.get("account_value"))
    sleeve_cfg = _sleeve_config(targets, sleeve)
    target_pct = _optional_amount(sleeve_cfg.get("target_pct"))
    current_value = None
    current_pct = None
    remaining = None
    target_amount = account * target_pct if account and target_pct is not None else None

    if sleeve_market_values and sleeve in sleeve_market_values:
        current_value = _amount(sleeve_market_values.get(sleeve))
        current_pct = round((current_value / account) * 100, 2) if account else None
        remaining = max(0.0, (target_amount or 0.0) - current_value) if target_amount is not None else None

    if target_pct is None:
        status = "unknown_target"
    elif current_value is None:
        status = "target_known_current_unknown"
    elif remaining and remaining > 0:
        status = "below_target"
    else:
        status = "at_or_above_target"

    target_pct_text = f"{target_pct * 100:.1f}%" if target_pct is not None else "unknown"
    return LongTermSleeveContext(
        sleeve=sleeve,
        label="Long-term/core",
        target_pct=target_pct,
        target_pct_text=target_pct_text,
        target_amount=round(target_amount, 2) if target_amount is not None else None,
        current_value=round(current_value, 2) if current_value is not None else None,
        current_pct=current_pct,
        remaining_to_target=round(remaining, 2) if remaining is not None else None,
        status=status,
    )


def capital_deployment_context(
    targets: Mapping[str, object],
    *,
    candidate: object | None = None,
    decision_gate: Mapping[str, object] | None = None,
    allocation_safety: object | None = None,
    sleeve_market_values: Mapping[str, object] | None = None,
    account_value: float | None = None,
    today: date | None = None,
    stale_after_days: int = 45,
) -> dict[str, object]:
    """Build review-only capital deployment context without changing recommendations."""

    availability = capital_availability_from_config(
        targets,
        today=today,
        stale_after_days=stale_after_days,
    )
    allocation = _allocation_context(allocation_safety)
    decision = dict(decision_gate or {})
    long_term = long_term_sleeve_context(
        targets,
        account_value=account_value,
        sleeve_market_values=sleeve_market_values,
    )
    available = availability.available_amount
    suggested = _optional_amount(allocation.get("suggested_amount"))
    safe_to_add = _decision_safe(decision, allocation)

    if available is None:
        deployable: float | None = None
        held: float | None = None
        status = "needs_manual_update"
        reason = "Capital deployment held for review because available capital is unknown."
    elif not safe_to_add:
        deployable = 0.0
        held = available
        status = "held_no_safe_add"
        reason = "Capital deployment held because the current candidate is not decision-safe."
    else:
        deployable = min(available, suggested) if suggested is not None else available
        held = max(0.0, available - deployable)
        if deployable <= 0:
            status = "held_by_allocation"
            reason = "Capital deployment held because no allocation capacity is available."
        elif held > 0:
            status = "reduced_by_allocation"
            reason = "Capital deployment reduced by existing allocation or buy-capacity limits."
        else:
            status = "deployable"
            reason = "Capital is available for manual long-term add review."

    reduction_reasons = [str(item) for item in allocation.get("reduction_reasons", []) if str(item)]
    allocation_reason = _text(allocation.get("reason"))
    if allocation_reason and allocation_reason not in reason:
        reduction_reasons.append(allocation_reason)

    candidate_context = {
        "symbol": _candidate_field(candidate, "symbol"),
        "company": _candidate_field(candidate, "company"),
        "action": _candidate_field(candidate, "action"),
        "sleeve": _candidate_field(candidate, "sleeve"),
        "trade_type": _candidate_field(candidate, "trade_type"),
        "score": _candidate_field(candidate, "score"),
    }

    return CapitalDeploymentContext(
        capital_availability=availability,
        long_term_sleeve=long_term,
        deployable_amount=round(deployable, 2) if deployable is not None else None,
        held_amount=round(held, 2) if held is not None else None,
        status=status,
        reason=reason,
        candidate=candidate_context,
        allocation_safety=allocation,
        reduction_reasons=reduction_reasons,
    ).to_context()


__all__ = [
    "CapitalDeploymentContext",
    "LongTermSleeveContext",
    "RECOMMENDATION_ONLY_NOTE",
    "capital_deployment_context",
    "long_term_sleeve_context",
]
