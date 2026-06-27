# Lab02 PID Control

This lab controls the same one-dimensional MuJoCo plant with a readable scalar PID controller.

The main controlled variable is slider position. The controller changes force to make `position` follow `target_position`.

Read the plots in this order:

1. `position.png`: check whether position follows the target.
2. `error.png`: check tracking error, overshoot, and settling.
3. `control_force.png`: check how hard the controller pushed.

Run:

```powershell
.\run_lab02.cmd
```

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
```
