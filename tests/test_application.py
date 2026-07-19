from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.application.artifacts import (  # noqa: E402
    ReplayArchive,
    ReplayFrame,
    ReplayRecorder,
    legacy_replay_reason,
    verify_manifest,
    write_manifest,
)
from mclab.application.batch_runs import (  # noqa: E402
    ALL_COMPARE_ID,
    all_compare_command,
    create_all_compare_output,
    parse_batch_progress,
    update_batch_manifest,
)
from mclab.application.catalog import ScenarioCatalog  # noqa: E402
from mclab.application.error_messages import localized_error  # noqa: E402
from mclab.application.i18n import (  # noqa: E402
    SCENARIO_TITLES_KO,
    Translator,
    missing_translation_keys,
    normalize_language,
)
from mclab.application.launcher import create_scenario_adapter  # noqa: E402
from mclab.application.platform import PlatformServices  # noqa: E402
from mclab.application.presentation import (  # noqa: E402
    course_progress_payload,
    learning_path_payload,
    result_payloads,
    scenario_payload,
)
from mclab.application.readiness import (  # noqa: E402
    app_readiness,
    readiness_payload,
    scenario_readiness,
    scenario_readiness_payload,
)
from mclab.application.repositories import ArtifactRepository  # noqa: E402
from mclab.application.rendering import close_mujoco_renderer, spring_polyline  # noqa: E402
from mclab.application.run_manager import RunManager  # noqa: E402
from mclab.application.saved_runs import resolve_saved_run_launch  # noqa: E402
from mclab.application.session import SessionState, SimulationSession  # noqa: E402
from mclab.cli import _maybe_relaunch_macos_viewer, build_parser, main  # noqa: E402
from mclab.doctor import DoctorCheck, doctor_report_json  # noqa: E402
from mclab.application.qt_app import SHUTDOWN_WAIT_MS  # noqa: E402
from mclab.application.qt_batch import create_batch_controller  # noqa: E402
from mclab.application.qt_lifecycle import (  # noqa: E402
    has_active_experiment,
    pause_before_navigation,
    reject_running_batch,
    replace_session,
    stop_active_experiment,
)
from mclab.application.qt_smoke import schedule_smoke_action  # noqa: E402
from mclab.application.worker_commands import CommandQueue  # noqa: E402
from mclab.application.visual_semantics import (  # noqa: E402
    SEMANTIC_SHAPES,
    color_vision_separation,
)
from mclab.sim.interaction import InteractionLog  # noqa: E402


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    first, second = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (first + 0.05) / (second + 0.05)


