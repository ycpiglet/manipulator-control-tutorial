from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.doctor import (  # noqa: E402
    DoctorCheck,
    _config_and_model_check,
    _outputs_writable_check,
    doctor_exit_code,
    format_doctor_report,
    run_doctor_checks,
)


class DoctorTests(unittest.TestCase):
    def test_outputs_check_creates_a_new_user_data_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "new-user-data" / "outputs"

            check = _outputs_writable_check(outputs)

            self.assertEqual(check.status, "OK")
            self.assertTrue(outputs.is_dir())
            self.assertFalse((outputs / ".doctor_write_test").exists())

    def test_doctor_accepts_minimal_valid_project_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_project(root, model_exists=True)

            with patch.dict(os.environ, {"MCLAB_DATA_DIR": tmp}):
                checks = run_doctor_checks(root, required_modules=())

        self.assertTrue(all(check.status == "OK" for check in checks), checks)
        self.assertEqual(doctor_exit_code(checks), 0)
        report = format_doctor_report(checks)
        self.assertIn("MCLab Doctor", report)
        self.assertIn("Summary:", report)
        self.assertIn("[OK] Configs and models", report)
        self.assertIn("[OK] Learner menu readiness", report)
        self.assertIn("Next learner steps:", report)
        self.assertIn("python -m mclab menu", report)
        self.assertIn("python -m mclab params wall --filter hands-on", report)
        self.assertIn("python -m mclab next --preview", report)
        self.assertIn("python -m mclab review", report)
        self.assertIn("python -m mclab index --open", report)

    def test_doctor_reports_missing_model_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_project(root, model_exists=False)

            with patch.dict(os.environ, {"MCLAB_DATA_DIR": tmp}):
                checks = run_doctor_checks(root, required_modules=())

        self.assertEqual(doctor_exit_code(checks), 1)
        report = format_doctor_report(checks)
        self.assertIn("[FAIL] Configs and models", report)
        self.assertIn("Missing model assets", report)
        self.assertIn("configs/demo/default.yaml -> models/demo/scene.xml", report)
        self.assertIn("Next learner step: fix the FAIL item(s) above", report)

    def test_doctor_distinguishes_missing_and_partial_panda_trees(self) -> None:
        from mclab.application.asset_readiness import clear_panda_asset_readiness_cache

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "configs" / "lab04" / "default.yaml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "model_path: third_party/mujoco_menagerie/franka_emika_panda/scene.xml\n",
                encoding="utf-8",
            )

            missing = _config_and_model_check(root)

            panda_root = (
                root / "third_party" / "mujoco_menagerie" / "franka_emika_panda"
            )
            panda_root.mkdir(parents=True)
            (panda_root / "scene.xml").write_text("<mujoco/>\n", encoding="utf-8")

            clear_panda_asset_readiness_cache()
            partial = _config_and_model_check(root)

        self.assertEqual(missing.status, "FAIL")
        self.assertIn("Missing Panda runtime asset tree", missing.detail)
        self.assertIn("assets install`", missing.fix)
        self.assertNotIn("--force", missing.fix)
        self.assertEqual(partial.status, "FAIL")
        self.assertIn("verification failed", partial.detail)
        self.assertIn("missing runtime file", partial.detail)
        self.assertIn("assets install --force", partial.fix)

    def test_doctor_classifies_an_unsafe_panda_root_as_invalid(self) -> None:
        from mclab.application.assets import AssetSafetyError

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "configs" / "lab04" / "default.yaml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "model_path: third_party/mujoco_menagerie/franka_emika_panda/scene.xml\n",
                encoding="utf-8",
            )
            unsafe = AssetSafetyError(
                root / "third_party" / "mujoco_menagerie" / "franka_emika_panda",
                ["runtime tree is a link or reparse point"],
            )

            with patch(
                "mclab.application.asset_readiness.verify_assets",
                side_effect=unsafe,
            ):
                check = _config_and_model_check(root)

        self.assertEqual(check.status, "FAIL")
        self.assertIn("verification failed", check.detail)
        self.assertIn("link or reparse point", check.detail)
        self.assertIn("Inspect and remove unsafe links", check.fix)

    def test_doctor_rejects_an_untracked_panda_model_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "configs" / "lab04" / "default.yaml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "model_path: "
                "third_party/mujoco_menagerie/franka_emika_panda/typo.xml\n",
                encoding="utf-8",
            )

            check = _config_and_model_check(root)

        self.assertEqual(check.status, "FAIL")
        self.assertIn("Invalid Panda model_path values", check.detail)
        self.assertIn("tracked XML model", check.detail)
        self.assertIn("Use a tracked Panda XML model path", check.fix)

    def test_doctor_reports_learner_menu_readiness_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_project(root, model_exists=True)
            (root / "src" / "mclab" / "learner_menu.py").write_text("# marker\n", encoding="utf-8")

            with patch.dict(os.environ, {"MCLAB_DATA_DIR": tmp}):
                checks = run_doctor_checks(root, required_modules=())

        self.assertEqual(doctor_exit_code(checks), 1)
        report = format_doctor_report(checks)
        self.assertIn("[FAIL] Learner menu readiness", report)
        self.assertIn("scenario issue", report)
        self.assertIn("Missing config", report)

    def test_doctor_exit_code_only_fails_on_failures(self) -> None:
        checks = [
            DoctorCheck("OK item", "OK", "fine"),
            DoctorCheck("Warning item", "WARN", "notice"),
        ]
        self.assertEqual(doctor_exit_code(checks), 0)
        self.assertEqual(doctor_exit_code([*checks, DoctorCheck("Fail item", "FAIL", "broken")]), 1)

    def test_source_doctor_uses_the_configured_default_outputs_root(self) -> None:
        with (
            tempfile.TemporaryDirectory() as project_tmp,
            tempfile.TemporaryDirectory() as data_tmp,
        ):
            project_root = Path(project_tmp)
            data_root = Path(data_tmp).resolve()
            _write_minimal_project(project_root, model_exists=True)

            with patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}):
                checks = run_doctor_checks(project_root, required_modules=())

            output_check = next(check for check in checks if check.name == "Outputs folder")
            self.assertEqual(output_check.status, "OK")
            self.assertTrue((data_root / "outputs").is_dir())
            self.assertFalse((project_root / "outputs").exists())

    def test_frozen_doctor_uses_the_packaged_default_outputs_root(self) -> None:
        from mclab import config

        with tempfile.TemporaryDirectory() as tmp:
            data_home = Path(tmp).resolve()
            expected = data_home / "mclab" / "outputs"
            checked_paths: list[Path] = []

            def capture_outputs_path(outputs: Path) -> DoctorCheck:
                checked_paths.append(outputs)
                return DoctorCheck("Outputs folder", "OK", "captured")

            with (
                patch.object(config.sys, "frozen", True, create=True),
                patch.object(config.sys, "platform", "linux"),
                patch.dict(
                    config.os.environ,
                    {"MCLAB_DATA_DIR": "", "XDG_DATA_HOME": str(data_home)},
                ),
                patch("mclab.doctor._outputs_writable_check", side_effect=capture_outputs_path),
            ):
                run_doctor_checks(ROOT, required_modules=())

        self.assertEqual(checked_paths, [expected])


def _write_minimal_project(root: Path, *, model_exists: bool) -> None:
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (root / "src" / "mclab").mkdir(parents=True)
    (root / "configs" / "demo").mkdir(parents=True)
    (root / "models" / "demo").mkdir(parents=True)
    (root / "configs" / "demo" / "default.yaml").write_text(
        "model_path: models/demo/scene.xml\nsim_time: 0.01\n",
        encoding="utf-8",
    )
    if model_exists:
        (root / "models" / "demo" / "scene.xml").write_text("<mujoco/>\n", encoding="utf-8")
