# MuJoCo Manipulator Control Lab

**MuJoCo Manipulator Control Lab**은 MuJoCo 하나로 질량-스프링-댐퍼 시스템부터 PID 제어, 2DOF 매니퓰레이터, 6/7DOF 매니퓰레이터 제어까지 실습하는 교육용 로봇 제어 시뮬레이터입니다.

이 저장소의 목표는 “산업용 로봇과 정량적으로 동일한 디지털 트윈”이 아니라, 제어 파라미터가 로봇의 움직임에 어떤 영향을 주는지 눈으로 확인하는 **교육용 동역학 시뮬레이션 실험실**을 만드는 것입니다.

---

## Recommended repository name

```text
mujoco-manipulator-control-lab
```

대체 후보:

```text
mujoco-robot-control-lab
robot-control-playground
physical-ai-control-lab
```

추천 라이선스: **Apache-2.0**

이유:

- MuJoCo 생태계와 잘 맞는 permissive license입니다.
- 교육용 코드, 예제, 연구용 확장에 적합합니다.
- MuJoCo Menagerie 모델을 참고하거나 submodule로 연결할 때 라이선스 정리가 비교적 깔끔합니다.
- 단, `third_party/`에 외부 모델을 포함하거나 submodule로 연결할 경우 각 모델 디렉터리의 `LICENSE`를 반드시 보존해야 합니다.

---

## Project scope

이 프로젝트는 네 개의 시뮬레이터를 모두 MuJoCo 기반으로 구현합니다.

| Lab | Topic | Main purpose |
|---|---|---|
| `lab01_mass_spring_damper` | Mass-Spring-Damper | stiffness, damping, mass, force, overshoot, oscillation 이해 |
| `lab02_pid_control` | PID Control | Kp, Ki, Kd, saturation, delay, noise 변화에 따른 응답 비교 |
| `lab03_2dof_arm` | 2DOF Manipulator | FK, IK, Jacobian, trajectory profile, joint/task-space control 이해 |
| `lab04_panda_or_ur5e` | 6/7DOF Manipulator | joint control, trajectory, torque/current proxy, Cartesian impedance, virtual wall 실습 |

핵심 Lab은 `lab04_panda_or_ur5e`입니다. 따라서 개발은 6/7DOF POC부터 시작합니다.

---

## What this project should demonstrate

수강생은 같은 로봇 모델에서 아래 현상을 직접 확인할 수 있어야 합니다.

- `Kp`, `Kd`, `Ki` 변화에 따른 오버슈트, 진동, 수렴 속도 변화
- 질량, 감쇠, 강성 변화에 따른 출렁임과 에너지 소산
- step input, trapezoidal profile, S-curve, minimum-jerk trajectory 차이
- 위치, 속도, 가속도, jerk profile과 토크 피크의 관계
- 토크 제한과 current proxy 제한이 응답에 주는 영향
- 6/7DOF 매니퓰레이터의 joint-space control과 task-space control 차이
- Cartesian stiffness/damping 설정에 따른 impedance control 반응 차이
- virtual wall 또는 접촉 상황에서 위치제어와 임피던스 제어의 차이

---

## Non-goals

이 저장소는 아래를 목표로 하지 않습니다.

- 실제 산업용 로봇과 정량적으로 일치하는 고정밀 digital twin
- 모터 드라이버, 전류 루프, 전력전자까지 포함한 full actuator simulation
- 복잡한 웹 배포, React/Three.js 기반 실시간 웹 시뮬레이터
- Blender/CAD 기반 6DOF 로봇 모델링
- ROS2/Isaac Sim 연동

전류는 초기 버전에서 다음과 같은 교육용 proxy로 다룹니다.

```text
current_proxy = torque_command / Kt
```

---

## Target user experience

초기 버전은 웹이 아니라 로컬 실행을 우선합니다.

현재 구현된 첫 번째 로컬 실행 범위:

```bash
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --headless --plot
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

현재 `lab03`은 2DOF 매니퓰레이터 전체 구현 전 단계로, 1D MuJoCo plant에서 step, trapezoidal, minimum-jerk, S-curve trajectory를 생성하고 추종하는 trajectory planning lab입니다.

목표 실행 방식:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer
python -m mclab run lab04 --config configs/lab04_panda/impedance_wall.yaml --viewer
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --viewer
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --plot
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --plot
```

각 실행은 다음 결과물을 남깁니다.

