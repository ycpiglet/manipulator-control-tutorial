from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from dataclasses import replace
from html import escape as html_escape
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mclab.application.artifacts import write_manifest
from mclab.application.catalog import BatchDefinition, ScenarioCatalog
from mclab.application.i18n import Translator
from mclab.application.presentation import (
    course_progress_payload,
    result_payloads,
    scenario_payload,
)
from mclab.application.repositories import ArtifactRecord, ArtifactRepository
from mclab.batch import (
    _completion_html as _batch_completion_html,
    _completion_worksheet_lines as _batch_completion_worksheet_lines,
)
from mclab.cli import _print_output_summary, main
from mclab.completion import (
    CompletionDecision,
    CompletionEvidence,
    CompletionReason,
    CompletionRecordKind,
    InteractionEvidence,
    ObservationEvidence,
    evaluate_completion,
)
from mclab.learner_menu import (
    BATCH_ACTIONS,
    MENU_ACTIONS,
    _action_completion_assessment,
    _completion_context,
    completion_target_id,
)
from mclab.sim.reporting import (
    INDEX_LEARNING_PATH,
    _completion_section as _run_completion_html,
    _completion_status_text,
    _discover_runs,
    _learning_path_item,
    _render_outputs_index,
    _worksheet_completion_lines as _run_completion_worksheet_lines,
    write_outputs_index,
    write_run_report,
)


def _decision_verdict(decision: CompletionDecision) -> tuple[bool, str]:
    return decision.complete, decision.primary_reason.value


def _complete_evidence(target: object) -> CompletionEvidence:
    rule = target.completion  # type: ignore[attr-defined]
    observations = (
        (
            ObservationEvidence(
                has_prediction=rule.requires_prediction,
                has_note=rule.requires_note,
                has_outcome=True,
            ),
        )
        if rule.requires_observation or rule.requires_prediction or rule.requires_note
        else ()
    )
    return CompletionEvidence(
        CompletionRecordKind.MANIFEST_V1,
        status="completed",
        plot_count=int(rule.requires_plot),
        interaction=InteractionEvidence(
            learner_control_count=int(rule.requires_learner_control),
            observations=observations,
            preset_labels=rule.required_presets,
        ),
        artifact_keys=rule.required_artifacts,
    )


def _catalog_parity_cases(
    target: object,
) -> tuple[tuple[str, str, CompletionEvidence], ...]:
    """Return complete plus every missing-evidence axis declared by one rule."""

    rule = target.completion  # type: ignore[attr-defined]
    complete = _complete_evidence(target)
    cases: list[tuple[str, str, CompletionEvidence]] = [("complete", "complete", complete)]
    if rule.requires_run:
        cases.append(("missing-status", "status", replace(complete, status="stopped")))
    if rule.requires_plot:
        cases.append(("missing-plot", "plot", replace(complete, plot_count=0)))
    if rule.requires_learner_control:
        cases.append(
            (
                "missing-learner-control",
                "learner-control",
                replace(
                    complete,
                    interaction=replace(
                        complete.interaction,
                        learner_control_count=0,
                    ),
                ),
            )
        )
    if rule.requires_observation:
        cases.append(
            (
                "missing-observation",
                "observation",
                replace(
                    complete,
                    interaction=replace(complete.interaction, observations=()),
                ),
            )
        )
    if rule.requires_prediction:
        cases.append(
            (
                "missing-prediction",
                "prediction",
                replace(
                    complete,
                    interaction=replace(
                        complete.interaction,
                        observations=(
                            ObservationEvidence(
                                has_prediction=False,
                                has_note=True,
                                has_outcome=True,
                            ),
                        ),
                    ),
                ),
            )
        )
    if rule.requires_note:
        cases.append(
            (
                "uncorrelated-prediction-note",
                "prediction-note-correlation",
                replace(
                    complete,
                    interaction=replace(
                        complete.interaction,
                        observations=(
                            ObservationEvidence(
                                has_prediction=True,
                                has_note=False,
                                has_outcome=True,
                            ),
                            ObservationEvidence(
                                has_prediction=False,
                                has_note=True,
                                has_outcome=True,
                            ),
                        ),
                    ),
                ),
            )
        )
    if rule.required_presets:
        attempted = (*rule.required_presets[1:], rule.required_presets[0])
        cases.append(
            (
                "out-of-order-required-presets",
                "required-preset-order",
                replace(
                    complete,
                    interaction=replace(
                        complete.interaction,
                        preset_labels=attempted,
                    ),
                ),
            )
        )
    for artifact_key in rule.required_artifacts:
        axis = (
            "batch-child"
            if artifact_key.startswith("batch.")
            else f"artifact-{artifact_key}"
        )
        label = f"missing-{artifact_key.replace('.', '-')}"
        cases.append(
            (
                label,
                axis,
                replace(
                    complete,
                    artifact_keys=tuple(
                        key for key in complete.artifact_keys if key != artifact_key
                    ),
                ),
            )
        )
    return tuple(cases)


