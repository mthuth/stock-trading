# Data Gap Work Requests

Codex-ready work requests generated from local data-maintenance signals. These are docs/backlog items only; no GitHub issues were created.

## DMW-001: Restore missing current price coverage

- Priority: P0 blocker
- Status: proposed
- Recommended action: fix_config
- Suggested branch: `codex/data-maintenance-fix-config-missing-current-price`
- Root cause: missing_current_price
- Decision impact: Missing current price blocks trustworthy upside, sizing, and buy-readiness review.
- Affected symbols: ALAB, BBAI, PLAB
- Affected sources: Configured current price, FMP/Alpha Vantage
- Source refs: reports/provider-coverage-audit.csv:ALAB, reports/provider-coverage-audit.csv:BBAI, reports/provider-coverage-audit.csv:PLAB, reports/provider-gap-action-plan.md#missing-current-price

Acceptance criteria:
- Affected symbols have nonzero current price with source attribution.
- Each affected symbol has nonzero current price with source attribution.
- If a live quote is unavailable, a reviewed latest-history fallback is labeled clearly.
- Missing price appears as reliability blocker, not bearish thesis evidence.

Codex prompt seed:

> Create `codex/data-maintenance-fix-config-missing-current-price` to fix_config for missing_current_price. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

## DMW-002: Add foreign-issuer or companyfacts fallback

- Priority: P1 high
- Status: proposed
- Recommended action: add_fallback
- Suggested branch: `codex/data-maintenance-add-fallback-missing-companyfacts`
- Root cause: missing_companyfacts
- Decision impact: Missing companyfacts-equivalent evidence weakens fundamental review for operating companies.
- Affected symbols: TSM
- Affected sources: SEC EDGAR, Taiwan Semiconductor
- Source refs: reports/provider-coverage-audit.csv:TSM

Acceptance criteria:
- Fallback evidence remains source-attributed and does not change target-blending math.
- Operating-company companyfacts gaps have SEC, foreign-issuer, official IR, or provider-fundamentals fallback evidence.

Codex prompt seed:

> Create `codex/data-maintenance-add-fallback-missing-companyfacts` to add_fallback for missing_companyfacts. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

## DMW-003: Resolve analyst target breadth gap

- Priority: P1 high
- Status: proposed
- Recommended action: paid_provider_decision
- Suggested branch: `codex/data-maintenance-paid-provider-decision-missing-analyst-target-br`
- Root cause: missing_analyst_target_breadth
- Decision impact: Missing analyst targets weaken target confidence and upside credibility.
- Affected symbols: AEHR, ALAB, ARM, ASML, AVGO, BBAI, CRWD, DDOG, MDB, MU, NET, PANW, PLAB, SNOW, SOUN
- Affected sources: Analyst target providers
- Source refs: reports/provider-gap-action-plan.md#missing-analyst-target-coverage

Acceptance criteria:
- ETF target gaps are marked expected/non-operating-company.
- Operating-company target gaps are backed by provider/manual rows or labeled low-confidence.

Codex prompt seed:

> Create `codex/data-maintenance-paid-provider-decision-missing-analyst-target-br` to paid_provider_decision for missing_analyst_target_breadth. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

## DMW-004: Resolve analyst target breadth gap

- Priority: P2 medium
- Status: proposed
- Recommended action: add_fallback
- Suggested branch: `codex/data-maintenance-add-fallback-missing-analyst-target-breadth`
- Root cause: missing_analyst_target_breadth
- Decision impact: Thin analyst target breadth weakens target confidence and upside credibility.
- Affected symbols: AEHR, ALAB, ARM, ASML, AVGO, BBAI, CRWD, DDOG, MDB, MU, NET, PANW, PLAB, SNOW, SOUN
- Affected sources: Analyst target providers
- Source refs: reports/provider-coverage-audit.csv:AEHR, reports/provider-coverage-audit.csv:ALAB, reports/provider-coverage-audit.csv:ARM, reports/provider-coverage-audit.csv:ASML, reports/provider-coverage-audit.csv:AVGO, reports/provider-coverage-audit.csv:BBAI, reports/provider-coverage-audit.csv:CRWD, reports/provider-coverage-audit.csv:DDOG, reports/provider-coverage-audit.csv:MDB, reports/provider-coverage-audit.csv:MU, reports/provider-coverage-audit.csv:NET, reports/provider-coverage-audit.csv:PANW, reports/provider-coverage-audit.csv:PLAB, reports/provider-coverage-audit.csv:SNOW, reports/provider-coverage-audit.csv:SOUN

Acceptance criteria:
- Manual analyst targets remain labeled manual and separate from provider/model targets.
- Operating-company target gaps are backed by provider/manual target rows or labeled low-confidence.

