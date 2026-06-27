# Lab04 Panda Manipulator

This lab uses the Franka Emika Panda model from MuJoCo Menagerie.

The Menagerie Panda model is position-actuated. In this implementation:

- `ctrl` is the desired joint position for the seven arm joints.
- `tau_cmd` is logged from MuJoCo `data.actuator_force`.
- `current_proxy = tau_cmd / Kt`, with `Kt = 1.0` by default.
- End-effector position is logged from the `hand` body.
- The virtual wall demo computes a repulsive task-space force and maps it to a small target-joint offset for stable educational behavior.

For `configs/lab04_panda/joint_pd.yaml`, the main controlled variable is joint 4, represented by `controlled_joint_index: 3`.

Read the plots in this order:

1. `position.png`: check whether `q_3` follows `target_q_3`.
2. `error.png`: check whether the joint tracking error remains small.
3. `torque.png` or `current_proxy.png`: check how much actuator effort the motion required.
4. `end_effector.png`: check how the joint motion moved the hand in Cartesian space.

For the virtual wall demo, also check `virtual_wall.png` for wall force and penetration.

The MuJoCo viewer side panels are not the main control interface for this lab. The Python simulation loop writes actuator `ctrl` values from the YAML target at every step. If you edit actuator controls in the viewer, the loop overwrites them during the run; after `--pause-at-end`, physics stepping has stopped. Learner-facing launchers hide the side panels and use the `MCLab Interaction` window instead.

Run:

```powershell
.\run_mclab.cmd
.\run_lab04.cmd
```

Interactive perturb demo:

```powershell
.\run_lab04_interactive.cmd
```

Use the small `MCLab Interaction` window next to the viewer. Click `Joint Target -` or `Joint Target +` to nudge the controlled joint target and observe the position-actuated controller response. Use `Live status` to read target offset, joint error norm, hand X position, wall penetration, and wall force while the viewer is running.

Interactive virtual wall demo:

```powershell
.\run_lab04_wall_interactive.cmd
```

Use the `MCLab Interaction` sliders to move the virtual wall and tune wall stiffness, damping, and retreat gain while the Panda moves toward the wall. Watch the live wall penetration and wall force in the panel, then compare `end_effector.png` and `virtual_wall.png` after the run.

Headless runs:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/impedance_wall.yaml --headless --plot
```

Full viewer command:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --hide-viewer-ui --realtime --pause-at-end --plot --plots essential
```

If `third_party/mujoco_menagerie` is missing, run the project bootstrap:

```bash
python scripts/bootstrap_and_run.py --setup-only
```
