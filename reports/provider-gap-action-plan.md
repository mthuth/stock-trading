# Provider Gap Action Plan

Generated: 2026-05-31

Branch: `codex/provider-gap-action-plan`

Source inputs:

- `reports/provider-coverage-audit.md`
- `reports/provider-coverage-audit.csv`
- `stock_trading/provider_gap_status.py`
- `stock_trading/source_health.py`
- `scripts/plan_ingestion_runs.py`
- `config/research_source_integrations.csv`

Scope guardrail: this is a report-only action plan. Do not change scoring, target blending, decision safety, provider API behavior, or dashboard code while executing this plan. Convert accepted actions into separate scoped branches.

## Priority Model

| Priority | Decision impact | How to use it |
| --- | --- | --- |
| Critical | Blocks decision-safe buy | Fix before allowing any buy/readiness interpretation for affected symbols. |
| High | Weakens target confidence | Prioritize after critical blockers; these affect upside credibility and target-source breadth. |
| Medium | Weakens research synthesis | Improve evidence quality, freshness, or corroboration; should not change actions directly. |
| Low | Expected/acceptable gap | Mark explicitly so dashboards and audits stop presenting expected non-company gaps as operational failures. |

## Executive Priority Order

1. Critical: restore current-price coverage for `BBAI`, `ALAB`, and `PLAB`.
2. High: resolve analyst-target breadth for operating companies missing analyst target rows.
3. High: classify SEC companyfacts gaps into foreign-issuer fallback work versus ETF expected gaps.
4. Medium: improve official IR parsing for operating-company IR URLs that are configured but failing.
5. Medium: decide whether FMP transcripts/news and richer analyst-target coverage justify paid-provider work.
6. Medium: improve Finnhub company-news and Alpha Vantage sentiment reliability where current free/provider limits allow.
7. Low: mark ETF/non-operating-company gaps as expected for `QQQM`, `VGT`, and `SMH`.

## Action Plan By Root Cause

### Missing Current Price

Priority: Critical

Decision impact: Missing current price blocks decision-safe buy because upside and target-vs-price interpretation depend on a current price.

Affected symbols:

- `BBAI`
- `ALAB`
- `PLAB`

Evidence from audit:

- Configured current price coverage is 22/25.
- `BBAI`, `ALAB`, and `PLAB` have price history but no configured current price in `config/research_inputs.csv`.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Fix config | Update `config/research_inputs.csv` only after a verified refresh or manual review provides current prices and source attribution. | Preserve recommendation-only behavior; do not hardcode unsupported values. |
| Add fallback | Add a separate ingestion/reporting task to use latest valid price-history close as a display fallback when current quote refresh fails. | This should be its own behavior PR with regression tests because it can affect decision safety. |
| Mark expected gap | Do not mark these as expected gaps. | These are operating/speculative symbols where missing price is a real blocker. |

Exit criteria:

- Each affected symbol has a nonzero current price and a clear price source, or the dashboard explicitly blocks buy-readiness using a latest-history fallback label.

### Missing Analyst Target Coverage

Priority: High for operating companies; Low for ETFs

Decision impact: Missing analyst targets weaken target confidence because target methodology expects multiple independent target inputs where available.

Affected operating-company symbols:

- `SNOW`
- `MDB`
- `AVGO`
- `NET`
- `ASML`
- `DDOG`
- `PANW`
- `CRWD`
- `ARM`
- `MU`
- `SOUN`
- `AEHR`
- `BBAI`
- `ALAB`
- `PLAB`

ETF symbols to handle as expected gaps:

- `QQQM`
- `VGT`
- `SMH`

Evidence from audit:

- Analyst target source rows exist for 7/25 symbols.
- Analyst target rows exist only for `AMD`, `AMZN`, `GOOGL`, `META`, `MSFT`, `NVDA`, and `TSM`.
- `config/research_inputs.csv` labels many missing target sources as `Needs paid target provider`.
- Requirements defer paid analyst-provider decisions until enough provider-gap runs or usage evidence justify the spend.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Paid provider decision needed | Decide whether to pay for broader analyst targets through FMP, Finnhub, Benzinga, or another provider. | Keep decision separate from implementation; document cost, endpoint fit, and expected symbol coverage. |
| Add fallback | Use `config/manual_analyst_targets.csv` for reviewed supplemental analyst targets where paid coverage is not approved. | Manual rows must remain labeled manual and separate from provider targets. |
| Fix config | For any symbol with known reviewed analyst targets, add them to the manual analyst target file rather than changing scoring logic. | Do not change target blending weights. |
| Mark expected gap | Mark ETF analyst-target gaps as expected/non-company target gaps. | ETFs should use allocation, trend, risk, and basket/sector proxy logic rather than single-company analyst targets. |

Exit criteria:

- Operating-company target gaps are either backed by provider/manual target rows or explicitly labeled as low-confidence target breadth gaps.
- ETF target gaps are not counted as operating-company analyst coverage failures.

