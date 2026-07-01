"""Local setup diagnostics for learner-facing runs."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

from mclab.config import PROJECT_ROOT, load_config

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
    checks = [
        _python_runtime_check(),
        _required_modules_check(required_modules),
        _project_layout_check(project_root),
        _config_and_model_check(project_root),
        _learner_menu_readiness_check(project_root),
        _outputs_writable_check(project_root),
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


def _doctor_next_step_lines(fail_count: int) -> list[str]:
    if fail_count:
        return [
            "Next learner step: fix the FAIL item(s) above, then rerun `python -m mclab doctor`.",
        ]
    return [
        "Next learner steps:",
        "- Open the launcher: `python -m mclab menu`",
        "- See the next missing experience: `python -m mclab coverage`",
        "- Inspect editable parameters: `python -m mclab params wall --filter hands-on`",
        "- Preview the recommended path step: `python -m mclab next --preview`",
        "- Launch the next path step: `python -m mclab next`",
    ]


def _python_runtime_check() -> DoctorCheck:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        return DoctorCheck("Python runtime", "OK", f"Python {version} is supported.")
    return DoctorCheck(
        "Python runtime",
        "FAIL",
        f"Python {version} is too old; this project requires Python 3.10 or newer.",
        "Install Python 3.10+ and recreate .venv.",
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
            "Run `python -m pip install -e .[dev]` inside the project virtual environment.",
        )
    return DoctorCheck("Python packages", "OK", "Required packages import successfully.")


def _project_layout_check(root: Path) -> DoctorCheck:
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
    missing_models: list[str] = []
    model_paths: set[str] = set()
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
        if not resolved_model.exists():
            missing_models.append(f"{relative_config} -> {model_path}")

    if config_errors:
        return DoctorCheck(
            "Configs and models",
            "FAIL",
            _limited_list("Config load issues", config_errors),
            "Open the listed YAML files and fix syntax or required keys.",
        )
    if missing_models:
        fix = "Check model_path values and restore missing model files."
        if any("mujoco_menagerie" in item for item in missing_models):
            fix = "Run `python scripts/bootstrap_and_run.py --setup-only` to fetch MuJoCo Menagerie assets."
        return DoctorCheck(
            "Configs and models",
            "FAIL",
            _limited_list("Missing model assets", missing_models),
            fix,
        )
    return DoctorCheck(
        "Configs and models",
        "OK",
        f"{len(config_paths)} configs load and {len(model_paths)} unique model assets exist.",
    )


def _learner_menu_readiness_check(root: Path) -> DoctorCheck:
    if not (root / "src" / "mclab" / "learner_menu.py").exists():
        return DoctorCheck("Learner menu readiness", "OK", "No learner menu source was found in this project layout.")

    try:
        from mclab.learner_menu import BATCH_ACTIONS, MENU_ACTIONS, action_readiness, batch_readiness
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
        scenario_failures.append(f"{action.group} / {action.label}: {readiness.label} - {readiness.detail}")
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
            parts.append(_limited_list(f"{len(scenario_failures)} scenario issue(s)", scenario_failures, limit=3))
        if batch_failures:
            parts.append(_limited_list(f"{len(batch_failures)} batch issue(s)", batch_failures, limit=2))
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


def _outputs_writable_check(root: Path) -> DoctorCheck:
    outputs = root / "outputs"
    probe = outputs / ".doctor_write_test"
    try:
        outputs.mkdir(exist_ok=True)
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
