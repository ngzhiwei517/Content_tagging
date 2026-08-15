import json
import unittest
import warnings
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from ugc_tagger.dashboard_assistant import (
    DASHBOARD_CHAT_SUGGESTIONS,
    PAGE_CHAT_SUGGESTIONS,
    build_dashboard_context,
    build_dashboard_prompt,
    build_page_assistant_prompt,
    build_taggy_companion_url,
    chat_history_markdown,
    dashboard_context_json,
    dashboard_context_signature,
    generate_dashboard_answer,
    generate_page_assistant_answer,
    load_taggy_knowledge,
    page_help_answer,
    retrieve_taggy_knowledge,
    taggy_knowledge_answer,
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

    def test_app_reloads_stale_dashboard_assistant_api(self):
        self.assertIn("import ugc_tagger.dashboard_assistant as _dashboard_assistant", APP_SOURCE)
        self.assertIn("importlib.reload(_dashboard_assistant)", APP_SOURCE)
        self.assertIn('"PAGE_CHAT_SUGGESTIONS"', APP_SOURCE)

    def test_taggy_prefers_the_current_managed_gemini_key(self):
        taggy_start = APP_SOURCE.index("def _render_taggy_chat_content_v68_87")
        taggy_end = APP_SOURCE.index("@st.fragment", taggy_start)
        taggy_source = APP_SOURCE[taggy_start:taggy_end]
        managed_key = '_managed_api_secret_v68_43("GEMINI_API_KEY")'
        session_key = 'st.session_state.get("gemini_key")'

        self.assertIn(managed_key, taggy_source)
        self.assertIn(session_key, taggy_source)
        self.assertLess(taggy_source.index(managed_key), taggy_source.index(session_key))

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

    def test_mixed_uploaded_dates_do_not_warn_on_streamlit_reruns(self):
        frame = self.sample_frame().copy()
        frame["Date"] = ["2026-08-01", "13/08/2026"]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            context = build_dashboard_context(frame)

        self.assertEqual("2026-08-01", context["totals"]["date_range"]["start"])
        self.assertEqual("2026-08-13", context["totals"]["date_range"]["end"])
        self.assertFalse(
            any("Could not infer format" in str(item.message) for item in caught)
        )

    def test_prompt_forbids_external_knowledge_and_labels_recommendations(self):
        prompt = build_dashboard_prompt(
            "Suggest a campaign",
            dashboard_context_json(self.sample_frame()),
            [{"role": "user", "content": "What stands out?"}],
        )
        self.assertIn("Use only DASHBOARD_DATA", prompt)
        self.assertIn("Do not use the web, saved memory, or unstated facts", prompt)
        self.assertIn("general, timeless marketing knowledge", prompt)
        self.assertIn("recommendations or tests", prompt)
        self.assertIn("Suggest a campaign", prompt)
        self.assertIn("AI suggestions", prompt)
        self.assertIn("below 300 words", prompt)
        self.assertIn("short Markdown headings and bullet points", prompt)

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

    def test_page_help_is_available_locally_on_each_workflow_step(self):
        for step in range(2, 7):
            self.assertTrue(PAGE_CHAT_SUGGESTIONS[step])
            answer = page_help_answer(step, "How do I use this page?")
            self.assertTrue(answer)
        self.assertIn("CSV/XLSX", page_help_answer(2, "How do I use this page?"))
        self.assertIn("Keep", page_help_answer(5, "Please guide me on this page"))

    def test_approved_knowledge_base_is_local_and_substantial(self):
        entries = load_taggy_knowledge()
        self.assertGreaterEqual(len(entries), 30)
        self.assertTrue(all(entry["category"] for entry in entries))
        self.assertTrue(all(entry["questions"] for entry in entries))
        serialized = json.dumps(entries)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("paste-your-key", serialized)

    def test_project_knowledge_covers_product_workflow_and_limitations(self):
        entry_ids = {entry["id"] for entry in load_taggy_knowledge()}
        expected = {
            "tool_purpose",
            "complements_existing_tools",
            "required_inputs",
            "metrics_only",
            "scraping_sources",
            "tagging_accuracy",
            "creative_narrative_drama",
            "engagement_calculation",
            "creator_limits",
            "resume_after_closing",
            "export_results",
            "deploy_and_sync",
            "taggy_behavior",
        }
        self.assertTrue(expected.issubset(entry_ids))

    def test_project_questions_use_the_expected_trusted_entries(self):
        cases = [
            (1, "How is this different from MelodyIQ and CreatorCore?", "complements_existing_tools"),
            (2, "What fields are required and do I need artist?", "required_inputs"),
            (2, "What if I do not know the market?", "market_handling"),
            (4, "Why is drama tagging slower than normal posts?", "tagging_speed"),
            (6, "How is total engagement and engagement rate calculated?", "engagement_calculation"),
            (6, "How many creators and profile posts can I check?", "creator_limits"),
            (1, "Does Taggy use Gemini and remember our chat?", "taggy_behavior"),
            (2, "Why does a short TikTok link fail?", "link_compatibility"),
        ]
        for step, question, expected_id in cases:
            with self.subTest(question=question):
                matches = retrieve_taggy_knowledge(question, step=step, limit=1)
                self.assertTrue(matches)
                self.assertEqual(expected_id, matches[0]["id"])

    def test_close_and_reopen_question_uses_trusted_recovery_answer(self):
        answer = page_help_answer(
            4,
            "Can I close the website and reopen it again tomorrow?",
        )
        self.assertIn("current protected chunk has saved", answer)
        self.assertIn("bookmark the private recovery link", answer)
        self.assertIn("reopen that exact link", answer)

    def test_csv_template_request_does_not_return_generic_upload_help(self):
        question = "can u create a csv with the format i want i mean the col that i need"
        matches = retrieve_taggy_knowledge(question, step=2, limit=1)
        self.assertTrue(matches)
        self.assertEqual("csv_template", matches[0]["id"])

        answer = page_help_answer(2, question)
        self.assertIn("`Link,Market,Track,Artist`", answer)
        self.assertIn("exact columns and order", answer)
        self.assertNotIn("paste one TikTok or Instagram post link per line", answer)

    def test_retrieval_ranks_metric_definition_for_summary_question(self):
        matches = retrieve_taggy_knowledge(
            "What is the difference between batch average engagement and Avg ER 3m?",
            step=6,
        )
        self.assertTrue(matches)
        self.assertEqual("batch_profile_metrics", matches[0]["id"])
        self.assertIn("current filtered batch", matches[0]["answer"])

    def test_api_key_help_does_not_require_gemini(self):
        answer = taggy_knowledge_answer(
            1,
            "Where should I add the Gemini API key and Apify token?",
        )
        self.assertIn("Settings", answer)
        self.assertIn("Secrets", answer)
        self.assertIn("Never paste credentials", answer)

    def test_page_prompt_is_grounded_in_current_workflow_step(self):
        prompt = build_page_assistant_prompt(
            step=2,
            question="How should I upload my data?",
            context_json=dashboard_context_json(pd.DataFrame()),
        )
        self.assertIn("CURRENT_PAGE: Add posts", prompt)
        self.assertIn("Never ask for, repeat, or expose API keys", prompt)
        self.assertIn("Use only DASHBOARD_DATA", prompt)

    def test_page_prompt_includes_retrieved_trusted_help(self):
        prompt = build_page_assistant_prompt(
            step=4,
            question="Can I close the app and continue tomorrow?",
            context_json=dashboard_context_json(pd.DataFrame()),
        )
        self.assertIn("TRUSTED_HELP_KNOWLEDGE", prompt)
        self.assertIn("bookmark the private recovery link", prompt)
        self.assertIn("source of truth for app behavior", prompt)

    def test_page_generation_can_be_validated_without_live_credit(self):
        captured = {}

        def fake_request(model, prompt):
            captured["prompt"] = prompt
            return "Upload a file or paste one post link per line."

        answer = generate_page_assistant_answer(
            api_key="not-used",
            model="fake-model",
            step=2,
            question="What should I do?",
            context_json=dashboard_context_json(pd.DataFrame()),
            request_fn=fake_request,
        )
        self.assertIn("Upload", answer)
        self.assertIn("CURRENT_PAGE: Add posts", captured["prompt"])

    def test_page_generation_falls_back_to_trusted_help_when_gemini_fails(self):
        def failed_request(_model, _prompt):
            raise RuntimeError("simulated Gemini outage")

        answer = generate_page_assistant_answer(
            api_key="not-used",
            model="fake-model",
            step=4,
            question="Can I close the website and reopen it again?",
            context_json=dashboard_context_json(pd.DataFrame()),
            request_fn=failed_request,
        )
        self.assertIn("reopen that exact link", answer)

    def test_generated_markdown_keeps_line_breaks(self):
        answer = generate_page_assistant_answer(
            api_key="not-used",
            model="fake-model",
            step=6,
            question="Suggest a campaign",
            context_json=dashboard_context_json(self.sample_frame()),
            request_fn=lambda _model, _prompt: (
                "**Dashboard evidence**\n- Dance leads views.\n\n"
                "**AI suggestions**\n- Test a creator-led challenge."
            ),
        )
        self.assertIn("\n- Dance", answer)
        self.assertIn("\n\n**AI suggestions**", answer)

    def test_chat_history_can_be_exported_as_markdown(self):
        exported = chat_history_markdown(
            [
                {"role": "user", "content": "Suggest a campaign"},
                {"role": "assistant", "content": "**AI suggestions**\n- Test one idea."},
            ],
            page_title="Taggy - Summary and export",
        )
        self.assertIn("# Taggy - Summary and export", exported)
        self.assertIn("## User", exported)
        self.assertIn("## Taggy", exported)
        self.assertIn("\n- Test one idea.", exported)

    def test_app_renders_taggy_on_every_step_and_keeps_chat_out_of_checkpoints(self):
        self.assertGreaterEqual(len(DASHBOARD_CHAT_SUGGESTIONS), 4)
        self.assertIn("render_taggy_assistant_v68_76(st.session_state.step", APP_SOURCE)
        self.assertIn("render_taggy_assistant_v68_76(6, filtered)", APP_SOURCE)
        self.assertIn("assets\" / \"taggy-assistant.png", APP_SOURCE)
        self.assertIn('key="taggy_floating_launcher_v68_78"', APP_SOURCE)
        self.assertIn('"Taggy stays available while tagging"', APP_SOURCE)
        self.assertIn('else "May I help?"', APP_SOURCE)
        self.assertIn("position:fixed !important", APP_SOURCE)
        self.assertIn("bottom:max(76px", APP_SOURCE)
        self.assertIn("assistant_popover = st.popover(", APP_SOURCE)
        self.assertIn("st.chat_input(", APP_SOURCE)
        self.assertIn("st.chat_message(", APP_SOURCE)
        self.assertIn('"Download chat"', APP_SOURCE)
        self.assertIn("chat_history_markdown(", APP_SOURCE)
        checkpoint_block = APP_SOURCE.split(
            "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15 = (", 1
        )[1].split(")", 1)[0]
        self.assertNotIn("taggy_chat_messages_v68_76", checkpoint_block)

    def test_taggy_companion_url_is_secret_free_and_uses_a_new_session_route(self):
        recovery_id = "a" * 32
        url = build_taggy_companion_url(
            base_url="https://example.streamlit.app/",
            recovery_id=recovery_id,
            step=4,
        )
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        self.assertEqual("https", parsed.scheme)
        self.assertEqual("example.streamlit.app", parsed.netloc)
        self.assertEqual(
            {"run": [recovery_id], "step": ["4"], "taggy": ["1"]},
            query,
        )
        self.assertNotIn("tagjob", parsed.query)
        self.assertNotIn("token", parsed.query.lower())
        self.assertNotIn("key", parsed.query.lower())

    def test_taggy_companion_is_read_only_and_stops_before_workflow(self):
        shell = APP_SOURCE.split("# Application shell and workflow pages", 1)[1]
        before_step_two = shell.split("# STEP 2: Add posts", 1)[0]

        self.assertIn(
            "_restore_runtime_checkpoint_v68_15(persist=not taggy_companion_session_v68_87)",
            before_step_two,
        )
        self.assertIn("if not taggy_companion_session_v68_87:", before_step_two)
        self.assertIn("standalone=True", before_step_two)
        self.assertIn("st.stop()", before_step_two)
        self.assertNotIn("run_real_tagging_backend(", before_step_two)

        restore_start = APP_SOURCE.index("def _restore_runtime_checkpoint_v68_15")
        restore_end = APP_SOURCE.index("# Display values and engagement metrics", restore_start)
        restore_source = APP_SOURCE[restore_start:restore_end]
        self.assertIn("*, persist: bool = True", restore_source)
        self.assertIn("if persist:\n        _persist_runtime_checkpoint_v68_15()", restore_source)

    def test_run_tagging_launcher_embeds_companion_in_small_popover(self):
        taggy_start = APP_SOURCE.index("def render_taggy_assistant_v68_76")
        taggy_end = APP_SOURCE.index("def aggregate_summary_performance_v68_15", taggy_start)
        taggy_source = APP_SOURCE[taggy_start:taggy_end]

        self.assertIn('st.session_state.get("tagging_job_active_v68_43", False)', taggy_source)
        self.assertIn(
            '_taggy_companion_url_v68_87(int(step)) if int(step) == 4 else ""',
            taggy_source,
        )
        self.assertIn("use_companion = bool(companion_url)", taggy_source)
        self.assertIn("if use_companion:", taggy_source)
        self.assertIn('key="taggy_companion_embed_v68_91"', taggy_source)
        self.assertIn("st.iframe(", taggy_source)
        self.assertIn("height=520", taggy_source)
        self.assertNotIn("target='_self'", taggy_source)
        self.assertNotIn("target='_blank'", taggy_source)
        self.assertNotIn("Ask Taggy ↗", taggy_source)


if __name__ == "__main__":
    unittest.main()
