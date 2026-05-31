# Wave 9 Local Decision Console Requirements

Wave 9 defines the Local Decision Console Shell. This document is requirements-only for a future local, read-only-first console. It does not authorize console implementation in this branch and does not change scoring, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, AI generation, dashboard rendering, storage schema, broker behavior, or trading behavior.

## Product Goal

The local decision console should organize the latest artifact-backed decision surfaces in one local review shell.

It should help answer:

- What is the latest recommendation review?
- What is the best long-term add?
- What is the current capital deployment status?
- What earnings events need review?
- What provider or data gaps matter?
- What AI briefs exist, and are they draft, reviewed, rejected, or guardrail-blocked?
- What manual journal entries and recommendation outcomes exist?
- What did the latest runs produce?
- Where are the latest artifacts?

The console is a review and navigation layer over existing reports, contexts, fixtures, storage outputs, and generated artifacts. It must remain recommendation-only and read-only unless a future requirement explicitly scopes a non-trading write such as local journal entry editing.

## Non-Goals

Wave 9 must not add:

- Automatic trading.
- Order preview.
- Broker write actions.
- Real-time market monitoring.
- Run-control execution yet.
- Live provider refresh from the console.
- Score changes.
- Target changes.
- Target-confidence changes.
- Decision-safety changes.
- Allocation formula changes.
- Automatic source-weight changes.
- Automatic recommendation changes from feedback, outcomes, AI, or learning history.
- Future short-candidate integration into current buy/add queues.

The console must not imply guaranteed performance, target achievement, risk-free outcomes, or automatic execution.

## Console Navigation Requirements

The initial console shell should provide durable navigation, not new model behavior.

Required navigation panels:

- Latest Recommendation Review.
- Long-Term Add Queue.
- Capital Deployment.
- Earnings Review.
- Provider And Data Gaps.
- AI Briefs.
- Manual Journal.
- Learning And Outcomes.
- Run History.
- Artifacts.

The first screen should stay focused on current decision support: latest recommendation review, best long-term add, capital deployment, and blocking gaps. Audit and history panels should be available without crowding the primary decision area.

Each panel should expose:

- `panel_id`
- `title`
- `state`
- `source`
- `read_only`
- `empty_state`
- `last_updated` when known

Panel states should be stable values such as `available`, `empty`, `missing`, `pending`, `review_needed`, or `not_applicable`.

## Latest Artifact Requirements

The console should discover and display the latest generated artifacts without requiring live refreshes.

Artifact rows should include:

- `artifact_id`
- `artifact_type`
- `path`
- `report_date`
- `created_at` when known
- `status`
- `source`
- `notes`

Required artifact types:

- `report_context`
- `dashboard_html`
- `daily_markdown`
- `daily_csv`
- `email_summary`
- `ai_analysis_context`
- `ai_briefs`
- `synthesis_packets`
- `provider_gap_report`

Missing artifacts should be visible as missing data, not hidden. The console should show a clear empty state when no generated artifacts exist.

## Latest Decision Snapshot Requirements

The console should read from the latest report context or equivalent artifact-backed context and summarize:

- Latest recommendation review status.
- Top recommendation symbol, action, score, and decision gate status when available.
- Best long-term add and backup add when available.
- Capital deployment status and suggested manual review amount when available.
- Earnings review status.
- Provider/data gap status.
- AI brief review status.
- Learning/outcome review status.

The snapshot must preserve official recommendation fields exactly as produced by upstream analysis. It must not recalculate scores, change labels, change targets, alter decision safety, or change suggested amounts.

## Run History Requirements

Run history should show what local batch commands produced recently, without executing commands in Wave 9.

Run rows should include:

- `run_id`
- `run_type`
- `status`
- `started_at`
- `finished_at`
- `commands`
- `artifacts`
- `warnings`
- `errors`

Supported run statuses should include `success`, `ok_with_warnings`, `failed`, `missing`, and `not_run`.

Wave 9 requirements may define the run-history display contract. The console must not invoke run commands, live provider refreshes, broker actions, or model calls until future run-control requirements explicitly scope them.

## Read-Only Panel Requirements

All Wave 9 panels are read-only.

The shell may display:

