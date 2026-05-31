# Wave 12 Alerts And Review Triggers Requirements

Wave 12 defines the Alerts and Review Triggers layer. This document is requirements-only for fixture and test-harness alignment. It does not authorize alert implementation in this branch and does not change scoring formulas, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, AI generation, dashboard rendering, local-console implementation, storage schema, broker behavior, or trading behavior.

## Product Goal

Wave 12 should create review-only alerts that help the user know what changed and what to review manually.

Alerts should help answer:

- Did the decision gate change?
- Did target confidence improve or degrade?
- Did a provider/data gap resolve or become worse?
- Did price move enough to review?
- Did earnings move into a pre/post review window?
- Did a new source/news/catalyst event arrive?
- Did an AI brief get generated, reviewed, rejected, or fail guardrails?
- Did a recommendation outcome or tactical setup outcome cross a review threshold?
- Did a long-term add become blocked or decision-safe?
- Did a watchlist/speculative name move closer to buy-readiness?

Alerts are review prompts. They are not trading signals, order instructions, or automatic recommendation changes.

## Non-Goals

Wave 12 must not add:

- Automatic trading.
- Order preview.
- Broker write actions.
- Real-time broker/order behavior.
- Margin/account trading logic.
- Automatic scoring changes.
- Automatic target changes.
- Automatic decision-safety changes.
- Automatic source-weight changes.
- Model tuning.
- Automatic recommendation changes from alerts.
- Live push, email, SMS, Slack, or other external notification integrations unless a future branch scopes them as mock/local-only.

Alerts must not imply guaranteed performance, target achievement, risk-free outcomes, or urgency to trade.

## Alert And Review-Trigger Taxonomy

Supported alert types:

- `decision_gate_changed`
- `target_confidence_changed`
- `provider_gap_resolved`
- `provider_gap_worsened`
- `price_move_review`
- `earnings_window_entered`
- `post_earnings_review_due`
- `source_event_review`
- `ai_brief_ready`
- `ai_brief_guardrail_failed`
- `recommendation_outcome_review`
- `tactical_setup_review`
- `model_trust_changed`
- `capital_deployment_review`
- `watchlist_readiness_changed`

Each alert should include:

- `alert_id`
- `alert_type`
- `status`
- `severity`
- `priority`
- `created_at`
- `symbol`
- `company`
- `decision_mode`
- `source`
- `event_summary`
- `why_review`
- `review_action`
- `prior_state`
- `current_state`
- `dedupe_key`
- `dedupe_group`
- `related_artifacts`
- `review_only_note`

## Alert Lifecycle And Statuses

Supported statuses:

- `new`
- `seen`
- `acknowledged`
- `deferred`
- `dismissed`
- `resolved`

Lifecycle updates should be local review metadata only. They must not change recommendations, scores, targets, decision gates, source weights, allocation, provider behavior, broker behavior, or trading behavior.

## Severity And Priority Rules

Supported severity levels:

- `critical_review`
- `high_review`
- `medium_review`
- `low_review`
- `informational`

Suggested severity guidance:

- `critical_review`: review-blocking data reliability, guardrail failure, or a major decision gate change.
- `high_review`: buy/add safety state changed, major provider gap worsened, post-earnings review due, or price move above threshold.
- `medium_review`: target confidence changed, provider gap resolved, tactical setup appeared, or model trust changed.
- `low_review`: source/catalyst event to inspect, AI brief ready, or watchlist readiness changed without buy-readiness.
- `informational`: no-action or resolved lifecycle summaries.

Priority should be deterministic and stable within a generated alert inbox. Missing data should raise warnings rather than inflating severity.

## Deduplication Requirements

Alerts should deduplicate repeated signals that refer to the same symbol, alert type, source, and review window.

Deduplication should include:

- Stable `dedupe_key`.
- Optional `dedupe_group`.
- `duplicate_of` when an alert is collapsed.
- Count of collapsed duplicate signals where available.
- Preservation of the most severe or most recent review prompt when duplicates conflict.

Deduplication must not hide materially different alert types or statuses.

## Local Console Alert Inbox Requirements

A future local console alert inbox should be local and read-only-first.

Inbox rows should show:

- Alert type.
- Severity.
- Status.
- Symbol and company.
- Event summary.
- Why review.
- Review action.
- Created time.
- Related artifact links.
- Review-only note.

The console should not include run buttons, live refresh buttons, broker actions, order previews, order tickets, or external notification sending in Wave 12.

## Event And Signal Boundaries

Alerts may be derived from existing deterministic review surfaces:

