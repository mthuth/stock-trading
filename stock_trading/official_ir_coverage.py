#!/usr/bin/env python3
"""Official company investor-relations coverage helpers."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from stock_trading.storage.connection import ROOT, init_db


IR_PROVIDER = "Company investor relations"
IR_FIELD_NAME = "official_ir_page"

IR_EVIDENCE_TYPES = (
    "earnings_release",
    "investor_presentation",
    "annual_report",
    "transcript",
    "guidance",
    "investor_event",
    "ir_update",
    "unknown_official_ir_item",
)

OPERATING_COMPANY_EXCLUDED_TYPES = {"etf"}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def approved_operating_companies(rows: Iterable[Mapping[str, object]]) -> list[dict[str, str]]:
    companies: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol or symbol in seen:
            continue
        category = str(row.get("category", "")).strip().lower()
        sleeve = str(row.get("sleeve", "")).strip().lower()
        trade_type = str(row.get("trade_type", "")).strip().lower()
        if (
            category in OPERATING_COMPANY_EXCLUDED_TYPES
            or sleeve in OPERATING_COMPANY_EXCLUDED_TYPES
            or trade_type in OPERATING_COMPANY_EXCLUDED_TYPES
        ):
            continue
        companies.append(
            {
                "symbol": symbol,
                "company": str(row.get("company", "") or row.get("company_name", "")).strip(),
            }
        )
        seen.add(symbol)
    return companies


def security_type_for_row(row: Mapping[str, object]) -> str:
    tokens = " ".join(
        str(row.get(key, "")).strip().lower()
        for key in ("category", "sleeve", "trade_type", "company", "company_name")
    )
    return "non_operating_company" if "etf" in tokens or "non_operating" in tokens or "non-operating" in tokens else "operating_company"


def approved_ir_subjects(rows: Iterable[Mapping[str, object]]) -> list[dict[str, str]]:
    subjects: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol or symbol in seen:
            continue
        subjects.append(
            {
                "symbol": symbol,
                "company": str(row.get("company", "") or row.get("company_name", "")).strip(),
                "security_type": security_type_for_row(row),
            }
        )
        seen.add(symbol)
    return subjects


def ir_source_map(rows: Iterable[Mapping[str, object]]) -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        sources[symbol] = {
            "symbol": symbol,
            "company": str(row.get("company_name", "") or row.get("company", "")).strip(),
            "ir_url": str(row.get("ir_url", "")).strip(),
            "source_focus": str(row.get("source_focus", "")).strip(),
        }
    return sources


def classify_ir_evidence_type(text: str, href: str = "") -> str:
    haystack = f"{text or ''} {href or ''}".lower()
    if any(term in haystack for term in ("transcript", "call transcript")):
        return "transcript"
    if any(term in haystack for term in ("presentation", "slides", "deck")):
        return "investor_presentation"
    if any(term in haystack for term in ("annual report", "10-k", "form 10-k", "20-f")):
        return "annual_report"
    if any(term in haystack for term in ("guidance", "outlook", "forecast")):
        return "guidance"
    if any(term in haystack for term in ("earnings", "financial results", "quarterly results", "results release")):
        return "earnings_release"
    if any(term in haystack for term in ("investor day", "conference", "webcast", "event")):
        return "investor_event"
    if any(term in haystack for term in ("release", "news", "update", "press")):
        return "ir_update"
    return "unknown_official_ir_item"


def official_ir_provider_endpoint(evidence_type: str) -> str:
    if evidence_type not in IR_EVIDENCE_TYPES:
        evidence_type = "unknown_official_ir_item"
    return f"official_ir_{evidence_type}"


def _latest_status_by_symbol(rows: Iterable[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    latest: dict[str, Mapping[str, object]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        run_id = int(row.get("run_id") or 0)
        existing = latest.get(symbol)
        if existing is None or run_id >= int(existing.get("run_id") or 0):
            latest[symbol] = row
    return latest


def _latest_success_by_symbol(rows: Iterable[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    latest: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if str(row.get("status", "")).lower() != "ok":
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        run_id = int(row.get("run_id") or 0)
        existing = latest.get(symbol)
        if existing is None or run_id >= int(existing.get("run_id") or 0):
            latest[symbol] = row
    return latest


def _latest_issue_by_symbol(rows: Iterable[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    latest: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if str(row.get("status", "")).lower() == "ok":
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        run_id = int(row.get("run_id") or 0)
        existing = latest.get(symbol)
        if existing is None or run_id >= int(existing.get("run_id") or 0):
            latest[symbol] = row
    return latest


def _evidence_types_by_symbol(rows: Iterable[Mapping[str, object]]) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        evidence_type = str(row.get("ir_evidence_type") or "").strip()
        if not evidence_type:
            endpoint = str(row.get("provider_endpoint") or "")
            if endpoint.startswith("official_ir_"):
                endpoint_type = endpoint.removeprefix("official_ir_")
                if endpoint_type in IR_EVIDENCE_TYPES:
                    evidence_type = endpoint_type
        if not evidence_type:
            evidence_type = classify_ir_evidence_type(
                str(row.get("title", "") or row.get("summary", "")),
                str(row.get("source_url", "")),
            )
        if evidence_type:
            found.setdefault(symbol, set()).add(evidence_type)
    return {symbol: sorted(values) for symbol, values in found.items()}


def build_official_ir_coverage(
    approved_companies: Iterable[Mapping[str, object]],
    source_rows: Iterable[Mapping[str, object]],
    provider_status_rows: Iterable[Mapping[str, object]] = (),
    evidence_rows: Iterable[Mapping[str, object]] = (),
) -> list[dict[str, object]]:
    sources = ir_source_map(source_rows)
    status_rows = list(provider_status_rows)
    latest_status = _latest_status_by_symbol(status_rows)
    latest_success = _latest_success_by_symbol(status_rows)
    latest_issue = _latest_issue_by_symbol(status_rows)
    evidence_types = _evidence_types_by_symbol(evidence_rows)
    coverage: list[dict[str, object]] = []
    for company in approved_ir_subjects(approved_companies):
        symbol = company["symbol"]
        if company.get("security_type") == "non_operating_company":
            coverage.append(
                {
                    "symbol": symbol,
                    "company": str(company.get("company") or ""),
                    "security_type": "non_operating_company",
                    "configured_ir_url": "",
                    "ir_source_status": "expected",
                    "latest_successful_fetch": "",
                    "latest_issue": "ETF/non-operating symbol; official company IR source is not required.",
                    "evidence_types_found": [],
                    "source_focus": "non_operating_company",
                }
            )
            continue
        source = sources.get(symbol, {})
        latest = latest_status.get(symbol)
        success = latest_success.get(symbol)
        issue = latest_issue.get(symbol)
        configured_url = str(source.get("ir_url", "")).strip()
        if not configured_url:
            status = "missing_source"
            issue_message = "No official company IR source is configured."
        elif latest:
            status = str(latest.get("status") or "configured_no_fetch")
            issue_message = "" if status == "ok" else str(latest.get("message") or "")
        else:
            status = "configured_no_fetch"
            issue_message = "Official IR source is configured but has not been fetched yet."
        if issue and status == "ok":
            issue_message = str(issue.get("message") or "")
        elif issue and not issue_message:
            issue_message = str(issue.get("message") or "")
        coverage.append(
            {
                "symbol": symbol,
                "company": str(source.get("company") or company.get("company") or ""),
                "security_type": "operating_company",
                "configured_ir_url": configured_url,
                "ir_source_status": status,
                "latest_successful_fetch": str(success.get("refreshed_at") or "") if success else "",
                "latest_issue": issue_message,
                "evidence_types_found": evidence_types.get(symbol, []),
                "source_focus": str(source.get("source_focus") or ""),
            }
        )
    return coverage


def coverage_gap_status_rows(coverage: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in coverage:
        status = str(row.get("ir_source_status") or "")
        if status in {"ok", "configured_no_fetch"}:
            continue
        rows.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "provider": IR_PROVIDER,
                "field_name": IR_FIELD_NAME,
                "status": status,
                "message": str(row.get("latest_issue") or ""),
            }
        )
    return rows


def _provider_status_rows(conn: sqlite3.Connection) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            f.symbol,
            f.provider,
            f.field_name,
            f.status,
            f.message,
            p.id AS run_id,
            p.refreshed_at
        FROM provider_field_status f
        JOIN provider_refresh_runs p ON p.id = f.run_id
        WHERE f.provider = ?
          AND f.field_name = ?
        ORDER BY p.id ASC, f.id ASC
        """,
        (IR_PROVIDER, IR_FIELD_NAME),
    ).fetchall()
    return [dict(row) for row in rows]


def _evidence_rows(conn: sqlite3.Connection) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT symbol, evidence_type, provider_endpoint, title, summary, source_url, fetched_at
        FROM research_evidence
        WHERE source_name = ?
        """,
        (IR_PROVIDER,),
    ).fetchall()
    return [dict(row) for row in rows]


def official_ir_coverage_snapshot(
    research_inputs_path: Path | None = None,
    ir_sources_path: Path | None = None,
) -> list[dict[str, object]]:
    research_inputs_path = research_inputs_path or ROOT / "config" / "research_inputs.csv"
    ir_sources_path = ir_sources_path or ROOT / "config" / "official_ir_sources.csv"
    conn = init_db()
    try:
        return build_official_ir_coverage(
            read_csv_rows(research_inputs_path),
            read_csv_rows(ir_sources_path),
            _provider_status_rows(conn),
            _evidence_rows(conn),
        )
    finally:
        conn.close()
