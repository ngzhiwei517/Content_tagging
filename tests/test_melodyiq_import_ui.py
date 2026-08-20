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


if __name__ == "__main__":
    unittest.main()
