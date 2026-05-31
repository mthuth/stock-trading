"""Review-only alert and review-trigger helpers.

The alert layer converts already-computed review signals into deterministic
review prompts. It is deliberately pure and local: it does not refresh
providers, call models, change recommendations, or touch broker/trading paths.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Iterable, Mapping


ALERT_TYPES = {
    "decision_gate_changed",
    "target_confidence_changed",
    "provider_gap_resolved",
    "provider_gap_worsened",
    "price_move_review",
    "earnings_window_entered",
    "post_earnings_review_due",
    "source_event_review",
    "ai_brief_ready",
    "ai_brief_guardrail_failed",
    "recommendation_outcome_review",
    "tactical_setup_review",
    "model_trust_changed",
    "capital_deployment_review",
    "watchlist_readiness_changed",
}
SEVERITIES = {
    "critical_review",
    "high_review",
    "medium_review",
    "low_review",
    "informational",
}
STATUSES = {
    "new",
    "seen",
    "acknowledged",
    "deferred",
    "dismissed",
    "resolved",
}
RECOMMENDATION_ONLY_NOTE = (
    "Review-only alert. This prompt is recommendation-only decision support and "
    "does not place trades, preview orders, write to brokers, change scores, "
    "change actions, change targets, change decision gates, alter allocation, "
    "tune models, or change source weights."
)

SEVERITY_RANK = {
    "critical_review": 0,
    "high_review": 10,
    "medium_review": 20,
    "low_review": 30,
    "informational": 40,
}
BLOCKING_OR_WORSE_STATUSES = {
    "blocked",
    "rate_limited",
    "stale",
    "missing",
    "parser_gap",
    "not_implemented",
    "error",
    "failed",
    "needs_review",
    "needs_refresh",
}
OK_STATUSES = {"ok", "resolved", "available", "healthy", "ready", "clear", "none", ""}
ACTIVE_TACTICAL_LABELS = {
    "breakout_review",
    "pullback_review",
    "momentum_review",
    "reversal_review",
    "post_earnings_reaction_review",
    "pre_earnings_setup_review",
    "news_catalyst_review",
}


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _token(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(copy.deepcopy(value))
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _bool(value: object) -> bool:
    if isinstance(value, str):
        return _token(value) in {"true", "yes", "1", "ready", "passed", "ok"}
    return bool(value)


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _stable_hash(value: object, *, length: int = 16) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()[:length]


def _default_created_at(report_date: str) -> str:
    return f"{report_date or 'unknown'}T00:00:00"


def _dedupe_key(
    *,
    report_date: str,
    symbol: str,
    alert_type: str,
    reason_codes: Iterable[object],
    source_refs: Iterable[object],
) -> str:
    payload = {
        "report_date": report_date,
        "symbol": symbol,
        "alert_type": alert_type,
        "reason_codes": sorted(_text(code) for code in reason_codes if _text(code)),
        "source_refs": sorted(_text(ref) for ref in source_refs if _text(ref)),
    }
    return f"{alert_type}:{symbol or 'portfolio'}:{_stable_hash(payload, length=12)}"


def validate_alert(alert: Mapping[str, object]) -> dict[str, object]:
    """Validate an alert row and return structured warnings/errors."""

    row = _as_dict(alert)
    errors: list[str] = []
    warnings: list[str] = []
    if _text(row.get("alert_type")) not in ALERT_TYPES:
        errors.append("invalid_alert_type")
    if _text(row.get("severity")) not in SEVERITIES:
        errors.append("invalid_severity")
    if _text(row.get("status")) not in STATUSES:
        errors.append("invalid_status")
    if row.get("review_only") is not True:
        errors.append("review_only_required")
    if not _text(row.get("recommendation_only_note")):
        warnings.append("missing_recommendation_only_note")
    if not _text(row.get("alert_id")):
        warnings.append("missing_alert_id")
    if not _text(row.get("dedupe_key")):
        warnings.append("missing_dedupe_key")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def build_alert(
    *,
    report_date: str,
    alert_type: str,
    severity: str,
    title: str,
    summary: str,
    symbol: str = "",
    status: str = "new",
    created_at: str | None = None,
    reason_codes: Iterable[object] = (),
    source_refs: Iterable[object] = (),
    related_artifacts: Iterable[object] = (),
    recommended_review_action: str = "review_manually",
    dedupe_key: str = "",
    expires_at: str = "",
) -> dict[str, object]:
    """Build one deterministic, JSON-native alert row."""

    normalized_report_date = _text(report_date)
    normalized_type = _text(alert_type)
    normalized_severity = _text(severity)
    normalized_status = _text(status or "new")
    normalized_symbol = _text(symbol).upper()
    reason_list = [_text(code) for code in _as_list(reason_codes) if _text(code)]
    source_list = [_text(ref) for ref in _as_list(source_refs) if _text(ref)]
    artifact_list = [_text(ref) for ref in _as_list(related_artifacts) if _text(ref)]
    normalized_dedupe = dedupe_key or _dedupe_key(
        report_date=normalized_report_date,
        symbol=normalized_symbol,
        alert_type=normalized_type,
        reason_codes=reason_list,
        source_refs=source_list,
    )
    row = {
        "alert_id": f"alert_{_stable_hash({'created_at': created_at or _default_created_at(normalized_report_date), 'dedupe_key': normalized_dedupe})}",
        "created_at": _text(created_at) or _default_created_at(normalized_report_date),
        "report_date": normalized_report_date,
        "symbol": normalized_symbol,
        "alert_type": normalized_type,
        "severity": normalized_severity,
        "status": normalized_status,
        "title": _text(title),
        "summary": _text(summary),
        "reason_codes": reason_list,
        "source_refs": source_list,
        "related_artifacts": artifact_list,
        "recommended_review_action": _text(recommended_review_action or "review_manually"),
        "dedupe_key": normalized_dedupe,
        "expires_at": _text(expires_at),
        "review_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }
    validation = validate_alert(row)
    if validation["errors"]:
        raise ValueError(f"Invalid alert: {', '.join(validation['errors'])}")
    return row


def dedupe_alerts(alerts: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Deduplicate alert rows by dedupe key while keeping deterministic order."""

    by_key: dict[str, dict[str, object]] = {}
    for alert in alerts:
        row = _as_dict(alert)
        key = _text(row.get("dedupe_key")) or _text(row.get("alert_id"))
        if not key:
            continue
        existing = by_key.get(key)
        if existing is None or SEVERITY_RANK.get(_text(row.get("severity")), 99) < SEVERITY_RANK.get(
            _text(existing.get("severity")), 99
        ):
            by_key[key] = row
    return sorted(
        by_key.values(),
        key=lambda row: (
            SEVERITY_RANK.get(_text(row.get("severity")), 99),
            _text(row.get("report_date")),
            _text(row.get("symbol")),
            _text(row.get("alert_type")),
            _text(row.get("title")),
            _text(row.get("dedupe_key")),
        ),
    )


