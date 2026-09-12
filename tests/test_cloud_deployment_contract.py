import ast
import inspect
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
THEME_CONFIG = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
REQUIREMENTS = {
    line.strip()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
}
REQUIREMENT_NAMES = {
    line.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0].split("<", 1)[0].strip().lower()
    for line in REQUIREMENTS
}
APP_TREE = ast.parse(APP_SOURCE)


def load_function(name, namespace):
    node = next(
        item for item in APP_TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(ROOT / "app.py"), "exec"), namespace)
    return namespace[name]


class CloudDeploymentContractTests(unittest.TestCase):
    def test_cloud_run_container_starts_the_streamlit_frontend(self):
        self.assertIn("python -m streamlit run app.py", DOCKERFILE)
        self.assertIn("--server.address=0.0.0.0", DOCKERFILE)
        self.assertIn("--server.port=${PORT:-8080}", DOCKERFILE)
        self.assertNotIn("uvicorn cloudrun_main:app", DOCKERFILE)

    def test_managed_api_secret_accepts_cloud_run_environment_secret(self):
        class EmptySecrets:
            @staticmethod
            def get(_name, default=""):
                return default

        class StreamlitStub:
            secrets = EmptySecrets()

        clean_secret = lambda value: str(value or "").strip()
        managed_secret = load_function(
            "_managed_api_secret_v68_43",
            {"st": StreamlitStub(), "clean_api_secret": clean_secret, "os": os},
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": "cloud-secret"}):
            self.assertEqual(managed_secret("GEMINI_API_KEY"), "cloud-secret")

    def test_streamlit_secret_takes_priority_over_environment(self):
        class StreamlitSecrets:
            @staticmethod
            def get(_name, _default=""):
                return "streamlit-secret"

        class StreamlitStub:
            secrets = StreamlitSecrets()

        clean_secret = lambda value: str(value or "").strip()
        managed_secret = load_function(
            "_managed_api_secret_v68_43",
            {"st": StreamlitStub(), "clean_api_secret": clean_secret, "os": os},
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": "cloud-secret"}):
            self.assertEqual(managed_secret("GEMINI_API_KEY"), "streamlit-secret")

    def test_checkpoint_store_falls_back_when_hot_reload_keeps_legacy_class(self):
        class LegacyCheckpointStore:
            def __init__(self, root, *, chunk_size):
                self.root = root
                self.chunk_size = chunk_size

        namespace = {
            "Path": Path,
            "BatchCheckpointStore": LegacyCheckpointStore,
            "DEFAULT_CHUNK_SIZE": 50,
            "inspect": inspect,
            "LOGGER": logging.getLogger(__name__),
        }
        create_store = load_function("_create_batch_checkpoint_store_v68_48", namespace)
        remote = object()
        store = create_store(Path("checkpoint"), persistent_store=remote)
        self.assertIsInstance(store, LegacyCheckpointStore)
        self.assertEqual(store.chunk_size, 50)

    def test_checkpoint_store_uses_persistence_after_cold_start(self):
        class CurrentCheckpointStore:
            def __init__(self, root, *, chunk_size, persistent_store=None):
                self.root = root
                self.chunk_size = chunk_size
                self.persistent_store = persistent_store

        namespace = {
            "Path": Path,
            "BatchCheckpointStore": CurrentCheckpointStore,
            "DEFAULT_CHUNK_SIZE": 50,
            "inspect": inspect,
            "LOGGER": logging.getLogger(__name__),
        }
        create_store = load_function("_create_batch_checkpoint_store_v68_48", namespace)
        remote = object()
        store = create_store(Path("checkpoint"), persistent_store=remote)
        self.assertIs(store.persistent_store, remote)

    def test_streamlit_cloud_uses_a_fixed_light_theme(self):
        for setting in [
            'base = "light"',
            'textColor = "#111827"',
            'secondaryBackgroundColor = "#FFFFFF"',
            "showWidgetBorder = true",
        ]:
            with self.subTest(setting=setting):
                self.assertIn(setting, THEME_CONFIG)

    def test_cloud_uses_headless_opencv_only(self):
        self.assertIn("opencv-python-headless", REQUIREMENT_NAMES)
        self.assertNotIn("opencv-python", REQUIREMENT_NAMES)

    def test_css_does_not_force_dark_text_on_every_element(self):
        self.assertNotIn("html, body, p, span, label, div { color:", APP_SOURCE)

    def test_affected_controls_have_explicit_contrast_rules(self):
        for selector in [
            '.stButton button[kind="primary"] *',
            '[data-testid="stFileUploaderDropzone"] button *',
            '[data-testid="stFileUploaderFile"]',
            '[data-baseweb="popover"] [role="option"] *',
            '[data-testid="stExpander"] summary *',
            '[data-baseweb="input"] button *',
        ]:
            with self.subTest(selector=selector):
                self.assertIn(selector, APP_SOURCE)

    def test_page_headings_use_the_compact_style(self):
        # The marketing workflow has five visible pages; API access is managed
        # through deployment Secrets rather than a separate setup page.
        self.assertGreaterEqual(APP_SOURCE.count("card page-heading"), 5)

    def test_plotly_width_is_compatible_across_streamlit_versions(self):
        self.assertIn("def render_plotly_chart(fig)", APP_SOURCE)
        self.assertIn('if "width" in parameters:', APP_SOURCE)
        self.assertNotIn('st.plotly_chart(fig, width="stretch"', APP_SOURCE.split("def chart_bar", 1)[1])


if __name__ == "__main__":
    unittest.main()
