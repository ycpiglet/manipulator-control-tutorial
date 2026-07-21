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
    _cartesian_target_position,
    _live_status_specs,
    _plot_event_markers,
    _save_plots,
    _set_initial_state,
    _summary,
    _update_viewer_guides,
    _viewer_guides,
    _virtual_wall_force,
    _virtual_wall_force_components,
    _wall_contact_metrics,
    _wall_phase,
    _wall_retreat_distance,
    _wall_target_crossing_metrics,
)
from mclab.application.artifacts import write_manifest  # noqa: E402


class DummyLiveTuning:
    def value(self, _name: str, default: float) -> float:
        return default


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

    def test_cartesian_target_waypoints_use_smooth_time_interpolation(self) -> None:
        config = {
            "cartesian_target": {
                "waypoints": [
                    {"time": 0.0, "position": [0.50, 0.0, 0.58]},
                    {"time": 1.0, "position": [0.60, 0.0, 0.58]},
                    {"time": 2.0, "position": [0.52, 0.0, 0.58]},
                ]
            }
        }
        tuning = DummyLiveTuning()
        initial = [0.40, 0.0, 0.58]

        self.assertEqual(_cartesian_target_position(config, tuning, initial, 1.0, time=-0.1), [0.50, 0.0, 0.58])
        self.assertEqual(_cartesian_target_position(config, tuning, initial, 1.0, time=2.5), [0.52, 0.0, 0.58])
        halfway = _cartesian_target_position(config, tuning, initial, 1.0, time=0.5)

        self.assertAlmostEqual(halfway[0], 0.55)
        self.assertAlmostEqual(halfway[1], 0.0)
        self.assertAlmostEqual(halfway[2], 0.58)

    def test_force_retreat_gain_changes_retreat_with_same_wall_force(self) -> None:
        ee_position = [0.60, 0.0, 0.0]
        wall_force = [-12.0, 0.0, 0.0]
        low_gain = {
            "wall_x": 0.57,
            "cartesian_retreat_gain": 0.20,
            "force_retreat_gain": 0.00002,
            "max_cartesian_retreat": 0.05,
        }
        high_gain = {
            **low_gain,
            "force_retreat_gain": 0.00035,
        }

        low_retreat = _wall_retreat_distance(ee_position, wall_force, low_gain)
        high_retreat = _wall_retreat_distance(ee_position, wall_force, high_gain)

        self.assertGreater(high_retreat, low_retreat)

    def test_wall_phase_separates_target_command_from_contact(self) -> None:
        self.assertEqual(
            _wall_phase(target_wall_gap_m=-0.02, wall_penetration_m=0.0, wall_force_x=0.0),
            "Clear",
        )
        self.assertEqual(
            _wall_phase(target_wall_gap_m=0.0, wall_penetration_m=0.0, wall_force_x=0.0),
            "At wall",
        )
        self.assertEqual(
            _wall_phase(target_wall_gap_m=0.03, wall_penetration_m=0.0, wall_force_x=0.0),
            "Target past wall",
        )
        self.assertEqual(
            _wall_phase(target_wall_gap_m=0.03, wall_penetration_m=0.004, wall_force_x=-8.0),
            "Contact: wall pushing back",
        )

    def test_lab04_summary_reports_hold_stability_metrics(self) -> None:
        rows = [
            {
                "time": 0.0,
                "error_norm": 0.001,
                "q_0": 0.0,
                "q_1": 0.0,
                "qdot_0": 0.0,
                "qdot_1": 0.0,
                "xdot_ee_0": 0.0,
                "xdot_ee_1": 0.0,
                "xdot_ee_2": 0.0,
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
                "xdot_ee_0": 0.03,
                "xdot_ee_1": -0.04,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": 0.01,
                "tau_cmd_1": -0.02,
                "cartesian_error_cm": 0.0,
            },
        ]

        summary = _summary(rows)

        self.assertAlmostEqual(summary["max_abs_qdot"], 0.008)
        self.assertAlmostEqual(summary["max_settled_abs_qdot"], 0.008)
        self.assertAlmostEqual(summary["max_hand_x_speed"], 0.03)
        self.assertAlmostEqual(summary["max_hand_speed"], 0.05)
        self.assertAlmostEqual(summary["max_joint_drift_norm"], 0.005)
        self.assertAlmostEqual(summary["max_joint_error_norm"], 0.002)
        self.assertAlmostEqual(summary["max_abs_virtual_wall_spring_force"], 0.0)
        self.assertAlmostEqual(summary["max_abs_virtual_wall_damping_force"], 0.0)
        self.assertIsNone(summary["first_wall_contact_time"])
        self.assertIsNone(summary["last_wall_contact_time"])
        self.assertAlmostEqual(summary["wall_contact_duration"], 0.0)
        self.assertAlmostEqual(summary["wall_contact_fraction"], 0.0)

    def test_lab04_summary_reports_target_wall_command_phase(self) -> None:
        rows = [
            {
                "time": 0.0,
                "error_norm": 0.0,
                "q_0": 0.0,
                "qdot_0": 0.0,
                "xdot_ee_0": 0.0,
                "xdot_ee_1": 0.0,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": 0.0,
                "target_wall_gap_cm": -2.0,
                "wall_phase": "Clear",
                "wall_penetration_cm": 0.0,
                "wall_penetration": 0.0,
                "wall_retreat_cm": 0.0,
                "force_virtual_0": 0.0,
                "force_virtual_spring_0": 0.0,
                "force_virtual_damping_0": 0.0,
                "cartesian_error_cm": 0.1,
            },
            {
                "time": 0.4,
                "error_norm": 0.01,
                "q_0": 0.0,
                "qdot_0": 0.0,
                "xdot_ee_0": 0.0,
                "xdot_ee_1": 0.0,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": 0.0,
                "target_wall_gap_cm": 3.5,
                "wall_phase": "Target past wall",
                "wall_penetration_cm": 0.0,
                "wall_penetration": 0.0,
                "wall_retreat_cm": 0.0,
                "force_virtual_0": 0.0,
                "force_virtual_spring_0": 0.0,
                "force_virtual_damping_0": 0.0,
                "cartesian_error_cm": 0.2,
            },
            {
                "time": 0.8,
                "error_norm": 0.02,
                "q_0": 0.0,
                "qdot_0": 0.0,
                "xdot_ee_0": 0.0,
                "xdot_ee_1": 0.0,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": 0.0,
                "target_wall_gap_cm": 1.0,
                "wall_phase": "Contact: wall pushing back",
                "wall_penetration_cm": 0.4,
                "wall_penetration": 0.004,
                "wall_retreat_cm": 0.1,
                "force_virtual_0": -2.0,
                "force_virtual_spring_0": -1.6,
                "force_virtual_damping_0": -0.4,
                "cartesian_error_cm": 0.3,
            },
        ]

        summary = _summary(rows)
        markers = _plot_event_markers(rows)

        self.assertAlmostEqual(summary["max_target_wall_gap_cm"], 3.5)
        self.assertAlmostEqual(summary["peak_target_wall_gap_time"], 0.4)
        self.assertAlmostEqual(summary["final_target_wall_gap_cm"], 1.0)
        self.assertEqual(summary["final_wall_phase"], "Contact: wall pushing back")
        self.assertIn((0.4, "target crosses wall / deepest target"), markers["wall_target"])

    def test_wall_target_crossing_metrics_report_back_away_timing(self) -> None:
        rows = [
            {"time": 0.0, "target_wall_gap_cm": -1.0},
            {"time": 0.2, "target_wall_gap_cm": 2.0},
            {"time": 0.5, "target_wall_gap_cm": 3.0},
            {"time": 0.8, "target_wall_gap_cm": -0.5},
        ]

        metrics = _wall_target_crossing_metrics(rows)

        self.assertAlmostEqual(metrics["first_target_wall_cross_time"], 0.2)
        self.assertAlmostEqual(metrics["last_target_wall_cross_time"], 0.5)
        self.assertAlmostEqual(metrics["target_past_wall_duration"], 0.6)
        self.assertAlmostEqual(metrics["target_past_wall_fraction"], 0.75)
        self.assertEqual(metrics["target_wall_cross_episodes"], 1)
        self.assertAlmostEqual(metrics["first_target_wall_return_time"], 0.8)
        self.assertTrue(metrics["target_returned_before_wall"])

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
        self.assertEqual(metrics["wall_contact_episodes"], 1)
        self.assertAlmostEqual(metrics["first_wall_release_time"], 0.3)
        self.assertTrue(metrics["wall_released_after_contact"])

    def test_lab04_summary_reports_key_moment_times(self) -> None:
        rows = [
            {
                "time": 0.0,
                "error_norm": 0.0,
                "q_0": 0.0,
                "qdot_0": 0.0,
                "xdot_ee_0": 0.0,
                "xdot_ee_1": 0.0,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": 0.0,
                "wall_penetration_cm": 0.0,
                "wall_penetration": 0.0,
                "wall_retreat_cm": 0.0,
                "force_virtual_0": 0.0,
                "force_virtual_spring_0": 0.0,
                "force_virtual_damping_0": 0.0,
                "cartesian_error_cm": 0.2,
            },
            {
                "time": 0.4,
                "error_norm": 0.02,
                "q_0": 0.01,
                "qdot_0": 0.1,
                "xdot_ee_0": 0.2,
                "xdot_ee_1": 0.0,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": 1.0,
                "wall_penetration_cm": 0.8,
                "wall_penetration": 0.008,
                "wall_retreat_cm": 0.2,
                "force_virtual_0": -4.0,
                "force_virtual_spring_0": -3.0,
                "force_virtual_damping_0": -1.0,
                "cartesian_error_cm": 1.4,
            },
            {
                "time": 0.7,
                "error_norm": 0.03,
                "q_0": 0.02,
                "qdot_0": 0.3,
                "xdot_ee_0": 0.1,
                "xdot_ee_1": 0.3,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": -2.0,
                "wall_penetration_cm": 1.6,
                "wall_penetration": 0.016,
                "wall_retreat_cm": 0.4,
                "force_virtual_0": -9.0,
                "force_virtual_spring_0": -6.0,
                "force_virtual_damping_0": -3.0,
                "cartesian_error_cm": 0.5,
            },
        ]

        summary = _summary(rows)

        self.assertAlmostEqual(summary["peak_wall_penetration_time"], 0.7)
        self.assertAlmostEqual(summary["peak_wall_force_time"], 0.7)
        self.assertAlmostEqual(summary["peak_wall_damping_force_time"], 0.7)
        self.assertAlmostEqual(summary["peak_cartesian_error_time"], 0.4)
        self.assertAlmostEqual(summary["peak_hand_speed_time"], 0.7)

    def test_lab04_wall_plots_mark_key_moments(self) -> None:
        rows = [
            {
                "time": 0.0,
                "error_norm": 0.0,
                "q_0": 0.0,
                "qdot_0": 0.0,
                "xdot_ee_0": 0.0,
                "xdot_ee_1": 0.0,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": 0.0,
                "wall_penetration_cm": 0.0,
                "wall_penetration": 0.0,
                "wall_retreat_cm": 0.0,
                "force_virtual_0": 0.0,
                "force_virtual_spring_0": 0.0,
                "force_virtual_damping_0": 0.0,
                "cartesian_error_cm": 0.2,
            },
            {
                "time": 0.4,
                "error_norm": 0.02,
                "q_0": 0.01,
                "qdot_0": 0.1,
                "xdot_ee_0": 0.2,
                "xdot_ee_1": 0.0,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": 1.0,
                "wall_penetration_cm": 0.8,
                "wall_penetration": 0.008,
                "wall_retreat_cm": 0.2,
                "force_virtual_0": -4.0,
                "force_virtual_spring_0": -3.0,
                "force_virtual_damping_0": -1.0,
                "cartesian_error_cm": 1.4,
            },
            {
                "time": 0.7,
                "error_norm": 0.03,
                "q_0": 0.02,
                "qdot_0": 0.3,
                "xdot_ee_0": 0.1,
                "xdot_ee_1": 0.3,
                "xdot_ee_2": 0.0,
                "tau_cmd_0": -2.0,
                "wall_penetration_cm": 1.6,
                "wall_penetration": 0.016,
                "wall_retreat_cm": 0.4,
                "force_virtual_0": -9.0,
                "force_virtual_spring_0": -6.0,
                "force_virtual_damping_0": -3.0,
                "cartesian_error_cm": 0.5,
            },
        ]

        markers = _plot_event_markers(rows)

        self.assertEqual(
            markers["virtual_wall"],
            (
                (0.4, "first contact"),
                (0.7, "peak penetration / peak force / peak damping / peak speed"),
            ),
        )
        self.assertEqual(markers["wall_target"], ((0.4, "first contact"), (0.7, "peak penetration")))
        self.assertEqual(markers["cartesian_error"], ((0.4, "peak error"),))

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
        self.assertIn("wall_force_x", names)
        self.assertIn("wall_spring_force_x", names)
        self.assertIn("wall_damping_force_x", names)
        self.assertIn("wall_retreat_cm", names)
        self.assertIn("wall_phase", names)

        joint_names = [spec.name for spec in _live_status_specs("joint_trajectory")]
        self.assertNotIn("wall_x", joint_names)
        self.assertNotIn("wall_spring_force_x", joint_names)

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
            output = Path(tmp) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                '{"lab_name":"lab04_panda","config_name":"wall_plot_test","samples":1,"duration":0.0}',
                encoding="utf-8",
            )
            write_manifest(
                output,
                scenario_id="lab04.wall-plot-test",
                status="running",
                config={},
            )
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
            wall_force=[0.0, 0.0, 0.0],
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
            wall_force=[-12.0, 0.0, 0.0],
            wall_config={"wall_x": 0.57},
            wall_penetration=0.02,
        )
        self.assertEqual(scene.ngeom, 4)
        self.assertEqual(scene.geoms[0].geom_type, "box")
        self.assertEqual(scene.geoms[0].pos, [0.57, 0.0, 0.58])
        self.assertEqual(scene.geoms[1].geom_type, "sphere")
        self.assertEqual(scene.geoms[1].pos, [0.62, 0.01, 0.57])
        self.assertEqual(scene.geoms[2].geom_type, "sphere")
        self.assertEqual(scene.geoms[2].rgba, [1.0, 0.48, 0.10, 0.9])
        self.assertEqual(scene.geoms[3].geom_type, "box")
        self.assertLess(scene.geoms[3].pos[0], 0.59)
        self.assertAlmostEqual(scene.geoms[3].pos[2], 0.62)
