"""Learner-facing launcher menu for local MuJoCo labs."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from mclab.config import PROJECT_ROOT


@dataclass(frozen=True)
class MenuAction:
    group: str
    label: str
    lab_name: str
    config_path: str
    plots: str
    description: str


MENU_ACTIONS: tuple[MenuAction, ...] = (
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Auto demo",
        lab_name="lab01",
        config_path="configs/lab01_msd/default.yaml",
        plots="essential",
        description="Watch free response and force/position plots.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Interactive",
        lab_name="lab01",
        config_path="configs/lab01_msd/interactive_pull.yaml",
        plots="essential",
        description="Push the mass and tune mass, damping, stiffness.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Auto demo",
        lab_name="lab02",
        config_path="configs/lab02_pid/default.yaml",
        plots="essential",
        description="Watch PID tracking, error, and force.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Interactive",
        lab_name="lab02",
        config_path="configs/lab02_pid/interactive_disturbance.yaml",
        plots="essential",
        description="Disturb the mass and tune target, Kp, Ki, Kd, force limit.",
    ),
    MenuAction(
        group="Lab03 Trajectory Tracking",
        label="Auto demo",
        lab_name="lab03",
        config_path="configs/lab03_2dof/minimum_jerk.yaml",
        plots="essential",
        description="Compare trajectory tracking signals.",
    ),
    MenuAction(
        group="Lab03 Trajectory Tracking",
        label="Interactive",
        lab_name="lab03",
        config_path="configs/lab03_2dof/interactive_tracking.yaml",
        plots="essential",
        description="Disturb the tracker and tune gains, target offset, force limit.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Joint target",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_joint_hold.yaml",
        plots="essential",
        description="Nudge a Panda joint target and watch tracking error.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Virtual wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_virtual_wall.yaml",
        plots="wall",
        description="Tune wall position, stiffness, damping, and retreat gain.",
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
        "--hide-viewer-ui",
        "--realtime",
        "--pause-at-end",
        "--plot",
        "--plots",
        action.plots,
    ]


def launch_action(action: MenuAction) -> subprocess.Popen[Any]:
    return subprocess.Popen(build_run_args(action), cwd=PROJECT_ROOT)


def launch_outputs_folder() -> subprocess.Popen[Any] | None:
    outputs = PROJECT_ROOT / "outputs"
    outputs.mkdir(exist_ok=True)
    if sys.platform.startswith("win"):
        return subprocess.Popen(["explorer", str(outputs)])
    if sys.platform == "darwin":
        return subprocess.Popen(["open", str(outputs)])
    return subprocess.Popen(["xdg-open", str(outputs)])


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:  # pragma: no cover - depends on local GUI support.
        print(f"Learner menu could not start: {exc}")
        return 1

    root = tk.Tk()
    root.title("MuJoCo Control Lab")
    root.geometry("860x620")
    root.minsize(760, 540)

    outer = ttk.Frame(root, padding=16)
    outer.pack(fill="both", expand=True)

    title = ttk.Label(outer, text="MuJoCo Control Lab", font=("Segoe UI", 18, "bold"))
    title.pack(anchor="w")
    subtitle = ttk.Label(
        outer,
        text="Choose a lab, run it, then use the MCLab Interaction window to disturb and tune the system.",
    )
    subtitle.pack(anchor="w", pady=(4, 12))

    status = tk.StringVar(value="Ready.")

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
        frame.columnconfigure(1, weight=1)
        row += 1
        for action_index, action in enumerate(actions):
            ttk.Button(
                frame,
                text=action.label,
                width=16,
                command=lambda selected=action: _launch_from_menu(selected, status),
            ).grid(row=action_index, column=0, sticky="w", padx=(0, 12), pady=4)
            ttk.Label(frame, text=action.description, wraplength=560).grid(
                row=action_index, column=1, sticky="w", pady=4
            )

    bottom = ttk.Frame(outer)
    bottom.pack(fill="x", pady=(12, 0))
    ttk.Button(bottom, text="Open outputs folder", command=launch_outputs_folder).pack(side="left")
    ttk.Label(bottom, textvariable=status).pack(side="left", padx=12)

    root.mainloop()
    return 0


def _launch_from_menu(action: MenuAction, status: Any) -> None:
    process = launch_action(action)
    status.set(f"Started {action.group} - {action.label} (pid {process.pid}). Close the viewer to finish.")
