import json
import unittest
from pathlib import Path

from final_update2_adapter import (
    MARKETING_EXPORT_COLUMNS,
    QA_AUDIT_COLUMNS,
    _to_ui_row,
    review_audit_update,
)


class LabelAuditTests(unittest.TestCase):
    def test_automated_row_preserves_original_and_final_labels(self):
        row = _to_ui_row(
            {"Link": "https://www.tiktok.com/@tester/video/123"},
            {
                "Creative Type": "Fashion, Dance",
                "tier_used": "tier2b_9frames_adaptive",
                "validation_status": "review",
            },
            {},
        )
        self.assertEqual(row["App Version"], "v68.15")
        self.assertEqual(row["Original AI Labels"], "Fashion, Dance")
        self.assertEqual(row["Final Labels"], "Fashion, Dance")
        self.assertFalse(row["Human Reviewed"])
        self.assertFalse(row["Human Edited"])
        history = json.loads(row["Label History"])
        self.assertEqual(history[0]["stage"], "automated")
        self.assertEqual(history[0]["labels"], ["Fashion", "Dance"])

    def test_verifier_change_preserves_pre_verifier_labels_in_qa_history(self):
        row = _to_ui_row(
            {"Link": "https://www.tiktok.com/@tester/video/456"},
            {
                "Creative Type": "Fashion",
                "tier_used": "tier2a_3frames",
                "validation_status": "pass",
                "verifier_status": "changed",
                "verifier_input_labels": "Fashion, Dance",
                "verifier_output_labels": "Fashion",
                "verifier_confidence": 0.96,
                "verifier_reason": "No choreography is described.",
                "verifier_evidence": "The creator only poses in an outfit.",
                "verifier_triggers": "Secondary Dance lacks evidence",
            },
            {},
        )
        self.assertEqual(row["Original AI Labels"], "Fashion")
        self.assertEqual(row["Final Labels"], "Fashion")
        self.assertEqual(row["Verifier Input Labels"], "Fashion, Dance")
        self.assertEqual(row["Verifier Status"], "changed")
        self.assertFalse(row["Human Reviewed"])
        history = json.loads(row["Label History"])
        self.assertEqual(history[0]["stage"], "automated_pre_verifier")
        self.assertEqual(history[0]["labels"], ["Fashion", "Dance"])
        self.assertEqual(history[1]["stage"], "targeted_evidence_verifier")
        self.assertEqual(history[1]["labels"], ["Fashion"])
        self.assertEqual(history[1]["action"], "CHANGED")

    def test_human_edit_after_verifier_keeps_three_stage_history(self):
        row = _to_ui_row(
            {"Link": "https://www.tiktok.com/@tester/video/789"},
            {
                "Creative Type": "Fashion",
                "tier_used": "tier2a_3frames",
                "validation_status": "review",
                "verifier_status": "changed",
                "verifier_input_labels": "Fashion, Dance",
                "verifier_output_labels": "Fashion",
                "verifier_confidence": 0.92,
                "verifier_reason": "No choreography is described.",
            },
            {},
        )
        update = review_audit_update(
            row["Original AI Labels"],
            "Beauty",
            row["Label History"],
            action="KEEP",
            note="Reviewer selected Beauty",
            recorded_at="2026-07-13T00:00:00+00:00",
        )
        self.assertEqual(update["Original AI Labels"], "Fashion")
        self.assertEqual(update["Final Labels"], "Beauty")
        history = json.loads(update["Label History"])
        self.assertEqual(
            [entry["stage"] for entry in history],
            ["automated_pre_verifier", "targeted_evidence_verifier", "human_review"],
        )

    def test_malformed_verifier_confidence_is_safely_coerced(self):
        row = _to_ui_row(
            {"Link": "https://www.tiktok.com/@tester/video/999"},
            {
                "Creative Type": "Comedy",
                "verifier_status": "error",
                "verifier_confidence": "N/A",
            },
            {},
        )
        self.assertEqual(row["Verifier Confidence"], 0.0)

    def test_human_edit_preserves_original_and_updates_final(self):
        update = review_audit_update(
            "Fashion, Dance",
            "Fashion",
            json.dumps([{"stage": "automated", "labels": ["Fashion", "Dance"]}]),
            action="KEEP",
            note="Removed unsupported Dance",
            recorded_at="2026-07-12T00:00:00+00:00",
        )
        self.assertEqual(update["Original AI Labels"], "Fashion, Dance")
        self.assertEqual(update["Final Labels"], "Fashion")
        self.assertTrue(update["Human Reviewed"])
        self.assertTrue(update["Human Edited"])
        history = json.loads(update["Label History"])
        self.assertEqual(history[-1]["action"], "KEEP")
        self.assertEqual(history[-1]["labels"], ["Fashion"])

    def test_human_confirmation_is_reviewed_but_not_edited(self):
        update = review_audit_update(
            "Beauty",
            "Beauty",
            "",
            action="KEEP",
            recorded_at="2026-07-12T00:00:00+00:00",
        )
        self.assertTrue(update["Human Reviewed"])
        self.assertFalse(update["Human Edited"])

    def test_remove_event_keeps_labels_and_records_action(self):
        update = review_audit_update(
            "Comedy",
            "Comedy",
            "",
            action="REMOVE",
            note="Wrong link",
            recorded_at="2026-07-12T00:00:00+00:00",
        )
        self.assertEqual(update["Final Labels"], "Comedy")
        history = json.loads(update["Label History"])
        self.assertEqual(history[-1]["action"], "REMOVE")
        self.assertEqual(history[-1]["validation_status"], "removed")

    def test_audit_fields_stay_out_of_marketing_export(self):
        for column in QA_AUDIT_COLUMNS:
            self.assertNotIn(column, MARKETING_EXPORT_COLUMNS)

    def test_review_and_qa_export_use_the_audit_contract(self):
        app_source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
        self.assertIn("final_update2_review_audit_update", app_source)
        self.assertIn('audit_fields["Final Labels"]', app_source)
        self.assertIn('"All Rows": qa_df', app_source)
        self.assertIn("MARKETING_EXPORT_COLUMNS", app_source)


if __name__ == "__main__":
    unittest.main()
