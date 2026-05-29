# Stock Trading Research Engine Requirements

## Purpose

Build a daily stock research and recommendation engine for a retirement account with an emphasis on high-upside technology stocks. The engine should help identify attractive long-term holdings and shorter-term tactical opportunities, but it should not place trades automatically in the first version.

The engine's primary job is to answer:

> Given the approved tech universe, which stocks have the best risk-adjusted upside today, what is the blended target price, what evidence supports it, and should the position be bought, held, watched, trimmed, or avoided?

## Portfolio Strategy

The account starts with approximately $50,000.

Planned monthly buying amount is approximately $2,500.

Target portfolio structure:

| Sleeve | Allocation | Approximate Amount | Purpose |
| --- | ---: | ---: | --- |
| Long-term holdings | 75% | $37,500 | High-upside stocks intended for multi-month to multi-year holding periods |
| Short-term tactical trades | 25% | $12,500 | Day, week, or month opportunities based on catalysts, momentum, and market research |

The engine should distinguish clearly between long-term recommendations and short-term tactical recommendations.

Short-term tactical recommendations may include any of these trade types:

| Trade Type | Expected Holding Period | Primary Scoring Emphasis |
| --- | --- | --- |
| Day trade | Intraday | Price/volume momentum, liquidity, intraday catalyst, volatility control |
| Weekly swing | Several days to about one week | Trend continuation, breakout quality, relative strength, near-term catalyst |
| Tactical 2-4 week | About two to four weeks | Catalyst path, earnings/news setup, sector momentum, risk/reward to target |

The engine should score short-term ideas in the context of the trade type. A day-trade candidate should not be scored the same way as a 2-4 week tactical trade.

## Approved Starting Universe

Version 1 should focus on the following symbols.

| Category | Symbols |
| --- | --- |
| Mega-cap AI/platform | MSFT, NVDA, GOOGL, AMZN, META, AVGO |
| Semiconductors | AMD, ARM, MU, TSM, ASML, SMH |
| Cybersecurity/cloud/software | CRWD, PANW, NET, DDOG, SNOW, MDB |
| ETFs/ballast | QQQM, VGT, SMH |
| Speculative AI/small-mid cap | SOUN, AEHR, BBAI, ALAB, PLAB |

Notes:

- ETFs should be scored differently from individual stocks.
- ETFs may receive allocation, trend, and risk scores instead of traditional single-company target prices.
- Speculative AI/small-mid-cap stocks should be capped separately because of higher volatility and business-model risk.
- Speculative AI names should start as watchlist-only until provider data, source evidence, and score history are strong enough to allow buy recommendations.
- Initial speculative AI decision: SOUN, AEHR, BBAI, ALAB, and PLAB remain watchlist-only for 2-3 weeks before any buy recommendation is allowed.

## Recommendation Actions

The engine should use a controlled set of recommendation labels:

- Strong Buy
- Buy
- Add
- Hold
- Watch
- Trim
- Avoid

Recommendations should never imply guaranteed performance. Every recommendation must include supporting evidence and risks.

## Stock Scoring Model

Each individual stock should receive a daily score from 0 to 100.

Initial scoring components:

| Component | Suggested Weight | Description |
| --- | ---: | --- |
| Upside to blended target price | 25% | Measures estimated upside from current price to blended target |
| Revenue and earnings growth | 15% | Measures business acceleration and forward growth expectations |
| Margin and free cash flow quality | 10% | Rewards durable profitability and operating leverage |
| Valuation sanity | 10% | Penalizes excessive valuation relative to growth and peers |
| Momentum and relative strength | 15% | Measures whether the market is currently confirming the thesis |
| Catalyst score | 10% | Captures earnings, guidance, product launches, analyst revisions, sector momentum, and major news |
| Deep research thesis | 10% | Qualitative assessment of moat, AI/tech exposure, competitive position, and strategic upside |
| Risk penalty | -5% to -20% | Penalizes volatility, drawdown risk, earnings risk, balance-sheet risk, concentration, or thesis uncertainty |

The scoring model should be configurable so weights can be adjusted after backtesting and real-world review.

## Target Price Methodology

Each individual stock should receive multiple target prices.

The engine must not treat a single provider target, such as an FMP consensus target, as the full answer when making a buy/watch/avoid recommendation. A single provider value may be used as one input, but the dashboard should label it as such and show target confidence based on source breadth, freshness, and corroboration.

| Target Type | Description |
| --- | --- |
| Analyst target | Consensus target from one or more third-party analyst data providers |
| Fundamental target | Engine-estimated fair value based on growth, margins, valuation multiples, and peer comparison |
| Technical target | Near-term price objective based on trend, support/resistance, breakouts, volume, and relative strength |
| Deep-research target adjustment | Qualitative adjustment based on corroborated evidence, catalysts, risks, and thesis changes |
| Blended target | Final target used for scoring and recommendation output |

Target-source requirements:

