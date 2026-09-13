import ast
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def load_managed_secret_helper(secrets):
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    required = {"safe_str", "clean_api_secret", "_managed_api_secret_v68_43"}
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in required
    ]
    namespace = {
        "os": os,
        "pd": pd,
        "Path": Path,
        "st": SimpleNamespace(secrets=secrets),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), APP_PATH, "exec"), namespace)
    return namespace["_managed_api_secret_v68_43"]


class ManagedApiSecretTests(unittest.TestCase):
    def test_mounted_secret_file_has_precedence_for_hot_rotation(self):
        helper = load_managed_secret_helper({"APIFY_TOKEN": "streamlit-value"})
        secret_path = APP_PATH.parent / ".tmp" / "test-apify-secret.txt"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text("Bearer mounted-value\n", encoding="utf-8")
        self.addCleanup(secret_path.unlink, missing_ok=True)

        with patch.dict(
            os.environ,
            {
                "APIFY_TOKEN_FILE": str(secret_path),
                "APIFY_TOKEN": "cloud-value",
            },
        ):
            self.assertEqual(helper("APIFY_TOKEN"), "mounted-value")

    def test_unavailable_mounted_secret_file_uses_existing_fallback(self):
        helper = load_managed_secret_helper({"APIFY_TOKEN": "streamlit-value"})
        missing_path = APP_PATH.parent / ".tmp" / "missing-apify-secret.txt"

        with patch.dict(
            os.environ,
            {"APIFY_TOKEN_FILE": str(missing_path), "APIFY_TOKEN": "cloud-value"},
        ):
            self.assertEqual(helper("APIFY_TOKEN"), "streamlit-value")

    def test_cloud_run_environment_value_is_used(self):
        helper = load_managed_secret_helper({})
        with patch.dict(os.environ, {"GEMINI_API_KEY": "Bearer cloud-value"}):
            self.assertEqual(helper("GEMINI_API_KEY"), "cloud-value")

    def test_streamlit_secret_keeps_precedence(self):
        helper = load_managed_secret_helper({"APIFY_TOKEN": "streamlit-value"})
        with patch.dict(os.environ, {"APIFY_TOKEN": "cloud-value"}):
            self.assertEqual(helper("APIFY_TOKEN"), "streamlit-value")

    def test_environment_fallback_survives_unavailable_streamlit_secrets(self):
        class UnavailableSecrets:
            def get(self, _name, _default):
                raise RuntimeError("secrets unavailable")

        helper = load_managed_secret_helper(UnavailableSecrets())
        with patch.dict(os.environ, {"APIFY_TOKEN": "cloud-value"}):
            self.assertEqual(helper("APIFY_TOKEN"), "cloud-value")


if __name__ == "__main__":
    unittest.main()
