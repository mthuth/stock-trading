# Stock Trading Research Engine

Local batch research, ingestion, analysis, and presentation tooling for a focused retirement-account technology-stock universe.

The app produces recommendation-only research artifacts that help a human investor decide what to review, buy manually, hold, watch, trim, or avoid. It blends local configuration, provider data, price history, research evidence, portfolio rules, scoring logic, target methodology, and source-health signals into daily reports and a local dashboard.

## Current Non-Goals

- No automatic trading.
- No broker write actions.
- No order preview or order placement.
- No guarantees of performance, target achievement, or risk-free outcomes.
- No silent score, label, threshold, or target-methodology changes as part of cleanup work.

Every report, score, target, label, and dashboard affordance is decision support for a human investor.

## What The App Does

- Maintains an approved stock and ETF research universe in `config/research_inputs.csv`.
- Pulls or stores provider evidence, price history, public-source research, SEC data, investor-relations evidence, source-health status, and optional read-only brokerage snapshots.
- Scores recommendations using the controlled label set from `REQUIREMENTS.md`: `Strong Buy`, `Buy`, `Add`, `Hold`, `Watch`, `Trim`, and `Avoid`.
- Separates analyst, fundamental, technical, manual, and provider-derived target inputs before blending them.
- Generates daily Markdown, CSV, email-summary, dashboard, context JSON, insight-brief, end-of-day, and next-day-watchlist artifacts under `reports/`.
- Records provider gaps, stale data, blocked endpoints, missing inputs, feedback, workflow runs, recommendation runs, target sources, and blended targets in SQLite.

## Setup Assumptions

- Run commands from the repo root: `/Users/matthuth/Documents/Stock Trading`.
- Python 3.9 or newer is available as `python3`.
- The project is intentionally lightweight and primarily uses the Python standard library.
- SQLite database files live under `data/` and are created or migrated by the app as needed.
- Provider credentials are optional for many local/report-only workflows, but live refreshes need a local `.env`.
- Use `.env.example` as the template for local provider keys:
  - `FMP_API_KEY`
  - `ALPHA_VANTAGE_API_KEY`
  - `FINNHUB_API_KEY`
  - `BENZINGA_API_KEY`
  - `ETRADE_*` read-only/sandbox credentials when using E*TRADE snapshot tooling

Do not commit real credentials.

## Common Commands

Run the full local test suite:

```bash
python3 -m unittest discover -s tests
```

Run the repo quality gate:

```bash
python3 scripts/check_quality.py
```

Run the package-boundary contract:

```bash
python3 -m unittest tests.test_package_boundaries
```

Run daily workflow tests:

```bash
python3 -m unittest tests.test_run_daily
```

Render the checked-in report-context fixture:

```bash
python3 scripts/render_report_context.py --fixture tests/fixtures/report_context.json --output-dir /private/tmp/stock-report-context-render
```

Export review-only alert artifacts from a local fixture:

```bash
python3 scripts/export_alerts.py --fixture tests/fixtures/alerts/sample_alerts.json --output-dir reports/
```

Generate analysis without persisting or rendering context:

```bash
python3 scripts/run_analysis.py --no-persist --no-context
```

Serve a generated dashboard locally when reviewing feedback-save behavior:

```bash
python3 scripts/serve_dashboard.py
```

Build and render the static local decision console:

```bash
python3 scripts/build_local_console_manifest.py --output reports/local-console-manifest.json
python3 scripts/render_local_console.py --manifest reports/local-console-manifest.json --output reports/local-console.html
```

Open `reports/local-console.html` manually in a browser to review the console. The console is static and does not execute refreshes, run commands, broker actions, order previews, or trades.

## Quality Checks

The default local gate is:

```bash
python3 scripts/check_quality.py
```

It currently runs:

- `python3 -m unittest discover -s tests`
- Python compilation for `scripts/`, `stock_trading/`, `stock_trading/cli/`, `stock_trading/reporting/`, and `stock_trading/workflows/`

Use focused tests while iterating, then run the full quality gate before handing off changes when feasible.

## Run The Daily Report Safely

For a safe report-only run that avoids live provider refreshes and does not place or preview trades:

```bash
python3 scripts/run_daily.py --skip-refresh --show-gaps
```

For the usual daily research refresh bundle when live provider/network access is explicitly desired:

```bash
python3 scripts/run_daily.py --ingest-price-history --ingest-evidence --show-gaps
```

Useful narrower ingestion flags:

```bash
python3 scripts/run_daily.py --ingest-price-history --show-gaps
python3 scripts/run_daily.py --ingest-free-data --show-gaps
python3 scripts/run_daily.py --ingest-public-sources --show-gaps
python3 scripts/run_daily.py --ingest-sec --show-gaps
python3 scripts/run_daily.py --ingest-ir --show-gaps
python3 scripts/run_daily.py --ingest-finnhub --show-gaps
```

Provider failures, blocked endpoints, missing fields, and stale data should be recorded and surfaced as gaps rather than hidden. Treat `ok_with_warnings` as a reportable provider/source-health state, not as permission to infer that all external data refreshed cleanly.

## Config Locations

- `config/portfolio_targets.json`: account assumptions, allocation rules, model tuning knobs, target-blending weights, speculative-AI policy, report schedule, dashboard feature order, provider decisions, and feedback settings.
- `config/research_inputs.csv`: approved universe and core manual/provider-updated research inputs.
- `config/research_sources.csv`: research source catalog.
- `config/research_source_integrations.csv`: source implementation and access-model tracking.
- `config/official_ir_sources.csv`: official company investor-relations source list.
- `config/manual_analyst_targets.csv`: supplemental manual analyst targets.
- `config/symbol_aliases.csv`: evidence-tagging aliases for companies, products, people, funds, and tickers.
- `.env`: local provider credentials. Use `.env.example` as the template.

