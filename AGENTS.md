# Agent Guide

이 문서는 `README.md`와 `SIMULATOR_DEVELOPMENT_SPEC.md`를 기준으로, 앞으로 이 저장소에서 코딩 에이전트가 어떤 순서와 기준으로 작업해야 하는지 정리한 운영 가이드입니다.

## Project Intent

이 프로젝트는 산업용 로봇의 정밀 디지털 트윈이 아니라, MuJoCo 기반의 교육용 로봇 제어 실험실입니다. 모든 랩은 같은 물리 엔진, 같은 실행 방식, 같은 로깅/플로팅 파이프라인을 공유해야 합니다.

핵심 제품 가치는 다음입니다.

- 제어 파라미터 변화가 동역학 응답에 미치는 영향을 눈으로 확인한다.
- 1D 시스템에서 시작해 2DOF, 6/7DOF 매니퓰레이터까지 같은 개념을 확장한다.
- 실행 결과를 재현 가능한 YAML config, CSV/NPZ log, plot 이미지로 남긴다.
- 강의 자료에 바로 쓸 수 있는 안정적인 로컬 데모를 만든다.

## Non-Negotiable Rules

- 모든 랩은 MuJoCo로 구현한다.
- 첫 마일스톤은 웹이 아니라 로컬 CLI, MuJoCo viewer, 저장된 plot이다.
- 6/7DOF 모델은 직접 CAD/Blender로 만들지 말고 MuJoCo Menagerie 등 검증된 모델을 사용한다.
- `lab04` 6/7DOF POC를 가장 먼저 성공시킨다.
- 코드 구조는 단순하고 교육적으로 읽기 쉬워야 한다.
- 설정은 YAML로 재현 가능해야 한다.
- 로그와 plot 저장은 기본 동작으로 유지한다.
- third-party 모델이나 submodule을 추가하면 원본 라이선스를 보존한다.

## Repository Map

```text
configs/              Reproducible YAML experiment configs
models/               MuJoCo XML scenes and local model wrappers
third_party/          External models, preferably as submodules
src/mclab/            Python package source
src/mclab/sim/        Shared simulation loop, MuJoCo helpers, logging, plotting
src/mclab/controllers/Readable control laws
src/mclab/trajectories/Trajectory generators with a common interface
src/mclab/labs/       Lab-specific assembly code
src/mclab/analysis/   Metrics and report helpers
tests/                Fast unit and smoke tests
docs/                 Short lab explanations and teaching notes
outputs/              Generated run artifacts, ignored except `.gitkeep`
```

## Development Strategy

## Current Implementation Status

Implemented and verified:

- Phase 0 package skeleton, CLI, config loading, logger, plotting helper
- Lab01 mass-spring-damper on a MuJoCo slide-joint plant
- Lab02 PID control on the same MuJoCo plant
- Lab01/Lab02 viewer visual guides for equilibrium, target, and applied force direction
- Lab03 trajectory planning plus a torque-actuated 2DOF planar arm
- Lab03 FK, IK helper, analytic Jacobian, joint-space tracking, and task-space Jacobian-transpose PD
- Lab03 viewer visual guides for 2DOF hand target, current hand position, and singularity warning state
- Lab04 Franka Emika Panda manipulator using MuJoCo Menagerie
- Lab04 Cartesian reach with damped-least-squares Jacobian target offsets
- Lab04 soft/stiff Cartesian reach comparison configs and batch report
- Lab04 Cartesian interactive one-line launcher for live XYZ target tuning
- Lab04 deterministic virtual wall with soft/stiff stiffness-damping comparison configs
- Lab04 viewer visual guides for Cartesian target, current hand position, contact state, and virtual wall
- YAML configs, MuJoCo XML models, docs, and tests for the implemented labs
- Run reports with domain-specific checks for singularity, DLS speed, virtual wall response, and actuator effort
- Batch comparison reports with scenario cards, automatic comparison takeaways, min/max highlights, baseline deltas, parameter differences, and comparison plots
- Interactive `MCLab Interaction` quick presets with value previews for representative damping, PID, 2DOF reach, Panda reach, and virtual wall parameter sets
- Learner menu preset labels for interactive cards, including preset-name search
- Learner menu Explore filters for hands-on, comparison, PID, 2DOF, Panda, wall, and singularity scenario discovery
- Learner menu and CLI setup diagnostics through `python -m mclab doctor`
- Learner menu scenario readiness checks that disable run buttons when config or model assets are missing
- Learner menu scenario history labels and per-scenario latest-report buttons
- Learner menu scenario evidence labels for latest observation markers and learner notes
- Learner menu scenario value previews for key YAML parameters, searchable from the menu
- Learner menu, interaction panel, and run report reflection questions, searchable from the menu
- Learner menu scenario follow-up guidance and `Next` buttons for guided comparison flow
- Learner menu scenario-to-batch comparison guidance and `Compare` buttons
- Learner menu batch readiness checks that disable unavailable comparison launches
- Learner menu batch history labels and per-batch latest-report buttons
- Learner menu learning-path step report buttons for completed course steps
- Run reports include suggested next-run cards with reflection questions, key parameter changes, and ready-to-run commands for every guided config
- Observation markers capture the active learning question, learner notes, changed sliders, full slider snapshots, and live status snapshots
- Run reports summarize observation marker questions and learner notes with a review prompt
- Outputs index learning path cards include ready-to-run or repeat commands for each course step
- Run reports show configured preset cards and summarize learner actions, latest slider values, preset choices, observation markers, and raw interaction events

