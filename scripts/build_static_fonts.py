"""Instantiate the static UI font weights bundled with MCLab.

The desktop app registers static single-weight fonts instead of the variable
originals because several Qt/DirectWrite releases resolve non-default variable
weights (for example ``wght=700``) to mismatched glyph indexes on Windows,
which renders bold Korean labels as the wrong syllables. Static instances
sidestep runtime axis instancing entirely.

Run from the repository root after updating the pinned variable fonts:

    .venv/bin/python scripts/build_static_fonts.py

The variable originals stay in place for matplotlib plot rendering.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT_ROOT = PROJECT_ROOT / "third_party" / "fonts" / "noto"
STATIC_ROOT = FONT_ROOT / "static"

INSTANCES: tuple[tuple[str, dict[str, float], str], ...] = (
    ("NotoSansKR[wght].ttf", {"wght": 400}, "NotoSansKR-Regular.ttf"),
    ("NotoSansKR[wght].ttf", {"wght": 500}, "NotoSansKR-Medium.ttf"),
    ("NotoSansKR[wght].ttf", {"wght": 600}, "NotoSansKR-SemiBold.ttf"),
    ("NotoSansKR[wght].ttf", {"wght": 700}, "NotoSansKR-Bold.ttf"),
    ("NotoSansMono[wdth,wght].ttf", {"wdth": 100, "wght": 400}, "NotoSansMono-Regular.ttf"),
    ("NotoSansMono[wdth,wght].ttf", {"wdth": 100, "wght": 700}, "NotoSansMono-Bold.ttf"),
)


def build() -> list[Path]:
    STATIC_ROOT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source_name, axis_limits, target_name in INSTANCES:
        font = TTFont(FONT_ROOT / source_name, recalcTimestamp=False)
        instantiateVariableFont(font, axis_limits, inplace=True, updateFontNames=True)
        target = STATIC_ROOT / target_name
        font.save(target)
        written.append(target)
    return written


def main() -> int:
    for path in build():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{digest}  {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
