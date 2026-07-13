import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
THEME_CONFIG = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
REQUIREMENTS = {
    line.strip()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
}
REQUIREMENT_NAMES = {
    line.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0].split("<", 1)[0].strip().lower()
    for line in REQUIREMENTS
}


class CloudDeploymentContractTests(unittest.TestCase):
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

    def test_native_and_runtime_dependencies_are_pinned(self):
        for package in [
            "streamlit", "pandas", "pyarrow", "opencv-python-headless", "numpy",
            "google-genai", "apify-client", "protobuf",
        ]:
            with self.subTest(package=package):
                self.assertTrue(
                    any(line.lower().startswith(f"{package}==") for line in REQUIREMENTS),
                    f"{package} must be pinned for reproducible local/cloud runs",
                )

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
        self.assertGreaterEqual(APP_SOURCE.count("card page-heading"), 6)

    def test_plotly_width_is_compatible_across_streamlit_versions(self):
        self.assertIn("def render_plotly_chart(fig)", APP_SOURCE)
        self.assertIn('if "width" in parameters:', APP_SOURCE)
        self.assertNotIn('st.plotly_chart(fig, width="stretch"', APP_SOURCE.split("def chart_bar", 1)[1])


if __name__ == "__main__":
    unittest.main()