```text
outputs/
└── <timestamp>_<lab_name>/
    ├── config.yaml
    ├── log.csv
    ├── states.npz
    ├── summary.json
    ├── plots/
    │   ├── position.png
    │   ├── velocity.png
    │   ├── acceleration.png
    │   ├── torque.png
    │   └── current_proxy.png
    └── notes.md
```

---

## 사용자 가이드

### 빠른 실행

Windows PowerShell에서 가장 쉬운 방법:

```powershell
.\run_all.ps1
```

PowerShell 실행 정책 때문에 막히면:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_all.ps1
```

macOS/Linux 또는 Python으로 직접 실행하려면:

```bash
python scripts/bootstrap_and_run.py --verify
```

이 명령은 아래 작업을 한 번에 수행합니다.

- `.venv` 가상환경 생성
- Python 패키지 설치
- MuJoCo Menagerie 다운로드
- 테스트와 lint 실행
- 네 개 시뮬레이터를 headless 모드로 실행
- `outputs/` 아래에 로그와 plot 저장

### 수동 설치

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

MuJoCo Menagerie가 없으면 다음 명령으로 받습니다.

```bash
git clone --depth 1 https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
```

또는 자동 세팅만 실행합니다.

```bash
python scripts/bootstrap_and_run.py --setup-only
```

### 개별 실행

가상환경을 활성화한 뒤:

```bash
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --headless --plot
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

가상환경을 활성화하지 않고 Windows에서 직접 실행하려면:

```powershell
.\.venv\Scripts\python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

Viewer를 띄우고 움직임을 실제 시간에 가깝게 보려면 `--headless` 대신 `--viewer --realtime`을 사용합니다. 실행이 끝난 뒤 창을 유지하려면 `--pause-at-end`를 함께 붙입니다.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot
```

CLI 형식:

```bash
python -m mclab run <lab_name> --config <config_path> [--headless] [--viewer] [--realtime] [--pause-at-end] [--plot] [--output-dir <path>]
```

사용 가능한 lab 이름 확인:

```bash
python -m mclab list
```

### 파라미터 변경 방법

실험 파라미터는 `configs/` 아래 YAML 파일에서 바꿉니다. 기존 파일을 직접 수정해도 되고, 비교 실험을 위해 복사해서 새 파일을 만드는 것을 추천합니다.

예:

```bash
cp configs/lab02_pid/default.yaml configs/lab02_pid/my_pid_test.yaml
```

Windows PowerShell:

```powershell
Copy-Item configs/lab02_pid/default.yaml configs/lab02_pid/my_pid_test.yaml
```

그 다음 `my_pid_test.yaml`의 값을 수정하고 실행합니다.

```bash
python -m mclab run lab02 --config configs/lab02_pid/my_pid_test.yaml --headless --plot
```

자주 바꾸는 파라미터:

| Lab | Config path | Main parameters |
|---|---|---|
| Lab01 MSD | `configs/lab01_msd/*.yaml` | `mass`, `damping`, `stiffness`, `initial_position`, `force_input.magnitude` |
| Lab02 PID | `configs/lab02_pid/*.yaml` | `controller.kp`, `controller.ki`, `controller.kd`, `controller.output_limit`, `measurement_noise_std`, `control_delay` |
| Lab03 Trajectory | `configs/lab03_2dof/*.yaml` | `trajectory.type`, `trajectory.start`, `trajectory.end`, `trajectory.duration`, `tracking_controller.kp`, `tracking_controller.kd` |
| Lab04 Panda | `configs/lab04_panda/*.yaml` | `controlled_joint_index`, `trajectory.end`, `virtual_wall.wall_x`, `virtual_wall.stiffness`, `virtual_wall.damping` |

Lab02 PID 예시:

```yaml
controller:
  kp: 80.0
  ki: 0.0
  kd: 18.0
  output_limit: 100.0
  anti_windup: true
```

Lab03 trajectory 예시:

```yaml
trajectory:
  type: minimum_jerk
  start: 0.0
  end: 0.6
  duration: 2.0
  start_time: 0.4
```

Lab04 virtual wall 예시:

```yaml
virtual_wall:
  wall_x: 0.57
  stiffness: 260.0
  damping: 12.0
```

### 결과 확인

실행 결과는 `outputs/` 아래에 저장됩니다.

```text
outputs/
└── <run_name>/
    ├── config.yaml
    ├── log.csv
    ├── states.npz
    ├── summary.json
    ├── notes.md
    └── plots/
```

