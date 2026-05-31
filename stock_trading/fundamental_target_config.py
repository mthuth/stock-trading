#!/usr/bin/env python3
"""Configuration loading for the fundamental target model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Mapping


DEFAULT_FUNDAMENTAL_TARGET_CONFIG: dict[str, Any] = {
    "version": "v1_straightforward_adjustable",
    "primary_valuation_method": "score_adjusted_peer_group_return",
    "source": {
        "source_name": "Internal fundamental model",
        "source_type": "model",
        "provider_endpoint": "SEC companyfacts + configured fundamental_target_model assumptions",
    },
    "fallback_behavior": {
        "default_peer_group": "unknown",
        "default_base_upside_pct": 12,
        "default_min_upside_pct": -15,
        "default_max_upside_pct": 30,
        "thin_revenue_penalty_pct": 4,
        "thin_profitability_penalty_pct": 3,
        "confidence_with_complete_inputs": "medium",
        "confidence_with_missing_inputs": "low",
        "missing_metric_note": "thin fundamentals; target relies on score-based proxy assumptions",
    },
    "growth_adjustment": {
        "pe_points_per_growth_point_above_peer_median": 0.5,
        "max_pe_adjustment": 8,
        "cyclical_margin_haircut": 0.15,
        "thin_coverage_confidence_haircut": 0.25,
    },
    "target_return_defaults": {},
    "quality_adjustment": {
        "basis_score": 80,
        "pct_per_score_point": 0.2,
        "max_adjustment_pct": 6,
    },
    "catalyst_adjustment": {
        "basis_score": 75,
        "pct_per_score_point": 0.15,
        "max_adjustment_pct": 6,
    },
    "risk_adjustment": {
        "basis_score": 75,
        "pct_per_score_point_below_basis": 0.2,
        "max_penalty_pct": 8,
    },
    "margin_adjustment": {
        "strong_operating_margin": 0.25,
        "strong_cash_flow_margin": 0.20,
        "strong_margin_bonus_pct": 4,
        "negative_margin_penalty_pct": 8,
    },
    "range_width_pct": {
        "high": 0.08,
        "medium": 0.12,
        "low": 0.18,
    },
    "peer_groups": {},
    "speculative_watchlist": {
        "confidence": "low",
        "confidence_haircut": 0.35,
    },
}


@dataclass(frozen=True)
class FundamentalTargetAssumptions:
    peer_group: str
    primary_valuation_method: str
    primary_multiple: str
    default_forward_pe: float | None
    default_ev_revenue: float | None
    base_upside_pct: float
    min_upside_pct: float
    max_upside_pct: float
    quality_basis_score: float
    quality_pct_per_score_point: float
    quality_max_adjustment_pct: float
    catalyst_basis_score: float
    catalyst_pct_per_score_point: float
    catalyst_max_adjustment_pct: float
    risk_basis_score: float
    risk_pct_per_score_point_below_basis: float
    risk_max_penalty_pct: float
    strong_operating_margin: float
    strong_cash_flow_margin: float
    strong_margin_bonus_pct: float
    negative_margin_penalty_pct: float
    thin_revenue_penalty_pct: float
    thin_profitability_penalty_pct: float
    complete_input_confidence: str
    missing_input_confidence: str
    speculative_confidence: str
    confidence_haircut: float
    speculative_watchlist_haircut: float
    range_width_pct: dict[str, float]
    valuation_cap: str
    fallback_note: str
    peer_notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def deep_merge(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(dict(defaults))
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def normalize_fundamental_target_config(raw_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a complete, safe fundamental target config."""
    overrides = raw_config if isinstance(raw_config, Mapping) else {}
    return deep_merge(DEFAULT_FUNDAMENTAL_TARGET_CONFIG, overrides)


