"""Presentation helpers for Wave 15 decision-quality context."""

from __future__ import annotations

from typing import Any


CORE_MEGA_CAP_SYMBOLS = {"AAPL", "AMZN", "AVGO", "GOOG", "GOOGL", "META", "MSFT", "NVDA", "ORCL"}


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value else []
    return []


def text(value: object, default: str = "") -> str:
    if value is None or value == "":
        return default
    return str(value)


def money(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${amount:,.2f}"


def lane_for(row: dict[str, Any]) -> str:
    explicit = text(row.get("opportunity_lane") or row.get("lane"))
    if explicit:
        return explicit
    symbol = text(row.get("symbol")).upper()
    sleeve = text(row.get("sleeve")).lower()
    trade_type = text(row.get("trade_type")).lower()
    action = text(row.get("action")).lower()
    if "speculative" in sleeve or "speculative" in trade_type:
        return "Higher-upside / speculative"
    if "tactical" in sleeve or "short" in trade_type:
        return "Tactical review"
    if symbol in CORE_MEGA_CAP_SYMBOLS:
        return "Core mega-cap"
    if action == "watch":
        return "Watchlist / higher upside"
    return "Long-term core"


def plain_blocker(reason: object) -> str:
    raw = text(reason)
    lowered = raw.lower()
    if not raw:
        return ""
    if "watch action is not a buy action" in lowered:
        return "The model is saying to watch this idea, so buy/add capacity stays held until the official action clears the buy/add gate."
    if "verification" in lowered and "open" in lowered:
        return "A verification check is still open, so the candidate is not decision-safe yet."
    if "low target confidence" in lowered:
        return "Target support is thin or uncertain, so the app is treating sizing confidence as too low."
    if "wide target range" in lowered:
        return "Target estimates are spread too widely, so the app is avoiding false precision."
    if "partial target blend" in lowered:
        return "Only part of the target blend is available, so confidence is reduced until more target evidence is present."
    if "needs price" in lowered or "missing price" in lowered:
        return "Current price is missing, so upside and suggested amount are reliability-blocked rather than bearish."
    if "provider" in lowered or "missing" in lowered or "stale" in lowered:
        return "Provider data is missing or stale, which is a reliability blocker rather than a negative thesis."
    return raw


def top_reason_for(row: dict[str, Any]) -> str:
    for key in ("top_reason", "why_now", "why", "rationale", "notes", "score_breakdown"):
        value = row.get(key)
        if isinstance(value, list):
            return text(value[0]) if value else ""
        rendered = text(value)
        if rendered:
            return rendered
    return "Ranked by the existing official score and recommendation context."


def top_blocker_for(row: dict[str, Any]) -> str:
    explicit = text(row.get("top_blocker"))
    if explicit:
        return plain_blocker(explicit)
    blockers = as_list(row.get("top_blockers") or row.get("blocked_reasons"))
    if blockers:
        return plain_blocker(blockers[0])
    gate = as_dict(row.get("decision_gate"))
    reasons = as_list(gate.get("reasons"))
    if reasons:
        return plain_blocker(reasons[0])
    action = text(row.get("action"))
    if action == "Watch":
        return plain_blocker("Watch action is not a buy action")
    return "No blocker shown."


def reliability_note_for(row: dict[str, Any]) -> str:
    explicit = text(row.get("reliability_note") or row.get("data_reliability_note"))
    if explicit:
        return explicit
    data_status = text(row.get("data_status"), "Data status not available")
    confidence = text(row.get("confidence"), "confidence not available")
    return f"{data_status}; {confidence} confidence."


def compact_opportunity(row: dict[str, Any], index: int) -> dict[str, object]:
    gate = as_dict(row.get("decision_gate"))
    status = text(row.get("decision_gate_status") or gate.get("status"), "Review")
    suggested = text(row.get("suggested_amount_text")) or money(row.get("suggested_amount"))
    blockers = as_list(row.get("top_blockers") or row.get("blocked_reasons") or gate.get("reasons"))
    plain_blockers = [plain_blocker(reason) for reason in blockers if plain_blocker(reason)]
    return {
        "rank": row.get("rank") or index,
        "symbol": text(row.get("symbol"), "n/a"),
        "company": text(row.get("company")),
        "lane": lane_for(row),
        "action": text(row.get("action"), "n/a"),
        "score": text(row.get("score"), "n/a"),
        "decision_gate_status": status,
        "plain_english_blocked_explanation": plain_blockers[0] if plain_blockers else top_blocker_for(row),
        "suggested_amount": suggested,
        "top_reason": top_reason_for(row),
        "top_blocker": plain_blockers[0] if plain_blockers else top_blocker_for(row),
        "data_reliability_note": reliability_note_for(row),
        "holdings_capital_freshness": text(row.get("holdings_capital_freshness"), "See holdings freshness panel when broker/manual context is available."),
    }


def fallback_opportunities(context: dict[str, object]) -> list[dict[str, object]]:
    recommendations = [row for row in as_list(context.get("recommendations")) if isinstance(row, dict)]
    selected = list(recommendations[:5])
    if not any(lane_for(row) == "Higher-upside / speculative" for row in selected):
        speculative = next((row for row in recommendations[5:] if lane_for(row) == "Higher-upside / speculative"), None)
        if speculative is not None:
            selected = [*selected[:4], speculative]
    rows = []
    for index, row in enumerate(selected[:5], start=1):
        rows.append(compact_opportunity(row, index))
    return rows


def table(headers: list[str], rows: list[list[object]]) -> dict[str, object]:
    return {"headers": headers, "rows": rows, "raw_columns": []}


def build_decision_quality_view(context: dict[str, object]) -> dict[str, object]:
    section = as_dict(context.get("decision_quality"))
    top5 = as_list(section.get("top_5_ranked_opportunities")) or fallback_opportunities(context)
    top5 = [compact_opportunity(as_dict(row), index) for index, row in enumerate(top5, start=1)]
    glossary = as_dict(section.get("score_driver_glossary"))
    glossary_rows = as_list(glossary.get("rows")) or [
        ["Base evidence", "Company quality, financial context, and durable business evidence already in the official score."],
        ["Trends", "Recent score movement, technical trend context, and directional changes. Review-only here."],
        ["Targets", "Analyst, fundamental, and technical target evidence before blending. Thin or wide targets reduce confidence."],
        ["Gaps", "Missing, stale, blocked, or unimplemented provider data. This is a reliability issue, not a bearish thesis by itself."],
        ["Final action", "The controlled official label after score, target confidence, and decision-safety gates are applied."],
    ]
    maintenance = as_dict(section.get("data_maintenance_work_requests"))
    disagreement = as_dict(section.get("model_user_disagreement_learning"))
    queue_refinement = as_dict(section.get("queue_refinement"))
    holdings_freshness = as_dict(section.get("holdings_freshness"))
    return {
        "available": bool(section) or bool(top5),
        "review_only": section.get("review_only", True),
        "recommendation_only": section.get("recommendation_only", True),
        "note": text(
            section.get("note"),
            "Decision-quality review is recommendation-only; it clarifies the daily review without changing official recommendations.",
        ),
        "top5": table(
            ["Rank", "Symbol", "Lane", "Action", "Score", "Gate", "Amount", "Top reason", "Top blocker", "Reliability"],
            [
                [
                    row.get("rank"),
                    row.get("symbol"),
                    row.get("lane"),
                    row.get("action"),
                    row.get("score"),
                    row.get("decision_gate_status"),
                    row.get("suggested_amount"),
                    row.get("top_reason"),
                    row.get("top_blocker"),
                    row.get("data_reliability_note"),
                ]
                for row in top5
            ],
        ),
        "top5_rows": top5,
        "decision_gate_explanations": as_list(section.get("decision_gate_explanations")),
        "glossary": table(["Score driver", "Plain-English meaning"], glossary_rows),
        "data_maintenance": table(
            ["Priority", "Area", "Symbol/Source", "Request", "Next action"],
            as_list(maintenance.get("rows")),
        ),
        "model_user_disagreement": table(
            ["Symbol", "Model view", "User intent", "Learning use", "Status"],
            as_list(disagreement.get("rows")),
        ),
        "queue_refinement": table(
            ["Queue", "Role", "Duplication reduced"],
            as_list(queue_refinement.get("rows")),
        ),
        "holdings_freshness": table(
            ["Source", "As of", "Status", "Freshness note"],
            as_list(holdings_freshness.get("rows")),
        ),
        "empty_state": text(section.get("empty_state"), "Decision-quality context will appear after the next analysis run."),
    }


__all__ = ["build_decision_quality_view", "plain_blocker"]