- `log.csv`: 시간별 position, velocity, control force, torque/current proxy 등
- `states.npz`: NumPy로 읽기 좋은 배열 데이터
- `summary.json`: overshoot, settling time, tracking error 같은 요약 지표
- `plots/`: 강의 자료에 바로 쓰기 좋은 PNG plot

### 검증 명령

```bash
python -m pytest -q
python -m ruff check src tests scripts
```

### 문제 해결

- `mujoco_menagerie`가 없다는 오류가 나면 `python scripts/bootstrap_and_run.py --setup-only`를 실행합니다.
- `python -m mclab`가 동작하지 않으면 가상환경을 활성화했는지 확인하거나 `.\.venv\Scripts\python -m mclab ...` 형식으로 실행합니다.
- Viewer가 열리지 않으면 먼저 `--headless --plot`으로 실행해 시뮬레이션 자체가 정상인지 확인합니다.
- Viewer가 잠깐 뜨고 닫히면 정상 종료된 것입니다. 오래 보려면 `--viewer --realtime --pause-at-end`를 사용하거나 YAML의 `sim_time` 값을 늘립니다.
- `outputs/`가 너무 커지면 필요한 결과만 남기고 실행 결과 폴더를 삭제해도 됩니다.

---

## User Guide

### Quick Start

The easiest option on Windows PowerShell:

```powershell
.\run_all.ps1
```

If PowerShell blocks script execution:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_all.ps1
```

On macOS/Linux, or if you prefer calling Python directly:

```bash
python scripts/bootstrap_and_run.py --verify
```

This command performs the full local setup and verification:

- creates `.venv`
- installs Python dependencies
- downloads MuJoCo Menagerie
- runs tests and lint checks
- runs all four simulators in headless mode
- saves logs and plots under `outputs/`

### Manual Installation

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

If MuJoCo Menagerie is missing, fetch it with:

```bash
git clone --depth 1 https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
```

Or run setup only:

```bash
python scripts/bootstrap_and_run.py --setup-only
```

### Running Individual Labs

After activating the virtual environment:

```bash
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --headless --plot
python -m mclab run lab03 --config configs/lab03_2dof/minimum_jerk.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

Without activating the virtual environment on Windows:

```powershell
.\.venv\Scripts\python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

Use `--viewer --realtime` instead of `--headless` to open the MuJoCo viewer and pace motion close to wall-clock time. Add `--pause-at-end` to keep the window open after the simulation finishes.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot
```

CLI shape:

```bash
python -m mclab run <lab_name> --config <config_path> [--headless] [--viewer] [--realtime] [--pause-at-end] [--plot] [--output-dir <path>]
```

List available labs:

```bash
python -m mclab list
```

### Changing Parameters

Experiment parameters live in YAML files under `configs/`. You can edit an existing config, but copying one first is usually better for comparisons.

Example:

```bash
cp configs/lab02_pid/default.yaml configs/lab02_pid/my_pid_test.yaml
```

Windows PowerShell:

```powershell
Copy-Item configs/lab02_pid/default.yaml configs/lab02_pid/my_pid_test.yaml
```

Edit the new file, then run it:

```bash
python -m mclab run lab02 --config configs/lab02_pid/my_pid_test.yaml --headless --plot
```

Common parameters:

| Lab | Config path | Main parameters |
|---|---|---|
| Lab01 MSD | `configs/lab01_msd/*.yaml` | `mass`, `damping`, `stiffness`, `initial_position`, `force_input.magnitude` |
| Lab02 PID | `configs/lab02_pid/*.yaml` | `controller.kp`, `controller.ki`, `controller.kd`, `controller.output_limit`, `measurement_noise_std`, `control_delay` |
| Lab03 Trajectory | `configs/lab03_2dof/*.yaml` | `trajectory.type`, `trajectory.start`, `trajectory.end`, `trajectory.duration`, `tracking_controller.kp`, `tracking_controller.kd` |
| Lab04 Panda | `configs/lab04_panda/*.yaml` | `controlled_joint_index`, `trajectory.end`, `virtual_wall.wall_x`, `virtual_wall.stiffness`, `virtual_wall.damping` |

Lab02 PID example:

```yaml
controller:
  kp: 80.0
  ki: 0.0
  kd: 18.0
  output_limit: 100.0
  anti_windup: true
```

Lab03 trajectory example:

```yaml
trajectory:
  type: minimum_jerk
  start: 0.0
  end: 0.6
  duration: 2.0
  start_time: 0.4
```

Lab04 virtual wall example:

