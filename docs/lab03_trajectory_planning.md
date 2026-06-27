# Lab03 2DOF Arm and Trajectory Planning

This lab bridges the 1D plants and the Panda manipulator with a planar two-link MuJoCo arm.

The main controlled variables are:

- shoulder and elbow joint angles in joint-space mode
- end-effector X/Y position in task-space mode
- torque and current proxy at both joints

Run:

```powershell
.\run_lab03.cmd
```

This opens the 2DOF arm joint-space demo:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/joint_space_2dof.yaml --viewer --hide-viewer-ui --realtime --pause-at-end --plot --plots essential
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

Interactive 2DOF demo:

```powershell
.\run_lab03_interactive.cmd
```

Use the small `MCLab Interaction` window next to the viewer. Move `Target X`, `Target Y`, `Task stiffness`, `Task damping`, and `Torque limit` while the simulation is running. Use `Live status` to read `q1`, `q2`, hand X/Y, error norm, and max torque.

The older 1D trajectory profile demos are still available for comparing motion profiles before applying the idea to the arm:

```bash
python -m mclab run lab03 --config configs/lab03_2dof/step.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/trapezoidal.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --plot --headless
python -m mclab run lab03 --config configs/lab03_2dof/s_curve.yaml --plot --headless
```
