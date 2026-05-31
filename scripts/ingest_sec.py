#!/usr/bin/env python3
"""Ingest SEC CIK mapping, filing metadata, and selected company facts."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    load_env,
    read_csv,
    record_provider_payload,
    record_provider_run,
    record_research_evidence,
    upsert_company_identifier,
    RESEARCH_FILE,
)
from provider_client import fetch_json_url, sanitize_provider_message  # noqa: E402
from stock_trading.sec_coverage import (  # noqa: E402
    CikMapping,
    SecCoverageSubject,
    SecEndpointResult,
    normalize_sec_ticker_map,
    provider_status_rows,
    subject_from_research_row,
    summarize_symbol_coverage,
)


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
SEC_FACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts"
DEFAULT_USER_AGENT = "StockTradingResearch/0.1 mthuth@gmail.com"
RECENT_FILING_FORMS = {"10-K", "10-Q", "8-K", "20-F", "6-K"}
FACT_CONCEPTS = {
    "Revenues": "Revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
    "NetIncomeLoss": "Net income",
    "EarningsPerShareDiluted": "Diluted EPS",
    "OperatingIncomeLoss": "Operating income",
    "NetCashProvidedByUsedInOperatingActivities": "Operating cash flow",
    "Assets": "Assets",
    "Liabilities": "Liabilities",
    "StockholdersEquity": "Stockholders equity",
    "WeightedAverageNumberOfDilutedSharesOutstanding": "Diluted shares",
}


def sec_get_json(url: str, user_agent: str) -> tuple[str, object, str]:
    result = fetch_json_url(
        url,
        headers={"User-Agent": user_agent},
        timeout=30,
        retries=2,
    )
    message = result.message
    if result.error_class:
        message = f"{message}; error_class={result.error_class}; attempts={result.attempts}".strip("; ")
    elif result.attempts > 1:
        message = f"{message}; attempts={result.attempts}".strip("; ")
    return result.status, result.payload, sanitize_provider_message(message)


def symbols_from_research() -> list[str]:
    return [subject.symbol for subject in subjects_from_research()]


def subjects_from_research() -> list[SecCoverageSubject]:
    rows, _ = read_csv(RESEARCH_FILE)
    subjects = []
    for row in rows:
        subject = subject_from_research_row(row)
        if subject.symbol:
            subjects.append(subject)
    return subjects


def load_ticker_map(user_agent: str) -> dict[str, CikMapping]:
    status, payload, message = sec_get_json(SEC_TICKERS_URL, user_agent)
    record_provider_payload(
        provider="SEC EDGAR",
        endpoint="company_tickers",
        symbol="",
        status=status,
        message=message,
        payload_json=payload if status == "ok" else None,
    )
    if status != "ok" or not isinstance(payload, dict):
        raise RuntimeError(f"Unable to load SEC ticker map: {message}")

    return normalize_sec_ticker_map(payload)


def filing_url(cik: str, accession: str, primary_doc: str) -> str:
    accession_clean = accession.replace("-", "")
    cik_int = str(int(cik))
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_clean}/{primary_doc}"


def submission_evidence(symbol: str, cik: str, payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    recent = payload.get("filings", {}).get("recent", {})
    if not isinstance(recent, dict):
        return []
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    rows = []
    for index, form in enumerate(forms):
        if form not in RECENT_FILING_FORMS:
            continue
        if len(rows) >= 6:
            break
        accession = accessions[index] if index < len(accessions) else ""
        primary_doc = primary_docs[index] if index < len(primary_docs) else ""
        filed = filing_dates[index] if index < len(filing_dates) else ""
        report = report_dates[index] if index < len(report_dates) else ""
        url = filing_url(cik, accession, primary_doc) if accession and primary_doc else ""
        rows.append(
            {
                "run_id": None,
                "symbol": symbol,
                "evidence_type": "sec_filing",
                "source_name": "SEC EDGAR submissions API",
                "source_type": "SEC filing",
                "source_url": url,
                "provider_endpoint": "submissions",
                "provider_id": accession,
                "source_timestamp": filed,
                "title": f"{symbol} {form} filed {filed}",
                "summary": f"{form} filing for report date {report or 'n/a'} filed on {filed}.",
                "raw_text_ref": "",
                "confidence": "high",
                "corroboration_status": "primary_source",
                "user_feedback": "",
            }
        )
    return rows


def latest_fact_value(fact: Mapping[str, object]) -> tuple[str, str, str]:
    units = fact.get("units", {})
    if not isinstance(units, dict):
        return "", "", ""
    candidates = []
    for rows in units.values():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("val") not in (None, ""):
                candidates.append(row)
    if not candidates:
        return "", "", ""
    candidates.sort(key=lambda row: str(row.get("end", "")), reverse=True)
    latest = candidates[0]
    return str(latest.get("val", "")), str(latest.get("end", "")), str(latest.get("form", ""))


def companyfacts_evidence(symbol: str, payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    facts = payload.get("facts", {}).get("us-gaap", {})
    if not isinstance(facts, dict):
        return []
    rows = []
    for concept, label in FACT_CONCEPTS.items():
        fact = facts.get(concept)
        if not isinstance(fact, dict):
            continue
        value, period_end, form = latest_fact_value(fact)
        if not value:
            continue
        rows.append(
            {
                "run_id": None,
                "symbol": symbol,
                "evidence_type": "sec_company_fact",
                "source_name": "SEC EDGAR companyfacts API",
                "source_type": "SEC XBRL facts",
                "source_url": "",
                "provider_endpoint": "companyfacts",
                "provider_id": f"{symbol}-{concept}-{period_end}",
                "source_timestamp": period_end,
                "title": f"{symbol} {label}",
                "summary": f"{label}: {value} for period ending {period_end} from {form}.",
                "raw_text_ref": "",
                "confidence": "high",
                "corroboration_status": "primary_source",
                "user_feedback": "",
            }
        )
    return rows


def ingest_symbol(
    symbol: str,
    ticker_map: dict[str, CikMapping],
    user_agent: str,
    subject: SecCoverageSubject | None = None,
) -> tuple[int, list[dict[str, object]]]:
    subject = subject or SecCoverageSubject(symbol=symbol)
    coverage = summarize_symbol_coverage(
        subject,
        ticker_map,
        fact_concepts=tuple(FACT_CONCEPTS),
    )
    if coverage.coverage_status in {"not_applicable", "missing_cik", "foreign_or_adr_unmapped", "ambiguous_cik"}:
        return 0, provider_status_rows(coverage)

    mapping = ticker_map[symbol]
    cik = mapping.cik
    upsert_company_identifier(symbol, cik, mapping.company_name)
    evidence = []

    submissions_url = f"{SEC_SUBMISSIONS_BASE}/CIK{cik}.json"
    submissions_status, submissions_payload, submissions_message = sec_get_json(submissions_url, user_agent)
    record_provider_payload("SEC EDGAR", "submissions", symbol, submissions_status, submissions_message)
    if submissions_status == "ok":
        evidence.extend(submission_evidence(symbol, cik, submissions_payload))
    time.sleep(0.12)

    facts_url = f"{SEC_FACTS_BASE}/CIK{cik}.json"
    facts_status, facts_payload, facts_message = sec_get_json(facts_url, user_agent)
    record_provider_payload("SEC EDGAR", "companyfacts", symbol, facts_status, facts_message)
    if facts_status == "ok":
        evidence.extend(companyfacts_evidence(symbol, facts_payload))

    coverage = summarize_symbol_coverage(
        subject,
        ticker_map,
        submissions=SecEndpointResult(submissions_status, submissions_message, submissions_payload),
        companyfacts=SecEndpointResult(facts_status, facts_message, facts_payload),
        fact_concepts=tuple(FACT_CONCEPTS),
        latest_successful_sec_refresh=(
            datetime.now().isoformat(timespec="seconds")
            if submissions_status == "ok" or facts_status == "ok"
            else ""
        ),
    )
    inserted = record_research_evidence(evidence)
    return inserted, provider_status_rows(coverage)


def main() -> int:
    load_env()
    user_agent = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    if len(sys.argv) > 1:
        subjects = [SecCoverageSubject(symbol=symbol.upper()) for symbol in sys.argv[1:]]
    else:
        subjects = subjects_from_research()
    ticker_map = load_ticker_map(user_agent)

    total_inserted = 0
    all_status = []
    for subject in subjects:
        inserted, status_rows = ingest_symbol(subject.symbol, ticker_map, user_agent, subject=subject)
        total_inserted += inserted
        all_status.extend(status_rows)
        status_text = ", ".join(f"{row['field_name']}={row['status']}" for row in status_rows)
        print(f"{subject.symbol}: inserted_evidence={inserted}; {status_text}")
        time.sleep(0.12)

    gaps = sum(1 for row in all_status if row["status"] != "ok")
    run_id = record_provider_run(
        "SEC EDGAR",
        "ok" if all_status else "failed",
        f"symbols={len(subjects)}; inserted_evidence={total_inserted}; gaps={gaps}",
        all_status,
    )
    print(f"Recorded SEC provider run {run_id} with {gaps} gaps")
    return 0 if all_status else 1


if __name__ == "__main__":
    sys.exit(main())
