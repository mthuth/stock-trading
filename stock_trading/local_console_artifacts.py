"""Artifact indexing helpers for the local decision console."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Iterable


REPORT_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class ArtifactKind:
    key: str
    label: str
    prefix: str
    suffixes: tuple[str, ...]


ARTIFACT_KINDS: tuple[ArtifactKind, ...] = (
    ArtifactKind("dashboard", "Dashboard HTML", "dashboard-", (".html",)),
    ArtifactKind("daily_markdown", "Daily Markdown report", "daily-recommendation-", (".md",)),
    ArtifactKind("daily_csv", "Daily CSV export", "daily-recommendation-", (".csv",)),
    ArtifactKind("email_summary", "Email summary", "email-summary-", (".txt",)),
    ArtifactKind("end_of_day", "End-of-day review", "end-of-day-", (".md",)),
    ArtifactKind("next_day_watchlist", "Next-day watchlist", "next-day-watchlist-", (".md",)),
    ArtifactKind("report_context", "Report context JSON", "report-context-", (".json",)),
    ArtifactKind("ai_analysis_context", "AI analysis context", "ai-analysis-context-", (".json",)),
    ArtifactKind("ai_briefs_markdown", "AI insight briefs Markdown", "ai-insight-briefs-", (".md",)),
    ArtifactKind("ai_briefs_json", "AI insight briefs JSON", "ai-insight-briefs-", (".json",)),
    ArtifactKind("ai_briefs_html", "AI insight briefs HTML", "ai-insight-briefs-", (".html",)),
    ArtifactKind("synthesis_packets", "Synthesis packets", "synthesis-packets-", (".json",)),
    ArtifactKind("provider_gap_action_plan", "Provider gap action plan", "provider-gap-action-plan", (".md",)),
    ArtifactKind("provider_coverage_audit", "Provider coverage audit", "provider-coverage-audit", (".md", ".csv")),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def report_date_for(path: Path) -> str:
    match = REPORT_DATE_RE.search(path.name)
    return match.group(1) if match else ""


def artifact_kind_for(path: Path) -> ArtifactKind | None:
    for kind in ARTIFACT_KINDS:
        if path.name.startswith(kind.prefix) and path.suffix in kind.suffixes:
            return kind
    return None


def artifact_record(path: Path, root: Path) -> dict[str, object]:
    stat = path.stat()
    kind = artifact_kind_for(path)
    modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0)
    return {
        "kind": kind.key if kind else "other",
        "label": kind.label if kind else "Other report artifact",
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
        "file_name": path.name,
        "report_date": report_date_for(path),
        "extension": path.suffix,
        "size_bytes": stat.st_size,
        "modified_at": modified_at.isoformat().replace("+00:00", "Z"),
    }


def sort_artifacts(records: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        records,
        key=lambda item: (
            str(item.get("report_date") or ""),
            str(item.get("modified_at") or ""),
            str(item.get("file_name") or ""),
        ),
        reverse=True,
    )


def index_report_artifacts(reports_dir: str | Path = "reports", *, root: str | Path | None = None) -> dict[str, object]:
    base = Path(root).resolve() if root else Path.cwd().resolve()
    directory = Path(reports_dir)
    if not directory.is_absolute():
        directory = base / directory
    directory = directory.resolve()
    if not directory.exists():
        return {
            "reports_dir": str(directory),
            "items": [],
            "latest": {},
            "empty_state": "Reports directory is missing; run the daily report or render a fixture first.",
        }

    records = []
    for path in directory.iterdir():
        if path.is_file() and artifact_kind_for(path):
            records.append(artifact_record(path, base))

    items = sort_artifacts(records)
    latest: dict[str, dict[str, object]] = {}
    for item in items:
        key = str(item.get("kind") or "")
        if key and key not in latest:
            latest[key] = item

    return {
        "reports_dir": str(directory),
        "items": items,
        "latest": latest,
        "empty_state": "" if items else "No local report artifacts found yet.",
    }


__all__ = ["ARTIFACT_KINDS", "index_report_artifacts", "report_date_for", "utc_now"]
