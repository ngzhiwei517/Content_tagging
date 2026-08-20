import ast
from pathlib import Path
import unittest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _function_source(name: str) -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"Function {name!r} was not found in app.py")


class MelodyIQImportUiTests(unittest.TestCase):
    def test_catalog_match_confirms_track_and_supplies_blank_artist(self):
        source = _function_source("render_melodyiq_import_v68_97")

        self.assertIn("render_uploaded_track_catalog_feedback_v68_62(", source)
        self.assertIn("artists=[resolved_artist] if resolved_artist else None", source)
        self.assertIn(
            "st.session_state.melodyiq_artist_v68_97 = resolved_artist",
            source,
        )

    def test_authentication_error_does_not_also_show_no_matches(self):
        source = _function_source("render_melodyiq_import_v68_97")

        self.assertIn("search_failed = True", source)
        self.assertIn("if search_submitted and not search_failed:", source)

    def test_melodyiq_is_the_primary_confirmed_input_path(self):
        source = _function_source("render_melodyiq_import_v68_97")

        self.assertIn('st.markdown("### Find posts by track")', source)
        self.assertIn('"Find TikTok posts"', source)
        self.assertIn('"Prepare posts from selected sounds"', source)
        self.assertIn('st.markdown(f"#### Prepared reports ({len(queue)})")', source)

    def test_report_creation_appends_without_replacing_existing_reports(self):
        source = _function_source("render_melodyiq_import_v68_97")

        self.assertIn("queue = _melodyiq_report_queue_v68_100()", source)
        self.assertIn("queue.append(", source)
        self.assertIn("_melodyiq_save_report_queue_v68_100(queue)", source)
        self.assertNotIn(
            "st.session_state.melodyiq_report_v68_97 = report",
            source,
        )

    def test_each_report_uses_independent_widget_keys_and_cleanup(self):
        source = _function_source("_render_melodyiq_report_card_v68_100")

        self.assertIn('key=f"melodyiq_import_mode_{report_key}"', source)
        self.assertIn('key=f"melodyiq_import_posts_{report_key}"', source)
        self.assertIn('key=f"melodyiq_delete_report_{report_key}"', source)
        self.assertIn("client.delete_report(report_id)", source)
        self.assertIn("_melodyiq_remove_report_v68_100(report_id)", source)

    def test_report_queue_migrates_legacy_single_report(self):
        source = _function_source("_melodyiq_report_queue_v68_100")

        self.assertIn('st.session_state.pop("melodyiq_report_v68_97", None)', source)
        self.assertIn("st.session_state.melodyiq_reports_v68_100 = queue", source)

    def test_pending_report_refreshes_automatically(self):
        source = _function_source("_render_melodyiq_report_progress_v68_99")
        app_source = APP_PATH.read_text(encoding="utf-8")

        self.assertIn("@st.fragment(run_every=10)", app_source)
        self.assertIn("MelodyIQClient(api_key).get_report(report_id)", source)
        self.assertIn("pending[cursor % len(pending)]", source)
        self.assertIn("refreshes automatically", source)
        self.assertNotIn("Check report status", app_source)


if __name__ == "__main__":
    unittest.main()
