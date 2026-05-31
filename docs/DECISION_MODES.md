# Decision Modes

Decision modes prevent the app from mixing unlike decisions. A long-term Add, a speculative watchlist item, an earnings-event review, an ETF context row, and a future short candidate should not use the same decision language or risk posture.

This document is a strategy artifact only. It does not change recommendation labels, scoring, target blending, decision safety, allocation, provider behavior, or broker behavior.

## Why Decision Modes Matter

The current app is strongest when it answers:

> What should I buy/add today, especially for long-term holdings?

As the product grows, it also needs to answer:

> What should I review today to make better decisions?

Those questions require different modes. Without explicit modes, future agents may accidentally let tactical trades affect long-term holdings, let future short ideas appear in buy/add queues, or treat ETFs like operating companies.

## Decision Modes

| Mode | Purpose | Current status |
| --- | --- | --- |
| `long_term_buy_add` | Decide what long-term/core holding to buy or add manually today | Current priority |
| `long_term_hold_health` | Review whether an existing long-term holding remains healthy | Later |
| `tactical_trade` | Review shorter-duration trades with trend/catalyst support | Later |
| `earnings_event` | Review pre-earnings and post-earnings setups | Later |
| `speculative_watchlist` | Track speculative AI names until they earn buy-readiness | Active guardrail |
| `etf_context` | Treat ETFs as allocation/context instruments | Deferred dedicated logic |
| `future_short_candidate` | Track possible short/hedge candidates separately | Future |
| `portfolio_review` | Review allocation, exposure, capital availability, and outcomes | Emerging |

## Recommendation Horizons

Required horizons:

| Horizon | Typical use |
| --- | --- |
| `1_day` | Pre-market review, intraday trigger review, immediate data issues |
| `5_trading_days` | Weekly swing review, near-term catalyst checks |
| `20_trading_days` | Monthly tactical or earnings follow-through review |
| `60_trading_days` | Medium-term thesis and catalyst validation |
| `12_months` | Long-term target and business thesis review |
| `multi_year` | Core holding thesis and compounding potential |

## Portfolio Sleeves

| Sleeve | Decision mode relationship |
| --- | --- |
| `long_term_core` | Primary sleeve for `long_term_buy_add` and later `long_term_hold_health` |
| `tactical` | Should use `tactical_trade`, not long-term buy/add rules |
| `speculative_ai` | Should default to `speculative_watchlist` until evidence, confidence, and watchlist rules allow buy-readiness |
| `etf_context` | Should use ETF allocation/context logic, not operating-company logic |
| `future_short_candidate` | Must not appear in current buy/add recommendation flows |

## Mode-Specific Rules

`long_term_buy_add`:

- Current implementation priority.
- Should emphasize decision safety, target confidence, source breadth, provider gaps, and allocation safety.
- Should remain cautious while trust is being built.

`long_term_hold_health`:

- Later mode.
- Should start as holding-health review, not "sell now" output.
- Should ask whether thesis quality, source signals, downside risk, or allocation exposure changed.

`tactical_trade`:

- Later mode.
- Should remain separate from long-term recommendations.
- Should use shorter horizons and tighter catalyst/trend checks.

`earnings_event`:

- Later mode.
- Should eventually support pre-earnings and post-earnings decisions.
- Should separate expected move, guidance risk, transcript/IR evidence, and post-event follow-through.

`speculative_watchlist`:

- Should keep higher-risk AI names out of buy-ready recommendations until strict criteria pass.
- Missed upside is acceptable while trust is being built.

`etf_context`:

- ETFs are context/allocation instruments for now.
- ETF gaps for SEC CIK, companyfacts, official IR, and company analyst targets should be expected/non-operating-company gaps.

`future_short_candidate`:

- Future short candidates must not be mixed into current buy/add recommendations.
- Any future implementation should be review-only and separate from long-only recommendation queues.

`portfolio_review`:

- Should eventually combine capital availability, allocation, journal entries, outcomes, model trust, and risk posture.
- Should not execute or preview trades.

## Initial Implementation Priorities

1. Keep `long_term_buy_add` as the current daily priority.
2. Add capital-availability context before broker read-only integration.
3. Integrate Wave 6 learning outputs without model-impact behavior.
4. Label ETF operating-company gaps as expected.
5. Keep speculative AI watchlist-only behavior visible and strict.
6. Treat long-term sell/trim as future holding-health review.

## Future Modes

Future modes should be added only when they are separated from official long-term buy/add logic and covered by regression tests:

- Earnings pre-event planning.
- Earnings post-event follow-through.
- Tactical trade review.
- Intraday signal review.
- Future short/hedge candidate review.
- Model-shadow comparison review.
