# Data Maintenance Backlog

Generated from local provider/source gap inputs. This backlog is review-only and does not create GitHub issues.

- Total work requests: 9
- GitHub issues created: false

| ID | Priority | Title | Action | Symbols | Sources | Status |
| --- | --- | --- | --- | --- | --- | --- |
| DMW-001 | P0 blocker | Restore missing current price coverage | fix_config | ALAB, BBAI, PLAB | Configured current price, FMP/Alpha Vantage | proposed |
| DMW-002 | P1 high | Add foreign-issuer or companyfacts fallback | add_fallback | TSM | SEC EDGAR, Taiwan Semiconductor | proposed |
| DMW-003 | P1 high | Resolve analyst target breadth gap | paid_provider_decision | AEHR, ALAB, ARM, ASML, AVGO, BBAI, CRWD, DDOG, MDB, MU, NET, PANW, PLAB, SNOW, SOUN | Analyst target providers | proposed |
| DMW-004 | P2 medium | Resolve analyst target breadth gap | add_fallback | AEHR, ALAB, ARM, ASML, AVGO, BBAI, CRWD, DDOG, MDB, MU, NET, PANW, PLAB, SNOW, SOUN | Analyst target providers | proposed |
| DMW-005 | P2 medium | Improve parser for configured source failures | improve_parser | AEHR, ALAB, AMD, AMZN, ARM, ASML, AVGO, BBAI, CRWD, DDOG, GOOGL, MDB, META, MSFT, MU, NET, NVDA, PANW, PLAB, SNOW, SOUN, TSM | Company investor relations | proposed |
| DMW-006 | P2 medium | Decide paid provider strategy for transcripts and news | paid_provider_decision | AEHR, ALAB, AMD, AMZN, ARM, ASML, AVGO, BBAI, CRWD, DDOG, GOOGL, MDB, META, MSFT, MU, NET, NVDA, PANW, PLAB, QQQM, SMH, SNOW, SOUN, TSM, VGT | FMP | proposed |
| DMW-007 | P2 medium | Implement configured source or mark it deferred | paid_provider_decision | - | Benzinga news, Benzinga unusual options, Unusual Whales options flow | proposed |
| DMW-008 | P3 low | Verify feed URL for configured public source | fix_config | - | AMD Newsroom, ASML Press Releases, Arm Newsroom, BG2 podcast, Bens Bites newsletter, Broadcom Newsroom, Business Wire technology feed, Decoder podcast, GlobeNewswire technology feed, IEEE Global Semiconductors RSS, InfoQ AI ML Data Engineering, Micron Newsroom, MongoDB Blog, NVIDIA AI Podcast, NVIDIA official RSS, No Priors podcast, TSMC Newsroom, The Rundown AI newsletter | proposed |
| DMW-009 | P3 low | Mark ETF operating-company data gaps as expected | mark_expected_gap | QQQM, SMH, VGT | Analyst target providers, Company investor relations, SEC EDGAR | proposed |

Review-only data maintenance backlog. Work requests do not change scores, recommendation labels, targets, target confidence, decision-safety rules, allocation formulas, provider API behavior, broker behavior, or trading.
