#!/usr/bin/env python3
"""Watchlist-only policy evaluation for recommendation safety."""

from __future__ import annotations

from typing import Mapping


DEFAULT_REASON = (
    "Speculative/watchlist-only policy blocks buy-readiness until observation, "
    "evidence quality, and confidence requirements are met."
)


def _as_symbol_set(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value).strip().upper() for value in values if str(value).strip()}


def _as_requirement_list(values: object) -> list[str]:
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, dict):
        return [f"{key}: {value}" for key, value in values.items()]
    return []


def watchlist_policy_from_targets(targets: Mapping[str, object] | None) -> dict[str, object]:
    targets = targets or {}
    policy = targets.get("watchlist_only_policy")
    speculative = targets.get("speculative_ai")
    policy_config = policy if isinstance(policy, dict) else {}
    speculative_config = speculative if isinstance(speculative, dict) else {}

    symbols = _as_symbol_set(policy_config.get("symbols")) or _as_symbol_set(speculative_config.get("symbols"))
    allow_buy_recommendations = (
        policy_config.get("allow_buy_recommendations")
        if "allow_buy_recommendations" in policy_config
        else speculative_config.get("allow_buy_recommendations")
    )
    observation_days = (
        policy_config.get("observation_days")
        if "observation_days" in policy_config
        else speculative_config.get("watchlist_only_days", 0)
    )
    try:
        observation_days_int = int(observation_days or 0)
    except (TypeError, ValueError):
        observation_days_int = 0

    reason = str(
        policy_config.get("reason")
        or speculative_config.get("eligibility_reason")
        or DEFAULT_REASON
    )
    requirements = _as_requirement_list(
        policy_config.get("eligibility_requirements")
        or speculative_config.get("eligibility_requirements")
    )
    confidence_requirements = _as_requirement_list(
        policy_config.get("confidence_requirements")
        or speculative_config.get("confidence_requirements")
    )

    return {
        "configured": bool(policy_config or speculative_config),
        "allow_buy_recommendations": allow_buy_recommendations is True,
        "symbols": sorted(symbols),
        "observation_days": observation_days_int,
        "reason": reason,
        "eligibility_requirements": requirements,
        "confidence_requirements": confidence_requirements,
    }


def evaluate_watchlist_policy(
    symbol: str,
    sleeve: str,
    targets: Mapping[str, object] | None,
) -> dict[str, object]:
    policy = watchlist_policy_from_targets(targets)
    configured_symbols = set(policy["symbols"])
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_sleeve = str(sleeve or "").strip().lower()
    matches_policy = normalized_symbol in configured_symbols or (
        not configured_symbols
        and bool(policy.get("configured"))
        and normalized_sleeve == "speculative_ai"
    )
    blocked = bool(matches_policy and not policy["allow_buy_recommendations"])
    return {
        **policy,
        "symbol": normalized_symbol,
        "matches_policy": matches_policy,
        "blocked": blocked,
        "status": "Blocked" if blocked else "Eligible",
    }


def watchlist_reason(symbol: str, sleeve: str, targets: Mapping[str, object] | None) -> str:
    decision = evaluate_watchlist_policy(symbol, sleeve, targets)
    return str(decision.get("reason") or DEFAULT_REASON) if decision.get("blocked") else ""


__all__ = [
    "DEFAULT_REASON",
    "evaluate_watchlist_policy",
    "watchlist_policy_from_targets",
    "watchlist_reason",
]
