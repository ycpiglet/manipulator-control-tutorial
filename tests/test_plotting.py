from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.plotting import PlotSpec, select_plot_specs  # noqa: E402


class PlotSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.specs: list[PlotSpec] = [
            ("position.png", "Position", "m", ["position"]),
            ("error.png", "Error", "m", ["error"]),
            ("torque.png", "Torque", "N m", ["torque"]),
        ]

    def test_selects_comma_separated_plot_names(self) -> None:
        selected = select_plot_specs(self.specs, "position,error")
        self.assertEqual([spec[0] for spec in selected], ["position.png", "error.png"])

    def test_expands_presets(self) -> None:
        selected = select_plot_specs(self.specs, "essential", presets={"essential": ["position", "error"]})
        self.assertEqual([spec[0] for spec in selected], ["position.png", "error.png"])

    def test_rejects_unknown_plot_names(self) -> None:
        with self.assertRaises(ValueError):
            select_plot_specs(self.specs, "position,missing")