Verified commands:

```bash
python -m pytest -q
python scripts/bootstrap_and_run.py --verify
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --headless --plot
python -m mclab run lab03 --config configs/lab03_2dof/joint_space_2dof.yaml --headless --plot
python -m mclab run lab03 --config configs/lab03_2dof/task_space_2dof.yaml --headless --plot --plots task
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

The older Lab03 1D trajectory configs are still available for profile comparison. `lab04` currently uses Menagerie position actuators; do not treat it as a raw torque-control digital twin.

### Phase 0 - Package Skeleton

Goal: make the repository installable and navigable without implementing lab behavior yet.

Deliverables:

- `pyproject.toml`
- CLI entry point
- config loader stub
- package imports
- initial smoke tests
- README command accuracy check

Recommended first task:

```text
Initialize the Python package skeleton according to README.md and SIMULATOR_DEVELOPMENT_SPEC.md. Add pyproject.toml, src/mclab, tests, and a CLI entry point that prints available labs. Do not implement the labs yet.
```

### Phase 1 - Lab04 6/7DOF POC First

Goal: load a Panda or UR5e model, hold a neutral pose, track a simple smooth joint trajectory, and save logs/plots.

Target command:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --plot
```

Success criteria:

- model loads without manual asset path hacks
- viewer opens
- neutral pose remains stable for at least 10 seconds
- one or more joints track a smooth trajectory
- `q`, `qdot`, `ctrl`, `tau_cmd`, `x_ee` are logged
- plots are saved automatically
- the command is reproducible from a clean checkout with documented setup

Implementation notes:

- Start with joint PD plus MuJoCo bias force compensation.
- Explicitly map controlled joint names and actuator names.
- Clip torque commands from the first working version.
- If the Menagerie actuator interface does not fit torque control, create one clearly documented local wrapper scene.

### Phase 2 - Shared Infrastructure

Goal: factor only the infrastructure already proven by `lab04`.

Build:

- shared simulation runner
- logger that writes `config.yaml`, `log.csv`, `states.npz`, `summary.json`
- standard Matplotlib plotting utilities
- common target/trajectory interface
- config validation with Pydantic

Avoid building a broad framework before at least one real lab runs.

### Phase 3 - Lab01 Mass-Spring-Damper

Goal: show physical response to mass, damping, stiffness, initial state, and force input.

Required configs:

- `default.yaml`
- `underdamped.yaml`
- `over_damped.yaml`
- `high_stiffness.yaml`
- `low_stiffness.yaml`

Required outputs:

- position
- velocity
- acceleration estimate
- applied force
- kinetic/potential energy

### Phase 4 - Lab02 PID Control

Goal: use the Lab01 plant to explain P, PD, PID, windup, anti-windup, saturation, noise, and delay.

