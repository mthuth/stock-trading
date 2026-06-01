# Feedback Backlog

This backlog converts post-wave user validation feedback into scoped product backlog items. It is documentation-only and does not change application behavior.

## Status Values

- `proposed`: Captured but not yet scoped into implementation branches.
- `accepted`: Ready to break into implementation tasks.
- `in_progress`: Active branch or PR exists.
- `done`: Implemented and validated.
- `deferred`: Valid feedback, intentionally delayed.

## Wave 14 Dashboard Feedback Items

| ID | Title | Status | Wave | Primary lane | Source | Desired outcome |
| --- | --- | --- | --- | --- | --- | --- |
| `FB-001` | Clarify decision-gate blocked explanations | proposed | Wave 15 | UX / analysis explanation | Wave 14 dashboard validation | Blocked states use plain English and distinguish not-buy-action, missing verification, and data confidence issues. |
| `FB-002` | Reduce dashboard repetition and consolidate decision sections | proposed | Wave 15 | UX | Wave 14 dashboard validation | Top dashboard, daily decision review, recommendation action queue, and full action queue collapse into a clearer hierarchy with drilldowns. |
| `FB-003` | Show Top 5 ranked opportunities at the top of the dashboard | proposed | Wave 15 | UX / ranking presentation | Wave 14 dashboard validation | First screen shows the top 5 ranked opportunities rather than only one primary candidate. |
| `FB-004` | Distinguish core mega-cap candidates from higher-upside/speculative opportunities | proposed | Wave 15 | UX / queue design | Wave 14 dashboard validation | Top 5 presentation includes both core/mega-cap and higher-upside/speculative opportunities with clear lane labels. |
| `FB-005` | Track model/user disagreement when the model says Watch but the user manually buys | proposed | Wave 15 | Learning / feedback | Wave 14 dashboard validation | Manual user intent, such as buying MSFT despite a Watch output, is captured as learning context without changing official recommendations. |
| `FB-006` | Treat missing price/provider data as confidence/reliability blocker, not negative thesis | proposed | Wave 15 | UX / analysis explanation | Wave 14 dashboard validation | Missing data lowers confidence, blocks readiness/sizing, or queues maintenance without making high-quality companies feel bearish by default. |
| `FB-007` | Create data gap maintenance queue and Codex-ready docs/backlog work requests | proposed | Wave 15 | Data quality / workflow docs | Wave 14 dashboard validation | Data gaps can be converted into docs/backlog maintenance items with source, symbol, reason, priority, and suggested Codex prompt before GitHub issues are needed. |
| `FB-008` | Add score driver glossary/help text | proposed | Wave 15 | UX / analytics docs | Wave 14 dashboard validation | Dashboard explains base evidence, trends, targets, gaps, and final action in user-readable terms. |
| `FB-009` | Add "why now / why this / edge" explanation for mega-cap recommendations | proposed | Wave 15 | Analysis explanation / UX | Wave 14 dashboard validation | Obvious mega-cap recommendations explain timing, relative preference, and model edge rather than only naming familiar winners. |
| `FB-010` | Refine long-term and short-term queues | proposed | Wave 15 | UX / queue design | Wave 14 dashboard validation | Long-term and short-term queues feel curated, separated, and decision-ready instead of raw or unfinished. |
| `FB-011` | Add holdings/broker snapshot freshness display | proposed | Wave 15 | Broker read-only / UX | Wave 14 dashboard validation | Holdings sections clearly show source, timestamp, and freshness/staleness status. |
| `FB-012` | Improve research source activation/records visibility | proposed | Wave 15 | Data quality / UX | Wave 14 dashboard validation | Research source sections distinguish zero records, no records, not implemented, next actions, blocked sources, and maintenance needs. |
| `FB-013` | Formalize dictated feedback as primary post-wave validation input | proposed | Wave 15 | SDLC / docs | Wave 14 dashboard validation | Dictated ChatGPT feedback becomes an accepted post-wave validation input and feeds this backlog. |

## Wave 15 Candidate Grouping

Wave 15 should group these items into five implementation tracks:

1. Dashboard decision clarity: `FB-001`, `FB-002`, `FB-003`, `FB-004`, `FB-008`, `FB-009`, `FB-010`.
2. Model/user learning context: `FB-005`.
3. Data reliability and maintenance: `FB-006`, `FB-007`, `FB-012`.
4. Broker/holdings freshness: `FB-011`.
5. Feedback loop process: `FB-013`.

Wave 15 should not add new model families, broker behavior, new tactical features, automatic tuning, broker writes, order previews, or trading behavior.

## Wave 15 Dashboard Usability Iteration 1 Items

Current UI focus: Dashboard Usability Iteration 1 - Top Action Queue Drilldown.

This iteration should be narrow. It should make the first page easier to read by combining the useful Daily Decision Review detail with the useful Action Queue list shape. It should not introduce new model, data, broker, trading, scoring, target, allocation, provider, AI, or decision-safety behavior.

| ID | Title | Status | Wave | Primary lane | Source | Desired outcome |
| --- | --- | --- | --- | --- | --- | --- |
| `UI-001` | Combine Daily Decision Review with Action Queue into a Top 10 expandable section | proposed | Wave 15 | UX / dashboard hierarchy | Wave 15 dashboard readability follow-up | First page starts with a Top 10 Action Queue where each row can expand into Daily Decision Review-style detail. |
| `UI-002` | Add per-symbol expandable drilldowns for Score Drivers, Target Sources, and Provider Gaps | proposed | Wave 15 | UX / drilldown organization | Wave 15 dashboard readability follow-up | Each expanded Top 10 row shows Score Drivers, Target Source Drilldown, and Provider Gap Review for that symbol without forcing separate first-page sections. |
| `UI-003` | Move dashboard navigation near the top | proposed | Wave 15 | UX / navigation | Wave 15 dashboard readability follow-up | Dashboard navigation is available near the top so Matt can jump to sections without scanning to the bottom. |
| `UI-004` | Reduce top-page redundancy before doing broader redesign | proposed | Wave 15 | UX / simplification | Wave 15 dashboard readability follow-up | Daily Decision Review, Action Queue, and repeated decision surfaces are consolidated before any larger visual redesign. |
| `UI-005` | Treat remaining dashboard sections as future sub-tabs/drilldowns | proposed | Wave 16 candidate | UX / information architecture | Wave 15 dashboard readability follow-up | Valuable but secondary dashboard data is preserved for future tabs or drilldowns rather than competing with the first-page action queue. |

Iteration guidance:

- Make small UI changes until the first page is usable.
- Do not make many other page changes in the same branch.
- Preserve existing data value while moving detail into expandable rows, sub-tabs, or drilldowns.
- Keep recommendation-only and review-only wording visible.