Codex prompt seed:

> Create `codex/data-maintenance-add-fallback-missing-analyst-target-breadth` to add_fallback for missing_analyst_target_breadth. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

## DMW-005: Improve parser for configured source failures

- Priority: P2 medium
- Status: proposed
- Recommended action: improve_parser
- Suggested branch: `codex/data-maintenance-improve-parser-parser-failure`
- Root cause: parser_failure
- Decision impact: IR parser failures weaken primary-source corroboration.
- Affected symbols: AEHR, ALAB, AMD, AMZN, ARM, ASML, AVGO, BBAI, CRWD, DDOG, GOOGL, MDB, META, MSFT, MU, NET, NVDA, PANW, PLAB, SNOW, SOUN, TSM
- Affected sources: Company investor relations
- Source refs: reports/provider-coverage-audit.csv:AEHR, reports/provider-coverage-audit.csv:ALAB, reports/provider-coverage-audit.csv:AMD, reports/provider-coverage-audit.csv:AMZN, reports/provider-coverage-audit.csv:ARM, reports/provider-coverage-audit.csv:ASML, reports/provider-coverage-audit.csv:AVGO, reports/provider-coverage-audit.csv:BBAI, reports/provider-coverage-audit.csv:CRWD, reports/provider-coverage-audit.csv:DDOG, reports/provider-coverage-audit.csv:GOOGL, reports/provider-coverage-audit.csv:MDB, reports/provider-coverage-audit.csv:META, reports/provider-coverage-audit.csv:MSFT, reports/provider-coverage-audit.csv:MU, reports/provider-coverage-audit.csv:NET, reports/provider-coverage-audit.csv:NVDA, reports/provider-coverage-audit.csv:PANW, reports/provider-coverage-audit.csv:PLAB, reports/provider-coverage-audit.csv:SNOW, reports/provider-coverage-audit.csv:SOUN, reports/provider-coverage-audit.csv:TSM, reports/provider-gap-action-plan.md#official-ir-parser-errors

Acceptance criteria:
- IR parser distinguishes blocked access, parser gap, page-link capture, and full extraction.
- Official IR failures are actionable by symbol/source.

Codex prompt seed:

> Create `codex/data-maintenance-improve-parser-parser-failure` to improve_parser for parser_failure. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

## DMW-006: Decide paid provider strategy for transcripts and news

- Priority: P2 medium
- Status: proposed
- Recommended action: paid_provider_decision
- Suggested branch: `codex/data-maintenance-paid-provider-decision-paid-provider-gap`
- Root cause: paid_provider_gap
- Decision impact: Blocked transcript/news providers weaken catalyst review and management-commentary coverage.
- Affected symbols: AEHR, ALAB, AMD, AMZN, ARM, ASML, AVGO, BBAI, CRWD, DDOG, GOOGL, MDB, META, MSFT, MU, NET, NVDA, PANW, PLAB, QQQM, SMH, SNOW, SOUN, TSM, VGT
- Affected sources: FMP
- Source refs: reports/provider-coverage-audit.csv:AEHR, reports/provider-coverage-audit.csv:ALAB, reports/provider-coverage-audit.csv:AMD, reports/provider-coverage-audit.csv:AMZN, reports/provider-coverage-audit.csv:ARM, reports/provider-coverage-audit.csv:ASML, reports/provider-coverage-audit.csv:AVGO, reports/provider-coverage-audit.csv:BBAI, reports/provider-coverage-audit.csv:CRWD, reports/provider-coverage-audit.csv:DDOG, reports/provider-coverage-audit.csv:GOOGL, reports/provider-coverage-audit.csv:MDB, reports/provider-coverage-audit.csv:META, reports/provider-coverage-audit.csv:MSFT, reports/provider-coverage-audit.csv:MU, reports/provider-coverage-audit.csv:NET, reports/provider-coverage-audit.csv:NVDA, reports/provider-coverage-audit.csv:PANW, reports/provider-coverage-audit.csv:PLAB, reports/provider-coverage-audit.csv:QQQM, reports/provider-coverage-audit.csv:SMH, reports/provider-coverage-audit.csv:SNOW, reports/provider-coverage-audit.csv:SOUN, reports/provider-coverage-audit.csv:TSM, reports/provider-coverage-audit.csv:VGT, reports/provider-gap-action-plan.md#fmp-transcript-news-errors

Acceptance criteria:
- Official IR, SEC, and public-source fallbacks remain available before any paid-provider work.
- Paid transcript/news access has an explicit approve/defer decision.

Codex prompt seed:

> Create `codex/data-maintenance-paid-provider-decision-paid-provider-gap` to paid_provider_decision for paid_provider_gap. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

