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
        self.assertIn("opencv-python-headless", REQUIREMENTS)
        self.assertNotIn("opencv-python", REQUIREMENTS)

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


if __name__ == "__main__":
    unittest.main()
