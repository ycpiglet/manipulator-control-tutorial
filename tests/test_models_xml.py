from __future__ import annotations

import unittest
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]


class ModelXmlTests(unittest.TestCase):
    def test_implemented_mujoco_models_are_parseable_xml(self) -> None:
        for path in [
            ROOT / "models/lab01_msd/scene.xml",
            ROOT / "models/lab02_pid/scene.xml",
            ROOT / "models/lab03_2dof/scene.xml",
        ]:
            with self.subTest(path=path):
                tree = ElementTree.parse(path)
                self.assertEqual(tree.getroot().tag, "mujoco")

    def test_menagerie_panda_model_is_present_when_assets_are_fetched(self) -> None:
        path = ROOT / "third_party/mujoco_menagerie/franka_emika_panda/scene.xml"
        if not path.exists():
            self.skipTest("MuJoCo Menagerie has not been fetched")
        tree = ElementTree.parse(path)
        self.assertEqual(tree.getroot().tag, "mujoco")
