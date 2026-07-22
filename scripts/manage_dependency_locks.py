"""Run MCLab lock generation in a fresh, disposable, hash-locked tool venv."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]


def _run(command: Sequence[str]) -> None:
    subprocess.run(list(command), cwd=ROOT, check=True)


def _tool_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Regenerate in temp and compare.")
    mode.add_argument("--write", action="store_true", help="Rewrite every committed lock.")
    args = parser.parse_args(argv)

    if sys.implementation.name != "cpython" or not ((3, 10) <= sys.version_info[:2] < (3, 13)):
        print(
            "Dependency lock management requires CPython 3.10, 3.11, or 3.12.",
            file=sys.stderr,
        )
        return 2

    try:
        with tempfile.TemporaryDirectory(prefix="mclab-lock-tools-") as temporary:
            tool_venv = Path(temporary) / "venv"
            _run([sys.executable, "-m", "venv", str(tool_venv)])
            python = str(_tool_python(tool_venv))
            _run(
                [
                    python,
                    str(ROOT / "scripts" / "install_locked.py"),
                    "--allow-external-env",
                    "build",
                ]
            )
            _run(
                [
                    python,
                    "-m",
                    "pip",
                    "--isolated",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--force-reinstall",
                    "--require-hashes",
                    "--only-binary=:all:",
                    "-r",
                    str(ROOT / "requirements" / "tools" / "uv.txt"),
                ]
            )
            mode_flag = "--write" if args.write else "--check"
            _run([python, str(ROOT / "scripts" / "lock_requirements.py"), mode_flag])
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Dependency lock management failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
