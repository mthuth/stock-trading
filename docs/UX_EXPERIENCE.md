# Stock Trading Dashboard UX Experience

## Experience Goal

The dashboard should help the investor answer one question quickly and safely:

> What should I review next, why does the engine think that, and what data quality issues could make the recommendation unreliable?

The product remains recommendation-only. The experience must never imply that a trade has been placed, previewed, or guaranteed. Every action should preserve the user's role as final decision-maker.

## Primary User

The primary user is a retirement-account investor reviewing a focused technology-stock universe before market open and after market close. They need fast prioritization, plain-English rationale, and enough evidence to trust or challenge the score without reading raw provider payloads.

Key needs:

- See the next best review candidate without scanning the full universe.
- Separate long-term holdings, tactical opportunities, ETFs, and speculative AI names.
- Understand whether upside comes from a broad blended target or a thin single-source target.
- Spot stale provider data, blocked endpoints, and source-health issues before acting.
- Record feedback so the engine improves over repeated review cycles.

## Experience Principles

1. Decision first, audit second.
   The first screen should prioritize the Action Queue and top candidate. Detailed scoring, evidence, target sources, and full-universe tables should be one click away.

2. Confidence is part of the recommendation.
   Upside, score, and action must appear with data status, target confidence, and source-health context.

3. Sleeve context matters.
   A long-term Add, weekly swing Watch, ETF allocation idea, and speculative AI watchlist item should not feel like the same kind of decision.

4. Provider gaps are operational work, not noise.
   If an upstream source is blocked, stale, missing, or rate-limited, the dashboard should show the next action clearly.

5. Feedback should be low-friction and auditable.
   The current static dashboard can generate local save commands. A later local app can convert the same workflow into direct SQLite writes.

## Core Journey

### 1. Pre-Market Review

Entry point: `reports/dashboard-YYYY-MM-DD.html`

User intent:

- Check the top recommendation and Action Queue.
- Confirm data freshness and source health.
- Decide whether to buy manually, keep watching, or ignore the recommendation.

Expected flow:

1. Read the top recommendation summary.
2. Review the Pre-Market Readiness checklist for price data, target trust, source health, holdings context, and feedback review.
3. Open the Action Queue.
4. Hover or focus the action label for quick rationale.
5. Click the row for score explanation, target sources, research brief, and evidence.
6. Check Data Gaps or Health & Trends if confidence is low, target range is wide, or the source health count is elevated.
7. Record Agree, Disagree, or Too Risky feedback.

Success criteria:

- User can identify the top review candidate in under 10 seconds.
- User can explain why it is Add, Watch, Hold, or Avoid without opening source code.
- User can see whether the recommendation is blocked by missing or stale data before making any manual trade decision.

### 2. After-Close Review

Entry points:

- `reports/end-of-day-YYYY-MM-DD.md`
- `reports/dashboard-YYYY-MM-DD.html`
- `reports/next-day-watchlist-YYYY-MM-DD.md`

User intent:

- Understand what changed since the prior run.
- Review source-health failures.
- Prepare the next-day watchlist.

Expected flow:

1. Open End-of-Day Review.
2. Review score changes and source-health alerts.
3. Open dashboard Health & Trends for sparkline and source status context.
4. Open Next-Day Watchlist before the next session.
5. Add source feedback if a provider or source was useful, noisy, stale, or misleading.

Success criteria:

- User can distinguish "nothing changed" from "recommendation did not change because data failed to refresh."
- User can see which source issue is the top operational blocker.
- Next-day candidates are visible without scanning all rows.

### 3. Research Drilldown

Entry point: expanded recommendation row.

User intent:

- Challenge the score.
- Inspect target components.
- Review evidence and source attribution.

Expected flow:

1. Click a recommendation row.
2. Review the action rationale and blended target summary.
3. Inspect score driver weights and penalties.
4. Compare analyst, fundamental, and technical target inputs.
5. Read bull signals, bear/risk signals, recent catalysts, filings/transcripts/news, source confidence, and what would change the view.

Success criteria:

- Score explanation uses plain language and raw/weighted values.
- Target-source detail separates analyst, fundamental, and technical inputs.
- Evidence attribution is visible at the source level.

### 4. Feedback Loop

Entry point: Feedback tab.

User intent:

- Teach the engine which recommendations and sources are useful.

Expected flow:

1. Choose Recommendation or Research source.
2. Select symbol or source.
3. Add optional notes.
4. Choose Agree, Disagree, Too Risky, Useful Source, or Noisy Source.
5. Run the generated local command.

Success criteria:

- Feedback is captured as structured data.
- Feedback does not distract from the trading recommendation workflow.
- Source feedback can adjust future source weighting without hiding audit history.

## Information Architecture

### Header Summary

Purpose: orient the user immediately.

Required content:

- Generated timestamp.
- Recommendation-only status.
- Top recommendation and action.
- Score.
- Suggested amount or review priority.
- Blended target.
- Upside.
- Source health count.

### Recommendations

Primary tab for trading review.

Subtabs:

