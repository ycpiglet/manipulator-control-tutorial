# Simulator Development Spec

This document is the implementation brief for Codex, Claude, or any coding agent working on **MuJoCo Manipulator Control Lab**.

The project must be built as a local-first MuJoCo simulation package. Web deployment is not part of the initial milestone.

---

## 0. Core decision

Use **MuJoCo from the beginning to the end**.

Do not split the project into separate custom simulators for 1D/2D and MuJoCo only for 6DOF. The educational value comes from using the same physics engine, same simulation loop, same logging pipeline, and same controller interface across all labs.

The four required simulators are:

1. Mass-Spring-Damper system
2. PID control system
3. 2DOF manipulator path/trajectory/control simulator
4. 6DOF or 7DOF manipulator simulator

The 6/7DOF manipulator is the central risk and central product feature. Build its POC first.

---

## 1. Hard constraints

### Must do

- Use MuJoCo for every lab.
- Prioritize local execution over web deployment.
- Provide simple CLI commands.
- Use SI units unless explicitly stated otherwise.
- Save simulation logs and plots automatically.
- Make every experiment reproducible through YAML configs.
- Use existing high-quality MuJoCo robot models for 6/7DOF.
- Keep controllers readable and educational, not overly abstract.
- Maintain stable examples that can be used in lecture material.

### Must not do

- Do not build a custom rigid-body physics engine.
- Do not model a 6DOF robot from scratch in Blender/CAD.
- Do not promise real industrial digital-twin accuracy.
- Do not implement ROS2, Isaac Sim, or browser-based real-time rendering in the first milestone.
- Do not over-engineer the package before the 6/7DOF POC works.

---

## 2. Technical stack

Recommended stack:

```text
Python 3.10+
MuJoCo Python bindings
NumPy
SciPy
Matplotlib
Pandas
PyYAML
Pydantic
Rich
Pytest
Ruff
```

Optional later:

```text
Jupyter
Plotly
Streamlit
FastAPI
Docker
```

Initial project is CLI + MuJoCo viewer + saved plots.

---

## 3. Repository layout

Implement this structure unless there is a strong reason to change it.

```text
src/mclab/
├── cli.py
├── config.py
├── sim/
│   ├── runner.py
│   ├── mujoco_utils.py
│   ├── logging.py
│   └── plotting.py
├── controllers/
│   ├── base.py
│   ├── pid.py
│   ├── joint_pd.py
│   ├── task_space_pd.py
│   └── impedance.py
├── trajectories/
│   ├── base.py
│   ├── step.py
│   ├── trapezoidal.py
│   ├── s_curve.py
│   ├── quintic.py
│   └── minimum_jerk.py
├── labs/
│   ├── lab01_msd.py
│   ├── lab02_pid.py
│   ├── lab03_2dof.py
│   └── lab04_panda.py
└── analysis/
    ├── metrics.py
    └── report.py
```

Models:

```text
models/
├── lab01_msd/scene.xml
├── lab02_pid/scene.xml
├── lab03_2dof/scene.xml
└── lab04_panda/scene.xml
```

Configs:

```text
configs/
├── lab01_msd/default.yaml
├── lab02_pid/default.yaml
├── lab03_2dof/default.yaml
└── lab04_panda/
    ├── joint_pd.yaml
    ├── trajectory_tracking.yaml
    ├── task_space_pd.yaml
    └── impedance_wall.yaml
```

---

## 4. CLI contract

The final CLI should support this pattern:

```bash
python -m mclab run <lab_name> --config <config_path> [--viewer] [--plot] [--headless]
```

Examples:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer
python -m mclab run lab04 --config configs/lab04_panda/impedance_wall.yaml --viewer --plot
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --viewer --plot
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --plot
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --plot
```

Minimum CLI options:

```text
--config       YAML config path
--viewer       open MuJoCo viewer
--headless     run without viewer
--plot         save standard plots
--output-dir   output directory override
--seed         random seed if noise is enabled
```

---

## 5. Standard simulation loop

Every lab should follow the same loop shape.

Pseudo-code:

```python
model = mujoco.MjModel.from_xml_path(model_path)
data = mujoco.MjData(model)
controller = build_controller(config)
trajectory = build_trajectory(config)
logger = Logger(config)

while data.time < config.sim_time:
    target = trajectory.evaluate(data.time)
    command = controller.compute(model, data, target)
    apply_control(model, data, command)
    mujoco.mj_step(model, data)
    logger.record(model, data, target, command)
    if viewer:
        viewer.sync()

