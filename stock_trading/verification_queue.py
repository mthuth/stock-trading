"""Semi-automatic verification queue runner."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from stock_trading.storage import (
    latest_open_verification_queue,
    update_verification_queue_item_status,
)


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class VerificationPlan:
    automation_mode: str
    commands: list[list[str]]
    blocked_status: str = ""
    blocked_summary: str = ""


Runner = Callable[[list[str]], int]


def command_plan(next_check: str, symbol: str, env: dict[str, str] | None = None) -> VerificationPlan:
    text = next_check.lower()
    env = env or os.environ
    symbol = symbol.upper()
    if "show_provider_gaps.py" in text:
        return VerificationPlan(
            "blocked_provider",
            [],
            "blocked_provider_fix_needed",
            "Provider access/config review is required before this queue item can be resolved.",
        )
    if "ingest_benzinga_analyst_targets.py" in text:
        if not env.get("BENZINGA_API_KEY", "").strip():
            return VerificationPlan(
                "conditional",
                [],
                "manual_required",
                "BENZINGA_API_KEY is not configured; add verified targets to config/manual_analyst_targets.csv or provide a key.",
            )
        return VerificationPlan(
            "conditional",
            [[sys.executable, "scripts/ingest_benzinga_analyst_targets.py", "--symbols", symbol]],
        )
    if "config/manual_analyst_targets.csv" in text:
        return VerificationPlan(
            "manual",
            [],
            "manual_required",
            "Manual analyst target rows are required; the runner never invents or edits targets automatically.",
        )
    if "ingest_sec.py" in text and "ingest_official_ir.py" in text:
        return VerificationPlan(
            "auto",
            [
                [sys.executable, "scripts/ingest_sec.py", symbol],
                [sys.executable, "scripts/ingest_official_ir.py", "--symbols", symbol],
            ],
        )
    if "ingest_price_history.py" in text:
        return VerificationPlan(
            "auto",
            [[sys.executable, "scripts/ingest_price_history.py", "--symbols", symbol]],
        )
    if "ingest_research_depth.py" in text or "ingest_finnhub.py" in text:
        commands = []
        if "ingest_research_depth.py" in text:
            commands.append([sys.executable, "scripts/ingest_research_depth.py", "--symbols", symbol])
        if "ingest_finnhub.py" in text:
            commands.append([sys.executable, "scripts/ingest_finnhub.py", symbol])
        return VerificationPlan("auto_nonfatal", commands)
    return VerificationPlan(
        "manual",
        [],
        "manual_required",
        f"No safe automation mapping exists for next check: {next_check}",
    )


def execute_commands(commands: Iterable[list[str]], runner: Runner) -> tuple[bool, list[str]]:
    summaries: list[str] = []
    ok = True
    for command in commands:
        status = runner(command)
        label = " ".join(command[1:]) if command and command[0] == sys.executable else " ".join(command)
        summaries.append(f"{label}: exit={status}")
        if status != 0:
            ok = False
    return ok, summaries


def default_runner(command: list[str]) -> int:
    print(f"$ {' '.join(command)}", flush=True)
    return subprocess.call(command, cwd=ROOT)


def run_queue(
    execute: bool = False,
    limit: int = 10,
    symbol: str = "",
    runner: Runner = default_runner,
    env: dict[str, str] | None = None,
) -> int:
    rows = latest_open_verification_queue(limit=limit, symbol=symbol)
    executable = [row for row in rows if str(row["status"]) in {"queued", "failed"}]
    if not executable:
        print("No executable verification queue items found.")
        return 0
    failures = 0
    for row in executable:
        plan = command_plan(str(row["next_check"] or ""), str(row["symbol"] or ""), env)
        print(
            f"{row['symbol']}: {row['status']} -> {plan.automation_mode}; "
            f"{row['next_check']}",
            flush=True,
        )
        if not execute:
            continue
        if plan.blocked_status:
            update_verification_queue_item_status(
                int(row["id"]),
                plan.blocked_status,
                plan.blocked_summary,
                completed=True,
            )
            continue
        update_verification_queue_item_status(
            int(row["id"]),
            "running",
            "Verification commands started.",
            started=True,
        )
        ok, summaries = execute_commands(plan.commands, runner)
        status = "completed" if ok or plan.automation_mode == "auto_nonfatal" else "failed"
        if status == "failed":
            failures += 1
        update_verification_queue_item_status(
            int(row["id"]),
            status,
            "; ".join(summaries),
            completed=True,
        )
    return 1 if failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run queued stock insight verification checks.")
    parser.add_argument("--execute", action="store_true", help="Run safe queued verification commands.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum queue items to inspect.")
    parser.add_argument("--symbol", default="", help="Restrict to one ticker symbol.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_queue(execute=args.execute, limit=max(1, args.limit), symbol=args.symbol.strip().upper())


if __name__ == "__main__":
    sys.exit(main())
