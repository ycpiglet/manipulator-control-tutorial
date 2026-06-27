# Lab01 Mass-Spring-Damper

This lab uses a MuJoCo slide joint as a one-dimensional mass-spring-damper plant.

The main controlled input is the external force applied to the slider. Read the plots in this order:

1. `position.png`: check oscillation, overshoot, and settling.
2. `velocity.png`: check how damping reduces motion.
3. `force.png`: check the applied input force.

Run:

```powershell
.\run_lab01.cmd
```

Headless run:

```bash
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --plot --headless
```

Compare damping and stiffness with:

```bash
python -m mclab run lab01 --config configs/lab01_msd/underdamped.yaml --plot --headless
python -m mclab run lab01 --config configs/lab01_msd/over_damped.yaml --plot --headless
python -m mclab run lab01 --config configs/lab01_msd/high_stiffness.yaml --plot --headless
```
