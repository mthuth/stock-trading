#!/usr/bin/env python3
"""SEC coverage checks for approved-universe symbols."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime


SEC_PROVIDER = "SEC EDGAR"
STALE_FILING_AFTER_DAYS = 190
RECENT_FILING_FORMS = {"10-K", "10-Q", "8-K", "20-F", "6-K"}
FOREIGN_OR_ADR_SYMBOLS = {"ARM", "ASML", "TSM"}
FOREIGN_OR_ADR_COMPANY_HINTS = ("adr", "taiwan", "asml", "arm holdings")


@dataclass(frozen=True)
class SecCoverageSubject:
    symbol: str
    company_name: str = ""
    category: str = ""
    sleeve: str = ""
    trade_type: str = ""


@dataclass(frozen=True)
class CikMapping:
    cik: str = ""
    company_name: str = ""
    exchange: str = ""
    ambiguous: bool = False
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecEndpointResult:
    status: str = "not_checked"
    message: str = ""
    payload: object | None = None


@dataclass(frozen=True)
class SecCoverageRecord:
    symbol: str
    company_name: str
    security_type: str
    cik: str = ""
    submissions_status: str = "not_checked"
    companyfacts_status: str = "not_checked"
    latest_filing_date: str = ""
    latest_successful_sec_refresh: str = ""
    coverage_status: str = "needs_attention"
    issue: str = ""
    gap_field: str = ""
    gap_status: str = ""
    messages: dict[str, str] = field(default_factory=dict)

    @property
    def needs_attention(self) -> bool:
        return self.gap_status not in {"", "ok"}


def subject_from_research_row(row: Mapping[str, object]) -> SecCoverageSubject:
    return SecCoverageSubject(
        symbol=str(row.get("symbol", "")).strip().upper(),
        company_name=str(row.get("company") or row.get("company_name") or "").strip(),
        category=str(row.get("category", "")).strip(),
        sleeve=str(row.get("sleeve", "")).strip(),
        trade_type=str(row.get("trade_type", "")).strip(),
    )


def security_type(subject: SecCoverageSubject) -> str:
    tokens = " ".join([subject.category, subject.sleeve, subject.trade_type, subject.company_name]).lower()
    if "etf" in tokens:
        return "non_operating"
    if subject.symbol.upper() in FOREIGN_OR_ADR_SYMBOLS or any(hint in tokens for hint in FOREIGN_OR_ADR_COMPANY_HINTS):
        return "foreign_or_adr"
    return "operating_company"


def normalize_sec_ticker_map(payload: object) -> dict[str, CikMapping]:
    if not isinstance(payload, Mapping):
        return {}
    by_symbol: dict[str, list[CikMapping]] = {}
    for item in payload.values():
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker", "")).strip().upper()
        cik_value = str(item.get("cik_str", "")).strip()
        if not ticker or not cik_value:
            continue
        cik = cik_value.zfill(10)
        by_symbol.setdefault(ticker, []).append(
            CikMapping(
                cik=cik,
                company_name=str(item.get("title", "")).strip(),
                exchange=str(item.get("exchange", "")).strip(),
            )
        )
    normalized: dict[str, CikMapping] = {}
    for symbol, mappings in by_symbol.items():
        unique = sorted({mapping.cik for mapping in mappings})
        if len(unique) == 1:
            normalized[symbol] = mappings[0]
        else:
            normalized[symbol] = CikMapping(
                ambiguous=True,
                candidates=tuple(unique),
                company_name="; ".join(sorted({mapping.company_name for mapping in mappings if mapping.company_name})),
            )
    return normalized


def parse_iso_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def latest_submission_filing_date(payload: object, forms: set[str] | None = None) -> str:
    if not isinstance(payload, Mapping):
        return ""
    recent = payload.get("filings", {})
    if isinstance(recent, Mapping):
        recent = recent.get("recent", {})
    if not isinstance(recent, Mapping):
        return ""
    accepted_forms = forms or RECENT_FILING_FORMS
    filing_forms = list(recent.get("form", []) or [])
    filing_dates = list(recent.get("filingDate", []) or [])
    dates: list[date] = []
    for index, form in enumerate(filing_forms):
        if str(form) not in accepted_forms or index >= len(filing_dates):
            continue
        parsed = parse_iso_date(filing_dates[index])
        if parsed:
            dates.append(parsed)
    return max(dates).isoformat() if dates else ""


def companyfacts_has_coverage(payload: object, fact_concepts: Sequence[str]) -> bool:
    if not isinstance(payload, Mapping):
        return False
    facts = payload.get("facts", {})
    if not isinstance(facts, Mapping):
        return False
    us_gaap = facts.get("us-gaap", {})
    if not isinstance(us_gaap, Mapping):
        return False
    for concept in fact_concepts:
        fact = us_gaap.get(concept)
        if not isinstance(fact, Mapping):
            continue
        units = fact.get("units", {})
        if not isinstance(units, Mapping):
            continue
        for rows in units.values():
            if isinstance(rows, list) and any(isinstance(row, Mapping) and row.get("val") not in (None, "") for row in rows):
                return True
    return False


def freshness_status(latest_filing_date: str, as_of: date, stale_after_days: int = STALE_FILING_AFTER_DAYS) -> str:
    parsed = parse_iso_date(latest_filing_date)
    if not parsed:
        return "missing"
    return "stale" if (as_of - parsed).days > stale_after_days else "ok"


def endpoint_coverage_status(
    endpoint: str,
    result: SecEndpointResult,
    latest_filing_date: str = "",
    has_companyfacts: bool = False,
    as_of: date | None = None,
) -> tuple[str, str]:
    if result.status != "ok":
        message = result.message or f"{endpoint} endpoint did not refresh"
        normalized_status = "rate_limited" if "429" in message or "rate limit" in message.lower() else result.status
        return normalized_status, message
    if endpoint == "submissions":
        status = freshness_status(latest_filing_date, as_of or date.today())
        if status == "missing":
            return "missing", "No recent SEC submissions filings were found"
        if status == "stale":
            return "stale", f"Latest SEC filing is stale: {latest_filing_date}"
        return "ok", f"Latest SEC filing date {latest_filing_date}"
    if endpoint == "companyfacts":
        if not has_companyfacts:
            return "missing", "SEC companyfacts returned no supported fact concepts"
        return "ok", "SEC companyfacts coverage found"
    return result.status, result.message


def summarize_symbol_coverage(
    subject: SecCoverageSubject,
    ticker_map: Mapping[str, CikMapping],
    submissions: SecEndpointResult | None = None,
    companyfacts: SecEndpointResult | None = None,
    fact_concepts: Sequence[str] = (),
    latest_successful_sec_refresh: str = "",
    as_of: date | None = None,
) -> SecCoverageRecord:
    symbol = subject.symbol.upper()
    type_label = security_type(subject)
    company_name = subject.company_name
    messages: dict[str, str] = {}
    if type_label == "non_operating":
        return SecCoverageRecord(
            symbol=symbol,
            company_name=company_name,
            security_type=type_label,
            submissions_status="not_applicable",
            companyfacts_status="not_applicable",
            latest_successful_sec_refresh=latest_successful_sec_refresh,
            coverage_status="not_applicable",
            issue="ETF/non-operating symbol; SEC company filing coverage is not required.",
        )

    mapping = ticker_map.get(symbol)
    if mapping and mapping.ambiguous:
        return SecCoverageRecord(
            symbol=symbol,
            company_name=company_name or mapping.company_name,
            security_type=type_label,
            latest_successful_sec_refresh=latest_successful_sec_refresh,
            coverage_status="ambiguous_cik",
            issue=f"Ambiguous SEC CIK mapping candidates: {', '.join(mapping.candidates)}.",
            gap_field="cik_mapping",
            gap_status="ambiguous",
        )
    if not mapping or not mapping.cik:
        status = "foreign_or_adr_unmapped" if type_label == "foreign_or_adr" else "missing_cik"
        issue = (
            "Foreign/ADR symbol has no SEC CIK mapping; confirm SEC availability or track primary-source equivalent."
            if type_label == "foreign_or_adr"
            else "No SEC ticker CIK mapping found."
        )
        return SecCoverageRecord(
            symbol=symbol,
            company_name=company_name,
            security_type=type_label,
            latest_successful_sec_refresh=latest_successful_sec_refresh,
            coverage_status=status,
            issue=issue,
            gap_field="cik_mapping",
            gap_status="missing",
        )

    submission_result = submissions or SecEndpointResult()
    fact_result = companyfacts or SecEndpointResult()
    latest_filing = latest_submission_filing_date(submission_result.payload)
    facts_available = companyfacts_has_coverage(fact_result.payload, fact_concepts)
    submission_status, submission_message = endpoint_coverage_status(
        "submissions",
        submission_result,
        latest_filing_date=latest_filing,
        as_of=as_of,
    )
    fact_status, fact_message = endpoint_coverage_status(
        "companyfacts",
        fact_result,
        has_companyfacts=facts_available,
    )
    messages["submissions"] = submission_message
    messages["companyfacts"] = fact_message

    gap_field = ""
    gap_status = ""
    issue = ""
    if submission_status != "ok":
        gap_field = "submissions"
        gap_status = submission_status
        issue = submission_message
    elif fact_status != "ok":
        gap_field = "companyfacts"
        gap_status = fact_status
        issue = fact_message

    coverage_status = "covered" if not gap_status else "needs_attention"
    return SecCoverageRecord(
        symbol=symbol,
        company_name=company_name or mapping.company_name,
        security_type=type_label,
        cik=mapping.cik,
        submissions_status=submission_status,
        companyfacts_status=fact_status,
        latest_filing_date=latest_filing,
        latest_successful_sec_refresh=latest_successful_sec_refresh,
        coverage_status=coverage_status,
        issue=issue,
        gap_field=gap_field,
        gap_status=gap_status,
        messages=messages,
    )


def summarize_sec_coverage(
    subjects: Sequence[SecCoverageSubject],
    ticker_map: Mapping[str, CikMapping],
    submissions_by_symbol: Mapping[str, SecEndpointResult] | None = None,
    companyfacts_by_symbol: Mapping[str, SecEndpointResult] | None = None,
    fact_concepts: Sequence[str] = (),
    latest_successful_sec_refresh: str = "",
    as_of: date | None = None,
) -> list[SecCoverageRecord]:
    submissions_by_symbol = submissions_by_symbol or {}
    companyfacts_by_symbol = companyfacts_by_symbol or {}
    return [
        summarize_symbol_coverage(
            subject,
            ticker_map,
            submissions=submissions_by_symbol.get(subject.symbol),
            companyfacts=companyfacts_by_symbol.get(subject.symbol),
            fact_concepts=fact_concepts,
            latest_successful_sec_refresh=latest_successful_sec_refresh,
            as_of=as_of,
        )
        for subject in subjects
        if subject.symbol
    ]


def provider_status_rows(record: SecCoverageRecord) -> list[dict[str, object]]:
    if record.coverage_status == "not_applicable":
        return [
            {
                "symbol": record.symbol,
                "provider": SEC_PROVIDER,
                "field_name": "sec_coverage",
                "status": "ok",
                "message": record.issue,
            }
        ]
    if record.gap_field == "cik_mapping":
        return [
            {
                "symbol": record.symbol,
                "provider": SEC_PROVIDER,
                "field_name": "cik_mapping",
                "status": record.gap_status,
                "message": record.issue,
            }
        ]
    rows = []
    for field_name, status, fallback in (
        ("submissions", record.submissions_status, record.messages.get("submissions", "")),
        ("companyfacts", record.companyfacts_status, record.messages.get("companyfacts", "")),
    ):
        rows.append(
            {
                "symbol": record.symbol,
                "provider": SEC_PROVIDER,
                "field_name": field_name,
                "status": status,
                "message": fallback or record.issue,
            }
        )
    return rows