Required metrics:

- rise time
- overshoot percent
- settling time
- steady-state error
- max control effort

### Phase 5 - Lab03 2DOF Manipulator

Goal: bridge simple plants and full manipulator control.

Build:

- FK
- IK helper
- Jacobian
- joint-space trajectory tracking
- task-space Jacobian-transpose PD
- singularity demo
- torque/current proxy plots

Implemented so far:

- FK, IK helper, and analytic Jacobian in `src/mclab/sim/two_link.py`
- torque-actuated MuJoCo model in `models/lab03_2dof/two_link.xml`
- joint-space and task-space configs
- interactive task-space target/stiffness/damping/torque tuning
- singularity demo with Jacobian determinant, manipulability, and condition number logging/plotting
- damped least-squares singularity demo with DLS gain/damping and joint-speed logging/plotting
- standard logs and plots for joint position, end-effector position, torque, current proxy, and error

Remaining likely extension:

- richer singularity comparison lessons, such as condition-aware task control

### Phase 6 - Lab04 Advanced Control

Goal: turn the POC into the course-facing manipulator demo.

Required demos:

- neutral pose hold
- joint-space trajectory tracking
- end-effector position control
- translational Cartesian impedance
- deterministic virtual wall
- stiffness/damping comparison
- torque/current proxy visualization

Implemented so far:

- neutral pose hold
- joint-space trajectory tracking with Menagerie position actuators
- Cartesian reach using damped-least-squares Jacobian target offsets
- soft/stiff Cartesian reach comparison using Cartesian error and actuator effort metrics
- deterministic virtual wall with Jacobian-based target retreat
- soft/stiff wall comparison using wall force, penetration, and retreat metrics
- interactive wall position/stiffness/damping/retreat tuning
- viewer visual guides for target point, current hand point, contact hand point, and wall plane
- torque/current proxy visualization from MuJoCo actuator force output

Use translational-only impedance first. Add orientation impedance only after the simpler demo is stable.

## Coding Guidelines

- Prefer small, readable modules over generic abstractions.
- Keep controller equations visible in the controller files.
- Use SI units in configs and docs.
- Use explicit names for joints, actuators, bodies, and sites.
- Keep plotting consistent across labs.
- Write smoke tests that run headless and quickly.
- Do not require a viewer in CI or automated tests.
- Do not change project scope toward ROS2, Isaac Sim, or browser deployment in the first milestone.

## Testing Strategy

Add tests as soon as the corresponding feature exists.

Minimum expected tests:

- CLI imports and lists labs
- config loading and validation
- PID zero-error produces zero output
- trajectory boundary conditions
- Lab01 headless smoke run
- Lab04 model-load smoke test when assets are available

Viewer-based checks should be manual or optional, not required for fast test runs.

## Risk Handling

| Risk | Response |
|---|---|
| 6/7DOF asset paths fail | Prefer Menagerie submodule or a documented `robot_descriptions` path. Keep one working model path canonical. |
| Actuator type mismatch | Inspect actuators before writing controllers. Use the model's intended control interface or create a local motor-actuated wrapper scene. |
| Impedance instability | Start with low translational stiffness, small timestep, damping, and torque clipping. |
| Contact force complexity | Start with deterministic virtual wall force before MuJoCo contact extraction. |
| Over-abstraction | Only extract shared code after two concrete use cases need it. |
| Plot inconsistency | Centralize plot naming and signal conventions early. |

## Definition of Done

A lab is done when:

- it runs with one documented command
- it works headless and optionally with viewer
- it logs important state variables
- it saves standard plots
- it has default and comparison configs
- it has a short explanation in `docs/`
- it has at least one fast smoke test

The full project is course-demo ready when:

- all four labs run locally
- `lab04` runs for at least 30 seconds without numerical instability
- impedance and virtual wall demos are stable enough for live teaching
- generated plots are readable in lecture slides
- README quickstart works from a clean environment

## Next Best Task

Continue expanding Lab04 impedance/wall lessons or add Lab03 condition-aware task-control comparisons. Do not add web, ROS2, or Isaac Sim scope before the local MuJoCo labs are stable.
