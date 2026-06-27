from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.mujoco_utils import maybe_launch_viewer  # noqa: E402


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

    def test_viewer_side_panels_can_be_shown_for_debugging(self) -> None:
        launch_passive = Mock(return_value="viewer-handle")
        viewer_module = types.SimpleNamespace(launch_passive=launch_passive)
        mujoco_module = types.SimpleNamespace(viewer=viewer_module)

        with patch.dict(sys.modules, {"mujoco": mujoco_module}):
            maybe_launch_viewer("mujoco", "model", "data", enabled=True, show_ui=True)

        self.assertTrue(launch_passive.call_args.kwargs["show_left_ui"])
        self.assertTrue(launch_passive.call_args.kwargs["show_right_ui"])
