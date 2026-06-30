from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.learning_guides import (  # noqa: E402
    RUN_GUIDES,
    challenge_prompt_for_guide,
    guide_for_config,
    guide_for_run_summary,
    mission_prompt_for_guide,
    observation_prompt_for_guide,
    playbook_for_guide,
    prediction_prompt_for_guide,
    question_for_guide,
    viewer_legend_for_guide,
)


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
                self.assertTrue(mission_prompt_for_guide(guide).startswith("Mission: "))
                self.assertTrue(playbook_for_guide(guide).startswith("Playbook: "))
                self.assertTrue(challenge_prompt_for_guide(guide).startswith("Challenge: "))
                self.assertTrue(question_for_guide(guide).startswith("Question: "))
                self.assertTrue(observation_prompt_for_guide(guide).startswith("Evidence to capture: "))
                self.assertTrue(prediction_prompt_for_guide(guide).startswith("Prediction: "))

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

    def test_observation_prompt_uses_watch_guidance(self) -> None:
        guide = guide_for_config(config_path="configs/lab04_panda/interactive_virtual_wall.yaml")

        self.assertIsNotNone(guide)
        assert guide is not None
        prompt = observation_prompt_for_guide(guide)
        self.assertIn("Evidence to capture:", prompt)
        self.assertIn("Wall penetration", prompt)
        self.assertEqual(observation_prompt_for_guide(None), "")

    def test_prediction_prompt_connects_change_to_watch_guidance(self) -> None:
        guide = guide_for_config(config_path="configs/lab02_pid/interactive_disturbance.yaml")

        self.assertIsNotNone(guide)
        assert guide is not None
        mission = mission_prompt_for_guide(guide)
        self.assertIn("Mission:", mission)
        self.assertIn("live sliders", mission)
        self.assertIn("Live target", mission)
        prompt = prediction_prompt_for_guide(guide)
        self.assertIn("Prediction:", prompt)
        self.assertIn("live sliders", prompt)
        self.assertIn("Live target", prompt)
        self.assertEqual(mission_prompt_for_guide(None), "")
        self.assertEqual(playbook_for_guide(None), "")
        self.assertEqual(challenge_prompt_for_guide(None), "")
        self.assertEqual(prediction_prompt_for_guide(None), "")

    def test_playbook_guides_predict_action_and_evidence(self) -> None:
        guide = guide_for_config(config_path="configs/lab04_panda/interactive_virtual_wall.yaml")

        self.assertIsNotNone(guide)
        assert guide is not None
        playbook = playbook_for_guide(guide)

        self.assertIn("Playbook:", playbook)
        self.assertIn("predict how", playbook)
        self.assertIn("change live sliders/presets", playbook)
        self.assertIn("mark one observation", playbook)

    def test_challenge_guides_visible_evidence_goal(self) -> None:
        guide = guide_for_config(config_path="configs/lab04_panda/interactive_virtual_wall.yaml")

        self.assertIsNotNone(guide)
        assert guide is not None
        challenge = challenge_prompt_for_guide(guide)

        self.assertIn("Challenge:", challenge)
        self.assertIn("Use live sliders/presets", challenge)
        self.assertIn("visible change", challenge)
        self.assertIn("prediction-backed observation", challenge)

    def test_viewer_legend_matches_visible_guides(self) -> None:
        lab01_guide = guide_for_config(config_path="configs/lab01_msd/interactive_pull.yaml")
        lab03_guide = guide_for_config(config_path="configs/lab03_2dof/condition_aware_dls_2dof.yaml")
        lab03_retarget_guide = guide_for_config(
            config_path="configs/lab03_2dof/condition_aware_dls_inward_retarget_2dof.yaml"
        )
        lab04_wall_guide = guide_for_config(config_path="configs/lab04_panda/interactive_virtual_wall.yaml")
        lab04_joint_guide = guide_for_config(config_path="configs/lab04_panda/joint_pd.yaml")

        self.assertIn(("Green marker", "Target position."), viewer_legend_for_guide(lab01_guide))
        self.assertIn(
            ("Orange sphere", "Singularity warning when Jacobian conditioning is poor."),
            viewer_legend_for_guide(lab03_guide),
        )
        self.assertIn(
            ("Small green spheres", "Planned target waypoint path."),
            viewer_legend_for_guide(lab03_retarget_guide),
        )
        self.assertIn(("Red plane", "Virtual wall location."), viewer_legend_for_guide(lab04_wall_guide))
        self.assertIn(
            ("Orange bar", "Virtual wall force direction and relative magnitude."),
            viewer_legend_for_guide(lab04_wall_guide),
        )
        self.assertEqual(viewer_legend_for_guide(lab04_joint_guide), [])

    def test_unknown_config_without_lab_context_has_no_guide(self) -> None:
        self.assertIsNone(guide_for_config(config_path="configs/custom/unknown.yaml"))


if __name__ == "__main__":
    unittest.main()
