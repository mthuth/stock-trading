"""Read-only local decision-console manifest builder.

The manifest is an artifact index and context summary. It must not recompute
recommendations, refresh providers, call AI models, or touch broker APIs.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from stock_trading.report_context_schema import validate_report_context


MANIFEST_VERSION = "local-console-manifest-v1"
RECOMMENDATION_ONLY_NOTE = (
    "Read-only local console manifest for recommendation-only decision support. "
    "It does not place trades, preview orders, write to broker accounts, or change "
    "scores, targets, actions, allocation, AI output, or decision-safety gates."
)

ARTIFACT_KEYS = {
    "latest_dashboard_path": ("dashboard", "dashboard-{report_date}.html"),
    "latest_markdown_report_path": ("markdown", "daily-recommendation-{report_date}.md"),
    "latest_csv_path": ("csv", "daily-recommendation-{report_date}.csv"),
    "latest_ai_context_path": ("ai_context", "ai-analysis-context-{report_date}.json"),
}

AI_BRIEF_KEYS = {
    "markdown": ("ai_briefs_markdown", "ai-insight-briefs-{report_date}.md"),
    "json": ("ai_briefs_json", "ai-insight-briefs-{report_date}.json"),
    "html": ("ai_briefs_html", "ai-insight-briefs-{report_date}.html"),
}

PROVIDER_GAP_ARTIFACTS = {
    "provider_gap_action_plan": "provider-gap-action-plan.md",
    "provider_coverage_audit_markdown": "provider-coverage-audit.md",
    "provider_coverage_audit_csv": "provider-coverage-audit.csv",
}


def as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def load_report_context(path: Path | str) -> dict[str, Any]:
    """Load a report-context JSON file without triggering any app behavior."""

    data = json.loads(Path(path).read_text())
    return data if isinstance(data, dict) else {}


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _latest_path(directory: Path, pattern: str) -> Path | None:
    matches = sorted(path for path in directory.glob(pattern) if path.is_file())
    return matches[-1] if matches else None


def find_latest_report_context(reports_dir: Path | str) -> Path | None:
    """Return the lexicographically latest report-context artifact, if present."""

    return _latest_path(Path(reports_dir), "report-context-*.json")


def _artifact_name(
    context: Mapping[str, Any],
    artifact_key: str,
    template: str,
    report_date: str,
) -> str:
    configured = as_dict(context.get("artifacts")).get(artifact_key)
    if configured:
        return text(configured)
    return template.format(report_date=report_date or "latest")


def _artifact_path(
    reports_dir: Path,
    context: Mapping[str, Any],
    artifact_key: str,
    template: str,
    report_date: str,
) -> Path:
    name = _artifact_name(context, artifact_key, template, report_date)
    path = Path(name)
    return path if path.is_absolute() else reports_dir / path


def _field_summary(source: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: copy.deepcopy(source[field]) for field in fields if field in source}


def _count_rows(value: object) -> int:
    if isinstance(value, Mapping):
        rows = value.get("rows")
        if isinstance(rows, list):
            return len(rows)
        table = value.get("table")
        if isinstance(table, Mapping) and isinstance(table.get("rows"), list):
            return len(table["rows"])
    if isinstance(value, list):
        return len(value)
    return 0


def _capital_deployment_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    section = as_dict(context.get("long_term_capital_deployment"))
    if not section:
        return {}
    primary = as_dict(section.get("primary_candidate"))
    fallback = as_dict(section.get("fallback_candidate"))
    capital = as_dict(section.get("capital_availability"))
    return {
        **_field_summary(
            section,
            (
                "review_only",
                "recommendation_only",
                "decision_mode",
                "status",
                "decision_safety_status",
                "target_confidence",
                "hold_capacity_message",
                "note",
            ),
        ),
        "primary_candidate": _field_summary(
            primary,
            (
                "symbol",
                "company",
                "action",
                "score",
                "decision_safe",
                "decision_gate_status",
                "target_confidence",
                "suggested_amount",
                "suggested_amount_text",
            ),
        ),
        "fallback_candidate": _field_summary(
            fallback,
            (
                "symbol",
                "company",
                "action",
                "score",
                "decision_safe",
                "decision_gate_status",
                "target_confidence",
                "suggested_amount",
                "suggested_amount_text",
            ),
        ),
        "capital_availability": _field_summary(
            capital,
            (
                "source",
                "status",
                "as_of_date",
                "freshness",
                "available_capital",
                "available_capital_text",
                "monthly_buy_capacity",
                "deployable_amount",
                "deployable_amount_text",
                "held_amount",
                "held_amount_text",
                "reason",
                "reduction_reasons",
            ),
        ),
    }


def _earnings_review_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    section = as_dict(context.get("earnings_review"))
    if not section:
        return {}
    signal_summary = as_dict(section.get("earnings_signal_summary"))
    return {
        **_field_summary(
            section,
            ("review_only", "recommendation_only", "decision_mode", "note"),
        ),
        "upcoming_count": _count_rows(section.get("upcoming_earnings_queue")),
        "recent_count": _count_rows(section.get("recent_earnings_queue")),
        "pre_earnings_setup_count": _count_rows(section.get("pre_earnings_setup_review")),
        "post_earnings_reaction_count": _count_rows(section.get("post_earnings_reaction_review")),
        "provider_gap_count": _count_rows(section.get("provider_data_gaps")),
        "signal_summary": _field_summary(
            signal_summary,
            (
                "overall_direction",
                "positive_count",
                "negative_count",
                "unknown_count",
                "signal_count",
                "review_only",
                "recommendation_impact",
            ),
        ),
    }


def _decision_safety_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    section = as_dict(context.get("decision_safety")) or as_dict(as_dict(context.get("summary")).get("decision_gate"))
    return _field_summary(section, ("safe_to_buy", "status", "candidate_action", "summary", "reasons"))


def _provider_gap_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    review = as_dict(context.get("provider_gap_review"))
    if review:
        return {
            **_field_summary(review, ("review_only", "top_symbol", "status", "summary")),
            "row_count": _count_rows(review),
        }

    source_health = as_dict(context.get("source_health"))
    provider_blockers = as_dict(source_health.get("provider_blockers"))
    summary = as_dict(source_health.get("summary"))
    if source_health or provider_blockers:
        return {
            "summary": copy.deepcopy(summary),
            "top_blocker": source_health.get("top_blocker", ""),
            "provider_blocker_count": _count_rows(provider_blockers),
        }
    return {}


def _learning_review_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    learning = as_dict(context.get("learning_review"))
    if not learning:
        return {}
    return {
        **_field_summary(learning, ("review_only", "recommendation_only", "note")),
        "manual_journal": _manual_journal_summary(context),
        "recommendation_outcomes": _recommendation_outcome_summary(context),
        "source_usefulness": _source_usefulness_summary(context),
        "catalyst_follow_through_count": _count_rows(learning.get("catalyst_follow_through")),
        "decision_safety_effectiveness_count": _count_rows(learning.get("decision_safety_effectiveness")),
    }


def _manual_journal_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    learning = as_dict(context.get("learning_review"))
    section = as_dict(context.get("manual_journal")) or as_dict(context.get("manual_trade_journal")) or as_dict(learning.get("manual_journal"))
    if not section:
        return {}
    return {
        **_field_summary(section, ("review_only", "entry_count", "latest_entry_date", "summary")),
        "row_count": _count_rows(section),
    }


def _recommendation_outcome_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    learning = as_dict(context.get("learning_review"))
    section = as_dict(context.get("recommendation_outcomes")) or as_dict(learning.get("recommendation_outcomes"))
    if not section:
        return {}
    return {
        **_field_summary(
            section,
            ("review_only", "outcome_count", "evaluated_count", "not_enough_history_count", "summary"),
        ),
        "row_count": _count_rows(section),
    }


def _source_usefulness_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    learning = as_dict(context.get("learning_review"))
    section = as_dict(context.get("source_usefulness")) or as_dict(learning.get("source_usefulness"))
    if section:
        return {
            **_field_summary(section, ("review_only", "source_count", "summary", "top_sources")),
            "row_count": _count_rows(section),
        }

    source_quality = as_dict(context.get("source_quality"))
    if source_quality:
        return {
            "summary": copy.deepcopy(as_dict(source_quality.get("summary"))),
            "row_count": _count_rows(source_quality.get("table")),
            "low_relevance_count": _count_rows(source_quality.get("low_relevance")),
        }
    return {}


def _ai_brief_metadata(context: Mapping[str, Any], ai_brief_paths: Mapping[str, str]) -> dict[str, Any]:
    ai_analysis = as_dict(context.get("ai_analysis"))
    ai_briefs = context.get("ai_briefs")
    return {
        "context_path": text(ai_analysis.get("context_path")),
        "guardrail_status": text(as_dict(ai_analysis.get("guardrails")).get("status")),
        "brief_count": len(ai_briefs) if isinstance(ai_briefs, list) else _count_rows(ai_briefs),
        "paths": dict(ai_brief_paths),
        "review_only": True,
        "recommendation_only": True,
    }


def _run_history_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    metadata = as_dict(context.get("metadata"))
    artifacts = as_dict(context.get("artifacts"))
    return {
        "analysis_run_id": metadata.get("analysis_run_id"),
        "recommendation_run_id": metadata.get("recommendation_run_id"),
        "workflow_run_id": metadata.get("workflow_run_id"),
        "generated_at": metadata.get("generated_at"),
        "artifact_count": len([value for value in artifacts.values() if value]),
        "artifact_names": copy.deepcopy(artifacts),
    }


def _validate_context(context: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    result = validate_report_context(context)
    validation = result.to_dict()
    warnings = [
        f"{issue.path}: {issue.message}"
        for issue in [*result.warnings, *result.errors]
    ]
    return validation, warnings


def build_local_console_manifest(
    reports_dir: Path | str = "reports",
    *,
    report_context_path: Path | str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a read-only local-console manifest from existing artifacts."""

    reports_path = Path(reports_dir)
    warnings: list[str] = []
    missing_artifacts: list[dict[str, str]] = []

    resolved_context_path = Path(report_context_path) if report_context_path else find_latest_report_context(reports_path)
    context: dict[str, Any] = {}
    if resolved_context_path and resolved_context_path.exists():
        context = load_report_context(resolved_context_path)
    else:
        warnings.append("No report-context artifact found; manifest contains artifact references only.")
        resolved_context_path = None

    metadata = as_dict(context.get("metadata"))
    report_date = text(metadata.get("report_date"))
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": generated_at or _utc_now(),
        "report_date": report_date,
        "read_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
        "latest_report_context_path": str(resolved_context_path) if resolved_context_path else "",
    }

    if context:
        schema_validation, schema_warnings = _validate_context(context)
        manifest["report_context_schema_validation"] = schema_validation
        warnings.extend(f"report_context_schema: {warning}" for warning in schema_warnings)

    for output_key, (artifact_key, template) in ARTIFACT_KEYS.items():
        path = _artifact_path(reports_path, context, artifact_key, template, report_date)
        manifest[output_key] = str(path) if path.exists() else ""
        if not path.exists():
            missing_artifacts.append({"artifact": artifact_key, "path": str(path)})

    ai_brief_paths: dict[str, str] = {}
    for label, (artifact_key, template) in AI_BRIEF_KEYS.items():
        path = _artifact_path(reports_path, context, artifact_key, template, report_date)
        ai_brief_paths[label] = str(path) if path.exists() else ""
        if not path.exists():
            missing_artifacts.append({"artifact": artifact_key, "path": str(path)})
    manifest["latest_ai_briefs_paths"] = ai_brief_paths

    provider_gap_paths: dict[str, str] = {}
    for label, filename in PROVIDER_GAP_ARTIFACTS.items():
        path = reports_path / filename
        if path.exists():
            provider_gap_paths[label] = str(path)
    manifest["latest_provider_gap_paths"] = provider_gap_paths

    manifest["capital_deployment_summary"] = _capital_deployment_summary(context)
    manifest["earnings_review_summary"] = _earnings_review_summary(context)
    manifest["decision_safety_summary"] = _decision_safety_summary(context)
    manifest["provider_gap_summary"] = _provider_gap_summary(context)
    manifest["learning_review_summary"] = _learning_review_summary(context)
    manifest["manual_journal_summary"] = _manual_journal_summary(context)
    manifest["recommendation_outcome_summary"] = _recommendation_outcome_summary(context)
    manifest["source_usefulness_summary"] = _source_usefulness_summary(context)
    manifest["ai_brief_metadata"] = _ai_brief_metadata(context, ai_brief_paths)
    manifest["run_history_summary"] = _run_history_summary(context)
    manifest["missing_artifacts"] = missing_artifacts
    if missing_artifacts:
        warnings.append(f"{len(missing_artifacts)} expected artifact(s) are missing.")
    manifest["warnings"] = warnings

    return manifest


def write_local_console_manifest(
    output_path: Path | str,
    *,
    reports_dir: Path | str = "reports",
    report_context_path: Path | str | None = None,
    generated_at: str | None = None,
) -> Path:
    """Write the manifest JSON to disk and return the output path."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_local_console_manifest(
        reports_dir,
        report_context_path=report_context_path,
        generated_at=generated_at,
    )
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return destination


__all__ = [
    "MANIFEST_VERSION",
    "RECOMMENDATION_ONLY_NOTE",
    "build_local_console_manifest",
    "find_latest_report_context",
    "load_report_context",
    "write_local_console_manifest",
]
