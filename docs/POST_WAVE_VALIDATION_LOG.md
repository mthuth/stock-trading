# Post-Wave Validation Log

This log captures user validation feedback after deployed or reviewable waves. It is documentation-only and does not change scoring, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, dashboard rendering, broker behavior, or trading behavior.

## 2026-06-01 - Wave 14 Dashboard Validation

Source: dictated post-wave feedback from Matt through ChatGPT after reviewing the Wave 14 dashboard deployment.

Validation context:

- Wave 14 broker read-only context had been deployed/integrated.
- Matt reviewed the dashboard as an end user, focusing on whether the app clearly answered the daily decision question.
- Feedback is accepted as primary SDLC feedback input and should feed Wave 15 planning.

Key observations:

1. The top dashboard area looks promising, but the decision-gate explanation is unclear.
2. `Blocked: Watch action is not a buy action; verification check still open` needs plain-English clarification.
3. Microsoft should not feel negative just because data/prices are missing; missing data should reduce confidence or block sizing, not imply bearishness.
4. Top dashboard, daily decision review, recommendation action queue, and full action queue are repetitive.
5. Score drivers look valuable, but the user needs definitions for base evidence, trends, targets, gaps, and final action.
6. Target/source drilldown and analyst insight sections often show missing evidence/data.
7. Decision briefs are dominated by obvious mega-cap names like Microsoft, NVIDIA, Meta, Amazon, and Google; the app needs to explain why now, why this one, and what edge exists.
8. Long-term queue and short-term queue feel unrefined.
9. Data gaps are useful to see, but the app needs a way to convert them into maintenance work requests.
10. Current holdings showed NVIDIA but did not clearly show when holdings data was last pulled.
11. Data ingestion and research sources show many next actions, no records, and not-implemented sources; the app needs a daily data maintenance process.
12. The dashboard feedback tool is less useful than dictated feedback through ChatGPT; dictated post-wave feedback should become the main SDLC feedback loop.

Backlog items created:

- `FB-001`: Clarify decision-gate blocked explanations.
- `FB-002`: Reduce dashboard repetition and consolidate decision sections.
- `FB-003`: Treat missing price/provider data as confidence/reliability blocker, not negative thesis.
- `FB-004`: Create data gap maintenance queue and Codex-ready work requests.
- `FB-005`: Add score driver glossary/help text.
- `FB-006`: Add "why now / why this / edge" explanation for mega-cap recommendations.
- `FB-007`: Refine long-term and short-term queues.
- `FB-008`: Add holdings/broker snapshot freshness display.
- `FB-009`: Improve research source activation/records visibility.
- `FB-010`: Formalize dictated feedback as primary post-wave validation input.

Roadmap impact:

- Add Wave 15: Decision Quality Beta.
- Wave 15 should focus on dashboard clarity, decision trust, data maintenance, holdings freshness, and queue refinement.
- Wave 15 should not add new model families, broker behavior, new tactical features, or automatic tuning.
