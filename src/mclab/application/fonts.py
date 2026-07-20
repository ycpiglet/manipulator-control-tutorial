"""Select the bundled UI font files the desktop app registers with Qt.

The app registers static single-weight instances instead of the variable
originals: several Qt/DirectWrite releases resolve non-default variable
weights (``wght=600``/``700``) to mismatched glyph indexes on Windows, which
renders bold Korean labels as the wrong syllables. The variable fonts remain
bundled for matplotlib plot rendering; regenerate the static set with
``scripts/build_static_fonts.py``.
"""

from __future__ import annotations

from pathlib import Path

from mclab.config import PROJECT_ROOT

FONT_ROOT = PROJECT_ROOT / "third_party" / "fonts" / "noto"

STATIC_FONT_NAMES = (
    "NotoSansKR-Regular.ttf",
    "NotoSansKR-Medium.ttf",
    "NotoSansKR-SemiBold.ttf",
    "NotoSansKR-Bold.ttf",
    "NotoSansMono-Regular.ttf",
    "NotoSansMono-Bold.ttf",
)

VARIABLE_FONT_NAMES = (
    "NotoSansKR[wght].ttf",
    "NotoSansMono[wdth,wght].ttf",
)


def application_font_files(font_root: str | Path = FONT_ROOT) -> list[Path]:
    """Return the font files to register, preferring the static weights."""
    root = Path(font_root)
    static_files = [root / "static" / name for name in STATIC_FONT_NAMES]
    if all(path.is_file() for path in static_files):
        return static_files
    return [root / name for name in VARIABLE_FONT_NAMES]
