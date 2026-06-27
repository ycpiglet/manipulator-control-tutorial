"""Learner-facing launcher menu for local MuJoCo labs."""

from __future__ import annotations

import subprocess
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any

from mclab.config import PROJECT_ROOT
from mclab.sim.reporting import write_outputs_index

RUN_COMPLETE_PREFIX = "Run complete:"
DOC_PATHS = {
    "lab01": "docs/lab01_mass_spring_damper.md",
    "lab02": "docs/lab02_pid_control.md",
    "lab03": "docs/lab03_trajectory_planning.md",
    "lab04": "docs/lab04_panda_manipulator.md",
}


@dataclass(frozen=True)
class MenuAction:
    group: str
    label: str
    lab_name: str
    config_path: str
    plots: str
    description: str
    try_this: str
    watch: str


MENU_ACTIONS: tuple[MenuAction, ...] = (
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Auto demo",
        lab_name="lab01",
        config_path="configs/lab01_msd/default.yaml",
        plots="essential",
        description="Watch free response and force/position plots.",
        try_this="Start here and compare position, velocity, and applied force.",
        watch="How quickly the mass returns near zero.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Underdamped",
        lab_name="lab01",
        config_path="configs/lab01_msd/underdamped.yaml",
        plots="essential",
        description="Low damping makes the mass oscillate before settling.",
        try_this="Run this after Auto demo and compare the number of swings.",
        watch="Large overshoot and slow energy decay.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Overdamped",
        lab_name="lab01",
        config_path="configs/lab01_msd/over_damped.yaml",
        plots="essential",
        description="High damping removes oscillation but slows the return.",
        try_this="Run after Underdamped and compare settling behavior.",
        watch="Little overshoot, slower motion.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="High stiffness",
        lab_name="lab01",
        config_path="configs/lab01_msd/high_stiffness.yaml",
        plots="essential",
        description="A stiffer spring creates faster, sharper motion.",
        try_this="Compare against Low stiffness.",
        watch="Higher frequency motion and larger force changes.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Low stiffness",
        lab_name="lab01",
        config_path="configs/lab01_msd/low_stiffness.yaml",
        plots="essential",
        description="A softer spring responds more slowly.",
        try_this="Compare against High stiffness.",
        watch="Lower frequency motion and slower return.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Interactive",
        lab_name="lab01",
        config_path="configs/lab01_msd/interactive_pull.yaml",
        plots="essential",
        description="Push the mass and tune mass, damping, stiffness.",
        try_this="Click Pull/Push, then move damping and stiffness sliders.",
        watch="Live status position, force, and total energy.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Auto demo",
        lab_name="lab02",
        config_path="configs/lab02_pid/default.yaml",
        plots="essential",
        description="Watch PID tracking, error, and force.",
        try_this="Start here and use the plots as the baseline response.",
        watch="Tracking error and control force.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Low P gain",
        lab_name="lab02",
        config_path="configs/lab02_pid/p_low_gain.yaml",
        plots="essential",
        description="Low proportional gain responds gently but slowly.",
        try_this="Compare against High P gain.",
        watch="Slow rise and persistent error.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="High P gain",
        lab_name="lab02",
        config_path="configs/lab02_pid/p_high_gain.yaml",
        plots="essential",
        description="High proportional gain reacts strongly.",
        try_this="Compare against Low P gain.",
        watch="Overshoot, oscillation, and larger force.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="PD damping",
        lab_name="lab02",
        config_path="configs/lab02_pid/pd_damped.yaml",
        plots="essential",
        description="Derivative action damps the P response.",
        try_this="Run after High P gain.",
        watch="Reduced overshoot and smoother force.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Saturation",
        lab_name="lab02",
        config_path="configs/lab02_pid/saturation_limit.yaml",
        plots="essential",
        description="Force limits cap the controller output.",
        try_this="Compare response speed against Auto demo.",
        watch="Control force clipping and slower tracking.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Windup",
        lab_name="lab02",
        config_path="configs/lab02_pid/pid_with_windup.yaml",
        plots="essential",
        description="Integral windup can keep pushing after saturation.",
        try_this="Run before Anti-windup.",
        watch="Overshoot after the error has changed sign.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Anti-windup",
        lab_name="lab02",
        config_path="configs/lab02_pid/pid_anti_windup.yaml",
        plots="essential",
        description="Anti-windup limits integral buildup.",
        try_this="Compare directly against Windup.",
        watch="Less overshoot and cleaner settling.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Interactive",
        lab_name="lab02",
        config_path="configs/lab02_pid/interactive_disturbance.yaml",
        plots="essential",
        description="Disturb the mass and tune target, Kp, Ki, Kd, force limit.",
        try_this="Click Pull/Push, then tune Kp, Ki, Kd, and force limit.",
        watch="Live status error, PID force, and disturbance.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF joint-space",
        lab_name="lab03",
        config_path="configs/lab03_2dof/joint_space_2dof.yaml",
        plots="essential",
        description="A two-link arm tracks shoulder and elbow joint targets.",
        try_this="Start here to see the actual 2DOF manipulator.",
        watch="Joint positions, end-effector motion, and torque.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF task-space",
        lab_name="lab03",
        config_path="configs/lab03_2dof/task_space_2dof.yaml",
        plots="task",
        description="The arm moves its hand toward an XY target with Jacobian-transpose PD.",
        try_this="Compare against joint-space tracking.",
        watch="Hand X/Y tracking and joint torque distribution.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF singularity",
        lab_name="lab03",
        config_path="configs/lab03_2dof/singularity_2dof.yaml",
        plots="singularity",
        description="The arm approaches a nearly straight singular posture.",
        try_this="Compare the singularity plot against the normal joint-space demo.",
        watch="Jacobian condition number rises while manipulability falls.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF interactive",
        lab_name="lab03",
        config_path="configs/lab03_2dof/interactive_2dof.yaml",
        plots="task",
        description="Tune the hand target, task stiffness, damping, and torque limit live.",
        try_this="Move target X/Y sliders, then change stiffness and damping.",
        watch="Live status hand position, error norm, and max torque.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="Step profile",
        lab_name="lab03",
        config_path="configs/lab03_2dof/step.yaml",
        plots="essential",
        description="A sudden target step demands abrupt control effort.",
        try_this="Run before smoother trajectory profiles.",
        watch="Force spike and tracking error.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="Trapezoid",
        lab_name="lab03",
        config_path="configs/lab03_2dof/trapezoidal.yaml",
        plots="essential",
        description="A trapezoidal profile limits velocity and acceleration.",
        try_this="Compare against Step profile.",
        watch="Lower force peaks and smoother velocity.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="Minimum jerk",
        lab_name="lab03",
        config_path="configs/lab03_2dof/minimum_jerk.yaml",
        plots="essential",
        description="Minimum-jerk motion starts and stops smoothly.",
        try_this="Compare against Trapezoid and S-curve.",
        watch="Smooth position/velocity and smaller error.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="S-curve",
        lab_name="lab03",
        config_path="configs/lab03_2dof/s_curve.yaml",
        plots="essential",
        description="S-curve motion smooths jerk transitions.",
        try_this="Compare against Step profile.",
        watch="Reduced abruptness in control effort.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="1D interactive",
        lab_name="lab03",
        config_path="configs/lab03_2dof/interactive_tracking.yaml",
        plots="essential",
        description="Disturb the tracker and tune gains, target offset, force limit.",
        try_this="Disturb the mass, then change Kp, Kd, and force limit.",
        watch="Live status target, error, and control force.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Neutral hold",
        lab_name="lab04",
        config_path="configs/lab04_panda/neutral_hold.yaml",
        plots="essential",
        description="Hold the Panda at a neutral pose.",
        try_this="Use this as the stable manipulator baseline.",
        watch="Joint error norm stays small.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Joint 4 path",
        lab_name="lab04",
        config_path="configs/lab04_panda/joint_pd.yaml",
        plots="essential",
        description="Move one Panda joint with a minimum-jerk target.",
        try_this="Compare q_3 against target_q_3 in the saved plot.",
        watch="Tracking error during the motion.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Joint 6 S-curve",
        lab_name="lab04",
        config_path="configs/lab04_panda/trajectory_tracking.yaml",
        plots="essential",
        description="Move another Panda joint with an S-curve target.",
        try_this="Compare against Joint 4 path.",
        watch="Which joint moves and how the hand position changes.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Reach X",
        lab_name="lab04",
        config_path="configs/lab04_panda/reach_x.yaml",
        plots="cartesian",
        description="Move a joint that visibly changes hand X position.",
        try_this="Watch the end-effector plot after the run.",
        watch="Hand X/Y/Z motion and joint error.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Cartesian reach",
        lab_name="lab04",
        config_path="configs/lab04_panda/cartesian_reach.yaml",
        plots="cartesian_reach",
        description="Move the Panda hand toward an explicit XYZ target.",
        try_this="Compare target_x_ee and x_ee in end_effector.png.",
        watch="Cartesian error, actuator force, and joint tracking error.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Cartesian interactive",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_cartesian_reach.yaml",
        plots="cartesian_reach",
        description="Tune hand target X/Y/Z and Cartesian gain live.",
        try_this="Move Target X/Y/Z sliders in the Interaction window.",
        watch="Live hand error and end-effector plot after the run.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Joint target",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_joint_hold.yaml",
        plots="essential",
        description="Nudge a Panda joint target and watch tracking error.",
        try_this="Click Joint Target -/+ several times.",
        watch="Live status target offset and error norm.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Soft wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_soft.yaml",
        plots="wall_compare",
        description="A lower-stiffness virtual wall lets the hand penetrate more.",
        try_this="Run before Stiff wall and compare virtual_wall.png.",
        watch="Higher penetration, lower force, smaller retreat.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Stiff wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_stiff.yaml",
        plots="wall_compare",
        description="A higher-stiffness virtual wall retreats more aggressively.",
        try_this="Run after Soft wall with the same trajectory.",
        watch="Lower penetration, higher force, larger retreat.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Virtual wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_virtual_wall.yaml",
        plots="wall",
        description="Tune wall position, stiffness, damping, and retreat gain.",
        try_this="Move wall X, then raise stiffness and damping.",
        watch="Wall penetration, wall force, and hand X position.",
    ),
)


