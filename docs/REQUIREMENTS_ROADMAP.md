# Requirements Roadmap

This roadmap translates the current product requirements into scoped development lanes for future Codex agents. It is a planning document only. It does not change scoring, target blending, recommendation labels, workflow behavior, dashboard behavior, provider ingestion, configuration, broker behavior, or trading behavior.

The stock-trading app remains recommendation-only decision support for a human investor. Future work must not place trades, preview orders, imply guaranteed performance, hide source-health uncertainty, or let feedback/AI/outcomes silently change official recommendations.

Related strategy docs:

- [Product Strategy](PRODUCT_STRATEGY.md)
- [Roadmap Status](ROADMAP_STATUS.md)
- [Wave 7 Handoff](WAVE7_HANDOFF.md)
- [Wave 8 Earnings Review Requirements](WAVE8_EARNINGS_REVIEW_REQUIREMENTS.md)
- [Decision Modes](DECISION_MODES.md)
- [Model Learning Strategy](MODEL_LEARNING_STRATEGY.md)
- [Local App Strategy](LOCAL_APP_STRATEGY.md)
- [UX Experience](UX_EXPERIENCE.md)

## Roadmap Status

Current status after Waves 1-6:

- Waves 1-5 are complete.
- Wave 6 is complete: manual journal, recommendation outcome tracking, decision-safety effectiveness, catalyst follow-through, and source usefulness have merged.
- PR #38 is complete: product strategy, roadmap status, decision modes, model learning strategy, and local app strategy are documented.
- The current step is Wave 6.5: Product Integration And Stabilization.
- The next feature wave is Wave 7: Long-Term Capital Deployment.
- Future development should not move into Wave 7 until Wave 6 integration and stabilization are done.

Use [Roadmap Status](ROADMAP_STATUS.md) as the living status map before starting new feature work.

## North Star Update

Current daily use case:

> What should I buy/add today, especially for long-term holdings?

Broader future use case:

> What should I review today to make better decisions?

Long-term product vision:

> A learning AI recommendation system that makes predictions, tracks outcomes, compares models, and improves over time.

Risk phase model:

1. Cautious Deployment
2. Measured Aggression
3. Performance Seeking

The app should start moderately safe / cautious growth. It can become more aggressive only after model trust is established through outcomes. The long-term performance goal is returns meaningfully above market performance, ideally at least 2x market performance once confidence is earned.

Decision modes and horizons are defined in [Decision Modes](DECISION_MODES.md). Long-term buy/add is the current priority. Long-term sell/trim should begin later as holding-health review rather than "sell now" output.

## Roadmap Principles

1. Preserve recommendation-only behavior.
   Every feature must keep the user as the final decision-maker. Reports, scores, labels, targets, AI briefs, and dashboards are review aids, not execution instructions.

2. Keep data quality visible.
   Provider failures, stale inputs, blocked endpoints, expected ETF gaps, and missing fields should surface as provider gaps, expected-gap labels, or source-health context instead of being silently ignored.

3. Protect model contracts.
   Scoring weights, target-blending weights, confidence rules, speculative-AI caps, allocation/suggested amount logic, and recommendation labels are product contracts. Change them only when the task is explicitly model tuning and has regression coverage.

4. Separate decision surfaces from audit surfaces.
   The primary dashboard should help the user decide what to review next. Detailed score, target, source, evidence, learning, and outcome explanations should remain available without crowding the first scan.

5. Keep package boundaries clean.
   Ingestion, analysis, presentation, workflows, storage, and scripts each have separate responsibilities. Shared behavior should move into package APIs before scripts grow new logic.

6. Prefer regression safety before new intelligence.
   Before adding model impact from AI, feedback, outcomes, or source usefulness, establish fixtures, report-context checks, source-quality history, and explicit promotion decisions.

## Current Architecture Contract

| Area | Owns | Must Not Own |
| --- | --- | --- |
| Ingestion | Provider refresh, evidence capture, source health, provider gaps, provider-neutral orchestration | Report rendering, scoring internals, dashboard behavior |
| Analysis | Scoring, targets, confidence, decision safety, verification queues, report context assembly | Provider/network calls, CLI modules, presentation rendering, scripts |
| Presentation | Dashboard, Markdown, email, CSV, and context validation rendering | Provider clients, storage internals, analysis engine internals, script modules |
| Workflow modules | Coordination of package APIs for daily, analysis, rendering, and refresh flows | Core scoring, provider implementation details, presentation formatting rules |
| Scripts | Compatibility wrappers around package APIs and workflows | New business logic that bypasses package boundaries |
| Storage | Database schema and repositories | Presentation behavior or provider-specific decision logic |

## Concurrent Development Lanes

