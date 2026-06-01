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
| `FB-003` | Treat missing price/provider data as confidence/reliability blocker, not negative thesis | proposed | Wave 15 | UX / analysis explanation | Wave 14 dashboard validation | Missing data lowers confidence, blocks sizing, or queues maintenance without making high-quality companies feel bearish by default. |
| `FB-004` | Create data gap maintenance queue and Codex-ready work requests | proposed | Wave 15 | Data quality / workflow docs | Wave 14 dashboard validation | Data gaps can be converted into actionable maintenance items with source, symbol, reason, priority, and suggested Codex prompt. |
| `FB-005` | Add score driver glossary/help text | proposed | Wave 15 | UX / analytics docs | Wave 14 dashboard validation | Dashboard explains base evidence, trends, targets, gaps, and final action in user-readable terms. |
| `FB-006` | Add "why now / why this / edge" explanation for mega-cap recommendations | proposed | Wave 15 | Analysis explanation / UX | Wave 14 dashboard validation | Obvious mega-cap recommendations explain timing, relative preference, and model edge rather than only naming familiar winners. |
| `FB-007` | Refine long-term and short-term queues | proposed | Wave 15 | UX / queue design | Wave 14 dashboard validation | Long-term and short-term queues feel curated, separated, and decision-ready instead of raw or unfinished. |
| `FB-008` | Add holdings/broker snapshot freshness display | proposed | Wave 15 | Broker read-only / UX | Wave 14 dashboard validation | Holdings sections clearly show source, timestamp, and freshness/staleness status. |
| `FB-009` | Improve research source activation/records visibility | proposed | Wave 15 | Data quality / UX | Wave 14 dashboard validation | Research source sections distinguish no records, not implemented, next actions, blocked sources, and maintenance needs. |
| `FB-010` | Formalize dictated feedback as primary post-wave validation input | proposed | Wave 15 | SDLC / docs | Wave 14 dashboard validation | Dictated ChatGPT feedback becomes an accepted post-wave validation input and feeds this backlog. |

## Wave 15 Candidate Grouping

Wave 15 should group these items into four implementation tracks:

1. Dashboard decision clarity: `FB-001`, `FB-002`, `FB-005`, `FB-006`, `FB-007`.
2. Data reliability and maintenance: `FB-003`, `FB-004`, `FB-009`.
3. Broker/holdings freshness: `FB-008`.
4. Feedback loop process: `FB-010`.

Wave 15 should not add new model families, broker behavior, new tactical features, automatic tuning, broker writes, order previews, or trading behavior.
