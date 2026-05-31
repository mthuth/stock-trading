# Regression Strategy

## Purpose

This repo treats recommendation behavior as a product contract. Refactors are allowed to improve structure, boundaries, maintainability, and presentation, but they must not silently change what the engine recommends, why it recommends it, or how much trust the user should place in the output.

Regression proof should answer one question:

> Did the same inputs still produce the same recommendation actions, scores, targets, confidence labels, provider-gap visibility, and recommendation-only artifacts after the change?

The default local gate is:

```bash
python3 scripts/check_quality.py
```

Use targeted tests while iterating, then run the full gate before handing off behavior-affecting changes when feasible. Do not run network-heavy ingestion or live refresh commands as a normal regression check unless the task is specifically about live data, provider validation, or the daily refresh.

## Regression Layers

### 1. Unit Tests

Unit tests prove the deterministic parts of recommendation behavior in isolation.

Use them for:

- Score component calculations.
- Action cutoff behavior for `Strong Buy`, `Buy`, `Add`, `Hold`, `Watch`, `Trim`, and `Avoid`.
- Target-source counting, stale-target handling, target confidence, and blended-target fallback behavior.
- Provider-gap normalization for missing, stale, blocked, and rate-limited inputs.
- Recommendation-only safeguards, including absence of trade execution, order preview, or broker-write behavior.

Unit tests should use fixtures, mocks, and in-memory data. They should not depend on provider availability, current market data, local credentials, or files under `reports/`.

When refactoring scoring, target, confidence, or queue code, add or update focused tests before changing expected behavior. If a test starts failing because behavior changed intentionally, the reviewer should be able to point to the product decision or requirement that authorized the change.

### 2. Import And Package-Boundary Tests

Package-boundary tests protect recommendation behavior from hidden coupling. Refactors should preserve the three-track architecture:

- Ingestion gathers and normalizes provider evidence without rendering reports or importing scoring internals.
- Analysis owns scores, targets, confidence, decision insights, verification queues, and report-context assembly without calling provider/network clients, CLI modules, presentation modules, or scripts.
- Presentation renders dashboard, markdown, email, CSV, and context-validation artifacts from report-context data without importing providers, storage internals, or analysis-engine internals.

The focused boundary check is:

```bash
python3 -m unittest tests.test_package_boundaries
```

Boundary tests are recommendation regression tests because a boundary violation often means a refactor moved behavior into the wrong layer. That can make output depend on live providers, script side effects, or presentation formatting in ways that are hard to see from a rendered report.

### 3. Fixture-Based Report Rendering Tests

Fixture-based rendering tests prove that presentation changes do not mutate recommendation meaning.

The core fixture is:

```text
tests/fixtures/report_context.json
```

The fixture should represent a stable, JSON-native report context with recommendation-only metadata, a top recommendation, reliability status, recommendations, queues, source health, data gaps, feedback affordances, and artifact names. Rendering tests should assert that the dashboard, markdown report, CSV, email summary, end-of-day review, watchlist, and report-context JSON can be produced from that fixture without provider calls or scoring calls.

Use the fixture render command when reviewing output manually:

```bash
python3 scripts/render_report_context.py --fixture tests/fixtures/report_context.json --output-dir /private/tmp/stock-report-context-render
```

Rendering tests should verify:

- The recommendation-only label remains visible.
- The Action Queue remains visible and scannable.
- Score, action, target, target confidence, data status, and source-health context appear together where decisions are made.
- Provider gaps and source-health alerts remain visible.
- Renderers do not call providers, storage internals, or scoring functions.

Presentation-only wording and layout may change, but the rendered decision meaning must remain stable unless the change is intentionally reviewed as a recommendation-output change.

### 4. Golden Report-Context Snapshots

Report-context snapshots are the strongest local proof that recommendation behavior did not drift after a refactor.

A golden snapshot should capture the recommendation-facing contract before rendering:

- Metadata: report date, model version, run ids, and `recommendation_only`.
- Summary: top symbol, top action, and top score.
- Recommendations: rank, symbol, sleeve, trade type, action, score, price, target, upside, confidence, data status, rationale, and notes.
- Target details: target price/range, source count, source label, blend status, freshness, and confidence.
- Queues: Action Queue, long-term queue, short-term queue, next-day watchlist, speculative-AI watchlist, and data-gap queue.
- Reliability and source health: provider status buckets, top alerts, stale/missing/blocked/rate-limited status, and next actions.
- Feedback context: available feedback labels and recent review records when present.

Golden snapshots should be deterministic. Remove or normalize volatile fields before comparison, such as generated timestamps, transient run ids, absolute paths, and live provider messages that are not part of the recommendation contract.

Suggested comparison rule:

