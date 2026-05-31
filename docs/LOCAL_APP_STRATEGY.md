# Local App Strategy

This document defines how the product should evolve from static reports into a local decision console. It is strategy only and does not authorize real-time behavior, broker writes, order previews, automated trading, or dashboard implementation in this PR.

## Current State

The product currently produces local batch artifacts:

- Daily Markdown and CSV recommendations.
- Static dashboard HTML.
- Report context JSON.
- AI analysis context.
- AI briefs and prompt/review artifacts.
- Provider gap and source-health outputs.
- Manual journal, outcome, catalyst, source-usefulness, and decision-safety effectiveness records.

The static dashboard is useful for review, but the long-term product needs a local app that can organize decisions, history, learning, and run controls without becoming a trading system.

## Why A Local App Matters

A local decision console should help the user:

- See the latest recommendations.
- Find the best long-term add.
- Review provider gaps.
- Check decision safety.
- Inspect target confidence.
- Read AI briefs.
- Record and review manual journal entries.
- Review outcomes and model trust.
- Inspect run history.

The app should reduce friction in review, not increase automation risk.

## Local App Stages

1. Batch Reports And Dashboard
   - Current state.
   - Keep static report generation reliable.
   - Preserve phone/offline review artifacts.

2. Local Decision Console Shell
   - Add a durable local navigation shell.
   - Show latest recommendation review, best long-term add, provider gaps, decision safety, target confidence, AI briefs, manual journal, outcomes, model trust, and run history.
   - Keep all behavior local and recommendation-only.
   - Current Wave 9 implementation target: build a JSON manifest from existing local artifacts, render a static `reports/local-console.html` shell, and require the user to open it manually.
   - The shell must not include run buttons, real-time refreshes, broker access, order previews, or trading actions.

3. Local Run Control
   - Allow safer local invocation of approved batch commands.
   - Show run status, artifacts, and failure modes.
   - Do not add live trading or broker writes.

4. Pre-Market / Post-Market Modes
   - Separate daily review modes.
   - Pre-market: best add, readiness, provider gaps, catalysts, capital availability.
   - Post-market: outcome movement, source updates, score changes, event follow-through.

5. Intraday Signal Console
   - Future review surface for signals and news triggers.
   - Should remain a review console, not a trading bot.
   - No real-time broker/order behavior.

6. Optional Broker Read-Only Context
   - Deferred until cash/holdings uncertainty harms recommendations.
   - Must remain read-only and never support order placement, preview, modification, or cancellation.

## Event / Signal Architecture

Future event/signal architecture should support:

- Earnings date.
- Price move.
- Provider gap resolved.
- Target confidence changed.
- Decision gate changed.
- News/source event.
- AI brief generated.
- Source/catalyst follow-through signal.

Events should become review triggers and learning inputs. They should not become automated trade triggers.

## Pre-Market And Post-Market Review

Pre-market review should answer:

- What should I buy/add today?
- Is the top candidate decision-safe?
- What data gaps could invalidate the recommendation?
- What capital is available?
- What should I review before acting manually?

Post-market review should answer:

- What changed?
- Did today's signals matter?
- Which provider/source issues need attention?
- Did any blocked/watchlist names move toward buy-readiness?
- What should be queued for tomorrow?

## Earnings Review

Earnings review should eventually support:

- Pre-earnings expectations.
- Expected move and risk.
- Management guidance and transcript review.
- Post-earnings follow-through.
- Thesis changes.
- Source/catalyst usefulness.

Earnings mode should be separate from normal long-term buy/add mode.

## Intraday Signal Review

Intraday signals should be future review prompts only.

Possible triggers:

- Large price move.
- Major source/news event.
- Provider gap resolved.
- Target confidence changed.
- Decision gate changed.
- AI brief generated.

Intraday mode should not imply the app is monitoring markets for automated trading decisions.

## What Not To Build Yet

Do not build yet:

- Real-time broker/order behavior.
- Trading automation.
- Order preview.
- Broker write actions.
- Automatic score tuning.
- Automatic source-weight changes.
- Automatic recommendation changes from feedback or outcomes.
- Future short-candidate integration into current buy/add queues.

## Relationship To Broker Read-Only Integration

Broker read-only integration is optional and deferred.

Before broker integration, the app should support capital availability through:

- Configured/manual cash.
- Monthly buy capacity.
- As-of date.
- Later optional broker read-only snapshot.

Broker integration must remain read-only and should only be added when cash/holding accuracy becomes a recommendation blocker.
