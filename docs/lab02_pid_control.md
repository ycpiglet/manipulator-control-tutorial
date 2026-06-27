# Lab02 PID Control

This lab controls the same one-dimensional MuJoCo plant with a readable scalar PID controller.

Run:

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

