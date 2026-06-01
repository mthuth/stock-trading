#!/usr/bin/env python3
"""Tests for queue hierarchy and de-duplication metadata."""

from __future__ import annotations

import copy
import unittest

from stock_trading.queue_refinement import refine_queue_context
from stock_trading.reporting.renderers import render_dashboard_html, render_markdown


def sample_context() -> dict[str, object]:
    return {
        "metadata": {"report_date": "2026-06-01", "generated_at": "2026-06-01T08:00:00"},
        "summary": {"top_symbol": "MSFT", "top_company": "Microsoft", "top_action": "Watch", "top_score": 81.0},
        "reliability": {"mode": "Fixture", "price_counts": {"fresh": 1, "missing": 0}},
        "source_health": {"summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0}},
        "queues": {
            "top5_opportunities": {
                "headers": ["Rank", "Symbol", "Action", "Score", "Lane", "Why"],
                "rows": [
                    [1, "MSFT", "Watch", "81.0", "Core mega-cap", "Core compounder, but gate is cautious."],
                    [2, "SOUN", "Watch", "77.0", "Speculative AI", "Higher-upside watchlist idea."],
                ],
            },
            "action_queue": {
                "headers": ["Rank", "Symbol", "Action", "Score", "Status", "Type", "Rationale"],
                "rows": [
                    [1, "MSFT", "Watch", "81.0", "Verification open", "Long term", "Same primary context."],
                    [2, "NVDA", "Add", "79.0", "Ready", "Long term", "Distinct audit row."],
                ],
            },
            "long_term": {
                "headers": ["Rank", "Symbol", "Action", "Score", "Why"],
                "rows": [[1, "MSFT", "Watch", "81.0", "Capital deployment context for the same symbol."]],
            },
            "short_term": {
                "headers": ["Rank", "Symbol", "Action", "Score", "Why"],
                "rows": [[1, "NVDA", "Watch", "70.0", "Tactical setup review only."]],
            },
            "speculative": {
                "headers": ["Rank", "Symbol", "Action", "Score", "Why"],
                "rows": [[1, "SOUN", "Watch", "77.0", "Watchlist-first speculative review."]],
            },
            "data_gaps": {
                "headers": ["Rank", "Symbol", "Data Gap", "Next Action"],
                "rows": [[1, "MSFT", "Analyst target stale", "Refresh reviewed target source."]],
            },
            "full_universe": {
                "headers": ["Rank", "Symbol", "Action", "Score"],
                "rows": [[1, "MSFT", "Watch", "81.0"], [2, "SOUN", "Watch", "77.0"]],
            },
        },
    }


class QueueRefinementTests(unittest.TestCase):
    def test_queue_sections_receive_purpose_metadata(self) -> None:
        refined = refine_queue_context(sample_context())
        queues = refined["queues"]

        self.assertEqual(queues["top5_opportunities"]["primary_or_drilldown"], "primary")
        self.assertIn("primary first-screen summary", queues["top5_opportunities"]["queue_purpose"])
        self.assertIn("capital deployment", queues["long_term"]["queue_purpose"])
        self.assertIn("review-only short-term", queues["short_term"]["queue_purpose"])
        self.assertIn("watchlist-first", queues["speculative"]["queue_purpose"])
        self.assertEqual(queues["full_universe"]["primary_or_drilldown"], "drilldown")

    def test_duplicate_symbol_in_drilldown_is_referenced_not_repeated(self) -> None:
        refined = refine_queue_context(sample_context())
        metadata = refined["queues"]["action_queue"]["row_metadata"][0]

        self.assertEqual(metadata["symbol"], "MSFT")
        self.assertEqual(metadata["display_mode"], "reference")
        self.assertEqual(metadata["duplicate_of"], "top5_opportunities:MSFT")
        self.assertEqual(metadata["related_primary_section"], "top5_opportunities")

    def test_top5_queue_is_synthesized_from_ranked_rows_when_missing(self) -> None:
        context = sample_context()
        del context["queues"]["top5_opportunities"]

        refined = refine_queue_context(context)

        self.assertIn("top5_opportunities", refined["queues"])
        self.assertEqual(refined["queues"]["top5_opportunities"]["primary_or_drilldown"], "primary")
        self.assertEqual(refined["queues"]["top5_opportunities"]["rows"], context["queues"]["action_queue"]["rows"][:5])
        self.assertEqual(refined["queues"]["action_queue"]["row_metadata"][0]["display_mode"], "reference")

    def test_same_symbol_allowed_when_queue_context_differs(self) -> None:
        refined = refine_queue_context(sample_context())
        metadata = refined["queues"]["long_term"]["row_metadata"][0]

        self.assertEqual(metadata["symbol"], "MSFT")
        self.assertEqual(metadata["display_mode"], "detail")
        self.assertEqual(metadata["duplicate_of"], "")
        self.assertIn("capital", metadata["queue_purpose"].lower())

    def test_no_recommendation_mutation(self) -> None:
        context = sample_context()
        before = copy.deepcopy(context)

        refined = refine_queue_context(context)

        self.assertEqual(context, before)
        self.assertEqual(refined["queues"]["top5_opportunities"]["rows"], before["queues"]["top5_opportunities"]["rows"])
        self.assertEqual(refined["queues"]["action_queue"]["rows"], before["queues"]["action_queue"]["rows"])

    def test_dashboard_renders_reference_card_and_preserves_full_audit(self) -> None:
        dashboard = render_dashboard_html(sample_context())

        self.assertIn("Top 5 Opportunities", dashboard)
        self.assertIn("Already covered in Top 5 Opportunities", dashboard)
        self.assertIn("Full Action Queue Audit", dashboard)
        self.assertIn("Same primary context.", dashboard)
        self.assertIn("Full Audit Queue", dashboard)
        self.assertIn("Long-Term Add Queue", dashboard)
        self.assertIn("Tactical Review Queue", dashboard)

    def test_markdown_report_includes_top5_summary(self) -> None:
        markdown = render_markdown(sample_context())

        self.assertIn("## Top 5 Opportunities", markdown)
        self.assertIn("Answers the daily question before detailed queue drilldowns.", markdown)


if __name__ == "__main__":
    unittest.main()
