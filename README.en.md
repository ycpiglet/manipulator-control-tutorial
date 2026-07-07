# MuJoCo Manipulator Control Lab

**MuJoCo Manipulator Control Lab** (`mclab`) is an educational robot-control
simulator built entirely on MuJoCo: it walks a beginner from a 1-D
mass-spring-damper system through PID control and a 2-DOF arm up to
6/7-DOF manipulator control with Cartesian impedance and a virtual wall.

The goal is not a quantitatively identical digital twin of an industrial
robot. It is a **teaching dynamics laboratory** where you can *see* how each
control parameter changes the robot's motion — and where expensive
trial-and-error mistakes (like launching an arm by misconfiguring stiffness)
can be experienced safely and for free.

> 한국어 문서: [README.md](README.md) (전체 개발 명세 포함).
> A companion Korean tutorial/review manuscript with full step-by-step
> derivations lives under [`paper/`](paper/).

## The four labs

| Lab | Topic | What you learn |
|---|---|---|
| `lab01` mass-spring-damper | 2nd-order dynamics | stiffness, damping, mass, overshoot, oscillation, energy |
| `lab02` PID control | feedback tuning | Kp/Ki/Kd trade-offs, saturation, windup, noise, delay |
| `lab03` 2-DOF arm | kinematics | FK, IK branches, Jacobian, singularities, trajectory profiles |
| `lab04` Panda (7-DOF) | manipulator control | joint/Cartesian control, impedance parameters, virtual wall contact |

Every config ships with a learning guide (focus, what to try, what to watch,
suggested next runs) and every run produces plots plus an HTML report, so the
labs can be used for self-study without an instructor.

### Failure gallery

Selected configs reproduce *real* misconfiguration accidents so you can study
them safely, e.g. `configs/lab01_msd/f2_launch_high_energy.yaml` stores
50 J in the virtual spring before motion starts (predict the ~10 m/s launch
with `v ≈ δ√(k/m)`, then watch it happen), and `f2_launch_precheck.yaml`
shows the same displacement made safe. The companion manuscript explains the
physics behind each case.

## Quick start

**Double-click [`START_HERE.cmd`](START_HERE.cmd)** (Windows). A menu opens;
pick a number to try any of the four simulators. The first launch auto-installs
what it needs (a few minutes) — the only prerequisite is Python ≥ 3.10.

That's it. The table below is only for picking a specific scenario **directly**.

### Scenarios by situation

Pick from the menu, or run a file directly:
`python -m mclab run <lab> --config configs/<lab_folder>/<file>.yaml --viewer --plot`

**Lab01 — mass-spring-damper (second-order basics)**

| What you want to see | config |
|---|---|
| Baseline response | `default` |
| Lingering oscillation (too little damping) | `underdamped` |
| Sluggish return (over-damped) | `over_damped` |
| Stiffness comparison | `high_stiffness` / `low_stiffness` |
| Push/pull and tune live | `interactive_pull` |
| ⚠️ The stiffness-misconfig launch accident | `f2_launch_high_energy` ↔ `f2_launch_precheck` |

**Lab02 — PID control**

| What you want to see | config |
|---|---|
| Baseline | `default` |
| Low/high P gain | `p_low_gain` / `p_high_gain` |
| Calm overshoot with D | `pd_damped` |
| Actuator saturation | `saturation_limit` |
| Integral windup and anti-windup | `pid_with_windup` / `pid_anti_windup` |
| Sensor noise / control delay | `measurement_noise` / `control_delay` |
| Disturb and tune live | `interactive_disturbance` |

**Lab03 — 2-DOF arm (kinematics & trajectories)**

| What you want to see | config |
|---|---|
| Joint- vs task-space control | `joint_space_2dof` / `task_space_2dof` |
| Trajectory profiles | `step` / `trapezoidal` / `s_curve` / `minimum_jerk` |
| Singularity and DLS relief | `singularity_2dof` / `dls_singularity_2dof` |
| Live control | `interactive_2dof` |

**Lab04 — 7-DOF Panda (impedance & contact)**

| What you want to see | config |
|---|---|
| Posture hold | `neutral_hold` |
| Cartesian reach (soft/stiff) | `cartesian_soft` / `cartesian_stiff` |
| Virtual-wall impedance contact | `impedance_wall` |
| Wall stiffness/damping comparison | `wall_soft` / `wall_stiff`, `wall_low_damping` / `wall_high_damping` |
| Push the wall yourself | `interactive_virtual_wall` |

Every run saves plots (`plots/*.png`) and an HTML report that tells you what to
look at first. The menu also contains full scenario lists and automatic
comparison experiments beyond this table.

## Manual install (advanced)

Requires Python ≥ 3.10.

```bash
git clone https://github.com/ycpiglet/manipulator-control-tutorial.git
cd manipulator-control-tutorial
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # Windows; use .venv/bin/pip on Linux/macOS
python -m mclab menu                        # same guided launcher as START_HERE.cmd
```

Lab04 also fetches the MuJoCo Menagerie Panda model into `third_party/`
(see the license note below).

## Verify your installation

```bash
python -m pytest -q          # 340 tests + 760+ subtests
python -m mclab --help
```

CI (GitHub Actions) enforces lint, the full test suite with a coverage floor
(≥80 %; local baseline 84 %), and the manuscript's formula/marker gates.

## Reuse and extension

- Add a scenario: drop a YAML into `configs/<lab>/` and register its
  learning guide (`src/mclab/learning_guides.py`) and next-run suggestions
  (`src/mclab/sim/reporting.py`); the test suite enforces both.
- Lab documentation for educators lives in [`docs/`](docs/) (English).
- The Korean manuscript under `paper/` provides the full theory with
  no skipped derivation steps, anchored to machine-checked numeric examples.

## Licenses

- **Code**: [Apache-2.0](LICENSE)
- **Educational content** (`docs/`, lab guides, manuscript text):
  [CC BY 4.0](LICENSE-docs)
- **Third-party models** (`third_party/mujoco_menagerie`): keep each model
  directory's own license file; the Panda model is from
  [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie).

## Citing

If you use these labs in teaching or research, please cite this repository.
Machine-readable metadata is in [`CITATION.cff`](CITATION.cff) — GitHub shows
a "Cite this repository" button from it. A JOSE submission is in preparation
and an archival Zenodo DOI will be added here once the first release is cut.
