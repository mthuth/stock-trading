# Roadmap Status

This document is the current living map for Stock Trading product work. It should be checked before starting new feature work. It is documentation-only and does not change application behavior.

## Current Status Summary

The app has moved from a basic research generator toward a decision-support and learning system.

Current state:

- Recommendation-only daily research/reporting is established.
- Decision safety, target confidence, allocation safety, watchlist-only enforcement, provider/source health, AI synthesis guardrails, learning loops, local console surfaces, shadow-model review, alerts, and broker read-only context are present.
- Waves 1-14 are complete through Wave 14 broker read-only integration.
- Wave 14 dashboard validation feedback has been captured in [Post-Wave Validation Log](POST_WAVE_VALIDATION_LOG.md), [Feedback Backlog](FEEDBACK_BACKLOG.md), and [Roadmap Decision Log](ROADMAP_DECISION_LOG.md).
- The next wave is Wave 15: Daily Decision Quality Beta.
- Wave 15 should focus on dashboard clarity, top 5 opportunity ranking, decision trust, data maintenance, holdings freshness, and queue refinement.
- Current UI focus: Dashboard Usability Iteration 1 - Top Action Queue Drilldown.
- The next UI changes should be small and feedback-driven until the first page becomes usable.
- This UI iteration should not add new model/data/broker/trading features.
- Wave 15 should not add new model families, broker behavior, new tactical features, automatic tuning, broker writes, order previews, or trading behavior.

## Completed Waves

| Wave | Status | Notes |
| --- | --- | --- |
| Wave 1: Stabilize And Protect | Complete | Package boundaries, regression/golden context coverage, and recommendation-safety guardrails were established. |
| Wave 2: Improve Decision Review | Complete | Decision safety, provider gaps, target drilldowns, score explainability, and dashboard review flow were integrated. |
| Wave 3: Improve Data Quality | Complete | Provider gap normalization, source health, SEC/IR/source coverage, and provider review UX were added. |
| Wave 4: Model Transparency And Allocation Safety | Complete | Technical/fundamental target transparency, target confidence calibration, watchlist-only enforcement, and allocation safety landed. |
| Wave 5: AI Synthesis | Complete | AI prompt packets, evidence guardrails, synthesis readiness, AI brief review workflow, and LLM research brief drafting landed as explanatory outputs. |
| Wave 6: Learning System Foundations | Complete | Manual journal, recommendation outcomes, decision-safety effectiveness, catalyst follow-through, and source usefulness landed as review-only learning foundations. |
| Strategy Docs Refresh | Complete | Product strategy, roadmap status, decision modes, model learning strategy, and local app strategy are documented. |
| Wave 7: Long-Term Capital Deployment | Complete | Long-term add queue, capital deployment context, best-add fallback, holding health, and dashboard integration landed as recommendation-only decision support. |
| Wave 8: Earnings Event Review | Complete | Earnings event queues, pre/post earnings review, earnings signals, and integration landed as review-only context. |
| Wave 9: Local Decision Console Shell | Complete | Local console requirements, manifest, static render shell, and integration landed as local read-only review surfaces. |
| Wave 10: Tactical Trade Review | Complete | Tactical requirements, risk zones, setup classifier, watchlist queue, tactical outcomes, and integration landed as review-only surfaces separate from long-term recommendations. |
| Wave 11: Model Evaluation And Backtesting | Complete | Prediction records, model registry, trust score, recommendation backtests, benchmark comparisons, AI thesis evaluation, and integration landed as review-only learning context. |
| Wave 12: Alerts And Review Triggers | Complete | Alert requirements, inbox/view model, lifecycle, deduplication, artifact export, rule engine, and integration landed as review prompts only. |
| Wave 13: Multi-Model Shadow Competition | Complete | Shadow model contracts, debate packets, promotion-readiness review, shadow recommendation runner, comparison scoreboard, and integration landed as shadow-only review context. |
| Wave 14: Broker Read-Only Integration | Complete | Broker read-only requirements, connector stubs/contracts, fixture importer, holdings/capital context, read-only view, and integration landed without broker write behavior. |

## Current / In-Progress Work

Post-Wave-14 validation feedback and Wave 15 dashboard readability follow-up are being captured as documentation-only planning input.

Current active work should be considered Wave 15 preparation: convert dashboard validation feedback into clear backlog items and roadmap decisions before implementation branches begin.

### Current UI Focus: Dashboard Usability Iteration 1 - Top Action Queue Drilldown

The next dashboard UI iteration should be narrow and feedback-driven.

Focus:

- Combine Daily Decision Review detail with the Action Queue list shape.
- Create a top-of-page Top 10 Action Queue.
- Make each of the 10 rows expandable.
- In each expanded row, include Daily Decision Review-style detail, Score Drivers, Target Source Drilldown, and Provider Gap Review.
- Move dashboard navigation currently near the bottom toward the top.
- Reduce top-page redundancy before broader redesign.
- Preserve other useful dashboard data as future sub-tabs or drilldowns.

Guardrails:

