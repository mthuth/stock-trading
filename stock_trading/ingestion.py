#!/usr/bin/env python3
"""Provider-neutral ingestion boundary for the stock research engine."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]

from stock_trading.provider_gap_status import PROVIDER_STATUSES, normalize_provider_status
from stock_trading.storage import init_db, latest_provider_gaps


CommandRunner = Callable[[list[str]], int]
INGESTION_STATUSES = PROVIDER_STATUSES


@dataclass(frozen=True)
class IngestionResult:
    provider: str
    endpoint: str
    symbol: str
    status: str
    message: str = ""
    payload_ref: str = ""
    normalized_rows: int = 0
    freshness: str = ""
    command: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_command(command: list[str]) -> int:
    return subprocess.call(command, cwd=ROOT)


def normalize_status(status: str, message: str = "") -> str:
    return normalize_provider_status(status, message)


def status_for_exit(status_code: int, message: str = "") -> str:
    if status_code == 0:
        return normalize_status("ok", message)
    return normalize_status("error", message or f"exit={status_code}")


def command_result(
    provider: str,
    endpoint: str,
    command: list[str],
    runner: CommandRunner = run_command,
) -> IngestionResult:
    status_code = runner(command)
    message = "" if status_code == 0 else f"exit={status_code}"
    status = status_for_exit(status_code, message)
    return IngestionResult(
        provider=provider,
        endpoint=endpoint,
        symbol="MARKET",
        status=status,
        message=message,
        command=" ".join(command),
    )


def refresh_prices(runner: CommandRunner = run_command) -> IngestionResult:
    return command_result(
        "multi-provider",
        "market_data",
        [sys.executable, "scripts/refresh_market_data.py"],
        runner,
    )


def refresh_price_history(
    provider: str = "yahoo",
    runner: CommandRunner = run_command,
) -> IngestionResult:
    return command_result(
        f"{provider} price history",
        "price_history",
        [sys.executable, "scripts/ingest_price_history.py", "--provider", provider],
        runner,
    )


def refresh_research_evidence(
    include_finnhub: bool = True,
    include_research_depth: bool = True,
    include_public_feeds: bool = False,
    runner: CommandRunner = run_command,
) -> list[IngestionResult]:
    steps: list[tuple[str, str, list[str]]] = []
    if include_finnhub:
        steps.append(("Finnhub", "research_evidence", [sys.executable, "scripts/ingest_finnhub.py"]))
    if include_research_depth:
        steps.append(("Research depth", "research_evidence", [sys.executable, "scripts/ingest_research_depth.py"]))
    if include_public_feeds:
        steps.append(("Public research feeds", "research_evidence", [sys.executable, "scripts/ingest_public_research_feeds.py"]))
    return [command_result(provider, endpoint, command, runner) for provider, endpoint, command in steps]


def refresh_filings(runner: CommandRunner = run_command) -> list[IngestionResult]:
    return [
        command_result("SEC EDGAR", "filings_and_facts", [sys.executable, "scripts/ingest_sec.py"], runner),
        command_result("Company investor relations", "official_ir", [sys.executable, "scripts/ingest_official_ir.py"], runner),
    ]


def provider_health_snapshot(limit: int = 200) -> list[dict[str, object]]:
    gaps = latest_provider_gaps(limit)
    return [
        {
            "refreshed_at": row["refreshed_at"],
            "symbol": row["symbol"],
            "provider": row["provider"],
            "field_name": row["field_name"],
            "status": row["status"],
            "message": row["message"],
        }
        for row in gaps
    ]


def latest_provider_statuses(limit: int = 50) -> list[dict[str, object]]:
    conn = init_db()
    conn.row_factory = __import__("sqlite3").Row
    rows = conn.execute(
        """
        SELECT p.refreshed_at, f.symbol, f.provider, f.field_name, f.status, f.message
        FROM provider_field_status f
        JOIN provider_refresh_runs p ON p.id = f.run_id
        ORDER BY p.id DESC, f.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    statuses = []
    for row in rows:
        item = dict(row)
        item["status"] = normalize_status(item.get("status", ""), str(item.get("message", "")))
        statuses.append(item)
    return statuses


def summarize_results(results: Iterable[IngestionResult]) -> dict[str, int]:
    summary = {status: 0 for status in sorted(INGESTION_STATUSES)}
    for result in results:
        summary[normalize_status(result.status, result.message)] += 1
    return summary