logger.save()
plot_standard_outputs(logger.output_path)
```

Keep the first implementation straightforward. Avoid framework complexity until all labs run.

---

## 6. Standard logged signals

Log as many of these as applicable:

```text
time
q
qdot
qddot_estimated
x_ee
xdot_ee
target_q
target_qdot
target_x
target_xdot
ctrl
tau_cmd
tau_bias
force_task
force_contact_or_virtual
current_proxy
position_error
velocity_error
kinetic_energy
potential_energy
```

For acceleration, finite difference is acceptable in the first version:

```text
qddot_estimated[k] = (qdot[k] - qdot[k-1]) / dt
```

For jerk, finite difference from acceleration is acceptable:

```text
jerk[k] = (acc[k] - acc[k-1]) / dt
```

---

## 7. Phase 1: 6/7DOF POC first

This is the first implementation priority.

### Goal

Run a Franka Panda or UR5e model in MuJoCo, hold a neutral pose, move joints along a simple trajectory, and save plots.

### Model choice

Primary:

```text
Franka Emika Panda 7DOF
```

Fallback:

```text
Universal Robots UR5e 6DOF
```

Use MuJoCo Menagerie as a submodule or use `robot_descriptions` if that is simpler.

### POC success criteria

The POC is successful only if all items below work:

- model loads without manual asset path hacking
- MuJoCo viewer opens
- robot does not explode numerically
- neutral pose hold works for 10 seconds
- one or more joints can track a smooth trajectory
- `q`, `qdot`, `tau_cmd`, `ctrl`, `x_ee` are logged
- plots are saved automatically
- command is simple and reproducible

Target command:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --plot
```

### Joint PD controller

Use this as the first controller:

```text
tau_cmd = Kp * (q_des - q) + Kd * (qdot_des - qdot) + tau_bias
```

Where `tau_bias` is the MuJoCo bias force term used as gravity/Coriolis compensation if available for the controlled joints.

Implementation guidance:

- Map only the controlled arm joints.
- Be explicit about joint names and actuator names.
- Clip torque command to configured limits.
- If Menagerie actuators are position actuators instead of torque motors, either use their intended control interface or create a modified local scene with motor actuators.
- Keep one clearly documented path that works.

### End-effector logging

Compute end-effector position using MuJoCo body/site APIs.

Recommended approach:

- add or identify an end-effector `site`
- read `data.site_xpos[site_id]`
- use `mujoco.mj_jacSite` for Jacobian

Log:

```text
x_ee
J_pos
J_rot if needed later
```

---

## 8. Phase 2: Lab 01 — Mass-Spring-Damper

### Purpose

Show how mass, stiffness, and damping change the physical response.

### MuJoCo model

Use a single body with a slide joint along x.

Parameters should be configurable:

```yaml
mass: 1.0
stiffness: 50.0
damping: 2.0
initial_position: 0.1
initial_velocity: 0.0
force_input:
  type: step
  magnitude: 0.0
  start_time: 0.0
sim_time: 5.0
```

### Required outputs

- x position
- velocity
- acceleration
- applied force
- kinetic energy
- potential energy
- damping behavior

### Educational comparison configs

Create at least:

```text
underdamped.yaml
over_damped.yaml
high_stiffness.yaml
low_stiffness.yaml
```

---

## 9. Phase 3: Lab 02 — PID Control

### Purpose

Show PID behavior on the same physical plant.

### Controller

```text
u = Kp * e + Ki * integral_error + Kd * error_rate
```

### Required features

- proportional-only control
- PD control
- PID control
- force/torque saturation
- anti-windup
- optional measurement noise
- optional control delay

### Required comparison configs

```text
p_low_gain.yaml
p_high_gain.yaml
pd_damped.yaml
pid_with_windup.yaml
pid_anti_windup.yaml
saturation_limit.yaml
```

### Metrics

Compute:

```text
rise_time
overshoot_percent
settling_time
steady_state_error
max_control_effort
```

---

## 10. Phase 4: Lab 03 — 2DOF manipulator

### Purpose

Bridge simple control and full manipulator control.

### Model

Use two hinge joints in a planar configuration.

Required variables:

```text
q1, q2
qdot1, qdot2
end-effector x, y
Jacobian J(q)
```

### Required features

- FK visualization
- IK target solving
- Jacobian calculation
- joint-space trajectory tracking
- task-space trajectory tracking
- singularity demonstration
- torque/current proxy plots

### Controllers

Start with:

```text
joint PD
task-space Jacobian-transpose PD
```

Optional:

```text
computed torque control
operational-space control
```

### Trajectory generators

Implement common trajectory interface:

```python
class Trajectory:
    def evaluate(self, t: float) -> Target:
        ...
```

Required trajectories:

```text
step
trapezoidal velocity
quintic polynomial
minimum jerk
```

S-curve can be added after the required trajectories are stable.

---

## 11. Phase 5: Lab 04 advanced — 6/7DOF manipulator

### Purpose

This is the course-facing core demo.

### Required demos

#### Demo A — Neutral pose hold

- gravity enabled
- robot holds neutral pose
- plot joint errors and torque commands

#### Demo B — Joint-space trajectory tracking

- move selected joints with smooth trajectory
- compare step vs minimum-jerk or trapezoidal trajectory
- show torque/current proxy difference

#### Demo C — End-effector position control

- move end-effector by +x 10 cm
- show joint motion, end-effector trajectory, tracking error

#### Demo D — Cartesian impedance control

- set target pose
- compare stiffness matrices such as:

```text
K = diag([20, 200, 200])
K = diag([200, 200, 200])
K = diag([500, 500, 500])
```

- show different compliance behavior

#### Demo E — Virtual wall

- add a wall plane or implement virtual wall force
- compare high stiffness position control vs impedance control
- show force spike and torque/current proxy response

