"""Cross-platform source bootstrap for the integrated desktop app."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    from scripts.install_locked import project_venv_redirect_error, support_error
except ModuleNotFoundError:  # Direct execution puts scripts/ first on sys.path.
    from install_locked import project_venv_redirect_error, support_error

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install and start MCLab.")
    parser.add_argument("--lang", choices=("ko", "en"))
    parser.add_argument("--safe-mode", action="store_true")
    parser.add_argument("--setup-only", action="store_true")
    args = parser.parse_args()

    _ensure_venv()
    _run([str(VENV_PYTHON), str(ROOT / "scripts" / "install_locked.py"), "app"])
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


def _ensure_venv() -> None:
    redirect_error = project_venv_redirect_error(VENV)
    if redirect_error:
        raise RuntimeError(
            f"Refusing unsafe project environment {VENV}: {redirect_error}. "
            "Remove it before setup."
        )
    if VENV_PYTHON.exists():
        return
    if VENV.exists():
        raise RuntimeError(
            f"Refusing to overwrite incomplete project environment {VENV}. "
            "Remove it before setup."
        )
    error = support_error("app")
    if error:
        raise RuntimeError(error)
    _run([sys.executable, "-m", "venv", str(VENV)])


def _run(command: list[str], *, accepted: tuple[int, ...] = (0,)) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode not in accepted:
        raise subprocess.CalledProcessError(completed.returncode, command)


if __name__ == "__main__":
    raise SystemExit(main())