```yaml
virtual_wall:
  wall_x: 0.57
  stiffness: 260.0
  damping: 12.0
```

### Reading Outputs

Each run writes artifacts under `outputs/`.

```text
outputs/
└── <run_name>/
    ├── config.yaml
    ├── log.csv
    ├── states.npz
    ├── summary.json
    ├── notes.md
    └── plots/
```

- `log.csv`: time-series signals such as position, velocity, control force, torque/current proxy
- `states.npz`: NumPy-friendly arrays
- `summary.json`: metrics such as overshoot, settling time, tracking error
- `plots/`: PNG plots suitable for quick inspection or lecture slides

### Verification

```bash
python -m pytest -q
python -m ruff check src tests scripts
```

### Troubleshooting

- If `mujoco_menagerie` is missing, run `python scripts/bootstrap_and_run.py --setup-only`.
- If `python -m mclab` fails, activate `.venv` or run `.\.venv\Scripts\python -m mclab ...`.
- If the viewer does not open, first run with `--headless --plot` to confirm that simulation works.
- If the viewer opens briefly and closes, the run completed normally. Use `--viewer --realtime --pause-at-end` or increase `sim_time` in the YAML config.
- If `outputs/` grows too large, you can delete old run folders safely.

---

## Suggested repository structure

```text
mujoco-manipulator-control-lab/
├── README.md
├── SIMULATOR_DEVELOPMENT_SPEC.md
├── LICENSE
├── pyproject.toml
├── .gitignore
├── configs/
│   ├── lab01_msd/
│   ├── lab02_pid/
│   ├── lab03_2dof/
│   └── lab04_panda/
├── models/
│   ├── lab01_msd/
│   │   └── scene.xml
│   ├── lab02_pid/
│   │   └── scene.xml
│   ├── lab03_2dof/
│   │   └── scene.xml
│   └── lab04_panda/
│       └── scene.xml
├── third_party/
│   └── mujoco_menagerie/          # optional git submodule
├── src/
│   └── mclab/
│       ├── __init__.py
│       ├── cli.py
│       ├── sim/
│       │   ├── runner.py
│       │   ├── logging.py
│       │   └── viewer.py
│       ├── controllers/
│       │   ├── pid.py
│       │   ├── joint_pd.py
│       │   ├── operational_space.py
│       │   └── impedance.py
│       ├── trajectories/
│       │   ├── step.py
│       │   ├── trapezoidal.py
│       │   ├── s_curve.py
│       │   └── minimum_jerk.py
│       ├── labs/
│       │   ├── lab01_msd.py
│       │   ├── lab02_pid.py
│       │   ├── lab03_2dof.py
│       │   └── lab04_panda.py
│       └── plots/
│           └── standard_plots.py
├── tests/
│   ├── test_pid.py
│   ├── test_trajectories.py
│   ├── test_2dof_kinematics.py
│   └── test_lab_smoke.py
└── outputs/
    └── .gitkeep
```

## Development order

이 프로젝트는 1D부터 순서대로 만들지 않습니다. 핵심 리스크가 6/7DOF이므로 `lab04` POC를 먼저 만듭니다.

### Phase 0 — Repository skeleton

- `pyproject.toml`
- package skeleton
- config loader
- output logger
- smoke test

### Phase 1 — 6/7DOF POC first

목표:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer
```

필수 기능:

- Panda 또는 UR5e 모델 로딩
- MuJoCo viewer 실행
- neutral pose 유지
- joint PD control
- trajectory target 적용
- `q`, `qdot`, `tau_cmd`, `x_ee` logging
- 결과 plot 저장

이 단계가 실패하면 강의형 프로젝트로 진행하면 안 됩니다.

### Phase 2 — Mass-Spring-Damper

- slide joint body
- mass, damping, stiffness config
- external force input
- response plot

현재 구현됨:

- `models/lab01_msd/scene.xml`
- `configs/lab01_msd/default.yaml`
- underdamped, over_damped, high_stiffness, low_stiffness comparison configs
- automatic CSV/NPZ/summary/plot outputs

### Phase 3 — PID Control

- 같은 1D plant 사용
- PID controller
- anti-windup
- actuator saturation
- delay/noise option

현재 구현됨:

- `models/lab02_pid/scene.xml`
- scalar PID controller
- output saturation
- anti-windup option
- measurement noise and control delay config hooks
- standard step-response metrics

### Phase 4 — 2DOF Arm

- hinge joint 2개
- FK/IK/Jacobian
- joint-space trajectory
- task-space trajectory
- torque/current proxy plot

현재 선행 구현:

- `lab03` trajectory planning on a 1D MuJoCo plant
- step, trapezoidal, quintic/minimum-jerk, S-curve trajectory generators
- target position/velocity/acceleration/jerk logging and plotting

### Phase 5 — 6/7DOF advanced control

- gravity compensation
- task-space position control
- Cartesian impedance control
- virtual wall
- stiffness/damping comparison
- torque/current proxy visualization

현재 구현됨:

- MuJoCo Menagerie Franka Emika Panda 모델 로딩
- neutral pose hold
- Menagerie position actuator 기반 joint-space trajectory tracking
- `q`, `qdot`, `ctrl`, `tau_cmd`, `current_proxy`, `x_ee`, `xdot_ee` logging
- Jacobian 기반 target retreat를 쓰는 virtual wall 교육용 데모
- automatic CSV/NPZ/summary/plot outputs

---

## Lab design details

### Lab 01 — Mass-Spring-Damper

Core equation:

```text
m x_ddot + c x_dot + k x = F
```

MuJoCo model concept:

```text
world
└── body: block
    └── slide joint along x
