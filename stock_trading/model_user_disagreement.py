"""Review-only model/user disagreement tracking.

This module compares manual journal entries with stored recommendation rows so
the app can learn where Matt acted differently from the model. The output is
measurement context only; it must not tune models or change recommendations.
"""

from __future__ import annotations

import copy
from typing import Iterable, Mapping


REVIEW_ONLY_NOTE = (
    "Review-only model/user disagreement tracking. These records do not tune models, "
    "change official recommendations, change scores, change targets, change decision "
    "safety, change allocation, write to brokers, preview orders, or trade."
)

BUY_ACTIONS = {"Strong Buy", "Buy"}
ADD_ACTIONS = {"Add"}
BUY_OR_ADD_ACTIONS = BUY_ACTIONS | ADD_ACTIONS
USER_BUY_ACTIONS = {"bought", "added"}
USER_HOLD_ACTIONS = {"held", "watched", "reviewed_only"}
USER_SKIP_ACTIONS = {"skipped"}
USER_AVOID_ACTIONS = {"avoided"}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [text(item) for item in value if text(item)]
    if isinstance(value, tuple):
        return [text(item) for item in value if text(item)]
    if isinstance(value, str):
        return [value] if value else []
    return []


def key_for(row: Mapping[str, object]) -> tuple[str, str]:
    symbol = text(row.get("symbol")).upper()
    report_date = text(row.get("report_date") or row.get("decision_date"))
    return symbol, report_date


def model_action(row: Mapping[str, object]) -> str:
    return text(row.get("model_action") or row.get("action") or row.get("candidate_action"))


def user_action(row: Mapping[str, object]) -> str:
    return token(row.get("action_taken") or row.get("user_action") or row.get("action"))


def decision_gate_status(row: Mapping[str, object]) -> str:
    return text(row.get("decision_gate_status") or row.get("decision_safety_status") or row.get("status"))


def blocked_reasons(row: Mapping[str, object]) -> list[str]:
    raw = (
        row.get("blocked_reasons")
        or row.get("decision_gate_reasons")
        or row.get("decision_safety_reasons")
        or []
    )
    return as_list(raw)


def is_blocked(status: str, reasons: Iterable[str]) -> bool:
    return token(status) == "blocked" or any("blocked" in token(reason) for reason in reasons)


def disagreement_type_for(
    *,
    action: str,
    user: str,
    gate_status: str,
    reasons: Iterable[str],
    has_recommendation: bool = True,
    has_journal: bool = True,
) -> str:
    """Classify the deterministic model/user relationship."""

    if not has_recommendation:
        return "missing_recommendation"
    if not has_journal:
        return "no_user_action_recorded"

    action = text(action)
    user = token(user)
    blocked = is_blocked(gate_status, reasons)

    if user in USER_BUY_ACTIONS and action == "Avoid":
        return "model_avoid_user_bought"
    if user in USER_BUY_ACTIONS and blocked:
        return "model_blocked_user_bought"
    if user in USER_BUY_ACTIONS and action == "Watch":
        return "model_watch_user_bought"
    if user in USER_AVOID_ACTIONS and action in BUY_ACTIONS:
        return "model_buy_user_avoided"
    if user in USER_SKIP_ACTIONS and action in BUY_ACTIONS:
        return "model_buy_user_skipped"
    if user in (USER_HOLD_ACTIONS | USER_SKIP_ACTIONS) and action in ADD_ACTIONS:
        return "model_add_user_held"
    if (
        (action in BUY_OR_ADD_ACTIONS and user in USER_BUY_ACTIONS)
        or (action == "Watch" and user in USER_HOLD_ACTIONS)
        or (action == "Avoid" and user in USER_AVOID_ACTIONS)
        or (blocked and user in USER_HOLD_ACTIONS | USER_SKIP_ACTIONS | USER_AVOID_ACTIONS)
    ):
        return "model_and_user_agreed"
    return "model_and_user_agreed"


def learning_note_for(disagreement_type: str, symbol: str) -> str:
    notes = {
        "model_watch_user_bought": (
            f"{symbol}: user bought or added despite a Watch model action; review whether the "
            "model was too conservative or missing user conviction."
        ),
        "model_blocked_user_bought": (
            f"{symbol}: user bought or added despite a blocked decision gate; review whether "
            "the block protected against risk or over-blocked a manual conviction buy."
        ),
        "model_buy_user_skipped": (
            f"{symbol}: model said Buy but user skipped; review whether trust, timing, "
            "valuation, or data gaps made the recommendation less usable."
        ),
        "model_add_user_held": (
            f"{symbol}: model said Add but user held or skipped; review whether sizing, "
            "timing, or explanation blocked manual action."
        ),
        "model_avoid_user_bought": (
            f"{symbol}: user bought or added despite Avoid; review model risk assessment and "
            "manual rationale before considering any future model-impact change."
        ),
        "model_buy_user_avoided": (
            f"{symbol}: model said Buy but user avoided; review whether risk language, "
            "data quality, or thesis trust was insufficient."
        ),
        "missing_recommendation": (
            f"{symbol}: manual journal entry has no matching recommendation row; preserve it "
            "for later learning but do not infer model quality."
        ),
        "no_user_action_recorded": (
            f"{symbol}: recommendation has no matching manual journal entry; no user/model "
            "disagreement can be evaluated yet."
        ),
        "model_and_user_agreed": (
            f"{symbol}: model and user action were aligned; keep as baseline learning context."
        ),
    }
    return notes.get(disagreement_type, notes["model_and_user_agreed"])


