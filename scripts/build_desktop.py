"""Build and size-check the platform-local PyInstaller application."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Bloat gate with headroom over measured baselines (2026-07-19): Linux
# 359,486,798 bytes (Qt/EGL shared libraries), macOS under 300 MB.
SIZE_LIMIT = 400 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--skip-size-gate", action="store_true")
    args = parser.parse_args()
    if args.clean:
        shutil.rmtree(ROOT / "build", ignore_errors=True)
        shutil.rmtree(ROOT / "dist" / "MCLab", ignore_errors=True)
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "packaging/mclab.spec"],
        cwd=ROOT,
        check=True,
    )
    output = ROOT / "dist" / "MCLab"
    # PyInstaller creates relative links from ``_internal`` to Qt's canonical
    # library directory on Unix.  Following those links counts the same bytes
    # twice even though the release archive stores the target only once.
    size = sum(
        path.lstat().st_size
        for path in output.rglob("*")
        if not path.is_symlink() and path.is_file()
    )
    print(f"MCLab one-folder size: {size / 1024 / 1024:.1f} MB")
    if size > SIZE_LIMIT and not args.skip_size_gate:
        raise RuntimeError(f"Desktop bundle exceeds 300 MB: {size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
