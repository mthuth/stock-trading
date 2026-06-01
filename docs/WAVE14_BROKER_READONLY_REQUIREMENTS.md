# Wave 14 Broker Read-Only Requirements

Wave 14 defines Broker Read-Only Integration. This document is requirements-only for fixture and test-harness alignment. It does not authorize broker connector implementation in this branch and does not change scoring formulas, target blending, recommendation labels, target-confidence rules, decision-safety rules, allocation formulas, provider behavior, AI generation, dashboard rendering, local-console implementation, storage schema, broker behavior, or trading behavior.

## Product Goal

Wave 14 should make the app better at answering:

- What do I currently hold?
- How much cash or buying capacity is available for manual review?
- What are current position market values?
- What is my current allocation by sleeve?
- Does the suggested long-term add fit current holdings and caps?
- Is holdings/cash data stale, missing, or unavailable?
- Does broker context change the capital-deployment review?

Broker context is read-only decision support. It may improve holdings, cash, allocation, and data-quality visibility, but it must not place trades, preview orders, write to broker accounts, or imply guaranteed performance.

## Non-Goals

Wave 14 must not add:

- Automatic trading.
- Order preview.
- Order placement.
- Order modification.
- Order cancellation.
- Broker write actions.
- Margin or day-trading compliance engine.
- Options or short-selling execution.
- Margin trading logic.
- Same-day trading execution logic.
- Live broker calls in tests.
- Real credentials, tokens, account numbers, OAuth secrets, refresh tokens, session tokens, or personally identifying account details in the repo.
- Automatic score changes from broker data.
- Automatic target changes from broker data.
- Automatic recommendation changes from broker data.
- Automatic decision-safety changes from broker data.
- Automatic source-weight changes from broker data.
- Automatic model tuning from broker data.

If broker data contains buying power, margin, options, shorts, day-trading, or similar fields, Wave 14 should treat them as read-only context with warnings. It must not operationalize FINRA Rule 4210, margin requirements, day-trading rules, options permissions, short-selling execution, or trade eligibility.

## Read-Only Broker Scope

Read-only broker integration may define contracts for:

- Account snapshots.
- Holdings/positions snapshots.
- Cash and buying-capacity snapshots.
- Broker sync status.
- Stale, missing, unavailable, or error states.
- Allocation and sleeve context derived from snapshots.
- Capital availability fallback to manual/configured values.

Broker data may inform report or local-console review context. It must not become execution logic, trading advice, order tickets, order previews, or automatic recommendation changes.

## Credential And Security Requirements

Security rules:

- Do not commit real credentials, tokens, account numbers, OAuth secrets, refresh tokens, session tokens, or personally identifying account details.
- Use `.env.example` placeholders only when connector setup is later scoped.
- Fixtures must use fake or masked account identifiers.
- Tests must reject unmasked account identifiers and obvious secret-like values.
- Tests must use fake account IDs, fake positions, and fixture-backed broker responses.
- No test may require a live broker account.
- Any future live broker connector must be opt-in, disabled by default, and clearly read-only.
- Raw broker payloads, if stored in a later implementation, must redact account identifiers and secrets before committing or exporting artifacts.

## Account Snapshot Requirements

An account snapshot should include:

- `account_id_masked`
- `account_label`
- `account_type`
- `broker_name`
- `snapshot_at`
- `source`
- `source_status`
- `currency`
- `total_market_value`
- `cash_available`
- `buying_capacity`
- `read_only`
- `warnings`

Account identifiers must remain masked. Account type is context only and must not enable margin, day-trading, options, short-selling, or execution behavior.

## Holdings Snapshot Requirements

Each holding should include:

- `account_id_masked`
- `symbol`
- `company`
- `quantity`
- `market_value`
- `last_price`
- `sleeve`
- `position_pct`
- `cost_basis`
- `cost_basis_status`
- `source`
- `snapshot_at`
- `warnings`

Unknown cost basis should be represented explicitly with `cost_basis_status: unknown` and a warning. It must not be inferred optimistically.

## Cash And Capital Availability Requirements

Broker cash context should include:

- Available cash or settled cash where provided.
- Buying capacity as read-only context if the broker provides it.
- Manual/config capital fallback status.
- Snapshot timestamp and source.
- Stale, missing, or unavailable warnings.
- Whether cash is enough to consider the existing long-term add amount.

Manual/config capital availability remains the fallback. Broker data should not remove the ability to run the app without broker credentials or a broker snapshot.

## Allocation And Sleeve Context Requirements

Broker holdings may support review-only allocation context:

- Current market value by sleeve.
- Current position percentage.
- Single-stock cap warning.
- Sleeve target gap or overage warning.
- Existing holding exposure before a suggested add.
- Whether a suggested add appears constrained by current holdings.

Broker data must not change allocation formulas or caps. It can only explain whether current holdings/cash appear to fit those existing rules.

