import unittest
from pathlib import Path


class ReviewHtmlRenderingTests(unittest.TestCase):
    def test_review_info_card_uses_html_renderer_not_markdown(self):
        source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(
            encoding="utf-8"
        )
        start = source.index("    with middle:")
        end = source.index("    with right:", start)
        review_info_block = source[start:end]
        self.assertIn("st.html(", review_info_block)
        self.assertIn("review-info-card", review_info_block)
        self.assertNotIn("unsafe_allow_html=True", review_info_block)


if __name__ == "__main__":
    unittest.main()
