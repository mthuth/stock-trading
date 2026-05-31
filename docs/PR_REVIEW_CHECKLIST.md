# PR Review Checklist

Use this checklist for human and Codex-assisted reviews in `mthuth/stock-trading`.
The app is recommendation-only decision support for a human investor, so every PR
should be reviewed for accidental trading behavior, recommendation drift, target
confidence drift, provider-gap visibility, and package-boundary regressions.

Start every review by reading the PR description, changed files, and relevant
contract docs:

- `AGENTS.md`
- `README.md`
- `REQUIREMENTS.md`
- `docs/UX_EXPERIENCE.md`
- `docs/REQUIREMENTS_ROADMAP.md`, if present

For each PR, confirm the author ran the full quality gate unless the PR clearly
documents why it could not be run:

```bash
python3 scripts/check_quality.py
```

## Universal Checks

- [ ] The PR scope is clear and does not mix unrelated docs, refactor, behavior,
      ingestion, UX, scoring, or infrastructure changes.
- [ ] No automatic trading, broker-write behavior, order preview, or order
      placement behavior was added.
- [ ] Recommendation-only wording remains accurate and visible where users make
      decisions.
- [ ] The controlled recommendation labels remain unchanged:
      `Strong Buy`, `Buy`, `Add`, `Hold`, `Watch`, `Trim`, `Avoid`.
- [ ] No score, threshold, action cutoff, queue priority, or target-blending
      change is hidden inside cleanup or refactor work.
- [ ] Decision-safety behavior is intentional, documented, and covered by
      targeted validation when it changes.
- [ ] Provider gaps, stale inputs, blocked endpoints, missing targets, and
      source-health states remain visible instead of being swallowed or converted
      into success.
- [ ] Package boundaries still match `tests/test_package_boundaries.py`.
- [ ] `scripts/*` entrypoints remain compatibility wrappers where applicable;
      package behavior should live under `stock_trading/`.
- [ ] The reviewer can point to tests or artifact inspection that validate the
      changed surface.

## Docs-Only PRs

- [ ] The PR changes only documentation or PR metadata.
- [ ] The docs do not describe unsupported behavior as already implemented.
- [ ] The docs preserve the product contract: recommendation-only, no automatic
      trading, no broker writes, no order previews, and no guaranteed outcomes.
- [ ] Recommendation labels, scoring rules, target methodology, provider-gap
      behavior, and decision-safety rules match `REQUIREMENTS.md` and
      `AGENTS.md`.
- [ ] Any new review, runbook, or workflow guidance references the canonical
      quality gate: `python3 scripts/check_quality.py`.

## Refactor PRs

- [ ] The PR explains which structure changed and which user-visible behavior
      should remain identical.
- [ ] Reported actions, scores, blended targets, target confidence labels,
      provider-gap status, and recommendation-only wording are unchanged unless
      explicitly approved as behavior changes.
- [ ] Refactored code respects ingestion, analysis, presentation, storage, CLI,
      workflow, and script-wrapper boundaries.
- [ ] Script-level compatibility imports and callable symbols remain available
      when existing tests or user workflows depend on them.
- [ ] Focused regression tests or fixture/rendered-artifact inspection confirm
      that recommendation meaning did not drift.

## Behavior-Changing PRs

- [ ] The PR identifies the intentional behavior change and links it to a
      requirement, product decision, or explicit user request.
- [ ] Tests cover the changed behavior at the appropriate level: unit,
      package-boundary, workflow, fixture, rendered artifact, or end-to-end
      command.
- [ ] The change does not add automatic trading, broker writes, order previews,
      or language implying the app acts without human review.
- [ ] User-facing wording still makes the human investor the final
      decision-maker.
- [ ] Backward compatibility, data migration needs, and report/dashboard impact
      are called out when applicable.

## Ingestion/Provider PRs

- [ ] Provider calls remain read-only and do not create broker write or order
      preview behavior.
- [ ] Missing, stale, blocked, rate-limited, paid-plan-limited, and credential
      failures are recorded and surfaced as provider gaps.
- [ ] Provider outputs remain source-attributed and do not silently overwrite
      analyst, fundamental, technical, manual, or provider-derived target
      inputs.
- [ ] Live-provider validation is clearly distinguished from local code
      validation; network failure is not reported as data correctness.
- [ ] The PR does not make source-depth, event clustering, or synthesis-readiness
      signals affect actions, scores, targets, or trading behavior unless that
      behavior change is explicit and tested.

## UX/Reporting PRs

- [ ] The decision surface still shows action, score, current price, blended
      target, upside, trade type, rationale, target confidence, data status, and
      source-health context where decisions are made.
- [ ] Recommendation-only status remains visible in the dashboard/report flow.
- [ ] Provider gaps and source-health blockers remain visible in dashboard,
      report, CSV, email-summary, or watchlist outputs affected by the PR.
- [ ] Layout or wording changes do not alter recommendation meaning unless the
      PR is explicitly behavior-changing.
- [ ] Feedback controls remain auditable and do not imply automatic model tuning
      or trade execution.
- [ ] Rendered artifacts or fixture-based checks were inspected when the output
      format changed.

## Scoring/Target/Decision-Safety PRs

- [ ] Any score weight, threshold, risk penalty, action cutoff, ranking,
      confidence, or queue-priority change is intentional and documented.
- [ ] Any analyst/fundamental/technical/manual target-source weighting,
      freshness rule, fallback rule, source-count rule, stale-target rule, or
      target-confidence label change is intentional and documented.
- [ ] Single-source or stale targets do not become high-confidence outputs by
      accident.
- [ ] Speculative AI names remain watchlist-only unless config and requirements
      explicitly allow buy recommendations.
- [ ] ETFs are not treated as single-company target-price outputs.
- [ ] Decision-safety gates fail closed or downgrade confidence when required
      inputs are missing, stale, blocked, or contradictory.
- [ ] Tests or snapshot comparisons prove expected action, score, target,
      confidence, provider-gap, and recommendation-label behavior.
