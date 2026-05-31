# Wave 11 Model Evaluation And Backtesting Requirements

Wave 11 defines the Model Evaluation and Backtesting layer. This document is requirements-only for fixture and test-harness alignment. It does not authorize a backtest engine implementation in this branch and does not change scoring formulas, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, AI generation, dashboard rendering, storage schema, broker behavior, or trading behavior.

## Product Goal

Wave 11 should make the app better at answering:

- Did the app's recommendations work?
- Did long-term buy/add calls beat relevant benchmarks?
- Did tactical setups work over their intended horizons?
- Did earnings event reviews identify useful opportunities or risks?
- Did AI theses predict what actually happened?
- Did decision-safety gates avoid downside or miss upside?
- Which sources and catalysts were associated with useful recommendations?
- Which model version performed better?
- Is there enough evidence to trust the model more?

Model evaluation is a review-only learning layer. It should measure, compare, and explain historical outcomes without changing official recommendations or tuning the model automatically.

## Non-Goals

Wave 11 must not add:

- Automatic trading.
- Order preview.
- Broker write actions.
- Automatic model tuning.
- Automatic score changes.
- Automatic target changes.
- Automatic decision-safety changes.
- Automatic source-weight changes.
- Automatic recommendation changes from feedback or outcomes.
- Model promotion into official recommendations.
- Claims that simulated or historical performance guarantees future performance.

Wave 11 may add requirements for prediction records, model version tracking, backtest summaries, benchmark comparisons, model trust score v1, performance review artifacts, and shadow-model evaluation scaffolding. Those outputs remain review-only.

## Prediction Record Requirements

Prediction records should capture what the system knew and expected at the historical decision time.

Required fields:

- `prediction_id`
- `recommendation_run_id`
- `symbol`
- `company`
- `model_name`
- `model_version`
- `model_role`
- `decision_mode`
- `horizon`
- `created_at`
- `decision_date`
- `official_action`
- `score`
- `target_price`
- `target_confidence`
- `decision_gate_status`
- `expected_direction`
- `expected_return_low`
- `expected_return_high`
- `confidence`
- `thesis`
- `risks`
- `invalidation_conditions`
- `evidence_ids`
- `source_ids`
- `data_available_as_of`
- `outcome_status`
- `evaluated_at`

Prediction records should be immutable enough to audit what the model expected at the time. Later outcomes should be appended, linked, or summarized separately. They must not rewrite the original prediction.

## Model Version Requirements

Model evaluation must distinguish:

- Official model versus shadow models.
- Model name and version.
- Decision mode and horizon.
- Configuration snapshot or config hash where available.
- Recommendation run ID or report context artifact used.
- Whether a model version is missing or unknown.

Missing model version should produce a warning and lower model trust confidence. It must not block review entirely if the historical recommendation can still be identified.

## Backtest Validity Guardrails

Backtesting must avoid misleading results.

Guardrails:

- Do not use data that was unavailable at the historical decision time.
- Distinguish stored historical recommendations from current generated recommendations.
- Distinguish official model outputs from shadow model outputs.
- Benchmark comparisons must use benchmark data available for the same date windows.
- Missing data must produce warnings instead of optimistic assumptions.
- Preserve original universe membership where possible to avoid survivorship bias.
- Avoid look-ahead bias in recommendations, benchmarks, target data, earnings evidence, AI briefs, and source/catalyst evidence.
- Avoid overfitting by treating small samples, concentrated symbols, or one market regime as low-confidence.
- Results are review-only and must not change official recommendations.

Any backtest output should clearly state the evaluation window, sample size, data completeness, warning count, and whether enough evidence exists to trust the conclusion.

## Benchmark Comparison Requirements

Benchmark comparisons should use the same date windows as the evaluated recommendation or setup.

Required fields:

- `benchmark_id`
- `benchmark_symbol`
- `benchmark_name`
- `benchmark_return`
- `comparison_window_start`
- `comparison_window_end`
- `excess_return`
- `benchmark_data_status`
- `benchmark_warning`

Benchmark missing or stale states should produce `benchmark_data_missing` or related warnings. The evaluator must not assume zero benchmark return.

## Recommendation Backtest Requirements

Long-term recommendation evaluation should compare:

- Official action at decision time.
- Decision mode and horizon.
- Later price movement over the intended horizon.
- Benchmark return over the same horizon.
- Excess return.
- Drawdown.
- Target progress where target data was available at decision time.
- Decision-safety status and blocked reasons.
- Provider/source gaps present at decision time.

Recommendation backtests must distinguish long-term buy/add calls from tactical setups and earnings review metadata.

## Tactical Setup Backtest Requirements

Tactical setup evaluation should use the intended tactical horizon from the historical setup.

It should track:

- Setup type.
- Review action.
- Intended horizon.
- Invalidation conditions.
- Whether confirmation appeared.
- Outcome over the intended horizon.
- Whether the setup worked, failed, or lacks enough data.

Tactical setup outcomes must not alter long-term capital deployment recommendations or official labels.

## Earnings Review Backtest Requirements

Earnings review evaluation should track whether pre-earnings and post-earnings review signals were useful.

It should compare:

- Pre-earnings review action.
- Post-earnings evidence.
- Revenue, EPS, guidance, margins, AI/capex commentary, risk language, and market reaction where available.
- Whether the review identified an opportunity, a warning, or a keep-watching case.
- Later movement over an event-specific window.

