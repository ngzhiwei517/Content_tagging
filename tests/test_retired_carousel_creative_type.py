import ast
import unittest
from pathlib import Path

from ugc_tagger.final_update2_adapter import (
    _to_ui_row,
    operational_creative_type,
)


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
BACKEND_SOURCE_PATH = ROOT / "ugc_tagger" / "final_update2_backend_source.py"


class RetiredCarouselCreativeTypeTests(unittest.TestCase):
    def test_carousel_is_not_a_manual_creative_type_option(self):
        tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
        creative_types = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "CREATIVE_TYPES"
                for target in node.targets
            )
        )
        self.assertNotIn("Carousel", creative_types)

    def test_carousel_is_removed_but_semantic_label_is_kept(self):
        self.assertEqual(
            operational_creative_type("Carousel, Beauty"),
            "Beauty",
        )
        self.assertEqual(
            operational_creative_type(["Carousel", "Quotes"]),
            "Quotes",
        )

    def test_carousel_only_result_safely_falls_back_to_others(self):
        self.assertEqual(operational_creative_type("Carousel"), "Others")

    def test_detailed_drama_carousel_name_is_not_removed(self):
        self.assertEqual(
            operational_creative_type("Drama Carousel"),
            "Drama Carousel",
        )

    def test_adapter_never_exposes_generic_carousel_as_creative_type(self):
        converted = _to_ui_row(
            {
                "Link": "https://www.tiktok.com/@creator/photo/123",
                "Platform": "TikTok",
            },
            {
                "Creative Type": "Carousel, Beauty",
                "Narrative": "Makeup advice",
                "Content Details": "A slideshow gives eye-makeup advice.",
                "validation_status": "pass",
            },
            {},
        )
        self.assertEqual(converted["Creative Type"], "Beauty")
        self.assertEqual(converted["Original AI Labels"], "Beauty")
        self.assertEqual(converted["Final Labels"], "Beauty")

    def test_prompt_treats_carousel_as_format_not_creative_type(self):
        source = BACKEND_SOURCE_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "do NOT use Carousel as a Creative Type.",
            source,
        )
        self.assertIn("if creative_type != 'Carousel'", source)
        self.assertNotIn(
            "If yes, include Carousel.",
            source,
        )


if __name__ == "__main__":
    unittest.main()
