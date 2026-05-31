# Wave 7 Handoff

This handoff prepares future Codex agents for Wave 7: Long-Term Capital Deployment. It is documentation-only and does not authorize app behavior changes.

## Product Goal

Wave 7 should make the app better at answering:

> What should I buy/add today for long-term holdings?

The broader product remains recommendation-only decision support for a human investor. The app can explain, prioritize, and record review context, but the user remains the only actor who can decide or place trades outside the app.

## Portfolio Intent

Current portfolio intent:

- Roughly two-thirds long-term/core holdings.
- Roughly one-third tactical, speculative, or higher-upside opportunity.

Wave 7 should prioritize the `long_term_core` sleeve and the `long_term_buy_add` decision mode. Tactical, speculative, ETF, and future short-candidate logic must remain separate from the current long-term add queue.

## Risk Posture

Current risk posture is cautious growth.

- Safety gates should remain stricter while trust is being built.
- Missed upside is acceptable when evidence, confidence, data quality, or allocation safety is weak.
- Measured aggression should come only after recommendation outcomes, decision-safety effectiveness, source usefulness, and catalyst follow-through show enough trust.

Wave 7 can improve how capital deployment is reviewed, but it must not loosen decision-safety rules or allocation formulas unless a future task explicitly scopes that behavior change and adds regression proof.

## Key Inputs Wave 7 Should Consume

Wave 7 should consume existing explanatory and review-only signals through established package APIs where possible:

- Decision safety.
- Target confidence.
- Allocation safety.
- Capital availability.
- Manual journal.
- Recommendation outcomes.
- AI synthesis and briefs.
- Provider gaps.
- Model learning context.

Capital availability should be introduced before broker read-only integration. The first shape should support configured/manual cash, monthly buy capacity, an as-of date, and a future optional broker read-only snapshot.

## What Wave 7 Must Not Do

Wave 7 must not add:

- Automatic trading.
- Broker write actions.
- Order preview.
- Tactical same-day engine behavior.
- Shorting or short-candidate integration into buy/add recommendations.
- Automatic model tuning.
- Automatic source-weight changes.
- AI output that changes official score, action, target, target confidence, suggested amount, decision gate, allocation, or provider behavior.

Wave 7 must not change scoring formulas, recommendation labels, target-blending math, target-confidence rules, decision-safety rules, allocation/suggested amount formulas, provider API behavior, broker behavior, or trading behavior unless the user explicitly scopes and approves that product change.

## Likely Wave 7 Branches

Use short-lived branches with one ownership area each:

| Branch | Purpose | Guardrail |
| --- | --- | --- |
| `codex/long-term-add-queue` | Make the long-term add queue clearer and more stable. | Do not change scoring, labels, or decision-safety rules. |
| `codex/capital-deployment-context` | Add manual/configured capital availability context. | No broker writes, no order preview, no trade execution. |
| `codex/best-add-if-blocked` | Explain the best add candidate when the top candidate is blocked. | Suggested amount must remain controlled by existing safety/allocation rules. |
| `codex/long-term-holding-health-v1` | Start long-term sell/trim review as holding-health context. | Do not create "sell now" instructions or short-side behavior. |
| `codex/capital-deployment-dashboard` | Surface long-term capital deployment context in review output. | Keep dashboard/report changes scoped and recommendation-only. |

## Recommended Wave 7 Sequencing

1. Define capital availability as review context.
2. Stabilize the long-term add queue around decision safety, target confidence, provider gaps, and allocation safety.
3. Add "best add if blocked" review context so blocked top candidates do not create ambiguity.
4. Introduce holding-health review only as a non-urgent long-term quality surface.
5. Integrate dashboard/report presentation only after the underlying context is stable.

## Provider And Data Follow-Ups

Wave 7 should be aware of the provider gap action plan at `reports/provider-gap-action-plan.md`.

Important follow-ups:

- Restore current-price coverage for `BBAI`, `ALAB`, and `PLAB`.
- Resolve or clearly label operating-company analyst target breadth gaps.
- Mark ETF CIK, companyfacts, official IR, and company analyst target gaps as expected/non-operating-company gaps.
- Add a TSM foreign-issuer/companyfacts-equivalent evidence plan.

These should be separate provider/data cleanup branches. They should not be bundled into a capital deployment behavior PR unless the user explicitly scopes that work.

## Validation Expectations

For docs-only Wave 7 planning work, run:

```bash
python3 scripts/check_quality.py
```

If Wave 7 changes analysis/report context, also run:

```bash
python3 scripts/run_analysis.py --no-persist --no-context
```

If Wave 7 changes report rendering, also run:

```bash
python3 scripts/render_report_context.py --fixture tests/fixtures/report_context.json --output-dir /private/tmp/stock-report-context-render
```

If Wave 7 changes daily workflow or report output, also run:

```bash
python3 scripts/run_daily.py --skip-refresh --show-gaps
```

## Handoff Summary

Wave 7 should improve the user-facing daily capital deployment decision without making the app more automated. The correct posture is clear, conservative, long-term, and review-first: show the best long-term add, explain blockers, account for available capital, preserve safety gates, and leave all trading decisions outside the app.
