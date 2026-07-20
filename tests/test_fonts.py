from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.application.fonts import (  # noqa: E402
    FONT_ROOT,
    STATIC_FONT_NAMES,
    application_font_files,
)

EXPECTED_STYLES = {
    "NotoSansKR-Regular.ttf": ("Noto Sans KR", 400),
    "NotoSansKR-Medium.ttf": ("Noto Sans KR", 500),
    "NotoSansKR-SemiBold.ttf": ("Noto Sans KR", 600),
    "NotoSansKR-Bold.ttf": ("Noto Sans KR", 700),
    "NotoSansMono-Regular.ttf": ("Noto Sans Mono", 400),
    "NotoSansMono-Bold.ttf": ("Noto Sans Mono", 700),
}


class ApplicationFontSelectionTests(unittest.TestCase):
    def test_prefers_complete_static_weight_set(self) -> None:
        files = application_font_files()
        self.assertEqual([path.name for path in files], list(STATIC_FONT_NAMES))
        for path in files:
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.parent.name, "static")

    def test_falls_back_to_variable_fonts_when_statics_missing(self) -> None:
        files = application_font_files(FONT_ROOT / "does-not-exist")
        self.assertEqual(
            [path.name for path in files],
            ["NotoSansKR[wght].ttf", "NotoSansMono[wdth,wght].ttf"],
        )


class StaticInstanceIntegrityTests(unittest.TestCase):
    """Bold Korean UI text must come from true static weights.

    Registering the variable font and asking Qt for wght=600/700 renders
    wrong glyphs on some Windows DirectWrite versions, so the bundled static
    instances must stay static, keep their weight metadata, and keep Hangul
    coverage.
    """

    def test_static_instances_are_static_and_correctly_named(self) -> None:
        from fontTools.ttLib import TTFont

        for path in application_font_files():
            font = TTFont(path, lazy=True)
            name = font["name"]
            family = name.getDebugName(16) or name.getDebugName(1)
            expected_family, expected_weight = EXPECTED_STYLES[path.name]
            self.assertNotIn("fvar", font, f"{path.name} still has variable axes")
            self.assertEqual(family, expected_family, path.name)
            self.assertEqual(font["OS/2"].usWeightClass, expected_weight, path.name)
            if "KR" in path.name:
                cmap = font.getBestCmap()
                for char in "한국어실험자동데모둘러보기0123456789":
                    self.assertIn(ord(char), cmap, f"{path.name} missing {char!r}")


if __name__ == "__main__":
    unittest.main()
