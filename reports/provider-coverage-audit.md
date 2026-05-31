# Provider Coverage Audit

Generated: 2026-05-31

Branch: `codex/provider-coverage-audit`

Scope: approved universe from `config/research_inputs.csv` (25 symbols) compared with the local SQLite data source `/Users/matthuth/Documents/Stock Trading/data/stock_trading.sqlite`. This audit is report-only: no live provider refreshes were run and no scoring, target blending, decision-safety, recommendation, or provider API behavior was changed.

## Executive Summary

| Coverage area | Symbols covered |
| --- | --- |
| Configured current price | 22/25 (88%) |
| Price history | 25/25 (100%) |
| Analyst target source rows | 7/25 (28%) |
| Fundamental target source rows | 25/25 (100%) |
| SEC companyfacts evidence | 21/25 (84%) |
| SEC CIK mapping | 22/25 (88%) |
| Official IR URL coverage | 22/25 (88%) |
| Public-source evidence | 25/25 (100%) |
| Unresolved provider gaps | 25/25 (100%) |

Key gaps:

- Configured current price: BBAI, ALAB, PLAB
- Price history: none
- Analyst target source rows: SNOW, MDB, AVGO, NET, ASML, DDOG, PANW, CRWD, ARM, MU, QQQM, VGT, SMH, SOUN, AEHR, BBAI, ALAB, PLAB
- SEC companyfacts evidence: TSM, QQQM, VGT, SMH
- SEC CIK mapping: QQQM, VGT, SMH
- Official IR URL coverage: QQQM, VGT, SMH
- Public-source evidence: none

Notes:

- All 25 symbols have price-history rows, but the latest stored price-history date is 2026-05-27, which is 4 calendar days before this audit date.
- Fundamental target source rows exist for all 25 symbols, but SEC companyfacts evidence exists for 21 symbols. ETFs (`QQQM`, `VGT`, `SMH`) and `TSM` do not currently have SEC companyfacts evidence rows in the local database.
- Analyst target source rows exist for 7 symbols: `AMD`, `AMZN`, `GOOGL`, `META`, `MSFT`, `NVDA`, and `TSM`.
- Every approved symbol currently has at least one unresolved provider gap, mostly from failed network/provider refresh attempts and missing paid/blocked endpoints.

## Symbol Coverage Matrix

| Symbol | Price | History | Analyst | Companyfacts | CIK | IR | Evidence | Gaps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | yes | yes (2026-05-27) | yes | yes | yes | yes | yes (55) | yes (12) |
| META | yes | yes (2026-05-27) | yes | yes | yes | yes | yes (34) | yes (12) |
| MSFT | yes | yes (2026-05-27) | yes | yes | yes | yes | yes (58) | yes (11) |
| SNOW | yes | yes (2026-05-27) | no | yes | yes | yes | yes (41) | yes (12) |
| AMZN | yes | yes (2026-05-27) | yes | yes | yes | yes | yes (47) | yes (11) |
| MDB | yes | yes (2026-05-27) | no | yes | yes | yes | yes (27) | yes (12) |
| TSM | yes | yes (2026-05-27) | yes | no | yes | yes | yes (27) | yes (11) |
| AVGO | yes | yes (2026-05-27) | no | yes | yes | yes | yes (33) | yes (12) |
| GOOGL | yes | yes (2026-05-27) | yes | yes | yes | yes | yes (44) | yes (11) |
| NET | yes | yes (2026-05-27) | no | yes | yes | yes | yes (30) | yes (11) |
| ASML | yes | yes (2026-05-27) | no | yes | yes | yes | yes (33) | yes (12) |
| DDOG | yes | yes (2026-05-27) | no | yes | yes | yes | yes (32) | yes (11) |
| AMD | yes | yes (2026-05-27) | yes | yes | yes | yes | yes (40) | yes (12) |
| PANW | yes | yes (2026-05-27) | no | yes | yes | yes | yes (38) | yes (11) |
| CRWD | yes | yes (2026-05-27) | no | yes | yes | yes | yes (31) | yes (12) |
| ARM | yes | yes (2026-05-27) | no | yes | yes | yes | yes (31) | yes (11) |
| MU | yes | yes (2026-05-27) | no | yes | yes | yes | yes (33) | yes (12) |
| QQQM | yes | yes (2026-05-27) | no | no | no | no | yes (13) | yes (11) |
| VGT | yes | yes (2026-05-27) | no | no | no | no | yes (8) | yes (12) |
| SMH | yes | yes (2026-05-27) | no | no | no | no | yes (14) | yes (11) |
| SOUN | yes | yes (2026-05-27) | no | yes | yes | yes | yes (27) | yes (12) |
| AEHR | yes | yes (2026-05-27) | no | yes | yes | yes | yes (30) | yes (11) |
| BBAI | no | yes (2026-05-27) | no | yes | yes | yes | yes (32) | yes (12) |
| ALAB | no | yes (2026-05-27) | no | yes | yes | yes | yes (31) | yes (11) |
| PLAB | no | yes (2026-05-27) | no | yes | yes | yes | yes (29) | yes (11) |

