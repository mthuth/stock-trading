#!/usr/bin/env python3
"""Plan source refresh priority and backfill work from stored ingestion state."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading import storage  # noqa: E402


PUBLIC_CATEGORIES = {
    "ai_research",
    "company_blog",
    "company_newsroom",
    "company_ir",
    "newsletter",
    "podcast",
    "press_wire",
    "semiconductor_news",
    "tech_news",
}
OFFICIAL_CATEGORIES = {"sec", "company_ir", "company_blog", "company_newsroom"}
NEWS_CATEGORIES = {"press_wire", "semiconductor_news", "tech_news", "ai_research"}
SLOW_CONTEXT_CATEGORIES = {"newsletter", "podcast"}
BLOCKED_STATUSES = {"blocked", "error", "failed", "missing", "parser_gap", "rate_limited"}
COOLDOWN_DAYS = {
    "blocked": 7,
    "rate_limited": 1,
    "error": 2,
    "failed": 2,
    "missing": 2,
    "parser_gap": 2,
    "stale": 0,
    "not_due": 0,
    "due": 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the ingestion freshness and backfill plan.")
    parser.add_argument("--rebuild", action="store_true", help="Replace the stored plan and backfill queue.")
    parser.add_argument("--source", default="", help="Optional source-name filter.")
    parser.add_argument("--limit", type=int, default=0, help="Only store the top N run-plan rows.")
    return parser.parse_args()


def clean(value: object) -> str:
    return str(value or "").strip()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: object) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00"), text[:19]):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def iso(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else ""


def load_source_configs() -> dict[str, dict[str, str]]:
    configs: dict[str, dict[str, str]] = {}
    for path in (storage.CONFIG_DIR / "research_sources.csv", storage.CONFIG_DIR / "research_source_integrations.csv"):
        if not path.exists():
            continue
        rows, _ = storage.read_csv(path)
        for row in rows:
            name = clean(row.get("source_name"))
            if not name:
                continue
            current = configs.setdefault(name, {"source_name": name})
            current.update({key: clean(value) for key, value in row.items()})
    return configs


def cadence_days(config: dict[str, str]) -> int:
    category = config.get("source_category") or config.get("source_type") or ""
    tier = config.get("source_tier") or ""
    access = config.get("access_model") or ""
    status = config.get("implementation_status") or ""
    if "paid_api_candidate" in access or status == "not_implemented":
        return 30
    if category in {"press_wire", "tech_news", "company_blog", "company_newsroom"}:
        return 1
    if category in {"ai_research", "semiconductor_news", "newsletter", "podcast"}:
        return 2
    if "tier_1" in tier:
        return 1
    return 7


def command_for_source(config: dict[str, str]) -> str:
    name = config.get("source_name", "")
    category = config.get("source_category") or config.get("source_type") or ""
    if name == "Alpha Vantage news sentiment":
        return "python3 scripts/ingest_research_depth.py --provider alpha_vantage"
    if name in {"SEC EDGAR", "SEC EDGAR submissions API", "SEC EDGAR companyfacts API"}:
        return "python3 scripts/ingest_sec.py"
    if name == "Company investor relations" or category == "company_ir":
        return "python3 scripts/ingest_official_ir.py"
    if category in PUBLIC_CATEGORIES:
        return f"python3 scripts/ingest_public_research_feeds.py --source {shellish(name)}"
    if "benzinga" in name.lower():
        return "python3 scripts/ingest_benzinga_analyst_targets.py"
    if "finnhub" in name.lower():
        return "python3 scripts/ingest_finnhub.py"
    return "python3 scripts/run_daily.py --ingest-free-data"


def shellish(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def latest_source_state(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    states: dict[str, dict[str, Any]] = {}

    def ensure(name: str) -> dict[str, Any]:
        return states.setdefault(
            name,
            {
                "records": 0,
                "raw_payloads": 0,
                "duplicates": 0,
                "latest_attempt": "",
                "latest_success": "",
                "latest_issue": "",
                "latest_status": "",
                "covered_since": "",
                "covered_until": "",
            },
        )

    for row in conn.execute(
        """
        SELECT source_name, COUNT(*) AS records, MIN(source_timestamp) AS covered_since,
               MAX(source_timestamp) AS covered_until, MAX(fetched_at) AS latest_success
        FROM research_evidence
        GROUP BY source_name
        """
    ):
        state = ensure(clean(row["source_name"]))
        state["records"] += int(row["records"] or 0)
        state["latest_success"] = latest_time(state["latest_success"], row["latest_success"])
        state["covered_since"] = earliest_time(state["covered_since"], row["covered_since"])
        state["covered_until"] = latest_time(state["covered_until"], row["covered_until"])

    for row in conn.execute(
        """
        SELECT provider, COUNT(*) AS raw_payloads, MAX(created_at) AS latest_attempt
        FROM raw_ingestion_payloads
        GROUP BY provider
        """
    ):
        state = ensure(clean(row["provider"]))
        state["raw_payloads"] += int(row["raw_payloads"] or 0)
        state["latest_attempt"] = latest_time(state["latest_attempt"], row["latest_attempt"])

    for row in conn.execute(
        """
        SELECT r.provider, r.status, r.message, r.created_at
        FROM raw_ingestion_payloads r
        JOIN (
            SELECT provider, MAX(id) AS latest_id
            FROM raw_ingestion_payloads
            GROUP BY provider
        ) latest ON latest.latest_id = r.id
        """
    ):
        state = ensure(clean(row["provider"]))
        state["latest_attempt"] = latest_time(state["latest_attempt"], row["created_at"])
        state["latest_status"] = clean(row["status"]).lower()
        if clean(row["status"]).lower() == "ok":
            state["latest_success"] = latest_time(state["latest_success"], row["created_at"])
        else:
            state["latest_issue"] = clean(row["message"]) or clean(row["status"])

    for row in conn.execute(
        """
        SELECT p.provider, p.status, p.message, p.created_at
        FROM provider_payloads p
        JOIN (
            SELECT provider, MAX(id) AS latest_id
            FROM provider_payloads
            GROUP BY provider
        ) latest ON latest.latest_id = p.id
        """
    ):
        state = ensure(clean(row["provider"]))
        state["latest_attempt"] = latest_time(state["latest_attempt"], row["created_at"])
        state["latest_status"] = clean(row["status"]).lower()
        if clean(row["status"]).lower() == "ok":
            state["latest_success"] = latest_time(state["latest_success"], row["created_at"])
        else:
            state["latest_issue"] = clean(row["message"]) or clean(row["status"])

    for row in conn.execute(
        """
        SELECT q.source_name, q.duplicate_records, q.raw_payloads, q.total_evidence,
               q.latest_success, q.latest_issue, q.latest_evidence_at,
               q.error_runs, q.blocked_runs
        FROM source_quality_metrics q
        JOIN (
            SELECT source_name, MAX(metric_date) AS metric_date
            FROM source_quality_metrics
            GROUP BY source_name
        ) latest
          ON latest.source_name = q.source_name
         AND latest.metric_date = q.metric_date
        """
    ):
        state = ensure(clean(row["source_name"]))
        state["duplicates"] = int(row["duplicate_records"] or 0)
        state["raw_payloads"] = max(int(state.get("raw_payloads") or 0), int(row["raw_payloads"] or 0))
        state["records"] = max(int(state.get("records") or 0), int(row["total_evidence"] or 0))
        state["latest_success"] = latest_time(state["latest_success"], row["latest_success"] or row["latest_evidence_at"])
        state["latest_issue"] = clean(row["latest_issue"]) or clean(state.get("latest_issue"))
        if int(row["blocked_runs"] or 0) > 0:
            state["latest_status"] = "blocked"
        elif int(row["error_runs"] or 0) > 0 and not clean(state.get("latest_status")):
            state["latest_status"] = "error"

    return states


def latest_time(current: object, candidate: object) -> str:
    current_dt = parse_time(current)
    candidate_dt = parse_time(candidate)
    if candidate_dt and (not current_dt or candidate_dt > current_dt):
        return clean(candidate)
    return clean(current)


def earliest_time(current: object, candidate: object) -> str:
    current_dt = parse_time(current)
    candidate_dt = parse_time(candidate)
    if candidate_dt and (not current_dt or candidate_dt < current_dt):
        return clean(candidate)
    return clean(current)


def quality_by_source(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT q.source_name, q.quality_label
        FROM source_quality_metrics q
        JOIN (
            SELECT source_name, MAX(metric_date) AS metric_date
            FROM source_quality_metrics
            GROUP BY source_name
        ) latest
          ON latest.source_name = q.source_name
         AND latest.metric_date = q.metric_date
        """
    ).fetchall()
    return {clean(row["source_name"]): clean(row["quality_label"]) for row in rows}


