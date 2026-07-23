"""Bundle the deterministic repository notice artifact with the desktop app."""

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
datas = [(str(_REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md"), ".")]
