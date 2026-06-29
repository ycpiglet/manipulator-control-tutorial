from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.labs.lab04_panda import (  # noqa: E402
    _live_status_specs,
    _save_plots,
    _set_initial_state,
    _summary,
    _update_viewer_guides,
    _viewer_guides,
    _virtual_wall_force,
    _virtual_wall_force_components,
    _wall_contact_metrics,
    _wall_retreat_distance,
)


class Lab04WallTests(unittest.TestCase):
    def test_lab04_initial_state_reset_clears_joint_velocity(self) -> None:
        data = types.SimpleNamespace(
            qpos=[9.0] * 9,
            qvel=[1.5] * 9,
            ctrl=[0.0] * 8,
        )

        _set_initial_state(data, [0.1, 0.2, 0.3, -1.0, 0.4, 1.1, -0.5], [0.03, 0.04])

        self.assertEqual(data.qpos[:9], [0.1, 0.2, 0.3, -1.0, 0.4, 1.1, -0.5, 0.03, 0.04])
        self.assertEqual(data.qvel, [0.0] * 9)
        self.assertEqual(data.ctrl[:7], [0.1, 0.2, 0.3, -1.0, 0.4, 1.1, -0.5])
        self.assertEqual(data.ctrl[7], 255.0)

    def test_stiffer_wall_creates_larger_force_and_retreat(self) -> None:
        ee_position = [0.60, 0.0, 0.0]
        ee_velocity = [0.05, 0.0, 0.0]
        soft = {
            "wall_x": 0.57,
            "stiffness": 120.0,
            "damping": 6.0,
            "cartesian_retreat_gain": 0.25,
            "force_retreat_gain": 0.00004,
            "max_cartesian_retreat": 0.05,
        }
        stiff = {
            "wall_x": 0.57,
            "stiffness": 520.0,
            "damping": 24.0,
            "cartesian_retreat_gain": 0.65,
            "force_retreat_gain": 0.00012,
            "max_cartesian_retreat": 0.05,
        }

        soft_force = _virtual_wall_force(ee_position, ee_velocity, soft)
        stiff_force = _virtual_wall_force(ee_position, ee_velocity, stiff)
        soft_retreat = _wall_retreat_distance(ee_position, soft_force, soft)
        stiff_retreat = _wall_retreat_distance(ee_position, stiff_force, stiff)

        self.assertGreater(abs(stiff_force[0]), abs(soft_force[0]))
        self.assertGreater(stiff_retreat, soft_retreat)

    def test_wall_force_components_separate_spring_and_damping(self) -> None:
        ee_position = [0.60, 0.0, 0.0]
        ee_velocity = [0.05, 0.0, 0.0]
        wall = {"wall_x": 0.57, "stiffness": 300.0, "damping": 40.0}

        total, spring, damping = _virtual_wall_force_components(ee_position, ee_velocity, wall)

        self.assertAlmostEqual(spring[0], -9.0)
        self.assertAlmostEqual(damping[0], -2.0)
        self.assertAlmostEqual(total[0], -11.0)
        self.assertEqual(_virtual_wall_force(ee_position, ee_velocity, wall), total)

    def test_lab04_summary_reports_hold_stability_metrics(self) -> None:
        rows = [
            {
                "time": 0.0,
                "error_norm": 0.001,
                "q_0": 0.0,
                "q_1": 0.0,
                "qdot_0": 0.0,
                "qdot_1": 0.0,
                "tau_cmd_0": 0.0,
                "tau_cmd_1": 0.0,
                "cartesian_error_cm": 0.0,
            },
            {
                "time": 1.2,
                "error_norm": 0.002,
                "q_0": 0.003,
                "q_1": -0.004,
                "qdot_0": 0.006,
                "qdot_1": -0.008,
                "tau_cmd_0": 0.01,
                "tau_cmd_1": -0.02,
                "cartesian_error_cm": 0.0,
            },
        ]

        summary = _summary(rows)

        self.assertAlmostEqual(summary["max_abs_qdot"], 0.008)
        self.assertAlmostEqual(summary["max_settled_abs_qdot"], 0.008)
        self.assertAlmostEqual(summary["max_joint_drift_norm"], 0.005)
        self.assertAlmostEqual(summary["max_joint_error_norm"], 0.002)
        self.assertAlmostEqual(summary["max_abs_virtual_wall_spring_force"], 0.0)
        self.assertAlmostEqual(summary["max_abs_virtual_wall_damping_force"], 0.0)
        self.assertIsNone(summary["first_wall_contact_time"])
        self.assertIsNone(summary["last_wall_contact_time"])
        self.assertAlmostEqual(summary["wall_contact_duration"], 0.0)
        self.assertAlmostEqual(summary["wall_contact_fraction"], 0.0)

    def test_wall_contact_metrics_report_timing_and_duration(self) -> None:
        rows = [
            {"time": 0.0, "wall_penetration_cm": 0.0},
            {"time": 0.1, "wall_penetration_cm": 0.2},
            {"time": 0.2, "wall_penetration_cm": 0.3},
            {"time": 0.3, "wall_penetration_cm": 0.0},
        ]

        metrics = _wall_contact_metrics(rows)

        self.assertAlmostEqual(metrics["first_wall_contact_time"], 0.1)
        self.assertAlmostEqual(metrics["last_wall_contact_time"], 0.2)
        self.assertAlmostEqual(metrics["wall_contact_duration"], 0.2)
        self.assertAlmostEqual(metrics["wall_contact_fraction"], 2.0 / 3.0)

    def test_lab04_viewer_guides_default_to_cartesian_and_wall_modes(self) -> None:
        self.assertTrue(_viewer_guides({}, "cartesian_reach")["enabled"])
        self.assertTrue(_viewer_guides({}, "impedance_wall")["enabled"])
        self.assertFalse(_viewer_guides({}, "joint_trajectory")["enabled"])
        self.assertFalse(_viewer_guides({"viewer_guides": {"enabled": False}}, "cartesian_reach")["enabled"])

    def test_lab04_wall_live_status_shows_target_wall_relationship(self) -> None:
        names = [spec.name for spec in _live_status_specs("impedance_wall")]

        self.assertIn("target_x", names)
        self.assertIn("wall_x", names)
        self.assertIn("target_wall_gap_cm", names)
        self.assertIn("wall_penetration_cm", names)

        joint_names = [spec.name for spec in _live_status_specs("joint_trajectory")]
        self.assertNotIn("wall_x", joint_names)

    def test_wall_plot_preset_includes_target_wall_relationship(self) -> None:
        rows = [
            {
                "time": 0.0,
                "x_ee_0": 0.55,
                "x_ee_1": 0.0,
                "x_ee_2": 0.62,
                "target_x_ee_0": 0.61,
                "target_x_ee_1": 0.0,
                "target_x_ee_2": 0.58,
                "tuned_wall_x": 0.57,
                "target_wall_gap_m": 0.04,
                "force_virtual_0": 0.0,
                "force_virtual_spring_0": 0.0,
                "force_virtual_damping_0": 0.0,
                "wall_penetration_cm": 0.0,
                "wall_retreat_cm": 0.0,
                "tau_cmd_0": 0.0,
                "error_norm": 0.0,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            _save_plots(output, rows, "wall")

            self.assertTrue((output / "plots" / "wall_target.png").exists())

    def test_lab04_viewer_guides_draw_target_hand_and_wall(self) -> None:
        def init_geom(geom, geom_type, size, pos, mat, rgba):
            geom.geom_type = geom_type
            geom.pos = [float(value) for value in pos]
            geom.rgba = [float(value) for value in rgba]

        fake_mujoco = types.SimpleNamespace(
            mjv_initGeom=Mock(side_effect=init_geom),
            mjtGeom=types.SimpleNamespace(mjGEOM_SPHERE="sphere", mjGEOM_BOX="box"),
            mjtCatBit=types.SimpleNamespace(mjCAT_DECOR="decor"),
        )
        scene = types.SimpleNamespace(ngeom=0, geoms=[types.SimpleNamespace() for _ in range(4)])
        viewer = types.SimpleNamespace(user_scn=scene)

        _update_viewer_guides(
            fake_mujoco,
            viewer,
            mode="cartesian_reach",
            guide_config={"enabled": True, "hand": True, "target": True, "wall": True},
            ee_position=[0.55, 0.02, 0.58],
            target_x_ee=[0.60, 0.10, 0.59],
            wall_config={},
            wall_penetration=0.0,
        )
        self.assertEqual(scene.ngeom, 2)
        self.assertEqual(scene.geoms[0].geom_type, "sphere")
        self.assertEqual(scene.geoms[0].pos, [0.60, 0.10, 0.59])
        self.assertEqual(scene.geoms[1].geom_type, "sphere")

        _update_viewer_guides(
            fake_mujoco,
            viewer,
            mode="impedance_wall",
            guide_config={"enabled": True, "hand": True, "target": True, "wall": True},
            ee_position=[0.59, 0.02, 0.58],
            target_x_ee=[0.62, 0.01, 0.57],
            wall_config={"wall_x": 0.57},
            wall_penetration=0.02,
        )
        self.assertEqual(scene.ngeom, 3)
        self.assertEqual(scene.geoms[0].geom_type, "box")
        self.assertEqual(scene.geoms[0].pos, [0.57, 0.0, 0.58])
        self.assertEqual(scene.geoms[1].geom_type, "sphere")
        self.assertEqual(scene.geoms[1].pos, [0.62, 0.01, 0.57])
        self.assertEqual(scene.geoms[2].geom_type, "sphere")
        self.assertEqual(scene.geoms[2].rgba, [1.0, 0.48, 0.10, 0.9])