def classify_due(
    state: dict[str, Any],
    config: dict[str, str],
    cadence: int,
    quality_label: str,
    needs_backfill: bool,
    now: datetime,
) -> tuple[str, datetime | None, datetime | None, str]:
    implementation_status = clean(config.get("implementation_status")).lower()
    access_model = clean(config.get("access_model")).lower()
    if implementation_status == "not_implemented":
        return "not_implemented", None, None, "Source is configured but ingestion is not implemented yet."
    if access_model == "paid_api_candidate":
        return "not_implemented", None, None, "Source requires a paid/API access decision before automation."

    latest_success = parse_time(state.get("latest_success"))
    latest_attempt = parse_time(state.get("latest_attempt"))
    latest_issue = clean(state.get("latest_issue"))
    latest_status = clean(state.get("latest_status")).lower()
    base_time = latest_success or latest_attempt
    next_run = (base_time + timedelta(days=cadence)) if base_time else now

    if latest_status in BLOCKED_STATUSES or quality_label == "blocked":
        cooldown_key = "blocked" if latest_status == "blocked" or quality_label == "blocked" else latest_status
        cooldown_days = COOLDOWN_DAYS.get(cooldown_key, COOLDOWN_DAYS["error"])
        cooldown_until = (latest_attempt or now) + timedelta(days=cooldown_days)
        if cooldown_until > now:
            return "cooldown", next_run, cooldown_until, latest_issue or "Recent blocked/error status; cooling down before retry."
        return "blocked", next_run, cooldown_until, latest_issue or "Blocked or failing source needs review before retry."
    if not base_time:
        return "due", now, None, "No successful source run recorded yet."
    if next_run <= now:
        return "stale", next_run, None, "Cadence elapsed; source data is stale and ready to refresh."
    if needs_backfill:
        return "backfill_needed", next_run, None, "Current data is fresh, but stored history does not cover the desired backfill window."
    return "not_due", next_run, None, "Recently refreshed; skip until cadence elapses."


