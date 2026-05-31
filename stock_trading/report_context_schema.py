"""Schema and safety-contract validation for report-context dictionaries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


CORE_SECTIONS = ("metadata", "summary", "recommendations")

SECTION_TYPES = {
    "metadata": dict,
    "summary": dict,
    "recommendations": list,
    "reliability": dict,
    "source_health": dict,
    "provider_gap_review": dict,
    "target_drilldowns": dict,
    "score_movement": dict,
    "decision_safety": dict,
    "ai_analysis": dict,
    "ai_synthesis": dict,
    "ai_briefs": (dict, list),
    "synthesis_readiness": dict,
    "learning_review": dict,
    "manual_journal": (dict, list),
    "manual_trade_journal": (dict, list),
    "recommendation_outcomes": (dict, list),
    "catalyst_follow_through": (dict, list),
    "source_usefulness": (dict, list),
    "decision_safety_effectiveness": (dict, list),
    "feedback": dict,
}

SUMMARY_FIELDS = ("top_symbol", "top_action", "top_score")
RECOMMENDATION_FIELDS = ("symbol", "action", "score")
DECISION_GATE_FIELDS = ("status", "safe_to_buy")
PROVIDER_GAP_FIELDS = ("summary", "rows")
TARGET_DRILLDOWN_FIELDS = ("top_candidate", "by_symbol")
TABLE_FIELDS = ("headers", "rows")

REVIEW_ONLY_SECTIONS = {
    "ai_synthesis",
    "ai_briefs",
    "manual_journal",
    "manual_trade_journal",
    "recommendation_outcomes",
    "catalyst_follow_through",
    "source_usefulness",
    "decision_safety_effectiveness",
    "learning_review",
}

MODEL_IMPACT_PATTERNS = (
    re.compile(r"\b(?:automatically|directly|silently)\s+changes?\s+(?:the\s+)?(?:score|action|target)", re.I),
    re.compile(r"\b(?:changes?|updates?|sets?)\s+(?:official\s+)?recommendations?\b", re.I),
    re.compile(r"\b(?:changes?|updates?|sets?)\s+(?:the\s+)?(?:score|action|target price|target confidence)\b", re.I),
    re.compile(r"\b(?:feeds?|drives?)\s+(?:the\s+)?(?:score|action|target|recommendation)\b", re.I),
    re.compile(r"\bautomatic\s+(?:score\s+tuning|source-weight\s+changes?|recommendation\s+changes?)\b", re.I),
)

RECOMMENDATION_ONLY_PATTERNS = (
    re.compile(r"\bplace(?:s|d)?\s+trades?\b", re.I),
    re.compile(r"\border\s+preview\b", re.I),
    re.compile(r"\bpreview\s+(?:a\s+)?(?:trade|order)\b", re.I),
    re.compile(r"\bbroker\s+write\b", re.I),
    re.compile(r"\bautomatic\s+trading\b", re.I),
)

NEGATION_GUARDS = (
    "must not",
    "does not",
    "do not",
    "cannot",
    "can not",
    "no automatic",
    "not automatically",
    "never",
)


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "path": self.path, "message": self.message}


@dataclass
class ValidationResult:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, path: str, message: str) -> None:
        self.errors.append(ValidationIssue("error", path, message))

    def add_warning(self, path: str, message: str) -> None:
        self.warnings.append(ValidationIssue("warning", path, message))

    def extend(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }


def _type_name(expected: object) -> str:
    if isinstance(expected, tuple):
        return " or ".join(item.__name__ for item in expected)
    if isinstance(expected, type):
        return expected.__name__
    return str(expected)


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _missing(mapping: Mapping[str, Any], fields: Iterable[str]) -> list[str]:
    return [field for field in fields if field not in mapping]


def _guarded_language(value: str, start: int) -> bool:
    prefix = value[max(0, start - 80) : start].lower()
    return any(guard in prefix for guard in NEGATION_GUARDS)


def _claim_matches(value: object, patterns: Iterable[re.Pattern[str]]) -> list[str]:
    if not isinstance(value, str):
        return []
    matches: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(value):
            if not _guarded_language(value, match.start()):
                matches.append(match.group(0))
    return matches


def _walk_strings(value: object, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{path}[{index}]")


def _has_review_only_flag(value: object) -> bool:
    if isinstance(value, Mapping):
        if value.get("review_only") is True:
            return True
        metadata = value.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("review_only") is True:
            return True
    return False


def validate_report_context(context: object) -> ValidationResult:
    """Validate a report-context dictionary without assuming optional sections exist."""

    result = ValidationResult()
    if not isinstance(context, Mapping):
        result.add_error("$", "Report context must be a dictionary.")
        return result

    for section in CORE_SECTIONS:
        if section not in context:
            result.add_error(section, f"Missing required report-context section: {section}.")

    for section, expected_type in SECTION_TYPES.items():
        if section in context and not isinstance(context[section], expected_type):
            result.add_error(section, f"Section must be {_type_name(expected_type)}.")

    metadata = _as_mapping(context.get("metadata"))
    if metadata:
        for field_name in ("report_date",):
            if field_name not in metadata:
                result.add_error(f"metadata.{field_name}", "Metadata field is required.")
        if metadata.get("recommendation_only") is False:
            result.add_error("metadata.recommendation_only", "Report context must remain recommendation-only.")
        elif "recommendation_only" not in metadata:
            result.add_warning("metadata.recommendation_only", "Recommendation-only flag is missing.")

    summary = _as_mapping(context.get("summary"))
    if summary:
        for field_name in _missing(summary, SUMMARY_FIELDS):
            result.add_error(f"summary.{field_name}", "Summary field is required when summary is present.")
        decision_gate = summary.get("decision_gate")
        if decision_gate is not None:
            if not isinstance(decision_gate, Mapping):
                result.add_error("summary.decision_gate", "Decision gate must be a dictionary when present.")
            else:
                for field_name in _missing(decision_gate, DECISION_GATE_FIELDS):
                    result.add_warning(
                        f"summary.decision_gate.{field_name}",
                        "Decision-gate field is expected when decision gate is present.",
                    )

    decision_safety = context.get("decision_safety")
    if decision_safety is not None and isinstance(decision_safety, Mapping):
        for field_name in _missing(decision_safety, DECISION_GATE_FIELDS):
            result.add_warning(
                f"decision_safety.{field_name}",
                "Decision-safety field is expected when decision safety is present.",
            )

    recommendations = context.get("recommendations")
    if isinstance(recommendations, list):
        for index, recommendation in enumerate(recommendations):
            if not isinstance(recommendation, Mapping):
                result.add_error(f"recommendations[{index}]", "Recommendation must be a dictionary.")
                continue
            for field_name in _missing(recommendation, RECOMMENDATION_FIELDS):
                result.add_error(
                    f"recommendations[{index}].{field_name}",
                    "Recommendation field is required when recommendations are present.",
                )
            if "score_explanation" in recommendation and not isinstance(recommendation["score_explanation"], Mapping):
                result.add_error(
                    f"recommendations[{index}].score_explanation",
                    "Score explanation must be a dictionary when present.",
                )
            if "target_drilldown" in recommendation and not isinstance(recommendation["target_drilldown"], Mapping):
                result.add_error(
                    f"recommendations[{index}].target_drilldown",
                    "Target drilldown must be a dictionary when present.",
                )

    provider_gap_review = context.get("provider_gap_review")
    if isinstance(provider_gap_review, Mapping):
        for field_name in _missing(provider_gap_review, PROVIDER_GAP_FIELDS):
            result.add_warning(
                f"provider_gap_review.{field_name}",
                "Provider-gap review field is expected when provider-gap review is present.",
            )

    target_drilldowns = context.get("target_drilldowns")
    if isinstance(target_drilldowns, Mapping):
        for field_name in _missing(target_drilldowns, TARGET_DRILLDOWN_FIELDS):
            result.add_warning(
                f"target_drilldowns.{field_name}",
                "Target-drilldown field is expected when target drilldowns are present.",
            )

    for table_section in ("score_movement", "synthesis_readiness"):
        table = context.get(table_section)
        if isinstance(table, Mapping):
            for field_name in _missing(table, TABLE_FIELDS):
                result.add_warning(
                    f"{table_section}.{field_name}",
                    "Table-style section should include headers and rows.",
                )

    result.extend(validate_review_only_sections(context))
    result.extend(validate_recommendation_only_language(context))
    return result


def validate_review_only_sections(context: object) -> ValidationResult:
    """Validate that learning and AI sections are explicitly review-only."""

    result = ValidationResult()
    if not isinstance(context, Mapping):
        result.add_error("$", "Report context must be a dictionary.")
        return result

    for section in sorted(REVIEW_ONLY_SECTIONS):
        if section not in context:
            continue
        value = context[section]
        if not isinstance(value, (Mapping, list)):
            result.add_error(section, "Review-only section must be a dictionary or list.")
            continue
        if isinstance(value, Mapping):
            if not _has_review_only_flag(value):
                result.add_error(section, "Review-only section must include review_only: true.")
        else:
            for index, item in enumerate(value):
                if not _has_review_only_flag(item):
                    result.add_error(f"{section}[{index}]", "Review-only item must include review_only: true.")
        for path, text_value in _walk_strings(value, section):
            for match in _claim_matches(text_value, MODEL_IMPACT_PATTERNS):
                result.add_error(path, f"Review-only section claims model impact: {match}.")

    return result


def validate_recommendation_only_language(context: object) -> ValidationResult:
    """Detect language that conflicts with recommendation-only decision support."""

    result = ValidationResult()
    if not isinstance(context, Mapping):
        result.add_error("$", "Report context must be a dictionary.")
        return result

    for path, text_value in _walk_strings(context):
        for match in _claim_matches(text_value, RECOMMENDATION_ONLY_PATTERNS):
            result.add_error(path, f"Recommendation-only context contains execution language: {match}.")
    return result


__all__ = [
    "ValidationIssue",
    "ValidationResult",
    "validate_report_context",
    "validate_review_only_sections",
    "validate_recommendation_only_language",
]
