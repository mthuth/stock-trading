# Wave 10 Tactical Trade Review Requirements

Wave 10 defines the Tactical Trade Review layer. This document is requirements-only for fixture and test-harness alignment. It does not authorize tactical scoring implementation in this branch and does not change scoring formulas, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, AI generation, dashboard rendering, storage schema, broker behavior, or trading behavior.

## Product Goal

Wave 10 should make the app better at answering:

- Is there a short-term setup worth reviewing?
- Is the setup same-day, same-week, or same-month?
- What is the setup type: momentum, pullback, breakout, reversal, post-earnings reaction, pre-earnings setup, or news/catalyst?
- What is the review action: watch, avoid, wait, tactical buy review, tactical sell review, or hold?
- What invalidates the setup?
- What risk zone should be reviewed?
- Did prior tactical setups work?

Tactical review is a decision-support layer. It must remain recommendation-only and review-only. It should help the user review short-duration setups manually without creating a trading system.

## Non-Goals

Wave 10 must not add:

- Automatic trading.
- Order preview.
- Broker write actions.
- Short selling execution.
- Margin or account logic.
- Real-time trading console behavior.
- Automatic score changes.
- Automatic target changes.
- Automatic decision-safety changes.
- Automatic model tuning.
- Automatic source-weight changes.
- Broker credential requirements.
- Tactical overrides of long-term capital deployment.
- Tactical overrides of official recommendations.

The layer must not imply guaranteed performance, target achievement, or risk-free outcomes.

## Tactical Modes

The tactical layer should use `tactical_trade` as a separate decision mode.

Tactical review should be separate from:

- `long_term_buy_add`
- `long_term_hold_health`
- `earnings_event`
- `speculative_watchlist`
- `etf_context`
- `future_short_candidate`

Tactical review rows may reference existing official recommendations for context, but they must not mutate those recommendations.

## Tactical Horizons

Supported tactical horizons:

- `same_day`
- `1_to_5_days`
- `5_to_20_days`
- `20_to_60_days`

The horizon should describe the review window, not a promise to act or an automated holding period.

## Tactical Setup Types

Supported setup types:

- `breakout_review`
- `pullback_review`
- `momentum_review`
- `reversal_review`
- `post_earnings_reaction_review`
- `pre_earnings_setup_review`
- `news_catalyst_review`
- `avoid_or_wait`

Each setup should include a concise thesis, supporting evidence, uncertainty, and what would invalidate the setup.

## Tactical Review Actions

Supported review actions:

- `tactical_buy_review`
- `tactical_sell_review`
- `wait_for_confirmation`
- `watch_intraday`
- `avoid_for_now`
- `hold_existing`
- `data_gap_review`

These are review actions only. They are not order instructions. `tactical_sell_review` is a review label for an existing position or risk review; it must not imply short selling execution, broker order routing, or margin behavior.

## Risk Zone Requirements

Each tactical setup should include a risk-zone section with:

- `risk_level`
- `review_zone`
- `downside_reference`
- `upside_reference`
- `volatility_context`
- `liquidity_context`
- `position_context`
- `notes`

Risk levels should be stable values such as `low`, `moderate`, `elevated`, `high`, or `not_applicable`.

Risk zones should explain what the user should review before acting manually. They must not produce broker-ready prices, order tickets, stop orders, limit orders, or automated execution instructions.

## Invalidation Requirements

Each setup should include:

- `invalidates_if`
- `confirmation_needed`
- `time_stop`
- `data_gaps`

Invalidation should say what would weaken or cancel the review thesis. It must not create automated stop-loss behavior, automatic sell behavior, or order-management rules.

## Earnings/Tactical Boundary

Tactical review may reference Wave 8 earnings review outputs when a setup is near or after earnings.

Rules:

- `pre_earnings_setup_review` must not loosen decision safety or encourage a buy before earnings when risk is too high.
- `post_earnings_reaction_review` must remain review-only and should distinguish opportunity review from warning review.
- Earnings signals may explain tactical context, but they must not change official score, target, action, target confidence, suggested amount, decision gate, source weights, or allocation.

## Long-Term/Tactical Boundary

Tactical review must not override long-term recommendations.

Rules:

