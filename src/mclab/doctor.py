"""Local setup diagnostics for learner-facing runs."""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from mclab.application.asset_readiness import (
    clear_panda_asset_readiness_cache,
    is_panda_model_path,
    panda_asset_readiness,
    resolve_panda_model_member,
)
from mclab.config import PROJECT_ROOT, default_outputs_root, is_frozen_bundle, load_config

DEFAULT_REQUIRED_MODULES = ("mujoco", "numpy", "matplotlib", "yaml")
REQUIRED_PROJECT_PATHS = ("pyproject.toml", "src/mclab", "configs", "models")


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str
    fix: str = ""


def run_doctor_checks(
    root: str | Path = PROJECT_ROOT,
    *,
    required_modules: tuple[str, ...] = DEFAULT_REQUIRED_MODULES,
) -> list[DoctorCheck]:
    project_root = Path(root)
    # One doctor invocation is one readiness refresh. The config and learner-menu
    # checks below share this result instead of hashing the Panda tree per card.
    clear_panda_asset_readiness_cache()
    checks = [
        _python_runtime_check(),
        _required_modules_check(required_modules),
        _project_layout_check(project_root),
        _config_and_model_check(project_root),
        _learner_menu_readiness_check(project_root),
        _desktop_app_check(project_root),
        _outputs_writable_check(default_outputs_root()),
    ]
    return checks


def format_doctor_report(checks: list[DoctorCheck]) -> str:
    lines = ["MCLab Doctor", ""]
    for check in checks:
        lines.append(f"[{check.status}] {check.name} - {check.detail}")
        if check.fix:
            lines.append(f"    Fix: {check.fix}")
    ok_count = sum(1 for check in checks if check.status == "OK")
    warn_count = sum(1 for check in checks if check.status == "WARN")
    fail_count = sum(1 for check in checks if check.status == "FAIL")
    lines.extend(("", f"Summary: {ok_count} OK, {warn_count} WARN, {fail_count} FAIL"))
    lines.extend(("", *_doctor_next_step_lines(fail_count)))
    return "\n".join(lines)


def doctor_exit_code(checks: list[DoctorCheck]) -> int:
    return 1 if any(check.status == "FAIL" for check in checks) else 0


