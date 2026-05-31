# AGENTS.md

Working rules for Codex and other agents in `mthuth/stock-trading`.

## Project Purpose

This repo is a local stock research, ingestion, analysis, and presentation engine for a retirement-account technology-stock universe. It produces recommendation-only research artifacts that help the user decide what to review, buy manually, hold, watch, trim, or avoid.

The product must not place trades, preview trade orders, or imply guaranteed performance. Treat every dashboard, report, score, and label as decision support for a human investor.

## Branching Rules

- Use short-lived branches with the `codex/` prefix unless the user asks for a different name.
- Keep each branch scoped to one change area: ingestion, analytics/scoring, UX/reporting, QA/tests, docs, or infrastructure.
- Do not mix refactors with behavior changes.
- Do not modify application code when the user asks for docs-only work.
- Before editing, check `git status -sb` and preserve unrelated local changes.
- Do not push, open PRs, merge, or publish artifacts unless the user explicitly asks.

## Files To Read First

Start with these files before changing behavior:

- `REQUIREMENTS.md`: product contract, recommendation labels, scoring model, target methodology, and recommendation-only constraints.
- `docs/PRODUCT_STRATEGY.md`: product north star, portfolio strategy, risk posture, AI role, broker policy, and local app direction.
- `docs/ROADMAP_STATUS.md`: completed waves, active integration needs, deferred decisions, and next recommended work.
- `docs/WAVE7_HANDOFF.md`: Wave 7 long-term capital deployment handoff, sequencing, and guardrails.
- `docs/DECISION_MODES.md`: decision modes, horizons, sleeves, and mode-specific guardrails.
- `docs/MODEL_LEARNING_STRATEGY.md`: prediction records, outcome evaluation, model trust, source usefulness, and model-promotion rules.
- `docs/LOCAL_APP_STRATEGY.md`: local decision console stages, event/signal architecture, and broker-read-only boundaries.
- `docs/REQUIREMENTS_ROADMAP.md`: current roadmap, waves, ownership lanes, and merge/review guidance.
- `docs/UX_EXPERIENCE.md`: dashboard journey, UX priorities, confidence display, feedback flow, and recommendation-only wording.
- `pyproject.toml`: project metadata and canonical command hints.
- `scripts/check_quality.py`: local quality gate used by this repo.
- `tests/test_package_boundaries.py`: package-boundary contract.
- `config/portfolio_targets.json`: allocation caps, target-blending config, speculative-AI rules, and model tuning knobs.

Before starting new feature work, check `docs/ROADMAP_STATUS.md` for completed waves, active integration needs, and deferred product decisions. Before starting Wave 7 work, also read `docs/WAVE7_HANDOFF.md`.

When touching a specific area, also read:

- Ingestion: `stock_trading/ingestion.py`, `stock_trading/provider_client.py`, `stock_trading/storage/provider_repository.py`, and the relevant `scripts/ingest_*.py`.
- Analytics/scoring: `stock_trading/analysis_engine.py`, `stock_trading/analysis_scoring.py`, `stock_trading/analysis_targets.py`, and target/scoring tests.
- Presentation/UX: `stock_trading/presentation.py`, `stock_trading/reporting/renderers.py`, `docs/UX_EXPERIENCE.md`, and presentation/reporting tests.
- Workflows/CLI: `stock_trading/workflows/`, `stock_trading/cli/`, and the matching `scripts/*` wrapper.

## Quality Checks

Default full local gate:

```bash
python3 scripts/check_quality.py
```

That gate runs the unittest suite and Python compilation checks. For faster targeted checks, use:

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_package_boundaries
python3 -m unittest tests.test_run_daily
```

Use targeted tests while iterating, then run `python3 scripts/check_quality.py` before handing off changes when feasible. Do not run network-heavy ingestion or refresh commands unless the user asked for live data, a daily refresh, or provider validation.

## Package-Boundary Rules

Respect the three-track boundary enforced by `tests/test_package_boundaries.py`:

- Ingestion owns provider-neutral refresh orchestration and provider status normalization. It must not render reports or import analysis scoring/reporting internals.
- Analysis owns scoring, targets, confidence/risk logic, decision insights, verification queues, and report context assembly. It must not call provider/network clients, CLI modules, presentation modules, or `scripts`.
- Presentation owns dashboard, markdown, email, CSV, and context validation rendering. It must not import provider clients, storage internals, analysis engine internals, or script modules.
- CLI/workflow modules coordinate package APIs and may be wrapped by scripts for compatibility.
- Storage modules own database schema/repositories and should stay free of presentation behavior.

Prefer adding package APIs under `stock_trading/` and keeping `scripts/` as thin entrypoints.

## Do-Not-Change Rules

These areas are product contracts. Do not alter them casually, silently, or as part of cleanup.

- Scoring: Do not change numeric scoring weights, thresholds, penalties, score overlays, speculative-AI caps, or action cutoffs unless the user explicitly asks for scoring/model tuning.
- Target blending: Do not change analyst/fundamental/technical blend weights, confidence rules, stale-target handling, single-source labeling, or target-source separation unless the user explicitly asks for target methodology changes.
- Recommendation labels: Preserve the controlled label set from `REQUIREMENTS.md`: `Strong Buy`, `Buy`, `Add`, `Hold`, `Watch`, `Trim`, `Avoid`. Do not invent new action labels or rename existing labels without an explicit product decision.
- Recommendation-only status: Do not add trade execution, order preview, broker-write behavior, or language that implies automated trading.
- Explanatory-only signals: Keep source-depth, event clustering, and synthesis-readiness signals explanatory unless requirements explicitly say they can affect actions, scores, targets, or trading behavior.
- Compatibility wrappers: Preserve `scripts/*` compatibility wrappers unless the user explicitly tells you to remove or replace them. Existing tests and user workflows may patch or call these script-level symbols directly.

## Guidance For Specialized Agents

### Architecture Agent

- Keep boundaries aligned with `tests/test_package_boundaries.py`.
- Move shared behavior into `stock_trading/` package modules before expanding script logic.
- Avoid broad reshuffles unless a failing boundary or user-requested design change requires them.
- Preserve script wrapper compatibility and public import surfaces.

### Ingestion Agent

- Treat providers as unreliable and evidence-producing, not authoritative.
- Record blocked, stale, missing, and rate-limited provider states as provider gaps instead of hiding them.
- Keep ingestion read-only with respect to trading activity.
- Avoid live network refreshes unless requested; prefer fixtures and repository tests for normal development.

### Analytics Agent

- Protect scoring, target blending, confidence, and recommendation labels as product contracts.
- Keep analyst, fundamental, technical, manual, and provider-derived target inputs separate before blending.
- Store tuning knobs in config where the model requires adjustability.
- Add regression tests before changing action, score, target, confidence, or queue behavior.

### UX Agent

- Keep the dashboard decision-first and audit-second.
- Show score, action, target confidence, data status, source-health context, and feedback affordances together where decisions are made.
- Preserve recommendation-only wording and make provider gaps visible rather than burying them in raw output.
- Use `docs/UX_EXPERIENCE.md` as the source for dashboard flow and prioritization.

### QA Agent

- Start with requirement-level risk: scoring labels, target confidence, package boundaries, provider-gap visibility, and recommendation-only behavior.
- Prefer focused tests for changed contracts, then run `python3 scripts/check_quality.py`.
- For live-refresh or provider work, distinguish code correctness from provider/network availability.
- Do not mark external data refreshes as verified unless the command actually ran and the generated artifacts were inspected.
