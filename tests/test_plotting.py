from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.plotting import PlotSpec, _apply_event_markers, select_plot_specs  # noqa: E402


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

    def test_applies_event_markers_to_axis(self) -> None:
        class FakeAxis:
            def __init__(self) -> None:
                self.lines: list[tuple[float, str]] = []
                self.labels: list[tuple[float, str, float]] = []

            def get_xaxis_transform(self) -> str:
                return "xaxis-transform"

            def axvline(self, x: float, *, color: str, linestyle: str, linewidth: float, alpha: float) -> None:
                del color, linewidth, alpha
                self.lines.append((x, linestyle))

            def text(self, x: float, y: float, label: str, **kwargs: object) -> None:
                assert kwargs["transform"] == "xaxis-transform"
                self.labels.append((x, label, y))

        axis = FakeAxis()

        _apply_event_markers(axis, [(0.4, "first contact"), (0.7, "peak force")])

        self.assertEqual(axis.lines, [(0.4, "--"), (0.7, "--")])
        self.assertEqual(axis.labels[0], (0.4, "first contact", 0.98))
        self.assertEqual(axis.labels[1], (0.7, "peak force", 0.86))