class FakeAdapter:
    def __init__(self, *, fail_at: float | None = None) -> None:
        self._time = 0.0
        self._dt = 0.01
        self.prepared = False
        self.closed = False
        self.reset_count = 0
        self.actions: list[tuple[str, object]] = []
        self.events: list[dict[str, object]] = []
        self.position = 0.0
        self.fail_at = fail_at

    @property
    def time(self) -> float:
        return self._time

    @property
    def timestep(self) -> float:
        return self._dt

    def prepare(self) -> None:
        self.prepared = True

    def step(self) -> dict[str, float]:
        if self.fail_at is not None and self._time >= self.fail_at:
            raise RuntimeError("injected physics failure")
        self._time += self._dt
        self.position += 1.0
        return {"time": self._time, "position": self.position}

    def reset(self) -> None:
        self._time = 0.0
        self.position = 0.0
        self.reset_count += 1

    def apply_action(self, name: str, value: object = None) -> None:
        self.actions.append((name, value))

    def state_vectors(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return np.asarray([self.position]), np.asarray([1.0]), np.asarray([0.5])

    def restore_frame(self, frame: ReplayFrame) -> None:
        self._time = frame.time
        self.position = float(frame.qpos[0])

    def render(self, width: int, height: int) -> np.ndarray:
        return np.zeros((height, width, 3), dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class ApplicationFoundationTests(unittest.TestCase):
    def test_qt_smoke_sequence_configures_window_and_beta_actions(self) -> None:
        class Root:
            width = 0
            height = 0

            def setWidth(self, value: int) -> None:  # noqa: N802
                self.width = value

            def setHeight(self, value: int) -> None:  # noqa: N802
                self.height = value

        class Timer:
            callbacks: list[tuple[int, object]] = []

            @classmethod
            def singleShot(cls, delay: int, callback: object) -> None:  # noqa: N802
                cls.callbacks.append((delay, callback))

        class Backend:
            nextScenarioId = "lab01.default"

            def __init__(self) -> None:
                self.calls: list[tuple[str, object]] = []

            def applyAction(self, name: str) -> None:  # noqa: N802
                self.calls.append(("action", name))

            def applyControl(self, name: str, value: float) -> None:  # noqa: N802
                self.calls.append(("control", (name, value)))

            def stepOnce(self) -> None:  # noqa: N802
                self.calls.append(("step", None))

        root = Root()
        backend = Backend()
        with patch.dict(
            os.environ,
            {
                "MCLAB_WINDOW_WIDTH": "640",
                "MCLAB_WINDOW_HEIGHT": "360",
                "MCLAB_SMOKE_ACTION": "push,control_target_x=0.88,step",
                "MCLAB_SMOKE_ACTION_MS": "100",
            },
        ):
            schedule_smoke_action(Timer, backend, [root])
        for _, callback in Timer.callbacks:
            callback()  # type: ignore[operator]

        self.assertEqual((root.width, root.height), (640, 360))
        self.assertEqual(
            backend.calls,
            [("action", "push"), ("control", ("target_x", 0.88)), ("step", None)],
        )

    def test_desktop_shutdown_allows_artifact_finalization_to_finish(self) -> None:
        self.assertGreaterEqual(SHUTDOWN_WAIT_MS, 30_000)

    def test_catalog_has_stable_ids_for_all_guided_scenarios(self) -> None:
        catalog = ScenarioCatalog.default()
        scenarios = catalog.all()

        self.assertEqual(len(scenarios), 70)
        self.assertEqual(len({scenario.id for scenario in scenarios}), 70)
        self.assertEqual(catalog.get("lab01.interactive-pull").lab_name, "lab01")
        self.assertEqual(catalog.get("lab04.interactive-virtual-wall").lab_name, "lab04")
        self.assertTrue(all(len(scenario.controls) <= 5 for scenario in scenarios))
        self.assertEqual(catalog.integrity_errors(), [])

    def test_explore_titles_keep_unique_lab_context_in_both_languages(self) -> None:
        scenarios = ScenarioCatalog.default().all()
        for language in ("ko", "en"):
            with self.subTest(language=language):
                titles = [
                    scenario_payload(scenario, Translator(language))["displayTitle"]
                    for scenario in scenarios
                ]
                self.assertEqual(len(titles), 70)
                self.assertEqual(len(set(titles)), 70)
                self.assertTrue(all(title.startswith("LAB0") for title in titles))

    def test_catalog_search_and_config_lookup_do_not_require_label_inference(self) -> None:
        catalog = ScenarioCatalog.default()

        self.assertEqual(
            catalog.find_by_config("configs/lab01_msd/default.yaml").id,  # type: ignore[union-attr]
            "lab01.default",
        )
        wall_ids = {scenario.id for scenario in catalog.search("virtual wall")}
        self.assertIn("lab04.interactive-virtual-wall", wall_ids)
        self.assertEqual(len(catalog.search("lab04 wall")), 14)
        self.assertEqual(len(catalog.search("wall lab04")), 14)

    def test_first_lab_desktop_manifest_starts_paused_with_one_guided_control(self) -> None:
        scenario = ScenarioCatalog.default().get("lab01.default")
        payload = scenario_payload(scenario, Translator("ko"))

        self.assertEqual([control.id for control in scenario.controls], ["damping"])
        self.assertTrue(payload["startsPaused"])
        self.assertEqual([control["id"] for control in payload["controls"]], ["damping"])
        self.assertFalse(payload["requiresEvidence"])

    def test_catalog_rejects_unknown_requested_desktop_core_control(self) -> None:
        scenario = ScenarioCatalog.default().get("lab01.default")
        invalid = replace(
            scenario,
            config_data={
                **scenario.config,
                "application": {
                    "start_paused": True,
                    "core_controls": ["not_a_control"],
                },
            },
        )

        errors = ScenarioCatalog((invalid,)).integrity_errors()

        self.assertTrue(any("unknown application core controls" in item for item in errors))
        self.assertTrue(any("not_a_control" in item for item in errors))

    def test_catalog_keeps_desktop_open_when_one_yaml_is_invalid(self) -> None:
        from mclab.application import catalog as catalog_module

        real_load = catalog_module.load_config

        def flaky_load(path: str) -> dict[str, object]:
            if str(path).endswith("configs/lab01_msd/default.yaml"):
                raise ValueError("injected invalid YAML")
            return real_load(path)

        with patch.object(catalog_module, "load_config", side_effect=flaky_load):
            catalog = ScenarioCatalog.default()

        broken = catalog.get("lab01.default")
        self.assertEqual(len(catalog.all()), 70)
        self.assertEqual(broken.config, {})
        self.assertIn("injected invalid YAML", broken.config_error)
        self.assertTrue(any("lab01.default: invalid" in item for item in catalog.integrity_errors()))

    def test_readiness_names_missing_assets_and_output_permission_recovery(self) -> None:
        scenario = ScenarioCatalog.default().get("lab04.interactive-virtual-wall")
        missing = replace(
            scenario,
            config_data={
                **scenario.config,
                "model_path": "third_party/mujoco_menagerie/missing/panda.xml",
            },
        )
        issue = scenario_readiness(missing, root=ROOT)
        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "missing_asset")  # type: ignore[union-attr]
        payload = scenario_readiness_payload(issue, Translator("ko"))
        self.assertFalse(payload["ready"])
        self.assertIn("missing/panda.xml", payload["readinessDetail"])
        self.assertIn("mclab assets install", payload["readinessAction"])

        with tempfile.TemporaryDirectory() as tmp:
            blocked_output = Path(tmp) / "not-a-folder"
            blocked_output.write_text("file", encoding="utf-8")
            issues = app_readiness(
                ScenarioCatalog((scenario,)),
                root=ROOT,
                outputs=blocked_output,
            )
        status = readiness_payload(issues, Translator("en"))
        self.assertFalse(status["ready"])
        self.assertIn("MCLAB_DATA_DIR", status["action"])

    def test_integrated_lab03_and_lab04_cards_expose_at_most_five_core_controls(self) -> None:
        catalog = ScenarioCatalog.default()
        dls = catalog.get("lab03.condition-aware-dls-2dof")
        wall = catalog.get("lab04.interactive-virtual-wall")

        self.assertEqual(
            [control.id for control in dls.controls],
            ["target_x", "target_y", "dls_gain", "dls_damping", "torque_limit"],
        )
        self.assertEqual(
            [control.id for control in wall.controls],
            ["target_x", "wall_x", "wall_stiffness", "wall_damping", "wall_retreat_gain"],
        )

    def test_explore_filter_facets_cover_all_scenarios_without_label_inference(self) -> None:
        catalog = ScenarioCatalog.default()
        scenarios = catalog.all()

        self.assertEqual(
            {
                difficulty: sum(item.difficulty == difficulty for item in scenarios)
                for difficulty in ("intro", "build", "deep-dive")
            },
            {"intro": 16, "build": 8, "deep-dive": 46},
        )
        self.assertEqual(
            sum(
                item.completion.requires_learner_control
                or item.completion.requires_observation
                for item in scenarios
            ),
            9,
        )
        payload = scenario_payload(
            catalog.get("lab03.joint-space-2dof"), Translator("en")
        )
        self.assertEqual(payload["difficultyId"], "build")

    def test_scene_legend_flags_match_scenario_semantics(self) -> None:
        catalog = ScenarioCatalog.default()
        slider = scenario_payload(catalog.get("lab01.default"), Translator("en"))
        arm = scenario_payload(catalog.get("lab03.interactive-2dof"), Translator("en"))
        panda = scenario_payload(
            catalog.get("lab04.interactive-cartesian-reach"), Translator("en")
        )
        wall = scenario_payload(
            catalog.get("lab04.interactive-virtual-wall"), Translator("en")
        )

        self.assertTrue(slider["showForce"])
        self.assertFalse(slider["spatialMotion"])
        self.assertTrue(arm["showWorkspace"])
        self.assertTrue(arm["showSingularity"])
        self.assertFalse(arm["showWall"])
        self.assertTrue(panda["spatialMotion"])
        self.assertFalse(panda["showWall"])
        self.assertTrue(wall["showWall"])
        self.assertTrue(wall["showForce"])
        self.assertTrue(wall["ready"])
        self.assertFalse(slider["requiresEvidence"])
        self.assertTrue(wall["requiresEvidence"])

    def test_every_scenario_has_a_concise_actionable_now_prompt(self) -> None:
        catalog = ScenarioCatalog.default()
        for language in ("ko", "en"):
            for scenario in catalog.all():
                with self.subTest(language=language, scenario=scenario.id):
                    prompt = scenario_payload(scenario, Translator(language))["nowPrompt"]
                    self.assertTrue(prompt.strip())
                    self.assertLessEqual(len(prompt), 90)

        wall = scenario_payload(
            catalog.get("lab04.interactive-virtual-wall"), Translator("ko")
        )
        self.assertIn("목표 X +", wall["nowPrompt"])
        self.assertIn("목표 X 값", wall["nowPrompt"])

    def test_live_controls_expose_step_sensitive_precision_and_units(self) -> None:
        catalog = ScenarioCatalog.default()
        controls = [
            control
            for scenario in catalog.all()
            for control in scenario_payload(scenario, Translator("en"))["controls"]
        ]
        for control in controls:
            with self.subTest(control=control["id"], step=control["step"]):
                digits = control["digits"]
                self.assertNotEqual(
                    f"{control['minimum']:.{digits}f}",
                    f"{control['minimum'] + control['step']:.{digits}f}",
                )
                self.assertIn("unit", control)

        wall = scenario_payload(
            catalog.get("lab04.interactive-virtual-wall"), Translator("en")
        )
        by_id = {control["id"]: control for control in wall["controls"]}
        self.assertEqual((by_id["target_x"]["digits"], by_id["target_x"]["unit"]), (3, "m"))
        self.assertEqual((by_id["wall_x"]["digits"], by_id["wall_x"]["unit"]), (3, "m"))
        self.assertEqual(by_id["wall_stiffness"]["unit"], "N/m")

        qml = (ROOT / "src/mclab/application/qml/ExperimentControls.qml").read_text()
        self.assertIn("formatControlValue", qml)
        self.assertIn("onHeightChanged: Qt.callLater(panel.revealFocusedControl)", qml)
        self.assertIn("control.digits", qml)
        self.assertNotIn("value.toFixed(1)", qml)

    def test_wide_observation_keeps_the_core_control_set_compact(self) -> None:
        catalog = ScenarioCatalog.default()
        hands_on = [
            scenario_payload(scenario, Translator("en"))
            for scenario in catalog.all()
            if scenario.completion.requires_learner_control
            or scenario.completion.requires_observation
        ]
        for scenario in hands_on:
            with self.subTest(scenario=scenario["id"]):
                self.assertGreater(len(scenario["controls"]), 0)
                self.assertLessEqual(len(scenario["controls"]), 5)

        qml_root = ROOT / "src/mclab/application/qml"
        controls = (qml_root / "ExperimentControls.qml").read_text(encoding="utf-8")
        evidence = (qml_root / "EvidenceWorkflow.qml").read_text(encoding="utf-8")
        experiment = (qml_root / "ExperimentPage.qml").read_text(encoding="utf-8")
        self.assertIn("columns: compact ? 1 : 2", controls)
        self.assertIn("Accessible.role: Accessible.Pane", controls)
        self.assertIn('"Core experiment controls"', controls)
        self.assertIn("columns: 2", evidence)
        self.assertIn("Layout.preferredHeight: 44", evidence)
        self.assertIn("Math.min(360, Math.max(310, page.width * 0.28))", experiment)

    def test_hands_on_prediction_prompts_match_the_physics_context(self) -> None:
        catalog = ScenarioCatalog.default()
        expected = {
            "lab01.interactive-pull": ("감쇠", "damping"),
            "lab02.interactive-disturbance": ("P 게인", "P gain"),
            "lab03.interactive-tracking": ("추종", "tracking"),
            "lab03.interactive-2dof": ("손 목표", "hand target"),
            "lab03.dls-singularity-2dof": ("특이점", "singularity"),
            "lab04.interactive-joint-hold": ("관절 목표", "joint target"),
            "lab04.interactive-cartesian-reach": ("손끝 목표", "hand target"),
            "lab04.interactive-virtual-wall": ("접촉 힘", "contact force"),
        }
        evidence_ids = {
            scenario.id
            for scenario in catalog.all()
            if scenario.completion.requires_learner_control
            or scenario.completion.requires_observation
        }
        self.assertEqual(len(evidence_ids), 9)
        self.assertTrue(set(expected).issubset(evidence_ids))
        for scenario_id in evidence_ids:
            for language in ("ko", "en"):
                payload = scenario_payload(catalog.get(scenario_id), Translator(language))
                self.assertTrue(payload["predictionPrompt"].strip())
        for scenario_id, fragments in expected.items():
            for language, fragment in zip(("ko", "en"), fragments, strict=True):
                with self.subTest(scenario=scenario_id, language=language):
                    payload = scenario_payload(catalog.get(scenario_id), Translator(language))
                    prompt = payload["predictionPrompt"]
                    self.assertIn(fragment.casefold(), prompt.casefold())
                    self.assertLessEqual(len(prompt), 90)
                    self.assertIn(fragment.casefold(), prompt[:32].casefold())

    def test_scene_tokens_remain_distinct_with_color_vision_deficiencies(self) -> None:
        self.assertEqual(len(set(SEMANTIC_SHAPES.values())), len(SEMANTIC_SHAPES))
        for condition, metrics in color_vision_separation().items():
            with self.subTest(condition=condition):
                self.assertGreaterEqual(metrics["minimum_token_distance"], 24.0)
                self.assertGreaterEqual(metrics["minimum_background_distance"], 100.0)

    def test_korean_and_english_ui_keys_are_complete(self) -> None:
        self.assertEqual(missing_translation_keys(), {"en": set(), "ko": set()})
        self.assertEqual(Translator("ko").text("transport.replay"), "기록 재생")
        self.assertEqual(Translator("en").text("transport.replay"), "Replay recording")
        self.assertEqual(normalize_language("ko_KR"), "ko")
        self.assertEqual(normalize_language("en-US"), "en")
        with self.assertRaises(ValueError):
            normalize_language("fr")

    def test_every_scenario_has_a_korean_title(self) -> None:
        ids = {scenario.id for scenario in ScenarioCatalog.default().all()}
        self.assertEqual(ids - set(SCENARIO_TITLES_KO), set())

    def test_learning_path_payload_explains_order_completion_and_next_step(self) -> None:
        catalog = ScenarioCatalog.default()
        payload = learning_path_payload(
            catalog.learning_path(),
            Translator("ko"),
            {"lab01.default", "lab01.interactive-pull"},
        )

        self.assertEqual(len(payload), 11)
        self.assertEqual([item["step"] for item in payload], list(range(1, 12)))
        self.assertTrue(payload[0]["completed"])
        self.assertTrue(payload[2]["isNext"])

    def test_course_progress_counts_only_successful_runs_and_has_a_true_end_state(self) -> None:
        catalog = ScenarioCatalog.default()
        path = catalog.learning_path()
        with tempfile.TemporaryDirectory() as tmp:
            for index, (scenario, status) in enumerate(
                zip(path[:3], ("completed", "stopped", "error"), strict=True)
            ):
                run = Path(tmp) / f"run-{index}"
                run.mkdir()
                (run / "manifest.json").write_text(
                    json.dumps({"scenario_id": scenario.id, "status": status}),
                    encoding="utf-8",
                )
            records = ArtifactRepository(tmp).list_runs()
            progress = course_progress_payload(path, Translator("ko"), records)

        self.assertEqual(progress["done"], 1)
        self.assertFalse(progress["complete"])
        self.assertEqual(progress["nextId"], path[1].id)
        self.assertTrue(progress["path"][0]["completed"])
        self.assertTrue(progress["path"][1]["isNext"])

        with tempfile.TemporaryDirectory() as tmp:
            for index, scenario in enumerate(path):
                run = Path(tmp) / f"run-{index}"
                run.mkdir()
                (run / "manifest.json").write_text(
                    json.dumps({"scenario_id": scenario.id, "status": "completed"}),
                    encoding="utf-8",
                )
            ready_for_compare = course_progress_payload(
                path,
                Translator("en"),
                ArtifactRepository(tmp).list_runs(),
            )
            batch_run = Path(tmp) / "all-compare"
            batch_run.mkdir()
            (batch_run / "manifest.json").write_text(
                json.dumps({"scenario_id": ALL_COMPARE_ID, "status": "completed"}),
                encoding="utf-8",
            )
            complete = course_progress_payload(
                path,
                Translator("en"),
                ArtifactRepository(tmp).list_runs(),
            )

        self.assertEqual(ready_for_compare["done"], len(path))
        self.assertEqual(ready_for_compare["total"], len(path) + 1)
        self.assertFalse(ready_for_compare["complete"])
        self.assertEqual(ready_for_compare["nextId"], ALL_COMPARE_ID)
        self.assertEqual(ready_for_compare["nextKind"], "batch")
        self.assertTrue(ready_for_compare["path"][-1]["isNext"])
        self.assertEqual(complete["done"], len(path) + 1)
        self.assertTrue(complete["complete"])
        self.assertEqual(complete["nextId"], "")
        self.assertEqual(complete["next"], {})
        self.assertFalse(any(item["isNext"] for item in complete["path"]))

    def test_course_batch_launch_metadata_and_progress_parser_are_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": tmp}
        ):
            output = create_all_compare_output()
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            program, arguments = all_compare_command(output)
            update_batch_manifest(output, status="stopped")
            stopped = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["scenario_id"], ALL_COMPARE_ID)
        self.assertEqual(manifest["status"], "running")
        self.assertEqual(program, sys.executable)
        self.assertEqual(arguments[-4:], ["batch", "all", "--output-dir", str(output)])
        self.assertEqual(stopped["status"], "stopped")
        self.assertIn("finished_at", stopped)
        self.assertEqual(
            parse_batch_progress("MCLAB_BATCH_PROGRESS 3/5 lab03_2dof_compare"),
            (3, 5, "lab03_2dof_compare"),
        )
        self.assertIsNone(parse_batch_progress("MCLAB_BATCH_PROGRESS 3/5"))
        self.assertIsNone(parse_batch_progress("MCLAB_BATCH_PROGRESS 6/5 invalid"))
        self.assertIsNone(parse_batch_progress("ordinary output"))

    @unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 is not installed")
    def test_qt_batch_process_reports_progress_failure_and_cancellation(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEventLoop, QObject, QProcess, QTimer, Signal
        from PySide6.QtGui import QGuiApplication

        application = QGuiApplication.instance() or QGuiApplication([])
        controller_type = create_batch_controller(QObject, QProcess, QTimer, Signal)

        def exercise(code: str, expected_signal: str) -> tuple[object, Path]:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            output = Path(temporary.name) / "batch"
            output.mkdir()
            update_batch_manifest(output, status="running")
            loop = QEventLoop()
            received: list[tuple[str, tuple[object, ...]]] = []
            controller = controller_type()
            controller.completed.connect(
                lambda *args: (received.append(("completed", args)), loop.quit())
            )
            controller.stopped.connect(
                lambda *args: (received.append(("stopped", args)), loop.quit())
            )
            controller.failed.connect(
                lambda *args: (received.append(("failed", args)), loop.quit())
            )
            with (
                patch(
                    "mclab.application.qt_batch.create_all_compare_output",
                    return_value=output,
                ),
                patch(
                    "mclab.application.qt_batch.all_compare_command",
                    return_value=(sys.executable, ["-u", "-c", code]),
                ),
            ):
                controller.start()
                if expected_signal == "stopped":
                    QTimer.singleShot(100, controller.cancel)
                QTimer.singleShot(4000, loop.quit)
                loop.exec()
            application.processEvents()
            self.assertTrue(received, "batch controller timed out without a terminal signal")
            self.assertEqual(received[0][0], expected_signal)
            return controller, output

        completed, completed_output = exercise(
            "print('MCLAB_BATCH_PROGRESS 2/5 lab02'); "
            "print('MCLAB_BATCH_PROGRESS 5/5 lab04')",
            "completed",
        )
        self.assertEqual((completed.current, completed.total, completed.name), (5, 5, "lab04"))
        self.assertEqual(
            json.loads((completed_output / "manifest.json").read_text())["status"],
            "completed",
        )

        failed, failed_output = exercise("print('injected batch failure'); raise SystemExit(7)", "failed")
        self.assertIn("injected batch failure", failed._tail)  # noqa: SLF001
        self.assertEqual(
            json.loads((failed_output / "manifest.json").read_text())["status"],
            "error",
        )

        _stopped, stopped_output = exercise("import time; time.sleep(10)", "stopped")
        self.assertEqual(
            json.loads((stopped_output / "manifest.json").read_text())["status"],
            "stopped",
        )

    def test_qml_components_respect_component_size_gate_and_visual_tokens(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        for path in qml_root.glob("*.qml"):
            with self.subTest(path=path.name):
                self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 400)
        source = "\n".join(path.read_text(encoding="utf-8") for path in qml_root.glob("*.qml"))
        for token in ("#F5F7FB", "#172033", "#2563EB", "#FFDD00", "#111827"):
            self.assertIn(token, source)
        self.assertIn("implicitHeight: 48", (qml_root / "MButton.qml").read_text())
        button_source = (qml_root / "MButton.qml").read_text(encoding="utf-8")
        self.assertIn("advanceWidth(text)", button_source)
        self.assertIn("Text.ElideNone", button_source)
        self.assertIn(
            "control.activeFocus ? 4 : !control.enabled ? 2 : control.secondary ? 2 : 0",
            button_source,
        )
        self.assertIn(
            'control.activeFocus ? "#FFDD00" : !control.enabled ? "#64748B"',
            button_source,
        )
        self.assertIn('!control.enabled ? "#E2E8F0"', button_source)
        self.assertIn('!control.enabled ? "#475569"', button_source)
        self.assertIn("!control.enabled ? 2", button_source)
        main_source = (qml_root / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("implicitWidth: Math.max(44, contentItem.implicitWidth + 16)", main_source)
        self.assertIn("implicitHeight: 44", main_source)
        home_source = (qml_root / "HomePage.qml").read_text(encoding="utf-8")
        tour_source = (qml_root / "TourStrip.qml").read_text(encoding="utf-8")
        environment_source = (qml_root / "EnvironmentStatusCard.qml").read_text(
            encoding="utf-8"
        )
        self.assertIn("backend.setupStatus.action", environment_source)
        self.assertEqual(home_source.count("EnvironmentStatusCard"), 2)
        self.assertIn("backend.courseProgress", home_source)
        self.assertIn("MProgressBar", home_source)
        self.assertIn('visible: !strip.compact && index < 2', tour_source)
        self.assertIn('color: "#4F8FF7"', tour_source)
        progress_source = (qml_root / "MProgressBar.qml").read_text(encoding="utf-8")
        self.assertIn('control.complete ? "#16794B" : "#2563EB"', progress_source)
        results = (qml_root / "ResultsPage.qml").read_text(encoding="utf-8")
        manage = (qml_root / "ResultManageDialog.qml").read_text(encoding="utf-8")
        for action in ("transport.replay", "transport.rerun", "transport.tuned"):
            self.assertIn(action, results + manage)
        self.assertIn('objectName: index === 0 ? "firstResultPrimaryAction"', results)
        self.assertIn("function focusFirstPrimary()", results)
        self.assertIn("primaryAction.launchesSession", results)
        self.assertIn("backend.rerunSavedRun(modelData.path, false)", results)
        explore = (qml_root / "ExplorePage.qml").read_text(encoding="utf-8")
        scenario_card = (qml_root / "ScenarioCard.qml").read_text(encoding="utf-8")
        self.assertIn("property var scenarioItems: backend.scenarios", explore)
        self.assertEqual(explore.count("backend.scenarios"), 1)
        self.assertIn("ScrollFocusHelper", explore)
        self.assertIn("onFocusRevealRequested", explore)
        self.assertIn("scenarioFocusScroll.reveal", explore)
        self.assertIn("scenario.displayTitle || scenario.title", scenario_card)
        self.assertEqual(scenario_card.count("scenario.displayTitle || scenario.title"), 2)
        self.assertIn("property bool inlineAction: width >= 560", scenario_card)
        self.assertIn("implicitHeight: inlineAction ? 128 : 154", scenario_card)
        self.assertIn("columns: card.inlineAction ? 2 : 1", scenario_card)
        self.assertIn("focusRevealRequested(card)", scenario_card)
        self.assertIn("resultFocusScroll.reveal", results)
        self.assertIn("resultCard, 4", results)
        self.assertIn("resultRepeater.itemAt(firstNewIndex)", results)
        self.assertIn("card.primaryControl.forceActiveFocus()", results)
        self.assertTrue((qml_root / "ScrollFocusHelper.qml").is_file())
        experiment = (qml_root / "ExperimentPage.qml").read_text(encoding="utf-8")
        scene_guide = (qml_root / "OneDSceneGuide.qml").read_text(encoding="utf-8")
        self.assertIn("OneDSceneGuide", experiment)
        active_session = (qml_root / "ActiveSessionBar.qml").read_text(encoding="utf-8")
        for context in (experiment, active_session):
            self.assertIn("backend.selectedScenario.displayTitle", context)
            self.assertIn("|| backend.selectedScenario.title", context)
        self.assertIn("visible: backend.safeMode", scene_guide)
        for responsive_scene_contract in (
            "property real sceneScale",
            "Math.min(width / 1000.0",
            "height / 520.0",
            "property real floorLineY",
            "property real massCenterX",
            "guide.massMidY - guide.massHeight / 2 - height",
            "guide.floorLineY + 16 * guide.sceneScale",
        ):
            self.assertIn(responsive_scene_contract, scene_guide)
        scene_keys = (
            "scene.spring",
            "scene.damper",
            "scene.mass_block",
            "scene.equilibrium",
        )
        for key in scene_keys:
            self.assertIn(key, scene_guide)
        spatial_guide = (qml_root / "SpatialSceneGuide.qml").read_text(encoding="utf-8")
        self.assertIn("SpatialSceneGuide", experiment)
        self.assertIn("visible: backend.safeMode", spatial_guide)
        for direct_hand_label_contract in (
            "property real currentMarkerX",
            "property real targetMarkerX",
            "property real labelScale",
            'visible: !guide.compact && (guide.isTwoLink || guide.isPanda)',
            '"scene.current_hand"',
            '"scene.target_hand"',
            "guide.isWall ? Math.max(8, guide.targetMarkerX - width - 14)",
        ):
            self.assertIn(direct_hand_label_contract, spatial_guide)
        spatial_keys = (
            "scene.joints",
            "scene.panda_arm",
            "scene.current_hand",
            "scene.target_hand",
            "legend.workspace",
            "legend.wall",
        )
        for key in spatial_keys:
            self.assertIn(key, spatial_guide)

    def test_compact_legend_and_contextual_accessibility_names_do_not_regress(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        experiment = (qml_root / "ExperimentPage.qml").read_text(encoding="utf-8")
        scene_hud = (qml_root / "SceneHud.qml").read_text(encoding="utf-8")
        scenario_card = (qml_root / "ScenarioCard.qml").read_text(encoding="utf-8")
        results = (qml_root / "ResultsPage.qml").read_text(encoding="utf-8")
        manage = (qml_root / "ResultManageDialog.qml").read_text(encoding="utf-8")

        self.assertIn("SceneHud", experiment)
        self.assertIn("height: compact ? 28 : 38", scene_hud)
        self.assertIn("legendDescription()", experiment)
        self.assertIn("markerPrefix + legendDescription", scene_hud)
        self.assertNotIn("visible: !hud.cameraFocused", scene_hud)
        self.assertNotIn("visible: !compact\n                    anchors.bottom", experiment)
        self.assertIn(
            'accessibleName: text + ": " + (scenario.displayTitle || scenario.title || "")',
            scenario_card,
        )
        self.assertIn(
            'accessibleName: text + ": " + modelData.lab + " · " + modelData.title + " · " + modelData.runLabel',
            results,
        )
        home = (qml_root / "HomePage.qml").read_text(encoding="utf-8")
        self.assertIn("backend.setupStatus.ready", home)
        self.assertIn("course.next.ready", home)
        self.assertIn('course.complete ? backend.navigate("results")', home)
        path = (qml_root / "LearningPathPage.qml").read_text(encoding="utf-8")
        self.assertEqual(path.count("MButton {"), 1)
        self.assertNotIn("ScenarioCard", path)
        self.assertIn(
            'backend.localizedText(backend.language, "path.review_results")', path
        )
        self.assertIn("dialog.run.availability", manage)
        self.assertIn("ResultManageDialog", results)
        self.assertIn(
            'backend.localizedText(backend.language, "results.start_first")', results
        )
        self.assertIn(
            'backend.localizedText(backend.language, "results.report")', results
        )
        self.assertIn(
            "backend.deleteRun(manageDialog.run.path, manageDialog.run.name)",
            results,
        )
        transport = (qml_root / "TransportBar.qml").read_text(encoding="utf-8")
        controls = (qml_root / "ExperimentControls.qml").read_text(encoding="utf-8")
        evidence = (qml_root / "EvidenceWorkflow.qml").read_text(encoding="utf-8")
        self.assertNotIn("\n                visible: backend.hasReplay && !compact\n", transport)
        self.assertIn("backend.sessionState === \"completed\" && backend.hasReplay", transport)
        self.assertIn('backend.sessionState !== "completed"', transport)
        self.assertIn("backend.hasReplay || panel.needsEvidenceRetry", controls)
        self.assertIn("backend.hasReplay ? 4", experiment)
        self.assertIn("!backend.hasPrediction ? 1", experiment)
        evidence = (qml_root / "EvidenceWorkflow.qml").read_text(encoding="utf-8")
        self.assertIn('inputObjectName: "predictionInput"', evidence)
        self.assertIn('inputObjectName: "observationInput"', evidence)
        self.assertIn('objectName: "outcomeSelector"', evidence)
        self.assertIn('backend.localizedText(backend.language, "experiment.saved_results")', experiment)
        self.assertIn('? "results" : "home"', experiment)
        for source in (experiment, evidence, controls, transport):
            self.assertIn("needsEvidenceRetry", source)
        self.assertIn(
            'secondary: !(backend.sessionState === "completed"', experiment
        )
        self.assertIn("Qt.callLater(transport.focusPrimary)", experiment)
        self.assertIn(
            "if (backend.waitingForPrediction)\n                    "
            "Qt.callLater(controls.focusEvidence)",
            experiment,
        )
        self.assertIn("!workflow.needsEvidenceRetry", evidence)
        self.assertIn("!panel.needsEvidenceRetry", controls)
        self.assertIn("&& !bar.needsEvidenceRetry", transport)
        self.assertIn('backend.localizedText(backend.language, "evidence.restart_first")', transport)
        self.assertIn("onClicked: backend.seekEvent(index)", transport)
        self.assertIn("height: 24", transport)
        self.assertIn("Layout.preferredHeight: 24", transport)
        self.assertIn('text: (checked ? "✓ "', transport)
        self.assertIn('compact ? "transport.loop_short" : "transport.loop"', transport)

    def test_experiment_primary_action_hierarchy_follows_the_learning_stage(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        experiment = (qml_root / "ExperimentPage.qml").read_text(encoding="utf-8")
        controls = (qml_root / "ExperimentControls.qml").read_text(encoding="utf-8")
        transport = (qml_root / "TransportBar.qml").read_text(encoding="utf-8")

        self.assertIn("function primaryActionIndex()", controls)
        self.assertIn("index !== panel.primaryActionIndex()", controls)
        self.assertIn("backend.hasLearnerAction", controls)
        self.assertIn("property bool experimentActionIsPrimary", transport)
        self.assertIn("property bool evidenceEntryIsPrimary", transport)
        self.assertIn("|| bar.experimentActionIsPrimary", transport)
        self.assertIn("|| bar.evidenceEntryIsPrimary", transport)
        self.assertEqual(
            transport.count("visible: backend.hasReplay\n                secondary: true"),
            4,
        )
        self.assertIn('text: (checked ? "✓ "', transport)
        self.assertIn(
            'secondary: !(backend.sessionState === "completed"', experiment
        )

    def test_evidence_entries_share_scroll_affordance_and_keyboard_handoff(self) -> None:
        evidence = (
            ROOT / "src/mclab/application/qml/EvidenceWorkflow.qml"
        ).read_text(encoding="utf-8")
        editor = (
            ROOT / "src/mclab/application/qml/EvidenceTextArea.qml"
        ).read_text(encoding="utf-8")

        self.assertEqual(evidence.count("EvidenceTextArea {"), 2)
        for contract in (
            'inputObjectName: "predictionInput"',
            'scrollerObjectName: "predictionScroller"',
            'scrollBarObjectName: "predictionVerticalScrollBar"',
            "maximumLength: 240",
            "tabTarget: savePredictionButton",
            'inputObjectName: "observationInput"',
            'scrollerObjectName: "observationScroller"',
            'scrollBarObjectName: "observationVerticalScrollBar"',
            "maximumLength: 300",
            "tabTarget: outcomeSelector",
        ):
            self.assertIn(contract, evidence)
        for contract in (
            "policy: ScrollBar.AsNeeded",
            "minimumSize: 0.25",
            "visible: editor.contentHeight > control.availableHeight + 0.5",
            "anchors.right: parent.right",
            '? "#334155" : "#64748B"',
            "wrapMode: TextEdit.WordWrap",
            "KeyNavigation.tab: control.tabTarget",
            "if (length > control.maximumLength)",
            "remove(control.maximumLength, length)",
        ):
            self.assertIn(contract, editor)

    def test_scene_camera_gestures_are_discoverable_by_mouse_keyboard_and_accessibility(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        experiment = (qml_root / "ExperimentPage.qml").read_text(encoding="utf-8")
        scene_hud = (qml_root / "SceneHud.qml").read_text(encoding="utf-8")
        controls = (qml_root / "ExperimentControls.qml").read_text(encoding="utf-8")
        evidence = (qml_root / "EvidenceWorkflow.qml").read_text(encoding="utf-8")

        self.assertIn('objectName: "sceneCameraArea"', experiment)
        self.assertIn("activeFocusOnTab: true", experiment)
        self.assertIn("hoverEnabled: true", experiment)
        self.assertIn("Qt.OpenHandCursor", experiment)
        self.assertIn('"control.camera_help"', experiment)
        self.assertIn("Keys.onLeftPressed", experiment)
        self.assertIn("Qt.ShiftModifier", experiment)
        self.assertIn("Qt.Key_Plus", experiment)
        self.assertIn("Qt.Key_0", experiment)
        self.assertIn("FocusRing", experiment)
        self.assertIn("SceneHud", experiment)
        self.assertIn(
            "page.compact ? Image.PreserveAspectCrop : Image.PreserveAspectFit",
            experiment,
        )
        self.assertIn("visible: !compact", experiment)
        self.assertIn('compactActionPrompt: backend.selectedScenario.nowPrompt || ""', experiment)
        self.assertIn("workflowPrompt: page.nowPrompt()", experiment)
        self.assertIn("property string compactActionPrompt", controls)
        self.assertIn("property string workflowPrompt", controls)
        self.assertIn("compactActionPrompt: panel.compactActionPrompt", controls)
        self.assertIn("function focusEvidence()", controls)
        self.assertIn("flick.contentY = 0", controls)
        self.assertIn("property string compactActionPrompt", evidence)
        self.assertIn("Accessible.ignored: !compact || backend.hasPrediction", evidence)
        self.assertIn("compact && workflow.compactActionPrompt", evidence)
        self.assertIn('"control.camera_keyboard_short"', scene_hud)
        self.assertIn('"control.camera_keyboard_micro"', scene_hud)
        self.assertIn("markerPrefix + legendDescription", scene_hud)
        self.assertIn("visible: hud.cameraFocused", scene_hud)
        self.assertNotIn("visible: !hud.cameraFocused", scene_hud)
        self.assertIn('objectName: "sceneCameraReset"', controls)
        self.assertIn('"control.reset_camera_help"', controls)
        self.assertIn("visible: resetCameraButton.hovered || resetCameraButton.activeFocus", controls)
        self.assertIn("width: resetCameraButton.width", controls)

    def test_core_keyboard_controls_use_redundant_yellow_black_focus_rings(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        for name in (
            "FocusRing.qml",
            "MButton.qml",
            "LanguageSelector.qml",
            "SpeedSelector.qml",
            "EvidenceWorkflow.qml",
        ):
            with self.subTest(name=name):
                source = (qml_root / name).read_text(encoding="utf-8")
                self.assertIn("#FFDD00", source)
                self.assertIn("#000000", source)
        for name in ("ExperimentControls.qml", "ExplorePage.qml", "TransportBar.qml", "Main.qml"):
            with self.subTest(name=name):
                self.assertIn(
                    "FocusRing",
                    (qml_root / name).read_text(encoding="utf-8"),
                )

    def test_checkboxes_have_explicit_redundant_high_contrast_states(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        checkbox_path = qml_root / "MCheckBox.qml"
        self.assertTrue(checkbox_path.is_file())
        checkbox = checkbox_path.read_text(encoding="utf-8")

        for token in (
            "implicitHeight: 44",
            "implicitWidth: 28",
            'border.color: control.enabled ? "#64748B"',
            'color: control.checked ? "#2563EB" : "#FFFFFF"',
            'text: "✓"',
            'color: "#FFFFFF"',
            "visible: control.checked",
            "wrapMode: Text.NoWrap",
            "FocusRing",
        ):
            self.assertIn(token, checkbox)
        self.assertNotIn("wrapMode: Text.WordWrap", checkbox)
        for name in ("Main.qml", "ExperimentControls.qml"):
            source = (qml_root / name).read_text(encoding="utf-8")
            self.assertIn("MCheckBox {", source)

    def test_result_metric_labels_use_readable_beginner_typography(self) -> None:
        results = (
            ROOT / "src/mclab/application/qml/ResultsPage.qml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("font.pixelSize: 10", results)
        self.assertIn('color: "#475569"', results)
        self.assertIn("font.bold: true", results)

    def test_replay_position_uses_readable_compact_typography(self) -> None:
        transport = (
            ROOT / "src/mclab/application/qml/TransportBar.qml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("compact ? 9 : 11", transport)
        self.assertIn(
            'color: "#334155"; font.pixelSize: 12; font.bold: true',
            transport,
        )
        self.assertIn("id: replayPositionLabel", transport)
        self.assertIn("anchors.right: replayPositionLabel.left", transport)

    def test_results_only_latest_card_uses_filled_primary_action(self) -> None:
        results = (
            ROOT / "src/mclab/application/qml/ResultsPage.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("secondary: index > 0", results)
        self.assertEqual(results.count("enabled: launchesSession ?"), 1)

    def test_modal_dialogs_share_high_contrast_surface_boundaries(self) -> None:
        main = (
            ROOT / "src/mclab/application/qml/Main.qml"
        ).read_text(encoding="utf-8")
        manage = (
            ROOT / "src/mclab/application/qml/ResultManageDialog.qml"
        ).read_text(encoding="utf-8")

        self.assertNotIn('border.color: "#A9B8CE"', main)
        for source in (main, manage):
            self.assertIn('color: "#FFFFFF"', source)
            self.assertIn("radius: 12", source)
            self.assertIn('border.color: "#64748B"', source)
            self.assertIn("border.width: 2", source)

    def test_core_evidence_inputs_have_three_to_one_inactive_boundaries(self) -> None:
        evidence = (
            ROOT / "src/mclab/application/qml/EvidenceWorkflow.qml"
        ).read_text(encoding="utf-8")
        editor = (
            ROOT / "src/mclab/application/qml/EvidenceTextArea.qml"
        ).read_text(encoding="utf-8")

        self.assertEqual(evidence.count("EvidenceTextArea {"), 2)
        self.assertEqual(editor.count("editor.activeFocus ? 4 : 2"), 1)
        self.assertEqual(evidence.count("outcomeSelector.activeFocus ? 4 : 2"), 1)
        self.assertIn('editor.activeFocus ? "#FFDD00" : "#64748B"', editor)
        self.assertIn(
            'outcomeSelector.activeFocus ? "#FFDD00" : "#64748B"', evidence
        )
        self.assertIn('compact ? "evidence.save_observation_short"', evidence)
        self.assertIn('compact ? "evidence.outcome_select_short"', evidence)
        self.assertIn('backend.language, "evidence.save_observation"', evidence)

    def test_experiment_and_modal_focus_contract_is_explicit(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        experiment = (qml_root / "ExperimentPage.qml").read_text(encoding="utf-8")
        transport = (qml_root / "TransportBar.qml").read_text(encoding="utf-8")
        controls = (qml_root / "ExperimentControls.qml").read_text(encoding="utf-8")
        results = (qml_root / "ResultsPage.qml").read_text(encoding="utf-8")
        manage = (qml_root / "ResultManageDialog.qml").read_text(encoding="utf-8")
        main = (qml_root / "Main.qml").read_text(encoding="utf-8")

        self.assertIn("transport.focusPrimary()", experiment)
        self.assertIn("function focusAfterEvidenceSaved()", experiment)
        self.assertIn("controls.showEvidenceComplete()", experiment)
        self.assertIn("savedResultsButton.forceActiveFocus()", experiment)
        self.assertIn(
            "onEvidenceSaved: Qt.callLater(page.focusAfterEvidenceSaved)", experiment
        )
        self.assertIn("primaryTransportButton.forceActiveFocus()", transport)
        self.assertIn("onOpened: closeButton.forceActiveFocus()", manage)
        self.assertIn("page.openManager(modelData, manageButton)", results)
        self.assertIn("target.forceActiveFocus()", manage)
        self.assertIn("onOpened: closeErrorButton.forceActiveFocus()", main)
        self.assertIn("onAboutToShow: returnFocusItem = window.activeFocusItem", main)
        self.assertIn("target.forceActiveFocus()", main)
        self.assertIn("Accessible.name: text", main)
        self.assertIn("function revealControl(control)", controls)
        self.assertIn("signal evidenceSaved()", controls)
        self.assertIn("onObservationCommitted: panel.evidenceSaved()", controls)
        completion_function = controls.split("function showEvidenceComplete()", 1)[1].split(
            "function focusEvidence()", 1
        )[0]
        self.assertNotIn("focusFirstExperimentControl", completion_function)
        self.assertGreaterEqual(controls.count("panel.revealControl("), 4)
        evidence = (qml_root / "EvidenceWorkflow.qml").read_text(encoding="utf-8")
        self.assertIn("workflow.revealRequested", evidence)

    def test_live_progress_and_replay_timeline_have_distinct_semantics(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        transport = (qml_root / "TransportBar.qml").read_text(encoding="utf-8")
        speed_selector = (qml_root / "SpeedSelector.qml").read_text(encoding="utf-8")
        qt_backend = (ROOT / "src/mclab/application/qt_app.py").read_text(encoding="utf-8")
        translations = (ROOT / "src/mclab/application/i18n.py").read_text(encoding="utf-8")

        self.assertIn("visible: !backend.hasReplay", transport)
        self.assertIn('"transport.progress"', transport)
        self.assertIn('"transport.progress_help"', transport)
        self.assertIn("visible: backend.hasReplay", transport)
        self.assertIn('"transport.timeline"', transport)
        self.assertIn('"transport.timeline_help"', transport)
        self.assertIn("backend.telemetry.playback_speed", speed_selector)
        self.assertIn('"playback_speed": self._speed', qt_backend)
        self.assertEqual(qt_backend.count("session.set_speed(self._speed)"), 2)
        for label in ("Experiment progress", "Replay timeline", "실험 진행률", "기록 재생 타임라인"):
            self.assertIn(label, translations)

    def test_desktop_ui_has_no_nonessential_motion_to_disable(self) -> None:
        qml_root = ROOT / "src/mclab/application/qml"
        source = "\n".join(path.read_text(encoding="utf-8") for path in qml_root.glob("*.qml"))
        for animation in (
            "Behavior on",
            "NumberAnimation",
            "PropertyAnimation",
            "SequentialAnimation",
            "SmoothedAnimation",
        ):
            with self.subTest(animation=animation):
                self.assertNotIn(animation, source)

    def test_visual_tokens_meet_text_and_graphic_contrast_gates(self) -> None:
        for foreground, background, threshold in (
            ("#172033", "#F5F7FB", 4.5),
            ("#475569", "#FFFFFF", 4.5),
            ("#FFFFFF", "#2563EB", 4.5),
            ("#FFFFFF", "#64748B", 4.5),
            ("#704000", "#FFF7E6", 4.5),
            ("#22D3EE", "#111827", 3.0),
            ("#D8A7FF", "#111827", 3.0),
            ("#FF8FA3", "#111827", 3.0),
            ("#FFD56A", "#111827", 3.0),
            ("#166534", "#E7F8EF", 4.5),
            ("#991B1B", "#FEECEC", 4.5),
            ("#FFFFFF", "#B42318", 4.5),
            ("#2563EB", "#D7DFEA", 3.0),
            ("#16794B", "#D7DFEA", 3.0),
            ("#4F8FF7", "#FFFFFF", 3.0),
            ("#475569", "#E2E8F0", 4.5),
            ("#64748B", "#E2E8F0", 3.0),
        ):
            with self.subTest(foreground=foreground, background=background):
                self.assertGreaterEqual(_contrast_ratio(foreground, background), threshold)

    def test_explore_search_placeholder_and_outline_meet_contrast_gates(self) -> None:
        source = (ROOT / "src/mclab/application/qml/ExplorePage.qml").read_text()

        self.assertIn('placeholderTextColor: "#5B6475"', source)
        self.assertIn('border.color: "#64748B"', source)
        self.assertIn("border.width: 2", source)
        self.assertGreaterEqual(_contrast_ratio("#5B6475", "#FFFFFF"), 4.5)
        self.assertGreaterEqual(_contrast_ratio("#64748B", "#FFFFFF"), 3.0)

    def test_spring_overlay_deforms_with_the_mass_position(self) -> None:
        near = spring_polyline((-1.4, 0.0, 0.1), (-0.2, 0.0, 0.1))
        far = spring_polyline((-1.4, 0.0, 0.1), (0.4, 0.0, 0.1))

        self.assertEqual(near[0], far[0])
        self.assertNotEqual(near[-1], far[-1])
        self.assertGreater(far[5][0], near[5][0])

    def test_one_dof_visual_guides_do_not_collide_with_the_plant(self) -> None:
        for model_name in ("lab01_msd", "lab02_pid"):
            xml = (ROOT / "models" / model_name / "scene.xml").read_text(encoding="utf-8")
            self.assertRegex(xml, r'name="rail"[^>]+contype="0" conaffinity="0"')
            self.assertRegex(xml, r'name="block_geom"[^>]+contype="0" conaffinity="0"')

    def test_common_korean_runtime_error_is_localized(self) -> None:
        detail, action = localized_error(
            "ko",
            "Cannot apply an action while completed.",
            "Return to the live experiment before changing controls.",
        )
        self.assertNotIn("Cannot apply", detail)
        self.assertIn("실험이 끝났습니다", detail)
        self.assertEqual(action, "실험 제어를 바꾸려면 실시간 실험으로 돌아가세요.")
        detail, action = localized_error(
            "ko",
            "The course comparison is already running.",
            "Use Cancel comparison or wait for the five sets to finish.",
        )
        self.assertEqual(detail, "전체 과정 비교가 이미 실행 중입니다.")
        self.assertIn("비교 실행 취소", action)

    def test_unknown_runtime_error_is_hidden_from_beginner_message(self) -> None:
        raw = "KeyError: 'Unsupported Lab01 action: invalid_beta_action'"
        detail, action = localized_error("ko", raw, "안전 모드로 다시 시도하세요.")
        self.assertEqual(detail, "요청을 처리하지 못했습니다.")
        self.assertNotIn("KeyError", detail)
        self.assertEqual(action, "안전 모드로 다시 시도하세요.")
        detail, action = localized_error("en", raw, "Retry in safe mode.")
        self.assertEqual(detail, "The request could not be completed.")
        self.assertNotIn("KeyError", detail)
        self.assertEqual(action, "Retry in safe mode.")

    def test_new_application_modules_respect_python_size_gate(self) -> None:
        for path in (ROOT / "src/mclab/application").glob("*.py"):
            with self.subTest(path=path.name):
                self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 800)

    def test_desktop_app_rejects_a_second_process_before_creating_a_gui(self) -> None:
        source = (ROOT / "src/mclab/application/qt_app.py").read_text(encoding="utf-8")
        self.assertLess(
            source.index("acquire_instance_lock(language)"),
            source.index("QGuiApplication.instance()"),
        )
        self.assertIn("instance_lock.unlock()", source)
        lock_source = (ROOT / "src/mclab/application/single_instance.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("instance_lock.setStaleLockTime(0)", lock_source)
        self.assertIn("instance_lock.tryLock(0)", lock_source)
        self.assertIn('translator = Translator(language)', lock_source)
        self.assertIn('"error.app_activated" if activated else "error.app_running"', lock_source)
        self.assertIn("def start_activation_server", lock_source)
        self.assertIn("QLocalServer", lock_source)
        self.assertIn("requestActivate", lock_source)
        self.assertIn("_request_existing_window", lock_source)
        self.assertIn("start_activation_server", source)
        startup_audit = (ROOT / "scripts/audit_app_startup.py").read_text(encoding="utf-8")
        self.assertIn("_duplicate_instance_probe", startup_audit)
        self.assertIn('second.returncode == 6', startup_audit)
        self.assertIn("activation_count == 1", startup_audit)
        self.assertIn('restart.returncode == 0', startup_audit)
        launcher = (ROOT / "scripts/start_mclab.py").read_text(encoding="utf-8")
        self.assertIn("_run(command, accepted=(0, 6))", launcher)

    def test_saved_results_distinguish_recording_rerun_and_last_tuning(self) -> None:
        catalog = ScenarioCatalog.default()
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "saved-run"
            run.mkdir()
            (run / "manifest.json").write_text(
                json.dumps(
                    {
                        "scenario_id": "lab01.default",
                        "status": "completed",
                        "config": {"resolved": {"mass": 7.0, "sim_time": 0.02}},
                    }
                ),
                encoding="utf-8",
            )
            (run / "summary.json").write_text("{}", encoding="utf-8")
            (run / "config.yaml").write_text("mass: 6.0\n", encoding="utf-8")
            (run / "learner_tuned_config.yaml").write_text(
                "mass: 9.0\nsim_time: 0.03\n", encoding="utf-8"
            )
            (run / "replay.npz").write_bytes(b"recording-marker")

            same = resolve_saved_run_launch(run, catalog)
            tuned = resolve_saved_run_launch(run, catalog, tuned=True)
            record = ArtifactRepository(Path(tmp)).list_runs()[0]

        self.assertEqual(same.scenario.id, "lab01.default")
        self.assertEqual(same.config["mass"], 7.0)
        self.assertEqual(tuned.config["mass"], 9.0)
        self.assertTrue(record.replay_available)
        self.assertTrue(record.rerun_available)
        self.assertTrue(record.tuned_available)
        interrupted = result_payloads(
            (replace(record, status="error"),), Translator("en")
        )[0]
        self.assertIn("replay the recording", interrupted["nextAction"])
        self.assertNotIn("rerun", interrupted["nextAction"])

    def test_results_disable_corrupt_recording_before_the_learner_clicks_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "broken-replay"
            run.mkdir()
            (run / "manifest.json").write_text(
                json.dumps({"scenario_id": "lab01.default", "status": "completed"}),
                encoding="utf-8",
            )
            (run / "config.yaml").write_text("mass: 1.0\n", encoding="utf-8")
            (run / "replay.npz").write_bytes(b"not a valid npz recording")
            repository = ArtifactRepository(tmp)
            quick = repository.list_runs()[0]
            checked = repository.list_runs(validate_replays=True)[0]

        self.assertTrue(quick.replay_available)
        self.assertFalse(checked.replay_available)
        self.assertTrue(checked.replay_reason)
        result = result_payloads((checked,), Translator("ko"))[0]
        self.assertIn("기록 없음", result["availability"])
        self.assertTrue(result["rerun"])
        self.assertEqual(result["title"], "자동 데모")
        self.assertEqual((result["status"], result["statusCode"]), ("기록 없음", "warning"))
        self.assertIn("완료", result["outcome"])

    def test_results_surface_localized_metrics_report_next_action_and_total_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "friendly-result"
            run.mkdir()
            (run / "manifest.json").write_text(
                json.dumps(
                    {
                        "scenario_id": "lab02.default",
                        "status": "completed",
                        "config": {"resolved": {"sim_time": 2.0}},
                    }
                ),
                encoding="utf-8",
            )
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        "duration": 2.0,
                        "steady_state_error": 0.004,
                        "settling_time": 0.8,
                        "overshoot_percent": 3.5,
                    }
                ),
                encoding="utf-8",
            )
            (run / "config.yaml").write_text("sim_time: 2.0\n", encoding="utf-8")
            (run / "report.html").write_text("<html></html>", encoding="utf-8")
            record = ArtifactRepository(tmp).list_runs(validate_replays=True)[0]
            result = result_payloads(
                (record,),
                Translator("ko"),
                ScenarioCatalog.default(),
            )[0]

        self.assertEqual(result["title"], "자동 데모")
        self.assertEqual(result["lab"], "LAB02")
        self.assertEqual(result["runLabel"], "최신")
        self.assertTrue(result["report"])
        self.assertIn("저장 실행 1개", result["collectionSummary"])
        self.assertIn("같은 설정", result["nextAction"])
        self.assertEqual(
            [item["label"] for item in result["metrics"]],
            ["최종 오차", "정착 시간", "오버슈트"],
        )

    def test_course_comparison_result_has_batch_semantics_without_fake_replay_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "all-compare"
            run.mkdir()
            (run / "manifest.json").write_text(
                json.dumps({"scenario_id": ALL_COMPARE_ID, "status": "completed"}),
                encoding="utf-8",
            )
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        "batch_name": "all",
                        "child_batches": 5,
                        "scenario_runs": 54,
                        "duration": 12.5,
                    }
                ),
                encoding="utf-8",
            )
            (run / "report.html").write_text("<html></html>", encoding="utf-8")
            record = ArtifactRepository(tmp).list_runs(validate_replays=True)[0]
            result = result_payloads(
                (record,), Translator("ko"), ScenarioCatalog.default()
            )[0]

        self.assertTrue(result["isBatch"])
        self.assertEqual(result["scenarioId"], ALL_COMPARE_ID)
        self.assertEqual((result["lab"], result["title"]), ("과정", "전체 과정 비교"))
        self.assertEqual((result["status"], result["statusCode"]), ("완료", "completed"))
        self.assertIn("리포트와 학습 활동지", result["availability"])
        self.assertIn("시나리오 실행 54개", result["outcome"])
        self.assertEqual(
            [item["label"] for item in result["metrics"]],
            ["비교 세트", "시나리오 실행", "실행 시간"],
        )
        self.assertIn("리포트", result["nextAction"])

        running = replace(record, status="running")
        stale = result_payloads((running,), Translator("en"))[0]
        active = result_payloads(
            (running,), Translator("en"), active_batch_path=running.path
        )[0]
        self.assertEqual((stale["status"], stale["statusCode"]), ("Stopped", "stopped"))
        self.assertIn("retry", stale["nextAction"])
        self.assertEqual((active["status"], active["statusCode"]), ("Running", "running"))
        self.assertIn("keep MCLab open", active["nextAction"])

    def test_saved_run_cleanup_requires_exact_confirmation_and_stays_in_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "delete-me"
            run.mkdir()
            (run / "manifest.json").write_text(
                json.dumps({"scenario_id": "lab01.default", "status": "completed"}),
                encoding="utf-8",
            )
            repository = ArtifactRepository(tmp)

            with self.assertRaisesRegex(ValueError, "exact folder name"):
                repository.delete_path(run, confirm_path="wrong-name")
            self.assertTrue(run.exists())
            repository.delete_path(run, confirm_path="delete-me")
            self.assertFalse(run.exists())

    def test_sixty_saved_runs_load_quickly_with_unique_progressive_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(60):
                run = Path(tmp) / f"saved-{index:03d}"
                run.mkdir()
                (run / "manifest.json").write_text(
                    json.dumps(
                        {
                            "scenario_id": "lab01.default",
                            "status": "completed",
                            "config": {"resolved": {"sim_time": 1.0}},
                        }
                    ),
                    encoding="utf-8",
                )
                (run / "summary.json").write_text(
                    json.dumps({"duration": 1.0, "max_abs_position": index / 100.0}),
                    encoding="utf-8",
                )
            started = time.perf_counter()
            records = ArtifactRepository(tmp).list_runs(validate_replays=True)
            results = result_payloads(records, Translator("en"), ScenarioCatalog.default())
            elapsed = time.perf_counter() - started

        self.assertEqual(len(results), 60)
        self.assertEqual(results[0]["runLabel"], "Latest")
        self.assertEqual(results[39]["runLabel"], "Older 40")
        self.assertEqual(len({item["runLabel"] for item in results}), 60)
        self.assertLess(elapsed, 2.0)
        results_qml = (ROOT / "src/mclab/application/qml/ResultsPage.qml").read_text()
        self.assertIn("property int visibleLimit: 20", results_qml)
        self.assertIn("page.runs.slice(0, page.visibleLimit)", results_qml)

    def test_representative_visible_controls_are_supported_by_all_lab_adapters(self) -> None:
        catalog = ScenarioCatalog.default()
        scenario_ids = (
            "lab01.interactive-pull",
            "lab02.interactive-disturbance",
            "lab03.condition-aware-dls-2dof",
            "lab04.interactive-virtual-wall",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for scenario_id in scenario_ids:
                with self.subTest(scenario_id=scenario_id):
                    scenario = catalog.get(scenario_id)
                    payload = scenario_payload(scenario, Translator("ko"))
                    adapter = create_scenario_adapter(
                        scenario,
                        dict(scenario.config),
                        output_dir=Path(tmp) / scenario_id,
                        safe_mode=True,
                    )
                    session = SimulationSession(adapter, duration=0.02)
                    session.start()
                    for control in payload["controls"]:
                        session.apply_action(control["id"], control["value"])
                    for action in payload["actions"]:
                        session.apply_action(action["id"])
                    session.apply_action("reset_camera")
                    session.apply_action("restore_defaults")
                    session.close()

    def test_lab04_prediction_frame_uses_configured_target_and_wall(self) -> None:
        scenario = ScenarioCatalog.default().get("lab04.interactive-virtual-wall")
        with tempfile.TemporaryDirectory() as tmp:
            adapter = create_scenario_adapter(
                scenario,
                dict(scenario.config),
                output_dir=Path(tmp),
                safe_mode=True,
            )
            session = SimulationSession(adapter, duration=0.02)
            session.start()

            self.assertAlmostEqual(adapter.last_wall, 0.57)
            np.testing.assert_allclose(adapter.last_target, [0.61, 0.0, 0.58])
            self.assertNotEqual(adapter.last_hand, adapter.last_target)
            session.close()

    def test_lab04_learner_camera_is_close_and_resettable(self) -> None:
        scenario = ScenarioCatalog.default().get("lab04.interactive-virtual-wall")
        with tempfile.TemporaryDirectory() as tmp:
            adapter = create_scenario_adapter(
                scenario,
                dict(scenario.config),
                output_dir=Path(tmp),
                safe_mode=True,
            )
            session = SimulationSession(adapter, duration=0.02)
            session.start()

            self.assertAlmostEqual(adapter.camera.distance, 1.7)
            initial_lookat = list(adapter.camera.lookat)
            session.apply_action("zoom", 120.0)
            self.assertNotAlmostEqual(adapter.camera.distance, 1.7)
            session.apply_action("reset_camera")
            self.assertAlmostEqual(adapter.camera.distance, 1.7)
            np.testing.assert_allclose(adapter.camera.lookat, initial_lookat)
            session.close()


class ReplayArtifactTests(unittest.TestCase):
    def test_recorder_resumes_sampling_after_simulation_time_rewinds(self) -> None:
        recorder = ReplayRecorder(sample_hz=10.0)
        for timestamp in (0.0, 0.05, 0.1, 0.0, 0.05, 0.1):
            recorder.record(time=timestamp, qpos=[timestamp], qvel=[0.0], ctrl=[0.0])

        np.testing.assert_allclose(recorder.archive().time, [0.0, 0.1, 0.0, 0.1])

    def test_recording_round_trip_preserves_states_semantics_and_events(self) -> None:
        recorder = ReplayRecorder(sample_hz=60.0)
        for index in range(121):
            time = index / 120.0
            recorder.record(
                time=time,
                qpos=[time, -time],
                qvel=[1.0, -1.0],
                ctrl=[index],
                semantic={"target": 0.5},
            )
        recorder.event(time=0.25, kind="button", name="push", value=80.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = recorder.archive().save(Path(tmp) / "replay.npz")
            loaded = ReplayArchive.load(path)

        self.assertGreaterEqual(loaded.frame_count, 59)
        self.assertLessEqual(loaded.frame_count, 61)
        np.testing.assert_allclose(loaded.qpos[:, 0], loaded.time, atol=1e-6)
        self.assertEqual(loaded.events[0]["name"], "push")
        self.assertAlmostEqual(loaded.events[0]["time"] / loaded.duration, 0.25, places=2)
        self.assertTrue(np.allclose(loaded.semantic["target"], 0.5))

    def test_corrupt_replay_is_rejected_with_a_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.npz"
            path.write_bytes(b"not an npz")
            with self.assertRaisesRegex(ValueError, "Could not read replay"):
                ReplayArchive.load(path)

    def test_manifest_hashes_detect_mutated_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "log.csv").write_text("time\n0\n", encoding="utf-8")
            write_manifest(
                output,
                scenario_id="lab01.default",
                status="completed",
                config={"sim_time": 1.0},
            )
            self.assertEqual(verify_manifest(output), [])
            (output / "log.csv").write_text("changed", encoding="utf-8")
            self.assertIn("Artifact hash mismatch: log.csv", verify_manifest(output))

    def test_legacy_output_explains_why_recording_replay_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "log.csv").write_text("time\n", encoding="utf-8")
            self.assertIn("legacy run", legacy_replay_reason(output))


class SessionTests(unittest.TestCase):
    def test_prediction_and_observation_evidence_round_trip_and_restart_clear(self) -> None:
        adapter = FakeAdapter()
        session = SimulationSession(adapter, duration=0.2)
        session.start()
        session.record_evidence(
            "prediction",
            "prediction",
            "More damping will reduce oscillation.",
            label="Prediction",
        )
        observation = {
            "prediction": "More damping will reduce oscillation.",
            "outcome": "Matched",
            "note": "The peaks became smaller.",
            "status": {"position": 0.2},
        }
        session.record_evidence(
            "marker",
            "observation",
            observation,
            label="Mark observation",
        )

        self.assertEqual(
            [(event["kind"], event["name"]) for event in adapter.events],
            [("prediction", "prediction"), ("marker", "observation")],
        )
        self.assertEqual(adapter.events[-1]["value"], observation)
        self.assertEqual(
            [(event["kind"], event["name"]) for event in session.recorder.archive().events],
            [("prediction", "prediction"), ("marker", "observation")],
        )

        session.restart()
        self.assertEqual(adapter.events, [])
        self.assertEqual(session.recorder.archive().events, ())

        adapter_with_log = FakeAdapter()
        adapter_with_log.events = InteractionLog()  # type: ignore[assignment]
        log_session = SimulationSession(adapter_with_log, duration=0.2)
        log_session.start()
        log_session.record_evidence("marker", "observation", observation)
        self.assertEqual(len(adapter_with_log.events.events()), 1)
        log_session.restart()
        self.assertEqual(adapter_with_log.events.events(), [])

    def test_evidence_is_rejected_after_completion_and_in_replay(self) -> None:
        adapter = FakeAdapter()
        session = SimulationSession(adapter, duration=0.01)
        session.start()
        session.tick()
        with self.assertRaisesRegex(RuntimeError, "while completed"):
            session.record_evidence("marker", "observation", {})
        session.begin_replay(session.recorder.archive())
        with self.assertRaisesRegex(RuntimeError, "while replaying"):
            session.record_evidence("marker", "observation", {})

    def test_worker_command_pump_runs_actions_on_the_simulation_thread(self) -> None:
        adapter = FakeAdapter()
        session = SimulationSession(adapter, duration=0.02)
        command_threads: list[int] = []
        errors: list[Exception] = []
        commands = CommandQueue(errors.append)
        commands.submit(
            lambda: (
                command_threads.append(threading.get_ident()),
                session.apply_action("gain", 3.0),
            )
        )

        simulation_thread = threading.get_ident()
        session.run_blocking(realtime=False, command_pump=commands.drain)

        self.assertEqual(command_threads, [simulation_thread])
        self.assertEqual(adapter.actions, [("gain", 3.0)])
        self.assertEqual(errors, [])

    def test_visible_live_advance_runs_one_tenth_second_and_stays_paused(self) -> None:
        adapter = FakeAdapter()
        session = SimulationSession(adapter, duration=0.2)

        telemetry = session.advance_live()

        self.assertAlmostEqual(adapter.time, 0.1)
        self.assertEqual(adapter.position, 10.0)
        self.assertEqual(telemetry["position"], 10.0)
        self.assertEqual(session.state, SessionState.PAUSED)

    def test_view_controls_remain_available_after_completion_and_during_replay(self) -> None:
        adapter = FakeAdapter()
        session = SimulationSession(adapter, duration=0.01)
        session.start()
        session.tick()
        self.assertEqual(session.state, SessionState.COMPLETED)

        session.apply_action("reset_camera")
        with self.assertRaisesRegex(RuntimeError, "while completed"):
            session.apply_action("gain", 2.0)

        session.begin_replay(session.recorder.archive())
        session.apply_action("zoom", 1.0)
        self.assertEqual(
            adapter.actions,
            [("reset_camera", None), ("zoom", 1.0)],
        )

    def test_view_actions_publish_an_updated_frame_while_paused(self) -> None:
        adapter = FakeAdapter()
        frames: list[np.ndarray] = []
        session = SimulationSession(adapter, duration=0.1, on_frame=frames.append)
        session.start()
        session.pause()

        session.apply_action("orbit", [24.0, 12.0])
        session.apply_action("reset_camera")

        self.assertEqual(len(frames), 2)
        self.assertEqual(
            adapter.actions,
            [("orbit", [24.0, 12.0]), ("reset_camera", None)],
        )
        self.assertEqual(session.state, SessionState.PAUSED)
        self.assertEqual(adapter.time, 0.0)

    def test_session_transitions_pause_step_reset_replay_and_cleanup(self) -> None:
        adapter = FakeAdapter()
        states: list[SessionState] = []
        session = SimulationSession(adapter, duration=0.03, on_state=states.append)

        session.start()
        self.assertEqual(session.state, SessionState.RUNNING)
        session.apply_action("gain", 4.0)
        session.pause()
        session.step_once()
        self.assertEqual(session.state, SessionState.PAUSED)
        session.resume()
        while session.state == SessionState.RUNNING:
            session.tick()
        self.assertEqual(session.state, SessionState.COMPLETED)
        self.assertEqual(adapter.actions, [("gain", 4.0)])

        archive = session.recorder.archive()
        session.begin_replay(archive)
        session.pause()
        session.seek_replay(0)
        session.step_once()
        self.assertEqual(adapter.position, float(archive.qpos[1, 0]))

        session.set_replay_loop(0.0, 0.25, enabled=True)
        session.seek_replay(1)
        session.step_once()
        self.assertEqual(session.replay_index, 0)
        session.set_replay_loop(0.0, 1.0, enabled=False)

        session.restart_replay()
        self.assertEqual(session.state, SessionState.REPLAYING)
        self.assertEqual(session.replay_index, 0)

        session.reset()
        self.assertEqual(session.state, SessionState.READY)
        self.assertEqual(adapter.reset_count, 1)
        session.close()
        session.close()
        self.assertTrue(adapter.closed)
        self.assertIn(SessionState.REPLAYING, states)

    def test_replay_uses_recorded_frame_timing_and_seeking_pauses(self) -> None:
        adapter = FakeAdapter()
        archive = ReplayArchive(
            time=np.asarray([0.0, 0.1, 0.2]),
            qpos=np.asarray([[0.0], [1.0], [2.0]]),
            qvel=np.zeros((3, 1)),
            ctrl=np.zeros((3, 1)),
            semantic={"position": np.asarray([0.0, 1.0, 2.0])},
            events=({"time": 0.05, "kind": "button", "name": "push"},),
        )
        session = SimulationSession(adapter, duration=0.2)
        session.begin_replay(archive)

        marker = session.replay_event_markers[0]
        self.assertEqual(marker["name"], "push")
        self.assertAlmostEqual(marker["position"], 0.25)
        session.seek_replay(1)
        self.assertEqual(session.state, SessionState.PAUSED)
        self.assertEqual(session.replay_time, 0.1)

        session.restart_replay()
        with patch("mclab.application.session.time.sleep") as sleeper:
            self.assertEqual(session.run_blocking(realtime=True), SessionState.COMPLETED)
        paced_seconds = sum(float(call.args[0]) for call in sleeper.call_args_list)
        self.assertGreater(paced_seconds, 0.18)
        self.assertLessEqual(paced_seconds, 0.21)

    def test_replay_normalizes_nonzero_timestamps_and_clamps_boundary_frames(self) -> None:
        adapter = FakeAdapter()
        archive = ReplayArchive(
            time=np.asarray([5.0, 5.1, 5.2]),
            qpos=np.asarray([[0.0], [1.0], [2.0]]),
            qvel=np.zeros((3, 1)),
            ctrl=np.zeros((3, 1)),
            semantic={},
            events=(
                {"time": 4.0, "kind": "button", "name": "before"},
                {"time": 5.1, "kind": "button", "name": "middle"},
                {"time": 6.0, "kind": "button", "name": "after"},
            ),
        )
        session = SimulationSession(adapter, duration=0.2)
        session.begin_replay(archive)

        self.assertAlmostEqual(archive.duration, 0.2)
        for measured, expected in zip(session.replay_event_positions, (0.0, 0.5, 1.0)):
            self.assertAlmostEqual(measured, expected)
        marker_times = [item["time"] for item in session.replay_event_markers]
        self.assertAlmostEqual(marker_times[0], 0.0)
        self.assertAlmostEqual(marker_times[1], 0.1)
        self.assertAlmostEqual(marker_times[2], 0.2)
        session.seek_replay(-99)
        self.assertEqual((session.replay_index, session.replay_time), (0, 0.0))
        session.seek_replay(99)
        self.assertEqual(session.replay_index, 2)
        self.assertAlmostEqual(session.replay_time, 0.2)

    def test_replay_markers_hide_view_motion_and_group_continuous_gestures(self) -> None:
        adapter = FakeAdapter()
        events = tuple(
            [
                {"time": 0.10, "kind": "learner", "name": "orbit"},
                {"time": 0.20, "kind": "slider", "name": "damping"},
                {"time": 0.25, "kind": "slider", "name": "damping"},
                {"time": 0.39, "kind": "slider", "name": "damping"},
                {"time": 0.80, "kind": "button", "name": "push"},
            ]
        )
        archive = ReplayArchive(
            time=np.asarray([0.0, 0.5, 1.0]),
            qpos=np.zeros((3, 1)),
            qvel=np.zeros((3, 1)),
            ctrl=np.zeros((3, 1)),
            semantic={},
            events=events,
        )
        session = SimulationSession(adapter, duration=1.0)
        session.begin_replay(archive)

        markers = session.replay_event_markers
        self.assertEqual([(item["name"], item["count"]) for item in markers], [("damping", 3), ("push", 1)])
        self.assertAlmostEqual(markers[0]["time"], 0.39)
        self.assertEqual(session.replay_event_positions, (0.39, 0.8))

    def test_replay_speed_scales_recorded_timeline_pacing(self) -> None:
        archive = ReplayArchive(
            time=np.asarray([0.0, 0.1, 0.2]),
            qpos=np.asarray([[0.0], [1.0], [2.0]]),
            qvel=np.zeros((3, 1)),
            ctrl=np.zeros((3, 1)),
            semantic={},
        )
        measured: dict[float, float] = {}
        for speed in (0.5, 2.0):
            session = SimulationSession(FakeAdapter(), duration=0.2)
            session.begin_replay(archive)
            session.set_speed(speed)
            with (
                patch("mclab.application.session.time.perf_counter", return_value=0.0),
                patch("mclab.application.session.time.sleep") as sleeper,
            ):
                session.run_blocking(realtime=True)
            measured[speed] = sum(float(call.args[0]) for call in sleeper.call_args_list)

        self.assertAlmostEqual(measured[0.5], 0.4)
        self.assertAlmostEqual(measured[2.0], 0.1)

    def test_session_error_recovery_and_stop_status(self) -> None:
        adapter = FakeAdapter(fail_at=0.01)
        session = SimulationSession(adapter, duration=0.1)
        session.start()
        self.assertEqual(session.run_blocking(realtime=False), SessionState.ERROR)
        self.assertIsInstance(session.error, RuntimeError)
        session.reset()
        adapter.fail_at = None
        session.start()
        session.stop()
        self.assertEqual(session.run_blocking(realtime=False), SessionState.COMPLETED)
        self.assertTrue(session.interrupted)

    def test_replacing_a_qt_session_closes_the_previous_resources(self) -> None:
        class Owner:
            def __init__(self, session: SimulationSession) -> None:
                self.session = session
                self.adapter = session.adapter

        previous_adapter = FakeAdapter()
        previous = SimulationSession(previous_adapter, duration=1.0)
        replacement_adapter = FakeAdapter()
        replacement = SimulationSession(replacement_adapter, duration=1.0)
        owner = Owner(previous)

        replace_session(owner, replacement, replacement_adapter)

        self.assertIs(owner.session, replacement)
        self.assertIs(owner.adapter, replacement_adapter)
        self.assertTrue(previous_adapter.closed)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            previous.start()
        replacement.close()

        owned_adapter = FakeAdapter()
        owned = SimulationSession(owned_adapter, duration=1.0)
        deferred_adapter = FakeAdapter()
        deferred = SimulationSession(deferred_adapter, duration=1.0)
        owned_owner = Owner(owned)
        owned_owner.worker = type(
            "Worker",
            (),
            {"session": owned, "isRunning": lambda self: True},
        )()
        replace_session(owned_owner, deferred, deferred_adapter)
        self.assertFalse(owned_adapter.closed)
        self.assertIs(owned_owner.session, deferred)
        owned.close()
        deferred.close()

        class BrokenSession:
            def __init__(self) -> None:
                self.adapter = FakeAdapter()

            def close(self) -> None:
                raise RuntimeError("injected close failure")

        guarded_adapter = FakeAdapter()
        guarded_replacement = SimulationSession(guarded_adapter, duration=1.0)
        broken_owner = Owner(BrokenSession())  # type: ignore[arg-type]
        with self.assertRaisesRegex(RuntimeError, "injected close failure"):
            replace_session(broken_owner, guarded_replacement, guarded_adapter)
        self.assertTrue(guarded_adapter.closed)

        qt_backend = (ROOT / "src/mclab/application/qt_app.py").read_text(encoding="utf-8")
        self.assertEqual(qt_backend.count("reject_running_experiment(self)"), 3)
        self.assertEqual(qt_backend.count("reject_running_batch(self)"), 3)
        detail, action = localized_error(
            "ko",
            "An experiment is already running.",
            "Return to the active experiment, or end and save it before starting another.",
        )
        self.assertEqual(detail, "다른 실험이 이미 실행 중입니다.")
        self.assertEqual(
            action,
            "실행 중인 실험으로 돌아가거나 종료하고 저장한 뒤 다른 실험을 시작하세요.",
        )
        detail, action = localized_error(
            "ko",
            "Saved evidence cannot be deleted while an experiment is active.",
            "Return to the active experiment, or end and save it before starting another.",
        )
        self.assertEqual(detail, "실험이 열려 있는 동안 저장 결과를 삭제할 수 없습니다.")
        self.assertIn("종료하고 저장", action)
        qt_batch = (ROOT / "src/mclab/application/qt_batch.py").read_text(encoding="utf-8")
        self.assertIn("if reject_running_experiment(self):", qt_batch)
        self.assertNotIn("self.worker is not None and self.worker.isRunning()", qt_batch)

    def test_running_batch_guard_has_one_cause_and_recovery_action(self) -> None:
        class Batch:
            running = True

        class Owner:
            _batch = Batch()

            def __init__(self) -> None:
                self.error: tuple[str, str] | None = None

            def _set_error(self, detail: str, action: str) -> None:
                self.error = (detail, action)

        owner = Owner()
        self.assertTrue(reject_running_batch(owner))
        self.assertEqual(
            owner.error,
            (
                "The course comparison is already running.",
                "Use Cancel comparison or wait for the five sets to finish.",
            ),
        )
        owner._batch.running = False
        owner.error = None
        self.assertFalse(reject_running_batch(owner))
        self.assertIsNone(owner.error)

    def test_background_navigation_pauses_and_stop_preserves_worker_ownership(self) -> None:
        class Worker:
            busy = True

            def isRunning(self) -> bool:  # noqa: N802
                return True

        class Owner:
            def __init__(self, session: SimulationSession) -> None:
                self.session = session
                self.worker = Worker()
                self._page = "experiment"

            @staticmethod
            def _submit_session(command: object) -> None:
                command()  # type: ignore[operator]

        session = SimulationSession(FakeAdapter(), duration=1.0)
        session.start()
        owner = Owner(session)

        self.assertTrue(has_active_experiment(owner))
        pause_before_navigation(owner, "home")
        self.assertEqual(session.state, SessionState.PAUSED)

        stop_active_experiment(owner)
        self.assertEqual(session.state, SessionState.COMPLETED)
        self.assertTrue(has_active_experiment(owner))
        owner.worker.busy = False
        self.assertFalse(has_active_experiment(owner))

    def test_renderer_cleanup_finishes_gpu_work_before_close(self) -> None:
        class Context:
            current = False

            def make_current(self) -> None:
                self.current = True

        class Renderer:
            def __init__(self) -> None:
                self._gl_context = Context()
                self.closed = False

            def close(self) -> None:
                self.closed = True

        renderer = Renderer()
        with patch("OpenGL.GL.glFinish") as finish:
            close_mujoco_renderer(renderer)

        self.assertTrue(renderer._gl_context.current)
        finish.assert_called_once_with()
        self.assertTrue(renderer.closed)

    def test_egl_renderer_factory_reuses_one_worker_owned_context(self) -> None:
        import mclab.application.rendering as rendering
        from mujoco.rendering.classic import gl_context

        class Context:
            instances = 0

            def __init__(self, _width: int, _height: int) -> None:
                type(self).instances += 1
                self.current_count = 0
                self.freed = False

            def make_current(self) -> None:
                self.current_count += 1

            def free(self) -> None:
                self.freed = True

        class Renderer:
            def __init__(self) -> None:
                self.created_without_private_context = gl_context.GLContext is None
                self._gl_context = None

        class Mujoco:
            @staticmethod
            def Renderer(_model: object, *, height: int, width: int) -> Renderer:  # noqa: N802
                self.assertGreater(height, 0)
                self.assertGreater(width, 0)
                return Renderer()

        rendering._RENDER_CONTEXT.context = None  # noqa: SLF001
        with (
            patch.dict(os.environ, {"MUJOCO_GL": "egl"}),
            patch.object(gl_context, "GLContext", Context),
        ):
            first = rendering.create_mujoco_renderer(Mujoco(), object(), height=8, width=12)
            second = rendering.create_mujoco_renderer(Mujoco(), object(), height=8, width=12)
            owned = rendering._RENDER_CONTEXT.context  # noqa: SLF001

            self.assertEqual(Context.instances, 1)
            self.assertTrue(first.created_without_private_context)
            self.assertTrue(second.created_without_private_context)
            self.assertIs(first._gl_context._context, owned)  # noqa: SLF001
            self.assertIs(second._gl_context._context, owned)  # noqa: SLF001
            first._gl_context.free()  # noqa: SLF001
            self.assertFalse(owned.freed)
            rendering.destroy_thread_mujoco_context()
            self.assertTrue(owned.freed)
            self.assertIsNone(rendering._RENDER_CONTEXT.context)  # noqa: SLF001

    def test_same_scenario_restart_adopts_exact_native_render_resources(self) -> None:
        from mclab.application.rendering import (
            adopt_adapter_render_resources,
            can_reuse_adapter_render_resources,
            retain_adapter_render_resources,
        )

        class Scenario:
            def __init__(self, scenario_id: str) -> None:
                self.id = scenario_id

        class Adapter:
            def __init__(self, scenario_id: str, *, ready: bool) -> None:
                self.scenario = Scenario(scenario_id)
                self.config = {"model_path": "same.xml", "gain": 1.0}
                self.safe_mode = False
                self.mujoco = "old-mujoco" if ready else None
                self.model = "old-model" if ready else None
                self.data = "old-data" if ready else None
                self.renderer = object() if ready else None
                self.camera = "old-camera" if ready else None
                self.prepared = 0
                self.reset_count = 0

            def prepare(self) -> None:
                self.prepared += 1
                self.mujoco = "new-mujoco"
                self.model = "new-model"
                self.data = "new-data"
                self.camera = "new-camera"

            def reset(self) -> None:
                self.reset_count += 1

        donor = Adapter("lab01.interactive-pull", ready=True)
        recipient = Adapter("lab01.interactive-pull", ready=False)
        other = Adapter("lab02.interactive-disturbance", ready=False)
        retained_renderer = donor.renderer
        with patch.dict(os.environ, {"MUJOCO_GL": "egl"}):
            self.assertTrue(can_reuse_adapter_render_resources(donor, recipient))
            self.assertFalse(can_reuse_adapter_render_resources(donor, other))
            resources = retain_adapter_render_resources(donor)
            self.assertIsNotNone(resources)
            self.assertIsNone(donor.renderer)
            self.assertTrue(adopt_adapter_render_resources(resources, recipient))  # type: ignore[arg-type]

        self.assertEqual(recipient.prepared, 1)
        self.assertEqual(recipient.reset_count, 1)
        self.assertEqual(
            (recipient.mujoco, recipient.model, recipient.data, recipient.camera),
            ("old-mujoco", "old-model", "old-data", "old-camera"),
        )
        self.assertIs(recipient.renderer, retained_renderer)

    def test_live_restart_resets_time_and_keeps_the_worker_state_running(self) -> None:
        adapter = FakeAdapter()
        session = SimulationSession(adapter, duration=0.1)
        session.start()
        session.tick()

        session.restart()

        self.assertEqual(session.state, SessionState.RUNNING)
        self.assertEqual(adapter.time, 0.0)
        self.assertEqual(adapter.reset_count, 1)
        self.assertEqual(session.recorder.archive().frame_count, 1)

    def test_prediction_wait_renders_at_zero_and_paused_restart_returns_to_zero(self) -> None:
        frames: list[np.ndarray] = []
        adapter = FakeAdapter()
        session = SimulationSession(
            adapter,
            duration=0.1,
            on_frame=frames.append,
        )
        session.start()
        session.pause()
        session.render_current()

        self.assertEqual(session.state, SessionState.PAUSED)
        self.assertEqual(adapter.time, 0.0)
        self.assertEqual(len(frames), 1)

        session.resume()
        session.tick()
        self.assertGreater(adapter.time, 0.0)
        session.restart(paused=True)

        self.assertEqual(session.state, SessionState.PAUSED)
        self.assertEqual(adapter.time, 0.0)
        self.assertEqual(session.recorder.archive().frame_count, 1)

    def test_run_manager_rejects_duplicate_launch_and_closes_sessions(self) -> None:
        manager = RunManager()
        adapter = FakeAdapter()
        session = manager.create("lab01.default", lambda: SimulationSession(adapter, duration=0.1))
        self.assertIs(manager.get("lab01.default"), session)
        with self.assertRaisesRegex(RuntimeError, "already running"):
            manager.create("lab01.default", lambda: SimulationSession(FakeAdapter(), duration=0.1))
        manager.release("lab01.default")
        self.assertTrue(adapter.closed)


class PlatformAndCliTests(unittest.TestCase):
    def test_qt_self_test_ignores_only_known_font_database_warning(self) -> None:
        from mclab.application.error_messages import self_test_qt_errors

        self.assertEqual(
            self_test_qt_errors(
                [
                    "QFontDatabase: Cannot find font directory /tmp/PySide6/lib/fonts.\n"
                    "Qt no longer ships fonts.",
                    "file:///Main.qml:42: ReferenceError: missingValue is not defined",
                ]
            ),
            ["file:///Main.qml:42: ReferenceError: missingValue is not defined"],
        )

    def test_public_app_replay_assets_and_json_doctor_arguments(self) -> None:
        parser = build_parser()
        app = parser.parse_args(
            ["app", "--lang", "ko", "--scenario", "lab01.default", "--safe-mode"]
        )
        replay = parser.parse_args(["replay", "outputs/run", "--lang", "en"])
        assets = parser.parse_args(["assets", "install", "--force"])
        doctor = parser.parse_args(["doctor", "--json"])

        self.assertEqual(app.scenario, "lab01.default")
        self.assertTrue(app.safe_mode)
        self.assertEqual(replay.run_dir, "outputs/run")
        self.assertTrue(assets.force)
        self.assertTrue(doctor.json)

    def test_doctor_json_is_machine_readable(self) -> None:
        payload = json.loads(doctor_report_json([DoctorCheck("Qt", "WARN", "missing", "install")]))
        self.assertEqual(payload["summary"], {"ok": 0, "warn": 1, "fail": 0})
        self.assertEqual(payload["checks"][0]["fix"], "install")

    def test_menu_alias_and_replay_delegate_to_qt_app(self) -> None:
        with patch("mclab.application.qt_app.run_app", return_value=0) as runner:
            self.assertEqual(main(["menu"]), 0)
            runner.assert_called_once_with(language=None, scenario_id=None, safe_mode=False)

        with patch("mclab.application.qt_app.run_app", return_value=0) as runner:
            self.assertEqual(main(["replay", "outputs/demo", "--safe-mode"]), 0)
            runner.assert_called_once_with(
                language=None,
                safe_mode=True,
                replay_dir=Path("outputs/demo"),
            )

    def test_macos_viewer_command_uses_mjpython(self) -> None:
        with patch("mclab.application.platform.sys.platform", "darwin"):
            command = PlatformServices().viewer_command(["run", "lab01"])
        self.assertTrue(command[0].endswith("mjpython"))

    def test_direct_macos_viewer_cli_relaunches_with_mjpython(self) -> None:
        args = build_parser().parse_args(
            ["run", "lab01", "--config", "configs/lab01_msd/default.yaml", "--viewer"]
        )
        with (
            patch("mclab.cli.sys.platform", "darwin"),
            patch("mclab.cli.sys.executable", "/usr/bin/python3"),
            patch("mclab.cli.subprocess.call", return_value=0) as call,
        ):
            self.assertEqual(
                _maybe_relaunch_macos_viewer(
                    args,
                    ["run", "lab01", "--config", "configs/lab01_msd/default.yaml", "--viewer"],
                ),
                0,
            )
        self.assertTrue(call.call_args.args[0][0].endswith("mjpython"))
        self.assertEqual(call.call_args.kwargs["env"]["MCLAB_MJPYTHON_RELAUNCH"], "1")

    def test_frozen_output_root_uses_user_data_override(self) -> None:
        from mclab import config

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(config.sys, "frozen", True, create=True),
            patch.dict(config.os.environ, {"MCLAB_DATA_DIR": tmp}),
        ):
            self.assertEqual(config.default_outputs_root(), Path(tmp).resolve() / "outputs")

    def test_asset_installer_extracts_only_panda_and_preserves_license(self) -> None:
        from mclab.application import assets as asset_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "assets.tar.gz"
            prefix = asset_module.PANDA_PREFIX
            with tarfile.open(archive, "w:gz") as bundle:
                for name, content in (
                    (prefix + "scene.xml", b"<mujoco/>"),
                    (prefix + "LICENSE", b"BSD-3-Clause"),
                    ("unrelated/large.bin", b"do not extract"),
                ):
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    bundle.addfile(info, io.BytesIO(content))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.object(asset_module, "MENAGERIE_ARCHIVE_SHA256", digest):
                target = asset_module.install_assets(root, archive_path=archive)

            self.assertTrue((target / "scene.xml").is_file())
            self.assertEqual((target / "LICENSE").read_text(), "BSD-3-Clause")
            self.assertFalse((target.parent / "unrelated").exists())

    @unittest.skipIf(
        importlib.util.find_spec("PySide6") is None, "PySide6 app extra is not installed"
    )
    def test_qt_offscreen_self_test_loads_qml(self) -> None:
        from PySide6.QtCore import QLockFile

        output = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            occupied_path = str(Path(tmp) / "occupied.lock")
            occupied = QLockFile(occupied_path)
            occupied.setStaleLockTime(0)
            self.assertTrue(occupied.tryLock(0))
            with patch.dict(os.environ, {"MCLAB_INSTANCE_LOCK": occupied_path}):
                with redirect_stdout(output):
                    self.assertEqual(main(["app", "--self-test", "--lang", "en"]), 0)
                self.assertEqual(os.environ["MCLAB_INSTANCE_LOCK"], occupied_path)
            occupied.unlock()
        self.assertIn('"qt": true', output.getvalue())


@unittest.skipIf(importlib.util.find_spec("mujoco") is None, "MuJoCo is not installed")
class IntegratedManipulatorAdapterTests(unittest.TestCase):
    def test_lab03_and_lab04_step_reset_controls_and_safe_render(self) -> None:
        from mclab.application.lab03_adapter import Lab03Adapter
        from mclab.application.lab04_adapter import Lab04Adapter

        catalog = ScenarioCatalog.default()
        cases = (
            (
                Lab03Adapter,
                "lab03.interactive-2dof",
                ("task_kp", 70.0),
                "shoulder_pulse",
            ),
            (
                Lab04Adapter,
                "lab04.interactive-virtual-wall",
                ("wall_stiffness", 300.0),
                "target_x_increase",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for adapter_type, scenario_id, control, action in cases:
                with self.subTest(scenario=scenario_id):
                    adapter = adapter_type(
                        catalog.get(scenario_id),
                        output_dir=Path(tmp) / scenario_id,
                        safe_mode=True,
                    )
                    adapter.prepare()
                    adapter.apply_action(*control)
                    adapter.apply_action(action)
                    telemetry = adapter.step()
                    self.assertGreater(float(telemetry["time"]), 0.0)
                    if scenario_id.startswith("lab04"):
                        self.assertTrue(
                            {"target_y", "target_z", "wall_x", "wall_force_x"}
                            <= telemetry.keys()
                        )
                    self.assertEqual(adapter.render(96, 54).shape, (54, 96, 3))
                    adapter.reset()
                    self.assertEqual(adapter.time, 0.0)
                    adapter.close()


if __name__ == "__main__":
    unittest.main()