def build_run_args(action: MenuAction) -> list[str]:
    return [
        sys.executable,
        "-m",
        "mclab",
        "run",
        action.lab_name,
        "--config",
        action.config_path,
        "--viewer",
        "--realtime",
        "--pause-at-end",
        "--plot",
        "--plots",
        action.plots,
    ]


def launch_action(action: MenuAction) -> subprocess.Popen[str]:
    return subprocess.Popen(
        build_run_args(action),
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def parse_run_output_path(line: str) -> Path | None:
    stripped = line.strip()
    if not stripped.startswith(RUN_COMPLETE_PREFIX):
        return None
    raw_path = stripped.removeprefix(RUN_COMPLETE_PREFIX).strip()
    if not raw_path:
        return None
    return Path(raw_path)


def action_config_path(action: MenuAction) -> Path:
    return PROJECT_ROOT / action.config_path


def action_doc_path(action: MenuAction) -> Path:
    return PROJECT_ROOT / DOC_PATHS[action.lab_name]


def launch_action_config(action: MenuAction) -> subprocess.Popen[Any] | None:
    return open_editable_path(action_config_path(action))


def launch_action_doc(action: MenuAction) -> subprocess.Popen[Any] | None:
    return open_editable_path(action_doc_path(action))


def launch_outputs_folder() -> subprocess.Popen[Any] | None:
    outputs = PROJECT_ROOT / "outputs"
    outputs.mkdir(exist_ok=True)
    return open_path(outputs)


def launch_outputs_index() -> subprocess.Popen[Any] | None:
    outputs = PROJECT_ROOT / "outputs"
    index = outputs / "index.html"
    if not index.exists():
        write_outputs_index(outputs)
    return open_path(index)


def launch_latest_output(latest_output: dict[str, Path | None]) -> subprocess.Popen[Any] | None:
    path = latest_output.get("path")
    if path is None:
        return None
    report = path / "report.html"
    return open_path(report if report.exists() else path)


def open_path(path: Path) -> subprocess.Popen[Any] | None:
    if not path.exists():
        return None
    if sys.platform.startswith("win"):
        import os

        os.startfile(str(path))
        return None
    if sys.platform == "darwin":
        return subprocess.Popen(["open", str(path)])
    return subprocess.Popen(["xdg-open", str(path)])


def open_editable_path(path: Path) -> subprocess.Popen[Any] | None:
    if not path.exists():
        return None
    code_command = shutil.which("code")
    if path.is_file() and code_command:
        return subprocess.Popen([code_command, "-r", str(path)])
    return open_path(path)


def parameter_hint(action: MenuAction) -> str:
    label = action.label.lower()
    config_name = Path(action.config_path).name

    if action.lab_name == "lab01":
        if label == "interactive":
            return "live sliders: mass, damping, stiffness; YAML: interaction.force"
        if "damped" in label:
            return "damping, stiffness, initial_position"
        if "stiffness" in label:
            return "stiffness, damping, initial_position"
        return "mass, damping, stiffness, initial_position, force_input.magnitude"

    if action.lab_name == "lab02":
        if label == "interactive":
            return "live sliders: target, Kp, Ki, Kd, force limit; YAML: controller.*"
        if label in {"windup", "anti-windup"}:
            return "controller.ki, controller.anti_windup, controller.output_limit"
        if label == "saturation":
            return "controller.output_limit, target.end"
        if "gain" in label or label == "pd damping":
            return "controller.kp, controller.kd, target.end"
        return "target.end, controller.kp, controller.ki, controller.kd, controller.output_limit"

    if action.lab_name == "lab03":
        if label == "2dof interactive":
            return "live sliders: Target X/Y, task stiffness, task damping, torque limit"
        if label == "2dof task-space":
            return "target_xy, tracking_controller.task_kp, tracking_controller.task_kd"
        if label in {"2dof joint-space", "2dof singularity"}:
            return "initial_q, target_q, trajectory.duration, tracking_controller.kp, tracking_controller.kd"
        if config_name == "interactive_tracking.yaml":
            return "live sliders: target offset, Kp, Kd, force limit"
        return (
            "trajectory.type, trajectory.duration, tracking_controller.kp, "
            "tracking_controller.kd, tracking_controller.force_limit"
        )

    if action.lab_name == "lab04":
        if label == "cartesian interactive":
            return "live sliders: Target X/Y/Z, Cartesian gain; YAML: cartesian_target.*"
        if label == "cartesian reach":
            return "cartesian_target.position, cartesian_target.gain, cartesian_target.max_step"
        if "wall" in label:
            return "virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping, virtual_wall.force_retreat_gain"
        if label == "joint target":
            return "interaction.target_step, interaction.target_limit, trajectory.end"
        if label == "neutral hold":
            return "home_q, sim_time"
        return "controlled_joint_index, trajectory.start, trajectory.end, trajectory.duration"

    return "config YAML values"


def lesson_text(action: MenuAction) -> str:
    return f"{action.description}\nTry: {action.try_this}\nChange: {parameter_hint(action)}\nWatch: {action.watch}"


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:  # pragma: no cover - depends on local GUI support.
        print(f"Learner menu could not start: {exc}")
        return 1

    root = tk.Tk()
    root.title("MuJoCo Control Lab")
    root.geometry("980x720")
    root.minsize(840, 600)

    outer = ttk.Frame(root, padding=16)
    outer.pack(fill="both", expand=True)

    title = ttk.Label(outer, text="MuJoCo Control Lab", font=("Segoe UI", 18, "bold"))
    title.pack(anchor="w")
    subtitle = ttk.Label(
        outer,
        text="Choose a guided scenario, run it, then use the MCLab Interaction window to disturb, tune, and observe.",
    )
    subtitle.pack(anchor="w", pady=(4, 12))

    status = tk.StringVar(value="Ready.")
    latest_output: dict[str, Path | None] = {"path": None}

    canvas = tk.Canvas(outer, highlightthickness=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    scroll_frame = ttk.Frame(canvas)
    scroll_frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    grouped: dict[str, list[MenuAction]] = {}
    for action in MENU_ACTIONS:
        grouped.setdefault(action.group, []).append(action)

    row = 0
    for group, actions in grouped.items():
        frame = ttk.LabelFrame(scroll_frame, text=group, padding=12)
        frame.grid(row=row, column=0, sticky="ew", pady=6)
        frame.columnconfigure(3, weight=1)
        row += 1
        for action_index, action in enumerate(actions):
            ttk.Button(
                frame,
                text=action.label,
                width=16,
                command=lambda selected=action: _launch_from_menu(
                    selected,
                    status,
                    root=root,
                    latest_output=latest_output,
                    latest_button=latest_button,
                ),
            ).grid(row=action_index, column=0, sticky="w", padx=(0, 12), pady=4)
            ttk.Button(
                frame,
                text="Config",
                width=8,
                command=lambda selected=action: launch_action_config(selected),
            ).grid(row=action_index, column=1, sticky="w", padx=(0, 6), pady=4)
            ttk.Button(
                frame,
                text="Lesson",
                width=8,
                command=lambda selected=action: launch_action_doc(selected),
            ).grid(row=action_index, column=2, sticky="w", padx=(0, 12), pady=4)
            ttk.Label(frame, text=lesson_text(action), wraplength=560, justify="left").grid(
                row=action_index, column=3, sticky="w", pady=4
            )

    bottom = ttk.Frame(outer)
    bottom.pack(fill="x", pady=(12, 0))
    ttk.Button(bottom, text="Open all reports", command=launch_outputs_index).pack(side="left")
    ttk.Button(bottom, text="Open outputs folder", command=launch_outputs_folder).pack(side="left", padx=(8, 0))
    latest_button = ttk.Button(bottom, text="Open latest report", command=lambda: launch_latest_output(latest_output))
    latest_button.pack(side="left", padx=(8, 0))
    latest_button.state(["disabled"])
    ttk.Label(bottom, textvariable=status).pack(side="left", padx=12)

    root.mainloop()
    return 0


def _launch_from_menu(
    action: MenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
) -> None:
    process = launch_action(action)
    status.set(f"Started {action.group} - {action.label} (pid {process.pid}). Close the viewer to finish.")
    Thread(
        target=_watch_process,
        args=(process, action, status),
        kwargs={"root": root, "latest_output": latest_output, "latest_button": latest_button},
        daemon=True,
    ).start()


def _watch_process(
    process: subprocess.Popen[str],
    action: MenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
) -> None:
    output_path: Path | None = None
    if process.stdout is not None:
        for line in process.stdout:
            parsed = parse_run_output_path(line)
            if parsed is not None:
                output_path = parsed
    return_code = process.wait()
    _set_status_after_run(
        action,
        status,
        return_code,
        output_path,
        root=root,
        latest_output=latest_output,
        latest_button=latest_button,
    )


def _set_status_after_run(
    action: MenuAction,
    status: Any,
    return_code: int,
    output_path: Path | None,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
) -> None:
    def update_ui() -> None:
        if return_code == 0:
            if output_path is not None:
                if latest_output is not None:
                    latest_output["path"] = output_path
                if latest_button is not None:
                    latest_button.state(["!disabled"])
                report = output_path / "report.html"
                latest = report if report.exists() else output_path
                status.set(f"Completed {action.group} - {action.label}. Latest report: {latest}")
            else:
                status.set(f"Completed {action.group} - {action.label}. Open the outputs folder for results.")
            return
        status.set(f"Failed {action.group} - {action.label} with exit code {return_code}.")

    if root is not None:
        root.after(0, update_ui)
    else:
        update_ui()
