from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import manage_dependency_locks  # noqa: E402


class ManageDependencyLocksTests(unittest.TestCase):
    def test_check_uses_a_disposable_tool_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(
                    manage_dependency_locks.tempfile,
                    "TemporaryDirectory",
                    return_value=_TemporaryDirectory(tmp),
                ),
                patch.object(manage_dependency_locks, "_run") as run,
            ):
                self.assertEqual(manage_dependency_locks.main(["--check"]), 0)

        commands = [call.args[0] for call in run.call_args_list]
        tool_python = str(manage_dependency_locks._tool_python(Path(tmp) / "venv"))
        self.assertEqual(commands[0], [sys.executable, "-m", "venv", str(Path(tmp) / "venv")])
        self.assertEqual(
            commands[1],
            [
                tool_python,
                str(ROOT / "scripts" / "install_locked.py"),
                "--allow-external-env",
                "build",
            ],
        )
        self.assertEqual(commands[2][:5], [tool_python, "-m", "pip", "--isolated", "install"])
        self.assertIn("--force-reinstall", commands[2])
        self.assertIn("--require-hashes", commands[2])
        self.assertIn("--only-binary=:all:", commands[2])
        self.assertEqual(commands[2][-1], str(ROOT / "requirements" / "tools" / "uv.txt"))
        self.assertEqual(
            commands[3],
            [tool_python, str(ROOT / "scripts" / "lock_requirements.py"), "--check"],
        )
        self.assertNotIn(
            str(ROOT / ".venv"),
            " ".join(" ".join(command) for command in commands[1:]),
        )

    def test_write_forwards_only_the_write_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(
                    manage_dependency_locks.tempfile,
                    "TemporaryDirectory",
                    return_value=_TemporaryDirectory(tmp),
                ),
                patch.object(manage_dependency_locks, "_run") as run,
            ):
                self.assertEqual(manage_dependency_locks.main(["--write"]), 0)

        self.assertEqual(run.call_args_list[-1].args[0][-1], "--write")

    def test_tool_failure_is_fail_closed(self) -> None:
        with patch.object(
            manage_dependency_locks,
            "_run",
            side_effect=subprocess.CalledProcessError(1, ["tool"]),
        ):
            self.assertEqual(manage_dependency_locks.main(["--check"]), 2)


class _TemporaryDirectory:
    def __init__(self, path: str) -> None:
        self.path = path

    def __enter__(self) -> str:
        return self.path

    def __exit__(self, *args: object) -> None:
        return None