def _case_name(index: int, target_id: str, label: str) -> str:
    safe_target = target_id.replace(".", "-").replace("_", "-")
    safe_label = label.replace(".", "-").replace("_", "-")
    return f"case-{index:03d}-{safe_target}-{safe_label}"


def _synthetic_record(
    root: Path,
    name: str,
    target: object,
    evidence: CompletionEvidence,
) -> ArtifactRecord:
    path = root / name
    summary = (
        {"lab_name": "batch", "batch_name": target.batch_name}
        if isinstance(target, BatchDefinition)
        else {"lab_name": target.lab_name, "config_name": target.id}
    )
    return ArtifactRecord(
        path=path,
        scenario_id=target.id,
        status=evidence.status or "invalid",
        size_bytes=0,
        replay_available=False,
        rerun_available=False,
        tuned_available=False,
        legacy=evidence.record_kind == CompletionRecordKind.LEGACY_SUMMARY,
        replay_reason="not part of completion parity",
        summary=summary,
        cleanup_token=name,
        manifest={},
        marker_name="manifest.json",
        completion_evidence=evidence,
        interaction_events=(),
        plot_paths=(path / "plots" / "evidence.png",) if evidence.plot_count else (),
        worksheet_available="worksheet" in evidence.artifact_keys,
        report_available="report" in evidence.artifact_keys,
        artifact_validation_errors=(),
        finished_at="",
        sort_timestamp=0.0,
    )


def _interaction_events_from_evidence(
    interaction: InteractionEvidence,
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = [
        {"kind": "button", "name": f"control-{index}"}
        for index in range(interaction.learner_control_count)
    ]
    events.extend(
        {"kind": "preset", "name": f"preset-{index}", "label": label}
        for index, label in enumerate(interaction.preset_labels, start=1)
    )
    for index, observation in enumerate(interaction.observations, start=1):
        value: dict[str, object] = {}
        if observation.has_prediction:
            value["prediction"] = f"prediction {index}"
        if observation.has_note:
            value["note"] = f"note {index}"
        if observation.has_outcome:
            value["outcome"] = "matched"
        events.append(
            {
                "kind": "marker",
                "name": "observation",
                "value": value,
            }
        )
    return events


def _completion_surface_text(
    target: object,
    decision: CompletionDecision,
) -> tuple[str, str]:
    if isinstance(target, BatchDefinition):
        return (
            _batch_completion_html(decision),
            "\n".join(_batch_completion_worksheet_lines(decision)),
        )
    return (
        _run_completion_html(decision),
        "\n".join(_run_completion_worksheet_lines(decision)),
    )


def _cli_completion_verdict(record: ArtifactRecord) -> tuple[bool, str]:
    stdout = StringIO()
    with (
        patch("mclab.cli._trusted_output_record", return_value=record),
        redirect_stdout(stdout),
    ):
        _print_output_summary("Run", record.path)
    completion_line = next(
        line.strip()
        for line in stdout.getvalue().splitlines()
        if line.strip().startswith("Completion:")
    )
    verdict, remainder = completion_line.removeprefix("Completion:").strip().split(" - ", 1)
    reason = remainder.rsplit(" (", 1)[0]
    return verdict == "Complete", reason


def _index_row(index_html: str, run_name: str) -> str:
    marker = f">{html_escape(run_name)}</a>"
    marker_index = index_html.rindex(marker)
    row_start = index_html.rfind("<tr>", 0, marker_index)
    row_end = index_html.index("</tr>", marker_index) + len("</tr>")
    return index_html[row_start:row_end]


def _write_complete_child_batch(
    course: Path,
    target: BatchDefinition,
) -> None:
    child = course / target.batch_name
    child.mkdir()
    (child / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": "batch",
                "batch_name": target.batch_name,
                "config_name": target.batch_name,
            }
        ),
        encoding="utf-8",
    )
    plots = child / "comparison_plots"
    plots.mkdir()
    (plots / "evidence.png").write_bytes(b"strict child plot")
    decision = evaluate_completion(target.completion, _complete_evidence(target))
    report, worksheet = _completion_surface_text(target, decision)
    (child / "report.html").write_text(report, encoding="utf-8")
    (child / "worksheet.md").write_text(
        worksheet + "\n\n## Prediction Check\n",
        encoding="utf-8",
    )
    write_manifest(
        child,
        scenario_id=target.id,
        status="completed",
        config={"batch_name": target.batch_name, "plot": True},
        run_kind="comparison_batch",
    )


