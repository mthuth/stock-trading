#!/usr/bin/env python3
"""AI brief review workflow tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.serve_dashboard import handle_ai_brief_review_payload
from stock_trading.ai_brief_review import (
    apply_review_metadata,
    brief_id_for,
    load_ai_brief_reviews,
    normalize_ai_brief_review,
    record_ai_brief_review,
)
from stock_trading.ai_briefs import build_ai_insight_briefs, render_ai_briefs_markdown
from tests.test_ai_insight_briefs import brief_context


class AiBriefReviewTests(unittest.TestCase):
    def test_draft_brief_is_not_trusted_research(self) -> None:
        result = build_ai_insight_briefs(brief_context())
        review = result["briefs"][0]["review"]

        self.assertEqual(review["status"], "draft")
        self.assertEqual(review["reason"], "needs_more_evidence")
        self.assertFalse(review["trusted_research"])
        self.assertTrue(review["review_required"])

    def test_accepted_brief_is_reviewed_user_approved_context(self) -> None:
        brief_id = brief_id_for("MSFT", "2026-05-29", 1)
        result = build_ai_insight_briefs(
            brief_context(),
            reviews=[
                normalize_ai_brief_review(
                    {
                        "symbol": "MSFT",
                        "report_date": "2026-05-29",
                        "brief_id": brief_id,
                        "status": "accepted",
                        "reason": "useful_insight",
                        "notes": "Useful synthesis with clear evidence trail.",
                    },
                    created_at="2026-05-31T09:00:00+00:00",
                )
            ],
        )
        review = result["briefs"][0]["review"]

        self.assertEqual(review["status"], "accepted")
        self.assertEqual(review["reason"], "useful_insight")
        self.assertTrue(review["trusted_research"])
        self.assertEqual(review["display_label"], "Reviewed user-approved context")

    def test_rejected_brief_is_not_presented_as_trusted(self) -> None:
        brief = {
            "symbol": "MSFT",
            "report_date": "2026-05-29",
            "brief_id": brief_id_for("MSFT", "2026-05-29", 1),
            "artifact_ref": "ai-insight-briefs-2026-05-29.json",
        }
        annotated = apply_review_metadata(
            [brief],
            [
                normalize_ai_brief_review(
                    {
                        "symbol": "MSFT",
                        "report_date": "2026-05-29",
                        "brief_id": brief["brief_id"],
                        "status": "rejected",
                        "reason": "unsupported_claim",
                        "notes": "Claim was not supported by audit refs.",
                    },
                    created_at="2026-05-31T09:05:00+00:00",
                )
            ],
        )

        review = annotated[0]["review"]
        self.assertEqual(review["status"], "rejected")
        self.assertEqual(review["reason"], "unsupported_claim")
        self.assertFalse(review["trusted_research"])
        self.assertIn("not trusted research", review["display_label"])

    def test_flagged_brief_records_hallucination_risk_reason(self) -> None:
        review = normalize_ai_brief_review(
            {
                "symbol": "MSFT",
                "report_date": "2026-05-29",
                "artifact_ref": "ai-insight-briefs-2026-05-29.json",
                "status": "flagged",
                "reason": "hallucination_risk",
                "notes": "Potential unsupported synthesis language.",
            },
            created_at="2026-05-31T09:10:00+00:00",
        )

        self.assertEqual(review["status"], "flagged")
        self.assertEqual(review["reason"], "hallucination_risk")
        self.assertEqual(review["symbol"], "MSFT")
        self.assertIn("2026-05-29", review["brief_id"])

    def test_review_records_are_file_backed_without_schema_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ai_brief_reviews.jsonl"
            saved = record_ai_brief_review(
                {
                    "symbol": "MSFT",
                    "report_date": "2026-05-29",
                    "brief_id": brief_id_for("MSFT", "2026-05-29", 1),
                    "status": "reviewed",
                    "reason": "useful_insight",
                    "notes": "Reviewed and source-backed.",
                },
                path=path,
            )
            records = load_ai_brief_reviews(path=path)

        self.assertEqual(saved["message"], "Recorded AI brief review for MSFT")
        self.assertEqual(records[0]["status"], "reviewed")
        self.assertTrue(records[0]["trusted_research"])

    def test_reviewed_brief_display_metadata_is_rendered(self) -> None:
        result = build_ai_insight_briefs(
            brief_context(),
            reviews=[
                normalize_ai_brief_review(
                    {
                        "symbol": "MSFT",
                        "report_date": "2026-05-29",
                        "brief_id": brief_id_for("MSFT", "2026-05-29", 1),
                        "status": "reviewed",
                        "reason": "useful_insight",
                        "notes": "Reviewed for traceability.",
                    },
                    created_at="2026-05-31T09:20:00+00:00",
                )
            ],
        )
        markdown = render_ai_briefs_markdown(result)

        self.assertIn("Review status: Reviewed context", markdown)
        self.assertIn("Review reason: useful_insight", markdown)

    def test_server_endpoint_records_ai_brief_review_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ai_brief_reviews.jsonl"
            with patch("stock_trading.ai_brief_review.DEFAULT_REVIEW_PATH", path):
                payload = handle_ai_brief_review_payload(
                    {
                        "symbol": "MSFT",
                        "report_date": "2026-05-29",
                        "brief_id": brief_id_for("MSFT", "2026-05-29", 1),
                        "status": "accepted",
                        "reason": "useful_insight",
                    }
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["review"]["status"], "accepted")
        self.assertEqual(payload["review"]["reason"], "useful_insight")
        self.assertEqual(payload["recent"][0]["symbol"], "MSFT")


if __name__ == "__main__":
    unittest.main()