Earnings review backtests must remain review-only and must not change official scores, targets, actions, target confidence, decision safety, allocation, or source weights.

## AI Thesis Evaluation Requirements

AI thesis evaluation should compare source-backed AI thesis claims with later evidence.

It should track:

- Brief ID or thesis ID.
- AI status at creation: draft, reviewed, rejected, or guardrail-blocked.
- Evidence IDs cited at creation time.
- Bull case, bear case, and expected outcome range.
- What would change the view.
- Later evidence status: validated, contradicted, mixed, missing, or not enough history.
- Whether the thesis was overconfident, under-supported, stale, or useful.

AI thesis evaluation must not change official score, action, target, target confidence, suggested amount, decision gate, watchlist eligibility, provider behavior, source weights, broker behavior, or trading behavior.

## Model Trust Score V1 Requirements

Model trust score v1 should be conservative and review-only.

Inputs may include:

- Sample size.
- Hit rate.
- Excess return versus benchmark.
- Drawdown control.
- Target progress.
- Decision-safety effectiveness.
- Tactical setup outcome quality.
- Earnings review usefulness.
- Source usefulness.
- Catalyst follow-through.
- AI thesis accuracy.
- Data completeness.
- Market-regime coverage.

Outputs should include:

- `trust_score`
- `trust_level`
- `sample_size`
- `confidence`
- `warnings`
- `drivers`
- `review_only`

Trust levels should align with the strategy levels in `docs/MODEL_LEARNING_STRATEGY.md`: `observe`, `assist`, `lean_in`, and `aggressive`. Wave 11 should default to `observe` when sample size is small, model version is missing, benchmark data is missing, or results are concentrated.

Model trust score v1 must not promote a model, change official recommendations, tune scoring, or alter source weights.

## Shadow-Model Evaluation Boundaries

Shadow models may be compared to the official model in review-only mode.

Rules:

- Shadow outputs are non-authoritative.
- Official recommendation label, score, target, target confidence, suggested amount, allocation, and decision safety remain unchanged.
- Shadow comparisons must use the same historical information window as the official model.
- Any future model promotion requires a separate explicit model-impact requirement, regression evidence, and user approval.

## Acceptance Criteria

- Requirements doc is clear and Codex-readable.
- Fixture scenarios cover long-term benchmark outperformance, long-term benchmark underperformance, blocked recommendation later declined, blocked recommendation later rose, tactical setup worked, tactical setup failed, earnings review improved after post-earnings evidence, AI thesis validated, AI thesis contradicted, not enough historical data, benchmark data missing, and model version missing.
- Fixture tests validate prediction record fields, model version fields, benchmark comparison fields, validity guardrails, review-only behavior, model trust score fields, warnings, and scenario-specific outcomes.
- Tests do not require live provider calls, broker access, model calls, report rendering, storage schema changes, or model evaluation implementation modules.
- No product behavior changes.
- No scoring, target, recommendation-label, decision-safety, allocation, provider-ingestion, dashboard, storage, broker, or trading behavior changes.

## Fixture Scenarios

Fixture scenarios live in `tests/fixtures/model_evaluation/`.

Required scenarios:

| Scenario | Fixture | Purpose |
| --- | --- | --- |
| Long-term recommendation beats benchmark | `long_term_beats_benchmark.json` | Long-term buy/add outperforms benchmark over the intended horizon. |
| Long-term recommendation underperforms benchmark | `long_term_underperforms_benchmark.json` | Long-term buy/add trails benchmark and lowers trust confidence. |
| Blocked recommendation later declines | `blocked_recommendation_later_declines.json` | Decision-safety block appears useful after later downside. |
| Blocked recommendation later rises | `blocked_recommendation_later_rises.json` | Decision-safety block may have missed upside. |
| Tactical setup works over intended horizon | `tactical_setup_works.json` | Tactical setup is evaluated over its stated horizon. |
| Tactical setup fails | `tactical_setup_fails.json` | Tactical setup fails or invalidates over its stated horizon. |
| Earnings review improves after post-earnings evidence | `earnings_review_improves_after_post_earnings.json` | Earnings review identifies a useful opportunity or risk after evidence arrives. |
| AI thesis validated by later evidence | `ai_thesis_validated.json` | Later evidence supports a source-backed AI thesis. |
| AI thesis contradicted by later evidence | `ai_thesis_contradicted.json` | Later evidence contradicts or weakens a source-backed AI thesis. |
| Not enough historical data | `not_enough_historical_data.json` | Evaluation remains inconclusive because sample/history is too small. |
| Benchmark data missing | `benchmark_data_missing.json` | Missing benchmark data produces warnings instead of optimistic assumptions. |
| Model version missing | `model_version_missing.json` | Missing model version produces warnings and lower trust confidence. |

These fixtures are contract examples. Later implementation branches should either consume them directly or add behavior-level fixtures that preserve these scenario labels, anti-bias guardrails, and review-only behavior.

## Future Integration Notes

Future Wave 11 implementation should prefer focused helper modules and fixture-driven tests before broad report, dashboard, local-console, storage, or workflow changes.

Likely follow-up branches:

- `codex/prediction-records-v1`
- `codex/backtest-summary-v1`
- `codex/model-trust-score-v1`
- `codex/shadow-model-evaluation`
- `codex/model-evaluation-console-panel`

Any future integration must keep model evaluation as a review surface. Model promotion, source-weight changes, score changes, target changes, decision-safety changes, and official recommendation changes require separate explicit model-impact approval.
