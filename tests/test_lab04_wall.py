from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.labs.lab04_panda import (  # noqa: E402
    _summary,
    _update_viewer_guides,
    _viewer_guides,
    _virtual_wall_force,
    _wall_retreat_distance,
)


class Lab04WallTests(unittest.TestCase):
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

    def test_lab04_viewer_guides_default_to_cartesian_and_wall_modes(self) -> None:
        self.assertTrue(_viewer_guides({}, "cartesian_reach")["enabled"])
        self.assertTrue(_viewer_guides({}, "impedance_wall")["enabled"])
        self.assertFalse(_viewer_guides({}, "joint_trajectory")["enabled"])
        self.assertFalse(_viewer_guides({"viewer_guides": {"enabled": False}}, "cartesian_reach")["enabled"])

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
            target_x_ee=[0.59, 0.02, 0.58],
            wall_config={"wall_x": 0.57},
            wall_penetration=0.02,
        )
        self.assertEqual(scene.ngeom, 2)
        self.assertEqual(scene.geoms[0].geom_type, "box")
        self.assertEqual(scene.geoms[0].pos, [0.57, 0.0, 0.58])
        self.assertEqual(scene.geoms[1].geom_type, "sphere")
        self.assertEqual(scene.geoms[1].rgba, [1.0, 0.48, 0.10, 0.9])
