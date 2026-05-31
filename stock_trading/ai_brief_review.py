#!/usr/bin/env python3
"""Review workflow helpers for AI-assisted research briefs.

Reviews are intentionally explanatory metadata only. They do not alter scores,
actions, targets, confidence, suggested amounts, or decision gates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from stock_trading.storage.connection import ROOT


VALID_REVIEW_STATUSES = ("draft", "reviewed", "accepted", "rejected", "flagged")
VALID_REVIEW_REASONS = (
    "unsupported_claim",
    "weak_source",
    "hallucination_risk",
    "stale_evidence",
    "useful_insight",
    "needs_more_evidence",
    "other",
)
TRUSTED_REVIEW_STATUSES = {"reviewed", "accepted"}
UNTRUSTED_REVIEW_STATUSES = {"draft", "rejected", "flagged"}
DEFAULT_REVIEW_PATH = ROOT / "data" / "ai_brief_reviews.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def brief_id_for(symbol: str, report_date: str, rank: object = "") -> str:
    clean_symbol = str(symbol or "").strip().upper()
    clean_date = str(report_date or "").strip()
    clean_rank = str(rank or "").strip()
    return ":".join(part for part in (clean_date, clean_symbol, clean_rank) if part)


def normalize_review_status(status: object) -> str:
    normalized = str(status or "draft").strip().lower()
    if normalized not in VALID_REVIEW_STATUSES:
        raise ValueError(f"AI brief review status must be one of: {', '.join(VALID_REVIEW_STATUSES)}.")
    return normalized


def normalize_review_reason(reason: object) -> str:
    normalized = str(reason or "other").strip().lower()
    if normalized not in VALID_REVIEW_REASONS:
        raise ValueError(f"AI brief review reason must be one of: {', '.join(VALID_REVIEW_REASONS)}.")
    return normalized


def review_trust_metadata(status: str) -> dict[str, object]:
    trusted = status in TRUSTED_REVIEW_STATUSES
    if status == "accepted":
        label = "Reviewed user-approved context"
    elif status == "reviewed":
        label = "Reviewed context"
    elif status == "rejected":
        label = "Rejected - not trusted research"
    elif status == "flagged":
        label = "Flagged - not trusted research"
    else:
        label = "Draft - not trusted research"
    return {
        "trusted_research": trusted,
        "display_label": label,
        "review_required": status in UNTRUSTED_REVIEW_STATUSES,
    }


def normalize_ai_brief_review(payload: dict[str, Any], created_at: str | None = None) -> dict[str, object]:
    symbol = str(payload.get("symbol") or "").strip().upper()
    report_date = str(payload.get("report_date") or "").strip()
    brief_id = str(payload.get("brief_id") or "").strip()
    artifact_ref = str(payload.get("artifact_ref") or payload.get("artifact") or "").strip()
    status = normalize_review_status(payload.get("status"))
    reason = normalize_review_reason(payload.get("reason"))
    notes = str(payload.get("notes") or "").strip()

    if not symbol:
        raise ValueError("AI brief review requires a symbol.")
    if not report_date:
        raise ValueError("AI brief review requires a report_date.")
    if not brief_id and not artifact_ref:
        raise ValueError("AI brief review requires a brief_id or artifact_ref.")
    if not brief_id:
        brief_id = brief_id_for(symbol, report_date)

    return {
        "symbol": symbol,
        "report_date": report_date,
        "brief_id": brief_id,
        "artifact_ref": artifact_ref,
        "status": status,
        "reason": reason,
        "notes": notes,
        "created_at": created_at or utc_now(),
    }


def record_ai_brief_review(payload: dict[str, Any], path: Path | None = None) -> dict[str, object]:
    review = normalize_ai_brief_review(payload)
    target_path = path or DEFAULT_REVIEW_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(review, sort_keys=True) + "\n")
    return {
        **review,
        **review_trust_metadata(str(review["status"])),
        "message": f"Recorded AI brief review for {review['symbol']}",
    }


def load_ai_brief_reviews(
    path: Path | None = None,
    limit: int = 50,
    symbol: str = "",
    report_date: str = "",
) -> list[dict[str, object]]:
    target_path = path or DEFAULT_REVIEW_PATH
    if not target_path.exists():
        return []
    symbol_filter = symbol.strip().upper()
    date_filter = report_date.strip()
    rows: list[dict[str, object]] = []
    for line in target_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        normalized = normalize_ai_brief_review(row, created_at=str(row.get("created_at") or utc_now()))
        if symbol_filter and normalized["symbol"] != symbol_filter:
            continue
        if date_filter and normalized["report_date"] != date_filter:
            continue
        rows.append({**normalized, **review_trust_metadata(str(normalized["status"]))})
    rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    return rows[: max(0, limit)]


def review_key(review: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(review.get("symbol") or "").upper(),
        str(review.get("report_date") or ""),
        str(review.get("brief_id") or ""),
    )


def latest_reviews_by_brief(reviews: Iterable[dict[str, object]]) -> dict[tuple[str, str, str], dict[str, object]]:
    latest: dict[tuple[str, str, str], dict[str, object]] = {}
    for review in reviews:
        key = review_key(review)
        if not all(key):
            continue
        existing = latest.get(key)
        if existing is None or str(review.get("created_at") or "") >= str(existing.get("created_at") or ""):
            latest[key] = review
    return latest


def default_review_metadata(symbol: str, report_date: str, brief_id: str, artifact_ref: str = "") -> dict[str, object]:
    status = "draft"
    return {
        "symbol": symbol,
        "report_date": report_date,
        "brief_id": brief_id,
        "artifact_ref": artifact_ref,
        "status": status,
        "reason": "needs_more_evidence",
        "notes": "AI-assisted brief has not been reviewed.",
        "created_at": "",
        **review_trust_metadata(status),
    }


def apply_review_metadata(
    briefs: list[dict[str, object]],
    reviews: Iterable[dict[str, object]] = (),
) -> list[dict[str, object]]:
    latest = latest_reviews_by_brief(reviews)
    annotated: list[dict[str, object]] = []
    for brief in briefs:
        symbol = str(brief.get("symbol") or "").upper()
        report_date = str(brief.get("report_date") or "")
        brief_id = str(brief.get("brief_id") or "")
        artifact_ref = str(brief.get("artifact_ref") or "")
        review = latest.get((symbol, report_date, brief_id)) or default_review_metadata(
            symbol,
            report_date,
            brief_id,
            artifact_ref,
        )
        review = {**review, **review_trust_metadata(str(review.get("status") or "draft"))}
        annotated.append({**brief, "review": review})
    return annotated


__all__ = [
    "DEFAULT_REVIEW_PATH",
    "TRUSTED_REVIEW_STATUSES",
    "UNTRUSTED_REVIEW_STATUSES",
    "VALID_REVIEW_REASONS",
    "VALID_REVIEW_STATUSES",
    "apply_review_metadata",
    "brief_id_for",
    "default_review_metadata",
    "load_ai_brief_reviews",
    "normalize_ai_brief_review",
    "record_ai_brief_review",
    "review_trust_metadata",
]
