from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.one_dof import SliderHandles, reset_slider_plant_state, update_slider_viewer_guides  # noqa: E402


class OneDofViewerGuideTests(unittest.TestCase):
    def test_reset_slider_plant_state_restores_initial_position_velocity_and_control(self) -> None:
        fake_mujoco = types.SimpleNamespace(mj_forward=Mock())
        model = types.SimpleNamespace()
        data = types.SimpleNamespace(time=3.2, qpos=[0.9], qvel=[-2.0], ctrl=[18.0])
        handles = SliderHandles(joint_id=0, body_id=0, actuator_id=0, qpos_adr=0, dof_adr=0)

        reset_slider_plant_state(
            fake_mujoco,
            model,
            data,
            handles,
            {"initial_position": -0.2, "initial_velocity": 0.35},
        )

        self.assertEqual(data.time, 0.0)
        self.assertEqual(data.qpos[0], -0.2)
        self.assertEqual(data.qvel[0], 0.35)
        self.assertEqual(data.ctrl[0], 0.0)
        fake_mujoco.mj_forward.assert_called_once_with(model, data)

    def test_slider_viewer_guides_draw_reference_target_and_force(self) -> None:
        def init_geom(geom, geom_type, size, pos, mat, rgba):
            geom.geom_type = geom_type
            geom.size = [float(value) for value in size]
            geom.pos = [float(value) for value in pos]
            geom.rgba = [float(value) for value in rgba]

        fake_mujoco = types.SimpleNamespace(
            mjv_initGeom=Mock(side_effect=init_geom),
            mjtGeom=types.SimpleNamespace(mjGEOM_BOX="box"),
            mjtCatBit=types.SimpleNamespace(mjCAT_DECOR="decor"),
        )
        scene = types.SimpleNamespace(
            ngeom=0,
            geoms=[
                types.SimpleNamespace(category=None, transparent=0),
                types.SimpleNamespace(category=None, transparent=0),
                types.SimpleNamespace(category=None, transparent=0),
            ],
        )
        viewer = types.SimpleNamespace(user_scn=scene)

        update_slider_viewer_guides(
            fake_mujoco,
            viewer,
            position=0.2,
            force=45.0,
            reference_position=0.0,
            target_position=0.4,
        )

        self.assertEqual(scene.ngeom, 3)
        self.assertEqual(scene.geoms[0].geom_type, "box")
        self.assertEqual(scene.geoms[0].pos, [0.0, -0.11, 0.045])
        self.assertEqual(scene.geoms[1].pos, [0.4, 0.11, 0.045])
        self.assertEqual(scene.geoms[1].rgba, [0.1, 0.82, 0.28, 0.82])
        self.assertGreater(scene.geoms[2].pos[0], 0.2)
        self.assertEqual(scene.geoms[2].rgba, [1.0, 0.48, 0.1, 0.84])

    def test_slider_viewer_guides_can_be_disabled(self) -> None:
        fake_mujoco = types.SimpleNamespace(
            mjv_initGeom=Mock(),
            mjtGeom=types.SimpleNamespace(mjGEOM_BOX="box"),
        )
        scene = types.SimpleNamespace(ngeom=2, geoms=[types.SimpleNamespace(), types.SimpleNamespace()])
        viewer = types.SimpleNamespace(user_scn=scene)

        update_slider_viewer_guides(fake_mujoco, viewer, position=0.0, force=0.0, enabled=False)

        self.assertEqual(scene.ngeom, 0)
        fake_mujoco.mjv_initGeom.assert_not_called()


if __name__ == "__main__":
    unittest.main()