def peer_group_for_symbol(symbol: str, raw_config: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    config = normalize_fundamental_target_config(raw_config)
    peer_groups = as_mapping(config.get("peer_groups"))
    for name, peer_config in peer_groups.items():
        peer_config = as_mapping(peer_config)
        symbols = [str(item).upper() for item in peer_config.get("symbols", [])]
        if symbol.upper() in symbols:
            return str(name), dict(peer_config)
    fallback = as_mapping(config.get("fallback_behavior"))
    return str(fallback.get("default_peer_group") or "unknown"), {}


def assumptions_for_symbol(
    symbol: str,
    sleeve: str,
    raw_config: Mapping[str, Any] | None,
) -> FundamentalTargetAssumptions:
    config = normalize_fundamental_target_config(raw_config)
    peer_group, peer_config = peer_group_for_symbol(symbol, config)
    if sleeve == "etf":
        peer_group = "etf_ballast"
        peer_groups = as_mapping(config.get("peer_groups"))
        peer_config = dict(as_mapping(peer_groups.get("etf_ballast")))

    fallback = as_mapping(config.get("fallback_behavior"))
    target_defaults = as_mapping(config.get("target_return_defaults"))
    group_defaults = as_mapping(target_defaults.get(peer_group))
    quality = as_mapping(config.get("quality_adjustment"))
    catalyst = as_mapping(config.get("catalyst_adjustment"))
    risk = as_mapping(config.get("risk_adjustment"))
    margin = as_mapping(config.get("margin_adjustment"))
    growth = as_mapping(config.get("growth_adjustment"))
    speculative = as_mapping(config.get("speculative_watchlist"))
    range_widths = as_mapping(config.get("range_width_pct"))

    base_upside = to_float(group_defaults.get("base_upside_pct"), to_float(fallback.get("default_base_upside_pct"), 12))
    min_upside = to_float(group_defaults.get("min_upside_pct"), to_float(fallback.get("default_min_upside_pct"), -15))
    max_upside = to_float(group_defaults.get("max_upside_pct"), to_float(fallback.get("default_max_upside_pct"), 30))
    confidence_haircut = to_float(peer_config.get("confidence_haircut"), to_float(growth.get("thin_coverage_confidence_haircut"), 0.25))
    speculative_haircut = to_float(
        peer_config.get("speculative_watchlist_haircut", peer_config.get("confidence_haircut")),
        to_float(speculative.get("confidence_haircut"), 0.35),
    )

    return FundamentalTargetAssumptions(
        peer_group=peer_group,
        primary_valuation_method=str(config.get("primary_valuation_method") or "score_adjusted_peer_group_return"),
        primary_multiple=str(peer_config.get("primary_multiple") or peer_config.get("default_target_method") or "score_adjusted_return"),
        default_forward_pe=(
            to_float(peer_config.get("default_forward_pe"))
            if peer_config.get("default_forward_pe") not in (None, "")
            else None
        ),
        default_ev_revenue=(
            to_float(peer_config.get("default_ev_revenue"))
            if peer_config.get("default_ev_revenue") not in (None, "")
            else None
        ),
        base_upside_pct=base_upside,
        min_upside_pct=min_upside,
        max_upside_pct=max_upside,
        quality_basis_score=to_float(quality.get("basis_score"), 80),
        quality_pct_per_score_point=to_float(quality.get("pct_per_score_point"), 0.2),
        quality_max_adjustment_pct=to_float(quality.get("max_adjustment_pct"), 6),
        catalyst_basis_score=to_float(catalyst.get("basis_score"), 75),
        catalyst_pct_per_score_point=to_float(catalyst.get("pct_per_score_point"), 0.15),
        catalyst_max_adjustment_pct=to_float(catalyst.get("max_adjustment_pct"), 6),
        risk_basis_score=to_float(risk.get("basis_score"), 75),
        risk_pct_per_score_point_below_basis=to_float(risk.get("pct_per_score_point_below_basis"), 0.2),
        risk_max_penalty_pct=to_float(risk.get("max_penalty_pct"), 8),
        strong_operating_margin=to_float(margin.get("strong_operating_margin"), 0.25),
        strong_cash_flow_margin=to_float(margin.get("strong_cash_flow_margin"), 0.20),
        strong_margin_bonus_pct=to_float(margin.get("strong_margin_bonus_pct"), 4),
        negative_margin_penalty_pct=to_float(margin.get("negative_margin_penalty_pct"), 8),
        thin_revenue_penalty_pct=to_float(fallback.get("thin_revenue_penalty_pct"), 4),
        thin_profitability_penalty_pct=to_float(fallback.get("thin_profitability_penalty_pct"), 3),
        complete_input_confidence=str(fallback.get("confidence_with_complete_inputs") or "medium"),
        missing_input_confidence=str(fallback.get("confidence_with_missing_inputs") or "low"),
        speculative_confidence=str(speculative.get("confidence") or "low"),
        confidence_haircut=confidence_haircut,
        speculative_watchlist_haircut=speculative_haircut,
        range_width_pct={
            "high": to_float(range_widths.get("high"), 0.08),
            "medium": to_float(range_widths.get("medium"), 0.12),
            "low": to_float(range_widths.get("low"), 0.18),
        },
        valuation_cap=f"{min_upside:.1f}% to {max_upside:.1f}% modeled upside",
        fallback_note=str(fallback.get("missing_metric_note") or "thin fundamentals; target relies on score-based proxy assumptions"),
        peer_notes=str(peer_config.get("notes") or ""),
    )


def source_config(raw_config: Mapping[str, Any] | None) -> dict[str, str]:
    config = normalize_fundamental_target_config(raw_config)
    source = as_mapping(config.get("source"))
    return {
        "source_name": str(source.get("source_name") or "Internal fundamental model"),
        "source_type": str(source.get("source_type") or "model"),
        "provider_endpoint": str(source.get("provider_endpoint") or "SEC companyfacts + configured fundamental_target_model assumptions"),
    }
