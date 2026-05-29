# Release Notes

## V1.6 In Progress - Free Data Ingestion + Insight Scoring

- Added transparent insight scoring overlay using evidence freshness, price trend, target/source confidence, and ranked data-gap penalties.
- Changed active report scoring to persist and display evidence/trend/target/gap/final-score signal rows from `score_signals`.
- Added dashboard and markdown Insight Drivers, Score Movement, Trend Insights, and Ranked Data Gap Queue sections.
- Added Source Issue Groups to the Health & Trends dashboard tab so noisy source-health alerts are summarized by root cause before detailed audit rows.
- Added raw ingestion ledger storage through `raw_ingestion_payloads`, with inline storage for small payloads and file references for large payloads.
- Added `score_signals` storage for shadow-mode score-impact candidates that do not change official scores or actions.
- Added `scripts/curate_score_signals.py` to convert stored free data into auditable fundamentals/filings, IR, news, confidence, and technical shadow signals.
- Added `--ingest-free-data`, `--curate-score-signals`, and `--score-shadow` to the daily runner.
- Added dashboard Data Ingestion view with raw payload counts, curated record counts, latest issues, and next actions.
- Added expanded-row Score Signals sections so each stock can show shadow deltas, raw values, confidence, sources, freshness, and notes.
- Added paid-provider watchlist content for FMP, Alpha Vantage, Finnhub, Benzinga, and Unusual Whales while keeping implementation free-first.
- Added a The Batch public archive parser fallback when RSS/Atom discovery does not return parseable feed items.

## V1.5 In Progress

- Added compact Pre-Market Readiness checklist cards above the Action Queue for price data, target trust, source health, holdings context, and feedback review.
- Added `docs/UX_EXPERIENCE.md` to define the dashboard's decision-first review journey, information architecture, key states, accessibility expectations, and near-term UX backlog.
- Updated dashboard recommendation tables and summary metrics so target confidence and data status are visible before opening row details.
- Added persisted `recommendation_scores` rows so each report generation captures action, score, price, target, confidence, data status, score breakdown, and rationale for trend tracking.
- Added dashboard Health & Trends tab with source-health alerts, score-change review, and per-symbol score sparkline trends.
- Added Next-Day Watchlist subtab under Recommendations.
- Added generated `end-of-day-YYYY-MM-DD.md` and `next-day-watchlist-YYYY-MM-DD.md` artifacts.
- Added `scripts/run_scheduled_refresh.py` as a scheduler-friendly wrapper for pre-market and after-close runs.
- Added first-pass official company investor-relations ingestion for V1 operating-company symbols.
- Added configured official IR URLs in `config/official_ir_sources.csv`.
- Official IR ingestion stores provider payload status plus curated `Company investor relations` evidence rows for page snapshots and discovered release/deck/transcript links.
- Wired official IR ingestion into `scripts/run_daily.py --ingest-evidence` and added `--ingest-ir` for standalone refreshes.
- Updated dashboard source status mapping so Company investor relations now appears as implemented with records and gaps.
- Updated research brief handling so official IR snapshots are primary-source context, not bullish signals by default.
- Fixed FMP earnings transcript ingestion to use the current transcript-date discovery endpoint before requesting full transcripts.
- Redacted provider error messages before storage when an upstream provider echoes an API key in rate-limit text.
- Added approved podcast/newsletter source tracking for Hard Fork, AI Daily Brief, SemiAnalysis, The Information AI, The Batch, Import AI, TLDR AI, and Platformer.
- Added candidate paid-source tracking for Benzinga news, Benzinga analyst ratings, Benzinga unusual options, and Unusual Whales options flow.
- Added `config/research_source_integrations.csv` so dashboard source drilldowns can show access model, planned use, next step, and user action needed.
- Added public RSS/archive ingestion for approved podcast/newsletter sources through `scripts/ingest_public_research_feeds.py`.
- Wired public feed ingestion into `scripts/run_daily.py --ingest-evidence` and standalone `--ingest-public-feeds`.
- Added Beehiiv archive parsing for AI Daily Brief so public posts can be pulled from `aidailybrief.beehiiv.com`.
- Added `evidence_symbol_tags` SQLite storage and `scripts/tag_research_evidence.py` so broad podcast/newsletter evidence can be deterministically attached to V1 symbols without duplicating raw evidence rows.
- Wired source-to-symbol tagging into `scripts/run_daily.py --ingest-evidence` and standalone `--tag-evidence`.
- Updated dashboard research briefs, target/evidence drilldowns, and source record detail rows to show tagged evidence and the matched term used by the deterministic tagger.
- Added `config/manual_analyst_targets.csv` as a one-row-per-target fallback for supplemental analyst targets without overwriting FMP data.
- Added `scripts/ingest_benzinga_analyst_targets.py` as the second analyst-target provider path; it normalizes Benzinga ratings into the supplemental analyst target CSV when `BENZINGA_API_KEY` is available.
- Updated dashboard source drilldowns to show analyst-target breadth separately from all target rows.

