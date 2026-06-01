# Post-Wave Validation Log

This log captures user validation feedback after deployed or reviewable waves. It is documentation-only and does not change scoring, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, dashboard rendering, broker behavior, or trading behavior.

## 2026-06-01 - Wave 14 Dashboard Validation

Source: dictated post-wave feedback from Matt through ChatGPT after reviewing the Wave 14 dashboard deployment.

Validation context:

- Wave 14 broker read-only context had been deployed/integrated.
- Matt reviewed the dashboard as an end user, focusing on whether the app clearly answered the daily decision question.
- Feedback is accepted as primary SDLC feedback input and should feed Wave 15 planning.

Key observations:

1. The top dashboard area is promising, but decision-gate wording is unclear.
2. `Blocked: Watch action is not a buy action; verification check still open` needs plain-English clarification.
3. Microsoft is not the problem. Matt likes MSFT and intends to buy some. The issue is that the dashboard repeats Microsoft too much and does not clearly explain the model/user disagreement.
4. The top dashboard area should show the top 5 ranked opportunities, not only one primary candidate.
5. The top 5 should include both mega-cap/core candidates and higher-upside/speculative opportunities.
6. Missing price/provider data should reduce confidence or block readiness, but should not imply a bearish thesis.
7. Top dashboard, daily decision review, recommendation action queue, and full action queue are repetitive.
8. Score drivers look useful, but the user needs definitions for base evidence, trends, targets, gaps, and final action.
9. Target/source drilldown and analyst insight sections often show missing evidence/data.
10. Decision briefs are dominated by obvious mega-cap names like Microsoft, NVIDIA, Meta, Amazon, and Google. The app should explain why now, why this one, and what edge exists.
11. Long-term queue and short-term queue feel unrefined.
12. Data gaps are useful to see, but the app needs a way to convert them into maintenance work requests.
13. Current holdings showed NVIDIA but did not clearly show when holdings data was last pulled.
14. Data ingestion and research sources show many next actions, zero records, and not-implemented sources. The app needs a daily data maintenance process.
15. The dashboard feedback tool is less useful than dictated feedback through ChatGPT. Dictated post-wave feedback should become the main SDLC feedback loop.
16. Data maintenance work should start as docs/backlog items, then later become GitHub issues if needed.

Backlog items created:

- `FB-001`: Clarify decision-gate blocked explanations.
- `FB-002`: Reduce dashboard repetition and consolidate decision sections.
- `FB-003`: Show Top 5 ranked opportunities at the top of the dashboard.
- `FB-004`: Distinguish core mega-cap candidates from higher-upside/speculative opportunities.
- `FB-005`: Track model/user disagreement when the model says Watch but the user manually buys.
- `FB-006`: Treat missing price/provider data as confidence/reliability blocker, not negative thesis.
- `FB-007`: Create data gap maintenance queue and Codex-ready docs/backlog work requests.
- `FB-008`: Add score driver glossary/help text.
- `FB-009`: Add "why now / why this / edge" explanation for mega-cap recommendations.
- `FB-010`: Refine long-term and short-term queues.
- `FB-011`: Add holdings/broker snapshot freshness display.
- `FB-012`: Improve research source activation/records visibility.
- `FB-013`: Formalize dictated feedback as primary post-wave validation input.

Roadmap impact:

- Add Wave 15: Daily Decision Quality Beta.
- Wave 15 should focus on dashboard clarity, top 5 opportunity ranking, decision trust, data maintenance, holdings freshness, and queue refinement.
- Wave 15 should not add new model families, broker behavior, new tactical features, or automatic tuning.

## 2026-06-01 - Wave 15 Dashboard Readability Follow-Up

Source: Matt's follow-up dashboard usability feedback after reviewing the post-Wave-14 / early Wave-15 dashboard direction.

Validation context:

- The Daily Decision Review is useful and should remain the pattern for decision detail.
- The Action Queue has the right top-10 list shape.
- The dashboard still needs a narrower first-page readability iteration before broader redesign work.
- This feedback is documentation-only planning input and does not authorize application behavior changes.

Key observations:

1. The Daily Decision Review detail is useful.
2. The Action Queue list shape is useful, especially as a top-10 queue.
3. The next iteration should combine Daily Decision Review detail with the Action Queue list instead of leaving them as separate repeated sections.
4. The first page should start with a Top 10 Action Queue.
5. Each Top 10 row should be expandable.
6. Each expanded row should include Daily Decision Review-style detail, Score Drivers, Target Source Drilldown, and Provider Gap Review.
7. Dashboard navigation currently near the bottom should move toward the top.
8. The next UI pass should avoid many other page changes.
9. Future dashboard iterations should stay small and feedback-driven until the first page becomes usable.
10. Existing data elements may still be valuable, but many should move into sub-tabs or drilldowns instead of competing for first-page attention.

Backlog items created:

- `UI-001`: Combine Daily Decision Review with Action Queue into a Top 10 expandable section.
- `UI-002`: Add per-symbol expandable drilldowns for Score Drivers, Target Sources, and Provider Gaps.
- `UI-003`: Move dashboard navigation near the top.
- `UI-004`: Reduce top-page redundancy before doing broader redesign.
- `UI-005`: Treat remaining dashboard sections as future sub-tabs/drilldowns.

Roadmap impact:

- Add current UI focus: Dashboard Usability Iteration 1 - Top Action Queue Drilldown.
- The next UI changes should be small and feedback-driven.
- This UI iteration should not add new model, data, broker, trading, scoring, target, allocation, provider, AI, or decision-safety behavior.