def priority_for(row: dict[str, Any], quality_label: str) -> int:
    base = {
        "due": 100,
        "stale": 90,
        "backfill_needed": 180,
        "blocked": 650,
        "not_implemented": 900,
        "not_due": 500,
        "cooldown": 800,
    }.get(row["due_status"], 600)
    quality_bonus = {
        "high_signal": -40,
        "useful_context": -20,
        "needs_review": 10,
        "not_enough_data": -10,
        "blocked": 100,
    }.get(quality_label, 0)
    category = clean(row.get("source_category"))
    tier = clean(row.get("source_tier"))
    if category in OFFICIAL_CATEGORIES or "official" in tier:
        category_bonus = -35
    elif category in NEWS_CATEGORIES:
        category_bonus = -15
    elif category in SLOW_CONTEXT_CATEGORIES:
        category_bonus = 40
    else:
        category_bonus = 0
    record_penalty = 20 if int(row.get("records") or 0) == 0 else 0
    return max(1, base + quality_bonus + category_bonus + record_penalty)


def backfill_window_days(config: dict[str, str]) -> int:
    category = config.get("source_category") or config.get("source_type") or ""
    if category in {"company_blog", "company_newsroom", "press_wire"}:
        return 90
    if category in {"newsletter", "podcast"}:
        return 60
    if category in {"tech_news", "ai_research", "semiconductor_news"}:
        return 45
    return 30


def backfill_needed(state: dict[str, Any], config: dict[str, str], now: datetime) -> tuple[bool, int, str]:
    desired_days = backfill_window_days(config)
    covered_since = parse_time(state.get("covered_since"))
    records = int(state.get("records") or 0)
    if records < 3:
        return True, desired_days, "No records yet." if records == 0 else "Too few records for source history."
    if not covered_since:
        return True, desired_days, "Missing source coverage start date."
    if covered_since > now - timedelta(days=desired_days):
        return True, desired_days, "Stored history does not cover desired window."
    return False, desired_days, ""