def decision_gate_alerts(
    changes: Iterable[Mapping[str, object]],
    *,
    report_date: str,
    created_at: str | None = None,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for raw in changes:
        row = _as_dict(raw)
        symbol = _text(row.get("symbol")).upper()
        previous = _text(
            row.get("previous_status")
            or row.get("previous_decision_gate_status")
            or row.get("before_status")
            or _as_dict(row.get("previous")).get("status")
        )
        current = _text(
            row.get("current_status")
            or row.get("current_decision_gate_status")
            or row.get("after_status")
            or _as_dict(row.get("current")).get("status")
        )
        if not previous or not current or _token(previous) == _token(current):
            continue
        current_token = _token(current)
        severity = "high_review" if current_token in {"blocked", "not_ready", "needs_review"} else "medium_review"
        alerts.append(
            build_alert(
                report_date=report_date,
                created_at=created_at,
                symbol=symbol,
                alert_type="decision_gate_changed",
                severity=severity,
                title=f"{symbol or 'Portfolio'} decision gate changed",
                summary=f"Decision gate moved from {previous} to {current}.",
                reason_codes=["decision_gate_changed", f"from_{_token(previous)}", f"to_{current_token}"],
                source_refs=_as_list(row.get("source_refs")),
                related_artifacts=_as_list(row.get("related_artifacts")),
                recommended_review_action="review_decision_gate",
            )
        )
    return alerts


def provider_gap_alerts(
    gaps: Iterable[Mapping[str, object]],
    *,
    report_date: str,
    created_at: str | None = None,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for raw in gaps:
        row = _as_dict(raw)
        symbol = _text(row.get("symbol")).upper()
        provider = _text(row.get("provider") or row.get("source") or "provider")
        field = _text(row.get("endpoint") or row.get("field") or row.get("field_name") or row.get("data_type") or "data")
        previous = _token(row.get("previous_status") or row.get("before_status") or _as_dict(row.get("previous")).get("status"))
        current = _token(row.get("current_status") or row.get("status") or row.get("after_status") or _as_dict(row.get("current")).get("status"))
        change = _token(row.get("change") or row.get("change_type"))
        if change == "resolved" or (previous not in OK_STATUSES and current in OK_STATUSES):
            alerts.append(
                build_alert(
                    report_date=report_date,
                    created_at=created_at,
                    symbol=symbol,
                    alert_type="provider_gap_resolved",
                    severity="informational",
                    title=f"{provider} {field} gap resolved",
                    summary=f"{provider} {field} now reports {current or 'ok'}.",
                    reason_codes=["provider_gap_resolved", f"provider_{_token(provider)}", f"field_{_token(field)}"],
                    source_refs=[provider, field],
                    related_artifacts=_as_list(row.get("related_artifacts")),
                    recommended_review_action="review_resolved_gap",
                )
            )
            continue
        worsened = change == "worsened" or current in BLOCKING_OR_WORSE_STATUSES
        if not worsened:
            continue
        severity = "high_review" if current in {"blocked", "rate_limited", "error", "failed"} else "medium_review"
        issue = _text(row.get("latest_issue") or row.get("message") or row.get("issue"))
        summary = f"{provider} {field} is {current}."
        if issue:
            summary = f"{summary} Latest issue: {issue}"
        alerts.append(
            build_alert(
                report_date=report_date,
                created_at=created_at,
                symbol=symbol,
                alert_type="provider_gap_worsened",
                severity=severity,
                title=f"{provider} {field} needs review",
                summary=summary,
                reason_codes=["provider_gap_worsened", current, f"provider_{_token(provider)}", f"field_{_token(field)}"],
                source_refs=[provider, field],
                related_artifacts=_as_list(row.get("related_artifacts")),
                recommended_review_action="review_provider_gap",
            )
        )
    return alerts


def earnings_window_alerts(
    events: Iterable[Mapping[str, object]],
    *,
    report_date: str,
    created_at: str | None = None,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for raw in events:
        row = _as_dict(raw)
        symbol = _text(row.get("symbol")).upper()
        earnings_date = _text(row.get("earnings_date") or row.get("event_date"))
        review_window = _token(row.get("review_window"))
        event_type = _token(row.get("event_type"))
        days_until = _number(row.get("days_until_earnings"), default=9999)
        days_since = _number(row.get("days_since_earnings"), default=9999)
        if review_window == "pre_earnings" or (event_type == "upcoming_earnings" and 0 <= days_until <= 14):
            alerts.append(
                build_alert(
                    report_date=report_date,
                    created_at=created_at,
                    symbol=symbol,
                    alert_type="earnings_window_entered",
                    severity="medium_review",
                    title=f"{symbol} entered pre-earnings review window",
                    summary=f"Earnings date {earnings_date or 'unknown'} is in the pre-earnings review window.",
                    reason_codes=["earnings_window_entered", "pre_earnings"],
                    source_refs=_as_list(row.get("source_refs") or [row.get("source") or "earnings_event_queue"]),
                    related_artifacts=_as_list(row.get("related_artifacts")),
                    recommended_review_action="review_pre_earnings_setup",
                )
            )
        elif review_window == "post_earnings" or (event_type == "recent_earnings" and 0 <= days_since <= 7):
            alerts.append(
                build_alert(
                    report_date=report_date,
                    created_at=created_at,
                    symbol=symbol,
                    alert_type="post_earnings_review_due",
                    severity="medium_review",
                    title=f"{symbol} post-earnings review due",
                    summary=f"Earnings date {earnings_date or 'unknown'} is in the post-earnings review window.",
                    reason_codes=["post_earnings_review_due", "post_earnings"],
                    source_refs=_as_list(row.get("source_refs") or [row.get("source") or "earnings_event_queue"]),
                    related_artifacts=_as_list(row.get("related_artifacts")),
                    recommended_review_action="review_post_earnings_setup",
                )
            )
    return alerts


def ai_brief_alerts(
    briefs: Iterable[Mapping[str, object]],
    *,
    report_date: str,
    created_at: str | None = None,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for raw in briefs:
        row = _as_dict(raw)
        symbol = _text(row.get("symbol")).upper()
        guardrails = _as_dict(row.get("guardrail_result") or row.get("guardrails"))
        passed_value = guardrails.get("passed")
        status = _token(row.get("status") or guardrails.get("recommended_action"))
        failure_count = int(_number(guardrails.get("failure_count") or len(_as_list(guardrails.get("failures")))))
        failed = passed_value is False or failure_count > 0 or status in {"reject", "rejected", "failed", "guardrail_failed"}
        if failed:
            alerts.append(
                build_alert(
                    report_date=report_date,
                    created_at=created_at,
                    symbol=symbol,
                    alert_type="ai_brief_guardrail_failed",
                    severity="high_review",
                    title=f"{symbol or 'AI brief'} guardrail failed",
                    summary=_text(row.get("summary")) or "AI brief failed deterministic guardrails and needs manual review.",
                    reason_codes=["ai_brief_guardrail_failed", *[_text(item.get("category")) for item in _as_list(guardrails.get("failures")) if isinstance(item, Mapping)]],
                    source_refs=_as_list(row.get("source_refs") or row.get("audit_refs")),
                    related_artifacts=_as_list(row.get("related_artifacts")),
                    recommended_review_action="review_ai_brief_guardrails",
                )
            )
        elif status in {"ready", "generated", "needs_review", "accepted", "accept"}:
            alerts.append(
                build_alert(
                    report_date=report_date,
                    created_at=created_at,
                    symbol=symbol,
                    alert_type="ai_brief_ready",
                    severity="low_review",
                    title=f"{symbol or 'AI brief'} ready for review",
                    summary=_text(row.get("summary")) or "AI brief is ready for manual review.",
                    reason_codes=["ai_brief_ready"],
                    source_refs=_as_list(row.get("source_refs") or row.get("audit_refs")),
                    related_artifacts=_as_list(row.get("related_artifacts")),
                    recommended_review_action="review_ai_brief",
                )
            )
    return alerts


def recommendation_outcome_alerts(
    outcomes: Iterable[Mapping[str, object]],
    *,
    report_date: str,
    created_at: str | None = None,
    review_threshold_pct: float = 5.0,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for raw in outcomes:
        row = _as_dict(raw)
        symbol = _text(row.get("symbol")).upper()
        outcome = _token(row.get("outcome_status"))
        pct_change = _number(row.get("percent_change"))
        progress = _number(row.get("target_progress"))
        window = _text(row.get("window_trading_days") or row.get("window") or "unknown")
        should_alert = (
            outcome in {"drawdown_warning", "target_progress"}
            or abs(pct_change) >= review_threshold_pct
            or progress >= 50
        )
        if not should_alert:
            continue
        severity = "high_review" if outcome == "drawdown_warning" or pct_change <= -review_threshold_pct else "medium_review"
        alerts.append(
            build_alert(
                report_date=report_date,
                created_at=created_at,
                symbol=symbol,
                alert_type="recommendation_outcome_review",
                severity=severity,
                title=f"{symbol} outcome review threshold crossed",
                summary=f"{window}-day outcome is {outcome or 'review'} with {pct_change:.2f}% price change.",
                reason_codes=["recommendation_outcome_review", outcome or "threshold_crossed", f"window_{window}"],
                source_refs=_as_list(row.get("source_refs") or [f"recommendation_outcome:{symbol}:{window}"]),
                related_artifacts=_as_list(row.get("related_artifacts")),
                recommended_review_action="review_recommendation_outcome",
            )
        )
    return alerts


def tactical_setup_alerts(
    setups: Iterable[Mapping[str, object]],
    *,
    report_date: str,
    created_at: str | None = None,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for raw in setups:
        row = _as_dict(raw)
        symbol = _text(row.get("symbol")).upper()
        label = _token(row.get("setup_label"))
        if label not in ACTIVE_TACTICAL_LABELS:
            continue
        action = _text(row.get("review_action") or row.get("recommended_review_action") or "review_tactical_setup")
        severity = "high_review" if action in {"tactical_sell_review", "data_gap_review"} else "medium_review"
        alerts.append(
            build_alert(
                report_date=report_date,
                created_at=created_at,
                symbol=symbol,
                alert_type="tactical_setup_review",
                severity=severity,
                title=f"{symbol} tactical setup appeared",
                summary=f"Tactical setup label {label} is available for review.",
                reason_codes=["tactical_setup_review", label, _token(action)],
                source_refs=_as_list(row.get("source_refs") or [f"tactical_setup:{symbol}"]),
                related_artifacts=_as_list(row.get("related_artifacts")),
                recommended_review_action=action,
            )
        )
    return alerts


def model_trust_alerts(
    changes: Iterable[Mapping[str, object]],
    *,
    report_date: str,
    created_at: str | None = None,
    score_delta_threshold: float = 5.0,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for raw in changes:
        row = _as_dict(raw)
        model_name = _text(row.get("model_name") or "model")
        previous_level = _text(row.get("previous_trust_level") or row.get("previous_level") or _as_dict(row.get("previous")).get("trust_level"))
        current_level = _text(row.get("current_trust_level") or row.get("trust_level") or row.get("current_level") or _as_dict(row.get("current")).get("trust_level"))
        previous_score = row.get("previous_trust_score") or row.get("previous_score") or _as_dict(row.get("previous")).get("trust_score")
        current_score = row.get("current_trust_score") or row.get("trust_score") or row.get("current_score") or _as_dict(row.get("current")).get("trust_score")
        score_delta = _number(current_score) - _number(previous_score)
        level_changed = bool(previous_level and current_level and _token(previous_level) != _token(current_level))
        trust_changed = _bool(row.get("trust_level_changed")) or level_changed or abs(score_delta) >= score_delta_threshold
        if not trust_changed:
            continue
        severity = "medium_review" if score_delta < 0 or _token(current_level) == "observe" else "low_review"
        alerts.append(
            build_alert(
                report_date=report_date,
                created_at=created_at,
                symbol="",
                alert_type="model_trust_changed",
                severity=severity,
                title=f"{model_name} model trust changed",
                summary=f"Model trust moved from {previous_level or previous_score} to {current_level or current_score}.",
                reason_codes=["model_trust_changed", f"model_{_token(model_name)}", f"delta_{round(score_delta, 4)}"],
                source_refs=_as_list(row.get("source_refs") or [f"model_trust:{model_name}"]),
                related_artifacts=_as_list(row.get("related_artifacts")),
                recommended_review_action="review_model_trust",
            )
        )
    return alerts


def build_review_alerts(
    signals: Mapping[str, object],
    *,
    report_date: str,
    created_at: str | None = None,
) -> dict[str, object]:
    """Build a deterministic alert inbox from existing review-signal dictionaries."""

    data = _as_dict(signals)
    alerts: list[dict[str, object]] = []
    alerts.extend(decision_gate_alerts(_as_list(data.get("decision_gates")), report_date=report_date, created_at=created_at))
    alerts.extend(provider_gap_alerts(_as_list(data.get("provider_gaps")), report_date=report_date, created_at=created_at))
    alerts.extend(earnings_window_alerts(_as_list(data.get("earnings_events")), report_date=report_date, created_at=created_at))
    alerts.extend(ai_brief_alerts(_as_list(data.get("ai_briefs")), report_date=report_date, created_at=created_at))
    alerts.extend(
        recommendation_outcome_alerts(_as_list(data.get("recommendation_outcomes")), report_date=report_date, created_at=created_at)
    )
    alerts.extend(tactical_setup_alerts(_as_list(data.get("tactical_setups")), report_date=report_date, created_at=created_at))
    alerts.extend(model_trust_alerts(_as_list(data.get("model_trust")), report_date=report_date, created_at=created_at))
    rows = dedupe_alerts(alerts)
    return {
        "review_only": True,
        "recommendation_only": True,
        "report_date": _text(report_date),
        "generated_at": _text(created_at) or _default_created_at(_text(report_date)),
        "alert_count": len(rows),
        "alerts": rows,
        "note": RECOMMENDATION_ONLY_NOTE,
    }


__all__ = [
    "ALERT_TYPES",
    "SEVERITIES",
    "STATUSES",
    "RECOMMENDATION_ONLY_NOTE",
    "ai_brief_alerts",
    "build_alert",
    "build_review_alerts",
    "decision_gate_alerts",
    "dedupe_alerts",
    "earnings_window_alerts",
    "model_trust_alerts",
    "provider_gap_alerts",
    "recommendation_outcome_alerts",
    "tactical_setup_alerts",
    "validate_alert",
]
