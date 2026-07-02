from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.logging import RunLogger, create_output_path  # noqa: E402
from mclab.learning_guides import guide_for_config  # noqa: E402
from mclab.sim.reporting import (  # noqa: E402
    NEXT_RUN_SUGGESTIONS,
    _activity_mix_items,
    _learning_path_prediction_cue_text,
    _normalize_path,
    plot_priorities_for_context,
    write_outputs_index,
    write_run_report,
)


class FixedDatetime:
    @classmethod
    def now(cls) -> datetime:
        return datetime(2026, 6, 27, 20, 50, 0)


class LoggingTests(unittest.TestCase):
    def test_plot_priorities_follow_lesson_context(self) -> None:
        dls_priorities = plot_priorities_for_context(
            config_path="configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml",
            lab_name="lab03_2dof",
        )
        wall_batch_priorities = plot_priorities_for_context(
            config_name="lab04_wall_compare",
            batch_name="lab04_wall_compare",
        )

        self.assertEqual(dls_priorities[0], "dls")
        self.assertLess(dls_priorities.index("dls"), dls_priorities.index("error"))
        self.assertEqual(wall_batch_priorities[0], "wall_key_moment_timing")

    def test_learning_path_prediction_cue_preserves_dls_acronym(self) -> None:
        cue = _learning_path_prediction_cue_text(
            "Prediction: Before changing schedule, predict how DLS task-speed limit will change."
        )

        self.assertIn("predict how DLS task-speed limit", cue)
        self.assertNotIn("dLS", cue)

    def test_activity_mix_items_summarize_interaction_variety(self) -> None:
        items = dict(
            _activity_mix_items(
                [
                    {"kind": "preset", "label": "Soft wall"},
                    {"kind": "slider", "label": "Wall stiffness", "value": 300.0},
                    {"kind": "button", "label": "Pause simulation"},
                    {"kind": "marker", "name": "observation", "label": "Mark observation"},
                ]
            )
        )

        self.assertEqual(items["Control types used"], "button -> slider -> preset -> marker")
        self.assertEqual(
            items["Activity path"],
            "preset: Soft wall -> slider: Wall stiffness -> button: Pause simulation -> observation: Mark observation",
        )
        self.assertEqual(items["Button actions"], 1)
        self.assertEqual(items["Slider changes"], 1)
        self.assertEqual(items["Preset choices"], 1)
        self.assertEqual(items["Observation markers"], 1)
        self.assertEqual(items["Hands-on controls before review"], 3)
        self.assertEqual(items["Interaction variety"], "3/3 control families")
        self.assertEqual(
            items["Next activity step"],
            "Ready: compare this interaction mix against plots and the worksheet.",
        )

    def test_activity_mix_ignores_helper_and_view_events_as_controls(self) -> None:
        items = dict(
            _activity_mix_items(
                [
                    {"kind": "button", "name": "use_live_status_note", "label": "Use live status"},
                    {"kind": "button", "name": "use_changed_values_note", "label": "Use changed values"},
                    {"kind": "button", "name": "clear_observation_note", "label": "Clear note"},
                    {"kind": "button", "name": "pause_simulation", "label": "Pause simulation"},
                    {"kind": "button", "name": "step_simulation", "label": "Step once"},
                    {"kind": "slider", "name": "playback_speed", "label": "Playback speed", "value": 0.5},
                    {"kind": "marker", "name": "observation", "label": "Mark observation"},
                ]
            )
        )

        self.assertEqual(items["Control types used"], "marker")
        self.assertEqual(items["Activity path"], "observation: Mark observation")
        self.assertEqual(items["Button actions"], 0)
        self.assertEqual(items["Hands-on controls before review"], 0)
        self.assertEqual(items["Interaction variety"], "0/3 control families")

    def test_guided_configs_have_suggested_next_runs(self) -> None:
        missing: list[str] = []
        for config_path in sorted((ROOT / "configs").glob("**/*.yaml")):
            relative = config_path.relative_to(ROOT).as_posix()
            if guide_for_config(config_path=relative) and _normalize_path(relative) not in NEXT_RUN_SUGGESTIONS:
                missing.append(relative)

        self.assertEqual(missing, [])

    def test_automatic_output_paths_are_unique_within_same_second(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("mclab.sim.logging.PROJECT_ROOT", Path(temp_dir)),
                patch("mclab.sim.logging.datetime", FixedDatetime),
            ):
                first = create_output_path("lab01_msd")
                second = create_output_path("lab01_msd")

            self.assertEqual(first.name, "20260627_205000_lab01_msd")
            self.assertEqual(second.name, "20260627_205000_lab01_msd_001")
            self.assertTrue((first / "plots").is_dir())
            self.assertTrue((second / "plots").is_dir())

    def test_run_logger_writes_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = RunLogger(
                "lab01_msd",
                {"model_path": "models/lab01_msd/scene.xml", "mass": 1.0},
                config_path="configs/lab01_msd/default.yaml",
                output_dir=Path(temp_dir) / "run",
            )
            logger.record(time=0.0, position=0.1)
            output = logger.save_with_artifacts(
                summary={"max_position": 0.1, "settling_time": None, "interaction_events": 3},
                notes="# Lab01\nCheck position.",
                interaction_events=[
                    {
                        "time": 0.01,
                        "kind": "slider",
                        "name": "stiffness",
                        "label": "Stiffness [N/m]",
                        "value": 80.0,
                    },
                    {
                        "time": 0.015,
                        "kind": "preset",
                        "name": "stiff_spring",
                        "label": "Stiff spring",
                        "value": {
                            "purpose": "Higher restoring force and frequency.",
                            "values": {"damping": 1.0, "stiffness": 90.0},
                        },
                    },
                    {
                        "time": 0.02,
                        "kind": "marker",
                        "name": "observation",
                        "label": "Mark observation",
                        "value": {
                            "question": "Question: Which slider change made the response easiest to explain?",
                            "prediction": "Higher stiffness should create a sharper force peak.",
                            "outcome": "Matched",
                            "evidence_prompt": "Evidence to capture: position, force, and total energy.",
                            "challenge_proof": "review-ready; compare the saved observation with plots after the run.",
                            "note": (
                                "Higher stiffness made the force spike easier to see.; "
                                "Energy: 0.125; Changed values: Stiffness=80"
                            ),
                            "changed_sliders": {"stiffness": 80.0},
                            "sliders": {"stiffness": 80.0},
                            "status": {"energy": "0.125"},
                        },
                    },
                ],
                learner_snapshot={
                    "slider_values": {"stiffness": 80.0, "damping": 1.0},
                    "changed_sliders": {"stiffness": 80.0},
                    "live_status": {"energy": "0.125"},
                    "playback_speed": 1.5,
                    "extra_controls": {"joint_target_offset": 0.1},
                },
                learner_tuned_config={
                    "model_path": "models/lab01_msd/scene.xml",
                    "mass": 1.0,
                    "damping": 1.0,
                    "stiffness": 80.0,
                    "interaction": {"panel": False, "live_tuning": False},
                },
            )

            report = output / "report.html"
            self.assertTrue(report.exists())
            html = report.read_text(encoding="utf-8")
            self.assertIn("lab01_msd - default report", html)
            self.assertIn("Lab01 Baseline", html)
            self.assertIn("Course Position", html)
            self.assertIn("Learning path role", html)
            self.assertIn("Milestone", html)
            self.assertIn("1D Dynamics", html)
            self.assertIn("Learning path step", html)
            self.assertIn("1. Feel 1D physics", html)
            self.assertIn("Mass-spring-damper baseline response.", html)
            self.assertIn("Course Experience Coverage", html)
            self.assertIn("Experience coverage: 1/7 types tried", html)
            self.assertIn("Run next experience", html)
            self.assertIn("Next experience", html)
            self.assertIn("Hands-on controls", html)
            self.assertIn("hands-on viewer", html)
            self.assertIn("Next action", html)
            self.assertIn("Run an interactive viewer and use one button, slider, or preset.", html)
            self.assertIn(
                "At least one learner-control event plus one prediction-backed observation marker.",
                html,
            )
            self.assertIn("headless plot run", html)
            self.assertIn("A saved run report, priority plot, and worksheet for the baseline 1D plant.", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                "--viewer --realtime --pause-at-end --plot --plots essential --open-report",
                html,
            )
            self.assertIn("Intro basics", html)
            self.assertIn("Open all reports index", html)
            self.assertIn("Mission", html)
            self.assertIn("Playbook", html)
            self.assertIn("predict how quickly the mass returns", html)
            self.assertIn("Start steps", html)
            self.assertIn("Predict -&gt; Run scenario -&gt; Review priority plot and worksheet.", html)
            self.assertIn("Challenge", html)
            self.assertIn("verify it in the saved plot and worksheet", html)
            self.assertIn("Mission Evidence", html)
            self.assertIn("Mission proof status", html)
            self.assertIn("Next proof step", html)
            self.assertIn("Challenge Evidence", html)
            self.assertIn("Challenge proof status", html)
            self.assertIn("Needs plot evidence", html)
            self.assertIn("Priority plot and worksheet", html)
            self.assertIn("Try", html)
            self.assertIn("Change", html)
            self.assertIn("Prediction", html)
            self.assertIn("Question", html)
            self.assertIn("Before changing mass, damping, stiffness", html)
            self.assertIn("Viewer Legend", html)
            self.assertIn("Gray marker", html)
            self.assertIn("Green marker", html)
            self.assertIn(
                "What baseline motion should later damping and stiffness cases be compared against?",
                html,
            )
            self.assertIn("mass, damping, stiffness", html)
            self.assertIn("Next Actions", html)
            self.assertIn("Use these shortcuts right after reading this report.", html)
            self.assertIn("Review saved evidence", html)
            self.assertIn("Open raw artifacts", html)
            self.assertIn("Open output folder", html)
            self.assertIn("Replay tuned values", html)
            self.assertIn("Try next: Lab01 Underdamped", html)
            self.assertIn("Done when", html)
            self.assertIn("report.html, priority plot, and worksheet.md are saved.", html)
            self.assertIn("Controls:", html)
            self.assertIn("Pull/Push buttons and A/D keys", html)
            self.assertIn("Compare batch: Lab01 mass-spring-damper comparison", html)
            self.assertIn("Reproduce This Run", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --viewer",
                html,
            )
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot",
                html,
            )
            self.assertIn("Comparison Batch", html)
            self.assertIn("python -m mclab batch lab01_msd_compare --open-report", html)
            self.assertIn("Control Surface", html)
            self.assertIn("Viewer UI", html)
            self.assertIn("MuJoCo side panels are hidden", html)
            self.assertIn("Auto run", html)
            self.assertIn("Edit YAML or use Config Highlights before rerunning", html)
            self.assertIn("Config Highlights", html)
            self.assertIn("force_input.magnitude", html)
            self.assertIn("stiffness", html)
            self.assertIn("Result Check", html)
            self.assertIn("Data saved", html)
            self.assertIn("Learner actions", html)
            self.assertIn("max_position", html)
            self.assertIn("n/a", html)
            self.assertIn("Learner Action Summary", html)
            self.assertIn("Actions recorded", html)
            self.assertIn("Hands-on activity mix", html)
            self.assertIn("Control types used", html)
            self.assertIn("slider -&gt; preset -&gt; marker", html)
            self.assertIn("Activity path", html)
            self.assertIn(
                "slider: Stiffness [N/m] -&gt; preset: Stiff spring -&gt; observation: Mark observation",
                html,
            )
            self.assertIn("Interaction variety", html)
            self.assertIn("2/2 control families", html)
            self.assertIn("Ready: compare this interaction mix against plots and the worksheet.", html)
            self.assertIn("Latest slider values", html)
            self.assertIn("Preset choices", html)
            self.assertIn("Stiff spring", html)
            self.assertIn("Higher restoring force and frequency.", html)
            self.assertIn("90", html)
            self.assertIn("Learner Snapshot", html)
            self.assertIn("Changed slider values", html)
            self.assertIn("Final slider values", html)
            self.assertIn("Final live status", html)
            self.assertIn("Final control state", html)
            self.assertIn("Playback speed", html)
            self.assertIn("joint_target_offset", html)
            self.assertIn("Replay Tuned Config", html)
            self.assertIn("Regenerate tuned artifacts", html)
            self.assertIn("Watch tuned replay", html)
            self.assertIn("Learner Worksheet", html)
            self.assertIn("Open worksheet.md", html)
            self.assertIn("Observation Timeline", html)
            self.assertIn("1 observation shown in time order.", html)
            self.assertIn("<td>Observation 1</td>", html)
            self.assertIn("<td>0.02</td>", html)
            self.assertIn("<th>Challenge proof</th>", html)
            self.assertIn("<th>Note evidence</th>", html)
            self.assertIn("Observation Markers", html)
            self.assertIn("1 marked observation saved.", html)
            self.assertIn("Review prompt", html)
            self.assertIn("1 learning question, 1 prediction, 1 outcome, and 1 learner note were saved.", html)
            self.assertIn("Prediction Review", html)
            self.assertIn("Predictions saved", html)
            self.assertIn("Observation notes", html)
            self.assertIn("Latest observation", html)
            self.assertIn("Latest outcome", html)
            self.assertIn("Matched", html)
            self.assertIn("Evidence to compare", html)
            self.assertIn("Evidence Review Cue", html)
            self.assertIn("Review-ready pairs", html)
            self.assertIn("Prediction-only markers", html)
            self.assertIn("Observation-only markers", html)
            self.assertIn("Outcome judgments", html)
            self.assertIn("Decide whether each prediction matched, partially matched, or surprised you.", html)
            self.assertIn("Latest prediction:", html)
            self.assertIn("Latest note:", html)
            self.assertIn("Latest note evidence", html)
            self.assertIn("Which slider change made the response easiest to explain?", html)
            self.assertIn("Prediction", html)
            self.assertIn("Higher stiffness should create a sharper force peak.", html)
            self.assertIn("Evidence prompt", html)
            self.assertIn("position, force, and total energy", html)
            self.assertIn("Challenge proof", html)
            self.assertIn("review-ready; compare the saved observation with plots after the run.", html)
            self.assertIn("Higher stiffness made the force spike easier to see.", html)
            self.assertIn("Learner note evidence", html)
            self.assertIn("<li>Energy: 0.125</li>", html)
            self.assertIn("<li>Changed values: Stiffness=80</li>", html)
            self.assertIn("Changed sliders", html)
            self.assertIn("Sliders", html)
            self.assertIn("Live status", html)
            self.assertIn("Interaction Log", html)
            self.assertIn("Stiffness [N/m]", html)
            self.assertIn("Mark observation", html)
            self.assertIn("0.125", html)
            self.assertIn("interaction_events.json", html)
            self.assertIn("learner_snapshot.json", html)
            self.assertIn("learner_tuned_config.yaml", html)
            self.assertIn('<a href="./">Open output folder</a>', html)

            worksheet = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("## Course Position", worksheet)
            self.assertIn("- Milestone: 1D Dynamics", worksheet)
            self.assertIn("- Learning path step: 1. Feel 1D physics", worksheet)
            self.assertIn("- Step focus: Mass-spring-damper baseline response.", worksheet)
            self.assertIn("## Course Experience Coverage", worksheet)
            self.assertIn("- Summary: Experience coverage: 1/7 types tried", worksheet)
            self.assertIn("- Next experience: Hands-on controls", worksheet)
            self.assertIn("- Next mode: hands-on viewer", worksheet)
            self.assertIn(
                "- Next action: Run an interactive viewer and use one button, slider, or preset.",
                worksheet,
            )
            self.assertIn(
                "- Evidence needed: At least one learner-control event plus one prediction-backed observation marker.",
                worksheet,
            )
            self.assertIn(
                "- Next command: python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                "--viewer --realtime --pause-at-end --plot --plots essential --open-report",
                worksheet,
            )
            self.assertIn("  - Intro basics: Done", worksheet)
            self.assertIn(
                "mode: headless plot run; focus: Run Lab01 Mass-Spring-Damper - Auto demo.; "
                "evidence: A saved run report, priority plot, and worksheet for the baseline 1D plant.",
                worksheet,
            )
            self.assertIn("  - Hands-on controls: Next", worksheet)
            self.assertIn(
                "mode: hands-on viewer; focus: Run an interactive viewer and use one button, slider, or preset.; "
                "evidence: At least one learner-control event plus one prediction-backed observation marker.",
                worksheet,
            )
            self.assertIn("worksheet.md", html)
            self.assertIn("Check position.", html)
            self.assertIn("config.yaml", html)
            worksheet = output / "worksheet.md"
            self.assertTrue(worksheet.exists())
            worksheet_text = worksheet.read_text(encoding="utf-8")
            self.assertIn("# MCLab Learner Worksheet", worksheet_text)
            self.assertIn("## Learning Guide", worksheet_text)
            self.assertIn("- Done when: report.html, priority plot, and worksheet.md are saved.", worksheet_text)
            self.assertIn("- Mission:", worksheet_text)
            self.assertIn("- Playbook:", worksheet_text)
            self.assertIn("review the saved plot and worksheet", worksheet_text)
            self.assertIn("- Start steps: Predict -> Run scenario -> Review priority plot and worksheet.", worksheet_text)
            self.assertIn("- Challenge:", worksheet_text)
            self.assertIn("verify it in the saved plot and worksheet", worksheet_text)
            self.assertIn("## Mission Evidence", worksheet_text)
            self.assertIn("- Next proof step:", worksheet_text)
            self.assertIn("## Challenge Evidence", worksheet_text)
            self.assertIn("- Challenge status: Needs plot evidence", worksheet_text)
            self.assertIn("- Proof source: Priority plot and worksheet", worksheet_text)
            self.assertIn("## Key Parameters", worksheet_text)
            self.assertIn("## Observation Timeline", worksheet_text)
            self.assertIn(
                "- Observation 1 at 0.02 s: Prediction: Higher stiffness should create a sharper force peak.; "
                "Outcome: Matched; Note evidence: Higher stiffness made the force spike easier to see. "
                "\\| Energy: 0.125 \\| Changed values: Stiffness=80; "
                "Challenge proof: review-ready; compare the saved observation with plots after the run.; "
                "Status: energy=0.125",
                worksheet_text,
            )
            self.assertIn("## Observation Markers", worksheet_text)
            self.assertIn("### Evidence Review Cue", worksheet_text)
            self.assertIn("- Review-ready pairs: 1", worksheet_text)
            self.assertIn("- Learner controls: 2", worksheet_text)
            self.assertIn(
                "- Next review step: Decide whether each prediction matched, partially matched, or surprised you.",
                worksheet_text,
            )
            self.assertIn("Higher stiffness should create a sharper force peak.", worksheet_text)
            self.assertIn("Prediction outcome: Matched", worksheet_text)
            self.assertIn(
                "- Challenge proof: review-ready; compare the saved observation with plots after the run.",
                worksheet_text,
            )
            self.assertIn("- Learner note evidence:", worksheet_text)
            self.assertIn("  - Energy: 0.125", worksheet_text)
            self.assertIn("  - Changed values: Stiffness=80", worksheet_text)
            self.assertIn("Live status", worksheet_text)
            self.assertIn("energy: 0.125", worksheet_text)
            self.assertIn("## Review Checklist", worksheet_text)
            self.assertIn("- [ ] Compare the latest prediction with the plots in report.html.", worksheet_text)
            self.assertIn("## Hands-on Activity Mix", worksheet_text)
            self.assertIn(
                "- Activity path: slider: Stiffness [N/m] -> preset: Stiff spring -> observation: Mark observation",
                worksheet_text,
            )
            self.assertIn("- Interaction variety: 2/2 control families", worksheet_text)
            self.assertIn(
                "- Next activity step: Ready: compare this interaction mix against plots and the worksheet.",
                worksheet_text,
            )
            self.assertIn("Control coverage checklist:", worksheet_text)
            self.assertIn("- [x] Try one Quick preset to compare a named parameter regime. (1 recorded)", worksheet_text)
            self.assertIn(
                "- [x] Move one live slider to test a smaller parameter change. (1 recorded)",
                worksheet_text,
            )
            self.assertIn("- [x] Save one Mark observation with prediction and note. (1 recorded)", worksheet_text)
            self.assertNotIn("Outcome review pending", worksheet_text)
            self.assertIn("## Suggested Next Experiments", worksheet_text)
            self.assertIn("### Lab01 Underdamped", worksheet_text)
            self.assertIn("Reason: See what changes when damping is too low.", worksheet_text)
            self.assertIn("- Start steps: Predict -> Run scenario -> Compare priority plot and worksheet.", worksheet_text)
            self.assertIn("- Challenge: Explain how damping, stiffness, initial_position", worksheet_text)
            self.assertIn(
                "Command: python -m mclab run lab01 --config configs/lab01_msd/underdamped.yaml",
                worksheet_text,
            )
            self.assertIn("## Comparison Batch", worksheet_text)
            self.assertIn("Command: python -m mclab batch lab01_msd_compare --open-report", worksheet_text)
            self.assertIn("- report.html", worksheet_text)
            events = json.loads((output / "interaction_events.json").read_text(encoding="utf-8"))
            self.assertEqual(events[0]["name"], "stiffness")
            snapshot = json.loads((output / "learner_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["changed_sliders"], {"stiffness": 80.0})
            self.assertEqual(snapshot["playback_speed"], 1.5)
            tuned_config = (output / "learner_tuned_config.yaml").read_text(encoding="utf-8")
            self.assertIn("stiffness: 80.0", tuned_config)
            self.assertIn("live_tuning: False", tuned_config)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["config_path"], "configs/lab01_msd/default.yaml")
            self.assertEqual(summary["config_name"], "default")

    def test_run_report_renders_observation_timeline_in_time_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/interactive_pull.yaml",
                        "config_name": "interactive_pull",
                    }
                ),
                encoding="utf-8",
            )
            (output / "config.yaml").write_text("interaction:\n  panel: true\n", encoding="utf-8")
            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "time": 0.4,
                            "value": {
                                "prediction": "First push should move right.",
                                "note": "Live: position=0.1; Changed values: damping=2",
                            },
                        },
                        {
                            "kind": "marker",
                            "name": "observation",
                            "time": 1.2,
                            "value": {
                                "prediction": "Higher damping should settle sooner.",
                                "outcome": "Partly matched",
                                "note": "The second response was smaller.",
                                "status": {"Position [m]": "0.200", "Energy [J]": "0.030"},
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")

            self.assertIn("Observation Timeline", html)
            self.assertIn("2 observations shown in time order.", html)
            self.assertLess(html.index("<td>Observation 1</td>"), html.index("<td>Observation 2</td>"))
            self.assertIn("Live: position=0.1 | Changed values: damping=2", html)
            self.assertIn("Position [m]=0.200, Energy [J]=0.030", html)
            self.assertIn("## Observation Timeline", worksheet_text)
            self.assertIn(
                "- Observation 1 at 0.4 s: Prediction: First push should move right.; "
                "Outcome: missing; Note evidence: Live: position=0.1 \\| Changed values: damping=2",
                worksheet_text,
            )
            self.assertIn(
                "- Observation 2 at 1.2 s: Prediction: Higher damping should settle sooner.; "
                "Outcome: Partly matched; Note evidence: The second response was smaller.; "
                "Status: Position [m]=0.200, Energy [J]=0.030",
                worksheet_text,
            )

    def test_worksheet_control_coverage_requires_prediction_and_note_on_same_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/interactive_pull.yaml",
                        "config_name": "interactive_pull",
                    }
                ),
                encoding="utf-8",
            )
            (output / "config.yaml").write_text("interaction:\n  panel: true\n", encoding="utf-8")
            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"prediction": "More damping should settle faster."},
                        },
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"note": "The trace settled faster after the slider moved."},
                        },
                    ]
                ),
                encoding="utf-8",
            )

            write_run_report(output)

            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("- Observation markers: 2", worksheet_text)
            self.assertIn("- Predictions: 1", worksheet_text)
            self.assertIn("- Learner notes: 1", worksheet_text)
            self.assertIn("- [ ] Save one Mark observation with prediction and note. (0 recorded)", worksheet_text)

    def test_activity_mix_uses_configured_control_families(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab04_panda",
                        "config_path": "configs/lab04_panda/interactive_joint_hold.yaml",
                        "config_name": "interactive_joint_hold",
                    }
                ),
                encoding="utf-8",
            )
            (output / "config.yaml").write_text(
                (
                    "interaction:\n"
                    "  panel: true\n"
                    "  target_nudge: true\n"
                ),
                encoding="utf-8",
            )
            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "button", "name": "joint_target_offset", "label": "Target +", "value": 0.05},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "A positive nudge should move the joint target.",
                                "note": "The joint target offset increased.",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")

            self.assertIn("1/1 control families", html)
            self.assertIn("Counts as control", html)
            self.assertIn(
                "experiment buttons (Joint Target -  A / Left / Joint Target +  D / Right); "
                "view/evidence helpers",
                html,
            )
            self.assertNotIn("Move one live slider to test a smaller parameter change.", html)
            self.assertNotIn("Try a Quick preset to compare a named parameter regime.", html)
            self.assertIn("- Interaction variety: 1/1 control families", worksheet_text)
            self.assertNotIn("- [ ] Move one live slider", worksheet_text)
            self.assertIn(
                "- [x] Use target nudge buttons to move the commanded target. (1 recorded)",
                worksheet_text,
            )
            self.assertIn("- [x] Save one Mark observation with prediction and note. (1 recorded)", worksheet_text)
            self.assertNotIn("- [ ] Try one Quick preset", worksheet_text)

    def test_worksheet_review_checklist_flags_missing_prediction_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            (output / "config.yaml").write_text("mass: 1.0\n", encoding="utf-8")
            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "time": 0.2,
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "More damping should settle faster.",
                                "note": "The trace settled faster.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            write_run_report(output)

            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("## Mission Evidence", worksheet_text)
            self.assertIn("- Status: Outcome review pending", worksheet_text)
            self.assertIn("- Next proof step: Choose Matched, Partly matched, or Surprised", worksheet_text)
            self.assertIn("- Predictions: 1", worksheet_text)
            self.assertIn("- Prediction outcomes: 0", worksheet_text)
            self.assertIn(
                "- Outcome review pending: 1 prediction(s) still need Matched, Partly matched, or Surprised.",
                worksheet_text,
            )
            self.assertIn("- [ ] Mark one outcome for every prediction", worksheet_text)

    def test_run_report_points_to_relevant_comparison_batch(self) -> None:
        cases = [
            (
                {
                    "lab_name": "lab04_panda",
                    "config_path": "configs/lab04_panda/interactive_virtual_wall.yaml",
                    "config_name": "interactive_virtual_wall",
                },
                "python -m mclab batch lab04_wall_compare --open-report",
            ),
            (
                {
                    "lab_name": "lab04_panda",
                    "config_path": "configs/lab04_panda/cartesian_reach.yaml",
                    "config_name": "cartesian_reach",
                },
                "python -m mclab batch lab04_cartesian_compare --open-report",
            ),
            (
                {
                    "lab_name": "lab03_2dof",
                    "config_path": "configs/lab03_2dof/task_space_2dof.yaml",
                    "config_name": "task_space_2dof",
                },
                "python -m mclab batch lab03_2dof_compare --open-report",
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, (summary, command) in enumerate(cases):
                output = Path(temp_dir) / f"run_{index}"
                output.mkdir()
                (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
                (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

                html = write_run_report(output).read_text(encoding="utf-8")

                self.assertIn("Comparison Batch", html)
                self.assertIn(command, html)

    def test_interactive_run_report_shows_hands_on_evidence_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "interactive"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/interactive_pull.yaml",
                        "config_name": "interactive_pull",
                    }
                ),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Interactive\n", encoding="utf-8")

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Hands-on Evidence", html)
            self.assertIn("use at least one button, slider, or preset", html)
            self.assertIn("Needs observation", html)
            self.assertIn("write a prediction and note", html)
            self.assertIn(
                "Repeat this hands-on step, use experiment buttons (Pull/Push buttons and A/D keys), "
                "live sliders, or Quick presets at least once",
                html,
            )

            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "label": "Mark observation",
                            "value": {"note": "The mass settled after the pulse."},
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Needs prediction", html)
            self.assertIn("fill the Prediction field", html)
            self.assertIn("Observation markers", html)
            self.assertIn("Evidence Review Cue", html)
            self.assertIn("Observation-only markers", html)
            self.assertIn("Learner controls", html)
            self.assertIn(
                "Write a prediction, use experiment buttons (Pull/Push buttons and A/D keys), "
                "live sliders, or Quick presets, then mark the observation again.",
                html,
            )

            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "label": "Mark observation",
                            "value": {
                                "prediction": "More damping should settle faster.",
                                "note": "The mass settled after the pulse.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Needs learner control", html)
            self.assertIn(
                "Use experiment buttons (Pull/Push buttons and A/D keys), live sliders, or Quick presets, "
                "then mark another observation with prediction and note.",
                html,
            )
            self.assertIn(
                "Use experiment buttons (Pull/Push buttons and A/D keys), live sliders, or Quick presets, "
                "then mark the observation.",
                html,
            )
            self.assertIn(
                "Repeat this hands-on step and use experiment buttons (Pull/Push buttons and A/D keys), "
                "live sliders, or Quick presets at least once",
                html,
            )

            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "button", "name": "push_right", "label": "Push Right", "value": 12.0},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "label": "Mark observation",
                            "value": {
                                "prediction": "More damping should settle faster.",
                                "note": "The mass settled after the pulse.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Done for learning path", html)
            self.assertIn("Judge prediction outcome", html)
            self.assertIn("mark whether the prediction matched", html)

            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "button", "name": "push_right", "label": "Push Right", "value": 12.0},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "label": "Mark observation",
                            "value": {
                                "prediction": "More damping should settle faster.",
                                "outcome": "Partly matched",
                                "note": "The mass settled after the pulse.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Done for learning path", html)
            self.assertIn("one learner control plus a Mark observation with prediction and note", html)
            self.assertIn("Prediction outcome", html)
            self.assertIn("Partly matched", html)

    def test_run_report_includes_saved_plot_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            (output / "plots").mkdir(parents=True)
            (output / "summary.json").write_text('{"lab_name": "demo"}', encoding="utf-8")
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")
            (output / "plots" / "position.png").write_bytes(b"fake-png")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("plots/position.png", html)
            self.assertIn("position.png", html)
            self.assertIn("Next Actions", html)
            self.assertIn("Open the key plot", html)
            self.assertIn("Priority plot", html)
            self.assertIn("Plot Guide", html)
            self.assertIn("Position", html)
            self.assertIn("steady-state error", html)
            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("## Plot Review", worksheet_text)
            self.assertIn("Priority plot: plots/position.png", worksheet_text)
            self.assertIn("Read first: Position", worksheet_text)
            self.assertIn("Compare actual motion against target", worksheet_text)

    def test_run_report_renders_configured_presets_as_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                '{"lab_name": "lab02_pid", "config_name": "interactive_disturbance"}',
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")
            (output / "config.yaml").write_text(
                (
                    "model_path: models/lab02_pid/scene.xml\n"
                    "interaction:\n"
                    "  panel: true\n"
                    "  live_tuning: true\n"
                    "  tuning_presets:\n"
                    "    - label: Damped PD\n"
                    "      purpose: Show damping reducing overshoot.\n"
                    "      values:\n"
                    "        kp: 60.0\n"
                    "        kd: 16.0\n"
                    "    - label: Aggressive PID\n"
                    "      values:\n"
                    "        kp: 120.0\n"
                    "        output_limit: 120.0\n"
                ),
                encoding="utf-8",
            )
            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "time": 0.5,
                            "kind": "preset",
                            "name": "aggressive_pid",
                            "label": "Aggressive PID",
                            "value": {
                                "purpose": "Faster target chase with more effort.",
                                "values": {"kp": 120.0, "output_limit": 120.0},
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Configured Presets", html)
            self.assertIn("Control Surface", html)
            self.assertIn("Viewer UI", html)
            self.assertIn("MuJoCo side panels are hidden", html)
            self.assertIn("MCLab Interaction window", html)
            self.assertIn("Sliders with Changed values summary", html)
            self.assertIn("Prediction, outcome, Use live status, Mark observation", html)
            self.assertIn("Damped PD", html)
            self.assertIn("Show damping reducing overshoot.", html)
            self.assertIn("Aggressive PID", html)
            self.assertIn("Compare presets in order: Damped PD -&gt; Aggressive PID.", html)
            self.assertIn("Preset comparison progress", html)
            self.assertIn("Distinct presets tried", html)
            self.assertIn("<strong>1/2</strong>", html)
            self.assertIn("Try Damped PD", html)
            self.assertIn("Needs another preset", html)
            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("## Preset Comparison", worksheet_text)
            self.assertIn("<span>Preset order</span>", html)
            self.assertIn("<strong>Damped PD -&gt; Aggressive PID</strong>", html)
            self.assertIn("Preset order: Damped PD -> Aggressive PID", worksheet_text)
            self.assertIn("Distinct presets tried: 1/2", worksheet_text)
            self.assertIn("Next: Try Damped PD, watch live status, then mark one observation.", worksheet_text)
            self.assertIn("<span>kp</span>", html)
            self.assertIn("<strong>60</strong>", html)
            self.assertNotIn("interaction.tuning_presets", html)

    def test_run_report_renders_required_preset_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                '{"lab_name": "lab04_panda", "config_name": "interactive_virtual_wall"}',
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")
            (output / "config.yaml").write_text(
                (
                    "model_path: third_party/mujoco_menagerie/franka_emika_panda/scene.xml\n"
                    "interaction:\n"
                    "  panel: true\n"
                    "  live_tuning: true\n"
                    "  tuning_presets:\n"
                    "    - label: Soft wall\n"
                    "      values:\n"
                    "        target_x: 0.59\n"
                    "    - label: Stiff wall\n"
                    "      values:\n"
                    "        target_x: 0.62\n"
                    "    - label: Close wall\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.64\n"
                    "    - label: Back away\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.52\n"
                    "    - label: Re-enter wall\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.65\n"
                ),
                encoding="utf-8",
            )
            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"time": 0.5, "kind": "preset", "name": "soft_wall", "label": "Soft wall"},
                        {
                            "time": 1.0,
                            "kind": "preset",
                            "name": "close_wall",
                            "label": "Close wall",
                            "value": {"required": True, "values": {"target_x": 0.64}},
                        },
                        {
                            "time": 1.5,
                            "kind": "marker",
                            "name": "observation",
                            "label": "Mark observation",
                            "value": {
                                "prediction": "Back away should release contact.",
                                "outcome": "Matched",
                                "note": "Contact remained until backing away.",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn(
                "Predict -&gt; Run viewer -&gt; try required presets Close wall -&gt; Back away -&gt; Re-enter wall -&gt; Mark observation.",
                html,
            )
            self.assertIn("Required evidence: Close wall -&gt; Back away -&gt; Re-enter wall.", html)
            self.assertIn("Required evidence preset.", html)
            self.assertIn("Required presets", html)
            self.assertIn("Required presets tried", html)
            self.assertIn("<strong>1/3</strong>", html)
            self.assertIn("Try required preset Back away", html)
            self.assertIn("Needs required preset", html)
            self.assertIn("<span>Status</span><strong>Needs required preset Back away</strong>", html)
            self.assertIn("<span>Next proof step</span><strong>Try required preset Back away", html)
            self.assertIn("<span>Required evidence</span>", html)
            self.assertIn("<strong>yes</strong>", html)
            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn(
                "- Start steps: Predict -> Run viewer -> try required presets Close wall -> Back away -> "
                "Re-enter wall -> Mark observation.",
                worksheet_text,
            )
            self.assertIn("- Status: Needs required preset Back away", worksheet_text)
            self.assertIn("- Required presets tried: 1/3", worksheet_text)
            self.assertIn("- [ ] Try required preset Back away, watch live status, then mark one observation.", worksheet_text)
            self.assertIn("Required presets: Close wall -> Back away -> Re-enter wall", worksheet_text)
            self.assertIn("Required presets tried: 1/3", worksheet_text)
            self.assertIn(
                "Next: Try required preset Back away, watch live status, then mark one observation.",
                worksheet_text,
            )

    def test_worksheet_checklist_names_required_preset_before_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                '{"lab_name": "lab04_panda", "config_name": "interactive_virtual_wall"}',
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")
            (output / "config.yaml").write_text(
                (
                    "model_path: third_party/mujoco_menagerie/franka_emika_panda/scene.xml\n"
                    "interaction:\n"
                    "  panel: true\n"
                    "  live_tuning: true\n"
                    "  tuning_presets:\n"
                    "    - label: Close wall\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.64\n"
                    "    - label: Back away\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.52\n"
                    "    - label: Re-enter wall\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.65\n"
                ),
                encoding="utf-8",
            )
            (output / "interaction_events.json").write_text("[]", encoding="utf-8")

            write_run_report(output)

            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("- Required presets tried: 0/3", worksheet_text)
            self.assertIn(
                "- [ ] Try required preset Close wall, watch live status, then mark one observation.",
                worksheet_text,
            )
            self.assertIn("- [ ] Save one observation marker with a prediction and note.", worksheet_text)

    def test_auto_run_worksheet_uses_plot_review_instead_of_marker_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab03_2dof",
                        "config_path": "configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml",
                        "config_name": "condition_aware_dls_adaptive_speed_retarget_2dof",
                        "samples": 10,
                        "duration": 0.02,
                    }
                ),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Auto run\n", encoding="utf-8")
            (output / "config.yaml").write_text(
                (
                    "model_path: models/lab03_2dof/two_link.xml\n"
                    "mode: condition_aware_dls\n"
                    "tracking_controller:\n"
                    "  max_task_speed_schedule:\n"
                    "    - time: 0.0\n"
                    "      speed: 0.62\n"
                ),
                encoding="utf-8",
            )
            (output / "interaction_events.json").write_text("[]", encoding="utf-8")

            write_run_report(output)

            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("- No observation markers saved yet.", worksheet_text)
            self.assertIn(
                "- Next: use the Plot Review and Challenge Evidence sections for this auto-run scenario.",
                worksheet_text,
            )
            self.assertIn("- Hands-on marker evidence comes from interactive scenarios", worksheet_text)
            self.assertIn("- [ ] Answer the Prediction prompt before reading the plots.", worksheet_text)
            self.assertIn(
                "- [ ] Use Plot Review and Challenge Evidence to decide whether the result matched your expectation.",
                worksheet_text,
            )
            self.assertIn(
                "- [ ] Run one Suggested Next Experiment or the Comparison Batch for a controlled comparison.",
                worksheet_text,
            )
            self.assertNotIn("- [ ] Save one observation marker with a prediction and note.", worksheet_text)
            self.assertNotIn("- [ ] Capture one live status or note before moving to the next scenario.", worksheet_text)
            self.assertNotIn("press Mark observation", worksheet_text)

    def test_run_report_requires_preset_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                '{"lab_name": "lab04_panda", "config_name": "interactive_virtual_wall"}',
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")
            (output / "config.yaml").write_text(
                (
                    "interaction:\n"
                    "  panel: true\n"
                    "  live_tuning: true\n"
                    "  tuning_presets:\n"
                    "    - label: Close wall\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.64\n"
                    "    - label: Back away\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.52\n"
                    "    - label: Re-enter wall\n"
                    "      required: true\n"
                    "      values:\n"
                    "        target_x: 0.65\n"
                ),
                encoding="utf-8",
            )
            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "re-enter_wall", "label": "Re-enter wall"},
                        {"kind": "preset", "name": "close_wall", "label": "Close wall"},
                        {"kind": "preset", "name": "back_away", "label": "Back away"},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Re-entering should create a second contact.",
                                "outcome": "Matched",
                                "note": "The first Re-enter click was out of order.",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")

            self.assertIn("<span>Status</span><strong>Needs required preset Re-enter wall</strong>", html)
            self.assertIn("<span>Required presets tried</span><strong>2/3</strong>", html)
            self.assertIn("Try required preset Re-enter wall", html)
            self.assertIn("- Status: Needs required preset Re-enter wall", worksheet_text)
            self.assertIn("- Required presets tried: 2/3", worksheet_text)

    def test_run_report_suggests_next_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab02_pid",
                        "config_path": "configs/lab02_pid/p_high_gain.yaml",
                        "config_name": "p_high_gain",
                    }
                ),
                encoding="utf-8",
            )
            (output / "config.yaml").write_text(
                (ROOT / "configs/lab02_pid/p_high_gain.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Suggested Next Runs", html)
            self.assertIn("Lab02 PD Damping", html)
            self.assertIn("configs/lab02_pid/pd_damped.yaml", html)
            self.assertIn("Use derivative action to calm overshoot.", html)
            self.assertIn("Prediction:", html)
            self.assertIn("Before changing controller.kp, controller.kd", html)
            self.assertIn("Question:", html)
            self.assertIn("Which gain change trades speed for overshoot or smoother force?", html)
            self.assertIn("Start steps:", html)
            self.assertIn("Predict -&gt; Run scenario -&gt; Compare priority plot and worksheet.", html)
            self.assertIn("Challenge:", html)
            self.assertIn("Explain how controller.kp, controller.kd should change Reduced overshoot", html)
            self.assertIn("Key changes:", html)
            self.assertIn("controller.kd", html)
            self.assertIn("0 -&gt; 18", html)
            self.assertIn("Lab02 Saturation", html)
            self.assertIn(
                "python -m mclab run lab02 --config configs/lab02_pid/pd_damped.yaml",
                html,
            )
            self.assertIn("--plots essential --open-report", html)

    def test_run_report_next_actions_use_correct_lab_for_panda_trajectory_configs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab04_panda",
                        "config_path": "configs/lab04_panda/joint_pd.yaml",
                        "config_name": "joint_pd",
                    }
                ),
                encoding="utf-8",
            )
            (output / "config.yaml").write_text(
                (ROOT / "configs/lab04_panda/joint_pd.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Try next: Lab04 Panda S-Curve Joint Path", html)
            self.assertIn(
                "python -m mclab run lab04 --config configs/lab04_panda/trajectory_tracking.yaml",
                html,
            )
            self.assertNotIn(
                "python -m mclab run lab03 --config configs/lab04_panda/trajectory_tracking.yaml",
                html,
            )

    def test_run_report_includes_domain_specific_result_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab03_2dof",
                        "config_path": "configs/lab03_2dof/dls_singularity_2dof.yaml",
                        "config_name": "dls_singularity_2dof",
                        "samples": 120,
                        "max_jacobian_condition": 150.0,
                        "min_manipulability": 0.01,
                        "max_dls_joint_speed": 4.2,
                        "max_abs_tau_cmd": 75.0,
                        "max_dls_condition_scale": 0.82,
                        "max_dls_damping": 0.21,
                        "max_abs_qdot": 0.01,
                        "max_settled_abs_qdot": 0.0001,
                        "max_joint_drift_norm": 0.004,
                        "duration": 30.0,
                        "max_wall_penetration_cm": 1.2,
                        "max_wall_retreat_cm": 0.5,
                        "first_target_wall_cross_time": 1.2,
                        "first_wall_contact_time": 1.4,
                        "first_wall_release_time": 2.8,
                        "first_target_wall_return_time": 3.0,
                        "peak_target_wall_gap_time": 1.6,
                        "peak_wall_penetration_time": 2.1,
                        "peak_wall_force_time": 2.2,
                        "peak_wall_damping_force_time": 1.8,
                        "peak_cartesian_error_time": 0.6,
                        "peak_hand_speed_time": 1.7,
                        "wall_contact_duration": 2.2,
                        "wall_contact_fraction": 0.44,
                        "target_past_wall_duration": 1.8,
                        "target_past_wall_fraction": 0.36,
                        "max_target_wall_gap_cm": 4.0,
                        "final_target_wall_gap_cm": -0.5,
                        "final_wall_phase": "Clear",
                        "max_abs_virtual_wall_force": 22.0,
                        "max_abs_virtual_wall_spring_force": 18.0,
                        "max_abs_virtual_wall_damping_force": 4.0,
                        "max_cartesian_error_cm": 1.6,
                        "max_hand_speed": 0.34,
                    }
                ),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Jacobian condition", html)
            self.assertIn("near-singular motion", html)
            self.assertIn("Manipulability", html)
            self.assertIn("DLS joint speed", html)
            self.assertIn("Condition-aware DLS", html)
            self.assertIn("Damping schedule reached", html)
            self.assertIn("30s stability hold", html)
            self.assertIn("Settled joint speed", html)
            self.assertIn("Joint drift stability", html)
            self.assertIn("Actuator effort", html)
            self.assertIn("Virtual wall contact", html)
            self.assertIn("Wall retreat", html)
            self.assertIn("Wall contact timing", html)
            self.assertIn("First contact at", html)
            self.assertIn("Target-wall command", html)
            self.assertIn("Target moved", html)
            self.assertIn("at 1.2 s", html)
            self.assertIn("final phase Clear", html)
            self.assertIn("Target backed away", html)
            self.assertIn("Wall contact release", html)
            self.assertIn("Wall force", html)
            self.assertIn("Wall force components", html)
            self.assertIn("Key Moments", html)
            self.assertIn("Target crosses wall", html)
            self.assertIn("First wall contact", html)
            self.assertIn("Deepest target-wall command", html)
            self.assertIn("Target backs away", html)
            self.assertIn("Peak wall penetration", html)
            self.assertIn("Peak wall force", html)
            self.assertIn("Peak damping force", html)
            self.assertIn("Peak hand speed", html)
            self.assertIn("Peak Cartesian error", html)
            self.assertIn("check-inspect", html)
            self.assertIn("check-observed", html)
            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("## Key Moments", worksheet_text)
            self.assertIn("Target crosses wall: time 1.2 s; Target past-wall duration [s]: 1.8.", worksheet_text)
            self.assertIn("First wall contact: time 1.4 s; Contact duration [s]: 2.2.", worksheet_text)
            self.assertIn("Deepest target-wall command: time 1.6 s; Target past wall [cm]: 4.", worksheet_text)
            self.assertIn("Peak wall penetration: time 2.1 s; Penetration [cm]: 1.2.", worksheet_text)
            self.assertIn("Peak wall force: time 2.2 s; Wall force: 22.", worksheet_text)
            self.assertIn("Peak damping force: time 1.8 s; Damping force: 4.", worksheet_text)
            self.assertIn("Wall contact release: time 2.8 s; Final phase: Clear.", worksheet_text)
            self.assertIn("Target backs away: time 3 s; Final target-wall [cm]: -0.5.", worksheet_text)
            self.assertIn("Peak hand speed: time 1.7 s; Hand speed [m/s]: 0.34.", worksheet_text)
            self.assertIn("Peak Cartesian error: time 0.6 s; Error [cm]: 1.6.", worksheet_text)

    def test_run_report_updates_parent_outputs_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_150117_lab01_msd"
            (output / "plots").mkdir(parents=True)
            (output / "plots" / "position.png").write_bytes(b"fake-png")
            (output / "plots" / "energy.png").write_bytes(b"fake-png")
            (output / "learner_tuned_config.yaml").write_text("interaction:\n  panel: false\n", encoding="utf-8")
            (output / "summary.json").write_text(
                (
                    '{"lab_name": "lab01_msd", "config_path": "configs/lab01_msd/default.yaml", '
                    '"config_name": "default", "samples": 10, "duration": 0.18, "max_abs_position": 0.24}'
                ),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            write_run_report(output)

            index = Path(temp_dir) / "index.html"
            self.assertTrue(index.exists())
            html = index.read_text(encoding="utf-8")
            self.assertIn("20260627_150117_lab01_msd/report.html", html)
            self.assertIn("lab01_msd", html)
            self.assertIn("Config", html)
            self.assertIn("Progress Snapshot", html)
            self.assertIn("Experience Coverage", html)
            self.assertIn("Experience coverage: 1/7 types tried", html)
            self.assertIn("Done: Intro basics", html)
            self.assertIn("Missing: Hands-on controls", html)
            self.assertIn("<strong>Intro basics</strong>", html)
            self.assertIn('<span class="status">Done</span>', html)
            self.assertIn("<strong>Hands-on controls</strong>", html)
            self.assertIn('<span class="status">Next</span>', html)
            self.assertIn("Next: Run an interactive viewer and use one button, slider, or preset.", html)
            self.assertIn("Run next: Hands-on controls", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                "--viewer --realtime --pause-at-end --plot --plots essential --open-report",
                html,
            )
            self.assertIn("Learning Path", html)
            self.assertIn("1/12 steps complete", html)
            self.assertIn(
                "Milestones: 1D Dynamics 1/2; PID Control 0/2; 2DOF Control 0/4; "
                "Panda Manipulation 0/3; Course Compare 0/1. Next milestone: 1D Dynamics.",
                html,
            )
            self.assertIn("Next action: run lab01", html)
            self.assertIn("Done when: use at least one button, slider, or preset", html)
            self.assertIn("1. Feel 1D physics", html)
            self.assertIn("2. Disturb and tune", html)
            self.assertIn("7. Handle singularity", html)
            self.assertIn("8. Compare DLS retarget", html)
            self.assertIn(
                "<strong>Done when:</strong> the run report, priority plot, and worksheet are saved.",
                html,
            )
            self.assertIn(
                "<strong>Start steps:</strong> Predict -&gt; Run scenario -&gt; Review priority plot and worksheet.",
                html,
            )
            self.assertIn(
                "<strong>Done when:</strong> use at least one button, slider, or preset, then save one Mark observation "
                "with a Prediction and note; add the outcome during review.",
                html,
            )
            self.assertIn(
                "<strong>Start steps:</strong> Predict -&gt; Run viewer -&gt; try presets Lightly damped -&gt; Heavy damping -&gt; Stiff spring -&gt; Mark observation.",
                html,
            )
            self.assertIn(
                "<strong>Counts as control:</strong> experiment buttons (Pull/Push buttons and A/D keys), "
                "live sliders, Quick presets; "
                "view/evidence helpers such as Pause, Playback speed, and Use live status do not count.",
                html,
            )
            self.assertIn(
                "<strong>Start steps:</strong> Predict -&gt; Run viewer -&gt; try required presets Close wall -&gt; Back away -&gt; Re-enter wall -&gt; Mark observation.",
                html,
            )
            self.assertIn("configs/lab03_2dof/condition_aware_dls_2dof.yaml", html)
            self.assertIn("<strong>Predict:</strong>", html)
            self.assertIn("<strong>Watch:</strong>", html)
            self.assertNotIn("predict how How", html)
            self.assertIn("Not run yet", html)
            self.assertIn("Run this step", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml",
                html,
            )
            self.assertIn("--plots essential --open-report", html)
            self.assertIn("Repeat this step", html)
            self.assertIn("Lab01", html)
            self.assertIn("1 saved run", html)
            self.assertIn("Lesson", html)
            self.assertIn("Next", html)
            self.assertIn("Evidence", html)
            self.assertIn("<th>Worksheet</th>", html)
            self.assertIn("20260627_150117_lab01_msd/worksheet.md", html)
            self.assertIn("Worksheet", html)
            self.assertIn("<th>Folder</th>", html)
            self.assertIn('href="20260627_150117_lab01_msd/">Folder</a>', html)
            self.assertIn("<th>Replay</th>", html)
            self.assertIn("20260627_150117_lab01_msd/learner_tuned_config.yaml", html)
            self.assertIn("Tuned config", html)
            self.assertIn("Plots", html)
            self.assertIn("<th>Plot review</th>", html)
            self.assertIn("20260627_150117_lab01_msd/plots/position.png", html)
            self.assertIn("20260627_150117_lab01_msd/plots/energy.png", html)
            self.assertIn("Position", html)
            self.assertIn("Energy", html)
            self.assertIn("Plot review: Position - Compare actual motion against target", html)
            self.assertIn("Lab01 Baseline", html)
            self.assertIn("Run underdamped", html)
            self.assertIn("configs/lab01_msd/default.yaml", html)
            self.assertIn("Latest artifacts", html)
            self.assertIn(">Report</a>", html)
            self.assertIn(">Plot: Position</a>", html)
            self.assertIn(
                ">Plot: Position</a><a class=\"plot-chip\" "
                'href="20260627_150117_lab01_msd/">Folder</a><a class="plot-chip" '
                'href="20260627_150117_lab01_msd/learner_tuned_config.yaml">Replay tuned</a></div>'
                '<p class="muted">Plot review: Position - Compare actual motion against target',
                html,
            )
            self.assertIn(">Replay tuned</a>", html)
            self.assertIn("No markers", html)
            self.assertIn("max abs position", html)
            self.assertIn("0.24", html)

    def test_outputs_index_prioritizes_dls_plot_for_dls_learning_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260701_064136_lab03_2dof"
            plot_dir = output / "plots"
            plot_dir.mkdir(parents=True)
            (plot_dir / "error.png").write_bytes(b"fake-png")
            (plot_dir / "dls.png").write_bytes(b"fake-png")
            (plot_dir / "end_effector.png").write_bytes(b"fake-png")
            (output / "report.html").write_text("<html></html>", encoding="utf-8")
            (output / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab03_2dof",
                        "config_path": (
                            "configs/lab03_2dof/"
                            "condition_aware_dls_adaptive_speed_retarget_2dof.yaml"
                        ),
                        "config_name": "condition_aware_dls_adaptive_speed_retarget_2dof",
                        "samples": 10,
                        "duration": 1.0,
                    }
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn(
                f'href="{output.name}/plots/dls.png">Plot: Damped Least Squares</a>',
                html,
            )
            self.assertNotIn(f'href="{output.name}/plots/error.png">Plot: Error</a>', html)
            self.assertIn(
                f'href="{output.name}/plots/dls.png">Plot: Damped Least Squares</a>'
                f'<a class="plot-chip" href="{output.name}/">Folder</a></div>'
                '<p class="muted">Plot review: Damped Least Squares - Compare task speed',
                html,
            )
            self.assertLess(
                html.index(f'href="{output.name}/plots/dls.png">Damped Least Squares</a>'),
                html.index(f'href="{output.name}/plots/error.png">Error</a>'),
            )

    def test_outputs_index_links_to_batch_index_when_no_run_report_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_151000_lab02_pid_compare"
            output.mkdir()
            (output / "comparison_plots").mkdir()
            (output / "comparison_plots" / "error_compare.png").write_bytes(b"fake-png")
            (output / "summary.json").write_text(
                (
                    '{"lab_name": "batch", "config_name": "lab02_pid_compare", '
                    '"samples": 9, "duration": ""}'
                ),
                encoding="utf-8",
            )
            (output / "index.html").write_text("<html>batch</html>", encoding="utf-8")

            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn("20260627_151000_lab02_pid_compare/index.html", html)
            self.assertIn("lab02_pid_compare", html)
            self.assertIn("Progress Snapshot", html)
            self.assertIn("Batches", html)
            self.assertIn("1 saved run", html)
            self.assertIn("python -m mclab batch lab02_pid_compare --open-report", html)
            self.assertIn("Next cue: Rerun the comparison batch to regenerate the worksheet.", html)
            self.assertIn("20260627_151000_lab02_pid_compare/comparison_plots/error_compare.png", html)
            self.assertIn("Plot review: Error - Check how quickly error shrinks", html)
            self.assertNotIn("Viewer Handoff</a>", html)

    def test_outputs_index_marks_all_batch_learning_path_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_151000_all_batches"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch_group",
                        "config_name": "all_batches",
                        "batch_name": "all",
                        "samples": 4,
                        "duration": "",
                    }
                ),
                encoding="utf-8",
            )
            (output / "report.html").write_text("<html>all batches</html>", encoding="utf-8")
            (output / "worksheet.md").write_text("# Course worksheet\n", encoding="utf-8")

            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn("Learning Path", html)
            self.assertIn("1/12 steps complete", html)
            self.assertIn("12. Compare the course", html)
            self.assertIn(
                "<strong>Done when:</strong> the course comparison report, worksheet, and linked batch Prediction Checks are saved.",
                html,
            )
            self.assertIn(
                "<strong>Start steps:</strong> Predict the strongest course-level effect -&gt; Run all comparison batches -&gt; Open the course worksheet.",
                html,
            )
            self.assertIn("<strong>Compare:</strong> Generate the course batch report set.", html)
            self.assertIn(
                "<strong>Prediction check:</strong> Mark Matched, Partly matched, or Surprised in the worksheet.",
                html,
            )
            self.assertIn("Mission evidence: Course artifacts ready; Open the course worksheet", html)
            self.assertIn("Challenge evidence: Ready to review; source course worksheet", html)
            self.assertNotIn("Mission evidence: Needs plot", html)
            self.assertIn("Mission Review Queue", html)
            self.assertIn("1 ready, 0 pending", html)
            self.assertIn("No pending mission evidence.", html)
            self.assertIn(
                "Next cue: Open the course worksheet, then compare each linked batch Prediction Check "
                "and Viewer Handoff.",
                html,
            )
            self.assertIn("Next action: run lab01", html)
            self.assertIn("20260627_151000_all_batches/report.html", html)
            self.assertIn("python -m mclab batch all --open-report", html)

    def test_outputs_index_points_completed_batch_to_viewer_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_151000_lab01_msd_compare"
            output.mkdir()
            (output / "comparison_plots").mkdir()
            (output / "comparison_plots" / "position_compare.png").write_bytes(b"fake-png")
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch",
                        "config_name": "lab01_msd_compare",
                        "batch_name": "lab01_msd_compare",
                        "samples": 5,
                        "duration": "",
                    }
                ),
                encoding="utf-8",
            )
            (output / "report.html").write_text('<html><section id="viewer-handoff"></section></html>', encoding="utf-8")
            (output / "worksheet.md").write_text("# Batch worksheet\n\n## Prediction Check\n", encoding="utf-8")

            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn(
                "Next cue: Open the worksheet Prediction Check, then open the report Viewer Handoff "
                "and run the recommended viewer scenario.",
                html,
            )
            self.assertIn(
                'href="20260627_151000_lab01_msd_compare/report.html#viewer-handoff">Viewer Handoff</a>',
                html,
            )
            self.assertIn("20260627_151000_lab01_msd_compare/report.html", html)
            self.assertIn("20260627_151000_lab01_msd_compare/worksheet.md", html)

    def test_outputs_index_requires_hands_on_prediction_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline = Path(temp_dir) / "20260627_150000_lab01_msd"
            baseline.mkdir()
            (baseline / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            (baseline / "report.html").write_text("<html>baseline</html>", encoding="utf-8")

            interactive = Path(temp_dir) / "20260627_150100_lab01_interactive"
            interactive.mkdir()
            (interactive / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/interactive_pull.yaml",
                        "config_name": "interactive_pull",
                    }
                ),
                encoding="utf-8",
            )
            (interactive / "report.html").write_text("<html>interactive</html>", encoding="utf-8")

            index = write_outputs_index(temp_dir)
            html = index.read_text(encoding="utf-8")

            self.assertIn("1/12 steps complete. Evidence pending: 1 hands-on step(s).", html)
            self.assertIn("Next: 2. Disturb and tune", html)
            self.assertIn("Needs observation", html)
            self.assertIn("Add one Mark observation entry before moving on.", html)
            self.assertIn("20260627_150100_lab01_interactive/report.html", html)
            self.assertIn("<th>Evidence</th>", html)
            self.assertIn("<th>Next cue</th>", html)
            self.assertIn("<th>Repeat command</th>", html)
            self.assertIn("<th>Activity</th>", html)
            self.assertIn("<th>Mission evidence</th>", html)
            self.assertIn("<th>Challenge evidence</th>", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot --plots essential --open-report",
                html,
            )
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                "--viewer --realtime --pause-at-end --plot --plots essential --open-report",
                html,
            )
            self.assertIn("No markers", html)
            self.assertIn("No learner controls", html)
            self.assertIn("Next cue: Try preset Lightly damped, then mark a comparison observation.", html)
            self.assertIn(
                "Observation next step: use experiment buttons (Pull/Push buttons and A/D keys), "
                "live sliders, or Quick presets, "
                "then mark one observation with a prediction and note.",
                html,
            )
            self.assertIn("Needs observation; Run the demo, write a prediction, then press Mark observation.", html)
            self.assertIn(
                "Challenge evidence: Needs observation evidence; source Learner control, Mark observation, "
                "live status, and priority plot",
                html,
            )

            (interactive / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "note": "The mass settled faster after damping changed.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")
            self.assertIn("1/12 steps complete. Evidence pending: 1 hands-on step(s).", html)
            self.assertIn("Next: 2. Disturb and tune", html)
            self.assertIn("Needs prediction (1 observation, 1 note, 0 controls)", html)
            self.assertIn("Add one Prediction in Mark observation before moving on.", html)
            self.assertIn("1 observation, 0 predictions, 1 note", html)
            self.assertIn("Next cue: Add a prediction before marking the next observation.", html)
            self.assertIn("Needs prediction; Repeat or continue the demo and save a Mark observation with a prediction.", html)
            self.assertIn(
                "Latest evidence: Note: The mass settled faster after damping changed.",
                html,
            )
            self.assertIn("Activity mix: 0/3 control families; buttons 0, sliders 0, presets 0, markers 1", html)
            self.assertIn("Latest: Note: The mass settled faster after damping changed.", html)

            (interactive / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "outcome": "Matched",
                                "note": "The mass settled faster after damping changed.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")
            self.assertIn("Needs learner control (1 observation, 1 prediction, 1 outcome, 1 note, 0 controls)", html)
            self.assertIn(
                "Next cue: Use experiment buttons (Pull/Push buttons and A/D keys), "
                "live sliders, or Quick presets, then mark another observation with a prediction and note.",
                html,
            )
            self.assertIn(
                "Use experiment buttons (Pull/Push buttons and A/D keys), live sliders, or Quick presets "
                "before moving on.",
                html,
            )
            self.assertIn(
                "Observation next step: use experiment buttons (Pull/Push buttons and A/D keys), "
                "live sliders, or Quick presets, "
                "then mark another observation with a prediction and note.",
                html,
            )

            (interactive / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "button", "name": "manual_force", "label": "Push Right", "value": 12.0},
                        {"kind": "preset", "name": "heavy_damping", "label": "Heavy damping"},
                        {"kind": "slider", "name": "damping", "label": "Damping", "value": 5.0},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "note": "The mass settled faster after damping changed.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")
            self.assertIn("2/12 steps complete. Outcome review pending: 1 hands-on step(s).", html)
            self.assertIn("Next: 3. Close the loop", html)
            self.assertIn("Next cue: Review latest evidence and choose the missing prediction outcome.", html)
            self.assertIn("Done (1 observation, 1 prediction, 1 note, 3 controls)", html)
            self.assertIn("Add one Prediction outcome while reviewing.", html)
            self.assertIn(
                "Mission evidence: Outcome review pending; "
                "Choose Matched, Partly matched, or Surprised for each saved prediction.",
                html,
            )
            self.assertIn(
                "Challenge evidence: Needs prediction outcome review; "
                "source Learner control, Mark observation, live status, and priority plot",
                html,
            )
            self.assertIn(
                "Latest evidence: Prediction: More damping should settle faster.; "
                "Outcome: missing review; "
                "Note: The mass settled faster after damping changed.",
                html,
            )

            (interactive / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "outcome": "Matched",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")
            self.assertIn("1/12 steps complete. Evidence pending: 1 hands-on step(s).", html)
            self.assertIn("Next: 2. Disturb and tune", html)
            self.assertIn("Needs note (1 observation, 1 prediction, 1 outcome, 0 controls)", html)
            self.assertIn("Next cue: Add a short note or Use live status before moving on.", html)
            self.assertIn("Add a short note or Use live status before moving on.", html)

            (interactive / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "button", "name": "manual_force", "label": "Push Right", "value": 12.0},
                        {"kind": "preset", "name": "heavy_damping", "label": "Heavy damping"},
                        {"kind": "slider", "name": "damping", "label": "Damping", "value": 5.0},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "outcome": "Matched",
                                "note": "The mass settled faster after damping changed.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")
            self.assertIn("2/12 steps complete. Next: 3. Close the loop", html)
            self.assertIn("Next cue: Try preset Lightly damped, then mark a comparison observation.", html)
            self.assertIn("Done (1 observation, 1 prediction, 1 outcome, 1 note, 3 controls)", html)
            self.assertIn("1 observation, 1 prediction, 1 outcome, 1 note", html)
            self.assertIn(
                "Mission evidence: Ready for review; "
                "Compare mission evidence with the priority plot, then run Next or Compare.",
                html,
            )
            self.assertIn(
                "Challenge evidence: Ready to review; "
                "source Learner control, Mark observation, live status, and priority plot",
                html,
            )
            self.assertIn(
                "Latest evidence: Prediction: More damping should settle faster.; "
                "Outcome: Matched; "
                "Note: The mass settled faster after damping changed.",
                html,
            )
            self.assertIn(
                "Activity mix: 3/3 control families; buttons 1, sliders 1, presets 1, markers 1; "
                "next: Ready: compare this interaction mix against plots and the worksheet.; "
                "path: button: Push Right -&gt; preset: Heavy damping -&gt; slider: Damping -&gt; observation: Mark observation",
                html,
            )
            self.assertIn(
                "Latest: Prediction: More damping should settle faster.; "
                "Outcome: Matched; "
                "Note: The mass settled faster after damping changed.",
                html,
            )

    def test_outputs_index_requires_wall_required_presets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wall = Path(temp_dir) / "20260627_160000_lab04_wall_interactive"
            wall.mkdir()
            (wall / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab04_panda",
                        "config_path": "configs/lab04_panda/interactive_virtual_wall.yaml",
                        "config_name": "interactive_virtual_wall",
                    }
                ),
                encoding="utf-8",
            )
            (wall / "report.html").write_text("<html>wall</html>", encoding="utf-8")
            (wall / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "close_wall", "label": "Close wall"},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Back away should release contact.",
                                "outcome": "Matched",
                                "note": "Contact stayed active before backing away.",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn("11. Touch virtual wall", html)
            self.assertIn(
                "<strong>Done when:</strong> use at least one button, slider, or preset, then save one Mark observation "
                "with a Prediction and note after required presets: "
                "Close wall -&gt; Back away -&gt; Re-enter wall; add the outcome during review.",
                html,
            )
            self.assertIn(
                "Needs required preset (1 observation, 1 prediction, 1 outcome, 1 note, 1 control, required presets 1/3)",
                html,
            )
            self.assertIn("Try required preset Back away before moving on.", html)
            self.assertIn("Next cue: Try required preset Back away, then mark a comparison observation.", html)
            self.assertIn(
                "Mission evidence: Needs required preset Back away; "
                "Try required preset Back away, watch live status, then mark one observation.",
                html,
            )
            self.assertIn(
                "Challenge evidence: Needs required preset evidence; "
                "source Learner control, Mark observation, live status, and priority plot",
                html,
            )
            self.assertIn("required preset: 1", html)
            self.assertIn(
                'Next review: <a href="20260627_160000_lab04_wall_interactive/report.html">'
                "20260627_160000_lab04_wall_interactive</a> - Needs required preset Back away",
                html,
            )

    def test_outputs_index_summarizes_latest_observation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "20260627_151500_lab02_interactive"
            run.mkdir()
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab02_pid",
                        "config_path": "configs/lab02_pid/interactive_disturbance.yaml",
                        "config_name": "interactive_disturbance",
                    }
                ),
                encoding="utf-8",
            )
            (run / "report.html").write_text("<html>pid</html>", encoding="utf-8")
            (run / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Old prediction should not be summarized.",
                                "note": "Old note should not be summarized.",
                            },
                        },
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Higher damping should reduce overshoot.",
                                "outcome": "Surprised",
                                "note": (
                                    "Settling: The trace settled faster after the preset.; "
                                    "Changed values: Damping=5.0"
                                ),
                                "status": {
                                    "Error [m]": 0.0123456,
                                    "Control [N]": 4.2,
                                    "Unused": "--",
                                    "Energy": "n/a",
                                    "Mode": "observe",
                                },
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn("Evidence Quality", html)
            self.assertIn("Outcome coverage: 50% of predictions", html)
            self.assertIn("Outcome mix: Surprised 1", html)
            self.assertIn("2 observations, 2 predictions, 1 outcome, 2 notes", html)
            self.assertIn(
                "Latest: Prediction: Higher damping should reduce overshoot.; "
                "Outcome: Surprised; "
                "Note: Settling: The trace settled faster after the preset.; Changed values: Damping=5.0; "
                "Note evidence: Settling: The trace settled faster after the preset. | Changed values: Damping=5.0; "
                "Status: Error [m]=0.0123456, Control [N]=4.2, Mode=observe",
                html,
            )
            self.assertIn(
                "Observation flow: 2 markers; first prediction saved, outcome missing -&gt; "
                "latest prediction saved, outcome Surprised, "
                "note Settling: The trace settled faster after the preset. | Changed values: Damping=5.0, "
                "status Error [m]=0.0123456, Control [N]=4.2, Mode=observe",
                html,
            )
            self.assertIn(
                "Observation next step: judge 1 prediction outcome "
                "(Matched, Partly matched, or Surprised).",
                html,
            )
            self.assertNotIn("Old prediction should not be summarized.", html)

    def test_outputs_index_shows_mission_review_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ready = Path(temp_dir) / "20260627_150000_lab01_ready"
            ready.mkdir()
            (ready / "plots").mkdir()
            (ready / "plots" / "position.png").write_bytes(b"fake-png")
            (ready / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            (ready / "report.html").write_text("<html>ready</html>", encoding="utf-8")

            artifact = Path(temp_dir) / "20260627_150100_lab01_needs_plot"
            artifact.mkdir()
            (artifact / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            (artifact / "report.html").write_text("<html>artifact</html>", encoding="utf-8")

            needs_observation = Path(temp_dir) / "20260627_150200_lab01_interactive_empty"
            needs_observation.mkdir()
            (needs_observation / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/interactive_pull.yaml",
                        "config_name": "interactive_pull",
                    }
                ),
                encoding="utf-8",
            )
            (needs_observation / "report.html").write_text("<html>observation</html>", encoding="utf-8")

            needs_prediction = Path(temp_dir) / "20260627_150300_lab02_interactive_note"
            needs_prediction.mkdir()
            (needs_prediction / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab02_pid",
                        "config_path": "configs/lab02_pid/interactive_disturbance.yaml",
                        "config_name": "interactive_disturbance",
                    }
                ),
                encoding="utf-8",
            )
            (needs_prediction / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"note": "The response changed."},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (needs_prediction / "report.html").write_text("<html>prediction</html>", encoding="utf-8")

            outcome_pending = Path(temp_dir) / "20260627_150400_lab03_interactive_outcome"
            outcome_pending.mkdir()
            (outcome_pending / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab03_2dof",
                        "config_path": "configs/lab03_2dof/interactive_2dof.yaml",
                        "config_name": "interactive_2dof",
                    }
                ),
                encoding="utf-8",
            )
            (outcome_pending / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "slider", "name": "target_x", "label": "Target X", "value": 0.45},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "A farther target should need more torque.",
                                "note": "Torque rose after the preset.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (outcome_pending / "report.html").write_text("<html>outcome</html>", encoding="utf-8")

            note_pending = Path(temp_dir) / "20260627_150500_lab04_interactive_note"
            note_pending.mkdir()
            (note_pending / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab04_panda",
                        "config_path": "configs/lab04_panda/interactive_virtual_wall.yaml",
                        "config_name": "interactive_virtual_wall",
                    }
                ),
                encoding="utf-8",
            )
            (note_pending / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "A stiff wall should retreat more.",
                                "outcome": "Matched",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (note_pending / "report.html").write_text("<html>note</html>", encoding="utf-8")

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn("Mission Review Queue", html)
            self.assertIn("1 ready, 5 pending", html)
            self.assertIn(
                "Needs observation: 1; prediction: 1; outcome: 1; required preset: 1; note: 0; control: 0; artifact: 1",
                html,
            )
            self.assertIn(
                'Next review: <a href="20260627_150400_lab03_interactive_outcome/report.html">'
                "20260627_150400_lab03_interactive_outcome</a> - Outcome review pending",
                html,
            )

    def test_outputs_index_requires_evidence_for_live_tuning_learning_path_configs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dls_run = Path(temp_dir) / "20260627_150200_lab03_dls"
            dls_run.mkdir()
            (dls_run / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab03_2dof",
                        "config_path": "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
                        "config_name": "condition_aware_dls_2dof",
                    }
                ),
                encoding="utf-8",
            )
            (dls_run / "report.html").write_text("<html>dls</html>", encoding="utf-8")

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn("7. Handle singularity", html)
            self.assertIn("Needs observation", html)
            self.assertIn("20260627_150200_lab03_dls/report.html", html)

            (dls_run / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "balanced_dls", "label": "Balanced DLS"},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: What changed near the singularity?",
                                "prediction": "More damping should reduce joint speed.",
                                "note": "DLS damping rose as condition number increased.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn("Done (1 observation, 1 prediction, 1 note, 1 control)", html)
            self.assertIn("1 observation, 1 prediction, 1 note", html)

    def test_outputs_index_handles_empty_outputs_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn("Starter Commands", html)
            self.assertIn("Experience Coverage", html)
            self.assertIn("Run next: Intro basics", html)
            self.assertIn("<strong>Next action:</strong> Run Lab01 Mass-Spring-Damper - Auto demo.", html)
            self.assertIn("<strong>Mode:</strong> hands-on viewer", html)
            self.assertIn(
                "<strong>Evidence:</strong> At least one learner-control event plus one prediction-backed observation marker.",
                html,
            )
            self.assertIn(
                "<strong>Evidence:</strong> A batch comparison report and worksheet with a Prediction Check table.",
                html,
            )
            self.assertIn("MCLab Interaction window; Pull/Push buttons and A/D keys", html)
            self.assertIn(
                "<strong>Counts as control:</strong> experiment buttons (Pull/Push buttons and A/D keys), "
                "live sliders, Quick presets",
                html,
            )
            self.assertIn(
                "comparison batch; inspect plots and worksheet, then use Viewer Handoff for hands-on rerun.",
                html,
            )
            self.assertIn("<strong>Intro basics</strong>", html)
            self.assertIn('<span class="status">Next</span>', html)
            self.assertIn("<strong>Virtual wall</strong>", html)
            self.assertIn('<span class="status">Missing</span>', html)
            self.assertIn("Check setup", html)
            self.assertIn("python -m mclab doctor", html)
            self.assertIn(r".\run_mclab.cmd", html)
            self.assertIn("See next experience", html)
            self.assertIn("python -m mclab coverage", html)
            self.assertIn("Compare all experiences", html)
            self.assertIn("python -m mclab coverage --details", html)
            self.assertIn("Inspect parameters", html)
            self.assertIn("python -m mclab params wall --filter hands-on", html)
            self.assertIn("Preview next path step", html)
            self.assertIn("python -m mclab next --preview", html)
            self.assertIn("<strong>Plan:</strong> Intro; headless plot run; 5s simulated", html)
            self.assertIn("<strong>Plan:</strong> Intro; hands-on viewer; 120s simulated", html)
            self.assertIn("<strong>Plan:</strong> Compare; course batch; all comparison batches", html)
            self.assertIn("<strong>Mission:</strong> Compare position, velocity, force, and energy plots", html)
            self.assertIn("<strong>Challenge:</strong> Explain how mass, damping, stiffness", html)
            self.assertIn("<strong>Viewer:</strong> MuJoCo side panels are hidden", html)
            self.assertIn("Green sphere = Cartesian hand target", html)
            self.assertIn("<strong>Change:</strong> mass, damping, stiffness, initial_position", html)
            self.assertIn("Values:</strong> mass=1; damping=2; stiffness=50; initial_position=0.1", html)
            self.assertIn("tracking_controller.max_task_speed_schedule=4 points", html)
            self.assertIn("virtual_wall.stiffness=260", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot --plots essential --open-report",
                html,
            )
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                "--viewer --realtime --pause-at-end --plot --plots essential --open-report",
                html,
            )
            self.assertIn("Run first comparison", html)
            self.assertIn("python -m mclab batch lab01_msd_compare --open-report", html)
            self.assertIn("No run reports were found yet.", html)
            self.assertIn("No saved runs yet.", html)

    def test_outputs_index_coverage_complete_points_to_learning_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            lab01 = root / "run_lab01_interactive"
            lab01.mkdir()
            (lab01 / "summary.json").write_text(
                (
                    '{"lab_name": "lab01_msd", '
                    '"config_path": "configs/lab01_msd/interactive_pull.yaml", '
                    '"config_name": "interactive_pull"}'
                ),
                encoding="utf-8",
            )
            (lab01 / "interaction_events.json").write_text(
                '[{"kind": "button", "name": "push", "label": "Push Right"}]',
                encoding="utf-8",
            )
            lab03 = root / "run_lab03_dls"
            lab03.mkdir()
            (lab03 / "summary.json").write_text(
                (
                    '{"lab_name": "lab03", '
                    '"config_path": "configs/lab03_2dof/condition_aware_dls_2dof.yaml", '
                    '"config_name": "condition_aware_dls_2dof"}'
                ),
                encoding="utf-8",
            )
            lab04 = root / "run_lab04_wall"
            lab04.mkdir()
            (lab04 / "summary.json").write_text(
                (
                    '{"lab_name": "lab04", '
                    '"config_path": "configs/lab04_panda/interactive_virtual_wall.yaml", '
                    '"config_name": "interactive_virtual_wall"}'
                ),
                encoding="utf-8",
            )
            batch = root / "batch_lab02"
            batch.mkdir()
            (batch / "summary.json").write_text(
                '{"lab_name": "batch", "config_name": "lab02_pid_compare", "batch_name": "lab02_pid_compare"}',
                encoding="utf-8",
            )

            html = write_outputs_index(root).read_text(encoding="utf-8")

        self.assertIn("Experience coverage: 7/7 types tried", html)
        self.assertIn("continue the learning path", html)
        self.assertIn("All core experience types are represented.", html)
        self.assertIn("Continue the Learning Path below if it still shows pending evidence", html)
        self.assertIn("Learning Path", html)

    def test_outputs_index_review_queue_prioritizes_required_preset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "run_lab04_wall"
            run.mkdir()
            (run / "report.html").write_text("<html></html>", encoding="utf-8")
            (run / "summary.json").write_text(
                (
                    '{"lab_name": "lab04_panda", '
                    '"config_path": "configs/lab04_panda/interactive_virtual_wall.yaml", '
                    '"config_name": "interactive_virtual_wall"}'
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(root).read_text(encoding="utf-8")

        self.assertIn("required preset: 1", html)
        self.assertIn("run_lab04_wall</a> - Needs required preset Close wall", html)
        self.assertIn("Needs required preset Close wall; Try required preset Close wall", html)
        self.assertIn(
            "Observation next step: try required preset Close wall, "
            "then mark one observation with a prediction and note.",
            html,
        )
