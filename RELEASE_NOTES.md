# Release Notes

## V2.4 In Progress - AI Synthesis Prep + Evidence Review Queue

- Added `scripts/serve_dashboard.py` plus a local `POST /feedback` endpoint so dashboard feedback can save directly to SQLite when served locally, while preserving command fallback for static HTML review.
- Added `evidence_review_queue` and `synthesis_readiness` SQLite tables to gate event clusters before future AI synthesis.
- Added `scripts/prepare_synthesis_packets.py --rebuild` to classify event clusters as `ready_for_synthesis`, `needs_corroboration`, `needs_review`, or `ignore_for_now`.
- Added deterministic readiness scoring by symbol using ready events, review load, corroboration needs, primary-source events, and independent-confirmed events.
- Added deterministic synthesis packet export at `reports/synthesis-packets-YYYY-MM-DD.json`; packets are explicitly `llm_generated=false`.
- Wired synthesis preparation into `scripts/run_daily.py` through `--prepare-synthesis` and the existing ingestion bundles.
- Added Data Ingestion dashboard and markdown report sections for Evidence Review Queue and Synthesis Readiness By Symbol.
- V2.4 smoke run created 516 evidence review rows and 25 symbol readiness packets from the current event clusters; recommendation scores/actions remain unchanged.

## V2.3 In Progress - Event Clustering + Corroboration

- Added `evidence_event_clusters` and `evidence_event_members` SQLite tables so related evidence can be grouped into auditable source-backed events.
- Added `scripts/cluster_evidence_events.py --rebuild` to cluster evidence by symbol, event type, date bucket, topic terms, source families, and deterministic evidence tags.
- Added event classifications including earnings/guidance, filing disclosure, product launch, AI platform update, infrastructure capacity, security risk, analyst target, market sentiment, and general context.
- Added corroboration labels: `single_source`, `company_only`, `independent_confirmed`, `multi_source_confirmed`, `multi_source_unconfirmed`, and `primary_plus_confirmed`.
- Added source-family counts for primary, company-framed, independent, and opinion/context sources so repeated headlines do not look like independent corroboration.
- Wired evidence clustering into `scripts/run_daily.py` through `--cluster-evidence` and the existing ingestion bundles.
- Added Data Ingestion dashboard and markdown report sections for Evidence Events with corroboration, source count, evidence count, source mix, confidence, and summary.
- V2.3 smoke run generated 516 evidence event clusters from current stored evidence; recommendation scores/actions remain unchanged.

## V2.2 In Progress - Evidence Freshness + Backfill Control

- Added `ingestion_run_plan` and `ingestion_backfill_queue` SQLite tables to make source freshness, cooldown, run priority, and backfill needs auditable.
- Added `scripts/plan_ingestion_runs.py --rebuild` to compute source cadence, latest attempt, latest success, next run, cooldown window, run command, and reason from current provider payloads, raw payloads, evidence rows, and source-quality labels.
- Added deterministic cadence defaults by source category: daily for company blogs/newsrooms, press wires, and active tech/news feeds; slower cadence for podcasts/newsletters/context sources; monthly for paid/not-implemented candidates.
- Added blocked/error cooldown handling so repeatedly blocked sources are visible but do not waste every daily run.
- Added backfill queue generation for sources with no records or insufficient historical window coverage, including desired window, covered range, command, and next action.
- Added `--plan-ingestion` to the daily workflow and wired it into `--ingest-evidence`, `--ingest-free-data`, and `--ingest-public-sources` after source-quality scoring.
- Added Data Ingestion dashboard and markdown report sections for Next Ingestion Runs and Backfill Queue.
- V2.2 smoke run created 68 source refresh-plan rows and 62 backfill items; recommendation scores/actions remain unchanged.

## V2.1 In Progress - Source Depth Extraction