- Store each target input separately with symbol, source name, source type, provider endpoint or evidence reference, target value, as-of date, freshness, and confidence.
- Show whether the displayed target is single-source, partially blended, or fully blended.
- Show target freshness and stale-target warnings.
- Record missing target inputs as provider gaps instead of silently reusing old values.
- Prefer target ranges when source disagreement is high instead of implying false precision.
- Require at least two independent target inputs before labeling a target as high-confidence.
- Allow manual/user target notes, but label them as manual and keep them separate from provider or model-derived targets.

The blended target should use different weights depending on the intended holding period.

If a target input is unavailable, the engine should re-normalize the available weights and lower target confidence. It should not block the report unless price data is missing or the recommendation would materially depend on a missing target.

### Long-Term Blended Target

V1.3 initial weighting:

| Input | Weight |
| --- | ---: |
| Analyst target | 45% |
| Fundamental target | 45% |
| Technical target | 10% |
| Deep-research adjustment | Later scoring input |

### Short-Term Blended Target

V1.3 initial weighting:

| Input | Weight |
| --- | ---: |
| Analyst target | 20% |
| Fundamental target | 20% |
| Technical target | 60% |
| Catalyst/news score | Already included in the short-term score, not the target blend |

### Target Confidence

Each blended target should receive a confidence label.

| Confidence | Requirement |
| --- | --- |
| High | At least two independent target sources, current price data, fundamentals or estimates, and no major unresolved provider gaps |
| Medium | One strong target source plus corroborating fundamentals, estimates, or technical context |
| Low | Single-source target, stale target, missing fundamentals, large source disagreement, or highly speculative name |
| Needs review | Missing target, missing price, stale inputs, or provider errors that materially affect the recommendation |

The dashboard should show target confidence next to upside so the user can distinguish "42.9% upside from one provider target" from "42.9% upside from a broader blended target."

### Fundamental Target Model

Version 1 should use a straightforward, adjustable fundamental target model. The goal is not a perfect valuation model; the goal is a transparent fair-value estimate that can improve as better provider data, peer groups, and user feedback become available.

V1 fundamental target approach:

1. Use forward revenue growth, EPS growth, gross/operating margin quality, free cash flow quality, and valuation multiple sanity.
2. Assign each stock to a configurable peer group based on category.
3. Start with default peer-group valuation multiples and growth adjustments.
4. Estimate a fair-value target using the best available provider fundamentals/estimates.
5. Apply a confidence haircut when fundamentals are stale, incomplete, or based on thin coverage.
6. Store the result as a `fundamental` target-source row with inputs, peer group, assumptions, confidence, and notes.

Initial peer groups and defaults:

| Peer Group | Starting Universe | Primary Multiple | Default Multiple | Growth Adjustment | Notes |
| --- | --- | --- | ---: | --- | --- |
| Mega-cap AI/platform | MSFT, NVDA, GOOGL, AMZN, META, AVGO | Forward P/E or EV/Revenue | 30x forward EPS or 8x forward revenue | Add 0.5x P/E for each 1% growth above peer median, capped | Use quality and margin scores to avoid over-rewarding hype |
| Semiconductors | AMD, ARM, MU, TSM, ASML, SMH | Forward P/E or EV/Revenue | 28x forward EPS or 7x forward revenue | Higher cyclicality haircut when margins/earnings are volatile | ETFs use basket/sector proxy instead of company EPS |
| Cloud/software/cybersecurity | CRWD, PANW, NET, DDOG, SNOW, MDB | EV/Revenue and FCF margin | 9x forward revenue | Reward durable growth plus improving FCF margin | Penalize weak margin path or decelerating growth |
| ETF ballast | QQQM, VGT, SMH | Sector/basket fair-value proxy | Current price plus model trend range | Conservative adjustment only | Do not pretend ETFs have single-company fair value |
| Speculative AI | SOUN, AEHR, BBAI, ALAB, PLAB | EV/Revenue or manual range | 4x forward revenue | Heavy confidence haircut until coverage/history improves | Watchlist-only until observation period and source confidence improve |

Default model tuning rules:

- Store all default multiples and peer group mappings in config, not code.
- Allow each multiple, cap, haircut, and peer group assignment to be changed without rewriting the model.
- Prefer ranges when the model has weak inputs.
- Never let the fundamental model alone create a high-confidence Add recommendation.
- Show the fundamental target and assumptions in the dashboard once target-source drilldowns exist.

### Technical Target Model

Version 1 should use a straightforward, adjustable technical target model based on price history, trend, support, and resistance. The goal is to provide a transparent technical target input, especially for short-term recommendations, without overfitting.

V1 technical target approach:

1. Use recent daily price history, initially 20-day, 50-day, and 200-day windows.
2. Calculate trend using 20-day and 50-day moving averages relative to the current price.
3. Estimate support using recent swing lows and moving-average support.
4. Estimate resistance using recent swing highs and breakout levels.
5. Produce a technical target range rather than a single precise number when signals are mixed.
6. Store the result as a `technical` target-source row with inputs, lookback windows, support/resistance levels, confidence, and notes.

Initial technical defaults:

