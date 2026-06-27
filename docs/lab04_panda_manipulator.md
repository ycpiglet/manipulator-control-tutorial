# Lab04 Panda Manipulator

This lab uses the Franka Emika Panda model from MuJoCo Menagerie.

The Menagerie Panda model is position-actuated. In this implementation:

- `ctrl` is the desired joint position for the seven arm joints.
- `tau_cmd` is logged from MuJoCo `data.actuator_force`.
- `current_proxy = tau_cmd / Kt`, with `Kt = 1.0` by default.
- End-effector position is logged from the `hand` body.
- Cartesian reach mode maps hand XYZ error to small joint target offsets with a damped least-squares Jacobian solve.
- The virtual wall demo computes a repulsive task-space force and maps it to a small target-joint retreat for stable educational behavior.

For `configs/lab04_panda/joint_pd.yaml`, the main controlled variable is joint 4, represented by `controlled_joint_index: 3`.

Read the plots in this order:

1. `position.png`: check whether `q_3` follows `target_q_3`.
2. `error.png`: check whether the joint tracking error remains small.
3. `torque.png` or `current_proxy.png`: check how much actuator effort the motion required.
4. `end_effector.png`: check how the joint motion moved the hand in Cartesian space.
5. `cartesian_error.png`: for Cartesian reach, check whether the hand reached the XYZ target.

For the virtual wall demos, also check `virtual_wall.png` for wall force, penetration, and retreat distance.

The MuJoCo viewer side panels are not the main control interface for this lab. The Python simulation loop writes actuator `ctrl` values from the YAML target at every step. If you edit actuator controls in the viewer, the loop overwrites them during the run; after `--pause-at-end`, physics stepping has stopped. Viewer side panels are hidden by default, and learner-facing interaction uses the `MCLab Interaction` window instead.

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

Cartesian reach demo:

```bash
python -m mclab run lab04 --config configs/lab04_panda/cartesian_reach.yaml --headless --plot --plots cartesian_reach
python -m mclab run lab04 --config configs/lab04_panda/interactive_cartesian_reach.yaml --viewer --realtime --pause-at-end --plot --plots cartesian_reach
```

The automatic demo moves the hand toward a fixed XYZ target. The interactive demo opens sliders for target X/Y/Z and Cartesian gain. Compare `x_ee_*` and `target_x_ee_*` in `end_effector.png`, then check `cartesian_error.png`.

Interactive virtual wall demo:

```powershell
.\run_lab04_wall_interactive.cmd
```

Use the `MCLab Interaction` sliders to move the virtual wall and tune wall stiffness, damping, and retreat gain while the Panda moves toward the wall. Watch the live wall penetration and wall force in the panel, then compare `end_effector.png` and `virtual_wall.png` after the run.

Soft/stiff wall comparison:

```bash
python -m mclab run lab04 --config configs/lab04_panda/wall_soft.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_stiff.yaml --headless --plot --plots wall_compare
```

Use the same trajectory and compare `virtual_wall.png`. The soft wall should allow more penetration with lower virtual force and smaller target retreat. The stiff wall should show higher virtual force and stronger retreat. The summary file also reports `max_wall_penetration_cm`, `max_wall_retreat_cm`, and `max_abs_virtual_wall_force`.

Headless runs:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/cartesian_reach.yaml --headless --plot --plots cartesian_reach
python -m mclab run lab04 --config configs/lab04_panda/impedance_wall.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/wall_stiff.yaml --headless --plot --plots wall_compare
```

Full viewer command:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot --plots essential
```

If `third_party/mujoco_menagerie` is missing, run the project bootstrap:

```bash
python scripts/bootstrap_and_run.py --setup-only
```