- Added `scripts/curate_source_depth.py` to turn stored SEC companyfacts, SEC submissions, official IR links, and official company-source evidence into normalized source-depth rows.
- Added curated evidence types for `sec_fundamental_depth_signal`, `sec_filing_depth_signal`, `official_ir_depth_signal`, and `official_source_depth_signal`.
- Source-depth curation stays shadow/explanatory only: no recommendation score, action, blended target, or trading behavior changes.
- Added `--curate-source-depth` to the daily workflow and wired it into `--ingest-evidence`, `--ingest-free-data`, and `--ingest-public-sources` before source-quality scoring.
- Excluded the local source-depth curator from source-quality provider scoring so derived rows do not inflate real source reliability metrics.
- Added a Data Ingestion dashboard section and markdown report section for Source Depth Signals with symbol, depth type, signal, detail, confidence, corroboration, timestamp, and source URL.
- V2.1 smoke run curated 426 source-depth rows from current stored evidence and regenerated the 2026-05-29 dashboard/report; recommendation scores/actions remain unchanged.

## V2.0 In Progress - Source Relevance Tuning

- Added source-health alert filters on the Health & Trends tab so detailed provider alerts can be scanned by all alerts, blockers, review items, or info rows without losing auditability.
- Added a compact Action Queue decision scan to the dashboard, with rank, action, score, change marker, key metrics, and rationale visible while the full audit table stays collapsed below.
- Added `config/symbol_aliases.csv` so deterministic evidence tagging uses configurable company, product, person, fund, ticker, and official-source direct-symbol rules instead of only hardcoded aliases.
- Added source-aware tagging rules: official single-company sources can default to their mapped symbol, press wires require headline-level stock-specific matches, and broad AI/cloud/chip terms do not create stock-specific evidence tags by themselves.
- Added persisted evidence-tag confidence buckets and match reasons (`high`, `medium`, `low`, `needs_review`; `ticker`, `direct_symbol`, `company_alias`, `product_alias`, `person_alias`, `fund_alias`, `sector_context`).
- Updated source-quality scoring to use stock-specific high/medium matches for tag-rate quality while keeping low-confidence/context matches visible for review.
- Added Source Quality columns for match reasons, confidence buckets, and low-confidence counts; added a Low Confidence Matches review table to dashboard/markdown context.
- Added product mappings for AWS/Bedrock/Trainium, Azure/Copilot, Google Cloud/Gemini/TPU, CUDA/Blackwell/DGX, HBM, EUV, Falcon, Prisma/Cortex, Snowflake Cortex AI/Data Cloud, and the previous alias set.
- V2.0 smoke run rebuilt evidence tags from 57 to 100 deterministic tags and scored 75 sources: 21 `high_signal`, 7 `useful_context`, 3 `needs_review`, 8 `blocked`, and 36 `not_enough_data`; recommendation scores/actions remain unchanged.

## V1.9 In Progress - Ingestion Quality + Source Relevance

- Added dashboard Print Review mode with compact print/PDF output for Pre-Market Readiness, Action Queue, Data Gaps, and Next-Day Watchlist.
- Added `source_quality_metrics` SQLite storage so each source has auditable quality/relevance rollups by run date.
- Added `scripts/score_source_quality.py --rebuild` to measure records seen, inserted records, duplicates, raw payloads, success/error/blocked runs, tag rate, average match confidence, matched-symbol count, top matched terms, and quality labels.
- Added deterministic quality labels: `high_signal`, `useful_context`, `needs_review`, `blocked`, `stale`, and `not_enough_data`.
- Counted both deterministic `evidence_symbol_tags` and direct symbol-specific evidence as source relevance, so official company/newsroom rows are measured correctly.
- Wired source-quality scoring into `scripts/run_daily.py` after evidence tagging for `--ingest-evidence`, `--ingest-free-data`, `--ingest-public-sources`, and standalone `--score-source-quality`.
- Added dashboard Data Ingestion sections for Source Quality and Low Relevance / Noisy Sources.
- Added Research Sources columns for quality label, tag rate, average confidence, and top matched terms.
- Added Source Quality and Low Relevance / Noisy Sources sections to the markdown report and report context for future AI synthesis.
- Smoke run on 2026-05-29 scored 75 sources: 19 `high_signal`, 8 `useful_context`, 5 `needs_review`, 7 `blocked`, and 36 `not_enough_data`; recommendation scoring remained unchanged.

