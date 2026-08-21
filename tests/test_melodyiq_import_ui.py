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
        self.assertIn('"Find track"', source)
        self.assertIn('"Create report"', source)
        self.assertIn('st.markdown(f"#### Reports ({len(queue)})")', source)

    def test_find_track_uses_direct_button_on_the_first_click(self):
        source = _function_source("render_melodyiq_import_v68_97")

        self.assertIn("search_submitted = st.button(", source)
        self.assertIn('key="melodyiq_find_track_v68_102"', source)
        self.assertNotIn("with st.form(", source)
        self.assertNotIn("st.form_submit_button(", source)

    def test_report_creation_copy_is_concise_and_supports_multiple_reports(self):
        source = _function_source("render_melodyiq_import_v68_97")

        self.assertIn('"Review matched TikTok sounds"', source)
        self.assertIn("automatically adds related TikTok sounds", source)
        self.assertIn("may include thousands of posts", source)
        self.assertIn("You can create multiple reports at the same time", source)
        self.assertIn("after import to free a report slot.", source)
        self.assertNotIn("Prepare another standard report?", source)
        self.assertNotIn("Prepare posts from selected sounds", source)

    def test_report_creation_appends_without_replacing_existing_reports(self):
        source = _function_source("render_melodyiq_import_v68_97")

        self.assertIn("queue = _melodyiq_report_queue_v68_100()", source)
        self.assertIn("queue.append(", source)
        self.assertIn("_melodyiq_save_report_queue_v68_100(queue)", source)
        self.assertIn("_persist_runtime_checkpoint_v68_15()", source)
        self.assertNotIn(
            "st.session_state.melodyiq_report_v68_97 = report",
            source,
        )

    def test_each_report_uses_independent_widget_keys_and_cleanup(self):
        source = _function_source("_render_melodyiq_report_card_v68_100")

        self.assertIn('f"melodyiq_report_scope_{report_key}"', source)
        self.assertIn('key=f"melodyiq_import_posts_{report_key}"', source)
        self.assertIn('key=f"melodyiq_delete_report_{report_key}"', source)
        self.assertIn("client.delete_report(report_id)", source)
        self.assertIn("_melodyiq_remove_report_v68_100(report_id)", source)

    def test_report_creation_defers_import_scope_until_ready(self):
        source = _function_source("render_melodyiq_import_v68_97")

        self.assertNotIn("_render_melodyiq_import_plan_controls_v68_101(", source)
        self.assertIn("import_plan = _melodyiq_import_plan_v68_101()", source)
        self.assertIn('"import_scope": import_plan', source)
        self.assertIn("Choose posts to import after the report is ready", source)

    def test_import_scope_offers_top_latest_and_all(self):
        source = _function_source(
            "_render_melodyiq_import_plan_controls_v68_101"
        )
        constants = APP_PATH.read_text(encoding="utf-8")

        self.assertIn('"top": "Top posts"', constants)
        self.assertIn('"latest": "Latest posts"', constants)
        self.assertIn('"all": "All posts"', constants)
        self.assertIn("st.segmented_control(", source)
        self.assertIn('"Number of posts"', source)
        self.assertIn('"Number of recent posts"', source)
        self.assertNotIn('"Maximum rows to import"', source)
        self.assertIn("MELODYIQ_ALL_POSTS_SAFETY_LIMIT_V68_102", source)
        self.assertIn("All posts are selected automatically", source)

    def test_ready_report_applies_its_saved_import_scope(self):
        source = _function_source("_render_melodyiq_report_card_v68_100")

        self.assertIn("_render_melodyiq_import_plan_controls_v68_101(", source)
        self.assertIn('if import_plan["mode"] == "all":', source)
        self.assertIn('"postCreatedAt"', source)
        self.assertIn('limit=int(import_plan["limit"])', source)
        self.assertIn('sort_field=sort_field', source)
        self.assertIn('max_rows=int(import_plan["limit"])', source)
        self.assertIn('tiktok_report.get("postsExportUrl")', source)
        self.assertNotIn('"Download full report CSV"', source)
        self.assertNotIn('key=f"melodyiq_download_report_{report_key}"', source)
        self.assertNotIn("st.link_button(", source)
        self.assertNotIn("Download always", source)

    def test_report_preview_links_open_the_original_post(self):
        source = _function_source("_render_melodyiq_report_card_v68_100")
        preview_source = _function_source("_melodyiq_report_preview_rows_v68_103")

        self.assertIn('"Preview report"', source)
        self.assertIn('preview_column_config["Link"]', source)
        self.assertIn("st.column_config.LinkColumn(", source)
        self.assertIn(
            'key=f"melodyiq_report_preview_table_{report_key}"',
            source,
        )
        self.assertIn(
            'limit=min(max(int(import_plan.get("limit", 20)), 1), 20)',
            preview_source,
        )

    def test_report_queue_migrates_legacy_single_report(self):
        source = _function_source("_melodyiq_report_queue_v68_100")

        self.assertIn('st.session_state.pop("melodyiq_report_v68_97", None)', source)
        self.assertIn('value["import_scope"] = _melodyiq_import_plan_v68_101(', source)
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