| Setting | Default | Purpose |
| --- | ---: | --- |
| Short trend window | 20 trading days | Captures near-term momentum |
| Medium trend window | 50 trading days | Captures swing trend |
| Long trend window | 200 trading days | Captures major trend context |
| Support lookback | 60 trading days | Finds recent support zones |
| Resistance lookback | 60 trading days | Finds recent resistance/breakout zones |
| Breakout buffer | 3% | Avoids treating tiny moves as real breakouts |
| Stop/review buffer | 5% below support | Helps frame short-term invalidation levels |
| Max long-term technical target contribution | 10% of blended target | Keeps long-term recommendations from being dominated by charts |
| Max short-term technical target contribution | 45% of blended target | Allows technicals to matter more for short-term trades |

Technical model tuning rules:

- Store all windows, buffers, caps, and lookback periods in config, not code.
- Use simple moving averages and support/resistance first; defer advanced technical-analysis libraries until V1 output proves useful.
- Use lower confidence when price history is missing, stale, thinly traded, or extremely volatile.
- Technical targets should influence short-term trade type, entry zone, exit review trigger, and confidence.
- Technical targets should not create a high-confidence Add recommendation without analyst, fundamental, or deep-research support.

## Deep Research Requirements

For each stock, the engine should produce a research note that explains the score and target price.

Each research note should include:

- Bull thesis
- Bear thesis
- Key growth drivers
- AI/technology exposure
- Competitive position
- Recent news and catalysts
- Earnings and estimate revision trend
- Valuation concerns
- Major risks
- What would change the recommendation
- Suggested holding period
- Confidence level

The deep research layer should explain and challenge the numeric score. It should not replace the scoring model.

Deep research should use a blended evidence model. The engine should support analyst summaries, news and catalyst scanning, SEC filings, earnings releases, earnings call transcripts, sentiment, options-flow signals, podcasts, newsletters, and other curated expert sources when available.

Deep-research evidence capture can start before the scoring impact is finalized. Early ingestion should store evidence with attribution, timestamps, symbols, source type, and confidence, but should not automatically change buy/watch/avoid scores until the attribution and confidence model is stable.

Each research source should be tracked and rated so the engine can learn which sources are useful.

Source rating fields:

| Field | Description |
| --- | --- |
| Source name | Publisher, analyst, podcast, newsletter, data provider, or filing source |
| Source type | Analyst, news, SEC filing, earnings transcript, sentiment, options flow, podcast, newsletter, social, or manual note |
| Ticker coverage | Symbols or sectors the source is useful for |
| Reliability rating | 1-5 rating based on historical usefulness and accuracy |
| Timeliness rating | 1-5 rating based on how quickly the source surfaces relevant information |
| Signal rating | 1-5 rating based on how actionable the source tends to be |
| Default weight | Baseline source weighting before user feedback |
| Corroboration required | Whether the source should be treated as opinion until confirmed elsewhere |
| Bias/risk note | Known bias, promotional tone, hype risk, stale data risk, or conflicts |
| User feedback | User-provided approval, disagreement, or weighting adjustment |

Deep research output should show source attribution at the evidence level. A recommendation should explain which evidence came from which source category, and whether the source is highly trusted, experimental, or user-flagged.

Source-weighting algorithm:

1. Normalize reliability, timeliness, and signal ratings from 1-5 to 0-1.
2. Compute source quality as 45% reliability, 20% timeliness, and 35% signal rating.
3. Multiply source quality by default weight.
4. Apply a 15% haircut when corroboration is required and the evidence is not corroborated by another trusted source.
5. Apply user feedback adjustments from source feedback history.
6. Cap the final effective source weight between 0 and 1.

This source weight should influence deep-research confidence and catalyst scoring, not mechanically override price/target/fundamental data.

### Evidence Ingestion Plan

V1 evidence ingestion should prioritize durable, source-attributed inputs that can explain and challenge the numeric score.

