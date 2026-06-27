# Lab03 Trajectory Planning

This incremental Lab03 focuses on trajectory profiles before the later 2DOF manipulator implementation.
It generates target position, velocity, acceleration, and jerk, then tracks the profile on the same MuJoCo slide-joint plant.

Run:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --plot --headless
```

Compare profiles:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/step.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/trapezoidal.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/s_curve.yaml --plot --headless
```