## V1.8 In Progress - Verification Queue + Persisted Decision Insights

- Added `--mode` and `--categories` to public-source ingestion so RSS-only, page-link-only, and automatic RSS-to-page-link fallback runs can target source groups.
- Added generic public page-link extraction for official/free source pages, storing raw page payloads and curated `*_public_page_link` evidence rows.
- Added source status labels (`rss_ok`, `page_links_ok`, `missing_feed`, `blocked`, `parser_gap`) to public-source payload metadata and CLI output.
- Activated record-producing ingestion for company blogs/newsrooms, AI/semiconductor publications, and tech-news sources including NVIDIA, Google Cloud, Azure, Meta, AMD, ASML, IEEE Global Semiconductors, HPCwire, ServeTheHome, The Register AI, TechCrunch AI, and InfoQ.
- Left blocked or non-parseable public sources visible as gaps, including VentureBeat AI, Business Wire, GlobeNewswire, TSMC, Arm, Broadcom, and Micron from the V1.8 smoke run.
- Added persisted `decision_insights` and `verification_queue_items` SQLite tables so every generated brief and next check is auditable by report run.
- Added `scripts/run_verification_queue.py` for semi-automatic verification pulls; safe free/local scripts can run with `--execute`, while manual targets and provider-access fixes stay queued.
- Added `--verify-insights` to the daily workflow so the latest open queue can run before report generation without becoming default behavior.
- Added dashboard and markdown Verification Queue, Decision Insight History, and AI Analysis Context Ready sections.
- Added `reports/ai-analysis-context-YYYY-MM-DD.json` as a deterministic, no-LLM context package for future AI summaries.

## V1.7 In Progress - Decision-Grade Insights From Existing Data

- Added Next-day setup readiness and a Top next-day watch preview to the dashboard pre-market review flow.
- Expanded V1.7 source coverage with Tier 1 official company sources, Tier 2 press-wire candidates, Tier 3 AI/semiconductor publications, and Tier 4 newsletter/podcast context sources.
- Broadened public-source ingestion beyond podcasts/newsletters to support `company_blog`, `company_newsroom`, `press_wire`, `tech_news`, `ai_research`, and `semiconductor_news` categories.
- Added `--ingest-public-sources` as a daily-run alias for free public RSS/archive/page-link ingestion while keeping `--ingest-public-feeds` backward compatible.
- Added source-tier, ingestion-method, symbol-match, content-policy, confidence, and corroboration metadata to source integration tracking.
- Updated Data Ingestion and Research Sources dashboard views to show source tier/category metadata and new source records.
- Verified a five-source live smoke run: AWS News Blog, Cloudflare Blog, Semiconductor Engineering, and The Next Platform inserted public evidence; Google Cloud Blog remained a visible feed-discovery gap.
- Added deterministic Decision Insight briefs for each ranked stock with headline, insight type, supporting data, uncertainty, next check, and what would change the view.
- Added dashboard Decision Brief cards above the Action Queue plus per-symbol Decision Insight blocks in expanded action rows.
- Added Health & Trends Insight Themes to group recurring patterns such as missing analyst breadth, primary-source verification, trend-led candidates, and source blockers.
- Added markdown Top Decision Briefs, Insight Themes, and What To Verify Next sections to the daily, end-of-day, and next-day watchlist reports.
- Kept the V1.6 numeric score formula intact; V1.7 adds deterministic language and verification queues on top of the active signal overlay.

## V1.6 In Progress - Free Data Ingestion + Insight Scoring

- Added changed-since-last-run badges to dashboard recommendation tables so action, score, target, and new-row movement are visible before drilldown.
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
