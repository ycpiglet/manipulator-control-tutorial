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
from .learner_menu import main as learner_menu_main
from .labs import lab01_msd, lab02_pid, lab03_2dof, lab04_panda


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

    run_parser = subparsers.add_parser("run", help="Run a lab.")
    run_parser.add_argument("lab_name", choices=sorted(LABS), help="Lab to run.")
    run_parser.add_argument("--config", required=True, help="YAML config path.")
    run_parser.add_argument("--viewer", action="store_true", help="Open MuJoCo viewer without side panels.")
    run_parser.add_argument("--headless", action="store_true", help="Run without viewer.")
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

    if args.command == "run":
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
        print(f"Run complete: {output_path}")
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
        print(f"Batch complete: {output_path}")
        if args.open_report:
            _open_path(_preferred_output_entry(output_path))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _preferred_output_entry(output_path: Path) -> Path:
    report = output_path / "report.html"
    if report.exists():
        return report
    index = output_path / "index.html"
    if index.exists():
        return index
    return output_path


def _open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        import os

        os.startfile(str(path))
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])
