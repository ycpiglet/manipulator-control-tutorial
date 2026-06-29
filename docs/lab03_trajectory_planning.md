# Lab03 2DOF Arm and Trajectory Planning

This lab bridges the 1D plants and the Panda manipulator with a planar two-link MuJoCo arm.

The main controlled variables are:

- shoulder and elbow joint angles in joint-space mode
- end-effector X/Y position in task-space mode
- torque and current proxy at both joints

In the 2DOF viewer, green marks the target hand position and blue marks the current hand position. When the Jacobian condition number exceeds the configured warning threshold, the current hand marker turns orange to indicate a near-singular posture.

Run:

```powershell
.\run_lab03.cmd
```

This opens the 2DOF arm joint-space demo:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/joint_space_2dof.yaml --viewer --realtime --pause-at-end --plot --plots essential
```

Read the plots in this order:

1. `position.png`: check whether `q_0` and `q_1` follow their joint targets.
2. `end_effector.png`: check how joint motion changes hand X/Y position.
3. `torque.png`: check how much shoulder and elbow torque the motion used.
4. `error.png`: compare joint-space and task-space error norms.
5. `singularity.png`: check Jacobian condition number and manipulability when available.

Task-space demo:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/task_space_2dof.yaml --plot --headless --plots task
```

This uses analytic FK and a Jacobian-transpose PD command:

```text
tau = J(q)^T * (Kp * (x_target - x_ee) + Kd * (xdot_target - xdot_ee))
```

Singularity demo:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/singularity_2dof.yaml --plot --headless --plots singularity
```

This moves the arm toward a nearly straight posture. In `singularity.png`, the Jacobian condition number should rise while manipulability falls. That is the visual cue that the same end-effector command becomes harder to realize with well-conditioned joint motion.

Damped least-squares singularity demo:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/dls_singularity_2dof.yaml --viewer --realtime --pause-at-end --plot --plots dls
```

This moves the hand toward the workspace edge using a damped least-squares inverse Jacobian:

```text
qdot_cmd = J(q)^T * (J(q) * J(q)^T + lambda^2 I)^-1 * xdot_cmd
```

Use the `MCLab Interaction` sliders to change `DLS task gain` and `DLS damping` while the arm moves. Lower damping follows the hand command more aggressively but can demand faster joint motion near a singular posture. Higher damping is calmer but may leave more task-space error. Compare `dls.png`, `singularity.png`, `torque.png`, and `error.png` after the run.

Interactive 2DOF demo:

```powershell
.\run_lab03_interactive.cmd
```

Use the small `MCLab Interaction` window next to the viewer. Move `Target X`, `Target Y`, `Task stiffness`, `Task damping`, and `Torque limit` while the simulation is running, or use `Quick presets` to jump between soft reach, default reach, and near-edge targets. Use `Reset sliders` to return to the starting values. Watch the green target marker and blue hand marker move in the viewer; an orange hand marker means the arm is near a poorly conditioned posture. Press `Mark observation` when a response is worth comparing later; the report's `Observation Markers` section saves the learning question, prediction, evidence prompt, note, sliders, and live status snapshot together. Use `Live status` to read `q1`, `q2`, hand X/Y, error norm, and max torque.

The older 1D trajectory profile demos are still available for comparing motion profiles before applying the idea to the arm:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/step.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/trapezoidal.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/s_curve.yaml --plot --headless
```
