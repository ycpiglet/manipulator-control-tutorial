from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.mujoco_utils import (  # noqa: E402
    add_viewer_box,
    add_viewer_sphere,
    hide_viewer_side_panels,
    maybe_launch_viewer,
    realtime_wall_start,
    reset_viewer_overlays,
    sync_paused_viewer,
    sync_viewer,
)
from mclab.sim.runner import run_fixed_step_loop  # noqa: E402


class ViewerUtilityTests(unittest.TestCase):
    def test_viewer_side_panels_are_hidden_by_default(self) -> None:
        launch_passive = Mock(return_value="viewer-handle")
        viewer_module = types.SimpleNamespace(launch_passive=launch_passive)
        mujoco_module = types.SimpleNamespace(viewer=viewer_module)

        with patch.dict(sys.modules, {"mujoco": mujoco_module}):
            handle = maybe_launch_viewer("mujoco", "model", "data", enabled=True)

        self.assertEqual(handle, "viewer-handle")
        launch_passive.assert_called_once_with(
            "model",
            "data",
            key_callback=None,
            show_left_ui=False,
            show_right_ui=False,
        )

    def test_sync_paused_viewer_keeps_viewer_responsive(self) -> None:
        viewer = types.SimpleNamespace(sync=Mock())

        sync_paused_viewer(viewer, interval=0.0)

        viewer.sync.assert_called_once_with()

    def test_hide_viewer_side_panels_locks_private_mujoco_ui_flags(self) -> None:
        sim = types.SimpleNamespace(ui0_enable=True, ui1_enable=True)
        viewer = types.SimpleNamespace(_get_sim=lambda: sim)

        hide_viewer_side_panels(viewer)

        self.assertFalse(sim.ui0_enable)
        self.assertFalse(sim.ui1_enable)

    def test_sync_viewer_rehides_side_panels_if_viewer_reenables_them(self) -> None:
        sim = types.SimpleNamespace(ui0_enable=True, ui1_enable=True)

        def sync() -> None:
            sim.ui0_enable = True
            sim.ui1_enable = True

        viewer = types.SimpleNamespace(_get_sim=lambda: sim, sync=Mock(side_effect=sync))
        data = types.SimpleNamespace(time=1.0)

        sync_viewer(viewer, data)

        viewer.sync.assert_called_once_with()
        self.assertFalse(sim.ui0_enable)
        self.assertFalse(sim.ui1_enable)

    def test_fixed_step_loop_rehides_side_panels_around_direct_sync(self) -> None:
        sim = types.SimpleNamespace(ui0_enable=True, ui1_enable=True)

        def sync() -> None:
            sim.ui0_enable = True
            sim.ui1_enable = True

        def step(_model: object, data: object) -> None:
            data.time = 0.1

        mujoco = types.SimpleNamespace(mj_step=step)
        viewer = types.SimpleNamespace(_get_sim=lambda: sim, sync=Mock(side_effect=sync))
        data = types.SimpleNamespace(time=0.0)

        run_fixed_step_loop(
            mujoco=mujoco,
            model=object(),
            data=data,
            sim_time=0.1,
            step_callback=lambda _time: None,
            viewer=viewer,
        )

        viewer.sync.assert_called_once_with()
        self.assertFalse(sim.ui0_enable)
        self.assertFalse(sim.ui1_enable)

    def test_sync_viewer_uses_playback_speed_for_realtime_pacing(self) -> None:
        viewer = types.SimpleNamespace(sync=Mock())
        data = types.SimpleNamespace(time=3.0)

        with (
            patch("mclab.sim.mujoco_utils.perf_counter", return_value=12.0),
            patch("mclab.sim.mujoco_utils.sleep") as sleeper,
        ):
            sync_viewer(viewer, data, realtime=True, wall_start=10.0, sim_start=1.0, speed_scale=0.5)

        viewer.sync.assert_called_once_with()
        sleeper.assert_called_once_with(0.05)

        viewer.sync.reset_mock()
        sleeper.reset_mock()

        with (
            patch("mclab.sim.mujoco_utils.perf_counter", return_value=12.0),
            patch("mclab.sim.mujoco_utils.sleep") as sleeper,
        ):
            sync_viewer(viewer, data, realtime=True, wall_start=10.0, sim_start=1.0, speed_scale=4.0)

        viewer.sync.assert_called_once_with()
        sleeper.assert_not_called()

    def test_realtime_wall_start_accounts_for_playback_speed(self) -> None:
        with patch("mclab.sim.mujoco_utils.perf_counter", return_value=20.0):
            wall_start = realtime_wall_start(data_time=5.0, sim_start=1.0, speed_scale=0.5)

        self.assertEqual(wall_start, 12.0)

    def test_viewer_overlay_helpers_add_and_reset_user_geoms(self) -> None:
        def init_geom(geom, geom_type, size, pos, mat, rgba):
            geom.geom_type = geom_type
            geom.size = [float(value) for value in size]
            geom.pos = [float(value) for value in pos]
            geom.mat = [float(value) for value in mat]
            geom.rgba = [float(value) for value in rgba]

        fake_mujoco = types.SimpleNamespace(
            mjv_initGeom=Mock(side_effect=init_geom),
            mjtGeom=types.SimpleNamespace(mjGEOM_SPHERE="sphere", mjGEOM_BOX="box"),
            mjtCatBit=types.SimpleNamespace(mjCAT_DECOR="decor"),
        )
        scene = types.SimpleNamespace(
            ngeom=0,
            geoms=[
                types.SimpleNamespace(category=None, transparent=0),
                types.SimpleNamespace(category=None, transparent=0),
            ],
        )
        viewer = types.SimpleNamespace(user_scn=scene)

        self.assertTrue(add_viewer_sphere(fake_mujoco, viewer, [0.1, 0.2, 0.3], radius=0.04, rgba=[0, 1, 0, 0.8]))
        self.assertTrue(
            add_viewer_box(
                fake_mujoco,
                viewer,
                [0.6, 0.0, 0.5],
                half_size=[0.01, 0.2, 0.3],
                rgba=[1, 0, 0, 0.25],
            )
        )

        self.assertEqual(scene.ngeom, 2)
        self.assertEqual(scene.geoms[0].geom_type, "sphere")
        self.assertEqual(scene.geoms[0].size, [0.04, 0.04, 0.04])
        self.assertEqual(scene.geoms[0].category, "decor")
        self.assertEqual(scene.geoms[0].transparent, 1)
        self.assertEqual(scene.geoms[1].geom_type, "box")
        self.assertEqual(scene.geoms[1].pos, [0.6, 0.0, 0.5])

        reset_viewer_overlays(viewer)
        self.assertEqual(scene.ngeom, 0)
