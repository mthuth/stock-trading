# Model Learning Strategy

This document captures the long-term learning vision for the stock-trading app. It is strategy only. Feedback, outcomes, AI thesis reviews, and model comparisons are review-only until a future explicit model-impact phase approves otherwise.

## Why Learning Matters

The app should evolve from a research generator into a learning decision system. It should help answer:

- Did the app's recommendations help?
- Which recommendations worked?
- Which blocked recommendations were correctly blocked?
- Which watchlist names later became buy-ready?
- Which catalysts actually mattered?
- Which sources produced useful or noisy signals?
- Did decision safety improve or hurt outcomes?

Learning must not become automatic score tuning. The system should first observe, measure, and explain.

## Prediction Records

Every recommendation should eventually create a prediction record.

Required prediction fields:

- `prediction_id`
- `recommendation_run_id`
- `symbol`
- `model_name`
- `model_version`
- `decision_mode`
- `horizon`
- `expected_direction`
- `expected_return_low`
- `expected_return_high`
- `confidence`
- `thesis`
- `risks`
- `invalidation_conditions`
- `created_at`
- `outcome_status`
- `actual_return`
- `evaluated_at`

Prediction records should be immutable enough to audit what the model expected at the time. Later outcomes should be appended or linked, not used to rewrite the original prediction.

## Outcome Evaluation

Outcome evaluation should compare expected outcomes with actual outcomes over the relevant horizon.

Evaluation should include:

- Actual return.
- Benchmark return.
- Excess return versus benchmark.
- Drawdown.
- Target progress.
- Whether thesis catalysts happened.
- Whether risks or invalidation conditions occurred.
- Whether provider/source gaps affected the original decision.

Outcome evaluation must remain review-only until a future model-tuning phase is explicitly approved.

## Model Trust Score

A future Model Trust Score should consider:

- Hit rate.
- Excess return versus benchmark.
- Drawdown control.
- Target progress.
- Decision-safety effectiveness.
- Source usefulness.
- AI thesis accuracy.
- Sample size.
- Consistency over time.

Trust score should be conservative when sample size is small or results are concentrated in one market regime.

See [Wave 11 Model Evaluation Requirements](WAVE11_MODEL_EVALUATION_REQUIREMENTS.md) before implementing prediction records, backtest summaries, benchmark comparisons, or model trust score v1 behavior.

## Model Trust Levels

1. Observe
   - Model outputs are tracked but not relied on for behavior changes.
   - Current default for new learning loops and shadow models.

2. Assist
   - Model outputs can shape review priorities and explanations.
   - Official scores/actions still remain controlled by approved rules.

3. Lean In
   - Model has enough outcome evidence to influence future model-impact proposals.
   - Requires explicit approval before affecting official recommendations.

4. Aggressive
   - Long-term aspirational level after strong evidence across regimes.
   - Requires separate model-promotion decision and regression proof.

## AI Thesis Evaluation

AI briefs should produce source-backed thesis expectations:

- Bull case.
- Bear case.
- Expected outcome range.
- Key evidence.
- Weak or uncorroborated evidence.
- What would change the view.
- Invalidation conditions.

Later evaluation should ask whether the AI thesis was directionally useful, overconfident, under-supported, stale, or contradicted by later evidence.

AI thesis quality must not directly change official score, action, target, confidence, suggested amount, or decision gate without a future explicit model-impact requirement.

## Source Usefulness

Source usefulness should measure whether a source produced helpful, timely, corroborated signals.

Useful source signals may include:

- Early evidence that later mattered.
- Accurate catalyst framing.
- Reliable primary-source coverage.
- Good analyst/industry context.
- Repeated noisy or misleading claims.
- Stale, blocked, or low-corroboration evidence.

Source usefulness should remain review-only until a future source-weighting model-impact phase is approved.

## Decision Safety Effectiveness

Decision safety should be evaluated as a gate, not assumed perfect.

Questions to track:

- Did blocked candidates later perform poorly, validating the block?
- Did blocked candidates later outperform, suggesting the gate was too strict?
- Which reasons drove good blocks or missed upside?
- Did missing price, low target confidence, provider gaps, watchlist policy, or allocation safety matter most?

Safety gates should start stricter while trust is built, then become more aggressive only after outcome evidence supports it.

## Multi-Model Shadow Competition

Future models should compete in shadow mode only.

Shadow models may compare:

- Alternative scoring formulas.
- Different target-confidence thresholds.
- Different source-weighting approaches.
- AI thesis confidence variants.
- Tactical versus long-term modes.

Shadow output must never change official recommendations by itself.

## Rules Before Feedback Can Affect Recommendations

Feedback can affect official recommendations only after all are true:

1. Feedback and outcomes have enough sample size.
2. The effect is measurable against a benchmark.
3. The proposed behavior is documented in requirements.
4. Regression tests prove the change is intentional.
5. The model-impact PR explicitly states what changed.
6. The user approves the model-promotion or tuning decision.

Until then, feedback and outcomes are review-only.

## Future Promotion/Demotion Of Models

Model promotion should be explicit and reversible.

Promotion should require:

- Sufficient sample size.
- Better risk-adjusted outcomes than the current model.
- No unacceptable drawdown behavior.
- Strong source attribution and explainability.
- Evidence that the model performs across regimes.
- Clear rollback path.

Model demotion should occur when a model is noisy, overfits, weakens decision safety, or produces worse outcomes than the official model.
