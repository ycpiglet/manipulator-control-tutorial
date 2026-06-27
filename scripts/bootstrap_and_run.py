from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MENAGERIE = ROOT / "third_party" / "mujoco_menagerie"


DEFAULT_LABS = [
    ("lab01", "configs/lab01_msd/default.yaml"),
    ("lab02", "configs/lab02_pid/default.yaml"),
    ("lab03", "configs/lab03_2dof/joint_space_2dof.yaml"),
    ("lab04", "configs/lab04_panda/joint_pd.yaml"),
]

VERIFY_VARIANTS = [
    ("lab01", "configs/lab01_msd/underdamped.yaml"),
    ("lab01", "configs/lab01_msd/over_damped.yaml"),
    ("lab02", "configs/lab02_pid/p_low_gain.yaml"),
    ("lab02", "configs/lab02_pid/pd_damped.yaml"),
    ("lab03", "configs/lab03_2dof/task_space_2dof.yaml"),
    ("lab03", "configs/lab03_2dof/singularity_2dof.yaml"),
    ("lab03", "configs/lab03_2dof/dls_singularity_2dof.yaml"),
    ("lab03", "configs/lab03_2dof/trapezoidal.yaml"),
    ("lab03", "configs/lab03_2dof/step.yaml"),
    ("lab04", "configs/lab04_panda/neutral_hold.yaml"),
    ("lab04", "configs/lab04_panda/reach_x.yaml"),
    ("lab04", "configs/lab04_panda/cartesian_reach.yaml"),
    ("lab04", "configs/lab04_panda/wall_soft.yaml"),
    ("lab04", "configs/lab04_panda/wall_stiff.yaml"),
    ("lab04", "configs/lab04_panda/impedance_wall.yaml"),
]

REQUIRED_ARTIFACTS = ("config.yaml", "summary.json", "notes.md", "log.csv", "report.html")
REQUIRED_REPORT_SECTIONS = (
    "Reproduce This Run",
    "Config Highlights",
    "Result Check",
    "Summary",
    "Files",
)
PLOT_REPORT_SECTIONS = ("Plots", "Plot Guide")


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up and run local MuJoCo labs.")
    parser.add_argument("--setup-only", action="store_true", help="Only create .venv and fetch assets.")
    parser.add_argument("--verify", action="store_true", help="Run default labs plus comparison variants.")
    parser.add_argument("--no-plot", action="store_true", help="Skip plot generation.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest and ruff checks.")
    args = parser.parse_args()

    ensure_venv()
    ensure_dependencies()
    ensure_menagerie()

    if args.setup_only:
        print("Setup complete.")
        return 0

    if not args.skip_tests:
        run([str(VENV_PYTHON), "-m", "pytest", "-q"])
        run([str(VENV_PYTHON), "-m", "ruff", "check", "src", "tests"])

    run_set = DEFAULT_LABS + (VERIFY_VARIANTS if args.verify else [])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root_output = ROOT / "outputs" / f"local_run_{stamp}"
    root_output.mkdir(parents=True, exist_ok=True)

    for index, (lab, config) in enumerate(run_set, start=1):
        name = f"{index:02d}_{lab}_{Path(config).stem}"
        command = [
            str(VENV_PYTHON),
            "-m",
            "mclab",
            "run",
            lab,
            "--config",
            config,
            "--headless",
            "--output-dir",
            str(root_output / name),
        ]
        if not args.no_plot:
            command.append("--plot")
        run(command)
        verify_output_artifacts(root_output / name, expect_plots=not args.no_plot)

    print(f"All requested runs completed: {root_output}")
    return 0


def ensure_venv() -> None:
    if VENV_PYTHON.exists():
        return
    run([sys.executable, "-m", "venv", str(ROOT / ".venv")])


def ensure_dependencies() -> None:
    run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(VENV_PYTHON), "-m", "pip", "install", "-e", ".[dev]"])


def ensure_menagerie() -> None:
    if (MENAGERIE / "franka_emika_panda" / "scene.xml").exists():
        return
    target = str(MENAGERIE).replace("\\", "/")
    run(["git", "clone", "--depth", "1", "https://github.com/google-deepmind/mujoco_menagerie.git", target])


def run(command: list[str]) -> None:
    print("\n$ " + " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def verify_output_artifacts(output_dir: Path, *, expect_plots: bool) -> None:
    missing = [name for name in REQUIRED_ARTIFACTS if not (output_dir / name).exists()]
    if not ((output_dir / "states.npz").exists() or (output_dir / "states.json").exists()):
        missing.append("states.npz or states.json")
    if expect_plots and not any((output_dir / "plots").glob("*.png")):
        missing.append("plots/*.png")
    if missing:
        raise RuntimeError(f"Missing output artifact(s) in {output_dir}: {', '.join(missing)}")

    report_html = (output_dir / "report.html").read_text(encoding="utf-8")
    required_sections = list(REQUIRED_REPORT_SECTIONS)
    if expect_plots:
        required_sections.extend(PLOT_REPORT_SECTIONS)
    missing_sections = [section for section in required_sections if section not in report_html]
    if missing_sections:
        raise RuntimeError(
            f"Missing report section(s) in {output_dir / 'report.html'}: "
            f"{', '.join(missing_sections)}"
        )

    print(f"Verified artifacts: {output_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
