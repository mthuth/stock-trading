"""Read-only artifact index helpers for the local decision console."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from stock_trading.storage.connection import REPORTS_DIR, ROOT


REVIEW_ONLY_NOTE = (
    "Read-only local console artifact index. This view lists existing files and "
    "must not execute workflows, refresh providers, alter recommendations, or trade."
)
DATE_PATTERN = re.compile(r"(20\d{2}-\d{2}-\d{2})")


@dataclass(frozen=True)
class ArtifactDefinition:
    artifact_type: str
    pattern: str
    notes: str
    dated: bool = True


ARTIFACT_DEFINITIONS = (
    ArtifactDefinition("daily_markdown_report", "daily-recommendation-*.md", "Daily Markdown recommendation report."),
    ArtifactDefinition("csv_recommendation_export", "daily-recommendation-*.csv", "CSV recommendation export."),
    ArtifactDefinition("dashboard_html", "dashboard-*.html", "Static local dashboard HTML."),
    ArtifactDefinition("report_context_json", "report-context-*.json", "Report rendering context JSON."),
    ArtifactDefinition("ai_analysis_context", "ai-analysis-context-*.json", "Deterministic AI analysis context."),
    ArtifactDefinition("ai_brief", "ai-insight-briefs-*.*", "AI insight brief artifact."),
    ArtifactDefinition("synthesis_packets", "synthesis-packets-*.json", "AI synthesis readiness packets."),
    ArtifactDefinition("provider_coverage_audit", "provider-coverage-audit.*", "Provider coverage audit artifact.", False),
    ArtifactDefinition("provider_gap_action_plan", "provider-gap-action-plan.md", "Provider gap action plan.", False),
    ArtifactDefinition("local_console_manifest", "local-console-manifest.json", "Optional local console manifest.", False),
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def parse_date(value: object) -> date | None:
    raw = text(value)
    if not raw:
        return None
    match = DATE_PATTERN.search(raw)
    candidate = match.group(1) if match else raw[:10]
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def utc_timestamp(seconds: float) -> str:
    return datetime.utcfromtimestamp(seconds).isoformat(timespec="seconds")


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def artifact_status(
    *,
    exists: bool,
    report_date: date | None,
    modified_at: str,
    as_of: date,
    stale_after_days: int,
    dated: bool,
) -> tuple[str, str]:
    if not exists:
        return "missing", "Expected artifact not found."
    if report_date:
        age_days = (as_of - report_date).days
        if age_days < 0:
            return "future_dated", "Artifact date is after the review date."
        if age_days > stale_after_days:
            return "stale", f"Artifact report date is {age_days} day(s) old."
        return "current", f"Artifact report date is {age_days} day(s) old."
    if dated:
        return "unknown_date", "Could not parse report date from artifact name."
    if modified_at:
        return "available", "Undated reference artifact is available."
    return "available", "Artifact is available."


def artifact_row(
    artifact_type: str,
    path: Path,
    *,
    reports_dir: Path,
    root: Path,
    exists: bool,
    as_of: date,
    stale_after_days: int,
    definition_notes: str,
    dated: bool,
) -> dict[str, object]:
    stat = path.stat() if exists else None
    parsed_date = parse_date(path.name)
    modified_at = utc_timestamp(stat.st_mtime) if stat else ""
    freshness, freshness_note = artifact_status(
        exists=exists,
        report_date=parsed_date,
        modified_at=modified_at,
        as_of=as_of,
        stale_after_days=stale_after_days,
        dated=dated,
    )
    notes = definition_notes if freshness == "current" or freshness == "available" else f"{definition_notes} {freshness_note}"
    return {
        "artifact_type": artifact_type,
        "path": display_path(path, root),
        "report_date": parsed_date.isoformat() if parsed_date else "",
        "exists": exists,
        "size_bytes": int(stat.st_size) if stat else 0,
        "modified_at": modified_at,
        "freshness": freshness,
        "status": freshness,
        "notes": notes,
    }


def artifact_index(
    reports_dir: Path | str = REPORTS_DIR,
    *,
    root: Path | str = ROOT,
    as_of: object | None = None,
    stale_after_days: int = 2,
    definitions: Iterable[ArtifactDefinition] = ARTIFACT_DEFINITIONS,
) -> list[dict[str, object]]:
    """Return a read-only index of known local report artifacts."""

    reports_path = Path(reports_dir)
    root_path = Path(root)
    as_of_date = parse_date(as_of) or date.today()
    rows: list[dict[str, object]] = []
    for definition in definitions:
        matches = sorted(reports_path.glob(definition.pattern)) if reports_path.exists() else []
        if not matches:
            rows.append(
                artifact_row(
                    definition.artifact_type,
                    reports_path / definition.pattern,
                    reports_dir=reports_path,
                    root=root_path,
                    exists=False,
                    as_of=as_of_date,
                    stale_after_days=stale_after_days,
                    definition_notes=definition.notes,
                    dated=definition.dated,
                )
            )
            continue
        for path in matches:
            if not path.is_file():
                continue
            rows.append(
                artifact_row(
                    definition.artifact_type,
                    path,
                    reports_dir=reports_path,
                    root=root_path,
                    exists=True,
                    as_of=as_of_date,
                    stale_after_days=stale_after_days,
                    definition_notes=definition.notes,
                    dated=definition.dated,
                )
            )
    rows.sort(key=lambda row: (text(row["artifact_type"]), text(row["report_date"]), text(row["path"])))
    return rows


def latest_artifacts(rows: Iterable[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Return the latest existing artifact row by artifact type."""

    latest: dict[str, dict[str, object]] = {}
    for row in rows:
        if not row.get("exists"):
            continue
        artifact_type = text(row.get("artifact_type"))
        current = latest.get(artifact_type)
        if current is None:
            latest[artifact_type] = dict(row)
            continue
        current_key = (text(current.get("report_date")), text(current.get("modified_at")), text(current.get("path")))
        row_key = (text(row.get("report_date")), text(row.get("modified_at")), text(row.get("path")))
        if row_key > current_key:
            latest[artifact_type] = dict(row)
    return latest


def artifact_index_view_model(
    reports_dir: Path | str = REPORTS_DIR,
    *,
    root: Path | str = ROOT,
    as_of: object | None = None,
    stale_after_days: int = 2,
) -> dict[str, object]:
    rows = artifact_index(
        reports_dir,
        root=root,
        as_of=as_of,
        stale_after_days=stale_after_days,
    )
    latest = latest_artifacts(rows)
    missing = [row for row in rows if not row.get("exists")]
    stale = [row for row in rows if row.get("freshness") == "stale"]
    return {
        "metadata": {
            "review_only": True,
            "reports_dir": display_path(Path(reports_dir), Path(root)),
            "artifact_count": len(rows),
            "existing_count": len([row for row in rows if row.get("exists")]),
            "missing_count": len(missing),
            "stale_count": len(stale),
            "notes": REVIEW_ONLY_NOTE,
        },
        "artifacts": rows,
        "latest_by_type": latest,
        "missing": missing,
        "stale": stale,
        "review_only": True,
    }
