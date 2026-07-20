from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents" / "validation" / "check_workflow_action_pins.py"
SPEC = importlib.util.spec_from_file_location("check_workflow_action_pins", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


class WorkflowActionPinTests(unittest.TestCase):
    def test_repository_workflows_pin_every_external_action(self) -> None:
        references = CHECKER.external_action_references(CHECKER.workflow_files())
        self.assertEqual(len(references), 12)
        self.assertEqual(CHECKER.unpinned_references(references), [])

    def test_mutable_refs_fail_while_local_and_docker_actions_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.yml"
            path.write_text(
                """steps:
  - uses: actions/checkout@v4
  - uses: owner/action@34e114876b0b11c390a56381ad16ebd13914f8d5
  - uses: ./.github/actions/local
  - uses: docker://alpine:3.20
""",
                encoding="utf-8",
            )
            references = CHECKER.external_action_references([path])
            self.assertEqual(len(references), 2)
            self.assertEqual(
                CHECKER.unpinned_references(references),
                [(path, 2, "actions/checkout@v4")],
            )


if __name__ == "__main__":
    unittest.main()
