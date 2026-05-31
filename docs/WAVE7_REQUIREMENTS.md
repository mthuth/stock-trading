# Wave 7 Requirements

Wave 7 builds the Long-Term Capital Deployment layer. This document defines the intended behavior before dashboard or report-context integration. It is requirements-only and does not change scoring, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, dashboard rendering, storage schema, broker behavior, or trading behavior.

## Product Goal

Wave 7 should make the app better at answering:

> What should I buy/add today, especially for long-term holdings?

The first useful answer should identify the best long-term add, show whether it is decision-safe, explain how much capital could be considered under existing safety/allocation rules, and show the backup long-term add when the top idea is blocked.

## Non-Goals

Wave 7 must not add:

- Automatic trading.
- Broker write actions.
- Order preview.
- Short selling.
- Tactical same-day trading.
- Automatic model tuning.
- Automatic source-weight changes.
- Automatic score, target, target-confidence, decision-safety, allocation, or provider-behavior changes from outcomes or AI.

Wave 7 must preserve the controlled recommendation labels: `Strong Buy`, `Buy`, `Add`, `Hold`, `Watch`, `Trim`, and `Avoid`.

## Capital Deployment User Story

As the user reviewing the daily report, I want to know whether long-term buy capacity should be deployed or held today, so I can make a manual decision with the best available context.

The daily review should show:

- Best long-term add candidate.
- Decision-safety status and blocked reasons.
- Target confidence and target-source quality.
- Allocation safety and position-cap effects.
- Capital availability status.
- Suggested amount as review context only.
- Backup safe long-term add when the top candidate is blocked.
- Data/provider/evidence gaps that explain why capital may be held.

## Long-Term Add Queue Requirements

The long-term add queue should:

- Use the `long_term_buy_add` decision mode.
- Prioritize the `long_term_core` sleeve.
- Exclude tactical trades, ETFs using deferred ETF logic, speculative watchlist-only names, and future short candidates from the primary long-term add answer.
- Preserve existing scores, actions, target confidence, decision safety, and allocation logic.
- Show `candidate_role` values such as `top_candidate`, `fallback_candidate`, or `blocked_candidate` as review metadata, not new recommendation labels.
- Keep suggested amount at zero when decision safety blocks the candidate.
- Keep suggested amount at zero when capital availability is missing or unavailable.

## Fallback Add Requirements

When the top-ranked long-term candidate is blocked, Wave 7 should show the best safe fallback candidate if one exists.

Fallback display should:

- Preserve the top-ranked candidate and explain why it is blocked.
- Identify the highest-ranked safe long-term add candidate as fallback.
- Keep the top blocked candidate's suggested amount at zero.
- Use existing action labels and decision-gate status rather than inventing a new action.
- Explain when no safe fallback exists.

## Capital Deployment Context Requirements

Capital deployment context should start with manual/configured inputs:

- Monthly buy capacity.
- Manual available cash, if provided.
- As-of date.
- Source such as `configured`, `manual`, or future optional `broker_read_only_snapshot`.
- Notes that the context is recommendation-only.

Capital deployment context should answer:

- Is capital available?
- Is capital availability missing?
- Is capacity held because no candidate is decision-safe?
- Is capacity reduced by allocation safety?
- Is the remaining capacity better held for later review?

Broker integration remains deferred and read-only. No Wave 7 branch may add broker writes, order preview, order placement, order modification, or automatic execution.

## Long-Term Holding Health V1 Requirements

Long-term holding health should start as review context, not sell/trim instructions.

Holding health v1 should classify holdings as:

- `healthy`: thesis and evidence remain acceptable.
- `watch`: monitor because confidence, source quality, or momentum weakened.
- `needs_review`: review because material gaps, allocation pressure, thesis weakness, or safety issues exist.

Holding health must not create a `sell_now` instruction. Any future Trim/Sell work must be separately scoped and tested.

## Acceptance Criteria

- Wave 7 requirements are explicit and Codex-readable.
- Scenario fixtures cover safe add, blocked fallback, all blocked, missing capital, allocation cap reduction, healthy holding, and holding needs review.
- Fixture tests validate structure, labels, guardrails, decision mode, sleeve, capital status, and expected scenario outcomes.
- Tests do not require live provider calls, broker access, report rendering, or new feature modules.
- No app behavior changes.
- No scoring, target, decision-safety, allocation, provider, dashboard, storage, broker, or trading behavior changes.

## Review-Only And Recommendation-Only Guardrails

All Wave 7 outputs are review context. They must not:

- Place trades.
- Preview orders.
- Write to broker accounts.
- Alter official scores, actions, targets, target confidence, suggested amounts, decision gates, source weights, or provider behavior from AI or outcomes.
- Hide provider/source gaps that affect confidence.
- Convert manual journal or outcome data into automatic recommendations.

## Fixture Scenarios

Fixture scenarios live in `tests/fixtures/wave7/`.

Required scenarios:

| Scenario | Fixture | Purpose |
| --- | --- | --- |
| Clear safe long-term add | `clear_safe_long_term_add.json` | Top long-term core candidate is decision-safe with deployable capacity. |
| Top candidate blocked with safe fallback | `top_blocked_safe_fallback.json` | Top idea remains visible as blocked and fallback candidate is safe. |
| All candidates blocked | `all_candidates_blocked.json` | Capital is held because no long-term candidate is decision-safe. |
| Missing capital availability | `missing_capital_availability.json` | Candidate may be decision-safe, but deployment amount is zero until capital context exists. |
| Allocation cap reduces amount | `allocation_cap_reduces_amount.json` | Existing allocation rules reduce suggested amount below monthly capacity. |
| Long-term holding healthy | `long_term_holding_healthy.json` | Holding health review marks a core holding healthy without changing recommendations. |
| Long-term holding needs review | `long_term_holding_needs_review.json` | Holding health review flags review needs without issuing sell-now language. |

These fixtures are contract examples. Later implementation branches should either consume them directly or add behavior-level fixtures that preserve these scenario labels and guardrails.
