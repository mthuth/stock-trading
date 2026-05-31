# Requirements Roadmap

This roadmap translates the current product requirements into scoped development lanes for future Codex agents. It is a planning document only. It does not change scoring, target blending, recommendation labels, workflow behavior, dashboard behavior, provider ingestion, or configuration.

The stock-trading app remains recommendation-only decision support for a human investor. Future work must not place trades, preview orders, imply guaranteed performance, or hide source-health uncertainty.

## Roadmap Principles

1. Preserve recommendation-only behavior.
   Every feature must keep the user as the final decision-maker. Reports, scores, labels, targets, and dashboards are review aids, not execution instructions.

2. Keep data quality visible.
   Provider failures, stale inputs, blocked endpoints, and missing fields should surface as provider gaps or source-health context instead of being silently ignored.

3. Protect model contracts.
   Scoring weights, target-blending weights, confidence rules, speculative-AI caps, and recommendation labels are product contracts. Change them only when the task is explicitly model tuning and has regression coverage.

4. Separate decision surfaces from audit surfaces.
   The primary dashboard should help the user decide what to review next. Detailed score, target, source, and evidence explanations should remain available without crowding the first scan.

5. Keep package boundaries clean.
   Ingestion, analysis, presentation, workflows, storage, and scripts each have separate responsibilities. Shared behavior should move into package APIs before scripts grow new logic.

6. Prefer regression safety before new intelligence.
   Before adding AI synthesis or scoring impact from new signals, establish fixtures, report-context checks, source-quality history, and user-feedback loops.

## Current Architecture Contract

| Area | Owns | Must Not Own |
| --- | --- | --- |
| Ingestion | Provider refresh, evidence capture, source health, provider gaps, provider-neutral orchestration | Report rendering, scoring internals, dashboard behavior |
| Analysis | Scoring, targets, confidence, decision safety, verification queues, report context assembly | Provider/network calls, CLI modules, presentation rendering, scripts |
| Presentation | Dashboard, Markdown, email text, CSV exports, context validation rendering | Provider clients, storage internals, analysis engine internals, script modules |
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
| Architecture hygiene | Architecture Agent | Package boundaries, workflow APIs, script-wrapper compatibility | `codex/arch-*` |
| Documentation | Architecture Agent or relevant lane owner | Requirements, runbooks, acceptance criteria, handoff notes | `codex/docs-*` |

Agents may work concurrently only when branches stay within one lane and do not alter shared product contracts outside their scope.

## Wave 1: Stabilize And Protect

Goal: make the current recommendation engine safer to change by strengthening fixture coverage, report-context checks, package-boundary confidence, and provider-gap visibility.

### 1. Report Context Regression Fixture Coverage

Owner: QA Agent

Suggested branch: `codex/qa-report-context-fixtures`

Acceptance criteria:

- Add or update fixtures that cover at least one Add, Hold, Watch, and Avoid recommendation using the controlled label set.
- Validate that target confidence, data status, provider gaps, source-health summaries, and recommendation-only wording render through the fixture path.
- Run `python3 scripts/check_quality.py`.
- Do not change scoring weights, thresholds, target-blending weights, or recommendation labels.

### 2. Package Boundary Regression Expansion

Owner: Architecture Agent

Suggested branch: `codex/arch-boundary-regressions`

Acceptance criteria:

- Extend package-boundary tests only where they protect documented architecture ownership.
- Confirm scripts remain compatibility wrappers and do not become owners of business logic.
- Run `python3 scripts/check_quality.py`.
- Do not move behavior across packages unless the task is explicitly architecture cleanup.

### 3. Provider Gap Visibility Regression

Owner: QA Agent with Ingestion Agent review

Suggested branch: `codex/qa-provider-gap-visibility`

Acceptance criteria:

- Add regression coverage proving provider gaps remain visible in generated report context or rendered outputs.
- Cover stale, missing, blocked, and provider-error states where fixtures allow it.
- Confirm gap reporting remains explanatory and does not alter scores or actions unless existing requirements already specify that behavior.
- Run `python3 scripts/check_quality.py`.

### 4. Recommendation-Only Language Guardrail

Owner: QA Agent with UX Agent review

