from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.labs.lab04_panda import _virtual_wall_force, _wall_retreat_distance  # noqa: E402


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
