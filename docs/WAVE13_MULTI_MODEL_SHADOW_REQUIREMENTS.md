# Wave 13 Multi-Model Shadow Competition Requirements

Wave 13 defines the Multi-Model Shadow Competition layer. This document is requirements-only for fixture and test-harness alignment. It does not authorize a shadow model engine implementation in this branch and does not change scoring formulas, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, AI generation, dashboard rendering, storage schema, broker behavior, or trading behavior.

## Product Goal

Wave 13 should make the app better at answering:

- Can multiple models produce competing recommendations in shadow mode?
- Which model performs best by horizon, sleeve, decision mode, and market condition?
- Which model is better for long-term adds?
- Which model is better for tactical setups?
- Which model is better around earnings events?
- Which model avoids downside better?
- Which model misses less upside?
- Which model explains risk better?
- Which model should remain shadow-only?
- Which model may eventually deserve promotion review?

Multi-model competition is a review-only learning layer. It should compare alternative model outputs against the official baseline without making any shadow model authoritative.

## Non-Goals

Wave 13 must not add:

- Automatic trading.
- Order preview.
- Broker write actions.
- Automatic model promotion.
- Automatic official recommendation changes.
- Automatic scoring changes.
- Automatic target changes.
- Automatic decision-safety changes.
- Automatic allocation changes.
- Automatic source-weight changes.
- Live model calls in tests.
- Live provider calls in tests.
- Claims that backtested or shadow performance guarantees future performance.

Wave 13 may define shadow model roles, shadow output contracts, model comparison scoreboards, model debate packets, promotion-readiness reviews, and shadow-versus-official comparison artifacts. Those outputs remain review-only and shadow-only.

## Model Roles

Supported roles:

| Role | Purpose |
| --- | --- |
| `official_baseline` | The current official recommendation output used as the comparison baseline. |
| `conservative_long_term` | A long-term model that prioritizes drawdown control, data completeness, and decision-safety strictness. |
| `aggressive_growth` | A long-term growth model that tolerates more volatility and missed-data warnings in exchange for upside review. |
| `tactical_momentum` | A short-horizon model for tactical momentum or breakout review, separate from long-term deployment. |
| `earnings_event` | A model focused on pre-earnings and post-earnings review windows. |
| `risk_skeptic` | A model that emphasizes downside, invalidation conditions, and weak evidence. |
| `ai_thesis` | A source-backed AI-thesis model used only for explanatory comparison. |
| `source_quality_weighted` | A model that gives more review weight to corroborated, primary, timely sources. |
| `decision_safety_strict` | A stricter decision-safety variant for measuring avoided downside. |
| `decision_safety_loose` | A looser decision-safety variant for measuring missed upside risk. |

Only `official_baseline` may represent the official model state. All other roles are shadow-only even when their simulated results outperform the baseline.

## Shadow Model Output Contract

Each shadow output should be deterministic and auditable.

Required fields:

- `shadow_run_id`
- `model_id`
- `model_role`
- `model_name`
- `model_version`
- `official_status`
- `decision_mode`
- `horizon`
- `sleeve`
- `market_condition`
- `symbol`
- `company`
- `shadow_action`
- `shadow_score`
- `shadow_target`
- `shadow_target_confidence`
- `decision_gate_view`
- `safe_to_buy_view`
- `expected_return`
- `excess_return`
- `drawdown`
- `avoided_downside`
- `missed_upside`
- `risk_explanation_score`
- `thesis`
- `risk_explanation`
- `evidence_ids`
- `source_ids`
- `data_available_as_of`
- `warnings`
- `promotion_claim`
- `review_only`
- `shadow_only_note`

Shadow actions should be clearly labeled as shadow outputs. They must not be written back into official recommendation labels, scores, target prices, target confidence, suggested amounts, allocation decisions, or decision-safety gates.

## Official-Vs-Shadow Boundary

The official baseline is the only authoritative recommendation path.

Rules:

- Official recommendation label, score, target, target confidence, suggested amount, allocation notes, and decision gate status remain unchanged by shadow outputs.
- Shadow outputs may disagree with the official baseline, but disagreement is review context only.
- Shadow models may be ranked, compared, debated, or marked for promotion review, but they cannot promote themselves.
- A shadow model that claims official status must be rejected and flagged.
- AI-thesis shadow outputs must stay explanatory and source-backed.

## Shadow Recommendation Requirements

Shadow recommendations should capture what the model would have said at decision time.

They should include:

- Decision mode and horizon.
- Sleeve or portfolio context where applicable.
- The same decision-time data window used by the official model.
- Expected return range or direction.
- Risk and invalidation conditions.
- Evidence and source references.
- Data gaps and warnings.
- Whether the output is long-term, tactical, earnings-event, or thesis-review oriented.
- A review-only note that the output does not change official recommendations.

Shadow recommendation runners in future implementation branches must not call live providers or live LLMs in tests. Fixture-backed or stored historical inputs are required for deterministic test coverage.

## Model Comparison Requirements

Model comparison should evaluate role performance by:

- Horizon.
- Sleeve.
- Decision mode.
- Market condition.
- Benchmark-relative return.
- Drawdown.
- Downside avoided.
- Upside missed.
- Risk explanation quality.
- Source/evidence quality.
- Sample size.
- Data completeness.

