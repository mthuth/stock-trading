# Product Strategy

This document captures the current product strategy for the stock-trading research engine. It is a planning and alignment artifact only. It does not change scoring, target blending, recommendation labels, decision safety, allocation, provider behavior, report rendering, broker behavior, or trading behavior.

## Product North Star

The product is recommendation-only decision support for a human investor. It should help answer:

- What should I buy/add today, especially for long-term holdings?
- What should I review today to make better portfolio decisions?
- What changed, what evidence supports it, and what could make the view wrong?

The app must remain a research and review system. It must not become an automated trader, an order preview tool, or a system that implies guaranteed performance.

## Current Daily Use Case

The immediate daily use case is:

> What should I buy/add today, especially for long-term holdings?

Daily review should prioritize long-term capital deployment, decision safety, target confidence, data reliability, source quality, AI synthesis readiness, and provider gaps. The first useful answer should be practical and conservative: identify the best Add or Buy candidate, show why it passed or failed the decision gate, and explain what evidence or data gaps should be checked before the user acts manually.

## Long-Term Vision

The long-term vision is a learning AI recommendation system that makes predictions, tracks outcomes, compares models, and improves over time.

That system should:

- Treat every recommendation as a prediction that can later be evaluated.
- Track whether decisions helped or hurt outcomes.
- Compare official models against shadow models.
- Measure source usefulness, catalyst follow-through, and AI thesis quality.
- Earn greater autonomy only through reviewed outcome evidence.

Even in the long-term vision, model learning remains review-first. No model, AI brief, feedback item, or outcome metric may change official recommendations until a future explicit model-impact requirement and regression evidence approve it.

## Portfolio Strategy

The current portfolio intent is roughly:

- Two-thirds long-term/core holdings.
- One-third higher-risk, tactical, or speculative upside.

Portfolio sleeves:

| Sleeve | Purpose | Current posture |
| --- | --- | --- |
| `long_term_core` | Durable operating-company holdings and primary Add/Buy candidates | Current priority |
| `tactical` | Shorter-duration trades with catalyst, trend, or event support | Later, separate mode |
| `speculative_ai` | Higher-volatility AI/small-mid-cap ideas | Watchlist-first with strict gates |
| `etf_context` | ETF allocation/context instruments | Deferred dedicated logic |
| `future_short_candidate` | Potential short-side or hedge candidates | Future review-only mode |

Long-term buy/add is the current product priority. Long-term selling and trim logic is later and should begin as holding-health review rather than "sell now" instructions.

## Risk Phase Model

Risk should increase only as trust is earned.

1. Cautious Deployment
   - Current phase.
   - Moderately safe / cautious growth.
   - Safety gates should start stricter while trust is being built.
   - Prefer missed upside over false-confidence buys.

2. Measured Aggression
   - Future phase after enough recommendation, outcome, and decision-safety history exists.
   - More capital can be directed toward higher-conviction long-term and tactical setups.
   - Requires evidence that gates are not over-blocking good opportunities.

3. Performance Seeking
   - Long-term phase.
   - Goal is returns meaningfully above market performance, ideally at least 2x market performance once confidence is earned.
   - Requires model trust, source usefulness, catalyst follow-through, drawdown control, and prediction accuracy evidence.

## Missed-Upside Tolerance By Sleeve

Missed-upside tolerance is not the same across sleeves.

| Sleeve | Missed-upside tolerance | Reason |
| --- | --- | --- |
| `long_term_core` | Medium | Missing a great compounder matters, but the user needs trust before deploying more capital. |
| `tactical` | High initially | Tactical behavior is not mature enough to justify loose gates yet. |
| `speculative_ai` | High | Avoiding false positives matters more than catching every early move while watchlist rules mature. |
| `etf_context` | High | ETFs are allocation/context instruments for now, not operating-company alpha picks. |
| `future_short_candidate` | Very high | Future short/hedge ideas must stay out of current buy/add logic. |

## Analyst Target Coverage Policy

Do not pay for better analyst coverage immediately unless the model cannot mature without it.

Near-term target strategy:

- Use existing provider targets.
- Use reviewed manual analyst targets where appropriate.
- Continue fundamental and technical target generation.
- Use SEC, company IR, public evidence, and AI synthesis readiness to explain confidence.
- Downgrade target confidence when source breadth is weak.

Paid analyst coverage can be reconsidered later when one or more are true:

- Trading activity and deployed capital justify the cost.
- Target-confidence bottlenecks repeatedly block otherwise attractive long-term candidates.
- App usage shows analyst target breadth is the highest-value missing input.
- Provider gap history proves free/manual coverage cannot support model maturity.

## ETF Policy

ETF logic is deferred.

For now:

- Exclude ETFs from operating-company logic.
- Do not treat ETF SEC CIK, SEC companyfacts, official IR, or company analyst target gaps as unresolved operating-company provider failures.
- Label ETF gaps as expected/non-operating-company gaps where possible.
- Revisit a dedicated ETF logic track later.

ETFs should eventually use allocation, trend, risk, basket, sector, and liquidity context rather than operating-company target methodology.

## Broker Read-Only Policy

Broker read-only integration is deferred unless cash or holdings uncertainty prevents good buy/add recommendations.

Before expanding broker integration, add a capital-availability concept that can be maintained manually or from config:

- Configured/manual cash.
- Monthly buy capacity.
- As-of date.
- Future optional broker read-only snapshot.

Broker integration must remain read-only. It must never support order placement, order preview, account write actions, automated trading, or anything that implies the app can execute trades.

## Local App Direction

The app should evolve from static reports into a local decision console.

Future local app surfaces should include:

- Latest recommendation review.
- Best long-term add.
- Run history.
- Manual journal.
- Outcomes.
- AI briefs.
- Provider gaps.
- Pre-market review.
- Post-market review.
- Earnings event review.
- Intraday signals/news triggers.

Do not build real-time behavior in the current docs strategy phase. The next product step is alignment and stabilization, not a live trading console.

## AI Role In The Product

AI synthesis is core to the product vision, but it must remain explanatory until evaluated.

AI should produce:

- Source-backed reasoning.
- Bull and bear cases.
- Expected outcomes.
- Uncertainty.
- What would change the view.
- Evidence that is weak, stale, missing, blocked, or uncorroborated.

AI output must not change official score, action, target price, target confidence, suggested amount, decision gate status, watchlist eligibility, provider behavior, allocation behavior, or broker behavior unless a future explicit model-impact requirement and regression evidence approve it.

## What The App Must Never Do

The app must never:

- Place trades.
- Preview orders.
- Write to broker accounts.
- Automate trading.
- Imply guaranteed performance.
- Hide provider/source gaps that affect confidence.
- Invent recommendation labels outside the controlled label set.
- Let AI, feedback, or outcomes silently change official recommendations.
- Mix future short candidates into current buy/add recommendations.

## Near-Term Product Priorities

1. Stabilize Wave 6 learning outputs and documentation.
2. Keep long-term buy/add as the first daily decision surface.
3. Add capital-availability context before broker read-only integration.
4. Turn the provider gap action plan into scoped provider/data cleanup branches.
5. Mark ETF gaps as expected/non-operating-company gaps.
6. Improve report-context/status validation only where it protects current behavior.
7. Keep AI briefs explanatory and source-backed.
8. Prepare for Wave 7 long-term capital deployment without weakening safety gates prematurely.
