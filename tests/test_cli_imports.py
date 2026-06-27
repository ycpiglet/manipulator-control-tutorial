from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.batch import BATCH_SETS  # noqa: E402
from mclab.cli import LABS, main  # noqa: E402
from mclab.cli import build_parser  # noqa: E402


class CliImportTests(unittest.TestCase):
    def test_cli_lists_labs(self) -> None:
        self.assertIn("lab01", LABS)
        self.assertIn("lab02", LABS)
        self.assertIn("lab03", LABS)
        self.assertIn("lab04", LABS)
        self.assertEqual(main(["list"]), 0)
        self.assertIn("lab01_msd_compare", BATCH_SETS)
        self.assertIn("lab02_pid_compare", BATCH_SETS)

    def test_cli_accepts_batch_comparison_options(self) -> None:
        args = build_parser().parse_args(
            [
                "batch",
                "lab02_pid_compare",
                "--output-dir",
                "outputs/demo_batch",
                "--no-plot",
                "--seed",
                "7",
            ]
        )
        self.assertEqual(args.command, "batch")
        self.assertEqual(args.batch_name, "lab02_pid_compare")
        self.assertEqual(args.output_dir, "outputs/demo_batch")
        self.assertTrue(args.no_plot)
        self.assertEqual(args.seed, 7)

    def test_cli_accepts_viewer_quality_of_life_options(self) -> None:
        default_args = build_parser().parse_args(
            [
                "run",
                "lab04",
                "--config",
                "configs/lab04_panda/joint_pd.yaml",
                "--viewer",
            ]
        )
        self.assertTrue(default_args.viewer)
        self.assertFalse(default_args.show_viewer_ui)

        args = build_parser().parse_args(
            [
                "run",
                "lab04",
                "--config",
                "configs/lab04_panda/joint_pd.yaml",
                "--viewer",
                "--show-viewer-ui",
                "--realtime",
                "--pause-at-end",
                "--plots",
                "essential",
            ]
        )
        self.assertTrue(args.viewer)
        self.assertTrue(args.show_viewer_ui)
        self.assertTrue(args.realtime)
        self.assertTrue(args.pause_at_end)
        self.assertEqual(args.plots, "essential")