Suggested branch: `codex/qa-recommendation-only-copy`

Acceptance criteria:

- Add tests or fixture assertions that rendered outputs preserve recommendation-only wording.
- Confirm no output implies an order was placed, previewed, guaranteed, or automated.
- Run `python3 scripts/check_quality.py`.
- Do not add broker-write or order-preview behavior.

## Wave 2: Improve Decision Review

Goal: make the dashboard and generated summaries faster to review while preserving confidence, source-health, and recommendation-only context.

### 1. Target Confidence In CSV And End-Of-Day Markdown

Owner: UX Agent

Suggested branch: `codex/ux-target-confidence-exports`

Acceptance criteria:

- CSV and end-of-day Markdown include target confidence where recommendations are summarized.
- Existing dashboard target-confidence behavior is preserved.
- Fixture rendering demonstrates the new fields in generated artifacts.
- Run `python3 scripts/check_quality.py`.
- Do not change target-confidence rules or target-blending methodology.

### 2. Decision Summary Consistency Across Reports

Owner: UX Agent

Suggested branch: `codex/ux-decision-summary-consistency`

Acceptance criteria:

- Daily Markdown, dashboard, email summary, end-of-day Markdown, and next-day watchlist use consistent wording for action, score, target, upside, confidence, and data status.
- Recommendation-only wording remains visible in user-facing summaries.
- Generated fixture artifacts are inspected for layout and wording regressions.
- Run `python3 scripts/check_quality.py`.

### 3. Feedback Review Loop Polish

Owner: UX Agent

Suggested branch: `codex/ux-feedback-review-loop`

Acceptance criteria:

- Feedback capture remains low-friction in the dashboard and still works when served locally.
- Static HTML fallback behavior is preserved.
- Recent feedback remains auditable and does not distract from the Action Queue.
- Run `python3 scripts/check_quality.py`.
- Do not change feedback storage schema without an explicit storage task.

### 4. Phone-Friendly Report Review

Owner: UX Agent

Suggested branch: `codex/ux-phone-review`

Acceptance criteria:

- Decision-critical fields remain readable on narrow screens or exported phone views.
- Tabs, tables, and feedback controls do not overlap.
- The Action Queue remains the first practical review surface.
- Run `python3 scripts/check_quality.py`.

## Wave 3: Improve Data Quality

Goal: improve trust in the upstream evidence layer without letting provider availability silently distort recommendations.

### 1. Source Health Root-Cause Classification

Owner: Ingestion Agent

Suggested branch: `codex/ingestion-source-health-causes`

Acceptance criteria:

- Provider gaps classify common root causes such as network/DNS, credential, provider-plan block, stale data, missing field, and provider error.
- Classifications surface in report context and presentation without requiring raw provider payload review.
- Existing provider-gap records remain backward compatible.
- Run `python3 scripts/check_quality.py`.
- Do not change recommendation actions, scores, targets, or confidence rules.

### 2. Evidence Freshness And Coverage Checks

Owner: Ingestion Agent with QA Agent review

Suggested branch: `codex/ingestion-evidence-freshness`

Acceptance criteria:

- Evidence freshness and source coverage are recorded in a provider-neutral way.
- Missing or stale evidence becomes visible as source-health or provider-gap context.
- Analysis can consume freshness context only through documented package APIs.
- Run `python3 scripts/check_quality.py`.

### 3. Provider Access Decision Log

Owner: Ingestion Agent

Suggested branch: `codex/ingestion-provider-access-log`

Acceptance criteria:

- Provider access limitations, plan blocks, and credential-dependent endpoints are documented or surfaced in generated source-health context.
- The user can distinguish unavailable provider access from a code failure.
- No live network-heavy ingestion is required for normal regression tests.
- Run `python3 scripts/check_quality.py`.

### 4. Source Feedback Weighting Readiness

Owner: Ingestion Agent with Analytics Agent review

Suggested branch: `codex/ingestion-source-feedback-readiness`

Acceptance criteria:

- Source feedback is stored and summarized in a way that can later inform source weighting.
- Any quality labels remain explanatory unless requirements explicitly approve score or synthesis impact.
- Audit history is preserved.
- Run `python3 scripts/check_quality.py`.