Comparison outputs should include warnings when sample size is too small, benchmark data is missing, model version is missing, results are concentrated in one symbol or regime, or the comparison may be biased by survivor-only data.

## Model Debate Requirements

Model debate packets should organize disagreements without creating official instructions.

Each debate packet should include:

- Models being compared.
- Points of agreement.
- Points of disagreement.
- Evidence cited by each model.
- Risks or invalidation conditions raised by each model.
- Whether the disagreement is about horizon, source quality, target confidence, decision safety, or risk tolerance.
- What later evidence would resolve the disagreement.
- A review-only conclusion.

Debate packets must not tell the user to place a trade, preview an order, or treat a shadow model as authoritative.

## Model Promotion-Readiness Requirements

Promotion readiness is a review queue, not promotion.

A model may be marked `promotion_review_candidate` only when:

- Sample size is sufficient for the role and horizon.
- Benchmark comparisons are available for the evaluated window.
- Drawdown is acceptable relative to the official baseline.
- The model does not hide data gaps or weak evidence.
- The model explains risk clearly.
- The model performs across more than one symbol and market condition.
- The promotion review includes a rollback plan and explicit regression scope.

Even when these criteria are met, promotion requires a future explicit model-impact requirement, regression evidence, user approval, and a separate PR. Wave 13 must not promote models automatically.

## Evaluation And Bias Guardrails

Multi-model evaluation must avoid misleading results.

Guardrails:

- Do not use data that was unavailable at the historical decision time.
- Distinguish official recommendations from shadow recommendations.
- Distinguish evaluation data from decision-time input data.
- Distinguish official model versions from shadow model versions.
- Benchmark comparisons must use benchmark data available for the same date windows.
- Missing data must produce warnings instead of optimistic assumptions.
- Warn when sample size is too small.
- Warn when benchmark data is missing.
- Warn when model version is missing.
- Warn when results may be biased by survivor-only data.
- Warn when outcomes are concentrated in one symbol, sleeve, horizon, or market regime.
- Never present shadow performance as guaranteed future performance.

## Acceptance Criteria

- Requirements doc is clear and Codex-readable.
- Fixture scenarios cover official model wins, aggressive model wins with higher drawdown, conservative model avoids downside, tactical model works short-term but fails long-term, earnings model works only around earnings window, risk skeptic blocks a losing idea, AI thesis model overstates confidence, source-quality model avoids noisy evidence, insufficient sample size, missing benchmark data, and shadow model claiming official status is rejected.
- Fixture tests validate role coverage, output-contract fields, official-versus-shadow boundaries, guardrails, warnings, promotion readiness states, debate packets, and review-only behavior.
- Tests do not require live provider calls, broker credentials, live model calls, report rendering, storage schema changes, dashboard changes, or shadow model implementation modules.
- No product behavior changes.
- No scoring, target, recommendation-label, decision-safety, allocation, provider-ingestion, AI-generation, dashboard, storage, broker, or trading behavior changes.

## Fixture Scenarios

Fixture scenarios live in `tests/fixtures/shadow_models/`.

Required scenarios:

| Scenario | Fixture | Purpose |
| --- | --- | --- |
| Official model wins | `official_model_wins.json` | Official baseline outperforms reviewed shadow alternatives. |
| Aggressive model wins but with higher drawdown | `aggressive_model_wins_higher_drawdown.json` | Aggressive growth wins on return but carries worse drawdown warnings. |
| Conservative model avoids downside | `conservative_model_avoids_downside.json` | Conservative model avoids a loss the baseline accepted. |
| Tactical model works short-term but fails long-term | `tactical_model_short_term_only.json` | Tactical model works over its intended horizon but should not affect long-term recommendations. |
| Earnings model works only around earnings window | `earnings_model_window_only.json` | Earnings model value is limited to the event window. |
| Risk skeptic blocks a losing idea | `risk_skeptic_blocks_losing_idea.json` | Risk skeptic flags downside that later appears. |
| AI thesis model overstates confidence | `ai_thesis_overstates_confidence.json` | AI-thesis model is useful for explanation but overstates certainty. |
| Source-quality model avoids noisy evidence | `source_quality_avoids_noisy_evidence.json` | Source-quality weighting avoids weak or noisy evidence. |
| Insufficient sample size | `insufficient_sample_size.json` | Comparison remains inconclusive because sample size is too small. |
| Missing benchmark data | `missing_benchmark_data.json` | Missing benchmark data produces warnings instead of optimistic assumptions. |
| Shadow model tries to claim official status and is rejected | `shadow_claims_official_rejected.json` | Shadow model self-promotion is rejected and flagged. |

These fixtures are contract examples. Later implementation branches should either consume them directly or add behavior-level fixtures that preserve these scenario labels, role boundaries, warnings, promotion-readiness states, and shadow-only guardrails.

## Future Integration Notes

Future Wave 13 implementation should prefer focused helper modules and fixture-driven tests before report, dashboard, local-console, storage, workflow, or model-runner changes.

Likely follow-up branches:

- `codex/shadow-model-output-contract`
- `codex/shadow-recommendation-runner`
- `codex/model-comparison-scoreboard`
- `codex/model-debate-packets`
- `codex/model-promotion-readiness-review`
- `codex/local-console-shadow-model-section`

Any future shadow-model runner must keep official recommendations unchanged unless a later model-impact phase explicitly approves promotion. Shadow outputs remain review-only and shadow-only.
