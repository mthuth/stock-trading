"""Build the static local decision console manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stock_trading.local_console_artifacts import index_report_artifacts, utc_now
from stock_trading.local_console_panels import build_console_panels
from stock_trading.local_console_runs import DEFAULT_DB_PATH, read_recent_runs


ROOT = Path(__file__).resolve().parents[1]


GUARDRAILS = (
    "Recommendation-only decision support.",
    "No automatic trading.",
    "No broker access or broker writes.",
    "No order preview or order placement.",
    "No run buttons or command execution from the console.",
    "No real-time market behavior.",
    "No recommendation, scoring, target, decision-safety, allocation, provider, or AI behavior changes.",
)


def load_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        payload = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def latest_report_context_path(artifacts: dict[str, object]) -> str:
    latest = artifacts.get("latest")
    if not isinstance(latest, dict):
        return ""
    context = latest.get("report_context")
    if not isinstance(context, dict):
        return ""
    return str(context.get("path") or "")


def build_local_console_manifest(
    *,
    reports_dir: str | Path = "reports",
    report_context_path: str | Path | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    root: str | Path | None = None,
) -> dict[str, object]:
    base = Path(root).resolve() if root else ROOT
    artifacts = index_report_artifacts(reports_dir, root=base)
    context_path = str(report_context_path or latest_report_context_path(artifacts))
    report_context = load_json(context_path)
    runs = read_recent_runs(db_path)
    panels = build_console_panels(report_context, artifacts, runs)
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "recommendation_only": True,
        "review_only": True,
        "root": str(base),
        "workflow": {
            "build_manifest": "python3 scripts/build_local_console_manifest.py --output reports/local-console-manifest.json",
            "render_console": "python3 scripts/render_local_console.py --manifest reports/local-console-manifest.json --output reports/local-console.html",
            "open_console": "Open reports/local-console.html manually in a browser.",
            "note": "These are manual commands for the user; the console does not execute them.",
        },
        "guardrails": list(GUARDRAILS),
        "report_context": {
            "path": context_path,
            "available": bool(report_context),
            "report_date": str(report_context.get("metadata", {}).get("report_date", "")) if report_context else "",
            "empty_state": "" if report_context else "No report context artifact found; render a report context or daily report first.",
        },
        "artifacts": artifacts,
        "run_history": runs,
        "panels": panels,
    }


def write_manifest(manifest: dict[str, object], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local decision console manifest.")
    parser.add_argument("--reports-dir", default="reports", help="Directory containing generated report artifacts.")
    parser.add_argument("--report-context", default="", help="Optional explicit report-context JSON path.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Optional SQLite database path for read-only run history.")
    parser.add_argument("--output", required=True, help="Manifest JSON output path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_local_console_manifest(
        reports_dir=args.reports_dir,
        report_context_path=args.report_context or None,
        db_path=args.db_path,
    )
    path = write_manifest(manifest, args.output)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["GUARDRAILS", "build_local_console_manifest", "main", "write_manifest"]
