# Roadmap Decision Log

This log records product and roadmap decisions that should guide future branches. It is documentation-only and does not change application behavior.

## Decisions

### RD-001 - First Screen Decision Question

Decision: The first screen must answer, "What should I buy/add today?"

Rationale: The dashboard can include audits, learning loops, queues, and maintenance details, but the first scan must serve the primary daily decision before secondary review surfaces.

Implications:

- The top dashboard area should prioritize the best buy/add answer, decision-safety state, confidence, sizing/capital context, and why the user should review it today.
- Detailed queues and supporting sections should be drilldowns, not parallel repeated first-screen answers.

### RD-002 - Missing Data Meaning

Decision: Missing price/provider data should block confidence, sizing, or verification, but it should not imply bearishness by itself.

Rationale: A strong company such as Microsoft should not feel negative simply because current price, target source, or provider evidence is missing. Missing data is a reliability problem unless actual evidence weakens the thesis.

Implications:

- Missing data language should use reliability/confidence wording.
- Missing data can block buy readiness or suggested amount.
- Missing data should not be framed as a negative thesis unless evidence supports that interpretation.

### RD-003 - Dashboard Hierarchy Over Repetition

Decision: Repeated sections should be collapsed into hierarchy and drilldowns.

Rationale: Top dashboard, daily decision review, recommendation action queue, and full action queue currently overlap. Repetition makes the product feel less decisive.

Implications:

- Use one primary decision surface.
- Use supporting queues for explanation, alternatives, and audit.
- Preserve detail without forcing the user to reconcile multiple similar sections.

### RD-004 - Data Maintenance Is Product Workflow

Decision: Data maintenance is part of the product workflow.

Rationale: Provider gaps, not-implemented sources, missing records, and ingestion next actions are useful only if they can become maintainable work requests.

Implications:

- Data gaps should map to maintenance queue items where possible.
- Maintenance items should be Codex-ready with source, symbol, failure/missing reason, priority, and expected output.
- Daily data maintenance should be visible but should not crowd out the daily buy/add decision.

### RD-005 - Dictated Feedback Is Accepted SDLC Input

Decision: Dictated post-wave feedback through ChatGPT is an accepted SDLC input.

Rationale: Matt found dictated feedback more useful than the dashboard feedback tool for post-wave validation. The SDLC loop should support the feedback channel that captures the richest product signal.

Implications:

- Post-wave dictated feedback should be captured in `docs/POST_WAVE_VALIDATION_LOG.md`.
- Backlog items should be added to `docs/FEEDBACK_BACKLOG.md`.
- Roadmap-impacting decisions should be added to this decision log.
- Dashboard feedback tooling can remain supplemental rather than primary for post-wave validation.
