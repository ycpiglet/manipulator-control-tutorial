from __future__ import annotations

import importlib.util
import json
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
        action_lock = CHECKER.load_action_lock()
        self.assertEqual(len(references), 15)
        self.assertEqual(CHECKER.unpinned_references(references), [])
        self.assertEqual(CHECKER.action_lock_metadata_errors(action_lock), [])
        self.assertEqual(CHECKER.reviewed_reference_errors(references, action_lock), [])
        self.assertEqual(len(action_lock["actions"]), 5)
        self.assertEqual(
            {record["runtime"] for record in action_lock["actions"].values()},
            {"node24"},
        )

    def test_mutable_refs_and_docker_tags_fail_while_immutable_refs_pass(self) -> None:
        action_lock = CHECKER.load_action_lock()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.yml"
            path.write_text(
                """steps:
  - uses: actions/checkout@v4
  - uses: owner/action@34e114876b0b11c390a56381ad16ebd13914f8d5
  - uses: docker://alpine:3.20
  - uses: docker://alpine@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
""",
                encoding="utf-8",
            )
            references = CHECKER.external_action_references(
                [path],
                repository_root=Path(tmp),
            )
            self.assertEqual(len(references), 4)
            self.assertEqual(
                CHECKER.unpinned_references(references),
                [
                    (path, 2, "actions/checkout@v4"),
                    (path, 4, "docker://alpine:3.20"),
                ],
            )
            reviewed_errors = CHECKER.reviewed_reference_errors(references, action_lock)
            self.assertTrue(
                any(
                    error.startswith("UNREVIEWED")
                    and "docker://alpine@sha256:" in error
                    for error in reviewed_errors
                )
            )

    def test_uses_key_spacing_and_quotes_cannot_bypass_scanning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.yml"
            path.write_text(
                """steps:
  - uses : actions/checkout@v4
  - "uses": actions/setup-python@v7
  - {uses: actions/cache@v6}
  - {name: Inline, "uses" : "actions/upload-artifact@v7"}
  - ? uses
    : WtfJoke/setup-tectonic@v4
  - "\\x75ses": actions/checkout@v6
  - run: |
      echo '{uses: ignored/action@v1}'
  # uses: ignored/comment@v1
""",
                encoding="utf-8",
            )
            references = CHECKER.external_action_references(
                [path],
                repository_root=Path(tmp),
            )

        self.assertEqual(
            [reference for _path, _line, reference in references],
            [
                "actions/checkout@v4",
                "actions/setup-python@v7",
                "actions/cache@v6",
                "actions/upload-artifact@v7",
                "WtfJoke/setup-tectonic@v4",
                "actions/checkout@v6",
            ],
        )
        self.assertEqual(len(CHECKER.unpinned_references(references)), 6)

    def test_local_composite_action_dependencies_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflows = root / "workflows"
            local_actions = root / "actions"
            workflows.mkdir()
            action_dir = local_actions / "demo"
            action_dir.mkdir(parents=True)
            (workflows / "ci.yml").write_text(
                "steps:\n  - uses: ./actions/demo\n",
                encoding="utf-8",
            )
            action_path = action_dir / "action.yml"
            action_path.write_text(
                "runs:\n  using: composite\n  steps:\n    - uses: attacker/action@v1\n",
                encoding="utf-8",
            )
            paths = CHECKER.workflow_files(workflows)
            references = CHECKER.external_action_references(paths, repository_root=root)

        self.assertEqual(
            [reference for _path, _line, reference in references],
            ["attacker/action@v1"],
        )
        self.assertEqual(len(CHECKER.unpinned_references(references)), 1)

    def test_local_non_composite_actions_are_rejected(self) -> None:
        for runtime, descriptor in (
            (
                "docker",
                "runs: {using: docker, image: 'docker://alpine:latest'}\n",
            ),
            ("node24", "runs:\n  using: node24\n  main: dist/index.js\n"),
        ):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                workflows = root / "workflows"
                action_dir = root / "actions" / "demo"
                workflows.mkdir()
                action_dir.mkdir(parents=True)
                (workflows / "ci.yml").write_text(
                    "steps:\n  - uses: ./actions/demo\n",
                    encoding="utf-8",
                )
                (action_dir / "action.yml").write_text(
                    descriptor,
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "non-composite local actions are not allowed",
                ):
                    CHECKER.external_action_references(
                        CHECKER.workflow_files(workflows),
                        repository_root=root,
                    )

    def test_ambiguous_or_incomplete_local_action_metadata_is_rejected(self) -> None:
        fixtures = (
            (
                "duplicate-runs",
                "runs:\n  using: composite\nruns:\n  using: docker\n",
                "exactly one runs mapping",
            ),
            (
                "duplicate-escaped-using",
                'runs:\n  using: composite\n  "\\x75sing": docker\n',
                "non-composite local actions are not allowed",
            ),
            (
                "multiple-documents",
                "runs:\n  using: composite\n---\nruns:\n  using: composite\n",
                "one YAML mapping",
            ),
            (
                "empty-document-prefix",
                "---\n---\nruns:\n  using: composite\n",
                "one YAML mapping",
            ),
            (
                "non-mapping-document",
                "- runs:\n    using: composite\n",
                "one YAML mapping",
            ),
            (
                "missing-runs",
                "name: incomplete action\n",
                "exactly one runs mapping",
            ),
        )
        for name, descriptor, expected_error in fixtures:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                workflows = root / "workflows"
                action_dir = root / "actions" / "demo"
                workflows.mkdir()
                action_dir.mkdir(parents=True)
                (workflows / "ci.yml").write_text(
                    "steps:\n  - uses: ./actions/demo\n",
                    encoding="utf-8",
                )
                (action_dir / "action.yml").write_text(
                    descriptor,
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(ValueError, expected_error):
                    CHECKER.external_action_references(
                        CHECKER.workflow_files(workflows),
                        repository_root=root,
                    )

    def test_local_reusable_workflow_dependencies_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflows = root / "workflows"
            workflows.mkdir()
            entry = workflows / "ci.yml"
            entry.write_text(
                "jobs:\n  call:\n    uses: ./workflows/reusable.yml\n",
                encoding="utf-8",
            )
            reusable = workflows / "reusable.yml"
            reusable.write_text(
                "jobs:\n  nested:\n    steps:\n      - uses: attacker/action@v1\n",
                encoding="utf-8",
            )

            references = CHECKER.external_action_references(
                [entry],
                repository_root=root,
            )

        self.assertEqual(
            [reference for _path, _line, reference in references],
            ["attacker/action@v1"],
        )

    @unittest.skipIf(sys.platform.startswith("win"), "file symlink fixture requires POSIX")
    def test_local_reusable_workflow_symlink_cannot_escape_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            root = temp / "repo"
            workflows = root / "workflows"
            workflows.mkdir(parents=True)
            entry = workflows / "ci.yml"
            entry.write_text(
                "jobs:\n  call:\n    uses: ./workflows/reusable.yml\n",
                encoding="utf-8",
            )
            outside = temp / "outside-reusable.yml"
            outside.write_text(
                "jobs:\n  nested:\n    steps:\n      - uses: attacker/action@v1\n",
                encoding="utf-8",
            )
            (workflows / "reusable.yml").symlink_to(outside)

            with self.assertRaisesRegex(ValueError, "escapes repository root"):
                CHECKER.external_action_references(
                    [entry],
                    repository_root=root,
                )

    @unittest.skipIf(sys.platform.startswith("win"), "file symlink fixture requires POSIX")
    def test_local_action_definition_symlink_cannot_escape_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            root = temp / "repo"
            workflows = root / ".github" / "workflows"
            action_dir = root / ".github" / "actions" / "demo"
            workflows.mkdir(parents=True)
            action_dir.mkdir(parents=True)
            (workflows / "ci.yml").write_text(
                "steps:\n  - uses: ./.github/actions/demo\n",
                encoding="utf-8",
            )
            outside = temp / "outside-action.yml"
            outside.write_text(
                "runs:\n  using: composite\n  steps:\n    - uses: attacker/action@v1\n",
                encoding="utf-8",
            )
            (action_dir / "action.yml").symlink_to(outside)

            with self.assertRaisesRegex(ValueError, "definition escapes repository root"):
                CHECKER.external_action_references(
                    CHECKER.workflow_files(workflows),
                    repository_root=root,
                )

    @unittest.skipIf(sys.platform.startswith("win"), "file symlink fixture requires POSIX")
    def test_top_level_workflow_symlink_cannot_escape_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            root = temp / "repo"
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            outside = temp / "outside-workflow.yml"
            outside.write_text(
                "steps:\n  - uses: attacker/action@v1\n",
                encoding="utf-8",
            )
            (workflows / "ci.yml").symlink_to(outside)

            with self.assertRaisesRegex(ValueError, "action source escapes repository root"):
                CHECKER.external_action_references(
                    CHECKER.workflow_files(workflows),
                    repository_root=root,
                )

    def test_reviewed_lock_rejects_wrong_sha_comment_and_unknown_action(self) -> None:
        action_lock = CHECKER.load_action_lock()
        checkout_sha = action_lock["actions"]["actions/checkout"]["sha"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.yml"
            path.write_text(
                f"""steps:
  - uses: actions/checkout@{'0' * 40} # v7.0.0
  - uses: unknown/action@{checkout_sha} # v1.0.0
""",
                encoding="utf-8",
            )
            errors = CHECKER.reviewed_reference_errors(
                CHECKER.external_action_references(
                    [path],
                    repository_root=Path(tmp),
                ),
                action_lock,
            )

        self.assertTrue(any(error.startswith("SHA_MISMATCH") for error in errors))
        self.assertTrue(
            any(error.startswith("RELEASE_COMMENT_MISMATCH") for error in errors)
        )
        self.assertTrue(any(error.startswith("UNREVIEWED") for error in errors))
        self.assertTrue(any(error.startswith("UNUSED_LOCK") for error in errors))

    def test_action_lock_rejects_runtime_policy_drift_and_duplicate_keys(self) -> None:
        action_lock = json.loads(CHECKER.ACTION_LOCK_PATH.read_text(encoding="utf-8"))
        action_lock["policy"]["required_runtime"] = "node20"
        action_lock["minimum_actions_runner"] = "0.0.1"
        errors = CHECKER.action_lock_metadata_errors(action_lock)
        self.assertIn("policy.required_runtime must equal node24", errors)
        self.assertIn("minimum_actions_runner must equal 2.327.1", errors)

        action_lock["schema_version"] = True
        self.assertIn(
            "schema_version must equal 1",
            CHECKER.action_lock_metadata_errors(action_lock),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "actions-lock.json"
            path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                CHECKER.load_action_lock(path)


if __name__ == "__main__":
    unittest.main()