## V1.4 - Research Depth Briefs

Status: built

### Added

- Added `scripts/ingest_research_depth.py` for explanatory research evidence ingestion.
- Added Alpha Vantage `NEWS_SENTIMENT` evidence capture with ticker-relevance filtering.
- Added FMP stable endpoint checks for stock news and earnings call transcripts; blocked access is recorded as provider gaps instead of failing the run.
- Added V1.4 research-depth config for evidence limits, freshness, and deterministic brief sections.
- Added deterministic dashboard Research Brief sections for expanded recommendation rows:
  - bull signals
  - bear/risk signals
  - recent catalysts
  - filings/transcripts/news
  - source confidence and freshness
  - what would change the view
- Connected research-depth ingestion to `scripts/run_daily.py --ingest-evidence`.
- Improved provider-gap cleanup so older failed fields are hidden when a later provider run has resolved the same symbol/field.

### Notes

- V1.4 research briefs are explanatory only. They do not change score, action, blended target, or trade recommendations.
- Alpha Vantage news sentiment was verified with a one-symbol smoke test.
- FMP stable stock-news and transcript endpoints returned paid-plan restrictions under the current key and are tracked as provider gaps.
- FMP transcript access now checks `earning-call-transcript-dates` before trying `earning-call-transcript`, so the engine no longer guesses recent quarters blindly.
- Existing Finnhub and SEC evidence remains part of the brief and source drilldown context.

### How To Run

Run V1.4 research-depth ingestion for a small test:

```bash
python3 scripts/ingest_research_depth.py --symbols NVDA
```

Run the daily workflow with evidence ingestion:

```bash
python3 scripts/run_daily.py --ingest-evidence --show-gaps
```

## V1.3 - Technical Target Model

Status: built

### Added

- Added `price_history` storage in SQLite for daily historical bars.
- Added `scripts/ingest_price_history.py` to pull daily price history for the V1 universe.
- Added a first-pass internal technical target model using:
  - 20-day, 50-day, and 200-day moving averages
  - recent support and resistance
  - entry zone
  - stop/review level
  - 20-day volatility
- Added `technical` rows into `target_sources`.
- Updated the blended target model to combine analyst, fundamental, and technical targets.
- Added latest historical close as a fallback current price when quote refresh data is missing.
- Added sleeve-specific blended-target weights:
  - long-term: 45% analyst, 45% fundamental, 10% technical
  - short-term: 20% analyst, 20% fundamental, 60% technical
- Added `--ingest-price-history` to `scripts/run_daily.py`.
- Regenerated the Markdown report, CSV report, email summary, and HTML dashboard with the V1.3 target blend.

### Validation

- Yahoo chart data returned 251 daily bars for every V1 symbol tested in the full universe run.
- Latest generated target-source mix:
  - 7 analyst targets
  - 25 fundamental targets
  - 25 technical targets
- Dashboard expanded recommendation rows now show the internal technical target, entry zone, support/resistance, and stop/review notes alongside fundamental and analyst target sources.
- Python compile checks passed for the updated report and price-history scripts.
- SQLite migration completed with the new `price_history` table.

### Provider Notes

- Yahoo chart data is the current no-key historical-price fallback for technical targets.
- Alpha Vantage daily adjusted historical prices were blocked as a premium endpoint for the configured key.
- Stooq historical price access required API/captcha access during testing.
- Provider-gap reporting still needs cleanup so old blocked-provider attempts do not make successful Yahoo history ingestion look noisy.

### How To Run

Run a daily report with historical price ingestion:

```bash
python3 scripts/run_daily.py --ingest-price-history --show-gaps
```

Run a full evidence and price-history refresh:

```bash
python3 scripts/run_daily.py --ingest-evidence --ingest-price-history --show-gaps
```

## V1.2 - Fundamental Target Model

Status: built

### Added

- Added configurable V1 fundamental target defaults in `config/portfolio_targets.json`.
- Added internal fundamental target rows into `target_sources`.
- Added model assumption notes to dashboard target-source drilldowns.
- Added target ranges for fundamental model outputs.
- Added confidence labels for model-derived targets.
- Added blended target configuration for analyst plus fundamental targets.
- Added blended target persistence in SQLite.
- Updated recommendation scoring to use blended upside when available.
- Updated the main dashboard table, Markdown report, CSV export, and email summary to show blended targets instead of raw FMP-only targets.

### Notes

