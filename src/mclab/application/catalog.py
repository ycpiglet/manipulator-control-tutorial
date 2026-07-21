"""Stable scenario identities and learner-facing scenario metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from mclab.completion import CompletionRule
from mclab.config import PROJECT_ROOT, load_config

REPORT_ARTIFACT_KEY = "report"
WORKSHEET_ARTIFACT_KEY = "worksheet"
PREDICTION_CHECK_ARTIFACT_KEY = "prediction-check"

CONCRETE_BATCH_NAMES = (
    "lab01_msd_compare",
    "lab02_pid_compare",
    "lab03_2dof_compare",
    "lab04_wall_compare",
    "lab04_cartesian_compare",
)
CONCRETE_BATCH_TARGET_IDS = tuple(f"batch.{name}" for name in CONCRETE_BATCH_NAMES)
ALL_BATCH_TARGET_ID = "batch.all"
BATCH_TARGET_IDS = (*CONCRETE_BATCH_TARGET_IDS, ALL_BATCH_TARGET_ID)

LEARNING_PATH_SCENARIO_IDS = (
    "lab01.default",
    "lab01.interactive-pull",
    "lab02.default",
    "lab02.interactive-disturbance",
    "lab03.joint-space-2dof",
    "lab03.task-space-2dof",
    "lab03.condition-aware-dls-2dof",
    "lab03.condition-aware-dls-adaptive-speed-retarget-2dof",
    "lab04.neutral-hold",
    "lab04.cartesian-reach",
    "lab04.interactive-virtual-wall",
)
LEARNING_PATH_TARGET_IDS = (*LEARNING_PATH_SCENARIO_IDS, ALL_BATCH_TARGET_ID)


@dataclass(frozen=True)
class ControlDefinition:
    id: str
    label_key: str
    minimum: float
    maximum: float
    step: float
    config_path: str
    default: float | None = None


@dataclass(frozen=True)
class ScenarioDefinition:
    """A scenario manifest entry with a stable public ID."""

    id: str
    lab_name: str
    config_path: str
    group: str
    title: str
    purpose: str
    difficulty: str
    estimated_minutes: int
    plot_preset: str
    controls: tuple[ControlDefinition, ...] = ()
    completion: CompletionRule = CompletionRule()
    next_scenario_id: str | None = None
    config_data: dict[str, Any] | None = field(default=None, repr=False, compare=False)
    config_error: str = ""

    @cached_property
    def config(self) -> dict[str, Any]:
        if self.config_data is not None:
            return self.config_data
        return load_config(self.config_path)


@dataclass(frozen=True)
class BatchDefinition:
    """A comparison-batch target with explicit child and completion identities."""

    id: str
    batch_name: str
    child_target_ids: tuple[str, ...]
    completion: CompletionRule


CompletionTargetDefinition = ScenarioDefinition | BatchDefinition


class ScenarioCatalog:
    """Read-only catalog used by the desktop app, CLI, and validation tests.

    The first migration stage adapts the proven learner guide definitions into
    stable IDs.  Consumers no longer infer behavior from labels or filenames;
    they resolve a definition through this boundary.
    """

    def __init__(
        self,
        scenarios: tuple[ScenarioDefinition, ...],
        batches: tuple[BatchDefinition, ...] = (),
    ) -> None:
        self._scenarios = scenarios
        self._batches = batches
        self._by_id = {scenario.id: scenario for scenario in scenarios}
        if len(self._by_id) != len(scenarios):
            raise ValueError("Scenario IDs must be unique.")
        self._batches_by_id = {batch.id: batch for batch in batches}
        if len(self._batches_by_id) != len(batches):
            raise ValueError("Batch IDs must be unique.")
        if self._by_id.keys() & self._batches_by_id.keys():
            raise ValueError("Scenario and batch IDs must not overlap.")

    @classmethod
    def default(cls) -> "ScenarioCatalog":
        # Lazy import avoids pulling Tk or Qt into headless module imports.
        from mclab.learner_menu import MENU_ACTIONS

        ids = [stable_scenario_id(action.lab_name, action.config_path) for action in MENU_ACTIONS]
        scenarios: list[ScenarioDefinition] = []
        for index, action in enumerate(MENU_ACTIONS):
            try:
                config = load_config(action.config_path)
                config_error = ""
            except Exception as exc:
                config = {}
                config_error = f"{exc.__class__.__name__}: {exc}"
            interactive = _is_interactive(config)
            # Policy declaration only: COMP-02 must expose and record the same
            # ordered presets on every learner surface before wiring this rule.
            scenarios.append(
                ScenarioDefinition(
                    id=ids[index],
                    lab_name=action.lab_name,
                    config_path=action.config_path,
                    group=action.group,
                    title=action.label,
                    purpose=action.description,
                    difficulty=_difficulty(action.lab_name, action.label),
                    estimated_minutes=_estimated_minutes(config, interactive),
                    plot_preset=action.plots,
                    controls=_controls_for(action.lab_name, config),
                    completion=CompletionRule(
                        requires_plot=True,
                        requires_learner_control=interactive,
                        requires_observation=interactive,
                        requires_prediction=interactive,
                        requires_note=interactive,
                        required_presets=_required_preset_labels(config),
                    ),
                    next_scenario_id=ids[index + 1] if index + 1 < len(ids) else None,
                    config_data=config,
                    config_error=config_error,
                )
            )
        scenario_definitions = tuple(scenarios)
        return cls(scenario_definitions, _default_batch_definitions())

    def all(self) -> tuple[ScenarioDefinition, ...]:
        return self._scenarios

    def get(self, scenario_id: str) -> ScenarioDefinition:
        try:
            return self._by_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario ID: {scenario_id}") from exc

    def batches(self) -> tuple[BatchDefinition, ...]:
        return self._batches

    def get_batch(self, batch_id: str) -> BatchDefinition:
        try:
            return self._batches_by_id[batch_id]
        except KeyError as exc:
            raise KeyError(f"Unknown batch ID: {batch_id}") from exc

    def targets(self) -> tuple[CompletionTargetDefinition, ...]:
        return (*self._scenarios, *self._batches)

    def get_target(self, target_id: str) -> CompletionTargetDefinition:
        if target_id in self._by_id:
            return self._by_id[target_id]
        return self.get_batch(target_id)

    def find_by_config(self, config_path: str | Path) -> ScenarioDefinition | None:
        normalized = Path(config_path).as_posix()
        return next((item for item in self._scenarios if item.config_path == normalized), None)

    def search(
        self, query: str = "", *, lab_name: str | None = None
    ) -> tuple[ScenarioDefinition, ...]:
        terms = [term.lower() for term in query.split() if term]
        matches = []
        for scenario in self._scenarios:
            if lab_name and scenario.lab_name != lab_name:
                continue
            haystack = " ".join(
                (
                    scenario.id,
                    scenario.group,
                    scenario.title,
                    scenario.purpose,
                    scenario.config_path,
                )
            ).lower()
            if all(term in haystack for term in terms):
                matches.append(scenario)
        return tuple(matches)

    def learning_path(self) -> tuple[ScenarioDefinition, ...]:
        return tuple(self.get(scenario_id) for scenario_id in LEARNING_PATH_SCENARIO_IDS)

    def learning_path_targets(self) -> tuple[CompletionTargetDefinition, ...]:
        return tuple(self.get_target(target_id) for target_id in LEARNING_PATH_TARGET_IDS)

    def integrity_errors(self, root: Path = PROJECT_ROOT) -> list[str]:
        errors: list[str] = []
        for scenario in self._scenarios:
            config_path = root / scenario.config_path
            if not config_path.exists():
                errors.append(f"{scenario.id}: missing {scenario.config_path}")
                continue
            if scenario.config_error:
                errors.append(
                    f"{scenario.id}: invalid {scenario.config_path} ({scenario.config_error})"
                )
                continue
            model_path = scenario.config.get("model_path")
            if not model_path or not (root / str(model_path)).exists():
                errors.append(f"{scenario.id}: missing model {model_path}")
            if len(scenario.controls) > 5:
                errors.append(f"{scenario.id}: exposes more than five core controls")
            requested = set(_requested_core_controls(scenario.config))
            missing_controls = requested - {control.id for control in scenario.controls}
            if missing_controls:
                errors.append(
                    f"{scenario.id}: unknown application core controls "
                    + ", ".join(sorted(missing_controls))
                )
        target_ids = set(self._by_id) | set(self._batches_by_id)
        for batch in self._batches:
            if not batch.child_target_ids:
                errors.append(f"{batch.id}: has no child targets")
            unknown_children = set(batch.child_target_ids) - target_ids
            if unknown_children:
                errors.append(
                    f"{batch.id}: unknown child targets " + ", ".join(sorted(unknown_children))
                )
        return errors


def stable_scenario_id(lab_name: str, config_path: str | Path | None) -> str:
    """Return the one public manifest ID for a lab/config pair."""

    prefix = {
        "lab01_msd": "lab01",
        "lab02_pid": "lab02",
        "lab03_trajectory": "lab03",
        "lab03_2dof": "lab03",
        "lab04_panda": "lab04",
    }.get(lab_name, lab_name)
    stem = Path(config_path).stem.lower() if config_path is not None else "custom"
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return f"{prefix}.{slug}"


def target_from_legacy_summary(
    catalog: ScenarioCatalog,
    summary: dict[str, Any],
) -> CompletionTargetDefinition | None:
    """Resolve only pre-manifest diagnostic identity from legacy summary fields."""

    config_path = str(summary.get("config_path") or "").strip()
    if config_path:
        normalized = _normalized_config_path(config_path)
        for scenario in catalog.all():
            if _normalized_config_path(scenario.config_path) == normalized:
                return scenario

    batch_name = str(
        summary.get("batch_name") or (
            summary.get("config_name")
            if summary.get("lab_name") in {"batch", "batch_group"}
            else ""
        )
        or ""
    ).strip()
    if batch_name:
        try:
            return catalog.get_batch(f"batch.{batch_name}")
        except KeyError:
            pass

    config_name = str(summary.get("config_name") or "").strip().casefold()
    lab_name = str(summary.get("lab_name") or "").strip().casefold()
    if not config_name or not lab_name:
        return None
    return next(
        (
            scenario
            for scenario in catalog.all()
            if Path(scenario.config_path).stem.casefold() == config_name
            and (
                scenario.lab_name.casefold() in lab_name
                or lab_name in scenario.lab_name.casefold()
            )
        ),
        None,
    )


def _normalized_config_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./").casefold()


def _default_batch_definitions() -> tuple[BatchDefinition, ...]:
    # Keep the existing executable batch matrix as the child source until its
    # compatibility path can consume this registry in a separate change.
    from mclab.batch import BATCH_SETS

    concrete = tuple(
        BatchDefinition(
            id=batch_id,
            batch_name=batch_name,
            child_target_ids=tuple(
                stable_scenario_id(item.lab_name, item.config_path)
                for item in BATCH_SETS[batch_name]
            ),
            completion=CompletionRule(
                requires_plot=True,
                required_artifacts=(
                    REPORT_ARTIFACT_KEY,
                    WORKSHEET_ARTIFACT_KEY,
                    PREDICTION_CHECK_ARTIFACT_KEY,
                ),
            ),
        )
        for batch_name, batch_id in zip(
            CONCRETE_BATCH_NAMES,
            CONCRETE_BATCH_TARGET_IDS,
            strict=True,
        )
    )
    course = BatchDefinition(
        id=ALL_BATCH_TARGET_ID,
        batch_name="all",
        child_target_ids=CONCRETE_BATCH_TARGET_IDS,
        completion=CompletionRule(
            required_artifacts=(
                REPORT_ARTIFACT_KEY,
                WORKSHEET_ARTIFACT_KEY,
                *CONCRETE_BATCH_TARGET_IDS,
            ),
        ),
    )
    return (*concrete, course)


def _is_interactive(config: dict[str, Any]) -> bool:
    interaction = dict(config.get("interaction", {}))
    return bool(
        interaction.get("panel") or interaction.get("live_tuning") or interaction.get("key_force")
    )


def _required_preset_labels(config: dict[str, Any]) -> tuple[str, ...]:
    interaction = config.get("interaction")
    if not isinstance(interaction, dict):
        return ()
    presets = interaction.get("tuning_presets")
    if not isinstance(presets, list):
        return ()
    labels: list[str] = []
    for index, preset in enumerate(presets, start=1):
        if not isinstance(preset, dict) or not bool(preset.get("required", False)):
            continue
        label = str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        if label:
            labels.append(label)
    return tuple(labels)


def _difficulty(lab_name: str, label: str) -> str:
    if lab_name in {"lab01", "lab02"}:
        return "intro"
    if lab_name == "lab03" and "DLS" not in label and "singularity" not in label.lower():
        return "build"
    return "deep-dive"


def _estimated_minutes(config: dict[str, Any], interactive: bool) -> int:
    if interactive:
        return 5
    sim_time = float(config.get("sim_time", 5.0))
    return max(2, min(10, int(round(sim_time / 6.0)) + 2))


def _controls_for(lab_name: str, config: dict[str, Any]) -> tuple[ControlDefinition, ...]:
    interactive = _is_interactive(config)
    requested = set(_requested_core_controls(config))
    if lab_name == "lab01":
        controls = (
            ControlDefinition("mass", "control.mass", 0.2, 5.0, 0.1, "mass"),
            ControlDefinition("damping", "control.damping", 0.0, 12.0, 0.1, "damping"),
            ControlDefinition("stiffness", "control.stiffness", 0.0, 120.0, 1.0, "stiffness"),
        )
        if not interactive and not requested:
            return ()
        return tuple(
            control for control in controls if not requested or control.id in requested
        )
    if not interactive:
        return ()
    if lab_name == "lab02":
        controller = dict(config.get("controller", {}))
        limit = controller.get("output_limit", config.get("force_limit", 80.0))
        if isinstance(limit, (list, tuple)):
            limit = max(abs(float(item)) for item in limit)
        return (
            ControlDefinition("target_position", "value.position", -0.8, 0.8, 0.01, "target.end"),
            ControlDefinition("kp", "control.kp", 0.0, 180.0, 1.0, "controller.kp"),
            ControlDefinition("ki", "control.ki", 0.0, 20.0, 0.1, "controller.ki"),
            ControlDefinition("kd", "control.kd", 0.0, 40.0, 0.5, "controller.kd"),
            ControlDefinition(
                "output_limit", "control.force_limit", 5.0, 200.0, 1.0, "controller.output_limit"
            ),
        )
    if lab_name == "lab03":
        controller = dict(config.get("tracking_controller", {}))
        if str(config.get("plant", "")).lower() != "two_link_arm":
            limit = controller.get("force_limit", 200.0)
            if isinstance(limit, (list, tuple)):
                limit = max(abs(float(item)) for item in limit)
            return (
                ControlDefinition(
                    "target_offset", "control.target_offset", -0.5, 0.5, 0.01, "", 0.0
                ),
                ControlDefinition("kp", "control.kp", 0.0, 250.0, 1.0, "tracking_controller.kp"),
                ControlDefinition("kd", "control.kd", 0.0, 60.0, 0.5, "tracking_controller.kd"),
                ControlDefinition(
                    "force_limit",
                    "control.force_limit",
                    10.0,
                    250.0,
                    1.0,
                    "tracking_controller.force_limit",
                    float(limit),
                ),
            )
        mode = str(config.get("mode", "joint_space")).lower()
        torque = controller.get("torque_limit", [50.0, 40.0])
        torque_value = (
            max(abs(float(item)) for item in torque)
            if isinstance(torque, (list, tuple))
            else abs(float(torque))
        )
        if "dls" in mode:
            return (
                ControlDefinition("target_x", "control.target_x", -0.95, 1.05, 0.01, "target_xy.0"),
                ControlDefinition("target_y", "control.target_y", -0.85, 0.85, 0.01, "target_xy.1"),
                ControlDefinition(
                    "dls_gain", "control.dls_gain", 0.5, 12.0, 0.1, "tracking_controller.dls_gain"
                ),
                ControlDefinition(
                    "dls_damping",
                    "control.dls_damping",
                    0.0,
                    0.4,
                    0.01,
                    "tracking_controller.dls_damping",
                ),
                ControlDefinition(
                    "torque_limit", "control.torque_limit", 5.0, 80.0, 1.0, "", torque_value
                ),
            )
        if mode in {"task_space", "cartesian", "jacobian"}:
            return (
                ControlDefinition("target_x", "control.target_x", -0.95, 0.95, 0.01, "target_xy.0"),
                ControlDefinition("target_y", "control.target_y", -0.85, 0.85, 0.01, "target_xy.1"),
                ControlDefinition(
                    "task_kp", "control.task_kp", 5.0, 180.0, 1.0, "tracking_controller.task_kp"
                ),
                ControlDefinition(
                    "task_kd", "control.task_kd", 0.0, 45.0, 0.5, "tracking_controller.task_kd"
                ),
                ControlDefinition(
                    "torque_limit", "control.torque_limit", 5.0, 80.0, 1.0, "", torque_value
                ),
            )
        return (
            ControlDefinition("q1_offset", "control.q1_offset", -0.8, 0.8, 0.01, "", 0.0),
            ControlDefinition("q2_offset", "control.q2_offset", -0.8, 0.8, 0.01, "", 0.0),
            ControlDefinition("joint_kp", "control.joint_kp", 0.2, 2.0, 0.05, "", 1.0),
            ControlDefinition("joint_kd", "control.joint_kd", 0.2, 2.0, 0.05, "", 1.0),
            ControlDefinition(
                "torque_limit", "control.torque_limit", 5.0, 80.0, 1.0, "", torque_value
            ),
        )
    if lab_name == "lab04":
        mode = str(config.get("mode", "joint_trajectory")).lower()
        target = dict(config.get("cartesian_target", {}))
        if mode in {"impedance_wall", "virtual_wall", "wall"}:
            return (
                ControlDefinition(
                    "target_x", "control.target_x", 0.35, 0.75, 0.005, "cartesian_target.position.0"
                ),
                ControlDefinition(
                    "wall_x", "control.wall_x", 0.50, 0.70, 0.005, "virtual_wall.wall_x"
                ),
                ControlDefinition(
                    "wall_stiffness",
                    "control.wall_stiffness",
                    0.0,
                    800.0,
                    10.0,
                    "virtual_wall.stiffness",
                ),
                ControlDefinition(
                    "wall_damping", "control.wall_damping", 0.0, 40.0, 0.5, "virtual_wall.damping"
                ),
                ControlDefinition(
                    "wall_retreat_gain",
                    "control.wall_retreat",
                    0.0,
                    1.5,
                    0.05,
                    "virtual_wall.cartesian_retreat_gain",
                ),
            )
        if mode in {"cartesian_reach", "task_space", "ee_reach"}:
            position = target.get("position", [0.60, 0.10, 0.59])
            return (
                ControlDefinition(
                    "target_x",
                    "control.target_x",
                    0.35,
                    0.75,
                    0.005,
                    "cartesian_target.position.0",
                    float(position[0]),
                ),
                ControlDefinition(
                    "target_y",
                    "control.target_y",
                    -0.35,
                    0.35,
                    0.005,
                    "cartesian_target.position.1",
                    float(position[1]),
                ),
                ControlDefinition(
                    "target_z",
                    "control.target_z",
                    0.35,
                    0.80,
                    0.005,
                    "cartesian_target.position.2",
                    float(position[2]),
                ),
                ControlDefinition(
                    "cartesian_gain",
                    "control.cartesian_gain",
                    0.2,
                    2.0,
                    0.05,
                    "cartesian_target.gain",
                ),
            )
        return (
            ControlDefinition(
                "joint_target_offset", "control.joint_offset", -0.35, 0.35, 0.01, "", 0.0
            ),
        )
    return ()


def _requested_core_controls(config: dict[str, Any]) -> tuple[str, ...]:
    application = dict(config.get("application", {}))
    raw = application.get("core_controls", ())
    if isinstance(raw, str):
        return (raw,)
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(item) for item in raw)
