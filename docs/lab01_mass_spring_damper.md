# Lab01 Mass-Spring-Damper

This lab uses a MuJoCo slide joint as a one-dimensional mass-spring-damper plant.

Run:

```bash
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --plot --headless
```

Compare damping and stiffness with:

```bash
python -m mclab run lab01 --config configs/lab01_msd/underdamped.yaml --plot --headless
python -m mclab run lab01 --config configs/lab01_msd/over_damped.yaml --plot --headless
python -m mclab run lab01 --config configs/lab01_msd/high_stiffness.yaml --plot --headless
```