## Reports And Data

- `reports/daily-recommendation-YYYY-MM-DD.md`: daily Markdown recommendation report.
- `reports/daily-recommendation-YYYY-MM-DD.csv`: CSV recommendation export.
- `reports/dashboard-YYYY-MM-DD.html`: local dashboard.
- `reports/email-summary-YYYY-MM-DD.txt`: manual/draft email summary text.
- `reports/end-of-day-YYYY-MM-DD.md`: after-close review.
- `reports/next-day-watchlist-YYYY-MM-DD.md`: next-day prep list.
- `reports/report-context-YYYY-MM-DD.json`: report rendering context.
- `reports/ai-analysis-context-YYYY-MM-DD.json`: deterministic context package for future AI summaries.
- `reports/ai-insight-briefs-YYYY-MM-DD.*`: deterministic insight brief artifacts.
- `reports/synthesis-packets-YYYY-MM-DD.json`: evidence synthesis readiness packets.
- `reports/alerts.json` and `reports/alerts.md`: optional local review-trigger artifacts exported from fixture/local alert rows.
- `reports/local-console-manifest.json`: local decision console manifest with artifact index, panel summaries, and read-only run history.
- `reports/local-console.html`: static local decision console shell for manual review.
- `data/stock_trading.sqlite`: canonical SQLite database used by current storage paths.
- `data/raw_payloads/`: large raw provider payload storage when payloads are not kept inline.

Older or compatibility database files may exist in `data/`; confirm the active path in `stock_trading/storage/connection.py` before adding new storage behavior.

## Architecture And Product Docs

- [REQUIREMENTS.md](REQUIREMENTS.md): product contract, recommendation labels, scoring model, target methodology, and recommendation-only constraints.
- [docs/PRODUCT_STRATEGY.md](docs/PRODUCT_STRATEGY.md): product north star, portfolio strategy, risk posture, AI role, broker policy, and local app direction.
- [docs/ROADMAP_STATUS.md](docs/ROADMAP_STATUS.md): completed waves, current integration needs, next recommended work, and deferred decisions.
- [docs/WAVE7_HANDOFF.md](docs/WAVE7_HANDOFF.md): Wave 7 long-term capital deployment handoff and guardrails.
- [docs/WAVE7_REQUIREMENTS.md](docs/WAVE7_REQUIREMENTS.md): Wave 7 long-term capital deployment requirements and fixture scenarios.
- [docs/WAVE8_EARNINGS_REVIEW_REQUIREMENTS.md](docs/WAVE8_EARNINGS_REVIEW_REQUIREMENTS.md): Wave 8 earnings event review requirements and fixture scenarios.
- [docs/WAVE10_TACTICAL_REVIEW_REQUIREMENTS.md](docs/WAVE10_TACTICAL_REVIEW_REQUIREMENTS.md): Wave 10 tactical trade review requirements and fixture scenarios.
- [docs/WAVE11_MODEL_EVALUATION_REQUIREMENTS.md](docs/WAVE11_MODEL_EVALUATION_REQUIREMENTS.md): Wave 11 model evaluation, prediction record, benchmark comparison, and backtesting requirements.
- [docs/WAVE12_ALERTS_REVIEW_TRIGGERS_REQUIREMENTS.md](docs/WAVE12_ALERTS_REVIEW_TRIGGERS_REQUIREMENTS.md): Wave 12 alerts and review-trigger requirements and fixture scenarios.
- [docs/WAVE13_MULTI_MODEL_SHADOW_REQUIREMENTS.md](docs/WAVE13_MULTI_MODEL_SHADOW_REQUIREMENTS.md): Wave 13 multi-model shadow competition requirements and fixture scenarios.
- [docs/WAVE14_BROKER_READONLY_REQUIREMENTS.md](docs/WAVE14_BROKER_READONLY_REQUIREMENTS.md): Wave 14 broker read-only integration requirements and fixture scenarios.
- [docs/DECISION_MODES.md](docs/DECISION_MODES.md): decision modes, recommendation horizons, sleeves, and mode-specific guardrails.
- [docs/MODEL_LEARNING_STRATEGY.md](docs/MODEL_LEARNING_STRATEGY.md): prediction records, outcome evaluation, model trust, source usefulness, and shadow-model rules.
- [docs/LOCAL_APP_STRATEGY.md](docs/LOCAL_APP_STRATEGY.md): path from static reports to a local decision console.
- [docs/REQUIREMENTS_ROADMAP.md](docs/REQUIREMENTS_ROADMAP.md): roadmap waves, ownership lanes, and merge/review guidance.
- [docs/UX_EXPERIENCE.md](docs/UX_EXPERIENCE.md): dashboard journey, decision-first UX priorities, confidence display, feedback flow, and recommendation-only wording.
- [reports/data-ingestion-flow.md](reports/data-ingestion-flow.md): generated data-ingestion and report-generation flow diagram.
- [AGENTS.md](AGENTS.md): local working rules for Codex and other agents.
- [RELEASE_NOTES.md](RELEASE_NOTES.md): recent feature history and validation notes.
- [tests/test_package_boundaries.py](tests/test_package_boundaries.py): executable package-boundary architecture contract.

## Package Boundaries

The repo enforces a three-track boundary model:

- Ingestion owns provider-neutral refresh orchestration and provider status normalization.
- Analysis owns scoring, targets, confidence/risk logic, decision insights, verification queues, and report context assembly.
- Presentation owns dashboard, Markdown, email, CSV, and context validation rendering.

CLI and workflow modules coordinate package APIs. Scripts should remain thin compatibility entrypoints where possible.

Before changing behavior, read the relevant contract docs and targeted tests, check `git status -sb`, and preserve unrelated local changes.