- Decision safety.
- Target confidence.
- Provider/data gaps.
- Price history.
- Earnings event/review windows.
- Source/news/catalyst evidence.
- AI brief review and guardrails.
- Recommendation outcomes.
- Tactical setup outcomes.
- Model trust score.
- Long-term add queue and capital deployment.
- Watchlist/speculative readiness.

Alerts must not recalculate official model outputs. They should report state changes or review triggers from stored or fixture-backed data.

## Broker And Trading Boundaries

Alerts must not:

- Place trades.
- Preview orders.
- Write to broker accounts.
- Use margin/account trading logic.
- Trigger real-time broker/order behavior.
- Tell the user to execute a trade.
- Promote a tactical setup, AI brief, model trust change, or provider gap into an official recommendation.

Alert wording should use "review", "inspect", "check", "watch", "hold for review", or "acknowledge". It should not use broker/order language.

## Acceptance Criteria

- Requirements doc is clear and Codex-readable.
- Fixture scenarios cover decision gate changed from blocked to ready, target confidence degraded, provider gap resolved, provider gap worsened, price moved above threshold, upcoming earnings entered pre-earnings window, post-earnings review due, new source/catalyst event, AI brief ready, AI brief guardrail failed, recommendation outcome crossed review threshold, tactical setup appeared, model trust changed, duplicate alerts need deduping, alert acknowledged/dismissed lifecycle, and no alerts.
- Fixture tests validate alert types, statuses, severity levels, lifecycle fields, deduplication fields, local-only/no-notification boundaries, and review-only behavior.
- Tests do not require live provider calls, broker credentials, model calls, report rendering, storage schema changes, local-console implementation changes, or alert implementation modules.
- No product behavior changes.
- No scoring, target, recommendation-label, decision-safety, allocation, provider-ingestion, AI-generation, dashboard, local-console, storage, broker, or trading behavior changes.

## Fixture Scenarios

Fixture scenarios live in `tests/fixtures/alerts/`.

Required scenarios:

| Scenario | Fixture | Purpose |
| --- | --- | --- |
| Decision gate changed from blocked to ready | `decision_gate_blocked_to_ready.json` | Buy/add candidate becomes review-worthy without automatically changing recommendations. |
| Target confidence degraded | `target_confidence_degraded.json` | Target confidence degradation prompts manual review. |
| Provider gap resolved | `provider_gap_resolved.json` | Resolved provider gap is visible as an informational review prompt. |
| Provider gap worsened | `provider_gap_worsened.json` | Worsened provider gap raises review priority. |
| Price moved above threshold | `price_move_above_threshold.json` | Large price move queues review without becoming a trade signal. |
| Upcoming earnings entered pre-earnings window | `earnings_pre_window_entered.json` | Earnings date entering pre-window queues review. |
| Post-earnings review due | `post_earnings_review_due.json` | Recent earnings require post-event review. |
| New source/catalyst event | `source_catalyst_event.json` | Source/catalyst evidence queues review. |
| AI brief ready | `ai_brief_ready.json` | Generated or reviewed AI brief appears in alert inbox. |
| AI brief guardrail failed | `ai_brief_guardrail_failed.json` | Guardrail failure gets high review priority but remains non-authoritative. |
| Recommendation outcome crossed review threshold | `recommendation_outcome_threshold.json` | Outcome movement crosses a review threshold. |
| Tactical setup appeared | `tactical_setup_appeared.json` | Tactical setup queues review without affecting long-term recommendations. |
| Model trust changed | `model_trust_changed.json` | Model trust change is review-only. |
| Duplicate alerts need deduping | `duplicate_alerts_need_deduping.json` | Duplicate keys collapse repeated signals. |
| Alert acknowledged/dismissed lifecycle | `alert_lifecycle_acknowledged_dismissed.json` | Lifecycle status transitions are local review metadata. |
| No alerts | `no_alerts.json` | Empty alert inbox is explicit and does not invent alerts. |

These fixtures are contract examples. Later implementation branches should either consume them directly or add behavior-level fixtures that preserve these scenario labels, statuses, severities, deduplication behavior, and review-only guardrails.

## Future Integration Notes

Future Wave 12 implementation should prefer focused helper modules and fixture-driven tests before report, dashboard, local-console, storage, workflow, or notification changes.

Likely follow-up branches:

- `codex/alert-trigger-definitions`
- `codex/alert-inbox-view-model`
- `codex/alert-deduplication`
- `codex/alert-lifecycle-local`
- `codex/local-console-alert-section`

Any future external notification integration must be separately scoped and must be local/mock-only until explicitly approved. Alerts remain review prompts, not trade signals.
