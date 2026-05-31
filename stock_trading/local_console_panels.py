#!/usr/bin/env python3
"""Read-only local decision-console panel view models."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


GUARDRAIL_TEXT = (
    "Review-only and recommendation-only. No trades, order previews, broker writes, "
    "live provider calls, live model calls, or automatic recommendation changes."
)


def as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _panel(
    panel_id: str,
    title: str,
    *,
    status: str,
    summary: str,
    items: list[dict[str, object]] | None = None,
    warnings: list[str] | None = None,
    missing_data: bool = False,
    stale: bool = False,
) -> dict[str, object]:
    return {
        "id": panel_id,
        "title": title,
        "status": status,
        "summary": summary,
        "items": items or [],
        "warnings": warnings or [],
        "missing_data": missing_data,
        "stale": stale,
        "review_only": True,
        "recommendation_only": True,
        "guardrail": GUARDRAIL_TEXT,
    }


def _rows_from_table(table: object, limit: int = 5) -> list[dict[str, object]]:
    table_dict = as_dict(table)
    headers = [text(header) for header in as_list(table_dict.get("headers"))]
    rows = as_list(table_dict.get("rows"))
    rendered: list[dict[str, object]] = []
    for row in rows[:limit]:
        values = as_list(row)
        rendered.append({headers[index] if index < len(headers) else f"field_{index}": value for index, value in enumerate(values)})
    return rendered


def _safe_item(mapping: Mapping[str, object], keys: tuple[str, ...]) -> dict[str, object]:
    return {key: deepcopy(mapping.get(key)) for key in keys if key in mapping}


def _first_mapping(*values: object) -> dict[str, Any]:
    for value in values:
        data = as_dict(value)
        if data:
            return data
    return {}


def _string_list(value: object) -> list[str]:
    strings: list[str] = []
    for item in as_list(value):
        rendered = text(item.get("reason") or item.get("message") or item.get("status")) if isinstance(item, Mapping) else text(item)
        if rendered:
            strings.append(rendered)
    return strings


def current_decision_panel(summary: Mapping[str, object] | None) -> dict[str, object]:
    data = as_dict(summary)
    if not data:
        return _panel(
            "current_decision",
            "Current Decision",
            status="missing",
            summary="No current decision summary is available.",
            missing_data=True,
        )

    gate = as_dict(data.get("decision_gate"))
    status = text(gate.get("status") or data.get("top_action") or "review")
    safe_to_buy = gate.get("safe_to_buy")
    reasons = [text(reason) for reason in as_list(gate.get("reasons")) if text(reason)]
    warnings = reasons if safe_to_buy is False else []
    item = _safe_item(
        data,
        (
            "top_symbol",
            "top_company",
            "top_action",
            "top_score",
            "suggested_amount_text",
            "confidence",
            "data_status",
        ),
    )
    item["decision_gate_status"] = status
    item["safe_to_buy"] = bool(safe_to_buy) if safe_to_buy is not None else False
    if reasons:
        item["blocked_reasons"] = reasons
    summary_text = f"{text(data.get('top_symbol'), 'No symbol')} is the current top decision candidate."
    return _panel("current_decision", "Current Decision", status=status, summary=summary_text, items=[item], warnings=warnings)


def capital_deployment_panel(section: Mapping[str, object] | None) -> dict[str, object]:
    data = as_dict(section)
    if not data:
        return _panel(
            "capital_deployment",
            "Long-Term Capital Deployment",
            status="missing",
            summary="No long-term capital deployment review is available.",
            missing_data=True,
        )

    capital = as_dict(data.get("capital_availability"))
    candidate = as_dict(data.get("primary_candidate"))
    warnings = [text(reason) for reason in as_list(data.get("key_blockers")) if text(reason)]
    status = text(data.get("status") or capital.get("status") or "review")
    items = [
        {
            "decision_mode": text(data.get("decision_mode")),
            "question": text(data.get("question")),
            "primary_symbol": text(candidate.get("symbol")),
            "primary_action": text(candidate.get("action")),
            "decision_safety_status": text(data.get("decision_safety_status")),
            "target_confidence": text(data.get("target_confidence")),
            "deployable_amount_text": text(capital.get("deployable_amount_text")),
            "held_amount_text": text(capital.get("held_amount_text")),
            "capital_status": text(capital.get("status")),
        }
    ]
    fallback = as_dict(data.get("fallback_candidate"))
    if fallback:
        items[0]["fallback_symbol"] = text(fallback.get("symbol"))
    if text(data.get("hold_capacity_message")):
        warnings.append(text(data.get("hold_capacity_message")))
    return _panel(
        "capital_deployment",
        "Long-Term Capital Deployment",
        status=status,
        summary=text(data.get("note") or capital.get("reason") or "Capital deployment review is available."),
        items=items,
        warnings=warnings,
        missing_data=not bool(capital),
    )


def earnings_review_panel(section: Mapping[str, object] | None) -> dict[str, object]:
    data = as_dict(section)
    if not data:
        return _panel(
            "earnings_review",
            "Earnings Review",
            status="missing",
            summary="No earnings review section is available.",
            missing_data=True,
        )

    upcoming = as_list(as_dict(data.get("upcoming_earnings_queue")).get("rows"))
    recent = as_list(as_dict(data.get("recent_earnings_queue")).get("rows"))
    gaps = as_list(as_dict(data.get("provider_data_gaps")).get("rows"))
    signal_summary = as_dict(data.get("earnings_signal_summary"))
    warnings = [f"{text(row.get('symbol'))}: {text(row.get('latest_issue') or row.get('field'))}" for row in gaps if isinstance(row, Mapping)]
    status = "warning" if warnings else "ready"
    items = [
        {
            "upcoming_count": len(upcoming),
            "recent_count": len(recent),
            "overall_direction": text(signal_summary.get("overall_direction"), "unknown"),
            "provider_gap_count": len(gaps),
        }
    ]
    return _panel(
        "earnings_review",
        "Earnings Review",
        status=status,
        summary=text(data.get("note") or "Earnings review is available."),
        items=items,
        warnings=warnings,
    )


def provider_gaps_panel(section: Mapping[str, object] | None) -> dict[str, object]:
    data = as_dict(section)
    if not data:
        return _panel(
            "provider_gaps",
            "Data Reliability And Provider Gaps",
            status="missing",
            summary="No provider-gap or source-health data is available.",
            missing_data=True,
        )

    summary = as_dict(data.get("summary"))
    blockers = as_dict(data.get("provider_blockers"))
    alerts = as_dict(data.get("alerts"))
    blocker_items = _rows_from_table(blockers)
    alert_items = _rows_from_table(alerts)
    warnings = []
    if text(data.get("top_blocker")):
        warnings.append(f"Top blocker: {text(data.get('top_blocker'))}")
    for item in blocker_items:
        if text(item.get("Latest Detail")):
            warnings.append(text(item.get("Latest Detail")))
    stale_count = int(summary.get("stale") or 0) if str(summary.get("stale") or "0").isdigit() else 0
    status = "warning" if warnings else "stale" if stale_count else "ready"
    return _panel(
        "provider_gaps",
        "Data Reliability And Provider Gaps",
        status=status,
        summary=f"{len(blocker_items)} provider blocker row(s), {len(alert_items)} alert row(s).",
        items=[*blocker_items, *alert_items],
        warnings=warnings,
        stale=stale_count > 0,
    )


def ai_briefs_panel(section: Mapping[str, object] | list[object] | None) -> dict[str, object]:
    if isinstance(section, list):
        briefs = [item for item in section if isinstance(item, Mapping)]
        data: dict[str, object] = {"briefs": briefs}
    else:
        data = as_dict(section)
        briefs = [item for item in as_list(data.get("briefs") or data.get("rows")) if isinstance(item, Mapping)]

    if not data and not briefs:
        return _panel(
            "ai_briefs",
            "AI Briefs",
            status="missing",
            summary="No AI brief review data is available.",
            missing_data=True,
        )

    guardrails = as_dict(data.get("guardrails") or data.get("guardrail_summary"))
    warnings = _string_list(guardrails.get("warnings"))
    status = text(guardrails.get("status") or data.get("status") or ("ready" if briefs else "missing"))
    items = [
        _safe_item(brief, ("symbol", "title", "status", "review_status", "readiness", "guardrail_status"))
        for brief in briefs[:5]
    ]
    return _panel(
        "ai_briefs",
        "AI Briefs",
        status=status,
        summary=text(data.get("summary") or f"{len(briefs)} AI brief row(s) available."),
        items=items,
        warnings=warnings,
        missing_data=not bool(briefs),
    )


def learning_review_panel(section: Mapping[str, object] | None) -> dict[str, object]:
    data = as_dict(section)
    if not data:
        return _panel(
            "learning_review",
            "Learning Review",
            status="missing",
            summary="No learning review data is available.",
            missing_data=True,
        )

    sections = {
        "manual_journal": as_dict(data.get("manual_journal")),
        "recommendation_outcomes": as_dict(data.get("recommendation_outcomes")),
        "catalyst_follow_through": as_dict(data.get("catalyst_follow_through")),
        "source_usefulness": as_dict(data.get("source_usefulness")),
        "decision_safety_effectiveness": as_dict(data.get("decision_safety_effectiveness")),
    }
    items = []
    warnings = []
    for name, section_data in sections.items():
        available = text(section_data.get("available") or section_data.get("status"))
        count = section_data.get("entry_count", section_data.get("outcome_count", section_data.get("source_count", section_data.get("row_count", 0))))
        items.append({"section": name, "available": available, "count": count})
        if available in {"missing", "false", "False"}:
            warnings.append(f"{name} missing")
    return _panel(
        "learning_review",
        "Learning Review",
        status="warning" if warnings else "ready",
        summary=text(data.get("note") or "Learning sections are review-only and do not tune recommendations."),
        items=items,
        warnings=warnings,
    )


def manual_journal_outcomes_panel(section: Mapping[str, object] | None) -> dict[str, object]:
    data = as_dict(section)
    if not data:
        return _panel(
            "manual_journal_outcomes",
            "Manual Journal And Outcomes",
            status="missing",
            summary="No manual journal or outcome data is available.",
            missing_data=True,
        )

    manual = as_dict(data.get("manual_journal"))
    outcomes = as_dict(data.get("recommendation_outcomes"))
    manual_rows = as_list(manual.get("rows") or manual.get("entries"))
    outcome_rows = as_list(outcomes.get("rows") or outcomes.get("outcomes"))
    items = [
        {
            "manual_journal_count": manual.get("entry_count", len(manual_rows)),
            "recommendation_outcome_count": outcomes.get("outcome_count", len(outcome_rows)),
            "manual_status": text(manual.get("status") or manual.get("available")),
            "outcome_status": text(outcomes.get("status") or outcomes.get("available")),
        }
    ]
    warnings = []
    if not manual_rows and not manual.get("entry_count"):
        warnings.append("No manual journal entries recorded yet.")
    if not outcome_rows and not outcomes.get("outcome_count"):
        warnings.append("No recommendation outcome rows recorded yet.")
    return _panel(
        "manual_journal_outcomes",
        "Manual Journal And Outcomes",
        status="warning" if warnings else "ready",
        summary="Manual decisions and outcomes are review-only learning context.",
        items=items,
        warnings=warnings,
    )


def artifacts_run_history_panel(section: Mapping[str, object] | None) -> dict[str, object]:
    data = as_dict(section)
    if not data:
        return _panel(
            "artifacts_run_history",
            "Artifacts And Run History",
            status="missing",
            summary="No artifact or run-history data is available.",
            missing_data=True,
        )

    artifacts = as_dict(data.get("artifacts") or data)
    run_history = as_dict(data.get("run_history"))
    runs = as_list(data.get("runs") or run_history.get("runs") or data.get("run_history"))
    stale_artifacts = [text(item) for item in as_list(data.get("stale_artifacts")) if text(item)]
    items = []
    for key, value in sorted(artifacts.items()):
        if key in {"runs", "run_history", "stale_artifacts"}:
            continue
        if isinstance(value, Mapping):
            artifact = {"artifact": key, **deepcopy(dict(value))}
            if text(value.get("status")).lower() == "stale":
                stale_artifacts.append(key)
        else:
            artifact = {"artifact": key, "path": deepcopy(value)}
        items.append(artifact)
    items.extend({"run": deepcopy(run)} for run in runs[:5])
    warnings = [f"Stale artifact: {artifact}" for artifact in stale_artifacts]
    return _panel(
        "artifacts_run_history",
        "Artifacts And Run History",
        status="stale" if stale_artifacts else "ready",
        summary=f"{len(items)} artifact/run item(s) available.",
        items=items,
        warnings=warnings,
        missing_data=not bool(items),
        stale=bool(stale_artifacts),
    )


def build_local_console_panels(context: Mapping[str, object] | None) -> dict[str, dict[str, object]]:
    data = as_dict(context)
    learning = as_dict(data.get("learning_review"))
    manual_outcomes = {}
    if data.get("manual_journal") or data.get("recommendation_outcomes") or learning:
        manual_outcomes = {
            "manual_journal": _first_mapping(data.get("manual_journal"), learning.get("manual_journal")),
            "recommendation_outcomes": _first_mapping(
                data.get("recommendation_outcomes"),
                learning.get("recommendation_outcomes"),
            ),
        }
    artifacts = {}
    if data.get("artifacts") or data.get("run_history"):
        artifacts = {
            "artifacts": as_dict(data.get("artifacts")),
            "run_history": as_dict(data.get("run_history")),
        }
    return {
        "current_decision": build_current_decision_panel(as_dict(data.get("summary"))),
        "capital_deployment": build_capital_deployment_panel(as_dict(data.get("long_term_capital_deployment"))),
        "earnings_review": build_earnings_review_panel(as_dict(data.get("earnings_review"))),
        "provider_gaps": build_provider_gaps_panel(as_dict(data.get("source_health"))),
        "ai_briefs": build_ai_briefs_panel(data.get("ai_briefs")),
        "learning_review": build_learning_review_panel(learning),
        "manual_journal_outcomes": build_manual_journal_outcomes_panel(manual_outcomes),
        "artifacts_run_history": build_artifacts_run_history_panel(artifacts),
    }


build_current_decision_panel = current_decision_panel
build_capital_deployment_panel = capital_deployment_panel
build_earnings_review_panel = earnings_review_panel
build_provider_gaps_panel = provider_gaps_panel
build_ai_briefs_panel = ai_briefs_panel
build_learning_review_panel = learning_review_panel
build_manual_journal_outcomes_panel = manual_journal_outcomes_panel
build_artifacts_run_history_panel = artifacts_run_history_panel


__all__ = [
    "GUARDRAIL_TEXT",
    "ai_briefs_panel",
    "artifacts_run_history_panel",
    "build_ai_briefs_panel",
    "build_artifacts_run_history_panel",
    "build_capital_deployment_panel",
    "build_current_decision_panel",
    "build_earnings_review_panel",
    "build_local_console_panels",
    "build_learning_review_panel",
    "build_manual_journal_outcomes_panel",
    "build_provider_gaps_panel",
    "capital_deployment_panel",
    "current_decision_panel",
    "earnings_review_panel",
    "learning_review_panel",
    "manual_journal_outcomes_panel",
    "provider_gaps_panel",
]