- Exact-match stable fields that define recommendation behavior.
- Allow normalized timestamp/run-id differences.
- Produce a readable diff grouped by symbol and by output section.
- Fail loudly when action, score, target, upside, target confidence, data status, queue rank, or provider-gap status changes.

Snapshots should live under a dedicated future path such as:

```text
tests/golden/report_context/
```

Until that harness exists, reviewers should inspect report-context JSON diffs manually for score/action/target changes.

### 5. Daily Workflow Plan Tests

Daily workflow plan tests prove the orchestration still runs the expected steps in the expected order without performing live provider work.

The focused check is:

```bash
python3 -m unittest tests.test_run_daily
```

These tests should mock command execution and assert:

- A plain daily run keeps report generation enabled.
- `--skip-refresh` avoids market refresh while still rendering the report.
- Evidence ingestion runs prerequisite refresh and curation steps before report generation.
- Free-data ingestion includes price history, SEC, official IR, public feeds, tagging, curation, clustering, synthesis, source-quality scoring, planning, and score-signal curation in the expected order.
- Optional provider/evidence failures continue to report with `ok_with_warnings` when core data exists.
- Core market-data failure stops the run when there is no usable price data.

Daily workflow tests are plan tests, not live-data tests. They should prove command ordering, failure policy, and report-generation behavior without depending on current provider availability.

## When Output Changes Are Allowed

Recommendation output changes are allowed only when they are intentional, reviewed, and traceable.

Allowed output changes include:

- A user-requested scoring, action-threshold, target-blending, confidence, or queue-priority change.
- A bug fix where the previous output contradicted requirements.
- A data-contract correction where the prior output was missing, stale, incorrectly labeled, or using the wrong source.
- A presentation-only change that preserves recommendation meaning but alters wording, order, or layout.
- A fixture update that reflects a deliberate change to the report-context schema.

Output changes are not allowed as incidental side effects of:

- Moving code between modules.
- Renaming helpers.
- Extracting package APIs from scripts.
- Formatting renderers.
- Adding dashboard controls.
- Changing ingestion wrappers.

If output changes during a refactor, stop and classify the change before accepting it. Either update the requirements/tests because the behavior change is intentional, or fix the refactor so the prior recommendation behavior is preserved.

## Reviewing Score, Action, And Target Changes

Any score/action/target diff should be reviewed as a recommendation-impacting change.

Review checklist:

- Confirm the symbol, sleeve, and trade type affected.
- Compare previous and new action labels against the controlled set in `REQUIREMENTS.md`.
- Compare total score and score component movement, including upside, quality, momentum, catalyst, risk, owned-position penalty, speculative-AI penalty, and model label.
- Check whether a cutoff was crossed, especially into or out of `Strong Buy`, `Buy`, `Add`, `Trim`, or `Avoid`.
- Compare target price, target low/high range, upside, source count, source labels, blend status, and target confidence.
- Confirm missing, stale, blocked, and rate-limited provider inputs are still visible as provider gaps.
- Confirm speculative-AI names remain watchlist-only unless the explicit config/product decision allows buy recommendations.
- Confirm ETFs are not treated as single-company target-price outputs.
- Confirm recommendation-only wording remains visible and no trade execution or order preview behavior was introduced.
- Record whether the diff is expected, unexpected but acceptable, or a regression.

For intentional behavior changes, include the reason in the PR or handoff notes and update the matching tests or snapshots in the same branch.

## Suggested Future Tests For Recommendation Drift

Add these tests incrementally as the recommendation surface stabilizes:

- Golden report-context snapshot test that compares stable recommendation fields from a fixture against committed expected JSON.
- Symbol-level drift report that prints action, score, target, confidence, rank, and provider-gap deltas for every symbol.
- Score-threshold regression fixtures for symbols just below and just above each action cutoff.
- Target-confidence matrix tests for single-source, two-source, stale-source, wide-range, missing-price, and missing-fundamentals cases.
- Speculative-AI guardrail tests proving configured watchlist-only symbols cannot become buy recommendations while `allow_buy_recommendations` is false.
- ETF regression tests proving ETF outputs use allocation/trend/risk context instead of single-company fair-value assumptions.
- Recommendation-only smoke tests that scan rendered dashboard, markdown, email, and watchlist artifacts for prohibited execution/order-preview language.
- Provider-gap visibility tests proving missing, stale, blocked, and rate-limited inputs remain visible in the dashboard and report context.
- Report-context schema compatibility tests that fail when required fields disappear from recommendations, queues, target details, source health, or feedback.
- Daily workflow scenario tests for `ok`, `ok_with_warnings`, and `failed` outcomes with mocked provider failures.

These future tests should stay fixture-based and deterministic unless the task explicitly asks for live provider validation.