- The first-pass model uses SEC companyfacts when available, plus configured quality, catalyst, risk, margin, and peer-group assumptions.
- The model is intentionally conservative and transparent. It does not yet replace the scoring target or create high-confidence buy recommendations by itself.
- The blended model starts with 55% analyst target and 45% fundamental target when both are available, and reweights to a single-source low-confidence target when only one target source exists.
- Symbols without current prices do not receive model target rows.

## V1.1 - Research Evidence and Dashboard Drilldowns

Release date: 2026-05-27

### Summary

V1.1 expands the stock recommendation engine from a flat scoring/report workflow into a source-attributed research system. The engine now stores target inputs, provider payloads, SEC evidence, Finnhub evidence, and broker snapshots in SQLite, then uses that stored context to explain recommendations in the HTML dashboard.

This release keeps the system recommendation-only. It does not place trades.

### Major Changes

- Added SQLite as the system of record for research and target-source data.
- Added target-source storage so analyst targets are tracked as individual inputs instead of being treated as a single unquestioned answer.
- Added Finnhub ingestion for available free-key endpoints:
  - quote
  - company profile
  - company news
  - recommendation trends
  - earnings calendar
- Added SEC EDGAR ingestion:
  - ticker-to-CIK mapping
  - recent filings
  - companyfacts financial evidence
- Added provider payload storage for auditability and future source drilldowns.
- Added source-attributed evidence storage for recommendation explanations.
- Added dashboard source drilldowns:
  - expanded recommendation rows show Target Sources and Recent Evidence
  - Data Gaps tab includes Source Drilldowns
- Added daily-runner flags for evidence refresh:
  - `--ingest-evidence`
  - `--ingest-finnhub`
  - `--ingest-sec`
- Updated production E*TRADE sync behavior to use the IRA rollover account by default when available.
- Updated requirements to mark V1.1 implementation items complete and move remaining work into open decisions.

### Dashboard Changes

The dashboard now separates key views into tabs and subtabs:

- Recommendations
  - Action Queue
  - Long-Term Queue
  - Short-Term Queue
  - Speculative AI Watchlist
  - Data Gaps
- Current Holdings
- Research Sources
- Feedback

Action Queue rows can be expanded to show:

- why the stock is an Add, Watch, Hold, or Avoid
- score breakdown
- research note
- target sources
- recent evidence

### Data Refresh Status

Latest V1.1 refresh completed on 2026-05-27:

- Finnhub evidence refresh completed successfully.
- SEC EDGAR evidence refresh completed successfully.
- Market price and target refresh completed successfully with provider gaps recorded.
- Production E*TRADE IRA rollover sync completed successfully after OAuth verifier entry.
- Dashboard, Markdown report, CSV report, and email summary were regenerated.

Latest E*TRADE snapshot after refresh:

| Symbol | Quantity | Last Price | Market Value | Gain/Loss | Portfolio Weight |
| --- | ---: | ---: | ---: | ---: | ---: |
| NVDA | 10 | $209.98 | $2,099.80 | -$37.00 | 4.18% |

### Known Provider Gaps

- FMP still blocks many price/target endpoints behind paid-plan responses.
- Alpha Vantage filled many current prices, but some speculative symbols remain missing or stale.
- Finnhub free key does not currently provide several desired endpoints:
  - price targets
  - EPS estimates
  - revenue estimates
  - upgrades/downgrades
  - news sentiment
  - transcripts
- SEC EDGAR CIK mapping is not expected for ETF symbols such as QQQM, VGT, and SMH.

### How To Run

Run a full research and market-data refresh:

```bash
python3 scripts/run_daily.py --ingest-evidence --show-gaps
```

Run only report generation from the latest stored data:

```bash
python3 scripts/run_daily.py --skip-refresh --show-gaps
```

Refresh production E*TRADE holdings:

```bash
python3 scripts/etrade_readonly.py --env production
```

The E*TRADE refresh requires manual OAuth verifier entry.

### Validation

V1.1 was validated with:

- Python compile checks for updated scripts.
- SQLite migration run.
- Finnhub endpoint verification.
- Finnhub ingestion run.
- SEC ingestion run.
- Market-data refresh run.
- Production E*TRADE read-only sync.
- Report/dashboard regeneration.
- Browser-level dashboard interaction check for expanded recommendation source drilldowns.

### Remaining Work

- Start using stored evidence to influence scoring, not just explain recommendations.
- Add fundamental target model output into `target_sources`.
- Add technical target model output into `target_sources`.
- Add Alpha Vantage news/sentiment ingestion.
- Add transcript ingestion where provider access allows it.
- Improve provider-gap cleanup so failed sandbox/network attempts do not clutter the dashboard.
- Add Google Sheets export to the selected Google Drive location.
- Add daily email delivery to `mthuth@gmail.com`.
- Add dashboard feedback save workflow instead of command-generation only.
- Add score history charts and richer short-term trade queue fields.
- Evaluate paid data access after several real provider-gap runs.