See `reports/provider-coverage-audit.csv` for row-level details including latest dates, row counts, sources, CIKs, IR URLs, and unresolved provider-gap summaries.

## Provider And Source Issue Summary

This table combines latest unresolved provider field statuses with historical non-ok payload/raw-ingestion statuses where they identify blocked, rate-limited, parser-gapped, missing, stale, or not-implemented providers.

| Provider/source | Issue type | Count | Examples or note |
| --- | --- | --- | --- |
| FMP | missing data | 25 | target_price AEHR: FMP quote failed: <urlopen error [Errno 8] nodename nor servname provided, or not known>; error_class=network_transient;; target_price ALAB: FMP quote failed: <urlopen error [Errno 8] nodename nor servname provided, or not known>; error_class=network_transient; |
| FMP/Alpha Vantage | missing data | 3 | current_price ALAB: FMP quote failed: <urlopen error [Errno 8] nodename nor servname provided, or not known>; error_class=network_transient;; current_price BBAI: FMP quote failed: <urlopen error [Errno 8] nodename nor servname provided, or not known>; error_class=network_transient; |
| SEC EDGAR | missing data | 3 | cik_mapping QQQM: No SEC ticker CIK mapping found; cik_mapping SMH: No SEC ticker CIK mapping found |
| Alpha Vantage | rate-limited | 4 | news_sentiment NVDA: We have detected your API key as [redacted] and our standard API rate limit is 25 requests per day. Please subscribe to ; news_sentiment SNOW: Thank you for using Alpha Vantage! Please consider spreading out your free API requests more sparingly (1 request per se |
| FMP/Alpha Vantage | stale | 22 | current_price AEHR: FMP quote failed: <urlopen error [Errno 8] nodename nor servname provided, or not known>; error_class=network_transient;; current_price AMD: FMP quote failed: <urlopen error [Errno 8] nodename nor servname provided, or not known>; error_class=network_transient; |
| Benzinga news | not implemented | 1 | Decide whether to request API pricing or trial |
| Benzinga unusual options | not implemented | 1 | Compare with Unusual Whales before purchasing |
| Unusual Whales options flow | not implemented | 1 | Evaluate API token cost and endpoint fit for V1 short-term queue |
| Business Wire technology feed | blocked | 2 | historical payload/raw ingestion non-ok rows |
| Company investor relations | blocked | 8 | historical payload/raw ingestion non-ok rows |
| FMP | blocked | 58 | historical payload/raw ingestion non-ok rows |
| Finnhub | blocked | 4 | historical payload/raw ingestion non-ok rows |
| TSMC Newsroom | blocked | 2 | historical payload/raw ingestion non-ok rows |
| The Information AI newsletter | blocked | 3 | historical payload/raw ingestion non-ok rows |
| VentureBeat AI | blocked | 2 | historical payload/raw ingestion non-ok rows |
| AI Daily Brief podcast | parser-gapped | 3 | historical payload/raw ingestion non-ok rows |
| Arm Newsroom | parser-gapped | 2 | historical payload/raw ingestion non-ok rows |
| SemiAnalysis newsletter | parser-gapped | 3 | historical payload/raw ingestion non-ok rows |
| Alpha Vantage | rate-limited | 12 | historical payload/raw ingestion non-ok rows |

## Interpretation

- Current-price coverage is incomplete for the speculative/watchlist names `BBAI`, `ALAB`, and `PLAB`; the local config has no current price for those symbols.
- Price-history coverage is broad, but stale relative to the audit date. The unresolved `yahoo price_history` gaps show the last refresh attempts failed with network errors.
- Analyst target coverage is the thinnest major target input. Most symbols rely on fundamental and technical target rows without an analyst target source row.
- SEC/IR coverage is good for individual companies but not ETFs, which is expected for CIK and company IR URL mapping.
- Provider failures remain visible even though reports can still be generated; this is desirable for review safety.

## Method

- Approved symbols came from `config/research_inputs.csv`.
- Configured current price came from `current_price` and `price_source` in `config/research_inputs.csv`.
- Price history came from `price_history` grouped by symbol.
- Analyst and fundamental target coverage came from `target_sources` grouped by `target_type`.
- SEC companyfacts coverage came from `research_evidence` rows where the source name/type indicates SEC companyfacts/XBRL.
- SEC CIK mapping came from `company_identifiers`.
- Official IR coverage came from `config/official_ir_sources.csv`.
- Public-source evidence came from `research_evidence`, excluding local derived sources whose names start with `Local `.
- Unresolved provider gaps came from the latest non-ok `provider_field_status` rows that had not been superseded by a later ok status for the same symbol/field.
