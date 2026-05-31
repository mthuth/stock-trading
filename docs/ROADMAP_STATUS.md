# Roadmap Status

This document is the current living map for Stock Trading product work. It should be checked before starting new feature work. It is documentation-only and does not change application behavior.

## Current Status Summary

The app has moved from a basic research generator toward a decision-support and learning system.

Current state:

- Recommendation-only daily research/reporting is established.
- Decision safety, target confidence, allocation safety, watchlist-only enforcement, provider/source health, and AI synthesis guardrails are present.
- Waves 1-5 are complete.
- Wave 6 learning foundations are merged: manual journal, recommendation outcomes, decision-safety effectiveness, catalyst follow-through, and source usefulness.
- PR #38 is merged, so the product strategy, roadmap, decision-mode, learning, and local-app direction docs are now part of `main`.
- Current Wave 6.5 work is product integration and stabilization, with Wave 7 handoff preparation as the immediate docs focus.
- Wave 7 should be Long-Term Capital Deployment after Wave 6.5 stabilization is complete.

## Completed Waves

| Wave | Status | Notes |
| --- | --- | --- |
| Wave 1: Stabilize And Protect | Complete | Package boundaries, regression/golden context coverage, and recommendation-safety guardrails were established. |
| Wave 2: Improve Decision Review | Complete | Decision safety, provider gaps, target drilldowns, score explainability, and dashboard review flow were integrated. |
| Wave 3: Improve Data Quality | Complete | Provider gap normalization, SEC/IR/source coverage, and provider review UX were added. |
| Wave 4: Model Transparency And Allocation Safety | Complete | Technical/fundamental target transparency, target confidence calibration, watchlist-only enforcement, and allocation safety landed. |
| Wave 5: AI Synthesis | Complete | AI prompt packets, evidence guardrails, synthesis readiness, AI brief review workflow, and LLM research brief drafting landed as explanatory outputs. |
| Wave 6: Learning System Foundations | Complete | PRs #33, #34, #35, #36, and #37 are merged: manual journal, outcome tracking, decision-safety effectiveness, catalyst follow-through, and source usefulness. |
| Strategy Docs Refresh | Complete | PR #38 is merged: product strategy, roadmap status, decision modes, model learning strategy, and local app strategy are documented. |

## Current / In-Progress Work

No Wave 7 implementation PRs were present when this document was updated after PR #38 merged.

Current active work should be considered Wave 6.5: product integration and stabilization. The main deliverable for this status audit is [Wave 7 Handoff](WAVE7_HANDOFF.md), which prepares future agents for Long-Term Capital Deployment without authorizing app behavior changes.

## Next Recommended Wave

### Current: Wave 6.5 Product Integration And Stabilization

Goal: integrate Wave 6 learning outputs, update roadmap status, and align the product around long-term capital deployment and learning without changing model behavior.

Suggested scope:

- Integrate Wave 6 learning outputs conceptually across docs and future report-context expectations.
- Update roadmap status after merged learning PRs.
- Add report-context schema/status validation later if appropriate.
- Align dashboard/report context around capital deployment and learning.
- Ensure manual journal, outcomes, catalyst follow-through, source usefulness, and decision-safety effectiveness remain review-only.
- Prepare for Wave 7.

Exit criteria:

- Roadmap/status docs reflect PRs #33-#38.
- [Wave 7 Handoff](WAVE7_HANDOFF.md) gives future agents a clear long-term capital deployment brief.
- No learning output changes score, action, target, target confidence, suggested amount, decision gate, source weighting, provider behavior, broker behavior, or trading behavior.
- Provider gap cleanup and ETF expected-gap work are left as scoped follow-up branches.

Future development should not move into Wave 7 before Wave 6 integration and stabilization are done.

### Next: Wave 7 Long-Term Capital Deployment

Wave 7 should focus on the daily question:

> What should I buy/add today for long-term holdings?

Likely Wave 7 branches:

- `codex/long-term-add-queue`
- `codex/capital-deployment-context`
- `codex/best-add-if-blocked`
- `codex/long-term-holding-health-v1`
- `codex/capital-deployment-dashboard`

Wave 7 must remain recommendation-only. It should not add automatic trading, broker writes, order previews, tactical same-day trading, shorting, automatic model tuning, automatic source-weight changes, or AI-driven official recommendation changes.

## Integration Backlog

- Align learning outputs into a coherent report-context/dashboard story.
- Decide how manual journal, recommendation outcomes, source usefulness, catalyst follow-through, and decision-safety effectiveness should appear in daily review.
- Add capital-availability context before expanding broker read-only integration.
- Add status/schema validation for learning outputs if future report context starts depending on them.
- Keep AI synthesis, learning outputs, and feedback review-only until a future model-impact phase.
- Clarify ETF expected-gap handling in report context and provider gap summaries.

## Provider/Data Backlog

The provider gap action plan exists at `reports/provider-gap-action-plan.md`. Convert accepted actions into scoped provider/data cleanup branches.

Priority backlog:

- Restore current-price coverage for `BBAI`, `ALAB`, and `PLAB`.
- Resolve analyst-target breadth for operating companies or document manual/provider fallback paths.
- Mark ETF CIK, companyfacts, official IR, and company analyst target gaps as expected/non-operating-company gaps.
- Add TSM/foreign-issuer fallback planning for companyfacts-equivalent evidence.
- Improve official IR parser behavior and page-link fallback.
- Decide later whether paid FMP/Finnhub/Benzinga analyst/news/transcript coverage is justified.

## Deferred Decisions

- Paid analyst target coverage.
- Dedicated ETF logic.
- Broker read-only integration.
- Tactical trade mode.
- Earnings event mode.
- Future short-candidate review.
- Model-impact feedback/source weighting.
- Automatic score tuning.
- Local decision console implementation.
- Intraday signal console.

## Known Product Risks

- False confidence from thin analyst target coverage.
- ETF gaps being misread as operating-company provider failures.
- Provider gaps creating noisy operational work.
- AI briefs sounding more confident than source evidence allows.
- Learning metrics being mistaken for approved model tuning.
- Decision safety over-blocking good opportunities while trust is still being built.
- Broker integration pressure before capital availability is modeled safely.
- Tactical or speculative ideas leaking into long-term buy/add recommendations.

## Required Stabilization Before Moving On

Before Wave 7 begins:

- Confirm Wave 6 outputs are documented and review-only.
- Confirm no learning output changes score, action, target, target confidence, suggested amount, decision gate, or broker behavior.
- Decide the first capital-availability shape: configured/manual cash, monthly buy capacity, as-of date, and optional future read-only broker snapshot.
- Turn provider gap action plan items into scoped data cleanup branches.
- Document ETF expected-gap handling.
- Keep `python3 scripts/check_quality.py` passing after docs and future integration changes.
