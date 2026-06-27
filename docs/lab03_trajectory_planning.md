# Lab03 Trajectory Planning

This incremental Lab03 focuses on trajectory profiles before the later 2DOF manipulator implementation.
It generates target position, velocity, acceleration, and jerk, then tracks the profile on the same MuJoCo slide-joint plant.

The main controlled variable is slider position over time. The key lesson is how the chosen trajectory profile changes velocity, acceleration, jerk, and control effort.

Read the plots in this order:

1. `position.png`: check whether position follows the planned profile.
2. `velocity.png`: compare the motion smoothness.
3. `torque.png`: check the force/torque proxy required by the profile.
4. `error.png`: check tracking quality.

Run:

```powershell
.\run_lab03.cmd
```

Interactive disturbance demo:

```powershell
.\run_lab03_interactive.cmd
```

Use `A` / left arrow or `D` / right arrow while the viewer is running to disturb the tracker. Watch how the controller recovers to the planned trajectory or final target.

Headless run:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --plot --headless
```

Compare profiles:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/step.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/trapezoidal.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/s_curve.yaml --plot --headless
```