```

Parameters:

```yaml
mass: 1.0
stiffness: 50.0
damping: 2.0
initial_position: 0.1
initial_velocity: 0.0
external_force: 0.0
sim_time: 5.0
```

Expected plots:

- position
- velocity
- acceleration
- force
- energy

---

### Lab 02 — PID Control

Controller:

```text
u = Kp * e + Ki * integral(e) + Kd * e_dot
```

Required experiments:

- low Kp / high Kp comparison
- Kd damping effect
- Ki steady-state error effect
- saturation and windup
- noise and delay instability

---

### Lab 03 — 2DOF Manipulator

Model:

```text
base
└── link1, hinge joint q1
    └── link2, hinge joint q2
```

Required concepts:

- forward kinematics
- inverse kinematics
- Jacobian
- joint-space vs task-space motion
- trajectory profile comparison
- singularity visualization

Trajectory types:

- step
- trapezoidal velocity
- S-curve
- minimum jerk

---

### Lab 04 — 6/7DOF Manipulator

Initial model:

```text
Franka Emika Panda 7DOF
```

Minimum required demos:

1. model loading
2. neutral pose hold
3. joint-space PD control
4. trajectory profile tracking
5. torque/current proxy logging
6. end-effector pose tracking
7. Cartesian stiffness/damping comparison
8. impedance control against virtual wall

Joint PD control:

```text
tau = Kp * (q_des - q) + Kd * (qdot_des - qdot) + tau_bias
```

Cartesian impedance control:

```text
F_task = Kx * (x_des - x) + Dx * (xdot_des - xdot)
tau = J^T * F_task + tau_bias
```

Current proxy:

```text
current_proxy = tau_cmd / Kt
```

For the first implementation, `Kt` can be set to `1.0` so that current proxy and torque have the same scale. Later, use joint-specific constants if available.

---

## Definition of done

A lab is considered done when:

- it runs with one command
- it can run with or without viewer
- it logs all important state variables
- it saves plots automatically
- it has one default config and at least two comparison configs
- it has a short explanation in `docs/` or `notes.md`
- it has at least one smoke test

The entire project is considered course-demo ready when:

- all four labs run locally
- `lab04` runs for at least 30 seconds without numerical instability
- `lab04` demonstrates at least one impedance/stiffness comparison
- plots are readable and directly usable in lecture slides
- the README quickstart commands work on a clean environment

---

## Suggested GitHub issues

Create these issues after repository initialization:

```text
[Phase 0] Initialize Python package and config system
[Phase 1] Load Panda/UR5e model in MuJoCo viewer
[Phase 1] Implement joint PD control for 6/7DOF arm
[Phase 1] Add logging and standard plots
[Phase 2] Implement mass-spring-damper lab
[Phase 3] Implement PID lab with saturation and anti-windup
[Phase 4] Implement 2DOF arm model and FK/Jacobian utilities
[Phase 4] Add trajectory generators: step, trapezoidal, minimum jerk
[Phase 5] Implement Cartesian impedance control
[Phase 5] Implement virtual wall demo
[Docs] Add lecture notes and experiment explanations
```

---

## References

- MuJoCo documentation: https://mujoco.readthedocs.io/
- MuJoCo Python API: https://mujoco.readthedocs.io/en/stable/python.html
- MuJoCo Menagerie: https://github.com/google-deepmind/mujoco_menagerie
- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0
