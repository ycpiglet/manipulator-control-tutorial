"""Regenerate or verify MCLab's universal hashed dependency locks."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UV_VERSION = "0.11.31"
EXCLUDE_NEWER = "2026-07-22T07:45:00Z"


@dataclass(frozen=True)
class LockProfile:
    name: str
    source: str
    output: str
    extras: tuple[str, ...] = ()


LOCK_PROFILES = (
    LockProfile("uv-tool", "requirements/tools/uv.in", "requirements/tools/uv.txt"),
    LockProfile(
        "supply-chain-tool",
        "requirements/tools/supply-chain.in",
        "requirements/tools/supply-chain.txt",
    ),
    LockProfile("build", "requirements/build.in", "requirements/locks/build.txt"),
    LockProfile("runtime", "pyproject.toml", "requirements/locks/runtime.txt"),
    LockProfile("app", "pyproject.toml", "requirements/locks/app.txt", ("app",)),
    LockProfile("dev", "pyproject.toml", "requirements/locks/dev.txt", ("dev",)),
    LockProfile(
        "app-dev",
        "pyproject.toml",
        "requirements/locks/app-dev.txt",
        ("app", "dev"),
    ),
    LockProfile(
        "package",
        "pyproject.toml",
        "requirements/locks/package.txt",
        ("app", "dev", "package"),
    ),
)


def compile_command(profile: LockProfile) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "uv",
        "pip",
        "compile",
        profile.source,
    ]
    for extra in profile.extras:
        command.extend(("--extra", extra))
    command.extend(
        (
            "--universal",
            "--python-version",
            "3.10",
            "--only-binary",
            ":all:",
            "--emit-build-options",
            "--generate-hashes",
            "--no-sources",
            "--exclude-newer",
            EXCLUDE_NEWER,
            "--no-python-downloads",
            "--output-file",
            profile.output,
        )
    )
    return command


def _installed_uv_version() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "uv", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    fields = completed.stdout.strip().split()
    return fields[1] if len(fields) >= 2 else ""


def _generate(root: Path) -> None:
    for profile in LOCK_PROFILES:
        output = root / profile.output
        output.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            compile_command(profile),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            if completed.stdout:
                print(completed.stdout, end="", file=sys.stderr)
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
            completed.check_returncode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check() -> int:
    with tempfile.TemporaryDirectory(prefix="mclab-lock-check-") as tmp:
        candidate_root = Path(tmp)
        shutil.copy2(ROOT / "pyproject.toml", candidate_root / "pyproject.toml")
        for profile in LOCK_PROFILES:
            source = ROOT / profile.source
            if source.name == "pyproject.toml":
                continue
            destination = candidate_root / profile.source
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        _generate(candidate_root)

        mismatches: list[str] = []
        for profile in LOCK_PROFILES:
            expected = ROOT / profile.output
            actual = candidate_root / profile.output
            if not expected.is_file() or expected.read_bytes() != actual.read_bytes():
                expected_hash = _sha256(expected) if expected.is_file() else "MISSING"
                mismatches.append(
                    f"{profile.name}: expected {expected_hash}, regenerated {_sha256(actual)}"
                )
        if mismatches:
            print("dependency lock regeneration mismatch:")
            for mismatch in mismatches:
                print(f"- {mismatch}")
            return 1

    print(f"dependency locks: PASS ({len(LOCK_PROFILES)}/{len(LOCK_PROFILES)} identical)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Regenerate in temp and compare.")
    mode.add_argument("--write", action="store_true", help="Rewrite the committed lock files.")
    args = parser.parse_args()

    try:
        actual_uv = _installed_uv_version()
    except (OSError, subprocess.CalledProcessError):
        print(
            "Run dependency lock generation through its disposable reviewed environment: "
            "python scripts/manage_dependency_locks.py --check (or --write).",
            file=sys.stderr,
        )
        return 2
    if actual_uv != UV_VERSION:
        print(f"uv version mismatch: expected {UV_VERSION}, got {actual_uv or 'unknown'}")
        return 2

    if args.write:
        _generate(ROOT)
        for profile in LOCK_PROFILES:
            path = ROOT / profile.output
            print(f"{profile.name}: {_sha256(path)}  {path.relative_to(ROOT)}")
        return 0
    return _check()


if __name__ == "__main__":
    raise SystemExit(main())
