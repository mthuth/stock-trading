"""Review-only data maintenance backlog helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Mapping

from stock_trading.provider_gap_status import EXPECTED, INFORMATIONAL, NON_OPERATING_COMPANY, normalize_provider_status


REVIEW_ONLY_NOTE = (
    "Review-only data maintenance backlog. Work requests do not change scores, "
    "recommendation labels, targets, target confidence, decision-safety rules, "
    "allocation formulas, provider API behavior, broker behavior, or trading."
)
PRIORITIES = ("P0 blocker", "P1 high", "P2 medium", "P3 low")
STATUSES = ("proposed", "accepted", "deferred", "resolved")
RECOMMENDED_ACTIONS = (
    "fix_config",
    "implement_source",
    "improve_parser",
    "mark_expected_gap",
    "add_fallback",
    "paid_provider_decision",
    "ignore_for_now",
)
ETF_SYMBOLS = {"QQQM", "VGT", "SMH"}
MISSING_PRICE_FIELDS = {"current_price", "price", "quote"}
TARGET_FIELDS = {"analyst_target", "target_price", "price_target", "analyst targets", "analyst target"}
ETF_EXPECTED_FIELDS = {
    "analyst_target",
    "analyst_targets",
    "target_price",
    "price_target",
    "cik",
    "cik_mapping",
    "companyfacts",
    "official_ir",
    "official_ir_url",
    "official_ir_page",
    "company_profile",
    "company_news",
    "earnings_transcripts",
    "transcripts",
}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def token(value: object, default: str = "") -> str:
    return text(value, default).lower().replace("-", "_").replace(" ", "_")


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,;|]", value) if part.strip()]
    return [] if value in (None, "") else [value]


def clean_list(values: Iterable[object]) -> list[str]:
    return sorted({text(value) for value in values if text(value)})


def symbol_list(value: object) -> list[str]:
    symbols = [text(item).upper() for item in as_list(value)]
    return clean_list(symbols)


def source_list(value: object) -> list[str]:
    return clean_list(as_list(value))


def safe_int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def is_truthy(value: object) -> bool:
    return token(value) in {"1", "true", "yes", "y", "top_5", "capital_deployment_candidate"}


def stable_digest(*parts: object) -> str:
    payload = json.dumps([part for part in parts], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def work_request(
    *,
    title: str,
    root_cause: str,
    affected_symbols: Iterable[object] = (),
    affected_sources: Iterable[object] = (),
    priority: str,
    decision_impact: str,
    recommended_action: str,
    acceptance_criteria: Iterable[str],
    source_refs: Iterable[object] = (),
    status: str = "proposed",
) -> dict[str, object]:
    action = recommended_action if recommended_action in RECOMMENDED_ACTIONS else "ignore_for_now"
    normalized_priority = priority if priority in PRIORITIES else "P2 medium"
    normalized_status = status if status in STATUSES else "proposed"
    symbols = symbol_list(list(affected_symbols))
    sources = source_list(list(affected_sources))
    refs = clean_list(source_refs)
    criteria = clean_list(acceptance_criteria)
    branch_slug = re.sub(r"[^a-z0-9]+", "-", f"{action}-{root_cause}")[:48].strip("-")
    request = {
        "work_request_id": stable_digest(title, root_cause, symbols, sources, action),
        "title": title,
        "root_cause": root_cause,
        "affected_symbols": symbols,
        "affected_sources": sources,
        "priority": normalized_priority,
        "decision_impact": decision_impact,
        "recommended_action": action,
        "codex_branch_suggestion": f"codex/data-maintenance-{branch_slug or 'work'}",
        "acceptance_criteria": criteria,
        "source_refs": refs,
        "status": normalized_status,
        "review_only": True,
        "notes": REVIEW_ONLY_NOTE,
    }
    return request


def request_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        text(row.get("root_cause")),
        text(row.get("recommended_action")),
        text(row.get("title")),
    )


def priority_rank(priority: object) -> int:
    try:
        return PRIORITIES.index(text(priority))
    except ValueError:
        return len(PRIORITIES)


def merge_requests(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        key = request_key(row)
        current = grouped.get(key)
        if current is None:
            grouped[key] = dict(row)
            continue
        current["affected_symbols"] = symbol_list([*as_list(current.get("affected_symbols")), *as_list(row.get("affected_symbols"))])
        current["affected_sources"] = source_list([*as_list(current.get("affected_sources")), *as_list(row.get("affected_sources"))])
        current["source_refs"] = clean_list([*as_list(current.get("source_refs")), *as_list(row.get("source_refs"))])
        current["acceptance_criteria"] = clean_list(
            [*as_list(current.get("acceptance_criteria")), *as_list(row.get("acceptance_criteria"))]
        )
        if priority_rank(row.get("priority")) < priority_rank(current.get("priority")):
            current["priority"] = row.get("priority")
        current["work_request_id"] = stable_digest(
            current.get("title"),
            current.get("root_cause"),
            current.get("affected_symbols"),
            current.get("affected_sources"),
            current.get("recommended_action"),
        )
    return sorted(
        grouped.values(),
        key=lambda item: (
            priority_rank(item.get("priority")),
            text(item.get("recommended_action")),
            text(item.get("title")),
            ",".join(as_list(item.get("affected_symbols"))),
        ),
    )


def provider_gap_request(row: Mapping[str, object]) -> dict[str, object] | None:
    status = normalize_provider_status(row.get("status") or row.get("gap_status"), row.get("message") or row.get("latest_issue"))
    symbol = text(row.get("symbol")).upper()
    provider = text(row.get("provider") or row.get("source") or row.get("source_name"))
    field = text(row.get("field") or row.get("field_name") or row.get("provider_endpoint") or row.get("endpoint"))
    message = text(row.get("message") or row.get("latest_issue") or row.get("notes"))
    field_token = token(field)
    message_token = token(message)
    top_five = is_truthy(row.get("top_5") or row.get("top_five") or row.get("capital_deployment_candidate"))
    source_ref = text(row.get("source_ref") or f"provider_gap:{provider}:{symbol}:{field}")

    if field_token in MISSING_PRICE_FIELDS or "current_price" in field_token or "no_price" in message_token:
        return work_request(
            title="Restore missing current price coverage",
            root_cause="missing_current_price",
            affected_symbols=[symbol],
            affected_sources=[provider],
            priority="P0 blocker" if top_five else "P1 high",
            decision_impact="Missing current price blocks trustworthy upside, sizing, and buy-readiness review.",
            recommended_action="fix_config",
            acceptance_criteria=[
                "Affected symbols have nonzero current price with source attribution.",
                "If a live quote is unavailable, a reviewed latest-history fallback is labeled clearly.",
            ],
            source_refs=[source_ref],
        )

    if symbol in ETF_SYMBOLS and status in {EXPECTED, INFORMATIONAL, NON_OPERATING_COMPANY, "missing"} and (
        any(expected in field_token for expected in ETF_EXPECTED_FIELDS)
        or any(expected in message_token for expected in ("company", "cik", "companyfacts", "analyst", "transcript"))
    ):
        return work_request(
            title="Mark ETF operating-company data gaps as expected",
            root_cause="etf_expected_gap",
            affected_symbols=[symbol],
            affected_sources=[provider],
            priority="P3 low",
            decision_impact="ETF/non-operating-company gaps should remain visible but not inflate operating-company blocker counts.",
            recommended_action="mark_expected_gap",
            acceptance_criteria=[
                "ETF CIK/companyfacts/IR/analyst-target gaps are labeled expected or non-operating-company.",
                "Real ETF price/history gaps remain visible as actionable data gaps.",
            ],
            source_refs=[source_ref],
        )

    if any(target in field_token for target in ("analyst_target", "target_price", "price_target")) or any(
        target in message_token for target in TARGET_FIELDS
    ):
        action = "paid_provider_decision" if "paid" in message_token or "paid" in token(provider) else "add_fallback"
        return work_request(
            title="Resolve analyst target breadth gap",
            root_cause="missing_analyst_target_breadth",
            affected_symbols=[symbol],
            affected_sources=[provider],
            priority="P1 high" if top_five or token(row.get("target_confidence")) in {"low", "needs_review"} else "P2 medium",
            decision_impact="Thin analyst target breadth weakens target confidence and upside credibility.",
            recommended_action=action,
            acceptance_criteria=[
                "Operating-company target gaps are backed by provider/manual target rows or labeled low-confidence.",
                "Manual analyst targets remain labeled manual and separate from provider/model targets.",
            ],
            source_refs=[source_ref],
        )

    if status == "parser_gap":
        return work_request(
            title="Improve parser for configured source failures",
            root_cause="parser_failure",
            affected_symbols=[symbol] if symbol else [],
            affected_sources=[provider],
            priority="P2 medium",
            decision_impact="Parser failures weaken source corroboration and research synthesis.",
            recommended_action="improve_parser",
            acceptance_criteria=[
                "Parser failures are separated from access blocks and no-record states.",
                "The source captures usable headline/link metadata or a clear parser-gap reason.",
            ],
            source_refs=[source_ref],
        )

    if status == "not_implemented":
        return work_request(
            title="Implement configured source or mark it deferred",
            root_cause="not_implemented_source",
            affected_symbols=[symbol] if symbol else [],
            affected_sources=[provider],
            priority="P2 medium",
            decision_impact="Configured but unimplemented sources create recurring next-action noise.",
            recommended_action="implement_source" if "paid" not in token(provider + message) else "paid_provider_decision",
            acceptance_criteria=[
                "Source has an importer, documented deferral, or explicit paid-provider decision.",
                "Not-implemented state no longer appears as unresolved operational noise.",
            ],
            source_refs=[source_ref],
        )

    if "benchmark" in field_token or "benchmark" in message_token:
        return work_request(
            title="Resolve benchmark data gap for model trust review",
            root_cause="benchmark_data_gap",
            affected_symbols=[symbol] if symbol else [],
            affected_sources=[provider],
            priority="P2 medium",
            decision_impact="Missing benchmark data weakens model trust and excess-return evaluation.",
            recommended_action="add_fallback",
            acceptance_criteria=[
                "Benchmark rows are available for model-evaluation windows or warnings remain explicit.",
                "Missing benchmark data is not treated as zero benchmark return.",
            ],
            source_refs=[source_ref],
        )

    if status in {"blocked", "rate_limited", "missing", "stale", "error"}:
        return work_request(
            title="Review unresolved provider gap",
            root_cause=f"provider_{status}",
            affected_symbols=[symbol] if symbol else [],
            affected_sources=[provider],
            priority="P1 high" if top_five else "P2 medium",
            decision_impact="Provider gap weakens confidence or source freshness until reviewed.",
            recommended_action="add_fallback" if status in {"blocked", "rate_limited"} else "fix_config",
            acceptance_criteria=[
                "Provider gap has a clear source-specific next action or expected/deferred label.",
                "Dashboard/reports continue to show the gap until it is resolved or expected.",
            ],
            source_refs=[source_ref],
        )
    return None


def source_health_request(row: Mapping[str, object]) -> dict[str, object] | None:
    source = text(row.get("source_name") or row.get("source") or row.get("provider"))
    label = token(row.get("quality_label") or row.get("label") or row.get("source_health_status"))
    total_records = safe_int(row.get("total_evidence") or row.get("records") or row.get("record_count") or 0)
    source_ref = text(row.get("source_ref") or f"source_health:{source}")
    configured_useful = token(row.get("configured_as") or row.get("source_tier") or row.get("planned_use"))

    if label == "parser_gap":
        return work_request(
            title="Improve parser for configured source failures",
            root_cause="parser_failure",
            affected_sources=[source],
            priority="P2 medium",
            decision_impact="Parser gaps prevent configured sources from contributing useful evidence.",
            recommended_action="improve_parser",
            acceptance_criteria=[
                "Parser produces usable source rows or records explicit parser-gap reasons.",
                "Zero usable evidence is not confused with bearish thesis evidence.",
            ],
            source_refs=[source_ref],
        )
    if total_records == 0 and ("useful" in configured_useful or "tier_1" in configured_useful or token(row.get("expected_useful")) == "true"):
        return work_request(
            title="Activate zero-record configured source",
            root_cause="zero_record_source",
            affected_sources=[source],
            priority="P2 medium",
            decision_impact="Configured useful sources with zero records add noise but no evidence.",
            recommended_action="implement_source",
            acceptance_criteria=[
                "Source produces at least one fixture-backed/local record or is marked deferred.",
                "Backlog notes explain whether the issue is parser, feed URL, access, or configuration.",
            ],
            source_refs=[source_ref],
        )
    return None


def research_source_request(row: Mapping[str, object]) -> dict[str, object] | None:
    source = text(row.get("source_name"))
    implementation_status = token(row.get("implementation_status"))
    access_model = token(row.get("access_model"))
    next_step = text(row.get("next_step"))
    if implementation_status == "not_implemented":
        action = "paid_provider_decision" if "paid" in access_model else "implement_source"
        return work_request(
            title="Implement configured source or mark it deferred",
            root_cause="not_implemented_source",
            affected_sources=[source],
            priority="P2 medium",
            decision_impact="Configured source cannot improve evidence coverage until implementation or deferral is explicit.",
            recommended_action=action,
            acceptance_criteria=[
                next_step or "Source has a documented implementation, paid-provider decision, or deferral.",
                "No live provider calls are added without explicit follow-up scope.",
            ],
            source_refs=[f"config/research_source_integrations.csv:{source}"],
        )
    if implementation_status in {"tracked_source_needs_feed_verification", "configured_public_source"} and not text(row.get("feed_url")):
        return work_request(
            title="Verify feed URL for configured public source",
            root_cause="missing_feed_url",
            affected_sources=[source],
            priority="P3 low",
            decision_impact="Missing feed URL may cause zero-record or parser-gap source behavior.",
            recommended_action="fix_config",
            acceptance_criteria=[
                "Source has a stable feed/archive URL or is documented as page-link only.",
                "No source is treated as implemented solely because it appears in config.",
            ],
            source_refs=[f"config/research_source_integrations.csv:{source}"],
        )
    return None


def ingestion_plan_request(row: Mapping[str, object]) -> dict[str, object] | None:
    source = text(row.get("source_name") or row.get("provider"))
    status = normalize_provider_status(row.get("status") or row.get("latest_status"), row.get("latest_issue") or row.get("message"))
    records = safe_int(row.get("records") or row.get("total_evidence") or 0)
    source_ref = text(row.get("source_ref") or f"ingestion_plan:{source}")
    if status == "not_implemented":
        return work_request(
            title="Implement configured source or mark it deferred",
            root_cause="not_implemented_source",
            affected_sources=[source],
            priority="P2 medium",
            decision_impact="Ingestion plan cannot refresh a source that has no implementation.",
            recommended_action="implement_source",
            acceptance_criteria=["Source has a runnable command, documented deferral, or paid-provider decision."],
            source_refs=[source_ref],
        )
    if records == 0 and status in {"ok", "missing", "error", "parser_gap"}:
        return work_request(
            title="Activate zero-record configured source",
            root_cause="zero_record_source",
            affected_sources=[source],
            priority="P2 medium",
            decision_impact="Refresh plan sees no usable records from a configured source.",
            recommended_action="improve_parser" if status == "parser_gap" else "fix_config",
            acceptance_criteria=["Source emits usable local rows or gets a clear expected/deferred label."],
            source_refs=[source_ref],
        )
    return None


def coverage_audit_requests(row: Mapping[str, object]) -> list[dict[str, object]]:
    symbol = text(row.get("symbol")).upper()
    company = text(row.get("company"))
    refs = [text(row.get("source_ref") or f"reports/provider-coverage-audit.csv:{symbol}")]
    requests: list[dict[str, object]] = []

    if token(row.get("current_price_available")) == "no":
        requests.append(
            provider_gap_request(
                {
                    "symbol": symbol,
                    "provider": text(row.get("current_price_source") or "Configured current price"),
                    "field_name": "current_price",
                    "status": "missing",
                    "message": "Missing current price in provider coverage audit",
                    "source_ref": refs[0],
                }
            )
        )

    if token(row.get("analyst_target_available")) == "no":
        requests.append(
            provider_gap_request(
                {
                    "symbol": symbol,
                    "provider": "Analyst target providers",
                    "field_name": "analyst_target",
                    "status": "missing",
                    "message": "No analyst target source row available",
                    "source_ref": refs[0],
                }
            )
        )

    if token(row.get("companyfacts_available")) == "no":
        if symbol in ETF_SYMBOLS:
            requests.append(
                provider_gap_request(
                    {
                        "symbol": symbol,
                        "provider": "SEC EDGAR",
                        "field_name": "companyfacts",
                        "status": "missing",
                        "message": "ETF has no SEC companyfacts coverage",
                        "source_ref": refs[0],
                    }
                )
            )
        else:
            requests.append(
                work_request(
                    title="Add foreign-issuer or companyfacts fallback",
                    root_cause="missing_companyfacts",
                    affected_symbols=[symbol],
                    affected_sources=["SEC EDGAR", company],
                    priority="P1 high",
                    decision_impact="Missing companyfacts-equivalent evidence weakens fundamental review for operating companies.",
                    recommended_action="add_fallback",
                    acceptance_criteria=[
                        "Operating-company companyfacts gaps have SEC, foreign-issuer, official IR, or provider-fundamentals fallback evidence.",
                        "Fallback evidence remains source-attributed and does not change target-blending math.",
                    ],
                    source_refs=refs,
                )
            )

    if token(row.get("sec_cik_mapping_available")) == "no":
        requests.append(
            provider_gap_request(
                {
                    "symbol": symbol,
                    "provider": "SEC EDGAR",
                    "field_name": "cik_mapping",
                    "status": "missing",
                    "message": "No SEC CIK mapping found",
                    "source_ref": refs[0],
                }
            )
        )

    if token(row.get("official_ir_coverage_available")) == "no":
        requests.append(
            provider_gap_request(
                {
                    "symbol": symbol,
                    "provider": "Company investor relations",
                    "field_name": "official_ir_url",
                    "status": "missing",
                    "message": "No official company IR URL is configured",
                    "source_ref": refs[0],
                }
            )
        )

    summary = text(row.get("unresolved_provider_gap_summary"))
    if "official_ir_page=error" in summary:
        requests.append(
            work_request(
                title="Improve parser for configured source failures",
                root_cause="parser_failure",
                affected_symbols=[symbol],
                affected_sources=["Company investor relations"],
                priority="P2 medium",
                decision_impact="IR parser failures weaken primary-source corroboration.",
                recommended_action="improve_parser",
                acceptance_criteria=[
                    "IR parser distinguishes blocked access, parser gap, page-link capture, and full extraction.",
                    "Official IR failures are actionable by symbol/source.",
                ],
                source_refs=refs,
            )
        )
    if "earnings_transcripts=error" in summary or "stock_news=error" in summary:
        requests.append(
            work_request(
                title="Decide paid provider strategy for transcripts and news",
                root_cause="paid_provider_gap",
                affected_symbols=[symbol],
                affected_sources=["FMP"],
                priority="P2 medium",
                decision_impact="Blocked transcript/news providers weaken catalyst review and management-commentary coverage.",
                recommended_action="paid_provider_decision",
                acceptance_criteria=[
                    "Paid transcript/news access has an explicit approve/defer decision.",
                    "Official IR, SEC, and public-source fallbacks remain available before any paid-provider work.",
                ],
                source_refs=refs,
            )
        )
    return [request for request in requests if request]


def action_plan_requests(text_blob: str) -> list[dict[str, object]]:
    content = text_blob or ""
    requests: list[dict[str, object]] = []
    if "Missing Current Price" in content:
        symbols = re.findall(r"`([A-Z]{2,5})`", content.split("### Missing Current Price", 1)[1].split("###", 1)[0])
        requests.append(
            work_request(
                title="Restore missing current price coverage",
                root_cause="missing_current_price",
                affected_symbols=symbols,
                affected_sources=["FMP/Alpha Vantage"],
                priority="P0 blocker",
                decision_impact="Missing current price blocks trustworthy upside, sizing, and buy-readiness review.",
                recommended_action="fix_config",
                acceptance_criteria=[
                    "Each affected symbol has nonzero current price with source attribution.",
                    "Missing price appears as reliability blocker, not bearish thesis evidence.",
                ],
                source_refs=["reports/provider-gap-action-plan.md#missing-current-price"],
            )
        )
    if "Missing Analyst Target Coverage" in content:
        section = content.split("### Missing Analyst Target Coverage", 1)[1].split("###", 1)[0]
        operating_section = section
        if "Affected operating-company symbols:" in operating_section:
            operating_section = operating_section.split("Affected operating-company symbols:", 1)[1]
        if "ETF symbols to handle as expected gaps:" in operating_section:
            operating_section = operating_section.split("ETF symbols to handle as expected gaps:", 1)[0]
        symbols = re.findall(r"`([A-Z]{2,5})`", operating_section)
        requests.append(
            work_request(
                title="Resolve analyst target breadth gap",
                root_cause="missing_analyst_target_breadth",
                affected_symbols=symbols,
                affected_sources=["Analyst target providers"],
                priority="P1 high",
                decision_impact="Missing analyst targets weaken target confidence and upside credibility.",
                recommended_action="paid_provider_decision" if "Paid provider decision" in section else "add_fallback",
                acceptance_criteria=[
                    "Operating-company target gaps are backed by provider/manual rows or labeled low-confidence.",
                    "ETF target gaps are marked expected/non-operating-company.",
                ],
                source_refs=["reports/provider-gap-action-plan.md#missing-analyst-target-coverage"],
            )
        )
    if "Official IR Parser Errors" in content:
        requests.append(
            work_request(
                title="Improve parser for configured source failures",
                root_cause="parser_failure",
                affected_sources=["Company investor relations"],
                priority="P2 medium",
                decision_impact="IR parser failures weaken primary-source corroboration.",
                recommended_action="improve_parser",
                acceptance_criteria=[
                    "IR parser distinguishes blocked access, parser gap, page-link capture, and full extraction.",
                    "Official IR failures are actionable by symbol/source.",
                ],
                source_refs=["reports/provider-gap-action-plan.md#official-ir-parser-errors"],
            )
        )
    if "FMP Transcript/News Errors" in content:
        requests.append(
            work_request(
                title="Decide paid provider strategy for transcripts and news",
                root_cause="paid_provider_gap",
                affected_symbols=[],
                affected_sources=["FMP"],
                priority="P2 medium",
                decision_impact="Blocked transcript/news providers weaken catalyst review and management-commentary coverage.",
                recommended_action="paid_provider_decision",
                acceptance_criteria=[
                    "Paid transcript/news access has an explicit approve/defer decision.",
                    "Official IR, SEC, and public-source fallbacks remain available before any paid-provider work.",
                ],
                source_refs=["reports/provider-gap-action-plan.md#fmp-transcript-news-errors"],
            )
        )
    if "ETF/Non-Operating-Company Expected Gaps" in content:
        requests.append(
            work_request(
                title="Mark ETF operating-company data gaps as expected",
                root_cause="etf_expected_gap",
                affected_symbols=["QQQM", "VGT", "SMH"],
                affected_sources=["SEC EDGAR", "Company investor relations", "Analyst target providers"],
                priority="P3 low",
                decision_impact="ETF/non-operating-company gaps should remain visible but not inflate operating-company blocker counts.",
                recommended_action="mark_expected_gap",
                acceptance_criteria=[
                    "ETF CIK/companyfacts/IR/analyst-target gaps are labeled expected or non-operating-company.",
                    "Real ETF price/history gaps remain visible as actionable data gaps.",
                ],
                source_refs=["reports/provider-gap-action-plan.md#etf-non-operating-company-expected-gaps"],
            )
        )
    return requests


def generate_data_maintenance_backlog(
    *,
    provider_gaps: Iterable[Mapping[str, object]] = (),
    source_health_rows: Iterable[Mapping[str, object]] = (),
    ingestion_plan_rows: Iterable[Mapping[str, object]] = (),
    provider_coverage_audit_rows: Iterable[Mapping[str, object]] = (),
    provider_gap_action_plan_text: str = "",
    research_source_rows: Iterable[Mapping[str, object]] = (),
    alert_rows: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for gap in provider_gaps:
        request = provider_gap_request(gap)
        if request:
            rows.append(request)
    for row in source_health_rows:
        request = source_health_request(row)
        if request:
            rows.append(request)
    for row in ingestion_plan_rows:
        request = ingestion_plan_request(row)
        if request:
            rows.append(request)
    for row in provider_coverage_audit_rows:
        rows.extend(coverage_audit_requests(row))
    for row in research_source_rows:
        request = research_source_request(row)
        if request:
            rows.append(request)
    for row in alert_rows:
        if token(row.get("review_area")) == "provider_data" or "data" in token(row.get("alert_type")):
            request = provider_gap_request({**row, "source_ref": text(row.get("alert_id") or row.get("id"))})
            if request:
                rows.append(request)
    rows.extend(action_plan_requests(provider_gap_action_plan_text))
    merged = merge_requests(rows)
    for index, row in enumerate(merged, start=1):
        row["work_request_id"] = f"DMW-{index:03d}"
    return {
        "work_requests": merged,
        "summary": {
            "total_work_requests": len(merged),
            "by_priority": count_by(merged, "priority"),
            "by_action": count_by(merged, "recommended_action"),
        },
        "review_only": True,
        "github_issues_created": False,
        "notes": REVIEW_ONLY_NOTE,
    }


def count_by(rows: Iterable[Mapping[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = text(row.get(key), "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def render_backlog_markdown(backlog: Mapping[str, object]) -> str:
    rows = [dict(row) for row in backlog.get("work_requests", []) if isinstance(row, Mapping)]
    lines = [
        "# Data Maintenance Backlog",
        "",
        "Generated from local provider/source gap inputs. This backlog is review-only and does not create GitHub issues.",
        "",
        f"- Total work requests: {len(rows)}",
        f"- GitHub issues created: {str(backlog.get('github_issues_created') is True).lower()}",
        "",
        "| ID | Priority | Title | Action | Symbols | Sources | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {id} | {priority} | {title} | {action} | {symbols} | {sources} | {status} |".format(
                id=text(row.get("work_request_id")),
                priority=text(row.get("priority")),
                title=text(row.get("title")).replace("|", "/"),
                action=text(row.get("recommended_action")),
                symbols=", ".join(as_list(row.get("affected_symbols"))) or "-",
                sources=", ".join(as_list(row.get("affected_sources"))) or "-",
                status=text(row.get("status")),
            )
        )
    lines.extend(["", REVIEW_ONLY_NOTE, ""])
    return "\n".join(lines)


def render_work_requests_markdown(backlog: Mapping[str, object]) -> str:
    rows = [dict(row) for row in backlog.get("work_requests", []) if isinstance(row, Mapping)]
    lines = [
        "# Data Gap Work Requests",
        "",
        "Codex-ready work requests generated from local data-maintenance signals. These are docs/backlog items only; no GitHub issues were created.",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"## {text(row.get('work_request_id'))}: {text(row.get('title'))}",
                "",
                f"- Priority: {text(row.get('priority'))}",
                f"- Status: {text(row.get('status'))}",
                f"- Recommended action: {text(row.get('recommended_action'))}",
                f"- Suggested branch: `{text(row.get('codex_branch_suggestion'))}`",
                f"- Root cause: {text(row.get('root_cause'))}",
                f"- Decision impact: {text(row.get('decision_impact'))}",
                f"- Affected symbols: {', '.join(as_list(row.get('affected_symbols'))) or '-'}",
                f"- Affected sources: {', '.join(as_list(row.get('affected_sources'))) or '-'}",
                f"- Source refs: {', '.join(as_list(row.get('source_refs'))) or '-'}",
                "",
                "Acceptance criteria:",
            ]
        )
        for criterion in as_list(row.get("acceptance_criteria")):
            lines.append(f"- {criterion}")
        lines.extend(["", "Codex prompt seed:", ""])
        lines.append(
            f"> Create `{text(row.get('codex_branch_suggestion'))}` to {text(row.get('recommended_action'))} for {text(row.get('root_cause'))}. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`."
        )
        lines.append("")
    lines.extend([REVIEW_ONLY_NOTE, ""])
    return "\n".join(lines)


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_backlog_docs(backlog: Mapping[str, object], output_dir: str | Path) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    backlog_path = directory / "DATA_MAINTENANCE_BACKLOG.md"
    requests_path = directory / "DATA_GAP_WORK_REQUESTS.md"
    backlog_path.write_text(render_backlog_markdown(backlog), encoding="utf-8")
    requests_path.write_text(render_work_requests_markdown(backlog), encoding="utf-8")
    return backlog_path, requests_path


__all__ = [
    "REVIEW_ONLY_NOTE",
    "generate_data_maintenance_backlog",
    "read_csv_rows",
    "render_backlog_markdown",
    "render_work_requests_markdown",
    "write_backlog_docs",
]