### Missing SEC CIK Mapping

Priority: Low

Decision impact: Expected/acceptable gap for ETF/non-operating-company holdings.

Affected symbols:

- `QQQM`
- `VGT`
- `SMH`

Evidence from audit:

- SEC CIK mapping coverage is 22/25.
- Missing CIK mappings are only the three ETFs.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Ignore for ETF | Do not attempt company CIK mapping for `QQQM`, `VGT`, or `SMH`. | These are funds, not operating-company issuers for this workflow. |
| Mark expected gap | Add a follow-up config/reporting task to classify ETF CIK gaps as expected. | This should reduce false operational noise in future audits. |

Exit criteria:

- ETF CIK gaps appear as expected/non-operating-company gaps, not unresolved provider failures.

### Missing SEC Companyfacts

Priority: High for `TSM`; Low for ETFs

Decision impact: Missing SEC companyfacts can weaken fundamental confidence for operating companies. For ETFs it is expected.

Affected operating-company symbol:

- `TSM`

ETF symbols:

- `QQQM`
- `VGT`
- `SMH`

Evidence from audit:

- SEC companyfacts coverage is 21/25.
- `TSM` has a CIK mapping but no companyfacts evidence rows.
- ETFs have neither companyfacts evidence nor CIK mapping.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Add fallback | Add a TSM-specific fallback plan for foreign-issuer fundamentals using annual-report, 20-F/6-K, official IR, or provider fundamentals. | Keep this as evidence/fundamentals ingestion work, not target-blending work. |
| Mark expected gap | Mark ETF companyfacts gaps as expected. | ETF fundamentals should use fund/sector/basket context, not SEC companyfacts. |
| Fix config | If TSM requires a different official filings/source path, document it in source configuration. | Do not change SEC provider behavior in this report-only PR. |

Exit criteria:

- `TSM` has either companyfacts-equivalent evidence or an explicit foreign-issuer fallback label.
- ETF companyfacts gaps are excluded from operating-company gap counts.

### Missing Official IR URL

Priority: Low

Decision impact: Expected/acceptable gap for ETF/non-operating-company holdings.

Affected symbols:

- `QQQM`
- `VGT`
- `SMH`

Evidence from audit:

- Official IR URL coverage is 22/25.
- `config/official_ir_sources.csv` contains operating-company IR URLs, not ETF fund pages.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Ignore for ETF | Do not add operating-company IR URLs for ETFs. | ETF fund pages are a different source category and should not masquerade as company IR. |
| Mark expected gap | Add a follow-up reporting classification for ETF official-IR gaps. | If ETF fund-page evidence is desired later, create a separate `fund_provider_page` or similar source category. |

Exit criteria:

- ETF IR gaps are labeled expected, or a separate fund-page source category is defined in a dedicated config/reporting task.

### Official IR Parser Errors

Priority: Medium

Decision impact: Weakens research synthesis and primary-source corroboration, but should not directly change scores/actions.

Affected symbols:

- 22 operating-company symbols with configured IR URLs.

Evidence from audit:

- `Company investor relations official_ir_page=error` appears for 22 symbols.
- `config/official_ir_sources.csv` already contains URLs for operating-company symbols.
- `source_health.py` classifies parser gaps and blocked sources as review-only source-health labels.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Improve parser | Add source-specific parsing for configured IR pages that block generic extraction or require release-link discovery. | Prioritize tier-1 official sources and symbols with high decision impact. |
| Fix config | Replace URLs that point to unstable landing pages with stable release/news pages when available. | Examples already use release pages for many symbols; verify failures before changing URLs. |
| Add fallback | Store page-link metadata even when full page extraction fails, so synthesis can cite official pages with lower confidence. | Keep fallback explanatory-only. |

Exit criteria:

- IR rows distinguish blocked access, parser gap, stable page-link capture, and full release extraction.
- Official IR failures are actionable by symbol/source instead of a flat 22-symbol error bucket.

### FMP Transcript/News Errors

Priority: Medium

Decision impact: Weakens research synthesis, catalyst review, and management-commentary coverage.

Affected symbols:

- All 25 approved symbols show `FMP earnings_transcripts=error`.
- All 25 approved symbols show `FMP stock_news=error`.

Evidence from audit:

- Provider issue summary shows FMP missing data for 25 symbols and historical blocked FMP rows.
- Requirements already state FMP stock-news/transcript access is blocked by the current plan and should remain visible until paid access is justified.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Paid provider decision needed | Decide whether FMP paid access is worth it for transcripts/news after enough observed gaps. | Compare value against Finnhub, Benzinga, official IR, and public-source alternatives. |
| Add fallback | Prefer official IR releases, SEC filings, public-source feeds, and manual transcript links before paying for transcripts. | Fallback evidence must remain source-attributed and explanatory. |
| Mark expected gap | For ETFs, mark transcript/news errors as expected. | ETFs do not have company earnings transcripts. |

Exit criteria:

- Operating-company transcript/news gaps have either a paid-provider decision, an official/public fallback, or a documented expected limitation.
- ETF transcript/news gaps are no longer treated as company evidence failures.

### Finnhub Company News Errors

Priority: Medium

Decision impact: Weakens company-news corroboration and near-term catalyst synthesis.

Affected symbols:

- 17 approved symbols in the audit summary, including operating companies and ETFs.

Evidence from audit:

- `Finnhub company_news=error` appears in 17 symbol summaries.
- Requirements say Finnhub free access was verified for quote, company profile, company news, recommendation trends, and earnings calendar, while other endpoints remain blocked.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Improve parser | Inspect whether failures are response-shape/parser issues versus provider access or symbol support. | Keep changes inside ingestion/source-health work, not scoring. |
| Add fallback | Use configured public sources and official IR evidence when Finnhub company news fails. | Public-source fallback should maintain corroboration-required labels. |
| Mark expected gap | For ETFs, mark company-news failures as expected or lower-priority. | ETF news should come from fund/sector sources, not company-news endpoints. |

Exit criteria:

- Finnhub company-news gaps classify as provider access, parser gap, no data, ETF expected gap, or successful ingestion by symbol.

### Alpha Vantage Sentiment Errors

Priority: Medium

Decision impact: Weakens sentiment/news context and catalyst synthesis; does not block the report.

Affected symbols from row-level unresolved gaps:

- `META`
- `MDB`
- `AVGO`
- `ASML`
- `AMD`
- `CRWD`
- `MU`
- `BBAI`

Evidence from audit:

- Provider issue summary shows Alpha Vantage rate limits.
- `scripts/plan_ingestion_runs.py` has cooldown behavior for `rate_limited` statuses.
- Requirements call for quota-aware Alpha Vantage rotation.

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Add fallback | Use public-source evidence and Finnhub company news where sentiment endpoint calls are rate-limited. | Sentiment should stay explanatory unless explicitly promoted later. |
| Fix config | Reduce or rotate Alpha Vantage sentiment pulls using source freshness/cooldown priorities. | This belongs in ingestion planning, not provider API semantics. |
| Paid provider decision needed | Decide later whether sentiment coverage justifies paid Alpha Vantage or another news/sentiment provider. | Do not upgrade blindly. |

Exit criteria:

- Alpha Vantage sentiment gaps identify rate-limit versus no-data versus parser failures.
- The planner avoids repeatedly spending daily quota on low-impact retries.

### ETF/Non-Operating-Company Expected Gaps

Priority: Low

Decision impact: Expected/acceptable gap. These should not create operating-company provider-remediation work.

Affected symbols:

- `QQQM`
- `VGT`
- `SMH`

Expected gaps:

- SEC CIK mapping
- SEC companyfacts
- Official company IR URL
- Earnings transcripts
- Company profile/news endpoints designed for operating companies
- Single-company analyst target rows

Recommended next actions:

| Action | Scope | Notes |
| --- | --- | --- |
| Ignore for ETF | Do not pursue company CIK, companyfacts, company IR, or company transcript work for ETF symbols. | Keep ETF scoring/reporting based on allocation, trend, risk, and basket/sector proxy context. |
| Mark expected gap | Add a future report classification so expected ETF gaps are separated from unresolved operating-company provider failures. | This reduces alert fatigue without hiding true provider failures. |
| Add fallback | If ETF evidence is needed, add a dedicated fund-page or fund-holdings source category. | Do not reuse company IR semantics for fund pages. |

Exit criteria:

- ETF expected gaps are explicitly classified and no longer inflate provider-remediation priority.

## Recommended Work Packages

| Order | Work package | Priority | Root causes covered | Suggested branch scope |
| ---: | --- | --- | --- | --- |
| 1 | Restore current-price coverage for speculative symbols | Critical | Missing current price | Config or ingestion fallback only |
| 2 | Analyst target breadth decision | High | Missing analyst target coverage | Provider decision doc plus optional manual target config |
| 3 | Foreign issuer and ETF SEC classification | High/Low | Missing SEC companyfacts, missing CIK mapping | Reporting/config classification only |
| 4 | Official IR parser hardening | Medium | Official IR parser errors, missing IR URL classification | Ingestion parser only |
| 5 | Transcript/news provider strategy | Medium | FMP transcript/news errors, Finnhub company news errors | Provider decision plus fallback source plan |
| 6 | Alpha Vantage quota-aware sentiment plan | Medium | Alpha Vantage sentiment errors | Ingestion planning only |
| 7 | ETF expected-gap suppression | Low | ETF/non-operating-company expected gaps | Reporting classification only |

## Non-Goals For Follow-Up PRs

- Do not change numeric scoring weights or action cutoffs.
- Do not change target-blending weights or confidence rules.
- Do not relax decision-safety blockers.
- Do not hide provider gaps; reclassify expected gaps separately.
- Do not add broker write behavior, order previews, or automatic trading.
- Do not purchase or assume paid provider access without an explicit product decision.