## Wave 4: Improve Model Transparency

Goal: make the current model easier to inspect and challenge without changing its official recommendations.

### 1. Score Driver Explanation Improvements

Owner: Analytics Agent

Suggested branch: `codex/analysis-score-driver-transparency`

Acceptance criteria:

- Recommendation drilldowns show raw and weighted score drivers in plain language.
- Risk penalties and confidence caveats are visible near the action rationale.
- Fixture coverage confirms score explanations render without altering official scores.
- Run `python3 scripts/check_quality.py`.
- Do not change numeric weights, cutoffs, penalties, or action thresholds.

### 2. Target-Source Drilldown Completion

Owner: Analytics Agent with UX Agent review

Suggested branch: `codex/analysis-target-source-drilldowns`

Acceptance criteria:

- Analyst, fundamental, technical, manual, and provider-derived target inputs remain separated before blending.
- Drilldowns show source type, as-of date, confidence, freshness, and missing-input warnings.
- Single-source targets are clearly labeled as lower confidence where applicable.
- Run `python3 scripts/check_quality.py`.
- Do not change blend weights or stale-target rules.

### 3. Decision Safety Review Queue

Owner: Analytics Agent

Suggested branch: `codex/analysis-decision-safety-queue`

Acceptance criteria:

- Recommendations with missing price, missing target, stale critical inputs, or material provider gaps are easy to find for review.
- The queue is explanatory and does not execute trades, preview orders, or override the human decision.
- Presentation receives the queue through report context or another package API.
- Run `python3 scripts/check_quality.py`.

### 4. Speculative AI Guardrail Transparency

Owner: Analytics Agent with UX Agent review

Suggested branch: `codex/analysis-speculative-ai-guardrails`

Acceptance criteria:

- Speculative AI watchlist-only constraints and confidence haircuts are visible in recommendation rationale.
- The dashboard explains why a speculative name remains Watch when underlying score components look attractive.
- Run `python3 scripts/check_quality.py`.
- Do not change speculative-AI caps, observation windows, or buy eligibility without an explicit model-tuning task.

## Wave 5: AI Synthesis

Goal: add useful explanatory synthesis after the deterministic data, regression, and transparency layers are safe enough to support it.

### 1. Synthesis Packet Quality Gate

Owner: Analytics Agent with QA Agent review

Suggested branch: `codex/ai-synthesis-packet-quality`

Acceptance criteria:

- Synthesis packets include source attribution, freshness, confidence, bull signals, bear/risk signals, catalysts, and what would change the view.
- Packets reject or flag missing source attribution instead of inventing support.
- Existing deterministic briefs keep rendering.
- Run `python3 scripts/check_quality.py`.

### 2. AI Summary Traceability

Owner: Analytics Agent with UX Agent review

Suggested branch: `codex/ai-summary-traceability`

Acceptance criteria:

- AI-generated or AI-assisted summaries clearly cite the deterministic context fields they summarize.
- Summaries distinguish facts, model-derived conclusions, and user-feedback-derived notes.
- Summaries preserve recommendation-only wording and do not imply guaranteed outcomes.
- Run `python3 scripts/check_quality.py`.

### 3. Source-Quality-Aware Synthesis

Owner: Analytics Agent with Ingestion Agent review

Suggested branch: `codex/ai-source-quality-synthesis`

Acceptance criteria:

- Synthesis can explain source quality and disagreement without changing official scores, actions, or targets.
- Low-quality, stale, or noisy evidence is labeled instead of omitted.
- Source-quality impact remains explanatory unless a future requirement explicitly approves model impact.
- Run `python3 scripts/check_quality.py`.

### 4. Human Feedback Review Before Model Impact

Owner: Analytics Agent with QA Agent review

Suggested branch: `codex/ai-feedback-review-before-impact`

Acceptance criteria:

- User feedback can be summarized for review without automatically changing scoring or target methodology.
- Any proposed score, source-weighting, or recommendation-impact change is documented as a future product decision.
- Regression tests prove feedback summaries do not alter official recommendation labels.
- Run `python3 scripts/check_quality.py`.

## Wave 6: Portfolio Feedback

