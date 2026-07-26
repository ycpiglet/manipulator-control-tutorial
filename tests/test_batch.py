from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab import batch  # noqa: E402
from mclab.application.artifacts import (  # noqa: E402
    verify_manifest,
    verify_terminal_batch_output,
    write_manifest,
)
from mclab.application.catalog import stable_scenario_id  # noqa: E402
from mclab.application.batch_runs import (  # noqa: E402
    ALL_COMPARE_BATCH_NAMES,
    BATCH_ACTIVE_DIR_NAME,
    BATCH_PROGRESS_FILE_NAME,
    BatchProgressBusy,
    all_compare_command,
    claim_all_compare_handoff,
    clear_all_compare_progress,
    create_all_compare_output,
    read_all_compare_handoff,
    read_batch_progress,
    release_all_compare_handoff,
    settle_all_compare_output,
    update_batch_manifest,
    write_batch_progress,
)
from mclab.application.batch_settlement import (  # noqa: E402
    RECOVERABLE_BATCH_SCENARIOS,
)
from mclab.config import load_config  # noqa: E402
from mclab.output_cleanup import build_cleanup_plan  # noqa: E402
from mclab.output_root import PinnedOutputRoot  # noqa: E402
from mclab.output_safety import CleanupBusyError  # noqa: E402
from mclab.sim.logging import RunLogger  # noqa: E402


