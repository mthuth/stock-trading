"""Presentation helpers for review-only multi-model shadow competition."""

from __future__ import annotations

from typing import Any


DISPLAY_NOTE = (
    "Recommendation-only shadow competition; shadow outputs are non-authoritative "
    "and do not change official recommendations."
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None or value == "":
        return default
    return str(value)


def rows_table(rows: object, headers: list[str], fields: list[str], empty_state: str) -> dict[str, object]:
    items = [as_dict(row) for row in as_list(rows)]
    return {
        "headers": headers,
        "rows": [[item.get(field, "") for field in fields] for item in items],
        "empty_state": empty_state,
    }


def warnings_table(warnings: object) -> dict[str, object]:
    rows = [[text(item)] for item in as_list(warnings) if text(item)]
    return {
        "headers": ["Warning"],
        "rows": rows,
        "empty_state": "No multi-model warnings are available.",
    }


def baseline_table(baseline: dict[str, Any]) -> dict[str, object]:
    if not baseline:
        rows: list[list[object]] = []
    else:
        rows = [
            [
                baseline.get("model_name", "official_recommendation_model"),
                baseline.get("model_version", ""),
                baseline.get("official_status", "official"),
                baseline.get("shadow_model_count", 0),
                baseline.get("official_recommendations_unchanged", True),
            ]
        ]
    return {
        "headers": ["Model", "Version", "Status", "Shadow Models", "Official Recommendations Unchanged"],
        "rows": rows,
        "empty_state": "No official baseline comparison is available yet.",
    }


def build_multi_model_competition_view(context: dict[str, object]) -> dict[str, object]:
    review = as_dict(context.get("multi_model_competition"))
    active_models = as_dict(review.get("active_shadow_models"))
    baseline = as_dict(review.get("official_baseline_comparison"))
    shadow_runs = as_dict(review.get("shadow_recommendations"))
    scoreboard = as_dict(review.get("model_competition_scoreboard"))
    debate = as_dict(review.get("debate_packet_summary"))
    readiness = as_dict(review.get("promotion_readiness_summary"))
    warnings = as_list(review.get("warnings"))
    return {
        "review_only": review.get("review_only", True),
        "shadow_only": review.get("shadow_only", True),
        "no_auto_promotion": review.get("no_auto_promotion", True),
        "note": text(review.get("note"), DISPLAY_NOTE),
        "cards": [
            {
                "label": "Active shadow models",
                "value": active_models.get("model_count", 0),
                "detail": "Registered comparison models; none are authoritative.",
            },
            {
                "label": "Official baseline",
                "value": text(baseline.get("model_version"), "n/a"),
                "detail": "Official recommendations remain the baseline.",
            },
            {
                "label": "Shadow runs",
                "value": shadow_runs.get("run_count", 0),
                "detail": "Deterministic shadow outputs generated from current context.",
            },
            {
                "label": "Debate packets",
                "value": debate.get("packet_count", 0),
                "detail": "Model disagreement summaries for review.",
            },
            {
                "label": "No auto promotion",
                "value": str(review.get("no_auto_promotion", True)),
                "detail": "Promotion readiness is a review queue only.",
            },
        ],
        "active_models": rows_table(
            active_models.get("rows"),
            ["Model", "Version", "Role", "Promotion Status", "Modes"],
            ["model_name", "model_version", "model_role", "promotion_status", "allowed_decision_modes"],
            text(active_models.get("empty_state"), "No shadow models are registered yet."),
        ),
        "baseline": baseline_table(baseline),
        "shadow_outputs": rows_table(
            shadow_runs.get("rows"),
            ["Model", "Symbol", "Shadow Action", "Shadow Score", "Confidence", "Horizon", "Official Action"],
            ["model_name", "symbol", "shadow_action", "shadow_score", "confidence", "horizon", "official_action"],
            text(shadow_runs.get("empty_state"), "No shadow recommendation rows are available yet."),
        ),
        "scoreboard": rows_table(
            scoreboard.get("rows"),
            ["Rank", "Model", "Status", "Mode", "Horizon", "Sample", "Score", "Warnings"],
            ["rank", "model_name", "status", "decision_mode", "horizon", "sample_size", "score", "warnings"],
            text(scoreboard.get("empty_state"), "No model competition scoreboard rows are available yet."),
        ),
        "debate": rows_table(
            debate.get("rows"),
            ["Symbol", "Models Compared", "Consensus", "Dominant Stance", "Disagreement"],
            ["symbol", "models_compared", "consensus_status", "dominant_stance", "disagreement_status"],
            text(debate.get("empty_state"), "No model debate packets are available yet."),
        ),
        "readiness": rows_table(
            readiness.get("rows"),
            ["Model", "Version", "Readiness", "Score", "Sample", "Human Review Action", "No Auto Promotion"],
            [
                "model_name",
                "model_version",
                "label",
                "readiness_score",
                "sample_size",
                "recommended_action",
                "no_auto_promotion",
            ],
            text(readiness.get("empty_state"), "No promotion-readiness rows are available yet."),
        ),
        "warnings": warnings_table(warnings),
    }
