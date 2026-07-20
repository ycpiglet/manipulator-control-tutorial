"""Output folder filtering helpers."""

from __future__ import annotations

from pathlib import Path


INTERNAL_OUTPUT_PREFIXES = ("_", "codex_", "verify_")
RESERVED_OUTPUT_NAMES = (".mclab-trash",)


def is_internal_output_dir(path_or_name: str | Path) -> bool:
    """Return True for agent verification outputs that should not drive learner UX."""
    name = Path(path_or_name).name.casefold()
    return name in RESERVED_OUTPUT_NAMES or name.startswith(INTERNAL_OUTPUT_PREFIXES)
