#!/usr/bin/env python3
"""Provider-neutral ingestion boundary for the stock research engine."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]

from stock_trading.storage import init_db, latest_provider_gaps


CommandRunner = Callable[[list[str]], int]


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


def command_result(
    provider: str,
    endpoint: str,
    command: list[str],
    runner: CommandRunner = run_command,
) -> IngestionResult:
    status_code = runner(command)
    status = "ok" if status_code == 0 else "error"
    return IngestionResult(
        provider=provider,
        endpoint=endpoint,
        symbol="MARKET",
        status=status,
        message="" if status_code == 0 else f"exit={status_code}",
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
    return [dict(row) for row in rows]


def summarize_results(results: Iterable[IngestionResult]) -> dict[str, int]:
    summary = {"ok": 0, "error": 0, "blocked": 0, "missing": 0, "stale": 0}
    for result in results:
        summary.setdefault(result.status, 0)
        summary[result.status] += 1
    return summary