def _write_strict_parity_case(
    outputs_root: Path,
    name: str,
    target: object,
    evidence: CompletionEvidence,
    catalog: ScenarioCatalog,
) -> Path:
    """Publish one small real schema-1 artifact tree for strict-reader parity."""

    run = outputs_root / name
    run.mkdir(parents=True)
    is_batch = isinstance(target, BatchDefinition)
    config_path = "" if is_batch else target.config_path  # type: ignore[attr-defined]
    summary = (
        {
            "lab_name": "batch",
            "batch_name": target.batch_name,
            "config_name": target.batch_name,
        }
        if is_batch
        else {
            "lab_name": target.lab_name,  # type: ignore[attr-defined]
            "config_name": Path(config_path).stem,
            "config_path": config_path,
        }
    )
    (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    if evidence.plot_count:
        plot_dir = run / ("comparison_plots" if is_batch else "plots")
        plot_dir.mkdir()
        (plot_dir / "evidence.png").write_bytes(b"strict parity plot")
    events = _interaction_events_from_evidence(evidence.interaction)
    if events:
        (run / "interaction_events.json").write_text(
            json.dumps(events),
            encoding="utf-8",
        )

    if isinstance(target, BatchDefinition) and target.id == "batch.all":
        for child_id in target.child_target_ids:
            if child_id in evidence.artifact_keys:
                _write_complete_child_batch(run, catalog.get_batch(child_id))

    decision = evaluate_completion(target.completion, evidence)  # type: ignore[attr-defined]
    report, worksheet = _completion_surface_text(target, decision)
    required_artifacts = set(target.completion.required_artifacts)  # type: ignore[attr-defined]
    publish_report = not required_artifacts or "report" in evidence.artifact_keys
    publish_worksheet = not required_artifacts or "worksheet" in evidence.artifact_keys
    if publish_report:
        (run / "report.html").write_text(report, encoding="utf-8")
    if publish_worksheet:
        prediction_check = (
            "\n\n## Prediction Check\n"
            if "prediction-check" in evidence.artifact_keys
            else ""
        )
        (run / "worksheet.md").write_text(
            worksheet + prediction_check,
            encoding="utf-8",
        )

    write_manifest(
        run,
        scenario_id=target.id,  # type: ignore[attr-defined]
        status=evidence.status or "error",
        config=(
            {"batch_name": target.batch_name, "plot": True}
            if is_batch
            else {"sim_time": 1.0}
        ),
        config_path=config_path or None,
        run_kind="comparison_batch" if is_batch else "",
    )
    return run


def _write_scenario_run(
    outputs_root: Path,
    name: str,
    *,
    scenario_id: str = "lab01.default",
    lab_name: str = "lab01_msd",
    config_path: str = "configs/lab01_msd/default.yaml",
    plot: bool = True,
    events: list[dict[str, object]] | None = None,
    legacy: bool = False,
    manifest_mutation: str = "",
    tamper_plot: bool = False,
    started_at: str = "2026-07-21T00:00:00+00:00",
    finished_at: str = "2026-07-21T00:01:00+00:00",
) -> Path:
    run = outputs_root / name
    run.mkdir(parents=True)
    (run / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": lab_name,
                "config_name": Path(config_path).stem,
                "config_path": config_path,
                "duration": 1.0,
                "samples": 10,
            }
        ),
        encoding="utf-8",
    )
    (run / "config.yaml").write_text("sim_time: 1.0\n", encoding="utf-8")
    (run / "notes.md").write_text("# Test note\n", encoding="utf-8")
    plot_path = (
        run
        / "plots"
        / ("wall_target.png" if scenario_id == "lab04.interactive-virtual-wall" else "position.png")
    )
    if plot:
        plot_path.parent.mkdir()
        plot_path.write_bytes(b"published plot")
    if events is not None:
        (run / "interaction_events.json").write_text(
            json.dumps(events),
            encoding="utf-8",
        )
    if legacy:
        return run

    write_manifest(
        run,
        scenario_id=scenario_id,
        status="running",
        config={"sim_time": 1.0},
        config_path=config_path,
        started_at=started_at,
        finished_at=finished_at,
    )
    write_run_report(
        run,
        update_index=False,
        completion_status="completed",
    )
    manifest_path = write_manifest(
        run,
        scenario_id=scenario_id,
        status="completed",
        config={"sim_time": 1.0},
        config_path=config_path,
        started_at=started_at,
        finished_at=finished_at,
    )
    if manifest_mutation:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_mutation == "future":
            payload["schema_version"] = 2
        elif manifest_mutation == "malformed":
            payload.pop("runtime")
        else:  # pragma: no cover - protects the test helper contract
            raise ValueError(f"Unknown manifest mutation: {manifest_mutation}")
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    if tamper_plot:
        plot_path.write_bytes(b"changed after manifest publication")
    return run


