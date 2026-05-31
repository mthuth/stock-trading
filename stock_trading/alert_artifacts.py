"""Review-only alert artifact export helpers."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


GUARDRAIL_TEXT = (
    "Review-only and recommendation-only. Alerts are local review prompts only; "
    "they do not execute actions, write accounts, send live notifications, or "
    "change recommendations."
)
ACTIVE_STATUSES = {"active", "new", "open", "needs_review", "review"}
RESOLVED_STATUSES = {"resolved", "dismissed", "closed", "ignored"}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
DEFAULT_TOP_LIMIT = 5


def as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return copy.deepcopy(list(value))
    return []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def token(value: object, default: str = "") -> str:
    raw = text(value, default)
    return raw.lower().replace("-", "_").replace(" ", "_")


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def alert_id(row: Mapping[str, object], fallback_index: int) -> str:
    explicit = text(row.get("alert_id") or row.get("id"))
    if explicit:
        return explicit
    symbol = text(row.get("symbol")).upper() or "GENERAL"
    area = token(row.get("review_area") or row.get("area") or "review")
    title = token(row.get("title") or row.get("summary") or row.get("trigger") or f"alert_{fallback_index}")
    return f"{symbol}:{area}:{title}"


def normalize_severity(value: object) -> str:
    severity = token(value, "info")
    if severity in SEVERITY_RANK:
        return severity
    if severity in {"blocker", "urgent"}:
        return "critical"
    if severity in {"warning", "warn", "needs_attention"}:
        return "high"
    if severity in {"review", "moderate"}:
        return "medium"
    return "info"


def normalize_status(value: object) -> str:
    status = token(value, "active")
    if status in ACTIVE_STATUSES:
        return "active" if status in {"new", "open", "needs_review", "review"} else status
    if status in RESOLVED_STATUSES:
        return status
    return "active"


def normalize_alert(row: Mapping[str, object], fallback_index: int) -> dict[str, object]:
    severity = normalize_severity(row.get("severity"))
    status = normalize_status(row.get("status"))
    return {
        "alert_id": alert_id(row, fallback_index),
        "symbol": text(row.get("symbol")).upper(),
        "title": text(row.get("title") or row.get("summary") or row.get("trigger"), "Review alert"),
        "summary": text(row.get("summary") or row.get("detail") or row.get("message") or row.get("title")),
        "severity": severity,
        "status": status,
        "review_area": token(row.get("review_area") or row.get("area"), "general_review"),
        "trigger_type": token(row.get("trigger_type") or row.get("trigger"), "review_trigger"),
        "priority_score": number(row.get("priority_score") or row.get("priority"), 0.0),
        "created_at": text(row.get("created_at") or row.get("detected_at")),
        "updated_at": text(row.get("updated_at") or row.get("resolved_at")),
        "recommended_review_action": text(row.get("recommended_review_action"), "review_manually"),
        "source": text(row.get("source") or row.get("provider")),
        "reasons": [text(reason) for reason in as_list(row.get("reasons")) if text(reason)],
        "review_only": True,
        "recommendation_only": True,
        "guardrail": GUARDRAIL_TEXT,
    }


def normalize_alerts(alerts: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    rows = [normalize_alert(row, index) for index, row in enumerate(alerts, start=1)]
    rows.sort(
        key=lambda row: (
            row["status"] != "active",
            SEVERITY_RANK.get(str(row["severity"]), 9),
            -number(row["priority_score"]),
            str(row["alert_id"]),
        )
    )
    return rows


def source_alert_rows(value: Mapping[str, object] | Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    if isinstance(value, Mapping):
        if isinstance(value.get("alerts"), list):
            return [row for row in value["alerts"] if isinstance(row, Mapping)]
        inbox = as_dict(value.get("inbox"))
        if isinstance(inbox.get("alerts"), list):
            return [row for row in inbox["alerts"] if isinstance(row, Mapping)]
        rows = as_list(value.get("rows"))
        return [row for row in rows if isinstance(row, Mapping)]
    return [row for row in value if isinstance(row, Mapping)]


def count_by(rows: Iterable[Mapping[str, object]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = text(row.get(field), "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_alert_artifact(
    source: Mapping[str, object] | Iterable[Mapping[str, object]],
    *,
    generated_at: str | None = None,
    report_date: str | None = None,
    top_limit: int = DEFAULT_TOP_LIMIT,
) -> dict[str, object]:
    """Build a deterministic JSON-serializable alert artifact from supplied rows."""

    metadata_source = as_dict(source) if isinstance(source, Mapping) else {}
    metadata = as_dict(metadata_source.get("metadata"))
    rows = normalize_alerts(source_alert_rows(source))
    active = [row for row in rows if row["status"] == "active"]
    dismissed = [row for row in rows if row["status"] == "dismissed"]
    resolved = [row for row in rows if row["status"] == "resolved"]
    metadata.update(
        {
            "generated_at": generated_at or metadata.get("generated_at") or iso_now(),
            "report_date": report_date or metadata.get("report_date") or date.today().isoformat(),
            "alert_count": len(rows),
            "active_alert_count": len(active),
            "review_only": True,
            "recommendation_only": True,
            "guardrail": GUARDRAIL_TEXT,
        }
    )
    return {
        "metadata": metadata,
        "active_alert_summary": {
            "active_count": len(active),
            "critical_count": sum(1 for row in active if row["severity"] == "critical"),
            "high_count": sum(1 for row in active if row["severity"] == "high"),
            "medium_count": sum(1 for row in active if row["severity"] == "medium"),
            "low_count": sum(1 for row in active if row["severity"] == "low"),
            "info_count": sum(1 for row in active if row["severity"] == "info"),
        },
        "alerts_by_severity": count_by(active, "severity"),
        "alerts_by_review_area": count_by(active, "review_area"),
        "top_priority_alerts": active[:top_limit],
        "dismissed_resolved_counts": {
            "dismissed": len(dismissed),
            "resolved": len(resolved),
            "inactive_total": len(rows) - len(active),
        },
        "alerts": rows,
        "guardrails": {
            "review_only": True,
            "recommendation_only": True,
            "no_live_notifications": True,
            "no_account_writes": True,
            "no_recommendation_changes": True,
            "text": GUARDRAIL_TEXT,
        },
    }


def markdown_escape(value: object) -> str:
    return text(value).replace("|", "\\|")


def render_alert_markdown(artifact: Mapping[str, object]) -> str:
    metadata = as_dict(artifact.get("metadata"))
    summary = as_dict(artifact.get("active_alert_summary"))
    top_alerts = [row for row in as_list(artifact.get("top_priority_alerts")) if isinstance(row, Mapping)]
    severity_counts = as_dict(artifact.get("alerts_by_severity"))
    area_counts = as_dict(artifact.get("alerts_by_review_area"))
    inactive = as_dict(artifact.get("dismissed_resolved_counts"))
    lines = [
        "# Alert Review Summary",
        "",
        GUARDRAIL_TEXT,
        "",
        "## Metadata",
        "",
        f"- Report date: {text(metadata.get('report_date'), 'unknown')}",
        f"- Generated at: {text(metadata.get('generated_at'), 'unknown')}",
        f"- Total alerts: {int(number(metadata.get('alert_count')))}",
        f"- Active alerts: {int(number(summary.get('active_count')))}",
        "",
        "## Active Alert Summary",
        "",
        f"- Critical: {int(number(summary.get('critical_count')))}",
        f"- High: {int(number(summary.get('high_count')))}",
        f"- Medium: {int(number(summary.get('medium_count')))}",
        f"- Low: {int(number(summary.get('low_count')))}",
        f"- Info: {int(number(summary.get('info_count')))}",
        "",
        "## Alerts By Severity",
        "",
    ]
    if severity_counts:
        lines.extend(f"- {severity}: {count}" for severity, count in severity_counts.items())
    else:
        lines.append("- No active alerts.")
    lines.extend(["", "## Alerts By Review Area", ""])
    if area_counts:
        lines.extend(f"- {area}: {count}" for area, count in area_counts.items())
    else:
        lines.append("- No active review areas.")
    lines.extend(
        [
            "",
            "## Top Priority Alerts",
            "",
            "| Priority | Severity | Area | Symbol | Title | Review action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if top_alerts:
        for row in top_alerts:
            lines.append(
                "| "
                + " | ".join(
                    (
                        markdown_escape(row.get("priority_score")),
                        markdown_escape(row.get("severity")),
                        markdown_escape(row.get("review_area")),
                        markdown_escape(row.get("symbol")),
                        markdown_escape(row.get("title")),
                        markdown_escape(row.get("recommended_review_action")),
                    )
                )
                + " |"
            )
    else:
        lines.append("|  |  |  |  | No active alerts. |  |")
    lines.extend(
        [
            "",
            "## Inactive Counts",
            "",
            f"- Dismissed: {int(number(inactive.get('dismissed')))}",
            f"- Resolved: {int(number(inactive.get('resolved')))}",
            f"- Total inactive: {int(number(inactive.get('inactive_total')))}",
            "",
        ]
    )
    return "\n".join(lines)


def write_alert_artifacts(
    source: Mapping[str, object] | Iterable[Mapping[str, object]],
    output_dir: str | Path,
    *,
    generated_at: str | None = None,
    report_date: str | None = None,
    basename: str = "alerts",
) -> dict[str, object]:
    artifact = build_alert_artifact(source, generated_at=generated_at, report_date=report_date)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / f"{basename}.json"
    markdown_path = destination / f"{basename}.md"
    json_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_alert_markdown(artifact) + "\n")
    return {
        "artifact": artifact,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "review_only": True,
        "recommendation_only": True,
        "guardrail": GUARDRAIL_TEXT,
    }


__all__ = [
    "GUARDRAIL_TEXT",
    "build_alert_artifact",
    "normalize_alert",
    "normalize_alerts",
    "render_alert_markdown",
    "write_alert_artifacts",
]
