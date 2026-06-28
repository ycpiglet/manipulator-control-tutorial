# Lab02 PID Control

This lab controls the same one-dimensional MuJoCo plant with a readable scalar PID controller.

The main controlled variable is slider position. The controller changes force to make `position` follow `target_position`.

Read the plots in this order:

1. `position.png`: check whether position follows the target.
2. `error.png`: check tracking error, overshoot, and settling.
3. `control_force.png`: check how hard the controller pushed.
4. In noisy runs, compare `measured_position` against true `position` in `position.png`.

Run:

```powershell
.\run_lab02.cmd
```

Interactive disturbance demo:

```powershell
.\run_lab02_interactive.cmd
```

Use the small `MCLab Interaction` window next to the viewer. Click `Pull Left` or `Push Right` to disturb the mass. Keyboard shortcuts also work when the viewer has focus: `A` / left arrow or `D` / right arrow. Use the live sliders to change target position, `Kp`, `Ki`, `Kd`, and force limit while the simulation is running, and use `Reset sliders` to return to the starting values. The viewer shows a gray zero/equilibrium marker, a green target marker, and an orange force bar when PID or disturbance force is applied. Press `Mark observation` when a response is worth comparing later in the report's `Observation Markers` section. Watch the PID controller push the mass back to the target position, and use `Live status` to compare target, position, error, PID force, and disturbance force.

Headless run:

```bash
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --plot --headless
```

Useful comparisons:

```bash
python -m mclab run lab02 --config configs/lab02_pid/p_low_gain.yaml --plot --headless
python -m mclab run lab02 --config configs/lab02_pid/p_high_gain.yaml --plot --headless
python -m mclab run lab02 --config configs/lab02_pid/pid_with_windup.yaml --plot --headless
python -m mclab run lab02 --config configs/lab02_pid/pid_anti_windup.yaml --plot --headless
python -m mclab run lab02 --config configs/lab02_pid/measurement_noise.yaml --plot --headless --plots pid
python -m mclab run lab02 --config configs/lab02_pid/control_delay.yaml --plot --headless
```

Use `measurement_noise_std` to simulate a noisy sensor and `control_delay` to simulate actuator or computation delay. The generated `report.html` and `outputs/index.html` include these values plus the measured-error summary so learners can compare runs without opening every CSV file.