def _outcome_lookup(
    recommendation_outcomes: Iterable[Mapping[str, object]] | None,
) -> dict[tuple[str, str], list[dict[str, object]]]:
    lookup: dict[tuple[str, str], list[dict[str, object]]] = {}
    for outcome in recommendation_outcomes or []:
        row = dict(outcome)
        lookup.setdefault(key_for(row), []).append(row)
    for rows in lookup.values():
        rows.sort(key=lambda row: int(float(row.get("window_trading_days") or 0)))
    return lookup


def _journal_lookup(
    manual_journal_entries: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], list[dict[str, object]]]:
    lookup: dict[tuple[str, str], list[dict[str, object]]] = {}
    for entry in manual_journal_entries:
        row = copy.deepcopy(dict(entry))
        key = key_for(row)
        if not key[0]:
            continue
        lookup.setdefault(key, []).append(row)
    for rows in lookup.values():
        rows.sort(key=lambda row: (text(row.get("decision_date")), text(row.get("id"))))
    return lookup


def _recommendation_lookup(
    recommendation_rows: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], dict[str, object]]:
    lookup: dict[tuple[str, str], dict[str, object]] = {}
    for rec in recommendation_rows:
        row = copy.deepcopy(dict(rec))
        key = key_for(row)
        if not key[0]:
            continue
        lookup.setdefault(key, row)
    return lookup


def model_user_disagreement_rows(
    manual_journal_entries: Iterable[Mapping[str, object]],
    recommendation_rows: Iterable[Mapping[str, object]],
    recommendation_outcomes: Iterable[Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Return deterministic review-only disagreement rows.

    Inputs are copied before use so callers can safely pass stored rows or
    in-memory fixtures without mutation.
    """

    journals = _journal_lookup(manual_journal_entries)
    recs = _recommendation_lookup(recommendation_rows)
    outcomes = _outcome_lookup(recommendation_outcomes)
    keys = sorted(set(journals) | set(recs))
    rows: list[dict[str, object]] = []

    for key in keys:
        symbol, report_date = key
        rec = recs.get(key, {})
        journal_rows = journals.get(key, [])
        journal = journal_rows[-1] if journal_rows else {}
        action = model_action(rec)
        user = user_action(journal)
        status = decision_gate_status(rec)
        reasons = blocked_reasons(rec)
        disagreement_type = disagreement_type_for(
            action=action,
            user=user,
            gate_status=status,
            reasons=reasons,
            has_recommendation=bool(rec),
            has_journal=bool(journal),
        )
        rows.append(
            {
                "symbol": symbol,
                "report_date": report_date,
                "model_action": action,
                "user_action": user,
                "decision_gate_status": status,
                "blocked_reasons": reasons,
                "disagreement_type": disagreement_type,
                "user_rationale": text(journal.get("rationale") or journal.get("notes")),
                "manual_journal_entries": len(journal_rows),
                "later_outcome": outcomes.get(key, []),
                "learning_note": learning_note_for(disagreement_type, symbol),
                "review_only": True,
                "no_model_change": True,
                "notes": REVIEW_ONLY_NOTE,
            }
        )

    rows.sort(key=lambda row: (text(row["report_date"]), text(row["symbol"]), text(row["disagreement_type"])))
    return rows


def summarize_disagreements(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    summary: dict[str, object] = {
        "review_only": True,
        "no_model_change": True,
        "row_count": 0,
        "disagreement_count": 0,
        "agreement_count": 0,
        "missing_recommendation_count": 0,
        "missing_journal_count": 0,
        "by_type": {},
        "notes": REVIEW_ONLY_NOTE,
    }
    by_type: dict[str, int] = {}
    for row in rows:
        disagreement_type = text(row.get("disagreement_type"), "unknown")
        by_type[disagreement_type] = by_type.get(disagreement_type, 0) + 1
        summary["row_count"] = int(summary["row_count"]) + 1
        if disagreement_type == "model_and_user_agreed":
            summary["agreement_count"] = int(summary["agreement_count"]) + 1
        elif disagreement_type == "missing_recommendation":
            summary["missing_recommendation_count"] = int(summary["missing_recommendation_count"]) + 1
        elif disagreement_type == "no_user_action_recorded":
            summary["missing_journal_count"] = int(summary["missing_journal_count"]) + 1
        else:
            summary["disagreement_count"] = int(summary["disagreement_count"]) + 1
    summary["by_type"] = dict(sorted(by_type.items()))
    return summary


def build_model_user_disagreement_review(
    manual_journal_entries: Iterable[Mapping[str, object]],
    recommendation_rows: Iterable[Mapping[str, object]],
    recommendation_outcomes: Iterable[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    rows = model_user_disagreement_rows(
        manual_journal_entries,
        recommendation_rows,
        recommendation_outcomes,
    )
    return {
        "metadata": {
            "review_only": True,
            "no_model_change": True,
            "row_count": len(rows),
            "notes": REVIEW_ONLY_NOTE,
        },
        "summary": summarize_disagreements(rows),
        "rows": rows,
    }


__all__ = [
    "REVIEW_ONLY_NOTE",
    "build_model_user_disagreement_review",
    "disagreement_type_for",
    "model_user_disagreement_rows",
    "summarize_disagreements",
]
