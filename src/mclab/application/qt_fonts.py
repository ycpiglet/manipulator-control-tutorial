"""Font environment defaults that must land before the QGuiApplication exists."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_font_environment(font_root: Path) -> None:
    """Point Qt at the bundled Noto fonts and pick a safe Windows font engine."""

    os.environ.setdefault("QT_QPA_FONTDIR", str(font_root))
    if sys.platform == "win32":
        # DirectWrite mismaps glyph indices for the bundled variable Noto
        # fonts (bold Hangul/Latin renders as the wrong characters);
        # FreeType shapes them correctly.
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:fontengine=freetype")
