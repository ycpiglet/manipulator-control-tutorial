"""Truthful, learner-facing readiness checks for the desktop application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mclab.application.catalog import ScenarioCatalog, ScenarioDefinition
from mclab.application.i18n import Translator
from mclab.config import PROJECT_ROOT, default_outputs_root


@dataclass(frozen=True)
class ReadinessIssue:
    code: str
    detail: str
    scenario_id: str = ""


def qt_available() -> tuple[bool, str]:
    try:
        import PySide6  # noqa: F401
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
    return True, "PySide6 is importable."


def scenario_readiness(
    scenario: ScenarioDefinition,
    *,
    root: Path = PROJECT_ROOT,
) -> ReadinessIssue | None:
    """Return the first concrete reason a scenario cannot start."""

    config_path = root / scenario.config_path
    if not config_path.is_file():
        return ReadinessIssue("missing_config", scenario.config_path, scenario.id)
    if scenario.config_error:
        return ReadinessIssue("invalid_config", scenario.config_path, scenario.id)
    model_path = scenario.config.get("model_path")
    if not isinstance(model_path, str) or not model_path.strip():
        return ReadinessIssue("invalid_config", scenario.config_path, scenario.id)
    if not (root / model_path).is_file():
        code = "missing_asset" if "mujoco_menagerie" in model_path else "missing_model"
        return ReadinessIssue(code, model_path, scenario.id)
    return None


def app_readiness(
    catalog: ScenarioCatalog,
    *,
    root: Path = PROJECT_ROOT,
    outputs: Path | None = None,
) -> tuple[ReadinessIssue, ...]:
    """Check every scenario plus the writable artifact destination."""

    issues = tuple(
        issue
        for scenario in catalog.all()
        if (issue := scenario_readiness(scenario, root=root)) is not None
    )
    output_issue = _output_issue(outputs or default_outputs_root())
    return issues + ((output_issue,) if output_issue else ())


def readiness_payload(
    issues: tuple[ReadinessIssue, ...],
    translator: Translator,
) -> dict[str, object]:
    """Localize the compact status shown on the home screen."""

    if not issues:
        return {
            "ready": True,
            "issueCount": 0,
            "title": translator.text("home.ready"),
            "detail": translator.text("home.environment_detail"),
            "action": translator.text("home.environment_items"),
        }
    first = issues[0]
    count_text = translator.text("setup.issue_count").replace("{count}", str(len(issues)))
    return {
        "ready": False,
        "issueCount": len(issues),
        "title": translator.text("setup.attention"),
        "detail": f"{count_text} · {first.detail}",
        "action": translator.text(f"setup.action.{first.code}"),
    }


def scenario_readiness_payload(
    issue: ReadinessIssue | None,
    translator: Translator,
) -> dict[str, object]:
    if issue is None:
        return {"ready": True, "readinessDetail": "", "readinessAction": ""}
    return {
        "ready": False,
        "readinessDetail": translator.text(f"setup.issue.{issue.code}").replace(
            "{path}", issue.detail
        ),
        "readinessAction": translator.text(f"setup.action.{issue.code}"),
    }


def _output_issue(outputs: Path) -> ReadinessIssue | None:
    probe = outputs / f".mclab_readiness_{os.getpid()}"
    try:
        outputs.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception:
        return ReadinessIssue("output_unwritable", str(outputs))
    return None