## DMW-007: Implement configured source or mark it deferred

- Priority: P2 medium
- Status: proposed
- Recommended action: paid_provider_decision
- Suggested branch: `codex/data-maintenance-paid-provider-decision-not-implemented-source`
- Root cause: not_implemented_source
- Decision impact: Configured source cannot improve evidence coverage until implementation or deferral is explicit.
- Affected symbols: -
- Affected sources: Benzinga news, Benzinga unusual options, Unusual Whales options flow
- Source refs: config/research_source_integrations.csv:Benzinga news, config/research_source_integrations.csv:Benzinga unusual options, config/research_source_integrations.csv:Unusual Whales options flow

Acceptance criteria:
- Compare with Unusual Whales before purchasing
- Decide whether to request API pricing or trial
- Evaluate API token cost and endpoint fit for V1 short-term queue
- No live provider calls are added without explicit follow-up scope.

Codex prompt seed:

> Create `codex/data-maintenance-paid-provider-decision-not-implemented-source` to paid_provider_decision for not_implemented_source. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

## DMW-008: Verify feed URL for configured public source

- Priority: P3 low
- Status: proposed
- Recommended action: fix_config
- Suggested branch: `codex/data-maintenance-fix-config-missing-feed-url`
- Root cause: missing_feed_url
- Decision impact: Missing feed URL may cause zero-record or parser-gap source behavior.
- Affected symbols: -
- Affected sources: AMD Newsroom, ASML Press Releases, Arm Newsroom, BG2 podcast, Bens Bites newsletter, Broadcom Newsroom, Business Wire technology feed, Decoder podcast, GlobeNewswire technology feed, IEEE Global Semiconductors RSS, InfoQ AI ML Data Engineering, Micron Newsroom, MongoDB Blog, NVIDIA AI Podcast, NVIDIA official RSS, No Priors podcast, TSMC Newsroom, The Rundown AI newsletter
- Source refs: config/research_source_integrations.csv:AMD Newsroom, config/research_source_integrations.csv:ASML Press Releases, config/research_source_integrations.csv:Arm Newsroom, config/research_source_integrations.csv:BG2 podcast, config/research_source_integrations.csv:Bens Bites newsletter, config/research_source_integrations.csv:Broadcom Newsroom, config/research_source_integrations.csv:Business Wire technology feed, config/research_source_integrations.csv:Decoder podcast, config/research_source_integrations.csv:GlobeNewswire technology feed, config/research_source_integrations.csv:IEEE Global Semiconductors RSS, config/research_source_integrations.csv:InfoQ AI ML Data Engineering, config/research_source_integrations.csv:Micron Newsroom, config/research_source_integrations.csv:MongoDB Blog, config/research_source_integrations.csv:NVIDIA AI Podcast, config/research_source_integrations.csv:NVIDIA official RSS, config/research_source_integrations.csv:No Priors podcast, config/research_source_integrations.csv:TSMC Newsroom, config/research_source_integrations.csv:The Rundown AI newsletter

Acceptance criteria:
- No source is treated as implemented solely because it appears in config.
- Source has a stable feed/archive URL or is documented as page-link only.

Codex prompt seed:

> Create `codex/data-maintenance-fix-config-missing-feed-url` to fix_config for missing_feed_url. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

## DMW-009: Mark ETF operating-company data gaps as expected

- Priority: P3 low
- Status: proposed
- Recommended action: mark_expected_gap
- Suggested branch: `codex/data-maintenance-mark-expected-gap-etf-expected-gap`
- Root cause: etf_expected_gap
- Decision impact: ETF/non-operating-company gaps should remain visible but not inflate operating-company blocker counts.
- Affected symbols: QQQM, SMH, VGT
- Affected sources: Analyst target providers, Company investor relations, SEC EDGAR
- Source refs: reports/provider-coverage-audit.csv:QQQM, reports/provider-coverage-audit.csv:SMH, reports/provider-coverage-audit.csv:VGT, reports/provider-gap-action-plan.md#etf-non-operating-company-expected-gaps

Acceptance criteria:
- ETF CIK/companyfacts/IR/analyst-target gaps are labeled expected or non-operating-company.
- Real ETF price/history gaps remain visible as actionable data gaps.

Codex prompt seed:

> Create `codex/data-maintenance-mark-expected-gap-etf-expected-gap` to mark_expected_gap for etf_expected_gap. Preserve recommendation-only behavior and run `python3 scripts/check_quality.py`.

Review-only data maintenance backlog. Work requests do not change scores, recommendation labels, targets, target confidence, decision-safety rules, allocation formulas, provider API behavior, broker behavior, or trading.