Goal: close the loop between recommendations, actual portfolio context, and human feedback without letting feedback silently rewrite model behavior.

Owner: Analytics Agent with UX Agent and QA Agent review

Suggested branch: `codex/portfolio-feedback-loop`

Acceptance criteria:

- Reports summarize recommendation feedback, source feedback, and manual review outcomes without changing scoring or recommendation labels.
- Portfolio context distinguishes current holdings, desired allocation, capped buy capacity, watchlist-only names, and avoided names.
- Feedback remains auditable and reversible.
- Any future model-impact proposal from feedback is documented as a separate product decision.
- Run `python3 scripts/check_quality.py`.

## Wave 7: Scenario Planning

Goal: let the user review "what if" situations for allocation, prices, targets, and data availability while keeping official recommendations unchanged.

Owner: Analytics Agent with UX Agent review

Suggested branch: `codex/scenario-planning-review`

Acceptance criteria:

- Scenario outputs are clearly labeled as hypothetical review aids.
- Scenarios can model price moves, target changes, monthly contribution changes, allocation caps, and missing-data assumptions.
- Official score, action, target, confidence, and decision-safety outputs are not overwritten by scenario runs.
- Scenario artifacts are separated from daily recommendation artifacts.
- Run `python3 scripts/check_quality.py`.

## Wave 8: Alerts And Review Triggers

Goal: surface review-worthy changes without creating trade execution, order preview, or broker-write behavior.

Owner: UX Agent with Analytics Agent review

Suggested branch: `codex/alerts-review-triggers`

Acceptance criteria:

- Alerts are recommendation-only review prompts, not trade instructions.
- Triggers cover material score movement, target-confidence degradation, provider blockers, stale data, price movement, allocation cap changes, and newly available primary-source evidence.
- Alerts include the reason, source context, and suggested manual review action.
- Alerts can be rendered in reports or local review output without requiring network-heavy live refreshes in tests.
- Run `python3 scripts/check_quality.py`.

## Wave 9: Backtesting And Regression History

Goal: compare historical recommendations, scores, targets, source-health states, and outcomes to improve confidence in future model changes.

Owner: QA Agent with Analytics Agent review

Suggested branch: `codex/backtesting-regression-history`

Acceptance criteria:

- Backtesting uses stored historical data or fixtures and does not fetch live provider data by default.
- Results distinguish recommendation quality, data freshness, provider availability, and target-confidence quality.
- Backtest output is explanatory and does not auto-tune scoring weights or target methodology.
- Regression history can detect recommendation drift before model changes are merged.
- Run `python3 scripts/check_quality.py`.

## Wave 10: Multi-Model Review

Goal: compare alternative scoring, target, or synthesis models in shadow mode before any product decision changes the official model.

Owner: Analytics Agent with QA Agent and Architecture Agent review

Suggested branch: `codex/multi-model-shadow-review`

Acceptance criteria:

- Alternative models run in shadow mode and are labeled as non-authoritative.
- The official recommendation label, score, target, and decision-safety output remain unchanged unless a separate model-tuning PR explicitly approves the change.
- Reports show differences between official and shadow outputs with enough context to review why they disagree.
- Tests prove shadow outputs do not change official daily recommendations.
- Run `python3 scripts/check_quality.py`.

## Wave 11: Local App Experience

Goal: improve the local review experience beyond static reports while keeping all behavior local, auditable, and recommendation-only.

Owner: UX Agent with Architecture Agent review

Suggested branch: `codex/local-app-review-experience`

Acceptance criteria:

- The local app preserves the existing dashboard/report review flow and recommendation-only wording.
- Feedback save, recent feedback, source-health review, target drilldown, data reliability, and decision-safety views remain visible.
- Static artifact rendering still works for phone/offline review.
- Local app changes do not introduce provider API behavior, broker writes, order previews, or storage schema changes unless separately approved.
- Run `python3 scripts/check_quality.py`.

## Wave 12: Broker Read-Only Integration

Goal: improve confidence in holdings and allocation context using broker read-only data without adding trading, order preview, or broker-write behavior.

Owner: Ingestion Agent with Architecture Agent and QA Agent review

Suggested branch: `codex/broker-readonly-integration`