- Action Queue: first stop for Add, Watch, and Hold decisions.
- Long-Term Queue: 75% sleeve review.
- Short-Term Queue: day, week, and 2-4 week tactical review.
- Next-Day Watchlist: pre-market prep list.
- Speculative AI Watchlist: observation-only names.
- Data Gaps: symbol-level and source-level quality blockers.

### Current Holdings

Purpose: show what portfolio context was used by the engine.

Required content:

- Holdings source.
- Quantity.
- Last price.
- Market value.
- Portfolio percentage.
- Allocation bars and cap context.

### Health & Trends

Purpose: operational trust.

Required content:

- Source health alerts.
- Top blocker.
- Score changes.
- Historical score trend.

### Research Sources

Purpose: source transparency and implementation planning.

Required content:

- Source implementation status.
- Records captured.
- Last run.
- Latest issue.
- Next action.
- Access model and user action needed.
- Expanded source record detail.

### Feedback

Purpose: review capture.

Required content:

- Feedback target type.
- Symbol or source selector.
- Free-text note.
- Structured feedback buttons.
- Generated local save command.

## Key States

### Recommendation Actions

Use the controlled labels from requirements:

- Strong Buy
- Buy
- Add
- Hold
- Watch
- Trim
- Avoid

Current V1 dashboard emphasis is Add, Watch, Hold, and Avoid. Strong Buy, Buy, and Trim can be introduced only when scoring thresholds and portfolio rules support them safely.

### Data Status

Important statuses:

- Blended: target includes multiple usable inputs.
- Partial blend: target exists but source breadth is limited.
- Wide range: source disagreement or model range is large.
- Needs price: current price is missing.
- Needs target: target is missing.
- Needs paid target provider: known provider limitation.

### Source Health

Important states:

- Healthy.
- Needs attention.
- Stale.
- Not implemented.
- Blocked by provider plan or credential.

## Desktop Layout Requirements

- Keep Action Queue visible as the primary work surface.
- Keep the full ranked universe collapsed by default.
- Use compact tables for repeated operational review.
- Avoid marketing-style hero content.
- Preserve horizontal scrolling for dense audit tables where necessary.
- Keep row expansion details directly below the selected row.

## Mobile And Phone-Friendly Requirements

The dashboard should remain usable when the user cannot run localhost and is reviewing a rendered artifact.

Requirements:

- Generated HTML remains the canonical interactive artifact.
- Generated PNG/PDF views should be produced for large diagrams or phone sharing when the experience is too dense for chat.
- Main tabs and recommendation subtabs should horizontally scroll without wrapping into unreadable controls.
- Secondary columns may hide on narrow screens only when the row still preserves rank, symbol, action, score, current price, target, upside, and rationale access.
- No text should overlap table cells, tabs, metrics, or feedback controls.

## Accessibility Expectations

- Tabs use `role="tab"` and `aria-selected`.
- Expandable recommendation and source rows are keyboard reachable.
- Hover explanations should also work on focus.
- Tables should keep visible headings.
- Color should never be the only indicator of recommendation action or health state.

## Current Experience Assessment

Already present:

- Dashboard tabs for Recommendations, Current Holdings, Health & Trends, Research Sources, and Feedback.
- Recommendation subtabs for Action Queue, Long-Term Queue, Short-Term Queue, Next-Day Watchlist, Speculative AI Watchlist, and Data Gaps.
- Header summary and recommendation tables expose target confidence and data status before drilldown.
- Pre-Market Readiness checklist exposes advisory checks for price data, target trust, source health, holdings context, feedback review, and next-day setup above the Action Queue.
- Top next-day watch preview appears inside Pre-Market Readiness with a direct jump to the Next-Day Watchlist.
- Compact print/PDF review mode keeps Pre-Market Readiness, Action Queue, Data Gaps, and Next-Day Watchlist usable as a browser-exported phone review.
- Action Queue and recommendation subtabs expose changed-since-last-run badges so score, target, action, and new-row movement are visible before drilldown.
- Action Queue opens as a compact decision scan with rank, action, score, change marker, core metrics, and rationale, while the full audit table remains collapsed below.
- Expandable recommendation rows with score explanation, research brief, target sources, and recent evidence.
- Source health alerts, score changes, and score trend sparklines.
- Source issue groups summarize network/DNS, provider access, missing data, provider error, and other root causes above detailed source-health alerts.
- Source health alert filters let the user switch between all alerts, blockers, review items, and info rows without hiding the audit table.
- Research source drilldowns with records, implementation status, next action, and user action.
- Feedback controls can save through the local dashboard server when available, show recent feedback, and fall back to generated local save commands for static HTML review.

Primary UX gaps:

- Target confidence still needs to carry through CSV and end-of-day Markdown summaries.

## Near-Term UX Backlog

1. Add target confidence to CSV and end-of-day Markdown summaries.

## Acceptance Criteria

- The dashboard opens to a decision-focused recommendations view, not a full-universe data dump.
- Every recommendation row can answer: action, score, current price, blended target, upside, trade type, rationale, confidence, and data status.
- Every expanded row can answer: how the score was calculated, which target sources were used, what evidence supports the view, and what would change the view.
- Every source-health alert includes last run, latest issue, and next action.
- Feedback can be captured without editing files by hand.
- The experience remains explicitly recommendation-only.
