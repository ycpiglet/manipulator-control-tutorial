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

For the virtual wall demos, also check `virtual_wall.png` for wall force, penetration, and retreat distance. The report and `worksheet.md` `Key Moments` sections list first contact, peak penetration, peak force, peak damping force, peak hand speed, and peak Cartesian error timestamps so learners can jump directly to the important parts of the plots. The same wall moments are drawn as dashed vertical markers on the saved wall plots.

The MuJoCo viewer side panels are not the main control interface for this lab. The Python simulation loop writes actuator `ctrl` values from the YAML target at every step. If you edit actuator controls in the viewer, the loop overwrites them during the run; after `--pause-at-end`, physics stepping has stopped. Viewer side panels are hidden by default, and learner-facing interaction uses the `MCLab Interaction` window instead.

In Cartesian reach and virtual wall modes, the viewer adds lightweight visual guides: green is the hand target, blue is the current hand position, the orange contact point means the hand is penetrating the virtual wall, the orange bar shows the wall-force direction and relative magnitude, and the translucent red box is the virtual wall. Set `viewer_guides.enabled: false` in a config only when you need an uncluttered raw model view.

Run:

```powershell
.\run_mclab.cmd
.\run_lab04.cmd
```

For a headless readiness check before a live class demo, run the 30-second neutral hold:

```bash
python -m mclab run lab04 --config configs/lab04_panda/neutral_hold_30s.yaml --headless --plot --plots stability
```

The report should show `30s stability hold` as OK when maximum joint speed and joint drift stay small. Inspect `velocity.png`, `error.png`, and `torque.png` before using the Panda viewer in front of learners.

Interactive perturb demo:

```powershell
.\run_lab04_interactive.cmd
```

Use the small `MCLab Interaction` window next to the viewer. Click `Joint Target -` or `Joint Target +` to nudge the controlled joint target and observe the position-actuated controller response. Use `Live status` to read target offset, joint error norm, hand X position, wall penetration, and wall force while the viewer is running.

Cartesian reach demo:

```powershell
.\run_lab04_cartesian_interactive.cmd
```

```bash
python -m mclab run lab04 --config configs/lab04_panda/cartesian_reach.yaml --headless --plot --plots cartesian_reach
python -m mclab run lab04 --config configs/lab04_panda/interactive_cartesian_reach.yaml --viewer --realtime --pause-at-end --plot --plots cartesian_reach
```

The automatic demo moves the hand toward a fixed XYZ target. The interactive launcher opens sliders for target X/Y/Z and Cartesian gain, plus `Quick presets` for soft, default, and farther reach targets. Use `Playback speed` or the `-` / `+` buttons next to a slider for one-resolution-step adjustments. Use `Pause / Resume` to stop the Panda before changing the hand target, `Step once` to advance one physics step at a time, or `Reset plant` to return the Panda to the home posture while keeping the current target and gain sliders. In the viewer, compare the green target point with the blue hand point. Compare `x_ee_*` and `target_x_ee_*` in `end_effector.png`, then check `cartesian_error.png`.

Soft/stiff Cartesian reach comparison:

```bash
python -m mclab run lab04 --config configs/lab04_panda/cartesian_soft.yaml --headless --plot --plots cartesian_reach
python -m mclab run lab04 --config configs/lab04_panda/cartesian_stiff.yaml --headless --plot --plots cartesian_reach
python -m mclab batch lab04_cartesian_compare --open-report
```

Use this comparison before the virtual wall demos. The soft reach uses lower Cartesian gain, smaller step limits, and more DLS damping, so it should move more calmly but can leave more hand error. The stiff reach pursues the same XYZ target more aggressively and should reduce final Cartesian error. Compare `cartesian_error.png`, `end_effector.png`, and `torque.png`, then use the batch report to inspect the parameter difference table and actuator-force traces.

Interactive virtual wall demo:

```powershell
.\run_lab04_wall_interactive.cmd
```

Use the `MCLab Interaction` sliders to move the green hand target through or away from the virtual wall, then tune wall stiffness, damping, and retreat gain while the Panda responds. Use `Quick presets` to compare soft wall, stiff wall, and close-wall cases without hand-entering each value. Use `Playback speed` or the `-` / `+` buttons next to a slider for one-resolution-step adjustments. Use `Pause / Resume` to freeze the wall-contact moment before changing wall parameters, `Step once` to advance the contact response one physics step at a time, `Reset sliders` to return to the starting wall settings after exploring, or `Reset plant` to return the Panda to the home posture while keeping the current wall and target sliders. Press `Mark observation` when a response is worth comparing later; the report's `Observation Markers` section saves the learning question, prediction, evidence prompt, note, sliders, and live status snapshot together. The report's `Learner Snapshot` section and `learner_snapshot.json` preserve the final slider, live-status, and joint-target nudge state for review, while `learner_tuned_config.yaml` lets you replay the final hand target and wall values without live controls. Watch `Target-Wall [cm]`, live wall penetration, and wall force in the panel, then compare `wall_target.png`, `end_effector.png`, and `virtual_wall.png` after the run.

