# Wave 8 Earnings Review Requirements

Wave 8 builds the Earnings Event Review layer. This document defines the intended behavior before ingestion, analysis, dashboard, or report-context integration. It is requirements-only and does not change scoring, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider ingestion, dashboard rendering, storage schema, broker behavior, or trading behavior.

## Product Goal

Wave 8 should make the app better at answering:

- Which owned, watchlist, or approved-universe stocks have earnings coming up?
- Should I buy before earnings, wait, buy after earnings, avoid the setup, or keep watching?
- What happened after earnings?
- Did guidance, estimates, margins, revenue, EPS, AI/capex commentary, or risk language improve or weaken the thesis?
- Was the market reaction an opportunity or a warning?
- Did the AI/model prediction about earnings work?

Earnings review is a decision-support layer. It must remain recommendation-only and review-only.

## Non-Goals

Wave 8 must not add:

- Automatic trading.
- Order preview.
- Short selling.
- Full tactical same-day engine behavior.
- Automatic scoring changes.
- Automatic target changes.
- Automatic decision-safety changes from AI.
- Automatic model tuning.
- Broker write actions.

Wave 8 must preserve the controlled recommendation labels: `Strong Buy`, `Buy`, `Add`, `Hold`, `Watch`, `Trim`, and `Avoid`.

## Pre-Earnings Review Requirements

Pre-earnings review should identify upcoming events and frame the decision without changing official recommendations.

It should show:

- Symbol, company, sleeve, and ownership/watchlist/universe scope.
- Earnings date, time of day when known, fiscal period, and source.
- Days until earnings.
- Current official action and decision-safety status.
- Existing target confidence and provider/data gaps.
- Whether the setup is `buy_before_earnings`, `wait_for_earnings`, `avoid_earnings_setup`, or `keep_watching` as review metadata only.
- What evidence would make the user wait.
- What evidence would make the user revisit after the report.

Pre-earnings review must not loosen decision gates or suggest an order.

## Post-Earnings Review Requirements

Post-earnings review should summarize what changed and whether the event strengthened or weakened the long-term thesis.

It should cover:

- Revenue result and growth direction.
- EPS result and profitability direction.
- Guidance, estimates, or outlook changes.
- Margin quality.
- AI, capex, demand, or product commentary where relevant.
- Risk-language changes.
- Market reaction and whether it looks like an opportunity, warning, or neutral reaction.
- Follow-up review actions such as refresh target sources, read transcript, review SEC/IR evidence, or keep watching.

Post-earnings review must not automatically change official score, target, action, target confidence, suggested amount, decision gate, source weights, or allocation.

## Earnings Event Queue Requirements

The earnings event queue should include owned, watchlist, and approved-universe symbols that have upcoming or recent earnings events.

Queue fields should include:

- `symbol`
- `company`
- `scope`
- `decision_mode`
- `event_phase`
- `earnings_date`
- `days_to_or_since_earnings`
- `event_status`
- `current_action`
- `decision_gate_status`
- `target_confidence`
- `earnings_confidence`
- `review_decision`
- `blocked_reasons`
- `provider_gaps`
- `next_review_action`

ETF rows should be marked `not_applicable` unless a future ETF-specific distribution or holdings-reporting event is explicitly scoped.

## Earnings Signal Requirements

Earnings signals should be review-only facts or interpretations.

Required signal categories:

- `guidance`
- `estimates`
- `margins`
- `revenue`
- `eps`
- `ai_capex_commentary`
- `risk_language`
- `market_reaction`
- `thesis_impact`

Allowed signal directions:

- `improved`
- `weakened`
- `mixed`
- `neutral`
- `missing`
- `not_applicable`

Signals may explain uncertainty and next checks. They must not mutate official model outputs.

## AI/LLM Boundaries

AI or LLM output may summarize earnings evidence, compare bull/bear interpretations, identify missing evidence, and explain what would change the view.

AI or LLM output must not:

- Change official score.
- Change official action.
- Change target price.
- Change target confidence.
- Change suggested amount.
- Change decision-safety status.
- Change source weights.
- Trigger broker behavior.

AI earnings summaries must cite deterministic evidence fields or explicitly say evidence is missing, stale, uncorroborated, company-only, or provider-blocked.

## Provider/Data Boundaries

Wave 8 tests must use fixtures and mocks. Do not run live provider calls in tests.

Provider/data review should distinguish:

- Earnings date available.
- Earnings date missing.
- Provider gap blocking earnings confidence.
- Foreign issuer or non-standard filing pattern.
- ETF not applicable.
- Company-only evidence that needs corroboration.
- Transcript, SEC, or official IR evidence missing.

Provider gaps should lower earnings confidence or trigger review, but they must not be hidden and must not automatically change official recommendations.

## Acceptance Criteria

- Requirements doc is clear and Codex-readable.
- Fixture scenarios cover upcoming earnings, blocked decision gate, positive post-earnings reaction, negative reaction with intact thesis, weakened thesis, missing date, ETF not applicable, foreign issuer filing pattern, and provider-gap blocked confidence.
- Fixture tests validate structure, labels, guardrails, signal categories, provider/data boundaries, and review-only behavior.
- Tests do not require live provider calls, broker access, report rendering, storage schema changes, or new feature modules.
- No product behavior changes.
- No scoring, target, recommendation-label, decision-safety, allocation, provider-ingestion, dashboard, storage, broker, or trading behavior changes.

## Fixture Scenarios

Fixture scenarios live in `tests/fixtures/earnings/`.

Required scenarios:

| Scenario | Fixture | Purpose |
| --- | --- | --- |
| Upcoming earnings with strong long-term candidate | `upcoming_strong_long_term_candidate.json` | Candidate is strong but earnings review frames whether to buy before or wait. |
| Upcoming earnings but decision gate blocked | `upcoming_decision_gate_blocked.json` | Earnings review must preserve blocked decision gate and zero deployment posture. |
| Recent earnings positive reaction | `recent_positive_reaction.json` | Post-earnings review shows improved signals and opportunity review. |
| Recent earnings negative reaction but thesis intact | `recent_negative_reaction_thesis_intact.json` | Market reaction is negative but thesis evidence remains acceptable. |
| Recent earnings thesis weakened | `recent_thesis_weakened.json` | Guidance/risk/margins weaken the thesis and require review. |
| Missing earnings date | `missing_earnings_date.json` | Provider/data gap prevents high-confidence earnings review. |
| ETF not applicable | `etf_not_applicable.json` | ETF row is marked not applicable, not an operating-company earnings failure. |
| Foreign issuer / different filing pattern | `foreign_issuer_different_filing_pattern.json` | Foreign issuer uses non-standard filing/evidence expectations. |
| Provider gap blocks earnings confidence | `provider_gap_blocks_earnings_confidence.json` | Provider blocker lowers earnings confidence and queues follow-up. |

These fixtures are contract examples. Later implementation branches should either consume them directly or add behavior-level fixtures that preserve these scenario labels, signal categories, and guardrails.

## Future Integration Notes

Future Wave 8 implementation should prefer focused helper modules and report-context fields before broad renderer work.

Likely follow-up branches:

- `codex/earnings-event-queue`
- `codex/pre-earnings-review-signals`
- `codex/post-earnings-review-signals`
- `codex/earnings-provider-gap-confidence`
- `codex/earnings-review-dashboard`

Any dashboard or markdown integration should stay compact and should show earnings review as audit/review context, not as a tactical trading engine.
