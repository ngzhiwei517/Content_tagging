import ast
import json
import re
import unittest
from pathlib import Path


class GeminiJsonRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = Path(__file__).resolve().parents[1] / "final_update2_backend_source.py"
        source = source_path.read_text(encoding="utf-8")
        parsed = ast.parse(source)
        function = next(
            node for node in parsed.body
            if isinstance(node, ast.FunctionDef) and node.name == "_decode_gemini_json"
        )
        module = ast.Module(body=[function], type_ignores=[])
        ast.fix_missing_locations(module)
        namespace = {"json": json, "re": re}
        exec(compile(module, str(source_path), "exec"), namespace, namespace)
        cls.decode = staticmethod(namespace["_decode_gemini_json"])

    def test_clean_json_is_unchanged(self):
        value = self.decode(
            '{"narrative":"Interview","creative_type":["Media/Infotainment"]}'
        )
        self.assertEqual(value["narrative"], "Interview")

    def test_markdown_fenced_json_is_recovered(self):
        value = self.decode(
            '```json\n{"narrative":"Drama news","creative_type":["Movie/Tv/Drama Edits"]}\n```'
        )
        self.assertEqual(value["narrative"], "Drama news")

    def test_json_surrounded_by_prose_is_recovered(self):
        value = self.decode(
            'Here is the result: {"narrative":"Celebrity interview","creative_type":["Celebrity Edits"]} Done.'
        )
        self.assertEqual(value["creative_type"], ["Celebrity Edits"])

    def test_invalid_text_still_raises_for_safe_review_routing(self):
        with self.assertRaises(ValueError):
            self.decode("not valid json")


if __name__ == "__main__":
    unittest.main()
