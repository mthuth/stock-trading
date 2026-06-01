# Roadmap Decision Log

This log records product and roadmap decisions that should guide future branches. It is documentation-only and does not change application behavior.

## Decisions

### RD-001 - First Screen Top 5 Question

Decision: The first screen must answer, "What are the top 5 ranked opportunities today?"

Rationale: The dashboard can include audits, learning loops, queues, and maintenance details, but the first scan must show the best ranked opportunities without forcing the user to reconcile repeated sections.

Implications:

- The top dashboard area should prioritize the top 5 ranked opportunities, decision-safety state, confidence, sizing/capital context, and why the user should review each today.
- Detailed queues and supporting sections should be drilldowns, not parallel repeated first-screen answers.

### RD-002 - Top 5 Opportunity Mix

Decision: The top 5 should include both core mega-cap candidates and higher-upside opportunities.

Rationale: A top list made only of obvious mega-cap names can feel stale or unsurprising. A useful daily decision surface should show the best core candidates while also surfacing credible higher-upside/speculative opportunities with their risks and readiness state.

Implications:

- Top opportunities should be labeled by lane, such as core/mega-cap, long-term core, speculative/watchlist, tactical review, or data-blocked opportunity.
- Higher-upside/speculative opportunities should remain gated and recommendation-only; visibility does not mean buy-readiness.
- The top 5 should explain why each opportunity appears now.

### RD-003 - Missing Data Meaning

Decision: Missing price/provider data should block confidence, sizing, or verification, but it should not imply bearishness by itself.

Rationale: A strong company such as Microsoft should not feel negative simply because current price, target source, or provider evidence is missing. Missing data is a reliability problem unless actual evidence weakens the thesis.

Implications:

- Missing data language should use reliability/confidence wording.
- Missing data can block buy readiness or suggested amount.
- Missing data should not be framed as a negative thesis unless evidence supports that interpretation.

### RD-004 - Dashboard Hierarchy Over Repetition

Decision: Repeated sections should be collapsed into hierarchy and drilldowns.

Rationale: Top dashboard, daily decision review, recommendation action queue, and full action queue currently overlap. Repetition makes the product feel less decisive.

Implications:

- Use one primary decision surface.
- Use supporting queues for explanation, alternatives, and audit.
- Preserve detail without forcing the user to reconcile multiple similar sections.

### RD-005 - Model/User Disagreement Is Learning Data

Decision: Model/user disagreement is valuable learning data and should be tracked.

Rationale: If the model says Watch but Matt manually buys, the disagreement is not necessarily an error. It is a signal about user conviction, model caution, missing evidence, or unclear explanation.

Implications:

- The app should capture model/user disagreement as review-only learning context.
- User intent should not silently change official recommendations, scores, targets, decision safety, allocation, or source weights.
- Decision briefs should explain model/user disagreement plainly, especially for familiar names like Microsoft.

### RD-006 - Data Maintenance Is Product Workflow

Decision: Data maintenance is part of the product workflow.

Rationale: Provider gaps, not-implemented sources, missing records, and ingestion next actions are useful only if they can become maintainable work requests.

Implications:

- Data gaps should map to maintenance queue items where possible.
- Maintenance items should be Codex-ready with source, symbol, failure/missing reason, priority, and expected output.
- Daily data maintenance should be visible but should not crowd out the daily buy/add decision.

### RD-007 - Data Maintenance Starts As Docs/Backlog

Decision: Data maintenance starts as docs/backlog items before GitHub issues.

Rationale: The app is still learning which gaps matter every day. Capturing maintenance work in docs/backlog first keeps the workflow lightweight and reviewable before creating issue-management overhead.

Implications:

- Data gap maintenance should first produce Codex-ready backlog entries.
- GitHub issues can be created later when an item is recurring, high priority, or ready for separate tracking.
- Maintenance backlog entries should preserve source, symbol, current status, and recommended next action.

### RD-008 - Dictated Feedback Is Accepted SDLC Input

Decision: Dictated post-wave feedback through ChatGPT is an accepted SDLC input.

Rationale: Matt found dictated feedback more useful than the dashboard feedback tool for post-wave validation. The SDLC loop should support the feedback channel that captures the richest product signal.

Implications:

- Post-wave dictated feedback should be captured in `docs/POST_WAVE_VALIDATION_LOG.md`.
- Backlog items should be added to `docs/FEEDBACK_BACKLOG.md`.
- Roadmap-impacting decisions should be added to this decision log.
- Dashboard feedback tooling can remain supplemental rather than primary for post-wave validation.

### RD-009 - Top Action Queue Drilldown Is The Next Dashboard Iteration

Decision: The next dashboard UI iteration should focus narrowly on a top-of-page Top 10 Action Queue with expandable per-symbol drilldowns.

Rationale: Matt found the Daily Decision Review useful and the Action Queue list shape directionally right. The product should combine those strengths before making broader dashboard changes. The first page should become usable through small, feedback-driven iterations rather than a large redesign.

Implications:

- Combine Daily Decision Review-style detail with the Action Queue list.
- Place a Top 10 Action Queue near the top of the dashboard.
- Each Top 10 item should expand to show Daily Decision Review-style detail, Score Drivers, Target Source Drilldown, and Provider Gap Review.
- Move dashboard navigation currently near the bottom toward the top.
- Reduce first-page redundancy before adding new surfaces.
- Treat remaining dashboard sections as candidates for future sub-tabs or drilldowns.
- Do not add new model, data, broker, trading, scoring, target, allocation, provider, AI, or decision-safety behavior in this UI iteration.
