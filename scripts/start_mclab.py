"""Cross-platform source bootstrap for the integrated desktop app."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install and start MCLab.")
    parser.add_argument("--lang", choices=("ko", "en"))
    parser.add_argument("--safe-mode", action="store_true")
    parser.add_argument("--setup-only", action="store_true")
    args = parser.parse_args()

    if not VENV_PYTHON.exists():
        _run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    if not _module_available("PySide6") or not _module_available("mclab"):
        _run([str(VENV_PYTHON), "-m", "pip", "install", "-e", ".[app]"])
    _run([str(VENV_PYTHON), "-m", "mclab", "assets", "install"])
    if args.setup_only:
        _run([str(VENV_PYTHON), "-m", "mclab", "app", "--self-test"])
        return 0
    command = [str(VENV_PYTHON), "-m", "mclab", "app"]
    if args.lang:
        command.extend(("--lang", args.lang))
    if args.safe_mode:
        command.append("--safe-mode")
    _run(command, accepted=(0, 6))
    return 0


def _module_available(name: str) -> bool:
    result = subprocess.run(
        [str(VENV_PYTHON), "-c", f"import {name}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _run(command: list[str], *, accepted: tuple[int, ...] = (0,)) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode not in accepted:
        raise subprocess.CalledProcessError(completed.returncode, command)


if __name__ == "__main__":
    raise SystemExit(main())