def build_plan(source_filter: str = "", limit: int = 0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    configs = load_source_configs()
    if source_filter:
        configs = {name: config for name, config in configs.items() if name == source_filter}
    conn = storage.init_db()
    states = latest_source_state(conn)
    quality = quality_by_source(conn)
    conn.close()
    now = utc_now()
    run_rows: list[dict[str, Any]] = []
    backfill_rows: list[dict[str, Any]] = []

    for name, config in sorted(configs.items()):
        category = config.get("source_category") or config.get("source_type") or ""
        state = states.get(name, {})
        cadence = cadence_days(config)
        quality_label = quality.get(name, "")
        needs_backfill, desired_days, backfill_reason = backfill_needed(state, config, now)
        due_status, next_run, cooldown_until, reason = classify_due(
            state,
            config,
            cadence,
            quality_label,
            needs_backfill,
            now,
        )
        row = {
            "source_name": name,
            "source_category": category,
            "source_tier": config.get("source_tier") or "",
            "cadence_days": cadence,
            "latest_attempt": clean(state.get("latest_attempt")),
            "latest_success": clean(state.get("latest_success")),
            "next_run_at": iso(next_run),
            "cooldown_until": iso(cooldown_until),
            "due_status": due_status,
            "priority_rank": 999,
            "records": int(state.get("records") or 0),
            "raw_payloads": int(state.get("raw_payloads") or 0),
            "duplicate_records": int(state.get("duplicates") or 0),
            "latest_issue": clean(state.get("latest_issue")),
            "run_command": command_for_source(config),
            "reason": f"{reason} {backfill_reason}".strip(),
        }
        row["priority_rank"] = priority_for(row, quality_label)
        run_rows.append(row)

        covered_since = parse_time(state.get("covered_since"))
        covered_until = parse_time(state.get("covered_until"))
        records = int(state.get("records") or 0)
        if needs_backfill and config.get("access_model") != "paid_api_candidate":
            symbol = direct_symbol_for_source(name)
            backfill_rows.append(
                {
                    "source_name": name,
                    "symbol": symbol or "ALL",
                    "backfill_type": "historical_source_window",
                    "status": "queued" if due_status != "cooldown" else "cooldown",
                    "priority_rank": row["priority_rank"] + (0 if records == 0 else 25),
                    "desired_window_days": desired_days,
                    "covered_since": clean(state.get("covered_since")),
                    "covered_until": clean(state.get("covered_until")),
                    "record_count": records,
                    "next_action": (
                        "Find stable feed/page-link path and backfill initial source window."
                        if records == 0
                        else f"Extend source history toward a {desired_days}-day window."
                    ),
                    "command": row["run_command"],
                    "reason": backfill_reason,
                }
            )

    run_rows.sort(key=lambda row: (int(row["priority_rank"]), row["source_name"]))
    for index, row in enumerate(run_rows, start=1):
        row["priority_rank"] = index
    backfill_rows.sort(key=lambda row: (int(row["priority_rank"]), row["source_name"]))
    for index, row in enumerate(backfill_rows, start=1):
        row["priority_rank"] = index
    if limit > 0:
        run_rows = run_rows[:limit]
    return run_rows, backfill_rows


def direct_symbol_for_source(source_name: str) -> str:
    path = storage.CONFIG_DIR / "symbol_aliases.csv"
    if not path.exists():
        return ""
    rows, _ = storage.read_csv(path)
    for row in rows:
        if clean(row.get("source_name")) == source_name and clean(row.get("match_type")) == "direct_symbol":
            return clean(row.get("symbol")).upper()
    return ""


def main() -> int:
    args = parse_args()
    plan_rows, backfill_rows = build_plan(args.source, args.limit)
    plan_inserted = storage.record_ingestion_run_plan(plan_rows, rebuild=args.rebuild and not args.source)
    backfill_inserted = storage.record_ingestion_backfill_queue(backfill_rows, rebuild=args.rebuild and not args.source)
    storage.record_provider_payload(
        "Local ingestion planner",
        "ingestion_freshness_backfill_plan",
        args.source or "ALL",
        "ok",
        f"run_plan={len(plan_rows)} backfill={len(backfill_rows)} inserted_plan={plan_inserted} inserted_backfill={backfill_inserted}",
        payload_json={
            "run_plan": len(plan_rows),
            "backfill": len(backfill_rows),
            "source": args.source,
        },
    )
    print(
        "Ingestion plan complete: "
        f"run_plan={len(plan_rows)} backfill={len(backfill_rows)} "
        f"inserted_plan={plan_inserted} inserted_backfill={backfill_inserted}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