- Do not make many other page changes yet.
- Do not add new model/data/broker/trading features in this UI iteration.
- Do not change scoring, target logic, target confidence, allocation, decision safety, provider behavior, broker behavior, recommendation labels, or trading behavior.
- Keep the experience recommendation-only and review-only.

## Next Recommended Wave

### Wave 15: Daily Decision Quality Beta

Goal: make the dashboard feel trustworthy, clear, and less repetitive for the daily decision question:

> What are the top 5 ranked opportunities today?

Wave 15 should focus on:

- Dashboard clarity and hierarchy.
- Top 5 opportunity ranking on the first screen.
- Top 10 expandable Action Queue as the immediate dashboard usability iteration.
- Clear distinction between core mega-cap candidates and higher-upside/speculative opportunities.
- Plain-English decision-gate explanations.
- Missing data as confidence/reliability and sizing blockers, not bearish thesis language.
- Model/user disagreement tracking when the model says Watch but the user manually buys.
- Score driver definitions and glossary/help text.
- "Why now / why this / edge" explanations for obvious mega-cap recommendations.
- Refined long-term and short-term queues.
- Data gap maintenance queue and Codex-ready docs/backlog work requests before GitHub issues.
- Holdings/broker snapshot freshness display.
- Research source activation and records visibility.
- Dictated feedback as the primary post-wave validation loop.

Wave 15 should not add:

- New model families.
- New broker behavior.
- New tactical features.
- Automatic tuning.
- Automatic score, target, recommendation, decision-safety, allocation, source-weight, or model changes.
- Broker writes, order previews, order placement, or trading behavior.

## Integration Backlog

- Break `FB-001` through `FB-013` into Wave 15 implementation branches.
- Break `UI-001` through `UI-005` into the first dashboard usability implementation branch before broader redesign work.
- Implement Dashboard Usability Iteration 1 - Top Action Queue Drilldown as a small UI change.
- Consolidate repeated decision sections into hierarchy and drilldowns.
- Add first-screen top 5 ranked opportunity presentation.
- Add top-of-page Top 10 Action Queue with expandable per-symbol detail.
- Move dashboard navigation toward the top.
- Distinguish core mega-cap candidates from higher-upside/speculative opportunities.
- Clarify decision-gate blocked wording.
- Track model/user disagreement as review-only learning context.
- Add score driver definitions and mega-cap edge explanations.
- Convert data gaps and research-source next actions into docs/backlog maintenance work requests before creating GitHub issues.
- Show broker/holdings snapshot source and freshness wherever holdings appear.
- Keep AI synthesis, learning outputs, broker context, model competition, alerts, and feedback review-only until a future model-impact phase explicitly approves otherwise.

## Provider/Data Backlog

The provider gap action plan exists at `reports/provider-gap-action-plan.md`. Convert accepted actions into scoped provider/data cleanup branches.

Priority backlog:

- Restore current-price coverage for `BBAI`, `ALAB`, and `PLAB`.
- Resolve analyst-target breadth for operating companies or document manual/provider fallback paths.
- Mark ETF CIK, companyfacts, official IR, and company analyst target gaps as expected/non-operating-company gaps.
- Add TSM/foreign-issuer fallback planning for companyfacts-equivalent evidence.
- Improve official IR parser behavior and page-link fallback.
- Decide later whether paid FMP/Finnhub/Benzinga analyst/news/transcript coverage is justified.

Wave 15 should make these gaps easier to convert into daily maintenance work requests.

## Deferred Decisions

- Paid analyst target coverage.
- Dedicated ETF logic.
- Additional broker behavior beyond read-only context.
- New tactical features beyond refinement of existing queues.
- Future short-candidate review.
- Model-impact feedback/source weighting.
- Automatic score tuning.
- Intraday signal console.

## Known Product Risks

- False confidence from thin analyst target coverage.
- ETF gaps being misread as operating-company provider failures.
- Provider gaps creating noisy operational work.
- AI briefs sounding more confident than source evidence allows.
- Learning metrics being mistaken for approved model tuning.
- Decision safety over-blocking good opportunities while trust is still being built.
- Missing price/provider data being read as negative thesis instead of lower confidence or sizing block.
- Model/user disagreement being hidden instead of captured as learning context.
- Broker/holdings data being shown without obvious freshness/source timestamp.
- Repetitive dashboard sections making the daily answer feel less decisive.
- Top dashboard showing only one primary candidate instead of a useful top 5.
- Mega-cap recommendations feeling obvious without explaining why now, why this one, or what edge exists.
- Tactical or speculative ideas leaking into long-term buy/add recommendations.

## Required Stabilization Before Moving On

Before Wave 15 implementation begins:

- Confirm Wave 14 dashboard feedback is captured in the validation log, feedback backlog, and decision log.
- Confirm Wave 15 scope stays focused on daily decision quality, top 5 opportunity ranking, dashboard clarity, data maintenance, holdings freshness, and queue refinement.
- Confirm Wave 15 does not add new model families, broker behavior, new tactical features, automatic tuning, broker writes, order previews, or trading behavior.
- Keep feedback/docs updates separate from app-code implementation unless a Wave 15 branch explicitly scopes implementation.
- Keep `python3 scripts/check_quality.py` passing after docs and future integration changes.