- Existing recommendations.
- Existing long-term add queue outputs.
- Existing capital availability and allocation-safety explanations.
- Existing earnings event review outputs.
- Existing provider/data gaps.
- Existing AI brief records and guardrail outcomes.
- Existing manual journal entries.
- Existing recommendation outcomes, catalyst follow-through, source usefulness, and decision-safety effectiveness summaries.
- Existing run history and artifact paths.

The shell must not write to storage, mutate artifacts, edit recommendations, submit broker actions, or run live ingestion/model calls in this branch.

## Recommendation-Only Guardrails

Every console scenario must preserve these guardrails:

- `no_automatic_trading`
- `no_broker_write`
- `no_order_preview`
- `no_real_time_market_monitoring`
- `no_run_control_execution_yet`
- `no_live_provider_refresh_from_console`
- `no_score_target_decision_safety_changes`
- `no_automatic_source_weight_changes`
- `no_automatic_recommendation_changes_from_feedback_or_outcomes`
- `no_future_short_candidate_in_buy_add`

Wording should use "review", "consider", "manual decision", and "hold buy capacity" where appropriate. It should not say "place an order", "execute", "guaranteed", "risk-free", or "will outperform".

## Accessibility And Phone Review

The future console should remain usable from a phone-sized viewport and should preserve the existing report-artifact habit of being easy to inspect locally.

Requirements:

- Decision-first summary appears before detailed audit sections.
- Critical blocked/missing states are visible without relying on color alone.
- Links to latest artifacts use readable labels and paths.
- Tables or lists should collapse into scannable rows on narrow screens.
- Empty states should say what is missing and what future review should check.
- Controls should not resemble trading controls or broker order tickets.

## Fixture Scenarios

Fixture scenarios live in `tests/fixtures/local_console/`.

Required scenarios:

| Scenario | Fixture | Purpose |
| --- | --- | --- |
| Latest long-term capital deployment available | `latest_long_term_capital_deployment_available.json` | Latest report context and long-term add queue are available with a decision-safe long-term add. |
| No safe add / hold capital | `no_safe_add_hold_capital.json` | Console shows buy capacity should be held because no decision-safe add exists. |
| Earnings review pending | `earnings_review_pending.json` | Console routes attention to an upcoming or recent earnings event requiring review. |
| AI brief draft/reviewed/rejected states | `ai_brief_draft_reviewed_rejected_states.json` | Console displays AI brief review status without treating AI as recommendation-changing. |
| Provider gaps present | `provider_gaps_present.json` | Console surfaces blocked, stale, missing, or rate-limited provider/data gaps. |
| Learning review with outcomes/journal | `learning_review_with_outcomes_journal.json` | Console summarizes manual actions and outcomes as review-only learning. |
| No learning history yet | `no_learning_history_yet.json` | Console handles missing outcome or journal history gracefully. |
| Missing latest report context | `missing_latest_report_context.json` | Console shows a missing-context state without crashing or inventing recommendations. |
| No generated artifacts | `no_generated_artifacts.json` | Console shows artifact empty states and does not run commands automatically. |

These fixtures are contract examples. Future implementation branches should either consume them directly or preserve their scenario labels, guardrails, and read-only behavior in behavior-level fixtures.

## Future Run-Control Boundary

Run control is a future phase.

Before run control is implemented, a separate requirement should define:

- Which commands are safe to invoke locally.
- How command arguments are constrained.
- How run logs, errors, and generated artifacts are displayed.
- How provider/network failures are surfaced.
- How to prevent accidental broker, trading, or write behavior.

Wave 9 only defines read-only run-history display and artifact discovery expectations. It does not add command execution.

## Future Intraday Boundary

Intraday mode is future review-only work, not part of the initial local console shell.

Future intraday review must not create a live trading console. It may eventually show review triggers such as price moves, source events, provider-gap resolution, or AI brief generation, but those triggers must remain review prompts and must not change official recommendations or trigger trades.

## Future Broker-Read-Only Boundary

Broker read-only context is optional and deferred.

If broker read-only context is added later, it must:

- Remain read-only.
- Avoid order preview, order placement, order modification, or cancellation.
- Avoid broker account writes.
- Explain as-of timestamps and data freshness.
- Fall back to configured/manual capital availability when broker data is missing.

Broker data must never make the console an execution surface.