Soft/stiff wall comparison:

```bash
python -m mclab run lab04 --config configs/lab04_panda/wall_soft.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_stiff.yaml --headless --plot --plots wall_compare
python -m mclab batch lab04_wall_compare --open-report
```

Use the same trajectory and compare `virtual_wall.png`. The soft wall should allow more penetration with lower virtual force and smaller target retreat. The stiff wall should show higher virtual force and stronger retreat. The summary file also reports `max_wall_penetration_cm`, `max_wall_retreat_cm`, `first_wall_contact_time`, `peak_wall_force_time`, `peak_wall_damping_force_time`, `wall_contact_duration`, and `max_abs_virtual_wall_force`. In the batch report, open `wall_key_moment_timing_compare.png` to compare when contact and peak wall responses happen across scenarios.

Damping-only wall comparison:

```bash
python -m mclab run lab04 --config configs/lab04_panda/wall_low_damping.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_high_damping.yaml --headless --plot --plots wall_compare
python -m mclab batch lab04_wall_compare --open-report
```

These two configs keep wall stiffness, wall position, retreat gains, and trajectory fixed while changing only `virtual_wall.damping`. Use this after the soft/stiff comparison to isolate the damping term. In the batch report, compare `wall_force_compare.png`, `wall_penetration_compare.png`, and `wall_retreat_compare.png` to discuss whether higher damping mainly changes force, penetration, or retreat.

Wall-position comparison:

```bash
python -m mclab run lab04 --config configs/lab04_panda/wall_near.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_far.yaml --headless --plot --plots wall_compare
python -m mclab batch lab04_wall_compare --open-report
```

These two configs keep wall stiffness, damping, retreat gains, and trajectory fixed while changing only `virtual_wall.wall_x`. The near wall should be reached earlier and produce larger penetration, force, and retreat. The far wall should barely be touched by the same motion. Compare `first_wall_contact_time`, `wall_contact_duration`, `wall_contact_fraction`, `wall_key_moment_timing_compare.png`, `wall_penetration_compare.png`, and `wall_force_compare.png`. Use this after the interactive wall demo so learners can connect the wall slider to a deterministic comparison report.

Approach-speed wall comparison:

```bash
python -m mclab run lab04 --config configs/lab04_panda/wall_slow_approach.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_fast_approach.yaml --headless --plot --plots wall_compare
python -m mclab batch lab04_wall_compare --open-report
```

These two configs keep wall stiffness, damping, position, and retreat gains fixed while changing only `trajectory.duration`. Use this after the damping-only comparison to show that the damping term depends on approach velocity, not just penetration. Compare `hand_x_speed_compare.png`, `wall_damping_force_compare.png`, `wall_force_compare.png`, `wall_key_moment_timing_compare.png`, `wall_contact_duration`, `max_hand_x_speed`, `peak_hand_speed_time`, and `max_abs_virtual_wall_damping_force`.

Force-to-retreat comparison:

```bash
python -m mclab run lab04 --config configs/lab04_panda/wall_low_retreat.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_high_retreat.yaml --headless --plot --plots wall_compare
python -m mclab batch lab04_wall_compare --open-report
```

These two configs keep wall stiffness, damping, wall position, and trajectory fixed while changing only `virtual_wall.force_retreat_gain`. Use this after the damping and wall-position comparisons to isolate how strongly virtual wall force is converted into target retreat. Compare `wall_retreat_compare.png`, `wall_penetration_compare.png`, `hand_x_compare.png`, `max_wall_retreat_cm`, and `max_wall_penetration_cm`.

Headless runs:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/cartesian_reach.yaml --headless --plot --plots cartesian_reach
python -m mclab run lab04 --config configs/lab04_panda/impedance_wall.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/wall_stiff.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_high_damping.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_near.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_fast_approach.yaml --headless --plot --plots wall_compare
python -m mclab run lab04 --config configs/lab04_panda/wall_high_retreat.yaml --headless --plot --plots wall_compare
```

Full viewer command:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot --plots essential
```

If `third_party/mujoco_menagerie` is missing, run the project bootstrap:

```bash
python scripts/bootstrap_and_run.py --setup-only
```
