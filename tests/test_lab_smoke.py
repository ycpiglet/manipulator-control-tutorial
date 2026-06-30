from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.config import load_config  # noqa: E402
from mclab.labs import lab01_msd, lab02_pid, lab03_2dof, lab04_panda  # noqa: E402


@unittest.skipIf(importlib.util.find_spec("mujoco") is None, "MuJoCo is not installed")
class LabSmokeTests(unittest.TestCase):
    def test_lab01_runs_headless_when_mujoco_is_available(self) -> None:
        config = load_config("configs/lab01_msd/default.yaml")
        config["sim_time"] = 0.02
        with tempfile.TemporaryDirectory() as tmp:
            output = lab01_msd.run(config, output_dir=Path(tmp) / "lab01", headless=True)
            self.assertTrue((output / "log.csv").exists())
            self.assertTrue((output / "summary.json").exists())

    def test_lab02_runs_headless_when_mujoco_is_available(self) -> None:
        config = load_config("configs/lab02_pid/default.yaml")
        config["sim_time"] = 0.02
        with tempfile.TemporaryDirectory() as tmp:
            output = lab02_pid.run(config, output_dir=Path(tmp) / "lab02", headless=True)
            self.assertTrue((output / "log.csv").exists())
            self.assertTrue((output / "summary.json").exists())

    def test_lab02_noise_and_delay_configs_run_headless_when_mujoco_is_available(self) -> None:
        for config_path in ("configs/lab02_pid/measurement_noise.yaml", "configs/lab02_pid/control_delay.yaml"):
            with self.subTest(config_path=config_path):
                config = load_config(config_path)
                config["sim_time"] = 0.02
                with tempfile.TemporaryDirectory() as tmp:
                    output = lab02_pid.run(config, output_dir=Path(tmp) / "lab02", headless=True)
                    self.assertTrue((output / "log.csv").exists())
                    self.assertTrue((output / "summary.json").exists())

    def test_lab03_runs_headless_when_mujoco_is_available(self) -> None:
        config = load_config("configs/lab03_2dof/joint_space_2dof.yaml")
        config["sim_time"] = 0.02
        with tempfile.TemporaryDirectory() as tmp:
            output = lab03_2dof.run(config, output_dir=Path(tmp) / "lab03", headless=True)
            self.assertTrue((output / "log.csv").exists())
            self.assertTrue((output / "summary.json").exists())

    def test_lab03_task_space_runs_headless_when_mujoco_is_available(self) -> None:
        config = load_config("configs/lab03_2dof/task_space_2dof.yaml")
        config["sim_time"] = 0.02
        with tempfile.TemporaryDirectory() as tmp:
            output = lab03_2dof.run(config, output_dir=Path(tmp) / "lab03_task", headless=True)
            self.assertTrue((output / "log.csv").exists())
            self.assertTrue((output / "summary.json").exists())

    def test_lab03_singularity_runs_headless_when_mujoco_is_available(self) -> None:
        config = load_config("configs/lab03_2dof/singularity_2dof.yaml")
        config["sim_time"] = 0.02
        with tempfile.TemporaryDirectory() as tmp:
            output = lab03_2dof.run(config, output_dir=Path(tmp) / "lab03_singularity", headless=True)
            self.assertTrue((output / "log.csv").exists())
            self.assertTrue((output / "summary.json").exists())

    def test_lab03_dls_singularity_runs_headless_when_mujoco_is_available(self) -> None:
        for config_path in (
            "configs/lab03_2dof/dls_singularity_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_early_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_late_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_inner_target_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_edge_target_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_upper_path_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_lower_path_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_high_torque_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_slow_command_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_fast_command_2dof.yaml",
        ):
            with self.subTest(config_path=config_path):
                config = load_config(config_path)
                config["sim_time"] = 0.02
                with tempfile.TemporaryDirectory() as tmp:
                    output = lab03_2dof.run(config, output_dir=Path(tmp) / "lab03_dls", headless=True)
                    self.assertTrue((output / "log.csv").exists())
                    self.assertTrue((output / "summary.json").exists())

    def test_lab04_runs_headless_when_assets_are_available(self) -> None:
        if not (ROOT / "third_party/mujoco_menagerie/franka_emika_panda/scene.xml").exists():
            self.skipTest("MuJoCo Menagerie has not been fetched")

        for config_path in ("configs/lab04_panda/neutral_hold.yaml", "configs/lab04_panda/neutral_hold_30s.yaml"):
            with self.subTest(config_path=config_path):
                config = load_config(config_path)
                config["sim_time"] = 0.02
                with tempfile.TemporaryDirectory() as tmp:
                    output = lab04_panda.run(config, output_dir=Path(tmp) / "lab04", headless=True)
                    self.assertTrue((output / "log.csv").exists())
                    self.assertTrue((output / "summary.json").exists())

    def test_lab04_wall_configs_run_headless_when_assets_are_available(self) -> None:
        if not (ROOT / "third_party/mujoco_menagerie/franka_emika_panda/scene.xml").exists():
            self.skipTest("MuJoCo Menagerie has not been fetched")

        for config_path in (
            "configs/lab04_panda/wall_stiff.yaml",
            "configs/lab04_panda/wall_low_damping.yaml",
            "configs/lab04_panda/wall_high_damping.yaml",
            "configs/lab04_panda/wall_near.yaml",
            "configs/lab04_panda/wall_far.yaml",
            "configs/lab04_panda/wall_slow_approach.yaml",
            "configs/lab04_panda/wall_fast_approach.yaml",
            "configs/lab04_panda/wall_low_retreat.yaml",
            "configs/lab04_panda/wall_high_retreat.yaml",
        ):
            with self.subTest(config_path=config_path):
                config = load_config(config_path)
                config["sim_time"] = 0.02
                with tempfile.TemporaryDirectory() as tmp:
                    output = lab04_panda.run(config, output_dir=Path(tmp) / "lab04_wall", headless=True)
                    self.assertTrue((output / "log.csv").exists())
                    self.assertTrue((output / "summary.json").exists())

    def test_lab04_cartesian_reach_runs_headless_when_assets_are_available(self) -> None:
        if not (ROOT / "third_party/mujoco_menagerie/franka_emika_panda/scene.xml").exists():
            self.skipTest("MuJoCo Menagerie has not been fetched")

        config = load_config("configs/lab04_panda/cartesian_reach.yaml")
        config["sim_time"] = 0.02
        with tempfile.TemporaryDirectory() as tmp:
            output = lab04_panda.run(config, output_dir=Path(tmp) / "lab04_cartesian", headless=True)
            self.assertTrue((output / "log.csv").exists())
            self.assertTrue((output / "summary.json").exists())

    def test_lab04_cartesian_comparison_configs_run_headless_when_assets_are_available(self) -> None:
        if not (ROOT / "third_party/mujoco_menagerie/franka_emika_panda/scene.xml").exists():
            self.skipTest("MuJoCo Menagerie has not been fetched")

        for config_path in ("configs/lab04_panda/cartesian_soft.yaml", "configs/lab04_panda/cartesian_stiff.yaml"):
            with self.subTest(config_path=config_path):
                config = load_config(config_path)
                config["sim_time"] = 0.02
                with tempfile.TemporaryDirectory() as tmp:
                    output = lab04_panda.run(config, output_dir=Path(tmp) / "lab04_cartesian_compare", headless=True)
                    self.assertTrue((output / "log.csv").exists())
                    self.assertTrue((output / "summary.json").exists())