| Lane | Primary Agent | Primary Scope | Default Branch Pattern |
| --- | --- | --- | --- |
| Regression safety | QA Agent | Tests, fixtures, report-context validation, boundary checks | `codex/qa-*` |
| Decision review UX | UX Agent | Dashboard review flow, feedback ergonomics, summary exports | `codex/ux-*` |
| Data and source quality | Ingestion Agent | Provider gaps, evidence freshness, source health, ingestion plans | `codex/ingestion-*` |
| Model transparency | Analytics Agent | Score explanations, target-source drilldowns, confidence rationale | `codex/analysis-*` |
| AI synthesis | Analytics Agent with UX review | Deterministic briefs, synthesis packets, explanatory summaries | `codex/ai-*` |
| Learning system | Analytics/QA | Prediction records, outcomes, source usefulness, model trust, shadow evaluation | `codex/learning-*` |
| Local app | UX/Architecture | Local decision console, run history, local review flows | `codex/local-app-*` |
| Architecture hygiene | Architecture Agent | Package boundaries, workflow APIs, script-wrapper compatibility | `codex/arch-*` |
| Documentation | Architecture Agent or relevant lane owner | Requirements, runbooks, acceptance criteria, handoff notes | `codex/docs-*` |

Agents may work concurrently only when branches stay within one lane and do not alter shared product contracts outside their scope.

## Completed Waves

## Wave 1: Stabilize And Protect

Status: Complete.

Outcome: package boundaries, regression fixture coverage, provider-gap visibility, and recommendation-only guardrails were established.

## Wave 2: Improve Decision Review

Status: Complete.

Outcome: decision safety, provider gap review, target drilldowns, score explainability, and dashboard review flow were integrated.

## Wave 3: Improve Data Quality

Status: Complete.

Outcome: provider gap normalization, source health, SEC/IR coverage, and data reliability review matured.

## Wave 4: Model Transparency And Allocation Safety

Status: Complete.

Outcome: technical/fundamental target transparency, target confidence calibration, watchlist-only enforcement, and allocation safety were added.

## Wave 5: AI Synthesis

Status: Complete.

Outcome: AI evidence guardrails, prompt packets, synthesis readiness, AI brief review workflow, and LLM research brief drafting landed as explanatory-only outputs.

## Wave 6: Learning System Foundations

Status: Complete.

Outcome: manual trade journal, recommendation outcome tracking, decision-safety effectiveness, catalyst follow-through, and source usefulness were added as review-only learning foundations.

## Next Recommended Wave

### Wave 6.5: Product Integration And Stabilization

Goal: integrate Wave 6 learning outputs, update roadmap status, align dashboard/report context around long-term capital deployment and learning, and prepare for Wave 7 without changing model behavior.

Acceptance criteria:

- Wave 6 learning outputs are documented as review-only.
- Manual journal, outcomes, catalyst follow-through, source usefulness, and decision-safety effectiveness have a coherent integration plan.
- [Wave 7 Handoff](WAVE7_HANDOFF.md) is available before Wave 7 implementation starts.
- Report-context schema/status validation is added later only if appropriate and scoped.
- Dashboard/report context direction is aligned around long-term capital deployment and learning.
- Review-only outputs remain review-only.
- Provider gap action plan is split into scoped provider/data cleanup branches.
- ETF expected-gap handling is documented before broad provider-gap display changes.
- Run `python3 scripts/check_quality.py`.

Do not move into Wave 7 before Wave 6.5 stabilization is done.

## Future Waves

## Wave 7: Long-Term Capital Deployment

Goal: improve long-term buy/add decisions and capital availability without broker writes or order preview.

Read [Wave 7 Handoff](WAVE7_HANDOFF.md) before starting implementation.

Likely scope:

- Best long-term add review.
- Capital availability concept: configured/manual cash, monthly buy capacity, as-of date, and future optional broker read-only snapshot.
- Long-term capital deployment history.
- Holding-health review framing for future trim/sell logic.

Broker integration remains deferred unless cash/holding accuracy becomes a recommendation blocker.

## Wave 8: Earnings Event Review

Goal: create pre-earnings and post-earnings review modes.

Read [Wave 8 Earnings Review Requirements](WAVE8_EARNINGS_REVIEW_REQUIREMENTS.md) before starting implementation.

Likely scope:

- Earnings date/event calendar.
- Expected move and risk framing.
- Earnings transcript/IR evidence.
- Post-earnings catalyst follow-through.
- Thesis changes and invalidation conditions.

## Wave 9: Local Decision Console Shell

Goal: evolve from static reports into a local decision console shell.

Likely scope:

- Latest recommendations.
- Best long-term add.
- Provider gaps.
- Decision safety.
- Target confidence.
- AI briefs.
- Manual journal.
- Outcomes.
- Model trust.
- Run history.

No real-time broker/order behavior and no trading automation.

## Wave 10: Tactical Trade Review

Goal: define tactical trade review separately from long-term buy/add recommendations.

Likely scope:

- Tactical mode and horizons.
- Shorter-duration catalyst/trend framing.
- Review-only entry/exit context.
- Strict separation from long-term core recommendation labels.

## Wave 11: Model Evaluation And Backtesting

Goal: evaluate historical predictions, outcomes, sources, and safety gates.

Likely scope:

- Prediction record evaluation.
- Benchmark comparison.
- Drawdown control.
- Target progress.
- Decision-safety effectiveness.
- Source usefulness and AI thesis quality.