def _wall_events(labels: tuple[str, ...]) -> list[dict[str, object]]:
    return [
        {"kind": "button", "name": "target_x_nudge"},
        *(
            {"kind": "preset", "name": f"preset-{index}", "label": label}
            for index, label in enumerate(labels, start=1)
        ),
        {
            "kind": "marker",
            "name": "observation",
            "value": {
                "prediction": "contact force will change",
                "note": "wall response changed",
                "outcome": "matched",
            },
        },
    ]


class CompletionSurfaceParityTests(unittest.TestCase):
    def test_catalog_has_zero_completion_surface_mismatches_for_every_rule_axis(self) -> None:
        catalog = ScenarioCatalog.default()
        targets = catalog.targets()
        actions = {
            completion_target_id(action): action for action in (*MENU_ACTIONS, *BATCH_ACTIONS)
        }

        self.assertEqual(len(catalog.all()), 72)
        self.assertEqual(len(catalog.batches()), 6)
        self.assertEqual(set(actions), {target.id for target in targets})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows: list[
                tuple[object, str, str, ArtifactRecord, CompletionDecision]
            ] = []
            axis_representatives: dict[
                str,
                tuple[object, CompletionEvidence, CompletionDecision],
            ] = {}
            case_index = 0
            for target in targets:
                for label, axis, evidence in _catalog_parity_cases(target):
                    case_index += 1
                    record = _synthetic_record(
                        root,
                        _case_name(case_index, target.id, label),
                        target,
                        evidence,
                    )
                    decision = evaluate_completion(target.completion, evidence)
                    rows.append(
                        (target, label, axis, record, decision)
                    )
                    axis_representatives.setdefault(axis, (target, evidence, decision))

            axis_counts = Counter(row[2] for row in rows)
            self.assertEqual(
                axis_counts,
                Counter(
                    {
                        "complete": 78,
                        "status": 78,
                        "plot": 77,
                        "learner-control": 9,
                        "observation": 9,
                        "prediction": 9,
                        "prediction-note-correlation": 9,
                        "required-preset-order": 1,
                        "artifact-report": 6,
                        "artifact-worksheet": 6,
                        "artifact-prediction-check": 5,
                        "batch-child": 5,
                    }
                ),
            )

            with patch(
                "mclab.sim.reporting.ArtifactRepository.list_runs",
                return_value=tuple(row[3] for row in rows),
            ):
                reporting_runs = _discover_runs(root)
            reporting_by_name = {str(item["name"]): item for item in reporting_runs}
            index_html = _render_outputs_index(root, reporting_runs)

            mismatches: list[str] = []
            for target, label, _axis, record, canonical in rows:
                expected = _decision_verdict(canonical)
                desktop = result_payloads((record,), Translator("en"), catalog)[0]
                menu = _action_completion_assessment(
                    actions[target.id],
                    catalog,
                    (record,),
                ).latest_decision
                reporting = reporting_by_name[record.path.name]["completion_decision"]
                cli = _cli_completion_verdict(record)
                observed = {
                    "desktop": (desktop["completed"], desktop["completionReason"]),
                    "menu": _decision_verdict(menu),
                    "cli": cli,
                    "reporting": _decision_verdict(reporting),
                }
                for surface, verdict in observed.items():
                    if verdict != expected:
                        mismatches.append(
                            f"{target.id}/{label}/{surface}: expected {expected}, got {verdict}"
                        )

                verdict_text = "Complete" if expected[0] else "Incomplete"
                report_text, worksheet_text = _completion_surface_text(target, reporting)
                self.assertIn(f"Completion verdict:</strong> {verdict_text}", report_text)
                self.assertIn(f"Completion verdict: {verdict_text}", worksheet_text)
                self.assertIn(expected[1], report_text)
                self.assertIn(expected[1], worksheet_text)
                index_row = _index_row(index_html, record.path.name)
                self.assertIn(expected[1], index_row)
                index_status = _completion_status_text(
                    reporting,
                    reporting_by_name[record.path.name]["summary"],
                )
                self.assertIn(html_escape(index_status), index_row)

            strict_root = root / "strict"
            strict_root.mkdir()
            strict_expected: dict[str, tuple[bool, str]] = {}
            for strict_index, (axis, representative) in enumerate(
                axis_representatives.items(),
                start=1,
            ):
                target, evidence, decision = representative
                name = f"axis-{strict_index:02d}-{axis}"
                _write_strict_parity_case(
                    strict_root,
                    name,
                    target,
                    evidence,
                    catalog,
                )
                strict_expected[name] = _decision_verdict(decision)

            strict_records = {
                record.path.name: record
                for record in ArtifactRepository(strict_root).list_runs()
            }
            self.assertEqual(set(strict_records), set(strict_expected))
            for name, expected in strict_expected.items():
                record = strict_records[name]
                target = catalog.get_target(record.scenario_id)
                actual = evaluate_completion(
                    target.completion,
                    record.completion_evidence,
                )
                self.assertEqual(
                    _decision_verdict(actual),
                    expected,
                    f"strict reader axis {name}",
                )

        self.assertEqual(len(rows), 292)
        self.assertEqual(len(axis_representatives), 12)
        self.assertEqual(len(mismatches), 0, "\n".join(mismatches))

    def test_strict_reader_cases_match_desktop_menu_cli_index_report_and_worksheet(self) -> None:
        catalog = ScenarioCatalog.default()
        target = catalog.get("lab01.default")
        action = next(item for item in MENU_ACTIONS if completion_target_id(item) == target.id)
        cases = (
            (
                "strict-complete",
                {"plot": True},
                CompletionRecordKind.MANIFEST_V1,
                CompletionReason.COMPLETE,
                True,
                "Review queue: 1 ready, 0 pending",
            ),
            (
                "strict-incomplete",
                {"plot": False},
                CompletionRecordKind.MANIFEST_V1,
                CompletionReason.PLOT_MISSING,
                False,
                "Next review status: Needs plot",
            ),
            (
                "legacy",
                {"plot": True, "legacy": True},
                CompletionRecordKind.LEGACY_SUMMARY,
                CompletionReason.LEGACY_MANIFEST_MISSING,
                False,
                "Next review status: Legacy manifest incomplete",
            ),
            (
                "future",
                {"plot": True, "manifest_mutation": "future"},
                CompletionRecordKind.UNSUPPORTED,
                CompletionReason.MANIFEST_SCHEMA_UNSUPPORTED,
                False,
                "Next review status: Unsupported manifest schema",
            ),
            (
                "malformed",
                {"plot": True, "manifest_mutation": "malformed"},
                CompletionRecordKind.INVALID,
                CompletionReason.MANIFEST_INVALID,
                False,
                "Next review status: Invalid manifest",
            ),
            (
                "tampered",
                {"plot": True, "tamper_plot": True},
                CompletionRecordKind.MANIFEST_V1,
                CompletionReason.PLOT_MISSING,
                False,
                "Next review status: Needs plot",
            ),
        )
        mismatches: list[str] = []

        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = Path(temporary)
            for name, run_options, record_kind, reason, complete, cli_status in cases:
                with self.subTest(case=name):
                    outputs_root = fixture_root / name
                    run = _write_scenario_run(outputs_root, "run", **run_options)
                    records = ArtifactRepository(outputs_root).list_runs()
                    self.assertEqual(len(records), 1)
                    record = records[0]
                    self.assertEqual(record.completion_evidence.record_kind, record_kind)
                    canonical = evaluate_completion(target.completion, record.completion_evidence)
                    expected = (complete, reason.value)
                    desktop = result_payloads((record,), Translator("en"), catalog)[0]
                    menu_catalog, menu_records = _completion_context(outputs_root)
                    menu = _action_completion_assessment(
                        action,
                        menu_catalog,
                        menu_records,
                    ).latest_decision
                    reporting_run = _discover_runs(outputs_root)[0]
                    observed = {
                        "canonical": _decision_verdict(canonical),
                        "desktop": (desktop["completed"], desktop["completionReason"]),
                        "menu": _decision_verdict(menu),
                        "reporting": _decision_verdict(reporting_run["completion_decision"]),
                    }
                    for surface, verdict in observed.items():
                        if verdict != expected:
                            mismatches.append(
                                f"{name}/{surface}: expected {expected}, got {verdict}"
                            )
                    self.assertIn(reason.value, reporting_run["mission_evidence"])

                    if name == "legacy":
                        self.assertFalse(record.report_available)
                        self.assertFalse(record.worksheet_available)
                        before = {
                            path.relative_to(run).as_posix(): path.read_bytes()
                            for path in run.rglob("*")
                            if path.is_file()
                        }
                        with self.assertRaisesRegex(RuntimeError, "terminal or unsafe"):
                            write_run_report(run, update_index=False)
                        after = {
                            path.relative_to(run).as_posix(): path.read_bytes()
                            for path in run.rglob("*")
                            if path.is_file()
                        }
                        self.assertEqual(after, before)
                    elif record.report_available and record.worksheet_available:
                        report = (run / "report.html").read_text(encoding="utf-8")
                        worksheet = (run / "worksheet.md").read_text(encoding="utf-8")
                        verdict_text = "Complete" if complete else "Incomplete"
                        self.assertIn(
                            f"Completion verdict:</strong> {verdict_text}",
                            report,
                        )
                        self.assertIn(
                            f"Completion verdict: {verdict_text}",
                            worksheet,
                        )
                        for text in (report, worksheet):
                            self.assertIn(reason.value, text)
                    else:
                        self.assertIn(
                            name,
                            {"future", "malformed", "tampered"},
                        )

                    index = write_outputs_index(outputs_root).read_text(encoding="utf-8")
                    self.assertIn(reason.value, index)
                    stdout = StringIO()
                    with redirect_stdout(stdout):
                        self.assertEqual(
                            main(
                                [
                                    "review",
                                    "--output-dir",
                                    str(outputs_root),
                                    "--limit",
                                    "0",
                                ]
                            ),
                            0,
                        )
                    self.assertIn(cli_status, stdout.getvalue())

        self.assertEqual(len(mismatches), 0, "\n".join(mismatches))

    def test_unknown_schema_one_id_never_uses_summary_to_award_completion(self) -> None:
        catalog = ScenarioCatalog.default()
        target = catalog.get("lab01.default")
        action = next(item for item in MENU_ACTIONS if completion_target_id(item) == target.id)

        with tempfile.TemporaryDirectory() as temporary:
            outputs_root = Path(temporary)
            run = _write_scenario_run(
                outputs_root,
                "unknown-id",
                scenario_id="bogus.target",
                lab_name="lab01_msd",
                config_path="configs/lab01_msd/default.yaml",
                plot=True,
            )
            record = ArtifactRepository(outputs_root).list_runs()[0]
            canonical = evaluate_completion(None, record.completion_evidence)
            desktop = result_payloads((record,), Translator("en"), catalog)[0]
            reporting = _discover_runs(outputs_root)[0]["completion_decision"]
            menu_catalog, menu_records = _completion_context(outputs_root)
            menu = _action_completion_assessment(
                action,
                menu_catalog,
                menu_records,
            ).latest_decision
            self.assertTrue(record.report_available)
            report = (run / "report.html").read_text(encoding="utf-8")
            index = write_outputs_index(outputs_root).read_text(encoding="utf-8")

        expected = (False, CompletionReason.RULE_UNAVAILABLE.value)
        self.assertEqual(_decision_verdict(canonical), expected)
        self.assertEqual(
            (desktop["completed"], desktop["completionReason"]),
            expected,
        )
        self.assertEqual(_decision_verdict(reporting), expected)
        self.assertFalse(menu.complete)
        self.assertEqual(menu.primary_reason, CompletionReason.MANIFEST_MISSING)
        self.assertIn("Completion verdict:</strong> Incomplete", report)
        self.assertIn(CompletionReason.RULE_UNAVAILABLE.value, report)
        self.assertIn(CompletionReason.RULE_UNAVAILABLE.value, index)

    def test_wall_required_preset_order_is_shared_by_every_surface(self) -> None:
        catalog = ScenarioCatalog.default()
        target = catalog.get("lab04.interactive-virtual-wall")
        action = next(item for item in MENU_ACTIONS if completion_target_id(item) == target.id)
        required = ("Close wall", "Back away", "Re-enter wall")
        self.assertEqual(target.completion.required_presets, required)
        desktop_scenario = scenario_payload(target, Translator("en"))
        self.assertEqual(
            desktop_scenario["requiredPresetGuide"],
            "Required order: Close wall → Back away → Re-enter wall",
        )
        self.assertEqual(
            tuple(
                preset["canonicalLabel"]
                for preset in desktop_scenario["presets"]
                if preset["required"]
            ),
            required,
        )
        cases = (
            ("none", (), "Close wall", False),
            ("first", ("Close wall",), "Back away", False),
            (
                "out-of-order",
                ("Close wall", "Re-enter wall", "Back away"),
                "Re-enter wall",
                False,
            ),
            ("first-two", ("Close wall", "Back away"), "Re-enter wall", False),
            ("complete", required, "", True),
        )

        with tempfile.TemporaryDirectory() as temporary:
            outputs_root = Path(temporary)
            for index, (name, labels, _next_required, _complete) in enumerate(cases):
                _write_scenario_run(
                    outputs_root,
                    name,
                    scenario_id=target.id,
                    lab_name="lab04_panda",
                    config_path="configs/lab04_panda/interactive_virtual_wall.yaml",
                    events=_wall_events(labels),
                    finished_at=f"2026-07-21T00:{index + 1:02d}:00+00:00",
                )
            records = {
                record.path.name: record for record in ArtifactRepository(outputs_root).list_runs()
            }
            reporting_runs = {str(item["name"]): item for item in _discover_runs(outputs_root)}

            mismatches: list[str] = []
            for name, _labels, next_required, complete in cases:
                record = records[name]
                canonical = evaluate_completion(target.completion, record.completion_evidence)
                desktop = result_payloads((record,), Translator("en"), catalog)[0]
                menu = _action_completion_assessment(
                    action,
                    catalog,
                    (record,),
                ).latest_decision
                reporting = reporting_runs[name]["completion_decision"]
                reason = (
                    CompletionReason.COMPLETE
                    if complete
                    else CompletionReason.REQUIRED_PRESET_MISSING
                )
                expected = (complete, reason.value)
                observed = {
                    "canonical": _decision_verdict(canonical),
                    "desktop": (desktop["completed"], desktop["completionReason"]),
                    "menu": _decision_verdict(menu),
                    "reporting": _decision_verdict(reporting),
                }
                for surface, verdict in observed.items():
                    if verdict != expected:
                        mismatches.append(f"{name}/{surface}: expected {expected}, got {verdict}")
                self.assertEqual(canonical.next_required_preset, next_required)
                self.assertEqual(menu.next_required_preset, next_required)
                self.assertEqual(reporting.next_required_preset, next_required)
                if next_required:
                    self.assertIn(next_required, reporting_runs[name]["mission_evidence"])

        self.assertEqual(len(mismatches), 0, "\n".join(mismatches))

    def test_older_complete_credit_survives_newer_incomplete_diagnostics(self) -> None:
        catalog = ScenarioCatalog.default()
        target = catalog.get("lab01.default")
        action = next(item for item in MENU_ACTIONS if completion_target_id(item) == target.id)

        with tempfile.TemporaryDirectory() as temporary:
            outputs_root = Path(temporary)
            _write_scenario_run(
                outputs_root,
                "older-complete",
                plot=True,
                started_at="2026-07-21T00:00:00+00:00",
                finished_at="2026-07-21T00:01:00+00:00",
            )
            _write_scenario_run(
                outputs_root,
                "newer-incomplete",
                plot=False,
                started_at="2026-07-21T01:00:00+00:00",
                finished_at="2026-07-21T01:01:00+00:00",
            )
            records = ArtifactRepository(outputs_root).list_runs()
            self.assertEqual(
                [record.path.name for record in records],
                ["newer-incomplete", "older-complete"],
            )

            menu = _action_completion_assessment(action, catalog, records)
            desktop = course_progress_payload((target,), Translator("en"), records)
            desktop_item = desktop["path"][0]
            reporting_runs = _discover_runs(outputs_root)
            index_item = _learning_path_item(INDEX_LEARNING_PATH[0], reporting_runs)
            index = write_outputs_index(outputs_root).read_text(encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(["path", "--output-dir", str(outputs_root), "--all"]),
                    0,
                )

        self.assertTrue(menu.complete)
        self.assertEqual(menu.latest_record.path.name, "newer-incomplete")
        self.assertEqual(menu.credited_record.path.name, "older-complete")
        self.assertEqual(menu.latest_decision.primary_reason, CompletionReason.PLOT_MISSING)
        self.assertTrue(menu.credited_decision.complete)

        self.assertTrue(desktop_item["completed"])
        self.assertEqual(
            desktop_item["completionDecision"],
            desktop_item["creditedCompletionDecision"],
        )
        self.assertEqual(
            desktop_item["latestCompletionDecision"]["primary_reason"],
            CompletionReason.PLOT_MISSING.value,
        )
        self.assertTrue(desktop_item["creditedCompletionDecision"]["complete"])
        self.assertEqual(Path(desktop_item["latestRun"]).name, "newer-incomplete")
        self.assertEqual(Path(desktop_item["creditedRun"]).name, "older-complete")

        self.assertTrue(index_item["completed"])
        self.assertEqual(index_item["run"]["name"], "newer-incomplete")
        self.assertEqual(
            index_item["run"]["completion_decision"].primary_reason,
            CompletionReason.PLOT_MISSING,
        )
        self.assertIn(CompletionReason.PLOT_MISSING.value, index)
        self.assertIn("1/12 steps complete", index)
        self.assertIn("Progress: 1/12 complete", stdout.getvalue())
        self.assertIn("Latest-attempt repair: 1 credited step", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
