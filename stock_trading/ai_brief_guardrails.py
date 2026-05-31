"""Deterministic guardrails for AI-written research briefs.

The checks in this module are intentionally local and rule-based. They do not
call an LLM and they do not alter scores, actions, targets, confidence, gates,
allocation, or trading behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


PRICE_TARGET_RE = re.compile(
    r"(?i)\b(?:price target|target price|will (?:hit|reach|trade at)|go(?:es)? to|upside to)\s+\$?\d+(?:\.\d+)?"
    r"|\$\d+(?:\.\d+)?\s+(?:price target|target|upside)"
)
GUARANTEED_PERFORMANCE_RE = re.compile(
    r"(?i)\b(?:guaranteed|guarantees|risk[- ]?free|cannot lose|can't lose|certain profit|sure thing|will definitely|locked in)\b"
)
ORDER_OR_EXECUTION_RE = re.compile(
    r"(?i)\b(?:place (?:an )?order|submit (?:an )?order|execute (?:the )?trade|trade automatically|automatic(?:ally)? trade|"
    r"broker will|order (?:was|will be) placed|buy now|sell now)\b"
)
LOW_READINESS_VALUES = {
    "not_ready",
    "not ready",
    "not-enough-data",
    "not enough data",
    "needs_more_data",
    "needs more data",
    "insufficient_evidence",
    "insufficient evidence",
}


@dataclass
class GuardrailFinding:
    category: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"category": self.category, "message": self.message}


@dataclass
class GuardrailResult:
    passed: bool
    warnings: list[GuardrailFinding] = field(default_factory=list)
    failures: list[GuardrailFinding] = field(default_factory=list)
    recommended_action: str = "accept"

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "warnings": [finding.to_dict() for finding in self.warnings],
            "failures": [finding.to_dict() for finding in self.failures],
            "recommended_action": self.recommended_action,
        }


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _brief_text(brief: dict[str, object]) -> str:
    parts: list[str] = []
    for key in (
        "brief",
        "bull_case",
        "bear_case",
        "recent_changes",
        "risk_or_uncertainty",
        "data_gaps",
        "what_would_change_the_view",
        "recommendation_only_disclaimer",
    ):
        value = brief.get(key)
        if isinstance(value, list):
            parts.extend(_text(item) for item in value)
        else:
            parts.append(_text(value))
    supporting = brief.get("supporting_data")
    if isinstance(supporting, list):
        parts.extend(_text(item) for item in supporting)
    return "\n".join(part for part in parts if part)


def _has_source_refs(brief: dict[str, object]) -> bool:
    for key in ("audit_refs", "source_references", "evidence_ids", "citations"):
        refs = _as_list(brief.get(key))
        if any(_text(ref).strip() for ref in refs):
            return True
    return False


def _has_target_support(brief: dict[str, object]) -> bool:
    if any(_text(ref).lower().startswith(("target_", "target:", "target-drilldown")) for ref in _as_list(brief.get("audit_refs"))):
        return True
    for key in ("target_source_refs", "target_evidence_ids", "target_drilldown"):
        value = brief.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, list) and value:
            return True
    return False


def _readiness_value(brief: dict[str, object]) -> str:
    readiness = _as_dict(brief.get("synthesis_readiness"))
    value = (
        readiness.get("Readiness")
        or readiness.get("readiness_status")
        or brief.get("readiness")
        or brief.get("readiness_status")
        or ""
    )
    return _text(value).strip().lower().replace("_", " ")


def _mentions_low_readiness(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "not enough data",
            "insufficient evidence",
            "not ready",
            "needs review",
            "needs more data",
            "uncorroborated",
            "no synthesis-readiness packet",
        )
    )


def _mentions_data_gaps(text: str) -> bool:
    lowered = text.lower()
    return "data gap" in lowered or "provider gap" in lowered or "no major data gaps found" in lowered


def validate_ai_brief(brief: dict[str, object]) -> GuardrailResult:
    """Validate a single AI/research brief using deterministic checks."""

    failures: list[GuardrailFinding] = []
    warnings: list[GuardrailFinding] = []
    text = _brief_text(brief)
    lowered = text.lower()

    if not _has_source_refs(brief):
        failures.append(
            GuardrailFinding(
                "missing_source_references",
                "Brief must include source references, evidence IDs, or audit refs.",
            )
        )

    if not _text(brief.get("risk_or_uncertainty")).strip() and "risk" not in lowered and "uncertainty" not in lowered:
        failures.append(
            GuardrailFinding(
                "missing_risk_uncertainty",
                "Brief must include a risk or uncertainty section.",
            )
        )

    if not _mentions_data_gaps(text):
        failures.append(
            GuardrailFinding(
                "missing_data_gap_status",
                "Brief must mention data gaps or explicitly state that no major data gaps were found.",
            )
        )

    if "recommendation-only" not in lowered and "decision support" not in lowered:
        failures.append(
            GuardrailFinding(
                "missing_recommendation_only_disclaimer",
                "Brief must state that it is recommendation-only decision support.",
            )
        )

    if not _text(brief.get("what_would_change_the_view")).strip() and "what would change" not in lowered:
        failures.append(
            GuardrailFinding(
                "missing_view_change_trigger",
                "Brief must explain what would change the view.",
            )
        )

    if GUARANTEED_PERFORMANCE_RE.search(text):
        failures.append(
            GuardrailFinding(
                "guaranteed_performance_language",
                "Brief uses guaranteed-performance language.",
            )
        )

    if ORDER_OR_EXECUTION_RE.search(text):
        failures.append(
            GuardrailFinding(
                "order_or_execution_language",
                "Brief implies placing orders, automatic trading, or trade execution.",
            )
        )

    if PRICE_TARGET_RE.search(text) and not _has_target_support(brief):
        failures.append(
            GuardrailFinding(
                "unsupported_target_claim",
                "Brief includes a price or target claim without target-source support.",
            )
        )

    readiness = _readiness_value(brief)
    if readiness in LOW_READINESS_VALUES and not _mentions_low_readiness(text):
        failures.append(
            GuardrailFinding(
                "ignored_low_readiness",
                "Brief has low synthesis readiness but does not acknowledge weak or insufficient evidence.",
            )
        )

    if not _as_list(brief.get("audit_refs")) and _has_source_refs(brief):
        warnings.append(
            GuardrailFinding(
                "non_audit_source_references",
                "Brief has source references but no repo audit refs.",
            )
        )

    recommended_action = "accept"
    if failures:
        recommended_action = "reject"
    elif warnings:
        recommended_action = "needs_review"

    return GuardrailResult(
        passed=not failures,
        warnings=warnings,
        failures=failures,
        recommended_action=recommended_action,
    )


def validate_ai_briefs(briefs: list[dict[str, object]]) -> dict[str, object]:
    """Validate a collection of briefs and return JSON-native results."""

    results = [validate_ai_brief(brief).to_dict() for brief in briefs]
    failure_count = sum(len(_as_list(result.get("failures"))) for result in results)
    warning_count = sum(len(_as_list(result.get("warnings"))) for result in results)
    return {
        "passed": failure_count == 0,
        "brief_count": len(briefs),
        "warning_count": warning_count,
        "failure_count": failure_count,
        "recommended_action": "accept" if failure_count == 0 and warning_count == 0 else "needs_review" if failure_count == 0 else "reject",
        "results": results,
    }


__all__ = [
    "GuardrailFinding",
    "GuardrailResult",
    "validate_ai_brief",
    "validate_ai_briefs",
]