class BatchTests(unittest.TestCase):
    def test_batch_sets_reference_valid_configs(self) -> None:
        self.assertNotIn(batch.ALL_BATCH_NAME, batch.list_batch_sets())
        self.assertIn(batch.ALL_BATCH_NAME, batch.list_batch_sets(include_all=True))
        self.assertIn("lab01_msd_compare", batch.list_batch_sets())
        self.assertIn("lab02_pid_compare", batch.list_batch_sets())
        self.assertIn("lab03_2dof_compare", batch.list_batch_sets())
        self.assertIn("lab04_wall_compare", batch.list_batch_sets())
        self.assertIn("lab04_cartesian_compare", batch.list_batch_sets())
        lab03_labels = {scenario.label for scenario in batch.BATCH_SETS["lab03_2dof_compare"]}
        self.assertIn("condition_aware_dls", lab03_labels)
        self.assertIn("condition_aware_early", lab03_labels)
        self.assertIn("condition_aware_late", lab03_labels)
        self.assertIn("condition_aware_inner_target", lab03_labels)
        self.assertIn("condition_aware_edge_target", lab03_labels)
        self.assertIn("condition_aware_upper_path", lab03_labels)
        self.assertIn("condition_aware_lower_path", lab03_labels)
        self.assertIn("condition_aware_shoulder_disturbance", lab03_labels)
        self.assertIn("condition_aware_elbow_disturbance", lab03_labels)
        self.assertIn("condition_aware_staggered_disturbance", lab03_labels)
        self.assertIn("condition_aware_low_torque", lab03_labels)
        self.assertIn("condition_aware_high_torque", lab03_labels)
        self.assertIn("condition_aware_slow_command", lab03_labels)
        self.assertIn("condition_aware_fast_command", lab03_labels)
        self.assertIn("condition_aware_low_joint_speed", lab03_labels)
        self.assertIn("condition_aware_high_joint_speed", lab03_labels)
        self.assertIn("condition_aware_direct_retarget", lab03_labels)
        self.assertIn("condition_aware_inward_retarget", lab03_labels)
        self.assertIn("condition_aware_fixed_speed_retarget", lab03_labels)
        self.assertIn("condition_aware_adaptive_speed_retarget", lab03_labels)
        lab04_wall_labels = {scenario.label for scenario in batch.BATCH_SETS["lab04_wall_compare"]}
        self.assertIn("low_damping_wall", lab04_wall_labels)
        self.assertIn("high_damping_wall", lab04_wall_labels)
        self.assertIn("near_wall", lab04_wall_labels)
        self.assertIn("far_wall", lab04_wall_labels)
        self.assertIn("low_retreat_wall", lab04_wall_labels)
        self.assertIn("high_retreat_wall", lab04_wall_labels)
        self.assertIn("slow_approach_wall", lab04_wall_labels)
        self.assertIn("fast_approach_wall", lab04_wall_labels)
        self.assertIn("shallow_push_wall", lab04_wall_labels)
        self.assertIn("deep_push_wall", lab04_wall_labels)
        self.assertIn("contact_cycle_wall", lab04_wall_labels)
        lab04_guide = batch.BATCH_GUIDES["lab04_wall_compare"]
        self.assertTrue(
            any("force-to-retreat gain" in question for question in lab04_guide.questions)
        )
        self.assertTrue(any("approach speed" in question for question in lab04_guide.questions))
        self.assertTrue(any("target push depth" in question for question in lab04_guide.questions))
        self.assertTrue(
            any("repeated target crossings" in question for question in lab04_guide.questions)
        )
        self.assertIn("max_hand_x_speed", lab04_guide.metric_keys)
        self.assertIn("max_target_wall_gap_cm", lab04_guide.metric_keys)
        self.assertIn("first_target_wall_cross_time", lab04_guide.metric_keys)
        self.assertIn("first_wall_release_time", lab04_guide.metric_keys)
        self.assertIn("first_target_wall_return_time", lab04_guide.metric_keys)
        self.assertIn("peak_wall_force_time", lab04_guide.metric_keys)
        self.assertIn("peak_wall_damping_force_time", lab04_guide.metric_keys)
        self.assertIn("target_wall_cross_episodes", lab04_guide.metric_keys)
        self.assertIn("wall_contact_episodes", lab04_guide.metric_keys)
        self.assertIn(
            (
                "hand_x_speed_compare.png",
                "Panda Hand X Speed Comparison",
                "x speed [m/s]",
                "xdot_ee_0",
            ),
            lab04_guide.comparison_specs,
        )
        self.assertEqual(
            RECOVERABLE_BATCH_SCENARIOS,
            {
                name: frozenset(scenario.label for scenario in scenarios)
                for name, scenarios in batch.BATCH_SETS.items()
            },
        )
        self.assertIn(
            (
                "target_wall_gap_compare.png",
                "Target-Wall Gap Comparison",
                "gap [cm]",
                "target_wall_gap_cm",
            ),
            lab04_guide.comparison_specs,
        )
        self.assertIn(
            (
                "wall_key_moment_timing_compare.png",
                "Wall Key Moment Timing Comparison",
                "time [s]",
                (
                    "first_target_wall_cross_time",
                    "first_wall_contact_time",
                    "first_wall_release_time",
                    "first_target_wall_return_time",
                    "peak_wall_penetration_time",
                    "peak_wall_force_time",
                    "peak_wall_damping_force_time",
                    "peak_hand_speed_time",
                ),
            ),
            lab04_guide.summary_comparison_specs,
        )
        self.assertIn(
            "max_dls_condition_scale", batch.BATCH_GUIDES["lab03_2dof_compare"].metric_keys
        )
        self.assertIn("max_dls_task_speed", batch.BATCH_GUIDES["lab03_2dof_compare"].metric_keys)
        self.assertIn(
            "min_dls_task_speed_limit", batch.BATCH_GUIDES["lab03_2dof_compare"].metric_keys
        )
        self.assertIn(
            "max_dls_task_speed_limit", batch.BATCH_GUIDES["lab03_2dof_compare"].metric_keys
        )
        lab03_guide = batch.BATCH_GUIDES["lab03_2dof_compare"]
        self.assertTrue(
            any(
                "lower torque limit increase task error" in question
                for question in lab03_guide.questions
            )
        )
        self.assertTrue(
            any("faster hand command" in question for question in lab03_guide.questions)
        )
        self.assertTrue(any("joint-speed limit" in question for question in lab03_guide.questions))
        self.assertTrue(
            any(
                "retargeting through an inner waypoint" in question
                for question in lab03_guide.questions
            )
        )
        self.assertTrue(
            any("slowing the task-speed limit" in question for question in lab03_guide.questions)
        )
        self.assertTrue(
            any("inner workspace to the edge" in question for question in lab03_guide.questions)
        )
        self.assertTrue(
            any("elbow-up and elbow-down paths" in question for question in lab03_guide.questions)
        )
        self.assertTrue(
            any(
                "shoulder, elbow, or staggered disturbances" in question
                for question in lab03_guide.questions
            )
        )
        self.assertIn("max_abs_tau_disturbance", lab03_guide.metric_keys)
        self.assertIn("max_task_error_during_disturbance", lab03_guide.metric_keys)
        self.assertIn("disturbance_recovery_duration", lab03_guide.metric_keys)
        self.assertIn(
            (
                "dls_task_speed_compare.png",
                "DLS Task Speed Comparison",
                "task speed",
                "dls_task_speed",
            ),
            lab03_guide.comparison_specs,
        )
        self.assertIn(
            (
                "dls_task_speed_limit_compare.png",
                "DLS Task Speed Limit Comparison",
                "task speed limit",
                "dls_task_speed_limit",
            ),
            lab03_guide.comparison_specs,
        )
        self.assertIn(
            ("hand_y_compare.png", "End-Effector Y Comparison", "y [m]", "x_ee_1"),
            lab03_guide.comparison_specs,
        )
        self.assertIn(
            (
                "shoulder_torque_compare.png",
                "Shoulder Torque Comparison",
                "torque [N m]",
                "tau_cmd_0",
            ),
            lab03_guide.comparison_specs,
        )
        self.assertIn(
            ("elbow_torque_compare.png", "Elbow Torque Comparison", "torque [N m]", "tau_cmd_1"),
            lab03_guide.comparison_specs,
        )
        self.assertIn(
            (
                "elbow_disturbance_compare.png",
                "Elbow Disturbance Comparison",
                "torque [N m]",
                "tau_disturbance_1",
            ),
            lab03_guide.comparison_specs,
        )
        self.assertIn(
            (
                "disturbance_recovery_time_compare.png",
                "Disturbance Recovery Time Comparison",
                "time [s]",
                ("disturbance_recovery_duration",),
            ),
            lab03_guide.summary_comparison_specs,
        )

        for batch_name, scenarios in batch.BATCH_SETS.items():
            with self.subTest(batch=batch_name):
                self.assertGreaterEqual(len(scenarios), 2)
                self.assertIn(batch_name, batch.BATCH_GUIDES)
                self.assertTrue(batch.BATCH_GUIDES[batch_name].comparison_specs)
            for scenario in scenarios:
                with self.subTest(batch=batch_name, scenario=scenario.label):
                    self.assertIn(scenario.lab_name, batch.LAB_RUNNERS)
                    config = load_config(scenario.config_path)
                    self.assertIn("model_path", config)
                    self.assertTrue(scenario.plots)

    def test_lab03_joint_speed_configs_isolate_joint_speed_limit(self) -> None:
        low = load_config("configs/lab03_2dof/condition_aware_dls_low_joint_speed_2dof.yaml")
        high = load_config("configs/lab03_2dof/condition_aware_dls_high_joint_speed_2dof.yaml")

        low_controller = dict(low["tracking_controller"])
        high_controller = dict(high["tracking_controller"])
        low_speed = low_controller.pop("max_joint_speed")
        high_speed = high_controller.pop("max_joint_speed")

        self.assertLess(low_speed, 0.5)
        self.assertGreater(high_speed, low_speed)
        self.assertEqual(low_controller, high_controller)
        for key in ("mode", "sim_time", "dt", "initial_q", "target_xy", "trajectory"):
            self.assertEqual(low[key], high[key])

    def test_lab03_adaptive_speed_schedule_configs_isolate_speed_schedule(self) -> None:
        fixed = load_config("configs/lab03_2dof/condition_aware_dls_fixed_speed_retarget_2dof.yaml")
        adaptive = load_config(
            "configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml"
        )

        fixed_controller = dict(fixed["tracking_controller"])
        adaptive_controller = dict(adaptive["tracking_controller"])
        schedule = adaptive_controller.pop("max_task_speed_schedule")

        self.assertNotIn("max_task_speed_schedule", fixed_controller)
        self.assertEqual(fixed_controller, adaptive_controller)
        self.assertEqual(fixed["target_xy_waypoints"], adaptive["target_xy_waypoints"])
        self.assertLess(
            min(point["speed"] for point in schedule), adaptive_controller["max_task_speed"]
        )
        for key in ("mode", "sim_time", "dt", "initial_q", "target_xy", "trajectory"):
            self.assertEqual(fixed[key], adaptive[key])

    def test_lab04_push_depth_configs_isolate_target_waypoint_depth(self) -> None:
        shallow = load_config("configs/lab04_panda/wall_shallow_push.yaml")
        deep = load_config("configs/lab04_panda/wall_deep_push.yaml")

        shallow_waypoints = shallow["cartesian_target"].pop("waypoints")
        deep_waypoints = deep["cartesian_target"].pop("waypoints")

        self.assertEqual(shallow["cartesian_target"], deep["cartesian_target"])
        for key in ("mode", "sim_time", "dt", "home_q", "trajectory", "virtual_wall"):
            self.assertEqual(shallow[key], deep[key])
        self.assertEqual(
            [point["time"] for point in shallow_waypoints],
            [point["time"] for point in deep_waypoints],
        )
        self.assertLess(shallow_waypoints[2]["position"][0], deep_waypoints[2]["position"][0])
        self.assertLess(shallow_waypoints[-1]["position"][0], deep_waypoints[-1]["position"][0])

    def test_run_batch_creates_child_runs_and_index(self) -> None:
        calls: list[dict[str, object]] = []
        batch_name = "lab01_msd_compare"
        scenario = batch.BatchScenario(
            label="demo scenario",
            lab_name="lab01",
            config_path="configs/lab01_msd/default.yaml",
            plots="essential",
        )

        def fake_runner(config: dict[str, object], **kwargs: object) -> Path:
            output = Path(kwargs["output_dir"])
            output.mkdir(parents=True, exist_ok=True)
            config_path = Path(kwargs["config_path"])
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": config_path.as_posix(),
                        "config_name": config_path.stem,
                        "duration": 1.0,
                        "samples": 3,
                        "max_abs_position": 0.5,
                    }
                ),
                encoding="utf-8",
            )
            (output / "report.html").write_text("<html></html>", encoding="utf-8")
            (output / "worksheet.md").write_text("# Scenario Worksheet\n", encoding="utf-8")
            (output / "plots").mkdir()
            (output / "plots" / "position.png").write_bytes(b"fake-png")
            write_manifest(
                output,
                scenario_id="lab01.default",
                status="completed",
                config=config,
                config_path=config_path,
            )
            calls.append({"config": config, **kwargs})
            return output

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(batch.BATCH_SETS, {batch_name: (scenario,)}, clear=False),
                patch.dict(batch.LAB_RUNNERS, {"lab01": fake_runner}, clear=False),
            ):
                output = batch.run_batch(
                    batch_name,
                    output_dir=Path(tmp).resolve() / "batch_output",
                    plot=False,
                    seed=11,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["plot"], False)
            self.assertEqual(calls[0]["viewer"], False)
            self.assertEqual(calls[0]["headless"], True)
            self.assertEqual(calls[0]["plot_selection"], "essential")
            self.assertEqual(calls[0]["seed"], 11)
            self.assertFalse(calls[0]["publish_parent_index"])
            self.assertTrue((output / "demo_scenario" / "summary.json").exists())
            self.assertTrue((output / "batch_summary.json").exists())
            self.assertTrue((output / "summary.json").exists())
            self.assertTrue((output / "report.html").exists())
            self.assertTrue((output / "worksheet.md").exists())
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scenario_id"], f"batch.{batch_name}")
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["run_kind"], "comparison_batch")
            self.assertEqual(verify_manifest(output), [])
            self.assertEqual(
                set(manifest["artifacts"]),
                {
                    path.relative_to(output).as_posix()
                    for path in output.rglob("*")
                    if path.is_file() and path != output / "manifest.json"
                },
            )
            cleanup_plan = build_cleanup_plan(
                output.parent,
                keep=0,
                allowed_root=output.parent,
            )
            self.assertEqual([entry.name for entry in cleanup_plan.selected], [output.name])
            self.assertIn(
                "demo_scenario/report.html", (output / "index.html").read_text(encoding="utf-8")
            )
            before = (output / "summary.json").read_bytes()
            with (
                patch.dict(batch.BATCH_SETS, {"unit_compare": (scenario,)}, clear=False),
                patch.dict(batch.LAB_RUNNERS, {"lab01": fake_runner}, clear=False),
                self.assertRaisesRegex(RuntimeError, "existing batch output directory"),
            ):
                batch.run_batch("unit_compare", output_dir=output, plot=False, seed=11)
            self.assertEqual((output / "summary.json").read_bytes(), before)
            self.assertTrue((output / "demo_scenario" / "worksheet.md").exists())
            report_html = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn("Learning Focus", report_html)
            self.assertIn(
                'class="table-wrap" tabindex="0" aria-label="Scrollable data table"',
                report_html,
            )
            self.assertIn(".table-wrap:focus-visible", report_html)
            self.assertIn("Open the batch worksheet", report_html)
            self.assertIn("digest-published and read-only", report_html)
            self.assertIn(
                "personal or course notes outside the saved-run folder",
                report_html,
            )
            self.assertIn("as a read-only reference", report_html)
            self.assertIn("Next Experiments", report_html)
            self.assertIn("Reproduce Commands", report_html)
            self.assertIn(
                f"python -m mclab batch {batch_name} --open-report",
                report_html,
            )
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot --plots essential",
                report_html,
            )
            self.assertIn("Viewer rerun command", report_html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
                "--viewer --realtime --pause-at-end --plot --plots essential",
                report_html,
            )
            self.assertIn("Headless rerun", report_html)
            self.assertIn("Viewer rerun", report_html)
            self.assertIn("Viewer Handoff", report_html)
            self.assertIn('id="viewer-handoff"', report_html)
            self.assertIn("Start with demo scenario", report_html)
            self.assertIn(
                "only saved scenario; inspect the motion before editing YAML", report_html
            )
            self.assertIn(
                "Open the scenario report, priority plot, worksheet, or folder first", report_html
            )
            self.assertIn("demo scenario", report_html)
            self.assertIn("Start steps", report_html)
            self.assertIn(
                "Predict -&gt; Run scenario -&gt; Review priority plot and worksheet.", report_html
            )
            self.assertIn("Challenge", report_html)
            self.assertIn("verify it in the saved plot and worksheet", report_html)
            self.assertIn("Predict", report_html)
            self.assertNotIn("predict how How", report_html)
            self.assertIn("Question", report_html)
            self.assertIn("Watch", report_html)
            self.assertIn("Control surface", report_html)
            self.assertIn("Auto run; edit YAML before rerunning.", report_html)
            self.assertIn("What baseline motion", report_html)
            self.assertIn("Open report", report_html)
            self.assertIn("Open position.png", report_html)
            self.assertIn("Open worksheet", report_html)
            self.assertIn("Open folder", report_html)
            self.assertIn("Plot review", report_html)
            self.assertIn("Position: Compare actual motion against target", report_html)
            self.assertIn('href="demo_scenario/plots/position.png"', report_html)
            self.assertIn('href="demo_scenario/worksheet.md"', report_html)
            self.assertIn('href="demo_scenario/"', report_html)
            self.assertIn("Changed from baseline", report_html)
            self.assertIn("Baseline reference", report_html)
            self.assertIn("Metric change from baseline", report_html)
            self.assertIn("Baseline metric reference", report_html)
            self.assertIn("max abs position", report_html)
            self.assertIn("Parameter Differences", report_html)
            self.assertIn("Plot Previews", report_html)
            self.assertIn("demo_scenario/plots/position.png", report_html)
            worksheet = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("# MCLab Batch Worksheet", worksheet)
            self.assertIn("## Saved Artifact Policy", worksheet)
            self.assertIn("digest-published and read-only", worksheet)
            self.assertIn(
                "personal or course notes outside the saved-run folder",
                worksheet,
            )
            self.assertIn("## Scenario Review", worksheet)
            self.assertIn("demo scenario", worksheet)
            self.assertIn("Folder: demo_scenario/", worksheet)
            self.assertIn("Worksheet: demo_scenario/worksheet.md", worksheet)
            self.assertIn(
                "Start steps: Predict -> Run scenario -> Review priority plot and worksheet.",
                worksheet,
            )
            self.assertIn("Challenge: Explain how mass, damping, stiffness", worksheet)
            self.assertIn("Priority plot: demo_scenario/plots/position.png", worksheet)
            self.assertIn("Plot review: Position - Compare actual motion against target", worksheet)
            self.assertIn(
                f"Batch command: python -m mclab batch {batch_name} --open-report",
                worksheet,
            )
            self.assertIn(
                "Scenario command: python -m mclab run lab01 --config configs/lab01_msd/default.yaml",
                worksheet,
            )
            self.assertIn(
                "Viewer rerun: python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
                "--viewer --realtime --pause-at-end --plot --plots essential",
                worksheet,
            )
            self.assertIn("## Viewer Handoff", worksheet)
            self.assertIn("Start with: demo scenario", worksheet)
            self.assertIn(
                "Why: only saved scenario; inspect the motion before editing YAML", worksheet
            )
            self.assertIn("Report: demo_scenario/report.html", worksheet)
            self.assertIn("Priority plot: demo_scenario/plots/position.png", worksheet)
            self.assertIn("Worksheet: demo_scenario/worksheet.md", worksheet)
            self.assertIn("Folder: demo_scenario/", worksheet)
            self.assertIn(
                "- Review prompt: Record which scenario best supports your prediction.",
                worksheet,
            )
            self.assertNotIn("- [ ]", worksheet)
            parent_index = output.parent / "index.html"
            self.assertIn("batch_output/report.html", parent_index.read_text(encoding="utf-8"))
            self.assertIn("batch_output/worksheet.md", parent_index.read_text(encoding="utf-8"))

    def test_run_batch_failure_publishes_strict_error_manifest_after_report_repair(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "partial-batch"
            original_report = batch.write_batch_report
            report_attempts = 0

            def fail_once(*args: object, **kwargs: object) -> Path:
                nonlocal report_attempts
                report_attempts += 1
                if report_attempts == 1:
                    raise RuntimeError("injected")
                return original_report(*args, **kwargs)

            with (
                patch.dict(batch.BATCH_SETS, {"lab01_msd_compare": ()}, clear=False),
                patch("mclab.batch.write_outputs_index"),
                patch(
                    "mclab.batch.write_batch_report",
                    side_effect=fail_once,
                ),
                self.assertRaisesRegex(RuntimeError, "injected"),
            ):
                batch.run_batch("lab01_msd_compare", output_dir=output, plot=False)

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "error")
            self.assertEqual(manifest["error"], "injected")
            self.assertEqual(verify_manifest(output), [])
            self.assertIn(
                "completion.v1.run_not_completed",
                (output / "report.html").read_text(encoding="utf-8"),
            )
            cleanup_plan = build_cleanup_plan(
                output.parent,
                keep=0,
                allowed_root=output.parent,
            )
            self.assertEqual([entry.name for entry in cleanup_plan.selected], [output.name])

    def test_run_batch_report_repair_failure_stays_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "partial-batch"
            with (
                patch.dict(batch.BATCH_SETS, {"unit_compare": ()}, clear=False),
                patch("mclab.batch.write_outputs_index"),
                patch(
                    "mclab.batch.write_batch_report",
                    side_effect=RuntimeError("injected"),
                ),
                self.assertRaisesRegex(RuntimeError, "injected"),
            ):
                batch.run_batch("unit_compare", output_dir=output, plot=False)

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "running")
            self.assertNotIn("error", manifest)
            self.assertEqual(verify_manifest(output), [])
            cleanup_plan = build_cleanup_plan(
                output.parent,
                keep=0,
                allowed_root=output.parent,
            )
            self.assertEqual(cleanup_plan.selected, ())

    def test_run_batch_stops_if_initial_running_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "partial-batch"
            with (
                patch.dict(batch.BATCH_SETS, {"unit_compare": ()}, clear=False),
                patch("mclab.batch.write_outputs_index"),
                patch(
                    "mclab.batch.write_batch_report",
                    side_effect=RuntimeError("original batch failure"),
                ),
                patch(
                    "mclab.application.artifacts.write_manifest",
                    side_effect=OSError("manifest failure"),
                ),
                self.assertRaisesRegex(OSError, "manifest failure"),
            ):
                batch.run_batch("unit_compare", output_dir=output, plot=False)

            self.assertTrue(output.exists())
            self.assertFalse((output / "manifest.json").exists())

    def test_run_all_batches_creates_group_report(self) -> None:
        def fake_run_batch(batch_name: str, **kwargs: object) -> Path:
            output = Path(kwargs["output_dir"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch",
                        "config_name": batch_name,
                        "samples": len(batch.BATCH_SETS[batch_name]),
                    }
                ),
                encoding="utf-8",
            )
            (output / "report.html").write_text("<html></html>", encoding="utf-8")
            (output / "worksheet.md").write_text(
                "# Batch Worksheet\n\n## Prediction Check\n",
                encoding="utf-8",
            )
            (output / "comparison_plots").mkdir()
            (output / "comparison_plots" / "comparison.png").write_bytes(b"plot")
            write_manifest(
                output,
                scenario_id=f"batch.{batch_name}",
                status="completed",
                config={"batch_name": batch_name, "plot": True},
                run_kind="comparison_batch",
            )
            return output

        expected_batches = list(batch.list_batch_sets())
        expected_scenarios = sum(len(scenarios) for scenarios in batch.BATCH_SETS.values())
        progress: list[tuple[int, int, str]] = []
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"MCLAB_DATA_DIR": tmp}):
            all_output = create_all_compare_output()
            _program, arguments = all_compare_command(all_output)
            with patch("mclab.batch.run_batch", side_effect=fake_run_batch) as runner:
                output = batch.run_all_batches(
                    output_dir=all_output,
                    plot=False,
                    seed=23,
                    handoff_token=arguments[-1],
                    on_progress=lambda current, total, name: progress.append(
                        (current, total, name)
                    ),
                )

            self.assertEqual([call.args[0] for call in runner.call_args_list], expected_batches)
            for call in runner.call_args_list:
                self.assertFalse(call.kwargs["plot"])
                self.assertEqual(call.kwargs["seed"], 23)
                self.assertFalse(call.kwargs["publish_parent_index"])
            self.assertTrue((output / "report.html").exists())
            self.assertTrue((output / "worksheet.md").exists())
            self.assertTrue((output / "index.html").exists())
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["batch_name"], batch.ALL_BATCH_NAME)
            self.assertEqual(summary["scenario_runs"], expected_scenarios)
            self.assertGreaterEqual(summary["duration"], 0.0)

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scenario_id"], "batch.all")
            self.assertEqual(manifest["status"], "completed")
            self.assertNotIn("handoff_token_sha256", manifest)
            self.assertEqual(verify_manifest(output), [])
            self.assertEqual(
                progress,
                [
                    (index, len(expected_batches), name)
                    for index, name in enumerate(expected_batches, start=1)
                ],
            )
            batch_summary = json.loads((output / "batch_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(len(batch_summary["batches"]), len(expected_batches))
            report_html = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn("All Comparison Batches", report_html)
            self.assertIn("lab01_msd_compare/report.html", report_html)
            self.assertIn("lab04_cartesian_compare/report.html", report_html)
            self.assertIn("lab04_wall_compare/report.html", report_html)
            self.assertIn("Compare how damping and stiffness change free response", report_html)
            self.assertIn("Which case oscillates the most before settling?", report_html)
            self.assertIn("<th>Worksheet</th>", report_html)
            self.assertIn("<th>Folder</th>", report_html)
            self.assertIn("Open viewer handoff", report_html)
            self.assertIn('href="lab01_msd_compare/report.html#viewer-handoff"', report_html)
            self.assertIn("Open worksheet", report_html)
            self.assertIn("Open folder", report_html)
            self.assertIn("lab01_msd_compare/worksheet.md", report_html)
            self.assertIn('href="lab01_msd_compare/"', report_html)
            self.assertIn("Open the course worksheet", report_html)
            self.assertIn("digest-published and read-only", report_html)
            self.assertIn(
                "personal or course notes outside the saved-run folder",
                report_html,
            )
            self.assertIn("as a read-only reference", report_html)
            worksheet = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("# MCLab Course Batch Worksheet", worksheet)
            self.assertIn("## Saved Artifact Policy", worksheet)
            self.assertIn("digest-published and read-only", worksheet)
            self.assertIn(
                "personal or course notes outside the saved-run folder",
                worksheet,
            )
            self.assertIn("lab01_msd_compare", worksheet)
            self.assertIn(
                "Focus: Compare how damping and stiffness change free response", worksheet
            )
            self.assertIn(
                "First question: Which case oscillates the most before settling?", worksheet
            )
            self.assertIn("Worksheet: lab01_msd_compare/worksheet.md", worksheet)
            self.assertIn("Viewer handoff: lab01_msd_compare/report.html#viewer-handoff", worksheet)
            self.assertIn(
                "- Review prompt: Record one idea that stayed the same from Lab01 to Lab04.",
                worksheet,
            )
            self.assertNotIn("- [ ]", worksheet)
            self.assertIn(
                "lab01_msd_compare/report.html", (output / "index.html").read_text(encoding="utf-8")
            )

    def test_desktop_batch_handoff_is_one_shot(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MCLAB_DATA_DIR": str(Path(tmp).resolve() / "data")}),
        ):
            output = create_all_compare_output()
            _program, arguments = all_compare_command(output)
            token = arguments[-1]
            self.assertEqual(
                batch.create_batch_output_path(
                    "all_batches",
                    output,
                    handoff_token=token,
                ),
                output,
            )
            with self.assertRaisesRegex(RuntimeError, "invalid or already used"):
                batch.create_batch_output_path(
                    "all_batches",
                    output,
                    handoff_token=token,
                )

    def test_authenticated_progress_precedes_callback_and_child_batch(self) -> None:
        events: list[str] = []
        original_progress = batch.write_batch_progress

        def write_progress(*args: object, **kwargs: object) -> object:
            events.append("authenticated-progress")
            return original_progress(*args, **kwargs)

        def run_child(name: str, **kwargs: object) -> Path:
            events.append(f"run:{name}")
            output = Path(kwargs["output_dir"])
            output.mkdir(parents=True)
            (output / "summary.json").write_text("{}", encoding="utf-8")
            return output

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}),
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            with (
                patch.dict(
                    batch.BATCH_SETS,
                    {name: () for name in ALL_COMPARE_BATCH_NAMES},
                    clear=True,
                ),
                patch(
                    "mclab.batch.list_batch_sets",
                    return_value=list(ALL_COMPARE_BATCH_NAMES),
                ),
                patch("mclab.batch.write_batch_progress", side_effect=write_progress),
                patch("mclab.batch.run_batch", side_effect=run_child),
                patch("mclab.batch.write_outputs_index"),
                patch("mclab.batch.write_all_batches_report"),
            ):
                batch.run_all_batches(
                    output_dir=output,
                    plot=False,
                    handoff_token=token,
                    on_progress=lambda *_args: events.append("callback"),
                )

        self.assertEqual(
            events,
            [
                event
                for name in ALL_COMPARE_BATCH_NAMES
                for event in ("authenticated-progress", "callback", f"run:{name}")
            ],
        )

    def test_desktop_batch_handoff_rejects_directory_links(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MCLAB_DATA_DIR": str(Path(tmp).resolve() / "data")}),
        ):
            linked_output = create_all_compare_output()
            _program, linked_arguments = all_compare_command(linked_output)
            alias = Path(tmp).resolve() / "batch-alias"
            try:
                alias.symlink_to(linked_output, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("directory symlinks are unavailable")
            with self.assertRaisesRegex(RuntimeError, "invalid or already used"):
                batch.create_batch_output_path(
                    "all_batches",
                    alias,
                    handoff_token=linked_arguments[-1],
                )

    def test_authenticated_batch_progress_is_ordered_and_token_bound(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}),
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertEqual(read_batch_progress(output, token), ())
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_manifest(
                output,
                scenario_id="batch.all",
                status="running",
                config={"batch_name": "all", "plot": True},
                run_kind="comparison_batch",
            )
            refreshed = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                refreshed["handoff_token_sha256"],
                hashlib.sha256(token.encode("ascii")).hexdigest(),
            )
            first = write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )

            self.assertEqual(read_batch_progress(output, token), (first,))
            sidecar = output / BATCH_ACTIVE_DIR_NAME / BATCH_PROGRESS_FILE_NAME
            self.assertNotIn(token.encode("ascii"), sidecar.read_bytes())
            self.assertLessEqual(len(sidecar.read_bytes()), 4096)
            self.assertEqual(
                set(json.loads(sidecar.read_text(encoding="ascii"))),
                {"schema", "events", "hmac_sha256"},
            )
            with self.assertRaisesRegex(RuntimeError, "replayed or out of order"):
                write_batch_progress(
                    output,
                    token,
                    sequence=1,
                    current=1,
                    total=5,
                    name=ALL_COMPARE_BATCH_NAMES[0],
                )
            for index, name in enumerate(ALL_COMPARE_BATCH_NAMES[1:], start=2):
                write_batch_progress(
                    output,
                    token,
                    sequence=index,
                    current=index,
                    total=5,
                    name=name,
                )
            self.assertEqual(
                tuple(event.name for event in read_batch_progress(output, token)),
                ALL_COMPARE_BATCH_NAMES,
            )
            with self.assertRaisesRegex(RuntimeError, "handoff digest does not match"):
                read_batch_progress(output, "f" * 64)

    def test_batch_progress_writer_retries_one_transient_lock_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            original_lock = PinnedOutputRoot.operation_lock
            attempts = 0

            @contextmanager
            def contend_once(root_pin: PinnedOutputRoot):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise CleanupBusyError("injected peer reader")
                with original_lock(root_pin):
                    yield

            with (
                patch.object(PinnedOutputRoot, "operation_lock", contend_once),
                patch("mclab.application.batch_integrity.time.sleep"),
            ):
                event = write_batch_progress(
                    output,
                    token,
                    sequence=1,
                    current=1,
                    total=5,
                    name=ALL_COMPARE_BATCH_NAMES[0],
                )

            self.assertEqual(attempts, 2)
            self.assertEqual(read_batch_progress(output, token), (event,))

    def test_batch_progress_reader_reports_transient_lock_owner(self) -> None:
        class BusyLock:
            @staticmethod
            def __enter__() -> None:
                raise CleanupBusyError("injected peer writer")

            @staticmethod
            def __exit__(*args: object) -> bool:
                return False

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            with (
                patch.object(PinnedOutputRoot, "operation_lock", return_value=BusyLock()),
                self.assertRaisesRegex(BatchProgressBusy, "being updated"),
            ):
                read_batch_progress(output, token)

    def test_batch_terminal_manifest_writer_retries_one_transient_lock_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            release_all_compare_handoff(output)
            original_lock = PinnedOutputRoot.operation_lock
            attempts = 0

            @contextmanager
            def contend_once(root_pin: PinnedOutputRoot):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise CleanupBusyError("injected peer reader")
                with original_lock(root_pin):
                    yield

            with (
                patch.object(PinnedOutputRoot, "operation_lock", contend_once),
                patch("mclab.application.batch_integrity.time.sleep"),
            ):
                write_manifest(
                    output,
                    scenario_id="batch.all",
                    status="stopped",
                    config={"batch_name": "all", "plot": True},
                    run_kind="comparison_batch",
                )

            self.assertEqual(attempts, 2)
            self.assertEqual(
                verify_terminal_batch_output(output, expected_status="stopped"),
                [],
            )

    def test_progress_read_holds_one_lock_across_terminal_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            event = write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            original_lock = PinnedOutputRoot.operation_lock
            lock_entries = 0

            @contextmanager
            def counted_lock(root_pin: PinnedOutputRoot):
                nonlocal lock_entries
                lock_entries += 1
                with original_lock(root_pin):
                    yield

            with patch.object(PinnedOutputRoot, "operation_lock", counted_lock):
                self.assertEqual(read_batch_progress(output, token), (event,))
            self.assertEqual(lock_entries, 1)

            clear_all_compare_progress(output, token)
            release_all_compare_handoff(output)
            write_manifest(
                output,
                scenario_id="batch.all",
                status="completed",
                config={"batch_name": "all", "plot": True},
                run_kind="comparison_batch",
            )
            lock_entries = 0
            with patch.object(PinnedOutputRoot, "operation_lock", counted_lock):
                self.assertEqual(read_batch_progress(output, token), ())
            self.assertEqual(lock_entries, 1)

    def test_batch_error_manifest_always_has_nonempty_error_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "batch-error"
            output.mkdir()
            write_manifest(
                output,
                scenario_id="batch.unit",
                status="error",
                config={"batch_name": "unit", "plot": False},
                run_kind="comparison_batch",
                error="",
            )

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["error"])
            self.assertEqual(
                verify_terminal_batch_output(output, expected_status="error"),
                [],
            )

    def test_non_error_batch_terminal_rejects_error_detail_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "batch-stopped"
            output.mkdir()
            with self.assertRaisesRegex(RuntimeError, "only valid for terminal error"):
                write_manifest(
                    output,
                    scenario_id="batch.unit",
                    status="stopped",
                    config={"batch_name": "unit", "plot": False},
                    run_kind="comparison_batch",
                    error="must not be published",
                )
            self.assertFalse((output / "manifest.json").exists())

    def test_terminal_batch_update_rejects_live_transient_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            before = (output / "manifest.json").read_bytes()

            with self.assertRaisesRegex(RuntimeError, "live transient marker"):
                update_batch_manifest(output, status="stopped")

            self.assertEqual((output / "manifest.json").read_bytes(), before)
            self.assertEqual(
                json.loads(before.decode("utf-8"))["status"],
                "running",
            )

    def test_authenticated_batch_progress_rejects_tamper_and_noncanonical_data(self) -> None:
        def signed(payload: dict[str, object], token: str) -> bytes:
            unsigned = {
                "schema": payload["schema"],
                "events": payload["events"],
            }
            canonical_unsigned = json.dumps(
                unsigned, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
            payload["hmac_sha256"] = hmac.new(
                bytes.fromhex(token), canonical_unsigned, hashlib.sha256
            ).hexdigest()
            return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")

        mutations = ("tamper", "extra", "bool", "noncanonical", "oversized", "malformed")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp, patch.dict(
                os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
            ):
                output = create_all_compare_output()
                token = read_all_compare_handoff(output)
                self.assertTrue(claim_all_compare_handoff(output, token))
                write_batch_progress(
                    output,
                    token,
                    sequence=1,
                    current=1,
                    total=5,
                    name=ALL_COMPARE_BATCH_NAMES[0],
                )
                sidecar = output / BATCH_ACTIVE_DIR_NAME / BATCH_PROGRESS_FILE_NAME
                payload = json.loads(sidecar.read_text(encoding="utf-8"))
                if mutation == "tamper":
                    payload["events"][0]["name"] = ALL_COMPARE_BATCH_NAMES[1]
                    sidecar.write_text(
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        encoding="ascii",
                    )
                elif mutation == "extra":
                    payload["extra"] = 1
                    sidecar.write_bytes(signed(payload, token))
                elif mutation == "bool":
                    payload["events"][0]["sequence"] = True
                    sidecar.write_bytes(signed(payload, token))
                elif mutation == "noncanonical":
                    sidecar.write_text(json.dumps(payload, indent=2), encoding="ascii")
                elif mutation == "oversized":
                    sidecar.write_bytes(b"x" * 4097)
                else:
                    sidecar.write_bytes(b"{")

                with self.assertRaises(RuntimeError):
                    read_batch_progress(output, token)

    @unittest.skipIf(os.name == "nt", "symlink creation is not reliable on Windows CI")
    def test_authenticated_batch_progress_rejects_linked_or_unknown_active_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            outside = Path(tmp) / "outside.json"
            outside.write_text("outside", encoding="utf-8")
            sidecar = output / BATCH_ACTIVE_DIR_NAME / BATCH_PROGRESS_FILE_NAME
            sidecar.symlink_to(outside)

            with self.assertRaises(RuntimeError):
                read_batch_progress(output, token)
            with self.assertRaises(RuntimeError):
                settle_all_compare_output(output, token, "stopped")
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")
            self.assertEqual(
                json.loads((output / "manifest.json").read_text(encoding="utf-8"))["status"],
                "running",
            )

    def test_batch_parent_settlement_recovers_each_authenticated_marker_boundary(self) -> None:
        states = ("preclaim", "postclaim", "empty-active", "markerless")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            for state in states:
                with self.subTest(state=state):
                    output = create_all_compare_output()
                    token = read_all_compare_handoff(output)
                    if state != "preclaim":
                        self.assertTrue(claim_all_compare_handoff(output, token))
                    if state in {"postclaim", "empty-active", "markerless"}:
                        write_batch_progress(
                            output,
                            token,
                            sequence=1,
                            current=1,
                            total=5,
                            name=ALL_COMPARE_BATCH_NAMES[0],
                        )
                    if state in {"empty-active", "markerless"}:
                        clear_all_compare_progress(output, token)
                    if state == "markerless":
                        release_all_compare_handoff(output)

                    self.assertEqual(
                        settle_all_compare_output(output, token, "stopped"),
                        "stopped",
                    )
                    self.assertFalse((output / BATCH_ACTIVE_DIR_NAME).exists())
                    self.assertFalse((output / ".mclab-batch-handoff").exists())
                    self.assertEqual(
                        verify_terminal_batch_output(output, expected_status="stopped"),
                        [],
                    )

    @unittest.skipIf(os.name == "nt", "Windows settlement never deletes partial paths")
    def test_batch_parent_settlement_prunes_only_empty_interrupted_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            baseline = output / "lab01_msd_compare" / "baseline"
            plots = baseline / "plots"
            plots.mkdir(parents=True)
            evidence = baseline / "partial.bin"
            evidence.write_bytes(b"preserve-partial-evidence")

            self.assertEqual(
                settle_all_compare_output(output, token, "stopped"),
                "stopped",
            )

            self.assertFalse(plots.exists())
            self.assertEqual(evidence.read_bytes(), b"preserve-partial-evidence")
            self.assertFalse((output / BATCH_ACTIVE_DIR_NAME).exists())
            self.assertEqual(
                verify_terminal_batch_output(output, expected_status="stopped"),
                [],
            )

    @unittest.skipIf(os.name == "nt", "Windows settlement never deletes partial paths")
    def test_batch_parent_settlement_prunes_producer_empty_ancestors(self) -> None:
        for boundary in ("batch", "scenario", "comparison_plots"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as tmp, (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")})
            ):
                output = create_all_compare_output()
                token = read_all_compare_handoff(output)
                self.assertTrue(claim_all_compare_handoff(output, token))
                write_batch_progress(
                    output,
                    token,
                    sequence=1,
                    current=1,
                    total=5,
                    name=ALL_COMPARE_BATCH_NAMES[0],
                )
                batch_output = output / "lab01_msd_compare"
                if boundary == "batch":
                    batch_output.mkdir()
                elif boundary == "scenario":
                    logger = RunLogger(
                        "lab01_msd",
                        {},
                        output_dir=batch_output / "baseline",
                    )
                    self.assertTrue((logger.output_path / "plots").is_dir())
                else:
                    (batch_output / "comparison_plots").mkdir(parents=True)

                self.assertEqual(
                    settle_all_compare_output(output, token, "stopped"),
                    "stopped",
                )

                self.assertFalse(batch_output.exists())
                self.assertEqual(
                    verify_terminal_batch_output(output, expected_status="stopped"),
                    [],
                )

    @unittest.skipIf(os.name == "nt", "Windows settlement never deletes partial paths")
    def test_batch_parent_settlement_preserves_nonempty_plot_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            plots = output / "lab01_msd_compare" / "baseline" / "plots"
            plots.mkdir(parents=True)
            first = plots / "first.png"
            second = plots / "second.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")

            self.assertEqual(
                settle_all_compare_output(output, token, "stopped"),
                "stopped",
            )

            self.assertEqual(first.read_bytes(), b"first")
            self.assertEqual(second.read_bytes(), b"second")
            self.assertEqual(
                verify_terminal_batch_output(output, expected_status="stopped"),
                [],
            )

    @unittest.skipIf(os.name == "nt", "Windows settlement never deletes partial paths")
    def test_batch_parent_empty_directory_prune_fault_stays_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            plots = output / "lab01_msd_compare" / "baseline" / "plots"
            plots.mkdir(parents=True)
            original_rmdir = PinnedOutputRoot.rmdir

            def fail_plots(root: PinnedOutputRoot, relative: tuple[str, ...]) -> None:
                if relative[-1:] == ("plots",):
                    raise OSError("injected empty-directory prune fault")
                original_rmdir(root, relative)

            with (
                patch.object(PinnedOutputRoot, "rmdir", fail_plots),
                self.assertRaisesRegex(RuntimeError, "prune fault"),
            ):
                settle_all_compare_output(output, token, "stopped")

            self.assertEqual(
                json.loads((output / "manifest.json").read_text(encoding="utf-8"))["status"],
                "running",
            )
            self.assertTrue(plots.is_dir())
            self.assertFalse((output / BATCH_ACTIVE_DIR_NAME).exists())
            self.assertEqual(
                settle_all_compare_output(output, token, "stopped"),
                "stopped",
            )

    @unittest.skipIf(os.name == "nt", "POSIX link and special-node fixture")
    def test_batch_parent_empty_directory_prune_rejects_unsafe_nodes(self) -> None:
        for unsafe_kind in ("link", "special"):
            with self.subTest(unsafe_kind=unsafe_kind), tempfile.TemporaryDirectory() as tmp, (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")})
            ):
                output = create_all_compare_output()
                token = read_all_compare_handoff(output)
                self.assertTrue(claim_all_compare_handoff(output, token))
                write_batch_progress(
                    output,
                    token,
                    sequence=1,
                    current=1,
                    total=5,
                    name=ALL_COMPARE_BATCH_NAMES[0],
                )
                partial = output / "lab01_msd_compare" / "baseline"
                partial.mkdir(parents=True)
                unsafe = partial / unsafe_kind
                outside = Path(tmp) / "outside"
                outside.write_bytes(b"outside-must-survive")
                if unsafe_kind == "link":
                    unsafe.symlink_to(outside)
                    expected = "link or reparse point"
                else:
                    os.mkfifo(unsafe)
                    expected = "special filesystem entry"

                with self.assertRaisesRegex(RuntimeError, expected):
                    settle_all_compare_output(output, token, "stopped")

                self.assertEqual(outside.read_bytes(), b"outside-must-survive")
                self.assertEqual(
                    json.loads((output / "manifest.json").read_text(encoding="utf-8"))[
                        "status"
                    ],
                    "running",
                )

    @unittest.skipIf(os.name == "nt", "Windows settlement never deletes partial paths")
    def test_batch_parent_empty_directory_prune_rejects_mount_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            plots = output / "lab01_msd_compare" / "baseline" / "plots"
            plots.mkdir(parents=True)
            original_mount_check = PinnedOutputRoot.is_mount_point

            def report_mount(root: PinnedOutputRoot, relative: tuple[str, ...]) -> bool:
                if relative[-1:] == ("plots",):
                    return True
                return original_mount_check(root, relative)

            with (
                patch.object(PinnedOutputRoot, "is_mount_point", report_mount),
                self.assertRaisesRegex(RuntimeError, "mount point"),
            ):
                settle_all_compare_output(output, token, "stopped")

            self.assertEqual(
                json.loads((output / "manifest.json").read_text(encoding="utf-8"))["status"],
                "running",
            )

    @unittest.skipIf(os.name == "nt", "Windows settlement never deletes partial paths")
    def test_batch_parent_empty_directory_prune_does_not_normalize_unknown_empty_dir(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            baseline = output / "lab01_msd_compare" / "baseline"
            plots = baseline / "plots"
            canary = baseline / "canary"
            plots.mkdir(parents=True)
            canary.mkdir()

            with self.assertRaisesRegex(RuntimeError, "unlisted empty directory"):
                settle_all_compare_output(output, token, "stopped")

            self.assertFalse(plots.exists())
            self.assertTrue(canary.is_dir())
            self.assertEqual(
                json.loads((output / "manifest.json").read_text(encoding="utf-8"))["status"],
                "running",
            )

    @unittest.skipIf(os.name == "nt", "Windows settlement never deletes partial paths")
    def test_batch_parent_settlement_preserves_unknown_scenario_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            unknown_plots = (
                output / "lab01_msd_compare" / "unknown-canary" / "plots"
            )
            unknown_plots.mkdir(parents=True)

            with self.assertRaisesRegex(RuntimeError, "unlisted empty directory"):
                settle_all_compare_output(output, token, "stopped")

            self.assertTrue(unknown_plots.is_dir())
            self.assertEqual(
                json.loads((output / "manifest.json").read_text(encoding="utf-8"))["status"],
                "running",
            )

    @unittest.skipIf(os.name == "nt", "POSIX symlink identity-swap fixture")
    def test_batch_parent_empty_directory_prune_rejects_identity_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            plots = output / "lab01_msd_compare" / "baseline" / "plots"
            plots.mkdir(parents=True)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            original_validate = PinnedOutputRoot.validate_directory
            swapped = False

            def swap_after_validation(
                root: PinnedOutputRoot,
                relative: tuple[str, ...],
                *,
                description: str,
            ) -> None:
                nonlocal swapped
                original_validate(root, relative, description=description)
                if relative[-1:] == ("plots",) and not swapped:
                    plots.rmdir()
                    plots.symlink_to(outside, target_is_directory=True)
                    swapped = True

            with (
                patch.object(PinnedOutputRoot, "validate_directory", swap_after_validation),
                self.assertRaises(RuntimeError),
            ):
                settle_all_compare_output(output, token, "stopped")

            self.assertTrue(swapped)
            self.assertTrue(plots.is_symlink())
            self.assertTrue(outside.is_dir())
            self.assertEqual(
                json.loads((output / "manifest.json").read_text(encoding="utf-8"))["status"],
                "running",
            )

    def test_batch_parent_settlement_preserves_terminal_and_never_synthesizes_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            running = create_all_compare_output()
            running_token = read_all_compare_handoff(running)
            running_bytes = (running / "manifest.json").read_bytes()
            with self.assertRaisesRegex(RuntimeError, "cannot be recovered"):
                settle_all_compare_output(running, running_token, "completed")
            self.assertEqual((running / "manifest.json").read_bytes(), running_bytes)

            settled = create_all_compare_output()
            settled_token = read_all_compare_handoff(settled)
            settle_all_compare_output(settled, settled_token, "error", "worker failed")
            terminal_bytes = (settled / "manifest.json").read_bytes()
            self.assertEqual(
                settle_all_compare_output(settled, "0" * 64, "completed"),
                "error",
            )
            self.assertEqual((settled / "manifest.json").read_bytes(), terminal_bytes)

    def test_batch_parent_cleanup_fault_never_terminalizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.assertTrue(claim_all_compare_handoff(output, token))
            write_batch_progress(
                output,
                token,
                sequence=1,
                current=1,
                total=5,
                name=ALL_COMPARE_BATCH_NAMES[0],
            )
            with (
                patch(
                    "mclab.application.batch_runs._unlink_regular_file_rooted",
                    side_effect=OSError("injected cleanup fault"),
                ),
                self.assertRaisesRegex(RuntimeError, "injected cleanup fault"),
            ):
                settle_all_compare_output(output, token, "error", "worker failed")

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "running")
            self.assertTrue((output / BATCH_ACTIVE_DIR_NAME / BATCH_PROGRESS_FILE_NAME).exists())

    def test_run_all_error_cleanup_failure_never_terminalizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCLAB_DATA_DIR": str(Path(tmp) / "data")}
        ):
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            with (
                patch("mclab.batch.run_batch", side_effect=RuntimeError("child failed")),
                patch("mclab.batch.write_all_batches_report"),
                patch("mclab.batch.write_outputs_index"),
                patch(
                    "mclab.batch.clear_all_compare_progress",
                    side_effect=RuntimeError("cleanup failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "child failed"),
            ):
                batch.run_all_batches(
                    output_dir=output,
                    plot=False,
                    handoff_token=token,
                )

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "running")
            self.assertIn("handoff_token_sha256", manifest)
            self.assertTrue((output / BATCH_ACTIVE_DIR_NAME / BATCH_PROGRESS_FILE_NAME).exists())

    def test_strict_terminal_batch_verifier_rejects_unlisted_and_transient_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary_root = Path(tmp).resolve()
            output = temporary_root / "batch"
            output.mkdir()
            (output / "summary.json").write_text("{}", encoding="utf-8")
            write_manifest(
                output,
                scenario_id="batch.unit",
                status="completed",
                config={"batch_name": "unit", "plot": False},
                run_kind="comparison_batch",
            )
            self.assertEqual(
                verify_terminal_batch_output(output, expected_status="completed"),
                [],
            )
            (output / "unlisted.txt").write_text("late", encoding="utf-8")
            self.assertTrue(
                any(
                    "Unlisted artifact: unlisted.txt" in error
                    for error in verify_terminal_batch_output(
                        output, expected_status="completed"
                    )
                )
            )

            transient = temporary_root / "transient"
            transient.mkdir()
            (transient / BATCH_ACTIVE_DIR_NAME).mkdir()
            with self.assertRaisesRegex(RuntimeError, "live transient marker"):
                write_manifest(
                    transient,
                    scenario_id="batch.unit",
                    status="completed",
                    config={"batch_name": "unit", "plot": False},
                    run_kind="comparison_batch",
                )

            published = temporary_root / "published-with-transient"
            published.mkdir()
            write_manifest(
                published,
                scenario_id="batch.unit",
                status="completed",
                config={"batch_name": "unit", "plot": False},
                run_kind="comparison_batch",
            )
            (published / BATCH_ACTIVE_DIR_NAME).mkdir()
            self.assertTrue(
                any(
                    "live transient marker" in error
                    for error in verify_terminal_batch_output(
                        published, expected_status="completed"
                    )
                )
            )

            if os.name != "nt":
                linked = temporary_root / "published-with-link"
                linked.mkdir()
                write_manifest(
                    linked,
                    scenario_id="batch.unit",
                    status="completed",
                    config={"batch_name": "unit", "plot": False},
                    run_kind="comparison_batch",
                )
                (linked / "unsafe-link").symlink_to(output / "summary.json")
                self.assertTrue(
                    any(
                        "link or reparse point" in error
                        for error in verify_terminal_batch_output(
                            linked, expected_status="completed"
                        )
                    )
                )

    def test_run_batch_rejects_unknown_batch_name(self) -> None:
        with self.assertRaises(ValueError):
            batch.run_batch("missing_batch")

    def test_display_metric_keys_skip_unrelated_all_zero_fallback_metrics(self) -> None:
        guide = batch.BATCH_GUIDES["lab04_cartesian_compare"]
        rows = [
            {
                "summary": {
                    "final_cartesian_error_cm": 0.6,
                    "max_wall_penetration_cm": 0.0,
                    "max_wall_retreat_cm": 0.0,
                    "max_abs_virtual_wall_force": 0.0,
                }
            }
        ]

        keys = batch._display_metric_keys(guide, rows)

        self.assertIn("final_cartesian_error_cm", keys)
        self.assertNotIn("max_wall_penetration_cm", keys)
        self.assertNotIn("max_wall_retreat_cm", keys)
        self.assertNotIn("max_abs_virtual_wall_force", keys)

    def test_viewer_handoff_picks_largest_metric_change_from_baseline(self) -> None:
        rows = [
            {"label": "baseline", "summary": {"tracking_error": 1.0, "control_effort": 10.0}},
            {"label": "small_change", "summary": {"tracking_error": 1.2, "control_effort": 11.0}},
            {"label": "large_change", "summary": {"tracking_error": 3.0, "control_effort": 10.5}},
        ]

        picked, reason = batch._viewer_handoff_pick(
            rows,
            ["tracking_error", "control_effort"],
            rows[0]["summary"],
        )

        self.assertEqual(picked["label"], "large_change")
        self.assertIn("largest tracking error change from baseline", reason)

    def test_viewer_handoff_section_includes_artifact_links(self) -> None:
        row = {
            "label": "demo",
            "lab_name": "lab01",
            "config_path": "configs/lab01_msd/default.yaml",
            "plot_selection": "essential",
            "report": "demo/report.html",
            "worksheet": "demo/worksheet.md",
            "folder": "demo/",
            "plots": {"position.png": "demo/plots/position.png"},
            "summary": {"max_abs_position": 0.1},
        }

        html = batch._viewer_handoff_section([row], ["max_abs_position"], row["summary"])

        self.assertIn('href="demo/report.html">Open report</a>', html)
        self.assertIn('href="demo/plots/position.png">Open position.png</a>', html)
        self.assertIn('href="demo/worksheet.md">Open worksheet</a>', html)
        self.assertIn('href="demo/">Open folder</a>', html)

    def test_comparison_takeaways_rank_error_metrics_by_magnitude(self) -> None:
        rows = [
            {"label": "near_zero", "summary": {"steady_state_error": -0.01}},
            {"label": "far_negative", "summary": {"steady_state_error": -0.5}},
            {"label": "positive", "summary": {"steady_state_error": 0.2}},
        ]

        html = batch._comparison_takeaways(rows, ["steady_state_error"])

        self.assertIn("near_zero</strong> has the smallest error magnitude", html)
        self.assertIn("far_negative</strong> has the largest", html)

    def test_prediction_check_ranks_error_metrics_by_magnitude(self) -> None:
        rows = [
            {"label": "near_zero", "summary": {"steady_state_error": -0.01}},
            {"label": "far_negative", "summary": {"steady_state_error": -0.5}},
            {"label": "positive", "summary": {"steady_state_error": 0.2}},
        ]

        items = batch._prediction_check_items(rows, ["steady_state_error"])
        html = batch._prediction_check(rows, ["steady_state_error"])
        worksheet_lines = batch._batch_worksheet_prediction_check_lines(
            rows, ["steady_state_error"]
        )

        self.assertEqual(len(items), 1)
        self.assertIn("near_zero (", items[0][1])
        self.assertIn("far_negative (", items[0][1])
        self.assertIn("Matched / Partly matched / Surprised", html)
        self.assertIn("digest-published and read-only", html)
        self.assertIn("personal or course notes outside the saved-run folder", html)
        self.assertTrue(any("## Prediction Check" in line for line in worksheet_lines))
        self.assertTrue(
            any(
                "personal or course notes outside the saved-run folder" in line
                for line in worksheet_lines
            )
        )
        self.assertTrue(any("Review prompt:" in line for line in worksheet_lines))
        self.assertFalse(any("- [ ]" in line for line in worksheet_lines))

    def test_comparison_plots_are_written_from_run_logs(self) -> None:
        scenarios = (
            batch.BatchScenario("baseline", "lab02", "configs/lab02_pid/default.yaml"),
            batch.BatchScenario("high gain", "lab02", "configs/lab02_pid/p_high_gain.yaml"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "batch_output"
            output.mkdir()
            write_manifest(
                output,
                scenario_id="batch.lab02_pid_compare",
                status="running",
                config={"batch_name": "lab02_pid_compare", "plot": True},
                run_kind="comparison_batch",
            )
            for scenario in scenarios:
                run_dir = output / scenario.label.replace(" ", "_")
                run_dir.mkdir()
                (run_dir / "log.csv").write_text(
                    (
                        "time,position,position_error,control_force\n"
                        "0.0,0.0,0.2,12.0\n"
                        "0.1,0.1,0.1,6.0\n"
                        "0.2,0.2,0.0,0.0\n"
                    ),
                    encoding="utf-8",
                )
                (run_dir / "summary.json").write_text(
                    json.dumps(
                        {
                            "lab_name": "lab02_pid",
                            "overshoot_percent": 0.0 if scenario.label == "baseline" else 12.5,
                        }
                    ),
                    encoding="utf-8",
                )
                (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
                write_manifest(
                    run_dir,
                    scenario_id=stable_scenario_id(scenario.lab_name, scenario.config_path),
                    status="completed",
                    config=load_config(scenario.config_path),
                    config_path=scenario.config_path,
                )

            written = batch.write_comparison_plots(output, "lab02_pid_compare", scenarios)
            batch.write_batch_report(output, "lab02_pid_compare", scenarios)
            write_manifest(
                output,
                scenario_id="batch.lab02_pid_compare",
                status="completed",
                config={"batch_name": "lab02_pid_compare", "plot": True},
                run_kind="comparison_batch",
            )

            self.assertTrue(written)
            self.assertEqual(verify_manifest(output), [])
            self.assertTrue((output / "comparison_plots" / "position_compare.png").exists())
            self.assertTrue((output / "comparison_plots" / "error_compare.png").exists())
            report_html = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn("Comparison Takeaways", report_html)
            self.assertIn("Prediction Check", report_html)
            self.assertIn("Outcome prompt", report_html)
            self.assertIn(
                "Record in personal or course notes: prediction outcome for overshoot percent - "
                "Matched / Partly matched / Surprised.",
                report_html,
            )
            self.assertIn("digest-published and read-only", report_html)
            self.assertIn(
                "personal or course notes outside the saved-run folder",
                report_html,
            )
            self.assertIn("Predict", report_html)
            self.assertIn("Which controller reaches the target fastest", report_html)
            self.assertIn("python -m mclab batch lab02_pid_compare --open-report", report_html)
            self.assertIn(
                "python -m mclab run lab02 --config configs/lab02_pid/default.yaml --headless --plot --plots essential",
                report_html,
            )
            self.assertIn("Changed from baseline", report_html)
            self.assertIn("controller.kp", report_html)
            self.assertIn("Metric change from baseline", report_html)
            self.assertIn("overshoot percent", report_html)
            self.assertIn("baseline</strong> has the least overshoot", report_html)
            self.assertIn("high gain</strong> overshoots most", report_html)
            self.assertIn("Metric Highlights", report_html)
            self.assertIn("overshoot percent", report_html)
            self.assertIn("high gain", report_html)
            self.assertIn("Baseline Changes", report_html)
            self.assertIn("+12.5", report_html)
            self.assertIn("raise `controller.kd`", report_html)
            self.assertIn("Parameter Differences", report_html)
            self.assertIn("controller.kp", report_html)
            self.assertIn("Comparison Plot Guide", report_html)
            self.assertIn("Position", report_html)
            self.assertIn("Compare actual motion against target", report_html)
            self.assertIn("Checkpoint:", report_html)
            self.assertIn("Comparison Plots", report_html)
            self.assertIn("comparison_plots/position_compare.png", report_html)
            worksheet = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("# MCLab Batch Worksheet", worksheet)
            self.assertIn("## Prediction Check", worksheet)
            self.assertIn(
                "Review prompt: Record in personal or course notes: prediction outcome for "
                "overshoot percent - Matched / Partly matched / Surprised.",
                worksheet,
            )
            self.assertIn("Comparison Notes", worksheet)
            self.assertIn("overshoot percent", worksheet)
            self.assertIn("## Comparison Plot Guide", worksheet)
            self.assertIn(
                "comparison_plots/position_compare.png: Position - Compare actual motion against target",
                worksheet,
            )
            self.assertIn(
                "Review prompt: Name which scenario changes motion most visibly",
                worksheet,
            )
            self.assertIn("comparison_plots/position_compare.png", worksheet)
            self.assertNotIn("- [ ]", worksheet)

    def test_summary_comparison_plots_are_written_from_scenario_summaries(self) -> None:
        scenarios = (
            batch.BatchScenario(
                "soft_wall", "lab04", "configs/lab04_panda/wall_soft.yaml", "wall_compare"
            ),
            batch.BatchScenario(
                "fast_wall", "lab04", "configs/lab04_panda/wall_fast_approach.yaml", "wall_compare"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "batch_output"
            output.mkdir()
            write_manifest(
                output,
                scenario_id="batch.lab04_wall_compare",
                status="running",
                config={"batch_name": "lab04_wall_compare", "plot": True},
                run_kind="comparison_batch",
            )
            for index, scenario in enumerate(scenarios):
                run_dir = output / scenario.label
                run_dir.mkdir()
                (run_dir / "summary.json").write_text(
                    json.dumps(
                        {
                            "lab_name": "lab04_panda",
                            "first_wall_contact_time": 0.8 + index,
                            "peak_wall_penetration_time": 2.0 + index,
                            "peak_wall_force_time": 2.1 + index,
                            "peak_wall_damping_force_time": 0.9 + index,
                            "peak_hand_speed_time": 1.1 + index,
                        }
                    ),
                    encoding="utf-8",
                )
                (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
                write_manifest(
                    run_dir,
                    scenario_id=stable_scenario_id(scenario.lab_name, scenario.config_path),
                    status="completed",
                    config=load_config(scenario.config_path),
                    config_path=scenario.config_path,
                )

            written = batch.write_comparison_plots(output, "lab04_wall_compare", scenarios)
            (output / "comparison_plots" / "wall_penetration_compare.png").write_bytes(b"fake-png")
            batch.write_batch_report(output, "lab04_wall_compare", scenarios)
            write_manifest(
                output,
                scenario_id="batch.lab04_wall_compare",
                status="completed",
                config={"batch_name": "lab04_wall_compare", "plot": True},
                run_kind="comparison_batch",
            )

            timing_plot = output / "comparison_plots" / "wall_key_moment_timing_compare.png"
            self.assertIn(timing_plot, written)
            self.assertTrue(timing_plot.exists())
            self.assertEqual(verify_manifest(output), [])
            report_html = (output / "report.html").read_text(encoding="utf-8")
            worksheet = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("wall_key_moment_timing_compare.png", report_html)
            self.assertIn("Comparison Plot Guide", report_html)
            self.assertIn("Wall Timing", report_html)
            self.assertIn("Compare when contact, peak penetration", report_html)
            self.assertIn("Name which scenario contacts first", report_html)
            self.assertIn("Wall Penetration", report_html)
            self.assertIn("Name which scenario penetrates deepest", report_html)
            self.assertIn("peak wall force time", report_html)
            self.assertIn("wall_key_moment_timing_compare.png", worksheet)
            self.assertIn("## Comparison Plot Guide", worksheet)
            self.assertIn(
                "comparison_plots/wall_key_moment_timing_compare.png: Wall Timing", worksheet
            )
            self.assertIn("Review prompt: Name which scenario contacts first", worksheet)
            self.assertIn(
                "comparison_plots/wall_penetration_compare.png: Wall Penetration", worksheet
            )
            self.assertIn("Review prompt: Name which scenario penetrates deepest", worksheet)
            self.assertNotIn("- [ ]", worksheet)

    def test_scenario_card_reports_missing_plot_links_without_failing(self) -> None:
        html = batch._scenario_card(
            {
                "label": "no plot",
                "lab_name": "lab01",
                "config_path": "configs/lab01_msd/default.yaml",
                "report": "no_plot/report.html",
                "plots": {},
                "summary": {"max_abs_position": 0.2},
                "config": load_config("configs/lab01_msd/default.yaml"),
            },
            ["max_abs_position"],
        )

        self.assertIn("Open report", html)
        self.assertIn("No plot link saved", html)
        self.assertIn("No worksheet link saved", html)
        self.assertIn("Control surface", html)
        self.assertIn("Auto run; edit YAML before rerunning.", html)

    def test_scenario_card_shows_interactive_control_surface(self) -> None:
        html = batch._scenario_card(
            {
                "label": "interactive",
                "lab_name": "lab01",
                "config_path": "configs/lab01_msd/interactive_pull.yaml",
                "report": "interactive/report.html",
                "plots": {},
                "summary": {"max_abs_position": 0.2},
                "config": load_config("configs/lab01_msd/interactive_pull.yaml"),
            },
            ["max_abs_position"],
        )

        self.assertIn("Control surface", html)
        self.assertIn("MCLab Interaction window", html)
        self.assertIn("Pull/Push buttons and A/D keys", html)
        self.assertIn("live sliders with Changed values", html)
        self.assertIn("quick presets (Lightly damped, Heavy damping, Stiff spring)", html)
        self.assertIn("Counts as control: experiment buttons, live sliders, Quick presets", html)
        self.assertIn("Pause/Step", html)
        self.assertIn("Reset plant", html)
        self.assertIn("Mark observation", html)

    def test_priority_plot_link_uses_index_plot_priority(self) -> None:
        selected = batch._priority_plot_link(
            {
                "torque.png": "run/plots/torque.png",
                "position.png": "run/plots/position.png",
            }
        )

        self.assertEqual(selected, ("position.png", "run/plots/position.png"))

    def test_scenario_change_summary_compares_against_baseline(self) -> None:
        html = batch._scenario_change_summary(
            {"config": {"controller": {"kp": 120.0, "kd": 0.0}}},
            {"controller": {"kp": 60.0, "kd": 12.0}},
        )

        self.assertIn("Changed from baseline", html)
        self.assertIn("controller.kp", html)
        self.assertIn("60", html)
        self.assertIn("120", html)

    def test_scenario_metric_change_summary_compares_against_baseline(self) -> None:
        html = batch._scenario_metric_change_summary(
            {"summary": {"overshoot_percent": 12.5, "settling_time": 1.8}},
            ["overshoot_percent", "settling_time"],
            {"overshoot_percent": 0.0, "settling_time": 2.0},
        )

        self.assertIn("Metric change from baseline", html)
        self.assertIn("overshoot percent", html)
        self.assertIn("+12.5", html)
        self.assertIn("n/a", html)


if __name__ == "__main__":
    unittest.main()
