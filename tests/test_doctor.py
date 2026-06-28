from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.doctor import (  # noqa: E402
    DoctorCheck,
    doctor_exit_code,
    format_doctor_report,
    run_doctor_checks,
)


class DoctorTests(unittest.TestCase):
    def test_doctor_accepts_minimal_valid_project_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_project(root, model_exists=True)

            checks = run_doctor_checks(root, required_modules=())

        self.assertTrue(all(check.status == "OK" for check in checks), checks)
        self.assertEqual(doctor_exit_code(checks), 0)
        report = format_doctor_report(checks)
        self.assertIn("MCLab Doctor", report)
        self.assertIn("Summary:", report)
        self.assertIn("[OK] Configs and models", report)

    def test_doctor_reports_missing_model_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_project(root, model_exists=False)

            checks = run_doctor_checks(root, required_modules=())

        self.assertEqual(doctor_exit_code(checks), 1)
        report = format_doctor_report(checks)
        self.assertIn("[FAIL] Configs and models", report)
        self.assertIn("Missing model assets", report)
        self.assertIn("configs/demo/default.yaml -> models/demo/scene.xml", report)

    def test_doctor_exit_code_only_fails_on_failures(self) -> None:
        checks = [
            DoctorCheck("OK item", "OK", "fine"),
            DoctorCheck("Warning item", "WARN", "notice"),
        ]
        self.assertEqual(doctor_exit_code(checks), 0)
        self.assertEqual(doctor_exit_code([*checks, DoctorCheck("Fail item", "FAIL", "broken")]), 1)


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