No automatic score tuning or recommendation changes.

## Wave 12: Alerts And Review Triggers

Goal: surface review-worthy changes without creating trade execution, order preview, or broker-write behavior.

Likely triggers:

- Earnings date.
- Price move.
- Provider gap resolved.
- Target confidence changed.
- Decision gate changed.
- News/source event.
- AI brief generated.
- Source/catalyst follow-through signal.

Alerts are review prompts, not trade instructions.

## Wave 13: Multi-Model Shadow Competition

Goal: compare alternative models in shadow mode before any model-promotion decision.

Rules:

- Shadow output is non-authoritative.
- Official recommendation label, score, target, confidence, suggested amount, and decision safety remain unchanged.
- Promotion requires outcome evidence and a separate model-promotion decision.

## Wave 14: Broker Read-Only Integration

Goal: improve holdings/cash context only if manual/configured capital availability is insufficient.

Rules:

- Read-only only.
- No order placement.
- No order preview.
- No account write actions.
- Missing/stale broker snapshots must surface as reliability gaps.

## Provider And ETF Notes

The provider gap action plan exists at `reports/provider-gap-action-plan.md` and should be turned into scoped provider/data cleanup branches.

ETF logic is deferred. ETFs should not create false operating-company provider failures. ETF SEC CIK, companyfacts, official IR, and company analyst target gaps should be labeled expected/non-operating-company gaps until a dedicated ETF logic track exists.

Analyst coverage is deferred. Do not pay for broader analyst coverage until model maturity, app usage, trading activity, deployed capital, or repeated target-confidence bottlenecks justify the cost.

## Suggested Branch Names

Use short-lived branches with the `codex/` prefix and keep each branch to one change area.

| Work Type | Suggested Branch |
| --- | --- |
| Roadmap integration | `codex/product-integration-stabilization` |
| Long-term capital deployment | `codex/long-term-capital-deployment` |
| Earnings event review | `codex/earnings-event-review` |
| Local decision console | `codex/local-decision-console` |
| Tactical trade review | `codex/tactical-trade-review` |
| Model evaluation | `codex/model-evaluation-backtesting` |
| Alerts and review triggers | `codex/alerts-review-triggers` |
| Multi-model shadow competition | `codex/multi-model-shadow-competition` |
| Broker read-only integration | `codex/broker-readonly-integration` |
| ETF expected gaps | `codex/etf-expected-gap-classification` |
| Provider gap cleanup | `codex/provider-gap-cleanup-*` |

## Agent Ownership By Lane

Architecture Agent:

- Owns package-boundary design, workflow/API placement, script-wrapper compatibility, and docs that govern implementation structure.
- Reviews any change that moves behavior between ingestion, analysis, presentation, workflows, scripts, storage, or local app shells.

Ingestion Agent:

- Owns provider refresh behavior, evidence capture, source-health state, provider gaps, provider access limitations, and ingestion planning.
- Must keep provider failures visible and must avoid changing official scores, targets, action labels, decision safety, or allocation.

Analytics Agent:

- Owns scoring, target sources, confidence, decision safety, verification queues, learning metrics, outcome evaluation, deterministic briefs, and AI synthesis readiness.
- Must protect numeric weights, thresholds, target-blending methodology, recommendation labels, and speculative-AI guardrails unless the user explicitly requests model tuning.

UX Agent:

- Owns dashboard review flow, generated report readability, feedback ergonomics, local decision console direction, summary consistency, accessibility, and phone-friendly review.
- Must keep the experience decision-first, audit-second, and explicitly recommendation-only.

QA Agent:

- Owns requirement-level regression coverage, fixture validation, quality gates, package-boundary checks, provider-gap visibility checks, and recommendation-only guardrails.
- Must distinguish local code correctness from external provider/network availability.

## Merge And Review Guidance

- Start every branch from current `main` unless the user asks for a stacked branch.
- Keep branches scoped to one lane and one roadmap item when possible.
- Do not mix refactors with behavior changes.
- Do not modify application code, tests, or configs for documentation-only work.
- Read `AGENTS.md`, `README.md`, `REQUIREMENTS.md`, `docs/PRODUCT_STRATEGY.md`, `docs/ROADMAP_STATUS.md`, `docs/DECISION_MODES.md`, `docs/MODEL_LEARNING_STRATEGY.md`, `docs/LOCAL_APP_STRATEGY.md`, `docs/UX_EXPERIENCE.md`, `pyproject.toml`, `scripts/check_quality.py`, `tests/test_package_boundaries.py`, and `config/portfolio_targets.json` before changing behavior.
- For ingestion work, avoid live network-heavy refreshes unless the user requested live data or provider validation.
- For model work, add regression tests before changing action, score, target, confidence, decision safety, allocation, or queue behavior.
- For presentation work, validate both report-context fixture rendering and user-facing output when feasible.
- Before handoff, run `python3 scripts/check_quality.py` unless a blocker prevents it.
- PR descriptions should state the lane, the product contract being protected, the validation command, and any behavior intentionally left unchanged.
- Draft PRs are preferred unless the user explicitly asks for ready-for-review.
