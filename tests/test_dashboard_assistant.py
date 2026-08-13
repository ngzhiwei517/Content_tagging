import json
import unittest
from pathlib import Path

import pandas as pd

from ugc_tagger.dashboard_assistant import (
    DASHBOARD_CHAT_SUGGESTIONS,
    build_dashboard_context,
    build_dashboard_prompt,
    dashboard_context_json,
    dashboard_context_signature,
    generate_dashboard_answer,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


class DashboardAssistantTests(unittest.TestCase):
    def sample_frame(self):
        return pd.DataFrame(
            [
                {
                    "Platform Display": "TikTok",
                    "Market Display": "SG",
                    "Track Display": "Example Track",
                    "Primary Creative Type": "Dance",
                    "Creator": "creator_one",
                    "KOL Size Display": "Micro",
                    "Followers": 12000,
                    "Views": 100000,
                    "Total Engagement": 10000,
                    "Narrative": "A choreographed group dance.",
                    "Date": "2026-08-01",
                    "Link": "https://example.test/secret-post",
                    "GEMINI_API_KEY": "must-not-leak",
                },
                {
                    "Platform Display": "Instagram Reels",
                    "Market Display": "MY",
                    "Track Display": "Example Track",
                    "Primary Creative Type": "Slice of Life",
                    "Creator": "creator_two",
                    "KOL Size Display": "Macro",
                    "Followers": 500000,
                    "Views": 50000,
                    "Total Engagement": 2500,
                    "Narrative": "A day-in-the-life montage.",
                    "Date": "2026-08-02",
                    "Link": "https://example.test/another-post",
                    "GEMINI_API_KEY": "must-not-leak",
                },
            ]
        )

    def test_context_is_compact_allowlisted_and_uses_filtered_rows(self):
        context = build_dashboard_context(self.sample_frame().iloc[:1])
        self.assertEqual(1, context["totals"]["posts"])
        self.assertEqual(100000, context["totals"]["total_views"])
        self.assertEqual(10, context["totals"]["average_engagement_rate_percent"])
        serialized = json.dumps(context)
        self.assertIn("creator_one", serialized)
        self.assertNotIn("creator_two", serialized)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("secret-post", serialized)

    def test_context_keeps_missing_metrics_missing_instead_of_false_zero(self):
        frame = self.sample_frame().iloc[:1].copy()
        frame["Views"] = pd.NA
        context = build_dashboard_context(frame)
        self.assertIsNone(context["totals"]["total_views"])
        self.assertIsNone(context["totals"]["average_engagement_rate_percent"])
        self.assertEqual(1, context["totals"]["posts_without_views"])

    def test_prompt_forbids_external_knowledge_and_labels_recommendations(self):
        prompt = build_dashboard_prompt(
            "Suggest a campaign",
            dashboard_context_json(self.sample_frame()),
            [{"role": "user", "content": "What stands out?"}],
        )
        self.assertIn("Use only DASHBOARD_DATA", prompt)
        self.assertIn("Do not use the web, external knowledge, saved memory", prompt)
        self.assertIn("recommendations or tests", prompt)
        self.assertIn("Suggest a campaign", prompt)

    def test_generation_can_be_validated_without_live_gemini_credit(self):
        captured = {}

        def fake_request(model, prompt):
            captured["model"] = model
            captured["prompt"] = prompt
            return "Recommendation: test Dance against Slice of Life."

        answer = generate_dashboard_answer(
            api_key="not-used",
            model="fake-model",
            question="What should we test?",
            context_json=dashboard_context_json(self.sample_frame()),
            request_fn=fake_request,
        )
        self.assertIn("Recommendation", answer)
        self.assertEqual("fake-model", captured["model"])
        self.assertIn("What should we test?", captured["prompt"])

    def test_context_signature_changes_when_dashboard_changes(self):
        full = dashboard_context_json(self.sample_frame())
        filtered = dashboard_context_json(self.sample_frame().iloc[:1])
        self.assertNotEqual(
            dashboard_context_signature(full), dashboard_context_signature(filtered)
        )

    def test_app_renders_suggestions_and_keeps_chat_out_of_checkpoints(self):
        self.assertGreaterEqual(len(DASHBOARD_CHAT_SUGGESTIONS), 4)
        self.assertIn("render_dashboard_assistant_v68_72(filtered)", APP_SOURCE)
        self.assertIn("st.chat_input(", APP_SOURCE)
        self.assertIn("st.chat_message(", APP_SOURCE)
        checkpoint_block = APP_SOURCE.split(
            "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15 = (", 1
        )[1].split(")", 1)[0]
        self.assertNotIn("dashboard_chat_messages_v68_72", checkpoint_block)


if __name__ == "__main__":
    unittest.main()