Acceptance criteria:

- Broker integration is read-only and cannot place, preview, modify, or cancel orders.
- Holdings, cash, market value, cost basis, and allocation context are clearly labeled by source and timestamp.
- Missing or stale broker snapshots surface as reliability/provider gaps instead of silently falling back.
- The 10% single-stock cap and recommendation-only language remain visible in reports.
- Tests use fixtures/mocks and do not require live broker access.
- Run `python3 scripts/check_quality.py`.

## Suggested Branch Names

Use short-lived branches with the `codex/` prefix and keep each branch to one change area.

| Work Type | Suggested Branch |
| --- | --- |
| Requirements roadmap | `codex/add-requirements-roadmap` |
| Regression fixture coverage | `codex/qa-report-context-fixtures` |
| Boundary test expansion | `codex/arch-boundary-regressions` |
| Provider-gap visibility | `codex/qa-provider-gap-visibility` |
| Target confidence exports | `codex/ux-target-confidence-exports` |
| Decision summary consistency | `codex/ux-decision-summary-consistency` |
| Source-health classifications | `codex/ingestion-source-health-causes` |
| Evidence freshness | `codex/ingestion-evidence-freshness` |
| Score transparency | `codex/analysis-score-driver-transparency` |
| Target-source drilldowns | `codex/analysis-target-source-drilldowns` |
| AI synthesis packet quality | `codex/ai-synthesis-packet-quality` |
| AI summary traceability | `codex/ai-summary-traceability` |
| Portfolio feedback loop | `codex/portfolio-feedback-loop` |
| Scenario planning review | `codex/scenario-planning-review` |
| Alerts and review triggers | `codex/alerts-review-triggers` |
| Backtesting regression history | `codex/backtesting-regression-history` |
| Multi-model shadow review | `codex/multi-model-shadow-review` |
| Local app review experience | `codex/local-app-review-experience` |
| Broker read-only integration | `codex/broker-readonly-integration` |

## Agent Ownership By Lane

Architecture Agent:

- Owns package-boundary design, workflow/API placement, script-wrapper compatibility, and docs that govern implementation structure.
- Reviews any change that moves behavior between ingestion, analysis, presentation, workflows, scripts, or storage.

Ingestion Agent:

- Owns provider refresh behavior, evidence capture, source-health state, provider gaps, provider access limitations, and ingestion planning.
- Must keep provider failures visible and must avoid changing official scores, targets, or action labels.

Analytics Agent:

- Owns scoring, target sources, confidence, decision safety, verification queues, report-context assembly, deterministic briefs, and AI synthesis readiness.
- Must protect numeric weights, thresholds, target-blending methodology, recommendation labels, and speculative-AI guardrails unless the user explicitly requests model tuning.

UX Agent:

- Owns dashboard review flow, generated report readability, feedback ergonomics, summary consistency, accessibility, and phone-friendly review.
- Must keep the experience decision-first, audit-second, and explicitly recommendation-only.

QA Agent:

- Owns requirement-level regression coverage, fixture validation, quality gates, package-boundary checks, provider-gap visibility checks, and recommendation-only guardrails.
- Must distinguish local code correctness from external provider/network availability.

## Merge And Review Guidance

- Start every branch from current `main` unless the user asks for a stacked branch.
- Keep branches scoped to one lane and one roadmap item when possible.
- Do not mix refactors with behavior changes.
- Do not modify application code, tests, or configs for documentation-only work.
- Read `REQUIREMENTS.md`, `docs/UX_EXPERIENCE.md`, `pyproject.toml`, `scripts/check_quality.py`, `tests/test_package_boundaries.py`, and `config/portfolio_targets.json` before changing behavior.
- For ingestion work, avoid live network-heavy refreshes unless the user requested live data or provider validation.
- For model work, add regression tests before changing action, score, target, confidence, or queue behavior.
- For presentation work, validate both report-context fixture rendering and user-facing output when feasible.
- Before handoff, run `python3 scripts/check_quality.py` unless a blocker prevents it.
- PR descriptions should state the lane, the product contract being protected, the validation command, and any behavior intentionally left unchanged.
- Draft PRs are preferred unless the user explicitly asks for ready-for-review.
