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
    action_challenge_text,
    action_control_credit_text,
    action_controls_text,
    action_mission_text,
    action_playbook_text,
    action_plan_text,
    action_readiness,
    action_start_steps_text,
    action_viewer_text,
    batch_plan_text,
    batch_readiness,
    command_for_target,
    experience_coverage_next_command,
    experience_coverage_next_label,
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
        _print_experience_coverage(Path(args.output_dir))
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


def _print_experience_coverage(outputs_root: Path) -> None:
    print(experience_coverage_summary_text(outputs_root))
    print(experience_coverage_status_text(outputs_root))
    next_command = experience_coverage_next_command(outputs_root)
    if next_command:
        print(f"Next experience: {experience_coverage_next_label(outputs_root)}")
        print(f"Next command: {next_command}")
    else:
        print("Next experience: Coverage complete")
        print("Next command: replay one saved scenario or run a comparison batch more deeply.")


def _print_learning_path(outputs_root: Path, *, show_all: bool = False) -> None:
    progress_items = learning_path_progress_items(outputs_root)
    print(learning_path_summary_text(progress_items))
    print(learning_path_milestone_text(progress_items))
    next_step = next_learning_path_step(progress_items)
    if next_step is not None:
        print(f"Next step: {learning_path_next_label(outputs_root)}")
        print(f"Next command: {learning_path_next_command(outputs_root)}")
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
    print(f"Next command: {command_for_target(target)}")
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


def _run_next_menu_target(target: MenuAction, *, seed: int | None = None) -> Path:
    config = load_config(target.config_path)
    runner = LABS[target.lab_name]
    return runner(
        config,
        config_path=Path(target.config_path),
        output_dir=None,
        plot=True,
        viewer=True,
        headless=False,
        realtime=True,
        pause_at_end=True,
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
        return

    print(f"Next review folder: {next_output}")
    print(f"Next review status: {next_review_status_text(outputs_root)}")
    entry = _preferred_output_entry(next_output)
    print(f"Next review report: {entry}")
    worksheet = next_output / "worksheet.md"
    if worksheet.exists():
        print(f"Next review worksheet: {worksheet}")
    if open_next:
        _open_path(entry)


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
    if limit > 0 and len(matches) > len(shown):
        print("Tip: use --limit 0 to print all matches.")
    for index, action in enumerate(shown, start=1):
        _print_scenario_card(index, action, details=details)


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
        print(f"   {action_playbook_text(action)}")
        print(f"   {action_viewer_text(action)}")
        control_credit = action_control_credit_text(action)
        if control_credit:
            print(f"   {control_credit}")
        readiness = action_readiness(action)
        print(f"   Setup: {readiness.label}{f' - {readiness.detail}' if readiness.detail else ''}")
    print(f"   Command: {command_for_target(action)}")


def _print_batches(query: str, *, limit: int = 8, details: bool = False) -> None:
    matches = _filter_batch_actions(query)
    shown = matches if limit <= 0 else matches[: max(0, limit)]
    query_text = query.strip() or "all"
    print(f"Batches: showing {len(shown)} of {len(matches)} match(es) for query '{query_text}'.")
    if not matches:
        print("No comparison batches matched. Try: all, lab01, PID, 2DOF, Panda, wall, Cartesian, or compare.")
        return
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
        batch_readiness(action).label,
        batch_readiness(action).detail,
        command_for_target(action),
        "compare comparison batch prediction check worksheet report plots handoff",
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
    print(f"   Command: {command_for_target(action)}")


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
    for line in text.splitlines():
        if line.startswith("- Priority plot: ") and not priority_plot:
            priority_plot = line.removeprefix("- Priority plot: ").strip()
        elif line.startswith("- Read first: ") and not read_first:
            read_first = line.removeprefix("- Read first: ").strip()
        elif line.startswith("- What to check: ") and not what_to_check:
            what_to_check = line.removeprefix("- What to check: ").strip()
        elif line.startswith("- Next proof step: ") and not next_proof_step:
            next_proof_step = line.removeprefix("- Next proof step: ").strip()
        elif line.startswith("- [ ] ") and not first_checklist_item:
            first_checklist_item = line.removeprefix("- [ ] ").strip()

    lines: list[str] = []
    if priority_plot:
        lines.append(f"Priority plot: {_worksheet_relative_path(output_path, priority_plot)}")
    if read_first or what_to_check:
        focus = f"{read_first} - {what_to_check}" if read_first and what_to_check else read_first or what_to_check
        lines.append(f"Review focus: {focus}")
    if next_proof_step:
        lines.append(f"Next proof step: {next_proof_step}")
    if first_checklist_item:
        lines.append(f"Review checklist: {first_checklist_item}")
    return lines


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
    next_command = ""
    for line in text.splitlines():
        if line.startswith("- Next experience: "):
            next_experience = line.removeprefix("- Next experience: ").strip()
        elif line.startswith("- Next command: "):
            next_command = line.removeprefix("- Next command: ").strip()

    lines: list[str] = []
    if next_experience:
        lines.append(f"Next experience: {next_experience}")
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
