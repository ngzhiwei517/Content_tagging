import unittest
from pathlib import Path


APP_SOURCE = (Path(__file__).resolve().parents[1] / "app.py").read_text(
    encoding="utf-8"
)


class AppTitleTests(unittest.TestCase):
    def test_home_title_uses_existing_hero_style_with_taggy_name(self):
        self.assertIn("<div class='app-title hero-v37 hero-title-only'>", APP_SOURCE)
        self.assertIn("<h1>Taggy</h1>", APP_SOURCE)
        self.assertNotIn("<h1>UGC Post Tagging Tool</h1>", APP_SOURCE)


if __name__ == "__main__":
    unittest.main()
