# Lab04 Panda Manipulator

This lab uses the Franka Emika Panda model from MuJoCo Menagerie.

The Menagerie Panda model is position-actuated. In this implementation:

- `ctrl` is the desired joint position for the seven arm joints.
- `tau_cmd` is logged from MuJoCo `data.actuator_force`.
- `current_proxy = tau_cmd / Kt`, with `Kt = 1.0` by default.
- End-effector position is logged from the `hand` body.
- The virtual wall demo computes a repulsive task-space force and maps it to a small target-joint offset for stable educational behavior.

Run:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/impedance_wall.yaml --headless --plot
```

If `third_party/mujoco_menagerie` is missing, run the project bootstrap:

```bash
python scripts/bootstrap_and_run.py --setup-only
```