## Sync Status And Staleness Requirements

Broker sync status should distinguish:

- `available`
- `stale`
- `missing`
- `error`
- `unavailable`

Each status should include:

- `last_success_at`
- `snapshot_at`
- `source_status`
- `stale_after_hours`
- `warnings`
- `fallback_used`

Stale or missing broker data should surface as reliability gaps. The app should not pretend stale holdings or cash are current.

## Local Console And Report Requirements

Future local console or report surfaces may show:

- Read-only broker sync status.
- Masked account list.
- Current holdings summary.
- Cash/capital availability context.
- Allocation by sleeve.
- Position cap and sleeve cap warnings.
- Manual/config fallback status.

The UI must clearly label broker data as read-only and timestamped. It must not include order preview, order placement, order modification, order cancellation, broker write actions, run buttons that call live broker APIs, or trade execution language.

## Fallback Behavior When Broker Is Unavailable

When broker data is unavailable, missing, stale, or errored:

- Preserve manual/config capital availability fallback.
- Show broker data status and warning.
- Do not block recommendation/report generation solely because broker data is absent.
- Do not infer cash, holdings, or cost basis from stale or missing broker data.
- If broker context is required for a future review, mark the review as needing broker snapshot refresh rather than changing the recommendation.

## Test And Fixture Requirements

Fixture scenarios live in `tests/fixtures/broker_readonly/`.

Required fixture contract:

- Fixtures use fake symbols, fake positions, or approved-universe symbols with fake quantities.
- Account identifiers are masked, for example `acct-****-001`.
- No secrets, tokens, account numbers, OAuth values, refresh tokens, session tokens, or personally identifying account details appear in fixtures.
- Fixtures include source and timestamp fields.
- Fixtures include read-only and recommendation-only guardrails.
- Tests do not import broker modules, require real credentials, or make live broker calls.

## Acceptance Criteria

- Requirements doc is clear and Codex-readable.
- Fixture scenarios cover account with cash and positions, no cash available, stale broker snapshot, missing broker snapshot, holding exceeds single-stock cap, holding below target sleeve, unknown cost basis, masked account identifiers, multiple accounts, broker unavailable/error, margin/buying-power field present but context-only, and no broker data with manual/config capital fallback.
- Fixture tests validate structure, source/timestamp fields, sync statuses, masked account identifiers, no-sensitive-value constraints, read-only guardrails, and fallback behavior.
- Tests do not require broker connector modules, live broker credentials, live broker calls, report rendering, storage schema changes, local-console changes, or application behavior changes.
- No product behavior changes.
- No credentials are added.

## Fixture Scenarios

| Scenario | Fixture | Purpose |
| --- | --- | --- |
| Account with cash and positions | `account_with_cash_and_positions.json` | Broker snapshot has read-only cash and holdings context. |
| No cash available | `no_cash_available.json` | Cash is zero and buy capacity should be held for manual review. |
| Stale broker snapshot | `stale_broker_snapshot.json` | Broker snapshot is stale and should produce warnings. |
| Missing broker snapshot | `missing_broker_snapshot.json` | Broker snapshot is missing and manual/config fallback should remain available. |
| Holding exceeds single-stock cap | `holding_exceeds_single_stock_cap.json` | Existing position exceeds cap and should be visible as context only. |
| Holding below target sleeve | `holding_below_target_sleeve.json` | Sleeve is below target and should appear as allocation context. |
| Unknown cost basis | `unknown_cost_basis.json` | Unknown cost basis is explicit and not inferred. |
| Masked account identifiers | `masked_account_identifiers.json` | Fixture proves account IDs remain redacted. |
| Multiple accounts | `multiple_accounts.json` | Multiple masked accounts can be summarized without revealing details. |
| Broker unavailable/error | `broker_unavailable_error.json` | Broker error is visible and does not block manual/config fallback. |
| Margin/buying-power field present but context-only | `margin_buying_power_context_only.json` | Margin or buying-power fields are warnings, not permissions. |
| No broker data, manual/config capital availability fallback used | `manual_config_fallback_used.json` | App can continue with configured capital context and no broker snapshot. |

These fixtures are contract examples. Later implementation branches should either consume them directly or add behavior-level fixtures that preserve read-only broker boundaries, masking, fallback behavior, and no-secret constraints.

## Future Integration Notes

Future Wave 14 implementation should prefer focused helper modules and fixture-driven tests before report, local-console, storage, workflow, or broker connector changes.

Likely follow-up branches:

- `codex/broker-readonly-snapshot-contract`
- `codex/broker-holdings-import-fixtures`
- `codex/broker-cash-capital-context`
- `codex/broker-sync-status`
- `codex/broker-readonly-report-section`
- `codex/local-console-broker-readonly-panel`

Any future live broker connector must be opt-in, disabled by default, read-only, and covered by mock/fixture tests. Broker context remains recommendation-only review support.
