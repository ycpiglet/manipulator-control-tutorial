from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.mujoco_utils import maybe_launch_viewer  # noqa: E402


class MujocoViewerLaunchTests(unittest.TestCase):
    def test_viewer_side_panels_are_hidden_by_default(self) -> None:
        launched_kwargs = self._launch_kwargs(show_ui=False)

        self.assertFalse(launched_kwargs["show_left_ui"])
        self.assertFalse(launched_kwargs["show_right_ui"])

    def test_viewer_side_panels_stay_hidden_even_if_requested(self) -> None:
        launched_kwargs = self._launch_kwargs(show_ui=True)

        self.assertFalse(launched_kwargs["show_left_ui"])
        self.assertFalse(launched_kwargs["show_right_ui"])

    def _launch_kwargs(self, *, show_ui: bool) -> dict[str, object]:
        def fake_launch_passive(*_args: object, **kwargs: object) -> dict[str, object]:
            return kwargs

        fake_mujoco = types.ModuleType("mujoco")
        fake_mujoco.viewer = types.SimpleNamespace(launch_passive=fake_launch_passive)

        with patch.dict(sys.modules, {"mujoco": fake_mujoco}):
            return maybe_launch_viewer(
                fake_mujoco,
                object(),
                object(),
                enabled=True,
                show_ui=show_ui,
            )
