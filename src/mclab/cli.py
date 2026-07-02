"""Command-line entry point for running labs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from .batch import ALL_BATCH_NAME, BATCH_SETS, run_all_batches, run_batch
from .config import load_config
from .doctor import doctor_exit_code, format_doctor_report, run_doctor_checks
from .learner_menu import (
    BATCH_ACTIONS,
    BatchMenuAction,
    MenuAction,
    action_activity_mix_text,
    action_challenge_text,
    action_challenge_evidence_text,
    action_compare_batch,
    action_control_credit_text,
    action_controls_text,
    action_course_lines,
    action_evidence_text,
    action_for_output,
    action_followup,
    action_history_text,
    action_latest_output,
    action_latest_evidence_text,
    action_latest_tuned_config,
    action_mission_text,
    action_mission_evidence_text,
    action_next_cue_text,
    action_observation_flow_text,
    action_observation_next_step_text,
    action_playbook_text,
    action_plot_review_text,
    action_plot_text,
    action_plan_text,
    action_preset_evidence_text,
    action_readiness,
    action_replay_text,
    action_start_steps_text,
    action_tags,
    action_viewer_text,
    action_worksheet_text,
    batch_plan_text,
    batch_prediction_check_text,
    batch_readiness,
    batch_viewer_handoff_text,
    command_for_target,
    config_value_preview,
    default_command_for_target,
    experience_coverage_next_command,
    experience_coverage_next_action,
    experience_coverage_next_evidence,
    experience_coverage_next_label,
    experience_coverage_next_mode,
    experience_coverage_next_target,
    experience_coverage_detail_lines,
    experience_coverage_status_text,
    experience_coverage_summary_text,
    filter_menu_actions,
    learning_path_milestone_text,
    learning_path_next_command,
    learning_path_next_label,
    learning_path_progress_items,
    learning_path_progress_text,
    learning_path_summary_text,
    learning_path_target,
    main as learner_menu_main,
    next_learning_path_step,
    next_review_output,
    next_review_status_text,
    parameter_hint,
    prediction_prompt,
    reflection_question,
    review_queue_summary_text,
)
from .labs import lab01_msd, lab02_pid, lab03_2dof, lab04_panda
from .sim.reporting import write_outputs_index


LabRunner = Callable[..., Path]

LABS: dict[str, LabRunner] = {
    "lab01": lab01_msd.run,
    "lab01_msd": lab01_msd.run,
    "msd": lab01_msd.run,
    "mass_spring_damper": lab01_msd.run,
    "lab02": lab02_pid.run,
    "lab02_pid": lab02_pid.run,
    "pid": lab02_pid.run,
    "lab03": lab03_2dof.run,
    "lab03_trajectory": lab03_2dof.run,
    "trajectory": lab03_2dof.run,
    "trajectory_planning": lab03_2dof.run,
    "lab04": lab04_panda.run,
    "lab04_panda": lab04_panda.run,
    "panda": lab04_panda.run,
    "manipulator": lab04_panda.run,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mclab",
        description="MuJoCo Manipulator Control Lab command-line interface.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Learner workflow:\n"
            "  python -m mclab doctor          check setup and see next learner steps\n"
            "  python -m mclab menu            open the guided launcher\n"
            "  python -m mclab coverage        see missing experience types and next command\n"
            "  python -m mclab coverage --details\n"
            "                                  compare all experience modes and evidence cues\n"
            "  python -m mclab params wall     see editable YAML/live-control parameters\n"
            "  python -m mclab next --preview  preview the next recommended step\n"
            "  python -m mclab next            launch the next path step"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="List available labs.")
    subparsers.add_parser("menu", help="Open the learner launcher menu.")
    subparsers.add_parser("doctor", help="Check local setup, packages, configs, assets, and outputs.")

    coverage_parser = subparsers.add_parser(
        "coverage",
        help="Show course experience coverage and the next learner command.",
    )
    coverage_parser.add_argument("--output-dir", default="outputs", help="Outputs root directory.")
    coverage_parser.add_argument(
        "--details",
        action="store_true",
        help="Print mode, focus, evidence, and command for every core experience type.",
    )

    path_parser = subparsers.add_parser(
        "path",
        help="Show recommended learning path progress and the next learner command.",
    )
    path_parser.add_argument("--output-dir", default="outputs", help="Outputs root directory.")
    path_parser.add_argument("--all", action="store_true", help="Print one status line for every path step.")

    next_parser = subparsers.add_parser(
        "next",
        help="Run the next recommended learning path step.",
    )
    next_parser.add_argument("--output-dir", default="outputs", help="Outputs root directory used to choose the step.")
    next_parser.add_argument("--preview", action="store_true", help="Print the next step without running it.")
    next_parser.add_argument("--seed", type=int, help="Random seed for noisy experiments.")

    review_parser = subparsers.add_parser(
        "review",
        help="Show the saved-run review queue and next report to inspect.",
    )
    review_parser.add_argument("--output-dir", default="outputs", help="Outputs root directory.")
    review_parser.add_argument("--open", action="store_true", help="Open the next pending review report.")

    scenarios_parser = subparsers.add_parser(
        "scenarios",
        help="Search learner guided scenarios and print ready-to-run commands.",
    )
    scenarios_parser.add_argument("query", nargs="*", help="Search terms, for example: wall stiffness.")
    scenarios_parser.add_argument("--filter", default="all", help="Experience filter such as hands-on, compare, wall.")
    scenarios_parser.add_argument("--limit", type=int, default=8, help="Maximum matches to print; 0 prints all.")
    scenarios_parser.add_argument(
        "--details",
        action="store_true",
        help="Include playbook, viewer, readiness, and full control-credit cues.",
    )

    params_parser = subparsers.add_parser(
        "params",
        help="Search guided scenarios and print editable parameters, current values, and commands.",
    )
    params_parser.add_argument("query", nargs="*", help="Search terms, for example: wall stiffness.")
    params_parser.add_argument("--filter", default="all", help="Experience filter such as hands-on, compare, wall.")
    params_parser.add_argument("--limit", type=int, default=6, help="Maximum matches to print; 0 prints all.")
    params_parser.add_argument("--values", type=int, default=8, help="Maximum current YAML values per scenario.")

    batches_parser = subparsers.add_parser(
        "batches",
        help="Search learner comparison batches and print ready-to-run commands.",
    )
    batches_parser.add_argument("query", nargs="*", help="Search terms, for example: wall damping.")
    batches_parser.add_argument("--limit", type=int, default=8, help="Maximum matches to print; 0 prints all.")
    batches_parser.add_argument("--details", action="store_true", help="Include readiness details.")

    index_parser = subparsers.add_parser("index", help="Generate the outputs review index.")
    index_parser.add_argument("--output-dir", default="outputs", help="Outputs root directory.")
    index_parser.add_argument("--open", action="store_true", help="Open the generated index after completion.")

    run_parser = subparsers.add_parser("run", help="Run a lab.")
    run_parser.add_argument("lab_name", choices=sorted(LABS), help="Lab to run.")
    run_parser.add_argument("--config", required=True, help="YAML config path.")
    run_mode = run_parser.add_mutually_exclusive_group()
    run_mode.add_argument("--viewer", action="store_true", help="Open MuJoCo viewer without side panels.")
    run_mode.add_argument("--headless", action="store_true", help="Run without viewer.")
    run_parser.add_argument("--realtime", action="store_true", help="Pace viewer runs near wall-clock time.")
    run_parser.add_argument("--pause-at-end", action="store_true", help="Keep viewer open after the run completes.")
    run_parser.add_argument("--plot", action="store_true", help="Save standard plots.")
    run_parser.add_argument(
        "--plots",
        help="Plot preset or comma-separated plot names, for example: essential or position,error.",
    )
    run_parser.add_argument("--output-dir", help="Output directory override.")
    run_parser.add_argument("--open-report", action="store_true", help="Open the run report after completion.")
    run_parser.add_argument("--seed", type=int, help="Random seed for noisy experiments.")

    batch_parser = subparsers.add_parser("batch", help="Run a learner comparison batch.")
    batch_parser.add_argument(
        "batch_name",
        choices=sorted([*BATCH_SETS, ALL_BATCH_NAME]),
        help="Batch set to run.",
    )
    batch_parser.add_argument("--output-dir", help="Output directory override.")
    batch_parser.add_argument("--no-plot", action="store_true", help="Skip plot image generation.")
    batch_parser.add_argument("--open-report", action="store_true", help="Open the batch report after completion.")
    batch_parser.add_argument("--seed", type=int, help="Random seed for noisy experiments.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {None, "list"}:
        print("Learner entry points:")
        print("  python -m mclab doctor          # check setup and see next learner steps")
        print("  python -m mclab menu            # open the guided launcher")
        print("  python -m mclab coverage        # see missing experience types and next command")
        print("  python -m mclab coverage --details")
        print("                                 # compare all experience modes and evidence cues")
        print("  python -m mclab params wall     # see editable YAML/live-control parameters")
        print("  python -m mclab next --preview  # preview the next recommended step")
        print("  python -m mclab next            # launch the next path step")
        print("Available labs:")
        for name in sorted(LABS):
            print(f"  {name}")
        print("Available batches:")
        for name in sorted([*BATCH_SETS, ALL_BATCH_NAME]):
            print(f"  {name}")
        return 0

    if args.command == "menu":
        return learner_menu_main()

    if args.command == "doctor":
        checks = run_doctor_checks()
        print(format_doctor_report(checks))
        return doctor_exit_code(checks)

    if args.command == "coverage":
        _print_experience_coverage(Path(args.output_dir), details=args.details)
        return 0

    if args.command == "path":
        _print_learning_path(Path(args.output_dir), show_all=args.all)
        return 0

    if args.command == "next":
        return _run_next_learning_path(Path(args.output_dir), preview=args.preview, seed=args.seed)

    if args.command == "review":
        _print_review_queue(Path(args.output_dir), open_next=args.open)
        return 0

    if args.command == "scenarios":
        _print_scenarios(" ".join(args.query), experience_filter=args.filter, limit=args.limit, details=args.details)
        return 0

    if args.command == "params":
        _print_params(" ".join(args.query), experience_filter=args.filter, limit=args.limit, max_values=args.values)
        return 0

    if args.command == "batches":
        _print_batches(" ".join(args.query), limit=args.limit, details=args.details)
        return 0

    if args.command == "index":
        index_path = write_outputs_index(Path(args.output_dir))
        print(f"Outputs index: {index_path}")
        if args.open:
            _open_path(index_path)
        return 0

    if args.command == "run":
        _validate_run_args(parser, args)
        config = load_config(args.config)
        runner = LABS[args.lab_name]
        output_path = runner(
            config,
            config_path=Path(args.config),
            output_dir=Path(args.output_dir) if args.output_dir else None,
            plot=args.plot,
            viewer=args.viewer,
            headless=args.headless,
            realtime=args.realtime,
            pause_at_end=args.pause_at_end,
            plot_selection=args.plots,
            seed=args.seed,
        )
        _print_output_summary("Run", output_path)
        if args.open_report:
            _open_path(_preferred_output_entry(output_path))
        return 0

    if args.command == "batch":
        batch_kwargs = {
            "output_dir": Path(args.output_dir) if args.output_dir else None,
            "plot": not args.no_plot,
            "seed": args.seed,
        }
        if args.batch_name == ALL_BATCH_NAME:
            output_path = run_all_batches(**batch_kwargs)
        else:
            output_path = run_batch(args.batch_name, **batch_kwargs)
        _print_output_summary("Batch", output_path)
        if args.open_report:
            _open_path(_preferred_output_entry(output_path))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _validate_run_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.plots and not args.plot:
        parser.error("--plots requires --plot.")
    viewer_only_flags = []
    if args.realtime:
        viewer_only_flags.append("--realtime")
    if args.pause_at_end:
        viewer_only_flags.append("--pause-at-end")
    if viewer_only_flags and not args.viewer:
        joined = " and ".join(viewer_only_flags)
        verb = "requires" if len(viewer_only_flags) == 1 else "require"
        parser.error(f"{joined} {verb} --viewer.")


def _preferred_output_entry(output_path: Path) -> Path:
    report = output_path / "report.html"
    if report.exists():
        return report
    index = output_path / "index.html"
    if index.exists():
        return index
    return output_path


def _print_output_summary(kind: str, output_path: Path) -> None:
    print(f"{kind} complete: {output_path}")
    for line in _output_artifact_lines(output_path):
        print(f"  {line}")


def _print_experience_coverage(outputs_root: Path, *, details: bool = False) -> None:
    print(experience_coverage_summary_text(outputs_root))
    print(experience_coverage_status_text(outputs_root))
    if details:
        for line in experience_coverage_detail_lines(outputs_root):
            print(line)
    next_command = experience_coverage_next_command(outputs_root)
    if next_command:
        print(f"Next experience: {experience_coverage_next_label(outputs_root)}")
        next_mode = experience_coverage_next_mode(outputs_root)
        if next_mode:
            print(f"Next mode: {next_mode}")
        next_action = experience_coverage_next_action(outputs_root)
        if next_action:
            print(f"Next action: {next_action}")
        next_evidence = experience_coverage_next_evidence(outputs_root)
        if next_evidence:
            print(f"Evidence needed: {next_evidence}")
        print(f"Next command: {next_command}")
        next_target = experience_coverage_next_target(outputs_root)
        if next_target is not None:
            _print_next_target_guide(next_target, outputs_root, include_viewer=False)
    else:
        print("Next experience: Coverage complete")
        _print_learning_path_after_coverage_complete(outputs_root)


def _print_learning_path_after_coverage_complete(outputs_root: Path) -> None:
    progress_items = learning_path_progress_items(outputs_root)
    print(learning_path_summary_text(progress_items))
    print(learning_path_milestone_text(progress_items))
    next_step = next_learning_path_step(progress_items)
    if next_step is None:
        print("Next path step: Course path complete")
        print("Next command: open outputs/index.html or rerun a comparison batch for deeper review.")
        return
    target = learning_path_target(next_step)
    print(f"Next path step: {learning_path_next_label(outputs_root)}")
    print(f"Next command: {learning_path_next_command(outputs_root)}")
    _print_next_target_guide(target, outputs_root, include_viewer=_target_default_opens_viewer(target))


def _print_learning_path(outputs_root: Path, *, show_all: bool = False) -> None:
    progress_items = learning_path_progress_items(outputs_root)
    print(learning_path_summary_text(progress_items))
    print(learning_path_milestone_text(progress_items))
    next_step = next_learning_path_step(progress_items)
    if next_step is not None:
        target = learning_path_target(next_step)
        print(f"Next step: {learning_path_next_label(outputs_root)}")
        print(f"Next command: {learning_path_next_command(outputs_root)}")
        _print_next_target_guide(target, outputs_root, include_viewer=_target_default_opens_viewer(target))
    else:
        print("Next step: Course path complete")
        print("Next command: open outputs/index.html or rerun a comparison batch for deeper review.")
    if show_all:
        print("Path map:")
        for step, progress in progress_items:
            status_line = _learning_path_status_line(step, progress)
            print(f"  {step.title}: {status_line}")


def _learning_path_status_line(step: object, progress: object) -> str:
    for line in learning_path_progress_text(step, progress).splitlines():
        if line.startswith("Status: "):
            return line.removeprefix("Status: ")
    return "Status unavailable"


def _run_next_learning_path(outputs_root: Path, *, preview: bool = False, seed: int | None = None) -> int:
    progress_items = learning_path_progress_items(outputs_root)
    next_step = next_learning_path_step(progress_items)
    print(learning_path_summary_text(progress_items))
    print(learning_path_milestone_text(progress_items))
    if next_step is None:
        print("Next step: Course path complete")
        print("Next command: open outputs/index.html or rerun a comparison batch for deeper review.")
        return 0

    target = learning_path_target(next_step)
    print(f"Next step: {next_step.title}")
    print(f"Next command: {default_command_for_target(target)}")
    _print_next_target_guide(target, outputs_root, include_viewer=_target_default_opens_viewer(target))
    if preview:
        return 0

    print(f"Running next step: {target.group} - {target.label}")
    if isinstance(target, BatchMenuAction):
        output_path = _run_next_batch_target(target, seed=seed)
        _print_output_summary("Batch", output_path)
    else:
        output_path = _run_next_menu_target(target, seed=seed)
        _print_output_summary("Run", output_path)
    _open_path(_preferred_output_entry(output_path))
    return 0


def _print_next_target_guide(
    target: MenuAction | BatchMenuAction,
    outputs_root: Path,
    *,
    include_viewer: bool = True,
) -> None:
    print(f"Next guide: {target.group} - {target.label}")
    if isinstance(target, BatchMenuAction):
        readiness = batch_readiness(target)
        lines = [
            batch_plan_text(target),
            *action_course_lines(target),
            action_mission_text(target),
            action_playbook_text(target),
            action_start_steps_text(target),
            action_challenge_text(target),
            action_worksheet_text(target, outputs_root),
            action_plot_text(target, outputs_root),
            action_plot_review_text(target, outputs_root),
            batch_prediction_check_text(target, outputs_root),
            batch_viewer_handoff_text(target),
            f"Setup: {readiness.label}{f' - {readiness.detail}' if readiness.detail else ''}",
        ]
    else:
        readiness = action_readiness(target)
        lines = [
            action_plan_text(target),
            *action_course_lines(target),
            action_mission_text(target),
            action_playbook_text(target),
            f"Try: {target.try_this}",
            f"Change: {parameter_hint(target)}",
            config_value_preview(target, max_items=8),
            prediction_prompt(target),
            reflection_question(target),
            f"Watch: {target.watch}",
            action_start_steps_text(target),
            action_challenge_text(target),
            action_controls_text(target),
        ]
        if include_viewer:
            lines.append(action_viewer_text(target))
        control_credit = action_control_credit_text(target)
        if control_credit:
            lines.append(control_credit)
        lines.extend(
            [
                f"Setup: {readiness.label}{f' - {readiness.detail}' if readiness.detail else ''}",
                action_next_cue_text(target, outputs_root),
            ]
        )
    for line in lines:
        print(f"  {line}")


def _target_default_opens_viewer(target: MenuAction | BatchMenuAction) -> bool:
    return isinstance(target, MenuAction) and "hands-on" in action_tags(target)


def _run_next_menu_target(target: MenuAction, *, seed: int | None = None) -> Path:
    config = load_config(target.config_path)
    runner = LABS[target.lab_name]
    opens_viewer = _target_default_opens_viewer(target)
    return runner(
        config,
        config_path=Path(target.config_path),
        output_dir=None,
        plot=True,
        viewer=opens_viewer,
        headless=not opens_viewer,
        realtime=opens_viewer,
        pause_at_end=opens_viewer,
        plot_selection=target.plots,
        seed=seed,
    )


def _run_next_batch_target(target: BatchMenuAction, *, seed: int | None = None) -> Path:
    if target.batch_name == ALL_BATCH_NAME:
        return run_all_batches(seed=seed)
    return run_batch(target.batch_name, seed=seed)


def _print_review_queue(outputs_root: Path, *, open_next: bool = False) -> None:
    print(review_queue_summary_text(outputs_root))
    next_output = next_review_output(outputs_root)
    if next_output is None:
        print("Next review: none")
        _print_review_path_context(outputs_root)
        return

    print(f"Next review folder: {next_output}")
    print(f"Next review status: {next_review_status_text(outputs_root)}")
    entry = _preferred_output_entry(next_output)
    print(f"Next review report: {entry}")
    worksheet = next_output / "worksheet.md"
    if worksheet.exists():
        print(f"Next review worksheet: {worksheet}")
    action = action_for_output(next_output)
    if action is not None:
        print(f"Next review action: {action.group} - {action.label}")
        print(f"Repair command: {default_command_for_target(action)}")
        latest_evidence = action_latest_evidence_text(action, outputs_root)
        if latest_evidence != "Latest evidence: None yet":
            print(latest_evidence)
        observation_next = action_observation_next_step_text(action, outputs_root)
        if observation_next:
            print(observation_next)
        print(action_plot_review_text(action, outputs_root))
    _print_review_path_context(outputs_root)
    if open_next:
        _open_path(entry)


def _print_review_path_context(outputs_root: Path) -> None:
    progress_items = learning_path_progress_items(outputs_root)
    next_step = next_learning_path_step(progress_items)
    if next_step is None:
        print("Course path next: Course path complete")
        print("Course path command: open outputs/index.html or rerun a comparison batch for deeper review.")
        return
    print(f"Course path next: {learning_path_next_label(outputs_root)}")
    print(f"Course path command: {learning_path_next_command(outputs_root)}")


def _print_scenarios(query: str, *, experience_filter: str = "all", limit: int = 8, details: bool = False) -> None:
    matches = filter_menu_actions(query, experience_filter=experience_filter)
    shown = matches if limit <= 0 else matches[: max(0, limit)]
    query_text = query.strip() or "all"
    print(
        f"Scenarios: showing {len(shown)} of {len(matches)} match(es) "
        f"for query '{query_text}' with filter '{experience_filter}'."
    )
    if not matches:
        print("No guided scenarios matched. Try: intro, hands-on, wall, PID, 2DOF, singularity, or compare.")
        return
    print(
        "Discovery tips: try `python -m mclab scenarios wall --filter hands-on --details`, "
        "`python -m mclab scenarios singularity --details`, or "
        "`python -m mclab scenarios prediction live target --details`."
    )
    if limit > 0 and len(matches) > len(shown):
        print("Tip: use --limit 0 to print all matches.")
    for index, action in enumerate(shown, start=1):
        _print_scenario_card(index, action, details=details)


def _print_params(query: str, *, experience_filter: str = "all", limit: int = 6, max_values: int = 8) -> None:
    matches = filter_menu_actions(query, experience_filter=experience_filter)
    shown = matches if limit <= 0 else matches[: max(0, limit)]
    query_text = query.strip() or "all"
    print(
        f"Parameter guide: showing {len(shown)} of {len(matches)} match(es) "
        f"for query '{query_text}' with filter '{experience_filter}'."
    )
    if not matches:
        print("No guided scenarios matched. Try: wall, PID, DLS, damping, stiffness, target, torque, or hands-on.")
        return
    print(
        "Control surface: edit YAML for auto/comparison runs; use MCLab Interaction sliders, presets, "
        "or buttons for hands-on runs. MuJoCo side panels stay hidden."
    )
    print(
        "Discovery tips: try `python -m mclab params wall --filter hands-on`, "
        "`python -m mclab params PID`, or `python -m mclab params DLS --limit 0`."
    )
    if limit > 0 and len(matches) > len(shown):
        print("Tip: use --limit 0 to print all matches.")
    for index, action in enumerate(shown, start=1):
        _print_params_card(index, action, max_values=max_values)


def _print_params_card(index: int, action: MenuAction, *, max_values: int = 8) -> None:
    print(f"{index}. {action.group} - {action.label}")
    print(f"   Config: {action.config_path}")
    print(f"   Change: {parameter_hint(action)}")
    print(f"   {config_value_preview(action, max_items=max(1, max_values))}")
    print(f"   {action_controls_text(action)}")
    control_credit = action_control_credit_text(action)
    if control_credit:
        print(f"   {control_credit}")
    print(f"   {prediction_prompt(action)}")
    print(f"   {action_start_steps_text(action)}")
    for command_line in _scenario_primary_command_lines(action):
        print(f"   {command_line}")


def _print_scenario_card(index: int, action: MenuAction, *, details: bool = False) -> None:
    print(f"{index}. {action.group} - {action.label}")
    print(f"   {action_plan_text(action)}")
    print(f"   {action_mission_text(action)}")
    print(f"   {action_start_steps_text(action)}")
    print(f"   {action_challenge_text(action)}")
    controls = action_controls_text(action)
    if controls:
        print(f"   {controls}")
    if details:
        for course_line in _scenario_course_lines(action):
            print(f"   {course_line}")
        print(f"   {action_playbook_text(action)}")
        print(f"   Try: {action.try_this}")
        print(f"   Change: {parameter_hint(action)}")
        print(f"   {config_value_preview(action, max_items=8)}")
        print(f"   {prediction_prompt(action)}")
        print(f"   {reflection_question(action)}")
        print(f"   Watch: {action.watch}")
        print(f"   {action_viewer_text(action)}")
        control_credit = action_control_credit_text(action)
        if control_credit:
            print(f"   {control_credit}")
        print(f"   {action_history_text(action)}")
        for artifact_line in _scenario_latest_artifact_lines(action):
            print(f"   {artifact_line}")
        print(f"   {action_mission_evidence_text(action)}")
        print(f"   {action_challenge_evidence_text(action)}")
        print(f"   {action_evidence_text(action)}")
        print(f"   {action_latest_evidence_text(action)}")
        observation_flow = action_observation_flow_text(action)
        if observation_flow:
            print(f"   {observation_flow}")
        observation_next = action_observation_next_step_text(action)
        if observation_next:
            print(f"   {observation_next}")
        preset_evidence = action_preset_evidence_text(action)
        if preset_evidence:
            print(f"   {preset_evidence}")
        activity_mix = action_activity_mix_text(action)
        if activity_mix:
            print(f"   {activity_mix}")
        print(f"   {action_next_cue_text(action)}")
        for command_line in _scenario_next_command_lines(action):
            print(f"   {command_line}")
        print(f"   {action_plot_text(action)}")
        print(f"   {action_plot_review_text(action)}")
        print(f"   {action_worksheet_text(action)}")
        print(f"   {action_replay_text(action)}")
        replay_command = _scenario_replay_command_line(action)
        if replay_command:
            print(f"   {replay_command}")
        readiness = action_readiness(action)
        print(f"   Setup: {readiness.label}{f' - {readiness.detail}' if readiness.detail else ''}")
    for command_line in _scenario_primary_command_lines(action):
        print(f"   {command_line}")


def _scenario_primary_command_lines(action: MenuAction) -> list[str]:
    if "hands-on" in action_tags(action):
        return [f"Command: {command_for_target(action)}"]

    return [
        f"Command: {default_command_for_target(action)}",
        f"Viewer rerun: {command_for_target(action)}",
    ]


def _scenario_recommended_command(action: MenuAction) -> str:
    return default_command_for_target(action)


def _scenario_latest_artifact_lines(action: MenuAction) -> list[str]:
    latest = action_latest_output(action)
    if latest is None:
        return ["Report: Not saved yet", "Folder: Not saved yet"]
    entry = _preferred_output_entry(latest)
    label = "Report" if (latest / "report.html").exists() else "Entry"
    return [f"{label}: Latest {entry}", f"Folder: Latest {latest}"]


def _scenario_replay_command_line(action: MenuAction) -> str:
    tuned_config = action_latest_tuned_config(action)
    if tuned_config is None:
        return ""
    parts = [
        "python",
        "-m",
        "mclab",
        "run",
        action.lab_name,
        "--config",
        str(tuned_config),
        "--viewer",
        "--realtime",
        "--pause-at-end",
        "--plot",
    ]
    if action.plots:
        parts.extend(["--plots", action.plots])
    parts.append("--open-report")
    return f"Replay command: {' '.join(parts)}"


def _scenario_next_command_lines(action: MenuAction) -> list[str]:
    followup = action_followup(action)
    if isinstance(followup, MenuAction):
        followup_command = _scenario_recommended_command(followup)
    else:
        followup_command = command_for_target(followup)
    lines = [f"Next command: {followup.group} - {followup.label} -> {followup_command}"]

    compare = action_compare_batch(action)
    compare_command = command_for_target(compare)
    if compare_command != followup_command:
        lines.append(f"Compare command: {compare.group} - {compare.label} -> {compare_command}")
    return lines


def _scenario_course_lines(action: MenuAction) -> list[str]:
    return action_course_lines(action)


def _print_batches(query: str, *, limit: int = 8, details: bool = False) -> None:
    matches = _filter_batch_actions(query)
    shown = matches if limit <= 0 else matches[: max(0, limit)]
    query_text = query.strip() or "all"
    print(f"Batches: showing {len(shown)} of {len(matches)} match(es) for query '{query_text}'.")
    if not matches:
        print("No comparison batches matched. Try: all, lab01, PID, 2DOF, Panda, wall, Cartesian, or compare.")
        return
    print(
        "Discovery tips: try `python -m mclab batches wall --details`, "
        "`python -m mclab batches 2DOF --details`, or "
        "`python -m mclab batches all --details`."
    )
    if limit > 0 and len(matches) > len(shown):
        print("Tip: use --limit 0 to print all matches.")
    for index, action in enumerate(shown, start=1):
        _print_batch_card(index, action, details=details)


def _filter_batch_actions(query: str) -> tuple[BatchMenuAction, ...]:
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return BATCH_ACTIONS
    matches = [action for action in BATCH_ACTIONS if _batch_matches_terms(action, terms)]
    return tuple(sorted(matches, key=lambda action: _batch_match_sort_key(action, terms)))


def _batch_matches_terms(action: BatchMenuAction, terms: list[str]) -> bool:
    fields = [
        action.group,
        action.label,
        action.batch_name,
        action.description,
        action.try_this,
        action.watch,
        batch_plan_text(action),
        action_mission_text(action),
        action_playbook_text(action),
        action_start_steps_text(action),
        action_challenge_text(action),
        " ".join(action_course_lines(action)),
        batch_readiness(action).label,
        batch_readiness(action).detail,
        command_for_target(action),
        "compare comparison batch prediction check worksheet report plots handoff course step done when",
    ]
    text = " ".join(fields).lower()
    return all(term in text for term in terms)


def _batch_match_sort_key(action: BatchMenuAction, terms: list[str]) -> tuple[int, int, str]:
    primary = " ".join((action.label, action.batch_name)).lower()
    secondary = " ".join((action.description, action.try_this, action.watch)).lower()
    primary_hits = sum(term in primary for term in terms)
    secondary_hits = sum(term in secondary for term in terms)
    return (-primary_hits, -secondary_hits, action.label)


def _print_batch_card(index: int, action: BatchMenuAction, *, details: bool = False) -> None:
    print(f"{index}. {action.group} - {action.label}")
    print(f"   {batch_plan_text(action)}")
    print(f"   {action_mission_text(action)}")
    print(f"   {action_start_steps_text(action)}")
    print(f"   {action_challenge_text(action)}")
    if details:
        readiness = batch_readiness(action)
        print(f"   Setup: {readiness.label}{f' - {readiness.detail}' if readiness.detail else ''}")
        for course_line in action_course_lines(action):
            print(f"   {course_line}")
        print(f"   {action_playbook_text(action)}")
        print(f"   {action_history_text(action)}")
        print(f"   {action_worksheet_text(action)}")
        print(f"   {action_plot_text(action)}")
        print(f"   {action_plot_review_text(action)}")
        print(f"   {batch_prediction_check_text(action)}")
        print(f"   {_batch_handoff_detail_text(action)}")
    print(f"   Command: {command_for_target(action)}")


def _batch_handoff_detail_text(action: BatchMenuAction) -> str:
    latest = action_latest_output(action)
    if latest is None:
        return batch_viewer_handoff_text(action)
    start, command = _worksheet_viewer_handoff(latest)
    if command:
        handoff = f"{start} -> {command}" if start else command
        return f"Handoff: {handoff}"
    if action.batch_name == ALL_BATCH_NAME:
        course_handoff = _course_batch_handoff_detail(latest)
        if course_handoff:
            return course_handoff
    report = latest / "report.html"
    if report.exists():
        return f"Handoff: Latest {report}#viewer-handoff"
    return "Handoff: Latest batch output has no report.html; rerun the batch or open the worksheet."


def _output_artifact_lines(output_path: Path) -> list[str]:
    lines: list[str] = []
    for label, filename in (
        ("Report", "report.html"),
        ("Worksheet", "worksheet.md"),
        ("Index", "index.html"),
    ):
        artifact = output_path / filename
        if artifact.exists():
            lines.append(f"{label}: {artifact}")
    parent_index = output_path.parent / "index.html"
    if parent_index.exists() and parent_index != output_path / "index.html":
        lines.append(f"All reports index: {parent_index}")
    lines.extend(_plot_artifact_lines(output_path, "plots", "Plots"))
    lines.extend(_plot_artifact_lines(output_path, "comparison_plots", "Comparison plots"))
    lines.extend(_worksheet_review_artifact_lines(output_path))
    lines.extend(_next_experience_artifact_lines(output_path))
    return lines


def _worksheet_review_artifact_lines(output_path: Path) -> list[str]:
    worksheet = output_path / "worksheet.md"
    if not worksheet.exists():
        return []
    try:
        text = worksheet.read_text(encoding="utf-8")
    except OSError:
        return []

    priority_plot = ""
    read_first = ""
    what_to_check = ""
    next_proof_step = ""
    first_checklist_item = ""
    has_prediction_check = False
    viewer_handoff_start, viewer_handoff_command = _viewer_handoff_from_worksheet_text(text)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "## Prediction Check":
            has_prediction_check = True
        if stripped.startswith("## "):
            continue

        if stripped.startswith("- Priority plot: ") and not priority_plot:
            priority_plot = stripped.removeprefix("- Priority plot: ").strip()
        elif stripped.startswith("- Read first: ") and not read_first:
            read_first = stripped.removeprefix("- Read first: ").strip()
        elif stripped.startswith("- What to check: ") and not what_to_check:
            what_to_check = stripped.removeprefix("- What to check: ").strip()
        elif stripped.startswith("- Next proof step: ") and not next_proof_step:
            next_proof_step = stripped.removeprefix("- Next proof step: ").strip()
        elif stripped.startswith("- [ ] ") and not first_checklist_item:
            first_checklist_item = stripped.removeprefix("- [ ] ").strip()

    lines: list[str] = []
    if priority_plot:
        lines.append(f"Priority plot: {_worksheet_relative_path(output_path, priority_plot)}")
    if read_first or what_to_check:
        focus = f"{read_first} - {what_to_check}" if read_first and what_to_check else read_first or what_to_check
        lines.append(f"Review focus: {focus}")
    if next_proof_step:
        lines.append(f"Next proof step: {next_proof_step}")
    if has_prediction_check:
        lines.append("Prediction check: Mark Matched, Partly matched, or Surprised in worksheet.md.")
    if viewer_handoff_command:
        handoff = (
            f"{viewer_handoff_start} -> {viewer_handoff_command}"
            if viewer_handoff_start
            else viewer_handoff_command
        )
        lines.append(f"Viewer handoff: {handoff}")
    if first_checklist_item:
        lines.append(f"Review checklist: {first_checklist_item}")
    return lines


def _worksheet_viewer_handoff(output_path: Path) -> tuple[str, str]:
    worksheet = output_path / "worksheet.md"
    if not worksheet.exists():
        return "", ""
    try:
        text = worksheet.read_text(encoding="utf-8")
    except OSError:
        return "", ""
    return _viewer_handoff_from_worksheet_text(text)


def _course_batch_handoff_detail(output_path: Path) -> str:
    linked_handoff = _course_linked_viewer_handoff(output_path)
    if linked_handoff:
        child_output = _linked_batch_output_path(output_path, linked_handoff)
        if child_output is not None:
            start, command = _worksheet_viewer_handoff(child_output)
            if command:
                label = child_output.name
                handoff = f"{label} / {start} -> {command}" if start else f"{label} -> {command}"
                return f"Handoff: {handoff}"
        return f"Handoff: Open linked batch handoff: {linked_handoff}"

    for batch_name in BATCH_SETS:
        child_output = output_path / batch_name
        start, command = _worksheet_viewer_handoff(child_output)
        if command:
            handoff = f"{batch_name} / {start} -> {command}" if start else f"{batch_name} -> {command}"
            return f"Handoff: {handoff}"
    return "Handoff: Open the course worksheet, then follow a linked batch Viewer Handoff."


def _course_linked_viewer_handoff(output_path: Path) -> str:
    worksheet = output_path / "worksheet.md"
    if not worksheet.exists():
        return ""
    try:
        text = worksheet.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Viewer handoff: "):
            value = stripped.removeprefix("- Viewer handoff: ").strip()
            if value and value.lower() != "n/a":
                return value
    return ""


def _linked_batch_output_path(output_path: Path, linked_handoff: str) -> Path | None:
    report_part = linked_handoff.split("#", 1)[0].strip()
    if not report_part:
        return None
    linked_path = Path(report_part)
    if not linked_path.is_absolute():
        linked_path = output_path / linked_path
    return linked_path.parent if linked_path.name == "report.html" else linked_path


def _viewer_handoff_from_worksheet_text(text: str) -> tuple[str, str]:
    in_viewer_handoff = False
    handoff_start = ""
    handoff_command = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_viewer_handoff = stripped == "## Viewer Handoff"
            continue
        if not in_viewer_handoff:
            continue
        if stripped.startswith("- Start with: ") and not handoff_start:
            handoff_start = stripped.removeprefix("- Start with: ").strip()
        elif stripped.startswith("- Viewer rerun: ") and not handoff_command:
            handoff_command = stripped.removeprefix("- Viewer rerun: ").strip()
    return handoff_start, handoff_command


def _worksheet_relative_path(output_path: Path, value: str) -> Path | str:
    path = Path(value)
    if path.is_absolute():
        return path
    return output_path / path


def _next_experience_artifact_lines(output_path: Path) -> list[str]:
    worksheet = output_path / "worksheet.md"
    if not worksheet.exists():
        return []
    try:
        text = worksheet.read_text(encoding="utf-8")
    except OSError:
        return []

    next_experience = ""
    next_mode = ""
    next_action = ""
    evidence_needed = ""
    next_command = ""
    for line in text.splitlines():
        if line.startswith("- Next experience: "):
            next_experience = line.removeprefix("- Next experience: ").strip()
        elif line.startswith("- Next mode: "):
            next_mode = line.removeprefix("- Next mode: ").strip()
        elif line.startswith("- Next action: "):
            next_action = line.removeprefix("- Next action: ").strip()
        elif line.startswith("- Evidence needed: "):
            evidence_needed = line.removeprefix("- Evidence needed: ").strip()
        elif line.startswith("- Next command: "):
            next_command = line.removeprefix("- Next command: ").strip()

    lines: list[str] = []
    if next_experience:
        lines.append(f"Next experience: {next_experience}")
    if next_mode:
        lines.append(f"Next mode: {next_mode}")
    if next_action:
        lines.append(f"Next action: {next_action}")
    if evidence_needed:
        lines.append(f"Evidence needed: {evidence_needed}")
    if next_command:
        lines.append(f"Next command: {next_command}")
    return lines


def _plot_artifact_lines(output_path: Path, directory_name: str, label: str) -> list[str]:
    plot_dir = output_path / directory_name
    if not plot_dir.exists():
        return []
    plots = sorted(plot_dir.glob("*.png"))
    if not plots:
        return []
    first_plot = plots[0]
    return [f"{label}: {plot_dir} ({len(plots)} PNG; first: {first_plot.name})"]


def _open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        import os

        os.startfile(str(path))
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])