| Priority | Source | Pull Method | Evidence Captured | Initial Use |
| ---: | --- | --- | --- | --- |
| 1 | SEC EDGAR submissions API | `data.sec.gov/submissions/CIK##########.json` with ticker-to-CIK lookup | Recent 10-K, 10-Q, 8-K, 20-F, 6-K filing metadata and filing URLs | Filing/event timeline, risk/catalyst prompts |
| 1 | SEC EDGAR companyfacts API | `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | Revenue, EPS/share facts, margins, cash flow, balance-sheet facts | Fundamental target inputs and primary-source validation |
| 2 | Company investor relations | Official company IR pages first, with configured URLs per symbol | Earnings releases, presentations, guidance, product/event releases | Corroborate filings and earnings-call claims |
| 2 | Earnings call transcripts | FMP transcript-date discovery first, then FMP full transcript fetch if current key supports it; Finnhub transcript endpoints if accessible | Management commentary, Q&A, guidance tone, demand/supply comments, risk language | Deep-research notes, catalyst confidence, qualitative thesis |
| 3 | Alpha Vantage news/sentiment | `NEWS_SENTIMENT` endpoint by ticker/topic | News headlines, URLs, publisher, sentiment labels/scores | News/catalyst queue and sentiment context |
| 3 | Finnhub company news/sentiment | Company news and sentiment endpoints if key supports them | Company-specific news, sentiment statistics, source URLs | News/catalyst queue and corroboration |
| 4 | FMP news | Stock/general news endpoints if current key supports them | Headlines, publisher, timestamps, URLs | News backup/fallback source |
| 5 | Approved podcasts | Public RSS/archive discovery first for Hard Fork and AI Daily Brief | AI platform/regulatory/thematic context and catalyst leads | Opinion/context only, corroboration required |
| 5 | Approved newsletters | Public RSS/archive discovery first for SemiAnalysis, The Information AI, The Batch, Import AI, TLDR AI, and Platformer | AI infrastructure, platform, research, and market-context notes | Opinion/reporting context only, corroboration required |
| 6 | Benzinga news/analyst/options APIs | Evaluate paid API access if free/low-cost feeds are too stale/noisy | Faster market-moving headlines, analyst ratings, and unusual options | Optional short-term catalyst and analyst-context upgrade |
| 6 | Unusual Whales options flow | Evaluate paid API token and endpoint fit for short-term sleeve | Options flow, dark-pool, volatility, and tactical market data | Short-term alert context only, strict noise controls |

Evidence storage requirements:

- Store evidence in SQLite as the system of record.
- Include symbol, evidence type, source name, source URL or provider endpoint, source timestamp, fetched timestamp, headline/title, summary, raw text reference, confidence, corroboration status, and user feedback.
- Keep raw provider payloads or payload references for auditability when practical.
- Deduplicate evidence by source URL, provider id, accession number, transcript id, or headline/time hash.
- Treat SEC filings and company-reported financial facts as high-reliability primary evidence.
- Treat news, podcasts, newsletters, social, and options-flow inputs as corroboration-required evidence.
- Do not let one uncorroborated news headline or transcript quote override the score.
- Surface evidence in the dashboard as source drilldowns before it materially changes scoring.

Near-term ingestion order:

1. Add CIK mapping and SEC submissions/companyfacts ingestion for V1 symbols.
2. Add transcript metadata and transcript fetch for FMP first, then Finnhub if available.
3. Add Alpha Vantage news/sentiment for V1 symbols.
4. Add Finnhub company news/sentiment if the configured key supports it.
5. Add source drilldowns on the dashboard.
6. Ingest approved podcasts/newsletters through public RSS/archive discovery first.
7. Evaluate Benzinga and Unusual Whales paid feeds only if current/free sources are insufficient or short-term options context becomes a priority.

The engine should allow user feedback on research quality. Feedback examples:

- Mark a source as useful or noisy.
- Increase or decrease a source's weighting.
- Flag a source as too promotional.
- Mark an analyst or newsletter as trusted for a sector.
- Record whether a catalyst actually mattered after the fact.

Feedback workflow decision:

- The target feedback experience is dashboard buttons plus a free-text box.
- Recommendation feedback buttons should include Agree, Disagree, and Too Risky.
- Source feedback buttons should include Useful Source and Noisy Source.
- Free-text feedback should allow detailed reasoning.
- While the dashboard is static HTML, feedback controls may generate a local command to run. A later local app/server can save feedback directly to SQLite from the dashboard.

Podcasts and newsletters may be added as research sources if they provide useful, repeatable coverage. The engine should not treat podcast or newsletter commentary as fact by default; it should classify it as opinion/commentary unless corroborated by primary filings, company releases, market data, or multiple trusted sources.

## Data Source Requirements

The engine should support multiple data providers because no single source will be complete or perfect.

Required source categories:

| Category | Purpose | Initial Requirement |
| --- | --- | --- |
| Price data | Current price, historical bars, relative strength, technical context | Use at least one primary provider plus stale-data detection |
| Analyst targets | Consensus targets, upgrades/downgrades, estimate revisions | Support multiple providers where available; track paid-provider gaps |
| Fundamentals | Revenue, EPS, margins, free cash flow, valuation multiples, balance sheet | Use provider data or filings-derived data for fundamental target modeling |
| SEC filings and company releases | Primary evidence for risks, growth drivers, capital allocation, and guidance | Treat as high-trust but slower-moving evidence |
| Earnings transcripts | Management commentary, guidance tone, demand signals, risk changes | Use for deep-research thesis and catalyst scoring |
| News and catalyst feeds | Product launches, analyst actions, regulatory events, sector moves | Require corroboration for high-impact claims |
| Sentiment and options flow | Short-term attention, volatility, unusual activity | Use only for short-term score context unless corroborated |
| Manual/user notes | User thesis, preferences, risk concerns, source feedback | Store separately and label clearly |

Candidate provider/tool options:

| Provider | Potential Use |
| --- | --- |
| Finnhub | Selected second analyst/estimate source for analyst targets, estimates, upgrades/downgrades, and company fundamentals |
| Financial Modeling Prep | Price target consensus, financial statements, ratios, estimates |
| Alpha Vantage | Market data, fundamentals, analyst estimates and revisions |
| Polygon | Price data, historical bars, market data, selected fundamentals |
| Nasdaq Data Link or similar datasets | Supplemental fundamentals, estimates, macro/sector datasets |
| SEC EDGAR APIs | Filings and company disclosures |
| Earnings transcript source | Earnings call transcripts and management commentary |
| News API/provider | Company and sector news/catalyst scanning |
| Options-flow provider | Unusual options activity and short-term positioning |
| E*TRADE API | Account holdings, balances, order preview, future trade execution |

Version 1 can operate without E*TRADE write access. Initial E*TRADE integration should be read-only if added.

Provider strategy:

- Do not upgrade market-data providers blindly.
- Use Financial Modeling Prep for symbols and endpoints supported by the current key.
- Add Alpha Vantage as a fallback and enrichment provider for fundamentals, earnings/revenue estimates, news, and sentiment.
- Use Finnhub as the selected second analyst/estimate provider after target-source storage exists, but gate each endpoint by verified account access.
- Finnhub inputs should be stored as separate target, estimate, recommendation-trend, and upgrade/downgrade source rows, not merged directly into the flat research CSV.
- Finnhub free-key verification on 2026-05-27 showed access to quote, company profile, company news, recommendation trends, and earnings calendar for NVDA.
- Finnhub free-key verification on 2026-05-27 returned blocked access for news sentiment, price target, EPS estimates, revenue estimates, upgrade/downgrade, and transcripts list.
- Until paid access is justified, use Finnhub for company news, recommendation trends, profile context, and earnings calendar; keep Finnhub analyst target/estimate/transcript fields as provider gaps.
- Add a target-source expansion layer before relying on upside for high-conviction recommendations.
- Separate provider ingestion from target blending so new sources can be added without rewriting the scoring model.
- Maintain a target-source table/history so each run can explain where every target and upside percentage came from.
- Add confidence penalties when upside is based on one provider, stale data, or uncorroborated evidence.
- Keep missing analyst target prices marked as "Needs paid target provider" or "Needs refresh" instead of blocking the full report.
- Track provider coverage gaps by symbol and endpoint.
- Later, decide whether paid analyst target coverage is worth upgrading, choosing between FMP, Finnhub, or another provider based on tested gaps rather than assumptions.
- Provider results should be source-attributed so the report can show whether a target, estimate, or catalyst came from FMP, Alpha Vantage, E*TRADE, analyst consensus, news, filings, or manual input.
- Paid analyst-target provider decision is deferred until the engine has collected at least 10 provider-gap runs or about 14 days of real usage, whichever provides enough evidence.

Near-term source-expansion priority:

1. Add target-source storage and dashboard attribution for current FMP/Alpha Vantage/manual inputs. Implemented in V1.1.
2. Add Finnhub as the second analyst-target and estimate-revision source, starting with any endpoints available under the current/free key. Implemented for verified free endpoints in V1.1; blocked endpoints remain provider gaps.
3. Add fundamentals-derived target modeling using revenue growth, EPS, margins, valuation multiples, and peer comparison. First-pass implemented in V1.2.
4. Add technical target context using historical prices, trend, support/resistance, and relative strength. First-pass implemented in V1.3.
5. Add SEC filing, earnings transcript, and news/catalyst evidence capture for deep-research notes.
6. Add sentiment/options-flow only after the core target and evidence model is stable.

## Daily Workflow

The engine should run twice per trading day unless API cost, provider limits, or data quality make that impractical.

Preferred workflow:

1. Pre-market, refresh available market data and generate a "what to buy today" recommendation report.
2. User reviews recommendations manually before any trade.
3. After market close, refresh prices, volume, fundamentals, news, and portfolio state.
4. After close, generate an end-of-day change report and next-day watchlist.
5. Future versions may support E*TRADE order preview after explicit user approval.

Cost note:

- With the V1 universe of about 20 symbols and two provider calls per symbol, each full refresh is roughly 40 API calls.
- Running both pre-market and after-close is roughly 80 API calls per trading day before adding news, fundamentals, sentiment, or fallback providers.
- The system should track provider failures and API limits so the schedule can be reduced if the selected provider becomes too costly.

## Daily Recommendation Report

The engine should generate a human-readable daily report.

Minimum report fields:

| Field | Description |
| --- | --- |
| Rank | Overall ranking within the relevant sleeve |
| Ticker | Stock or ETF symbol |
| Company/Fund | Name of company or ETF |
| Sleeve | Long-term, short-term, ETF/ballast, or speculative |
| Trade type | Long-term, day trade, weekly swing, 2-4 week tactical, ETF/ballast, or speculative |
| Action | Strong Buy, Buy, Add, Hold, Watch, Trim, or Avoid |
| Score | 0-100 score |
| Score breakdown | Component explanation showing how upside, quality, momentum, catalyst, risk, and penalties contributed |
| Current price | Latest available price |
| Blended target price | Final target price used by engine |
| Estimated upside/downside | Percentage difference between current price and blended target |
| Confidence | Low, Medium, or High |
| Suggested allocation | Dollar amount or percentage range |
| Reason summary | Short explanation of the recommendation |
| Action rationale | Plain-English reason why the action is Buy, Add, Watch, Hold, Trim, or Avoid |
| Key risks | Main reasons the recommendation could fail |

The report should include separate sections for:

- Top long-term opportunities
- Top short-term tactical opportunities
- Existing holdings to add, hold, trim, or avoid
- Watchlist names
- Major market/sector context
- Changes since the prior report
- Score explanations and action rationales so the user can understand why a stock is Add, Watch, Hold, Trim, or Avoid.

Report format roadmap:

- Version 1 should generate Markdown and a static HTML dashboard.
- Later versions should add email delivery and spreadsheet export.
- The HTML dashboard should be the primary local review surface before any trade decision.
- Email report decision: send a daily report to mthuth@gmail.com for now, preferably as a concise summary with a dashboard link. Actual sending should remain draft/manual-approval until the email workflow is explicitly enabled.
- Spreadsheet report decision: use a native Google Sheet stored in Google Drive as the primary spreadsheet artifact. Local CSV remains a fallback/staging export.
- Preferred Google Sheet tabs: Daily Recommendations, Holdings, Provider Gaps, Research Sources, and Feedback.
- Approved HTML dashboard roadmap: source drilldowns, holdings allocation chart, historical score trend, and short-term trade queue.
- Dashboard implementation order should start with holdings allocation chart, then short-term trade queue, then source drilldowns, then historical score trend.
- Dashboard layout should fit comfortably on a laptop monitor without making the full ranked universe the primary screen.
- The primary dashboard view should use focused tables for action queue, long-term core, short-term queue, speculative AI watchlist, data gaps, holdings, and sources.
- The full ranked universe should remain available as a secondary drilldown for auditing, filtering, and source/score detail.
- Research sources should live in a separate dashboard tab so source weighting can be reviewed without crowding the recommendation workflow.
- Research Sources should be an operational transparency page, not just a source catalog. For each source, show whether it is implemented, evidence/target/payload record counts, last run time, last run status, latest issue, and the next implementation action when it is not implemented.
- The source catalog should distinguish logical source categories from concrete provider endpoints. For example, "SEC EDGAR" may include submissions and companyfacts endpoints, while "Alpha Vantage news sentiment" is a concrete implemented endpoint.
- Implemented sources should refresh daily at least once. Preferred cadence is after market close plus optional pre-market refresh if provider limits allow.
- Alpha Vantage should use a quota-aware rotation. Track the last successful Alpha update per symbol, limit daily Alpha symbol pulls, and prioritize symbols that have never been updated or have the oldest successful Alpha refresh.
- Provider gaps, blocked endpoints, stale data, and rate-limit issues should be visible from the Research Sources tab.
- Unimplemented sources should have an action plan with candidate provider/API, expected value, cost/free-tier status, implementation complexity, and dependencies.
- Each source row should be clickable. The expanded source detail should show the records currently tracked for that source, including evidence rows, target rows, provider payload/status rows, account records, or feedback records as applicable.
- Source detail views do not need to force every source into the same permanent data model, but they should normalize display fields enough for review: updated time, record kind, symbol, record name, value/status, and notes.
- Current holdings should live in a separate dashboard tab with allocation details. The Action Queue should not duplicate holdings allocation unless needed for a specific position-cap warning.
- Feedback should live in a separate dashboard tab so review actions and text notes do not distract from the trading recommendation view.
- Action Queue should start with the queue itself, not a duplicated "why this is the top-ranked stock" summary above the table.
- Action Queue rows should show rank, symbol, action, score, current price, blended target, upside, trade type, and a concise rationale or synthesis.
- Hovering or focusing the action label should show a compact explanation containing action rationale, blended target, score breakdown, and key score drivers.
- Clicking a stock row should show deeper detail, including target sources, score explanations, research brief, and recent evidence.
- Score explanations should define each component in plain language and show raw input, weighting, weighted contribution, and penalties.
- Target-source detail should clearly separate technical model, fundamental model, analyst target, and future deep-research adjustment. Each source should show target price, target range where available, upside, confidence, and calculation or publication date.
- The current price should be shown beside target price so the user can immediately see the gap between today's price and the target.
- The "Why" concept should evolve into a synthesized thesis: a daily or data-refresh-generated AI synthesis that weighs target sources, filings, transcripts, news, analyst inputs, technicals, risks, and user feedback. The synthesis should be stored, timestamped, and auditable rather than generated ad hoc on every page load.
- The Recommendations tab should have secondary tabs for Action Queue, Long-Term Queue, Short-Term Queue, Speculative AI Watchlist, and Data Gaps.

Research source implementation action plan:

| Priority | Source | Status | Next Action |
| ---: | --- | --- | --- |
| 1 | Existing implemented providers | In progress | Add daily scheduled refresh, source health status, and alerting for provider gaps |
| 2 | SEC EDGAR companyfacts/submissions | Implemented | Improve mapping to score drivers and make filing evidence more readable |
| 3 | Alpha Vantage news sentiment | Implemented | Improve relevance filtering and sentiment attribution by ticker |
| 4 | Finnhub company news/recommendations/earnings evidence | Implemented/partial | Verify endpoint coverage and add clearer status per endpoint |
| 5 | FMP stock news/transcripts | Blocked by current plan | Keep gap visible; revisit paid tier only after enough runs prove value |
| 6 | Company investor relations | Implemented/first pass | Pull configured official company IR pages, store page snapshots and official release/deck/transcript links, then add detail extraction from those links |
| 7 | Earnings call transcripts | Partial/blocked | Evaluate free transcript sources or provider upgrade; store transcript excerpts separately from headlines |
| 8 | Analyst target consensus beyond FMP | Not implemented | Add second analyst-target provider if free/low-cost access is available |
| 9 | Market news feeds | Partial | Add one broader market news provider with stronger company relevance metadata |
| 10 | Approved podcasts/newsletters | Approved/tracked, not ingested | Add feed/email/transcript ingestion path and keep opinion sources corroboration-required |
| 11 | Benzinga news/analyst/options | Candidate paid source | Evaluate cost, trial access, endpoints, and overlap with FMP/Finnhub gaps |
| 12 | Unusual Whales options flow | Candidate paid source | Evaluate token cost, endpoint fit, and noise controls for short-term sleeve |
| 13 | Social sentiment | Not implemented | Treat as lower-trust context with strong manipulation/noise controls |

User setup/action items for expanding sources:

| Priority | User Action Needed | Why It Matters |
| ---: | --- | --- |
| 1 | Confirm whether to keep using free-provider-only mode or approve a paid market/news/transcript source later | Determines whether FMP/Finnhub/Benzinga-style blocked endpoints should remain gaps or become paid integrations |
| 2 | Review official-IR provider gaps after several runs and decide whether blocked company sites need alternate official URLs or manual links | Some official IR sites block automated fetches or require different release pages |
| 3 | Subscribe or confirm access path for SemiAnalysis, The Information, The Batch, Import AI, TLDR AI, and Platformer | Determines whether ingestion should use public archives, email/Gmail, RSS, or manual notes |
| 4 | Confirm exact AI Daily Brief feed if the configured `besuper.ai` source is not the one you mean | Avoids ingesting the wrong podcast |
| 5 | Decide whether Benzinga API access is worth a paid trial/API key | Needed before analyst-rating/news/options ingestion can be implemented |
| 6 | Decide whether Unusual Whales API access is worth a paid token | Needed before options-flow ingestion can be implemented |
| 7 | Confirm whether daily source refresh should also run pre-market in addition to after close | More frequent refresh improves freshness but may consume provider limits |

## Historical Tracking

The engine must save daily snapshots instead of overwriting prior results.

Historical records should include:

- Date and time of run
- Input data source versions or timestamps
- Current price
- Analyst target
- Fundamental target
- Technical target
- Blended target
- Score
- Recommendation action
- Confidence
- Research note
- Portfolio state, if available

This history should support later backtesting and performance review.

Key questions for historical review:

- Did high-scoring stocks outperform lower-scoring stocks?
- Were blended targets too optimistic or too conservative?
- Which scoring components were most predictive?
- Which data providers were most useful?
- Did short-term recommendations perform differently from long-term recommendations?

## Risk Management Requirements

The engine should enforce portfolio and recommendation guardrails.

Initial guardrails:

- No single stock should exceed 10% of the account without an explicit override.
- The engine may recommend adding to an existing stock only if the suggested purchase keeps that stock at or below 10% of total holdings.
- Short-term positions should generally not exceed 5% of the account each.
- The short-term sleeve should not exceed 25% of the account.
- The engine should flag excessive concentration in one theme, such as semiconductors or speculative AI.
- Short-term recommendations should include an exit or review trigger.
- Long-term holdings should be reviewed monthly unless a major risk event occurs.
- The engine should track cash availability and settlement constraints before recommending trades.
- The engine should avoid options, margin, short selling, leveraged ETFs, and automatic trade placement in version 1.

## Retirement Account Constraints

Because this account is a retirement account, the engine should be conservative about trading mechanics.

Requirements:

- Track whether funds are settled before recommending short-term redeployment.
- Flag potential day-trading or cash-trading issues.
- Avoid margin-based assumptions unless explicitly enabled and verified.
- Prefer manual approval before any trade action.
- Treat tax-advantaged status as a reason to avoid unnecessary churn, not as permission to overtrade.

## Future E*TRADE Integration

Potential E*TRADE integration should be phased.

| Phase | Capability |
| --- | --- |
| 1 | No E*TRADE integration; recommendations only |
| 2 | Read-only account balances and holdings |
| 3 | Portfolio drift and suggested trade sizing |
| 4 | Order preview after explicit user approval |
| 5 | Manual-confirm trade placement |

The engine should not place live trades without explicit user confirmation.

Execution boundary:

- Version 1 remains recommendation-only.
- Future versions may support E*TRADE order preview and manual-confirm trade placement.
- The system should never submit autonomous trades without a user approval step.
- Production read-only sync should default to the IRA rollover account. The account-selection design should still allow additional accounts in the future.
- For short-term trades, the system should optimize for fast review and execution: clear entry price, position size, stop/review trigger, target/exit trigger, holding-period type, and one-click-ready order preview where supported.
- Short-term recommendations should include both entry and exit planning before trade placement is enabled.
- A short-term position should be easy to exit quickly, but the engine should still avoid panic-selling automation. Exits should be recommended or previewed, then manually confirmed.
- Any future order placement workflow must distinguish buy, sell, trim, and exit actions and show the projected portfolio impact before confirmation.

Potential future short-term execution workflow:

1. Engine identifies short-term opportunity.
2. Engine shows trade type: day trade, weekly swing, or 2-4 week tactical.
3. Engine proposes entry range, order type, position size, target, and stop/review trigger.
4. User selects "preview order."
5. E*TRADE order preview returns estimated order details.
6. User manually confirms or rejects.
7. Engine records trade decision, rationale, and follow-up exit rule.

## Open Decisions

Items still to decide:

- V1.6 free-data ingestion: raw + curated storage is the default. Store small raw payloads inline in SQLite and large payloads under `data/raw_payloads/`; curate normalized `score_signals` in shadow mode before any score impact is enabled.
- Shadow score signals: V1.6 signals must be visible in dashboard drilldowns but must not change official score, action, blended target, or trade recommendation until validated with history and user feedback.
- Paid provider tracking: keep implementation free-only for now. Track known pricing and unlocks for FMP, Alpha Vantage, Finnhub, Benzinga, and Unusual Whales, but do not buy or depend on paid APIs until provider gaps justify the spend.
- Speculative AI review after observation period: SOUN, AEHR, BBAI, ALAB, and PLAB are approved as watchlist-only for 2-3 weeks; decide whether to add/remove names or enable buy recommendations after score history accumulates.
- Alpha Vantage rate-limit strategy: key is configured and fallback works for many current prices; decide whether to slow the refresh cadence, cache more aggressively, or upgrade if free-tier limits become a problem.
- Finnhub access: free key is configured and verified; decide later whether blocked endpoints such as price targets, estimates, upgrades/downgrades, sentiment, and transcripts justify paid access.
- Fundamentals target model tuning: V1.2 first-pass implementation stores internal fundamental target rows with assumptions and ranges; tune peer groups, valuation defaults, caps, and haircuts over time using backtesting and user feedback.
- Technical target model tuning: V1.3 first-pass implementation stores technical target rows from daily price history, moving averages, support/resistance, entry zones, stop/review levels, and volatility notes. Tune windows, buffers, caps, confidence haircuts, and short-term trade-type rules over time.
- Price-history provider strategy: V1.3 uses Yahoo chart data as the current no-key historical-price fallback. Alpha Vantage daily adjusted history was blocked as a premium endpoint for the configured key, and Stooq required API/captcha access during testing. Decide later whether to add a paid/official historical-price provider.
- Blended target tuning: V1.3 blends analyst, fundamental, and technical targets when available, with sleeve-specific weights. Next tuning should improve high-confidence criteria, stale/provider-gap penalties, and evidence-driven deep-research adjustments.
- Paid analyst-target provider review after observation period: defer until at least 10 provider-gap runs or about 14 days of real usage show whether FMP/Finnhub/another provider is worth paying for.
- Production E*TRADE multi-account expansion: current sync defaults to the IRA rollover account; decide future rules when adding more real accounts.
- Email delivery implementation details: recipient is mthuth@gmail.com and cadence is daily; decide subject format, delivery mechanism, and whether to create drafts or send automatically.
- Google Sheets implementation details: decide whether to create a new Drive spreadsheet or update an existing one, choose the Drive folder/location, and define whether charts/formulas/historical tabs are needed.
- Dashboard feature implementation details: source drilldowns are implemented for V1.1; holdings allocation chart, historical score trend, and richer short-term trade queue still need exact chart styling and trade-queue fields during implementation.
- Deep-research source subscriptions: dashboard now supports source rating and weighting; decide which podcasts, newsletters, analyst feeds, news sources, and options-flow sources to add first.
- Evidence ingestion implementation: V1.1 implements CIK mapping, SEC submissions/companyfacts ingestion, Finnhub free-endpoint ingestion, and source drilldowns. V1.4 implements Alpha Vantage news/sentiment ingestion and FMP stock-news/transcript access checks. Remaining ingestion candidates are richer transcript capture where provider access allows it, company investor-relations feeds, and richer Finnhub sentiment if paid access is enabled later.
- Research-depth implementation: V1.4 adds Alpha Vantage news/sentiment ingestion, FMP stock-news/transcript access checks, deterministic research briefs, and explanatory-only dashboard evidence summaries. Next tuning should improve relevance filtering, source feedback weighting, and eventual capped scoring impact after enough review history exists.
- Source-to-symbol relevance tagging: broad podcast/newsletter/source evidence should be stored once as raw evidence, then linked to relevant V1 symbols through deterministic `evidence_symbol_tags`. Dashboard views should show the matched term so relevance is auditable. Tagging remains explanatory only until enough review history exists.
- Feedback implementation detail: dashboard buttons plus text box are approved; decide later whether feedback should save through a local server/API or continue generating local commands from static HTML.
- Future E*TRADE order-preview requirements: order types, short-term exit workflow, confirmation screen, and audit log.
