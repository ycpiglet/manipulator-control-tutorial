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

Interactive pull demo:

```powershell
.\run_lab01_interactive.cmd
```

Use the small `MCLab Interaction` window next to the viewer. Click `Pull Left` or `Push Right` to apply a short force pulse to the mass. Keyboard shortcuts also work when the viewer has focus: `A` / left arrow or `D` / right arrow. Use the live sliders to change `mass`, `damping`, and `stiffness` while the simulation is running, and use `Reset sliders` to return to the starting values. The viewer shows a gray equilibrium marker and an orange force bar when a force is applied. Press `Mark observation` when a response is worth comparing later in the report's `Observation Markers` section. Watch the block oscillate and settle under spring stiffness and damping, and use `Live status` to read position, velocity, applied force, and total energy while it moves.

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