### Cartesian impedance controller

Start with translational-only impedance:

```text
F = Kx * (x_des - x) + Dx * (xdot_des - xdot)
tau_task = J_pos.T @ F
tau_cmd = tau_task + tau_bias
```

Do orientation impedance later.

### Virtual wall

Start with a deterministic virtual wall force before relying on MuJoCo contact force extraction.

Example:

```text
if x_ee[0] > wall_x:
    penetration = x_ee[0] - wall_x
    F_wall_x = -k_wall * penetration - d_wall * xdot_ee[0]
else:
    F_wall_x = 0
```

Then inject it as an external task-space force or use it only for analysis/visualization depending on stability.

### Torque/current proxy

Initial approximation:

```text
current_proxy = tau_cmd / Kt
```

Default:

```text
Kt = 1.0
```

This is not a motor-driver simulation. It is an educational signal showing how control effort changes.

---

## 12. Plotting requirements

Every lab should produce standard plots.

Minimum plots:

```text
position tracking
velocity tracking
acceleration estimate
control effort / torque
current proxy
error norm
```

For trajectory labs:

```text
position profile
velocity profile
acceleration profile
jerk profile
torque comparison
```

For impedance/contact labs:

```text
end-effector position
end-effector velocity
task-space force
virtual/contact force
torque/current proxy
```

Use Matplotlib first. Do not use complex visualization dependencies in the first milestone.

---

## 13. Testing requirements

Add simple tests early.

Required tests:

```text
test_cli_imports
test_config_loads
test_pid_zero_error_zero_output
test_minimum_jerk_boundary_conditions
test_trapezoidal_trajectory_boundary_conditions
test_lab01_runs_headless
test_lab04_model_loads_if_assets_available
```

Smoke tests should run quickly. Do not require viewer in CI.

---

## 14. AI coding agent workflow

When using Codex/Claude, do not ask for the entire project at once.

Use small tasks like these:

### Task 1

```text
Initialize the Python package skeleton according to README.md and SIMULATOR_DEVELOPMENT_SPEC.md. Add pyproject.toml, src/mclab, tests, and a CLI entry point that prints available labs. Do not implement the labs yet.
```

### Task 2

```text
Implement config loading with Pydantic and YAML. Add examples for lab04_panda/joint_pd.yaml and lab01_msd/default.yaml. Add tests for config loading.
```

### Task 3

```text
Implement the lab04 Panda/UR5e POC first. Load a MuJoCo Menagerie model, run a 10-second simulation, hold neutral pose with joint PD, log q/qdot/ctrl/tau_cmd/x_ee, and save plots. Keep the implementation simple and readable.
```

### Task 4

```text
Stabilize lab04. Add torque clipping, target joint trajectory, viewer flag, headless flag, and smoke test. Document how to run it.
```

### Task 5

```text
Implement lab01 mass-spring-damper using MuJoCo slide joint. Use the shared runner, logger, and plotting utilities.
```

### Task 6

```text
Implement lab02 PID control on the lab01 plant. Add anti-windup, saturation, and standard control metrics.
```

### Task 7

```text
Implement lab03 2DOF planar arm in MuJoCo. Add FK, Jacobian, joint PD, task-space PD, and minimum-jerk trajectory tracking.
```

### Task 8

```text
Implement lab04 Cartesian impedance control. Use translational-only stiffness/damping first. Add comparison configs for low/high stiffness and save plots.
```

### Task 9

```text
Implement lab04 virtual wall demo. Prefer deterministic virtual wall force first, then optionally add MuJoCo contact-based wall. Save force, torque, current_proxy, and position plots.
```

---

## 15. Risk register

| Risk | Probability | Impact | Mitigation |
|---|---:|---:|---|
| 6/7DOF model asset path issues | Medium | High | use Menagerie submodule or robot_descriptions; document one working path |
| Actuator type mismatch | High | High | inspect model actuators; create local scene with motor actuators if needed |
| Impedance control instability | Medium | High | start translational-only; low stiffness; torque clipping; small timestep |
| Contact force extraction is confusing | Medium | Medium | start with deterministic virtual wall force |
| Plots become inconsistent across labs | Medium | Medium | centralize logger and plotting functions |
| AI-generated code becomes too abstract | High | Medium | enforce simple functions and readable controllers |
| Overpromising digital twin accuracy | High | High | document educational scope clearly |

---

## 16. Course-demo readiness checklist

Before showing this as a lecture proposal, verify:

```text
[ ] Fresh clone installs successfully
[ ] lab04 joint PD demo runs with viewer
[ ] lab04 trajectory demo saves plots
[ ] lab04 impedance comparison works without exploding
[ ] lab01/lab02/lab03 run headless and save plots
[ ] README commands are accurate
[ ] outputs are visually clean enough for slides
[ ] limitations are clearly stated
[ ] third-party licenses are preserved
```

---

## 17. Implementation philosophy

Prefer this:

```text
simple, readable, physically interpretable, reproducible
```

Avoid this:

```text
general framework, too many abstractions, hidden magic, unstable demo
```

This repository is a teaching tool first and a simulator package second.
