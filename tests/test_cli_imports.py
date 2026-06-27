from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.cli import LABS, main  # noqa: E402


class CliImportTests(unittest.TestCase):
    def test_cli_lists_labs(self) -> None:
        self.assertIn("lab01", LABS)
        self.assertIn("lab02", LABS)
        self.assertIn("lab03", LABS)
        self.assertIn("lab04", LABS)
        self.assertEqual(main(["list"]), 0)