def doctor_report_json(checks: list[DoctorCheck]) -> str:
    payload = {
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
                "fix": check.fix,
            }
            for check in checks
        ],
        "summary": {
            "ok": sum(check.status == "OK" for check in checks),
            "warn": sum(check.status == "WARN" for check in checks),
            "fail": sum(check.status == "FAIL" for check in checks),
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _doctor_next_step_lines(fail_count: int) -> list[str]:
    if fail_count:
        return [
            "Next learner step: fix the FAIL item(s) above, then rerun `python -m mclab doctor`.",
        ]
    return [
        "Next learner steps:",
        "- Open the launcher: `python -m mclab menu`",
        "- See the next missing experience: `python -m mclab coverage`",
        "- Compare all experience modes and evidence cues: `python -m mclab coverage --details`",
        "- Inspect editable parameters: `python -m mclab params wall --filter hands-on`",
        "- Preview the recommended path step: `python -m mclab next --preview`",
        "- Launch the next path step: `python -m mclab next`",
        "- Review saved evidence: `python -m mclab review`",
        "- Open the reports index: `python -m mclab index --open`",
    ]


def _python_runtime_check() -> DoctorCheck:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if (3, 10) <= sys.version_info < (3, 13):
        return DoctorCheck("Python runtime", "OK", f"Python {version} is supported.")
    if sys.version_info >= (3, 13):
        return DoctorCheck(
            "Python runtime",
            "FAIL",
            f"Python {version} is newer than the reviewed lock range (3.10-3.12).",
            "Install CPython 3.10, 3.11, or 3.12 and recreate .venv.",
        )
    return DoctorCheck(
        "Python runtime",
        "FAIL",
        f"Python {version} is too old; the reviewed lock range is 3.10-3.12.",
        "Install CPython 3.10, 3.11, or 3.12 and recreate .venv.",
    )


def _required_modules_check(required_modules: tuple[str, ...]) -> DoctorCheck:
    if not required_modules:
        return DoctorCheck("Python packages", "OK", "No package checks requested.")

    failed: list[str] = []
    for module_name in required_modules:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            failed.append(f"{module_name} ({exc.__class__.__name__})")

    if failed:
        return DoctorCheck(
            "Python packages",
            "FAIL",
            "Missing or broken package imports: " + ", ".join(failed),
            "Run `python scripts/install_locked.py runtime` inside the project virtual environment.",
        )
    return DoctorCheck("Python packages", "OK", "Required packages import successfully.")


def _project_layout_check(root: Path) -> DoctorCheck:
    if is_frozen_bundle():
        missing_assets = [
            relative for relative in ("configs", "models") if not (root / relative).exists()
        ]
        if not missing_assets:
            return DoctorCheck(
                "Project layout", "OK", "Packaged configs and model resources are present."
            )
    missing = [relative for relative in REQUIRED_PROJECT_PATHS if not (root / relative).exists()]
    if missing:
        return DoctorCheck(
            "Project layout",
            "FAIL",
            "Missing required project paths: " + ", ".join(missing),
            "Run commands from the repository root or restore the missing files.",
        )
    return DoctorCheck("Project layout", "OK", "Required project folders and files are present.")


def _config_and_model_check(root: Path) -> DoctorCheck:
    config_root = root / "configs"
    config_paths = sorted(config_root.glob("**/*.yaml"))
    if not config_paths:
        return DoctorCheck(
            "Configs and models",
            "FAIL",
            "No YAML configs were found under configs/.",
            "Restore the configs/ directory.",
        )

    config_errors: list[str] = []
    invalid_panda_models: list[str] = []
    missing_models: list[str] = []
    model_paths: set[str] = set()
    uses_panda_assets = False
    for config_path in config_paths:
        relative_config = config_path.relative_to(root).as_posix()
        try:
            config = load_config(config_path)
        except Exception as exc:
            config_errors.append(f"{relative_config} ({exc.__class__.__name__})")
            continue
        model_path = config.get("model_path")
        if not isinstance(model_path, str) or not model_path.strip():
            config_errors.append(f"{relative_config} (missing model_path)")
            continue
        resolved_model = _resolve_from_root(root, model_path)
        model_paths.add(resolved_model.as_posix())
        is_panda_model = is_panda_model_path(model_path, root=root)
        uses_panda_assets = uses_panda_assets or is_panda_model
        if is_panda_model:
            try:
                resolve_panda_model_member(model_path, root=root)
            except ValueError as exc:
                invalid_panda_models.append(f"{relative_config} -> {exc}")
        elif not resolved_model.exists():
            missing_models.append(f"{relative_config} -> {model_path}")

    if config_errors:
        return DoctorCheck(
            "Configs and models",
            "FAIL",
            _limited_list("Config load issues", config_errors),
            "Open the listed YAML files and fix syntax or required keys.",
        )
    if invalid_panda_models:
        return DoctorCheck(
            "Configs and models",
            "FAIL",
            _limited_list("Invalid Panda model_path values", invalid_panda_models),
            "Use a tracked Panda XML model path in the listed YAML files, then rerun "
            "`python -m mclab doctor`.",
        )
    if missing_models:
        fix = "Check model_path values and restore missing model files."
        if any("mujoco_menagerie" in item for item in missing_models):
            fix = "Run `python -m mclab assets install` to install the pinned Panda assets."
        return DoctorCheck(
            "Configs and models",
            "FAIL",
            _limited_list("Missing model assets", missing_models),
            fix,
        )
    if uses_panda_assets:
        panda_readiness = panda_asset_readiness(root)
        if panda_readiness.code == "missing_asset":
            return DoctorCheck(
                "Configs and models",
                "FAIL",
                f"Missing Panda runtime asset tree: {panda_readiness.detail}",
                "Run `python -m mclab assets install` to install the pinned Panda assets, "
                "then rerun `python -m mclab doctor`.",
            )
        if panda_readiness.code == "invalid_asset":
            return DoctorCheck(
                "Configs and models",
                "FAIL",
                f"Panda runtime asset verification failed: {panda_readiness.detail}",
                "For an invalid physical tree, run `python -m mclab assets install --force`. "
                "Inspect and remove unsafe links or reparse points manually, then rerun "
                "`python -m mclab doctor`.",
            )
        panda_detail = (
            f" Panda inventory verified ({panda_readiness.file_count} files, "
            f"{panda_readiness.total_bytes} bytes)."
        )
    else:
        panda_detail = ""
    return DoctorCheck(
        "Configs and models",
        "OK",
        f"{len(config_paths)} configs load and {len(model_paths)} unique model assets exist."
        f"{panda_detail}",
    )


def _learner_menu_readiness_check(root: Path) -> DoctorCheck:
    if is_frozen_bundle():
        try:
            from mclab.application.catalog import ScenarioCatalog

            catalog = ScenarioCatalog.default()
            errors = catalog.integrity_errors()
        except Exception as exc:
            return DoctorCheck(
                "Scenario catalog",
                "FAIL",
                f"Could not load the packaged scenario catalog: {exc}",
                "Reinstall MCLab from a verified release archive.",
            )
        if errors:
            return DoctorCheck(
                "Scenario catalog",
                "FAIL",
                "; ".join(errors[:4]),
                "Reinstall MCLab from a verified release archive.",
            )
        return DoctorCheck(
            "Scenario catalog", "OK", f"{len(catalog.all())} packaged scenarios are valid."
        )
    if not (root / "src" / "mclab" / "learner_menu.py").exists():
        return DoctorCheck(
            "Learner menu readiness",
            "OK",
            "No learner menu source was found in this project layout.",
        )

    try:
        from mclab.learner_menu import (
            BATCH_ACTIONS,
            MENU_ACTIONS,
            action_readiness,
            batch_readiness,
        )
    except Exception as exc:
        return DoctorCheck(
            "Learner menu readiness",
            "FAIL",
            f"Could not import learner menu definitions: {exc.__class__.__name__}: {exc}",
            "Fix learner menu imports, then rerun `python -m mclab doctor`.",
        )

    scenario_failures: list[str] = []
    batch_failures: list[str] = []
    first_fix = ""
    for action in MENU_ACTIONS:
        readiness = action_readiness(action, root=root)
        if readiness.status == "ok":
            continue
        scenario_failures.append(
            f"{action.group} / {action.label}: {readiness.label} - {readiness.detail}"
        )
        if not first_fix and readiness.fix:
            first_fix = readiness.fix

    for action in BATCH_ACTIONS:
        readiness = batch_readiness(action, root=root)
        if readiness.status == "ok":
            continue
        batch_failures.append(f"{action.label}: {readiness.label} - {readiness.detail}")
        if not first_fix and readiness.fix:
            first_fix = readiness.fix

    if scenario_failures or batch_failures:
        parts: list[str] = []
        if scenario_failures:
            parts.append(
                _limited_list(
                    f"{len(scenario_failures)} scenario issue(s)", scenario_failures, limit=3
                )
            )
        if batch_failures:
            parts.append(
                _limited_list(f"{len(batch_failures)} batch issue(s)", batch_failures, limit=2)
            )
        return DoctorCheck(
            "Learner menu readiness",
            "FAIL",
            " | ".join(parts),
            first_fix or "Open the learner menu and use Check setup for the blocked scenario.",
        )

    return DoctorCheck(
        "Learner menu readiness",
        "OK",
        f"{len(MENU_ACTIONS)} guided scenarios and {len(BATCH_ACTIONS)} comparison batches are ready.",
    )


def _desktop_app_check(root: Path) -> DoctorCheck:
    app_source = root / "src" / "mclab" / "application" / "qt_app.py"
    if not is_frozen_bundle() and not app_source.exists():
        return DoctorCheck("Desktop app", "OK", "Desktop app is not part of this project layout.")
    try:
        importlib.import_module("PySide6.QtQml")
        importlib.import_module("PySide6.QtQuick")
    except Exception as exc:
        return DoctorCheck(
            "Desktop app",
            "WARN",
            f"Headless tools are ready, but the optional Qt app is unavailable ({exc.__class__.__name__}).",
            "Run `python scripts/install_locked.py app` to enable `mclab app` and `mclab menu`.",
        )
    return DoctorCheck("Desktop app", "OK", "PySide6 Qt Quick runtime imports successfully.")


def _outputs_writable_check(outputs: Path) -> DoctorCheck:
    probe = outputs / ".doctor_write_test"
    try:
        outputs.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        return DoctorCheck(
            "Outputs folder",
            "FAIL",
            f"Could not write to {outputs}: {exc}",
            "Check folder permissions or choose a writable project location.",
        )
    return DoctorCheck("Outputs folder", "OK", "outputs/ is writable for logs, plots, and reports.")


def _resolve_from_root(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _limited_list(prefix: str, items: list[str], *, limit: int = 4) -> str:
    shown = items[:limit]
    suffix = f"; plus {len(items) - limit} more" if len(items) > limit else ""
    return f"{prefix}: " + "; ".join(shown) + suffix