- The official controlled action remains one of `Strong Buy`, `Buy`, `Add`, `Hold`, `Watch`, `Trim`, or `Avoid`.
- Tactical review action is separate metadata.
- A tactical buy review must not make a watchlist-only or decision-blocked name buy-ready.
- A tactical sell review must not become "sell now" language for long-term holdings.
- Long-term capital deployment remains the primary daily buy/add surface.
- Future short candidates must stay out of current long-term and tactical long-only queues unless a future explicit short-review mode is scoped.

## AI Boundaries

AI output may summarize tactical evidence, explain uncertainty, compare bull/bear interpretations, and highlight missing evidence.

AI output must not:

- Change official score.
- Change official action.
- Change target price.
- Change target confidence.
- Change suggested amount.
- Change decision-safety status.
- Change source weights.
- Trigger broker behavior.
- Turn a review action into an order instruction.

AI tactical summaries must cite deterministic evidence fields or explicitly say evidence is missing, stale, uncorroborated, or provider-blocked.

## Provider/Data Boundaries

Wave 10 tests must use fixtures and mocks. Do not run live provider calls in tests.

Tactical review should distinguish:

- Price history available.
- Price history missing.
- Technical evidence stale.
- Earnings evidence present or missing.
- News/catalyst evidence present or uncorroborated.
- Provider blocked, rate-limited, missing, or stale.

Provider/data gaps may trigger `data_gap_review`, `avoid_for_now`, or `wait_for_confirmation` review metadata. They must not be hidden and must not automatically change official recommendations.

## Acceptance Criteria

- Requirements doc is clear and Codex-readable.
- Fixture scenarios cover clean breakout setup, pullback to support, post-earnings overreaction, pre-earnings too risky, momentum strong but data gap, reversal signal weak, no tactical setup, long-term add not overridden, watchlist-only name remains blocked from buy-ready, and missing price history.
- Fixture tests validate structure, tactical horizons, setup types, review actions, risk zones, invalidation fields, guardrails, provider/data boundaries, and long-term/tactical separation.
- Tests do not require live provider calls, broker access, model calls, report rendering, storage schema changes, or tactical implementation modules.
- No product behavior changes.
- No scoring, target, recommendation-label, decision-safety, allocation, provider-ingestion, dashboard, storage, broker, or trading behavior changes.

## Fixture Scenarios

Fixture scenarios live in `tests/fixtures/tactical/`.

Required scenarios:

| Scenario | Fixture | Purpose |
| --- | --- | --- |
| Clean breakout setup | `clean_breakout_setup.json` | Breakout review has enough evidence for tactical buy review without changing the official recommendation. |
| Pullback to support | `pullback_to_support.json` | Pullback review frames a manual review zone and invalidation conditions. |
| Post-earnings overreaction | `post_earnings_overreaction.json` | Post-earnings reaction is reviewed as tactical context without changing earnings or official recommendation outputs. |
| Pre-earnings too risky | `pre_earnings_too_risky.json` | Pre-earnings setup remains avoid/wait when event risk is high. |
| Momentum strong but data gap | `momentum_strong_but_data_gap.json` | Momentum signal is visible but provider/data gap prevents higher-confidence review. |
| Reversal signal weak | `reversal_signal_weak.json` | Weak reversal evidence produces wait/avoid posture. |
| No tactical setup | `no_tactical_setup.json` | Empty state is explicit and does not invent a setup. |
| Long-term add should not be overridden | `long_term_add_not_overridden.json` | Tactical review metadata does not override long-term add recommendation or allocation context. |
| Watchlist-only name remains blocked from buy-ready | `watchlist_only_remains_blocked.json` | Tactical interest does not bypass watchlist-only or decision-safety blocks. |
| Missing price history | `missing_price_history.json` | Missing price history triggers data-gap review and no tactical setup assertion. |

These fixtures are contract examples. Later implementation branches should either consume them directly or add behavior-level fixtures that preserve these scenario labels, tactical metadata, and guardrails.

## Future Integration Notes

Future Wave 10 implementation should prefer focused helper modules and report-context fields before broad renderer or local-console work.

Likely follow-up branches:

- `codex/tactical-review-queue`
- `codex/tactical-risk-zones`
- `codex/tactical-outcome-review`
- `codex/tactical-provider-gap-review`
- `codex/tactical-console-panel`

Any dashboard, report-context, or local-console integration should stay compact and should show tactical review as a separate review mode, not as a trading console or replacement for long-term capital deployment.
