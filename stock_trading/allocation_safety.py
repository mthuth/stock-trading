"""Suggested-buy allocation safety checks for recommendation context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _as_dict(value: object) -> Dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _pct(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value * 100, 2)


def position_market_value(position: Mapping[str, object] | None) -> float:
    if not position:
        return 0.0
    return _as_float(position.get("market_value"))


def sleeve_market_values_for_ranked(
    ranked: Iterable[Mapping[str, object]],
    positions: Mapping[str, Mapping[str, object]],
) -> Dict[str, float]:
    """Summarize current holdings by recommendation sleeve."""

    symbol_to_sleeve: Dict[str, str] = {}
    for row in ranked:
        item = row.get("input")
        symbol = str(getattr(item, "symbol", "") or "")
        sleeve = str(getattr(item, "sleeve", "") or "")
        if symbol and sleeve:
            symbol_to_sleeve[symbol] = sleeve

    values: Dict[str, float] = {}
    for symbol, position in positions.items():
        sleeve = symbol_to_sleeve.get(symbol)
        if not sleeve:
            continue
        values[sleeve] = values.get(sleeve, 0.0) + position_market_value(position)
    return values


@dataclass
class AllocationLimit:
    name: str
    label: str
    amount_available: float
    cap_pct: Optional[float] = None
    current_value: Optional[float] = None


@dataclass
class AllocationSafetyResult:
    symbol: str
    sleeve: str
    suggested_amount: float
    buy_capacity: float
    account_value: float
    current_position_market_value: float
    current_position_pct: float
    position_after_buy_pct: float
    decision_safety_status: str
    watchlist_only_blocked: bool
    applied_limit: str
    reduction_reasons: List[str] = field(default_factory=list)
    limits: List[AllocationLimit] = field(default_factory=list)
    reason: str = ""

    @property
    def buy_capacity_held(self) -> float:
        return max(0.0, self.buy_capacity - self.suggested_amount)

    def to_context(self) -> Dict[str, object]:
        return {
            "symbol": self.symbol,
            "sleeve": self.sleeve,
            "suggested_amount": round(self.suggested_amount, 2),
            "buy_capacity": round(self.buy_capacity, 2),
            "buy_capacity_held": round(self.buy_capacity_held, 2),
            "account_value": round(self.account_value, 2),
            "current_position_market_value": round(self.current_position_market_value, 2),
            "current_position_pct": round(self.current_position_pct, 2),
            "position_after_buy_pct": round(self.position_after_buy_pct, 2),
            "decision_safety_status": self.decision_safety_status,
            "watchlist_only_blocked": self.watchlist_only_blocked,
            "applied_limit": self.applied_limit,
            "reduction_reasons": list(self.reduction_reasons),
            "reason": self.reason,
            "limits": [
                {
                    "name": limit.name,
                    "label": limit.label,
                    "amount_available": round(max(0.0, limit.amount_available), 2),
                    "cap_pct": _pct(limit.cap_pct),
                    "current_value": (
                        round(limit.current_value, 2)
                        if limit.current_value is not None
                        else None
                    ),
                }
                for limit in self.limits
            ],
        }


def _single_stock_cap_pct(sleeve: str, targets: Mapping[str, object]) -> float:
    sleeves = _as_dict(targets.get("sleeves"))
    sleeve_config = _as_dict(sleeves.get(sleeve))
    speculative_config = _as_dict(targets.get("speculative_ai"))

    if sleeve == "etf":
        return _as_float(
            sleeve_config.get("max_single_etf_pct"),
            _as_float(sleeve_config.get("max_single_stock_pct"), 0.20),
        )
    if sleeve == "speculative_ai":
        short_term_config = _as_dict(sleeves.get("short_term"))
        return _as_float(
            speculative_config.get("max_single_stock_pct"),
            _as_float(short_term_config.get("max_single_stock_pct"), 0.05),
        )
    return _as_float(sleeve_config.get("max_single_stock_pct"), 0.10)


def _speculative_cap_pct(targets: Mapping[str, object]) -> float:
    speculative_config = _as_dict(targets.get("speculative_ai"))
    sleeves = _as_dict(targets.get("sleeves"))
    short_term_config = _as_dict(sleeves.get("short_term"))
    return _as_float(
        speculative_config.get("max_position_pct"),
        _as_float(
            speculative_config.get("max_allocation_pct"),
            _as_float(
                speculative_config.get("max_single_stock_pct"),
                _as_float(short_term_config.get("max_single_stock_pct"), 0.05),
            ),
        ),
    )


def _sleeve_target_pct(sleeve: str, targets: Mapping[str, object]) -> Optional[float]:
    sleeve_config = _as_dict(_as_dict(targets.get("sleeves")).get(sleeve))
    if "target_pct" not in sleeve_config:
        return None
    return _as_float(sleeve_config.get("target_pct"))


def allocation_safety_for_candidate(
    row: Mapping[str, object],
    decision_gate: Mapping[str, object],
    *,
    positions: Mapping[str, Mapping[str, object]],
    targets: Mapping[str, object],
    account_value: float,
    buy_capacity: float,
    sleeve_market_values: Mapping[str, float] | None = None,
) -> AllocationSafetyResult:
    """Calculate the explainable suggested buy amount for one candidate."""

    item = row.get("input")
    symbol = str(getattr(item, "symbol", "") or "")
    sleeve = str(getattr(item, "sleeve", "") or "")
    account_value = max(0.0, _as_float(account_value))
    buy_capacity = max(0.0, _as_float(buy_capacity))
    current_value = position_market_value(positions.get(symbol))
    current_pct = (current_value / account_value) * 100 if account_value else 0.0

    speculative_config = _as_dict(targets.get("speculative_ai"))
    speculative_allows_buys = speculative_config.get("allow_buy_recommendations") is True
    watchlist_only_blocked = sleeve == "speculative_ai" and not speculative_allows_buys
    decision_safe = bool(decision_gate.get("safe_to_buy"))
    decision_status = str(decision_gate.get("status") or ("Ready" if decision_safe else "Blocked"))

    if not decision_safe:
        reasons = [str(reason) for reason in decision_gate.get("reasons", []) if str(reason)]
        if watchlist_only_blocked and "watchlist-only" not in " ".join(reasons).lower():
            reasons.append("Speculative AI watchlist-only block")
        reason = "Buy capacity held because decision safety blocks this candidate."
        if reasons:
            reason = f"{reason} {'; '.join(reasons)}."
        return AllocationSafetyResult(
            symbol=symbol,
            sleeve=sleeve,
            suggested_amount=0.0,
            buy_capacity=buy_capacity,
            account_value=account_value,
            current_position_market_value=current_value,
            current_position_pct=current_pct,
            position_after_buy_pct=current_pct,
            decision_safety_status=decision_status,
            watchlist_only_blocked=watchlist_only_blocked,
            applied_limit="decision_safety",
            reduction_reasons=reasons,
            reason=reason,
        )

    if watchlist_only_blocked:
        return AllocationSafetyResult(
            symbol=symbol,
            sleeve=sleeve,
            suggested_amount=0.0,
            buy_capacity=buy_capacity,
            account_value=account_value,
            current_position_market_value=current_value,
            current_position_pct=current_pct,
            position_after_buy_pct=current_pct,
            decision_safety_status=decision_status,
            watchlist_only_blocked=True,
            applied_limit="watchlist_only",
            reduction_reasons=["Speculative AI watchlist-only block"],
            reason="Buy capacity held because this speculative AI name is watchlist-only.",
        )

    limits: List[AllocationLimit] = []
    single_cap_pct = _single_stock_cap_pct(sleeve, targets)
    limits.append(
        AllocationLimit(
            name="single_stock_cap",
            label="single-stock cap",
            amount_available=account_value * single_cap_pct - current_value,
            cap_pct=single_cap_pct,
            current_value=current_value,
        )
    )

    sleeve_cap_pct = _sleeve_target_pct(sleeve, targets)
    if sleeve_cap_pct is not None:
        sleeve_values = dict(sleeve_market_values or {})
        sleeve_value = _as_float(sleeve_values.get(sleeve))
        limits.append(
            AllocationLimit(
                name="sleeve_cap",
                label="sleeve cap",
                amount_available=account_value * sleeve_cap_pct - sleeve_value,
                cap_pct=sleeve_cap_pct,
                current_value=sleeve_value,
            )
        )

    if sleeve == "speculative_ai":
        spec_cap_pct = _speculative_cap_pct(targets)
        limits.append(
            AllocationLimit(
                name="speculative_cap",
                label="speculative cap",
                amount_available=account_value * spec_cap_pct - current_value,
                cap_pct=spec_cap_pct,
                current_value=current_value,
            )
        )

    limiting_amounts = [buy_capacity, *(max(0.0, limit.amount_available) for limit in limits)]
    suggested_amount = max(0.0, min(limiting_amounts) if limiting_amounts else 0.0)
    applied_limit = "buy_capacity"
    reduction_reasons: List[str] = []
    for limit in limits:
        available = max(0.0, limit.amount_available)
        if available < buy_capacity:
            reduction_reasons.append(f"{limit.label} reduced capacity to ${available:,.2f}")
        if available <= suggested_amount + 0.005 and available < buy_capacity:
            applied_limit = limit.name

    position_after_pct = (
        ((current_value + suggested_amount) / account_value) * 100 if account_value else 0.0
    )
    if suggested_amount <= 0:
        if reduction_reasons:
            reason = f"Buy capacity held because {'; '.join(reduction_reasons)}."
        else:
            reason = "Buy capacity held because no safe allocation capacity is available."
    elif reduction_reasons:
        reason = f"Suggested amount reduced because {'; '.join(reduction_reasons)}."
    else:
        reason = "Full buy capacity is available under allocation rules."

    return AllocationSafetyResult(
        symbol=symbol,
        sleeve=sleeve,
        suggested_amount=round(suggested_amount, 2),
        buy_capacity=buy_capacity,
        account_value=account_value,
        current_position_market_value=current_value,
        current_position_pct=current_pct,
        position_after_buy_pct=position_after_pct,
        decision_safety_status=decision_status,
        watchlist_only_blocked=False,
        applied_limit=applied_limit,
        reduction_reasons=reduction_reasons,
        limits=limits,
        reason=reason,
    )


__all__ = [
    "AllocationSafetyResult",
    "allocation_safety_for_candidate",
    "sleeve_market_values_for_ranked",
]
