#!/usr/bin/env python3
"""Plain-English glossary for score driver and decision-review language."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


REVIEW_ONLY_GUARDRAIL = (
    "This glossary is explanatory and review-only. It does not change scoring "
    "formulas, weights, thresholds, targets, decision gates, allocation, broker "
    "behavior, or recommendations."
)


_GLOSSARY_ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "term": "base evidence",
        "aliases": ("base", "evidence", "base_score", "base score"),
        "definition": (
            "The starting evidence score before the daily review layers explain "
            "trend movement, target confidence, data gaps, or final action."
        ),
        "plain_language": "What the core facts say before the extra review checks are layered on.",
    },
    {
        "term": "trend",
        "aliases": ("trends", "trend_delta", "trend delta", "momentum"),
        "definition": (
            "The recent direction and strength of price, momentum, score movement, "
            "or related market confirmation signals."
        ),
        "plain_language": "Whether the market is confirming or fighting the thesis right now.",
    },
    {
        "term": "target",
        "aliases": ("targets", "target_delta", "target delta", "blended target"),
        "definition": (
            "The analyst, fundamental, technical, manual, or blended price context "
            "used to explain upside and target confidence."
        ),
        "plain_language": "The upside estimate and how broad or thin the target evidence is.",
    },
    {
        "term": "gap",
        "aliases": ("gaps", "data_gap", "data gaps", "data_gap_delta", "data gap delta"),
        "definition": (
            "Missing, stale, blocked, or low-quality input data that can reduce "
            "confidence or require manual verification."
        ),
        "plain_language": "What the app does not know well enough yet.",
    },
    {
        "term": "final action",
        "aliases": ("action", "recommendation", "final_action", "final recommendation"),
        "definition": (
            "The controlled recommendation label shown after score, target, "
            "decision-safety, watchlist, allocation, and data-readiness checks."
        ),
        "plain_language": "The final review label, such as Add, Hold, Watch, Trim, or Avoid.",
    },
    {
        "term": "score driver",
        "aliases": ("driver", "drivers", "top driver", "score drivers"),
        "definition": (
            "A factor that helps explain why the score or review posture is higher, "
            "lower, or unchanged."
        ),
        "plain_language": "The main reasons the model likes, dislikes, or is cautious about an idea.",
    },
    {
        "term": "score risk",
        "aliases": ("risk", "risks", "top risk", "score risks"),
        "definition": (
            "A factor that could weaken the score, thesis, target confidence, or "
            "decision readiness."
        ),
        "plain_language": "What could make the score less trustworthy or the setup less attractive.",
    },
    {
        "term": "target confidence",
        "aliases": ("confidence", "target_confidence", "target quality"),
        "definition": (
            "A label that reflects target-source breadth, freshness, corroboration, "
            "current price availability, and unresolved provider gaps."
        ),
        "plain_language": "How much trust to put in the displayed upside estimate.",
    },
    {
        "term": "data status",
        "aliases": ("status", "data_status", "target status"),
        "definition": (
            "A short reliability label for whether the data behind the displayed "
            "target or recommendation context is current, partial, stale, or missing."
        ),
        "plain_language": "Whether the inputs are fresh enough for the review question.",
    },
    {
        "term": "decision gate",
        "aliases": ("gate", "decision_gate", "safety gate", "decision safety"),
        "definition": (
            "The manual-review checkpoint that explains whether an idea appears "
            "buy-ready, blocked, watchlist-only, or needs verification."
        ),
        "plain_language": "The safety check before treating an idea as ready for manual action.",
    },
    {
        "term": "source health",
        "aliases": ("source_health", "source status", "source reliability"),
        "definition": (
            "The freshness, availability, reliability, and issue status of research "
            "or data sources used by the app."
        ),
        "plain_language": "Whether the sources feeding the view are working and current.",
    },
    {
        "term": "provider gap",
        "aliases": ("provider_gap", "provider gaps", "provider issue", "provider blocker"),
        "definition": (
            "A provider-specific missing, blocked, stale, rate-limited, or expected "
            "data issue that should be visible instead of silently ignored."
        ),
        "plain_language": "A data-provider problem or expected limitation that may need cleanup.",
    },
    {
        "term": "allocation cap",
        "aliases": ("cap", "caps", "allocation_cap", "position cap", "single-stock cap"),
        "definition": (
            "A portfolio exposure limit used to frame whether a suggested add would "
            "fit current holdings and sleeve rules."
        ),
        "plain_language": "How much room the portfolio has before a position or sleeve gets too large.",
    },
    {
        "term": "watchlist-only",
        "aliases": ("watchlist", "watchlist_only", "speculative watchlist"),
        "definition": (
            "A review state for ideas that can be monitored but should not receive "
            "buy-ready treatment until their evidence, confidence, and guardrails improve."
        ),
        "plain_language": "Interesting enough to track, not ready enough to buy/add.",
    },
    {
        "term": "model/user disagreement",
        "aliases": ("model user disagreement", "disagreement", "user disagreement"),
        "definition": (
            "A review-only record that the model and user did not agree, such as "
            "when the model says Watch but the user manually buys."
        ),
        "plain_language": "A learning signal to review later, not permission to change the model automatically.",
    },
    {
        "term": "review-only output",
        "aliases": ("review only", "recommendation-only", "recommendation only", "guardrail"),
        "definition": (
            "An explanatory artifact for human review that must not place trades, "
            "preview orders, write to broker accounts, or imply guaranteed performance."
        ),
        "plain_language": "Decision support for Matt, not execution or automatic model tuning.",
        "guardrail": REVIEW_ONLY_GUARDRAIL,
    },
)


_COMPONENT_TO_TERM = {
    "base": "base evidence",
    "base_evidence": "base evidence",
    "base_score": "base evidence",
    "evidence": "base evidence",
    "trend": "trend",
    "trends": "trend",
    "trend_delta": "trend",
    "momentum": "trend",
    "target": "target",
    "targets": "target",
    "target_delta": "target",
    "blended_target": "target",
    "gap": "gap",
    "gaps": "gap",
    "data_gap": "gap",
    "data_gaps": "gap",
    "data_gap_delta": "gap",
    "final": "final action",
    "final_action": "final action",
    "action": "final action",
    "score_driver": "score driver",
    "driver": "score driver",
    "drivers": "score driver",
    "score_risk": "score risk",
    "risk": "score risk",
    "risks": "score risk",
    "target_confidence": "target confidence",
    "confidence": "target confidence",
    "data_status": "data status",
    "decision_gate": "decision gate",
    "gate": "decision gate",
    "source_health": "source health",
    "provider_gap": "provider gap",
    "allocation_cap": "allocation cap",
    "watchlist_only": "watchlist-only",
    "watchlist": "watchlist-only",
    "model_user_disagreement": "model/user disagreement",
    "review_only": "review-only output",
}


def _normalize(value: object) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _key(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _entry_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in _GLOSSARY_ENTRIES:
        terms = (entry["term"], *entry.get("aliases", ()))
        for term in terms:
            index[_normalize(term)] = entry
    return index


def _public_entry(entry: dict[str, Any], *, known: bool = True) -> dict[str, Any]:
    public = deepcopy(entry)
    public.pop("aliases", None)
    public["known"] = known
    public["review_only"] = True
    public["no_scoring_change"] = True
    public.setdefault("guardrail", REVIEW_ONLY_GUARDRAIL)
    return public


def glossary_entries() -> list[dict[str, Any]]:
    """Return all glossary entries as caller-safe dictionaries."""
    return [_public_entry(entry) for entry in _GLOSSARY_ENTRIES]


def glossary_entry(term: object) -> dict[str, Any]:
    """Return a glossary entry for a term, or a review-only unknown-term record."""
    normalized = _normalize(term)
    entry = _entry_index().get(normalized)
    if entry:
        return _public_entry(entry)
    display_term = str(term or "").strip() or "unknown"
    return {
        "term": display_term,
        "definition": "No glossary entry is available for this term yet.",
        "plain_language": "Treat this as unresolved help text and review the source context directly.",
        "known": False,
        "review_only": True,
        "no_scoring_change": True,
        "guardrail": REVIEW_ONLY_GUARDRAIL,
    }


def glossary_for_score_component(component: object) -> dict[str, Any]:
    """Map a score component or display key to its glossary entry."""
    mapped_term = _COMPONENT_TO_TERM.get(_key(component))
    if mapped_term:
        return glossary_entry(mapped_term)
    return glossary_entry(component)


__all__ = [
    "REVIEW_ONLY_GUARDRAIL",
    "glossary_entries",
    "glossary_entry",
    "glossary_for_score_component",
]
