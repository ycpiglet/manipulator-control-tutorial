from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.learning_guides import RUN_GUIDES, guide_for_config, guide_for_run_summary, question_for_guide  # noqa: E402


class LearningGuideTests(unittest.TestCase):
    def test_all_user_configs_have_report_guides(self) -> None:
        config_paths = sorted((ROOT / "configs").glob("*/*.yaml"))

        for config_path in config_paths:
            relative = config_path.relative_to(ROOT).as_posix()
            with self.subTest(config=relative):
                self.assertIn(relative, RUN_GUIDES)
                guide = guide_for_config(config_path=relative)
                self.assertIsNotNone(guide)
                assert guide is not None
                self.assertTrue(guide.focus)
                self.assertTrue(guide.try_this)
                self.assertTrue(guide.change)
                self.assertTrue(guide.watch)
                self.assertTrue(guide.next_step)
                self.assertTrue(question_for_guide(guide).startswith("Question: "))

    def test_guides_can_be_resolved_from_summary(self) -> None:
        guide = guide_for_run_summary(
            {
                "lab_name": "lab02_pid",
                "config_path": r"configs\lab02_pid\measurement_noise.yaml",
                "config_name": "measurement_noise",
            }
        )

        self.assertIsNotNone(guide)
        assert guide is not None
        self.assertIn("Sensor Noise", guide.title)
        self.assertIn("measurement_noise_std", guide.change)
        self.assertIn("noisy measurement", question_for_guide(guide))

    def test_unknown_config_uses_lab_fallback_when_possible(self) -> None:
        guide = guide_for_config(config_path="configs/custom/my_lab04_demo.yaml", lab_name="lab04_panda")

        self.assertIsNotNone(guide)
        assert guide is not None
        self.assertEqual(guide.title, "Lab04 Panda Manipulator")
        self.assertIn("Panda", question_for_guide(guide))

    def test_unknown_config_without_lab_context_has_no_guide(self) -> None:
        self.assertIsNone(guide_for_config(config_path="configs/custom/unknown.yaml"))


if __name__ == "__main__":
    unittest.main()
