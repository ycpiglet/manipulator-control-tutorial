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
python -m mclab run lab03 --config configs/lab03_2dof/joint_space_2dof.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

현재 `lab03`은 실제 2DOF planar arm을 포함합니다. `joint_space_2dof.yaml`은 어깨/팔꿈치 joint-space PD trajectory tracking을 보여주고, `task_space_2dof.yaml`은 FK/Jacobian 기반 end-effector task-space 제어를 보여줍니다. 기존 1D step, trapezoidal, minimum-jerk, S-curve trajectory 비교 config도 profile 학습용으로 유지됩니다.

목표 실행 방식:

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer
python -m mclab run lab04 --config configs/lab04_panda/impedance_wall.yaml --viewer
python -m mclab run lab03 --config configs/lab03_2dof/joint_space_2dof.yaml --viewer
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --plot
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --plot
```

CLI로 직접 실행할 때도 완료 후 리포트를 바로 열고 싶으면 `--open-report`를 추가합니다.

각 실행은 다음 결과물을 남깁니다.

```text
outputs/
├── index.html
└── <timestamp>_<lab_name>/
    ├── config.yaml
    ├── log.csv
    ├── states.npz
    ├── summary.json
    ├── report.html
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
.\run_mclab.cmd
```

이 명령은 학습자용 메뉴를 엽니다. 메뉴에서 Lab01-04의 자동 데모, 비교 시나리오, interactive 데모, Panda virtual wall 데모를 버튼으로 실행할 수 있습니다. 검색창에 `PID`, `noise`, `wall`, `interactive` 같은 키워드를 넣으면 관련 시나리오만 바로 볼 수 있습니다. 각 항목에는 `Try` / `Change` / `Watch` 안내가 붙어 있어 학습자가 무엇을 해보고, 어떤 YAML 파라미터를 바꾸고, 무엇을 관찰해야 하는지 바로 알 수 있습니다. `Config`는 해당 YAML 파라미터 파일을 열고, `Lesson`은 랩 설명 문서를 엽니다. 각 데모는 사이드 패널 없는 MuJoCo viewer를 열고, 필요한 경우 `MCLab Interaction` 창을 함께 띄웁니다. 이 창에는 현재 데모의 `Try` / `Change` / `Watch` 안내, 버튼, 슬라이더, live status가 표시됩니다. run과 batch 버튼은 완료 후 `report.html`을 자동으로 엽니다. 실행이 끝나면 메뉴 상태줄에 최신 결과 폴더가 표시되고, `Open latest report`로 실행 리포트를 다시 열 수 있습니다. 여러 실행 결과를 다시 보려면 `Open all reports`로 `outputs/index.html`을 엽니다.

메뉴에 포함된 주요 비교 시나리오:

| Lab | Scenario examples |
|---|---|
| Lab01 | underdamped, overdamped, high/low stiffness, interactive pull |
| Lab02 | low/high P gain, PD damping, saturation, windup vs anti-windup, sensor noise, control delay, interactive disturbance |
| Lab03 | 2DOF joint-space, 2DOF task-space, singularity, interactive XY target tuning, step/trapezoidal/minimum-jerk/S-curve profiles |
| Lab04 | neutral hold, joint trajectories, hand X motion, Cartesian reach, soft/stiff virtual wall, joint target nudge, virtual wall |

처음 학습자는 메뉴 상단의 `Recommended learning path`를 순서대로 따라가면 됩니다.
각 단계는 `outputs/`의 실행 기록을 읽어 `Done` 또는 `Not run yet` 상태를 보여줍니다. 메뉴 상단에는 전체 진행률과 다음 권장 단계가 표시되며, `Run next`를 누르면 아직 완료하지 않은 첫 단계를 바로 실행합니다. 실행 후 상태가 바로 바뀌지 않으면 `Refresh path`를 누릅니다.

| Step | Menu button | What it builds |
|---|---|---|
| 1 | `Feel 1D physics` | mass-spring-damper의 위치, 속도, 힘, 에너지 |
| 2 | `Disturb and tune` | 외란과 mass/damping/stiffness live tuning |
| 3 | `Close the loop` | PID tracking, error, control force |
| 4 | `Tune PID live` | target/Kp/Ki/Kd/force limit 조정 |
| 5 | `Move 2DOF joints` | 2DOF joint-space tracking |
| 6 | `Control the hand` | Jacobian 기반 task-space hand control |
| 7 | `Hold Panda` | 7DOF Panda neutral hold baseline |
| 8 | `Touch virtual wall` | virtual wall stiffness/damping 체험 |
| 9 | `Compare the course` | 모든 batch 비교 리포트 생성 |

개별 랩을 바로 실행하고 싶으면:

```powershell
.\run_lab01.cmd
.\run_lab02.cmd
.\run_lab03.cmd
.\run_lab04.cmd
```

각 명령은 해당 viewer를 사이드 패널 없이 열고, 랩별 핵심 그래프를 저장한 뒤 실행 리포트를 자동으로 엽니다. `.venv`가 없으면 먼저 자동 setup을 실행합니다. `run_lab04.cmd`는 MuJoCo Menagerie가 없을 때도 setup을 실행합니다.

| Command | Opens | Essential plots |
|---|---|---|
| `.\run_lab01.cmd` | mass-spring-damper viewer | `position`, `velocity`, `force` |
| `.\run_lab02.cmd` | PID viewer | `position`, `control_force`, `error` |
| `.\run_lab03.cmd` | 2DOF arm viewer | `position`, `end_effector`, `torque`, `error` |
| `.\run_lab04.cmd` | Panda viewer | `position`, `error` |

여러 조건을 한 번에 비교하려면 메뉴의 `Comparison batches` 버튼을 누르거나 CLI batch를 실행합니다.

```powershell
.\run_batch_lab01.cmd
.\run_batch_lab02.cmd
.\run_batch_lab03.cmd
.\run_batch_lab04.cmd
.\run_all_batches.cmd
```

동일한 작업을 CLI로 직접 실행하려면:

```powershell
python -m mclab batch lab01_msd_compare
python -m mclab batch lab02_pid_compare
python -m mclab batch lab03_2dof_compare
python -m mclab batch lab04_wall_compare
python -m mclab batch all
```

batch는 viewer 없이 여러 config를 순서대로 실행하고, `outputs/<timestamp>_<batch_name>/report.html`에 학습자용 비교 리포트를 저장합니다. `run_batch_*.cmd` 런처는 완료 후 이 리포트를 자동으로 엽니다. CLI에서 직접 열고 싶으면 `--open-report`를 추가합니다. 리포트에는 학습 질문, 다음 실험 제안, scenario 카드, metric min/max highlights, baseline 대비 metric 변화량, YAML parameter difference table, 여러 시나리오를 한 그래프에 겹친 comparison plots, 핵심 metric table, plot preview가 포함됩니다. 같은 폴더의 `index.html`은 모든 개별 실행 report와 artifact를 여는 상세 목록입니다. Lab01 batch는 damping/stiffness 차이, Lab02 batch는 gain/saturation/windup/noise/delay 차이, Lab03 batch는 joint-space/task-space/singularity 차이, Lab04 batch는 soft/stiff virtual wall 차이를 한 번에 비교할 때 씁니다. 전체 코스 자료를 한 번에 만들려면 `.\run_all_batches.cmd` 또는 `python -m mclab batch all --open-report`를 실행합니다. 이 명령은 `outputs/<timestamp>_all_batches/report.html` 상위 리포트를 만들고, 그 안에서 네 개 batch 리포트로 이동할 수 있게 합니다.

직접 외란을 주며 물리 현상을 보고 싶으면 interactive launcher를 사용합니다.

```powershell
.\run_lab01_interactive.cmd
.\run_lab02_interactive.cmd
.\run_lab03_interactive.cmd
.\run_lab04_interactive.cmd
.\run_lab04_wall_interactive.cmd
```

Interactive launcher는 사이드 패널 없는 MuJoCo viewer와 함께 작은 `MCLab Interaction` 창을 엽니다. Lab01-03에서는 `Pull Left` / `Push Right` 버튼이 mass에 짧은 힘 펄스를 넣고, 슬라이더로 주요 파라미터를 실행 중에 바꿉니다. 키보드는 viewer 창에 포커스가 있을 때 `A` 또는 왼쪽 화살표, `D` 또는 오른쪽 화살표도 지원합니다. Lab04에서는 버튼으로 제어 중인 관절 목표를 이동하고, wall 데모에서는 virtual wall 파라미터도 슬라이더로 바꿉니다. 슬라이더를 여러 번 바꾼 뒤에는 `Reset sliders`로 실행 시작값으로 되돌릴 수 있습니다. 중요한 순간에는 `Mark observation`을 눌러 현재 슬라이더와 live status 값을 저장할 수 있습니다. 창 아래쪽의 `Live status` 영역은 위치, 오차, 힘, 에너지, wall penetration처럼 지금 관찰해야 할 핵심 숫자만 보여줍니다. 버튼이나 슬라이더를 사용한 경우 실행 리포트의 `Interaction Log`와 `interaction_events.json`에 조작 이력이 저장됩니다.

무엇을 보면 되는지:

| Command | Interaction | What to observe |
|---|---|---|
| `.\run_lab01_interactive.cmd` | mass에 좌/우 힘 펄스, `mass/damping/stiffness` 슬라이더 | 자유 진동, 감쇠, 복원력 |
| `.\run_lab02_interactive.cmd` | PID plant에 좌/우 외란, `target/Kp/Ki/Kd/force limit` 슬라이더 | PID가 목표 위치로 복원하는 과정 |
| `.\run_lab03_interactive.cmd` | 2DOF arm의 `target X/Y`, `task stiffness/damping`, `torque limit` 슬라이더 | 손끝 목표 위치, Jacobian 제어 오차, 토크 제한 |
| `.\run_lab04_interactive.cmd` | Panda 관절 목표 nudge | 목표 관절 위치 변화와 tracking error |
| `.\run_lab04_wall_interactive.cmd` | Panda 관절 목표 nudge, `wall X/stiffness/damping/retreat gain` 슬라이더 | virtual wall 위치와 강성/감쇠 변화 |

전체 검증을 한 번에 돌리려면:

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
python -m mclab run lab03 --config configs/lab03_2dof/joint_space_2dof.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

가상환경을 활성화하지 않고 Windows에서 직접 실행하려면:

```powershell
.\.venv\Scripts\python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

Viewer를 띄우고 움직임을 실제 시간에 가깝게 보려면 `--headless` 대신 `--viewer --realtime`을 사용합니다. 실행이 끝난 뒤 창을 유지하려면 `--pause-at-end`를 함께 붙입니다. Viewer 사이드 패널은 기본으로 숨겨지며, MuJoCo 원본 모델을 디버깅할 때만 `--show-viewer-ui`로 다시 표시할 수 있습니다.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot
```

필요한 그래프만 저장하려면 `--plots`를 붙입니다.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot --plots essential
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot --plots position,error,torque
```

Lab04 `joint_pd.yaml`에서 가장 먼저 확인할 것은 `position.png`의 `q_3`와 `target_q_3`, 그리고 `error.png`의 tracking error입니다. 현재 데모는 Panda의 4번째 관절, 즉 `controlled_joint_index: 3`을 minimum-jerk 목표 위치로 움직이는 조인트 위치 제어 예제입니다.

MuJoCo viewer 양옆 패널은 이 프로젝트의 주 제어 UI가 아닙니다. 현재 랩들은 Python loop가 매 step마다 actuator `ctrl` 값을 YAML 기반 target이나 controller output으로 다시 넣습니다. 따라서 viewer side panel에서 actuator 값을 바꿔도 실행 중에는 곧바로 덮어써지고, `--pause-at-end`로 멈춘 뒤에는 물리 step이 진행되지 않아 움직임이 보이지 않습니다. 그래서 viewer 사이드 패널은 기본으로 숨겨집니다. 실험 값은 `configs/`의 YAML이나 `MCLab Interaction` 창으로 제어하고, 실행 중 핵심 상태도 그 창에서 확인합니다.

CLI 형식:

```bash
python -m mclab run <lab_name> --config <config_path> [--headless] [--viewer] [--show-viewer-ui] [--realtime] [--pause-at-end] [--plot] [--plots <preset_or_names>] [--output-dir <path>]
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
| Lab03 2DOF/Trajectory | `configs/lab03_2dof/*.yaml` | `mode`, `initial_q`, `target_q`, `target_xy`, `trajectory.type`, `tracking_controller.kp`, `tracking_controller.task_kp`, `tracking_controller.task_kd` |
| Lab04 Panda | `configs/lab04_panda/*.yaml` | `controlled_joint_index`, `trajectory.end`, `cartesian_target.position`, `virtual_wall.wall_x`, `virtual_wall.stiffness`, `virtual_wall.damping`, `virtual_wall.force_retreat_gain` |

Plot preset:

| Lab | Presets |
|---|---|
| Lab01 MSD | `essential`, `energy` |
| Lab02 PID | `essential`, `pid` |
| Lab03 2DOF/Trajectory | `essential`, `profile`, `joint`, `task`, `singularity`, `control` |
| Lab04 Panda | `essential`, `control`, `cartesian`, `cartesian_reach`, `wall`, `wall_compare` |

Lab02 PID 예시:

```yaml
controller:
  kp: 80.0
  ki: 0.0
  kd: 18.0
  output_limit: 100.0
  anti_windup: true
```

Lab03 2DOF task-space 예시:

```yaml
plant: two_link_arm
mode: task_space
target_xy: [0.62, 0.42]
trajectory:
  type: minimum_jerk
  start: 0.0
  end: 1.0
  duration: 2.6
  start_time: 0.4
tracking_controller:
  task_kp: 95.0
  task_kd: 18.0
  torque_limit: [50.0, 38.0]
```

Lab04 virtual wall 예시:

```yaml
virtual_wall:
  wall_x: 0.57
  stiffness: 260.0
  damping: 12.0
  force_retreat_gain: 0.00008
```

Lab04 Cartesian reach 예시:

```yaml
mode: cartesian_reach
cartesian_target:
  position: [0.60, 0.10, 0.59]
  gain: 1.0
  max_step: 0.06
```

### 결과 확인

실행 결과는 `outputs/` 아래에 저장됩니다.

```text
outputs/
├── index.html
└── <run_name>/
    ├── config.yaml
    ├── log.csv
    ├── states.npz
    ├── summary.json
    ├── report.html
    ├── notes.md
    └── plots/
```

- `log.csv`: 시간별 position, velocity, control force, torque/current proxy 등
- `states.npz`: NumPy로 읽기 좋은 배열 데이터
- `summary.json`: config 이름, overshoot, settling time, tracking error 같은 요약 지표
- `report.html`: `Try` / `Change` / `Watch` 학습 가이드, 재현 실행 명령, 자동 결과 점검, 요약값, notes, plot 이미지와 plot 해석 가이드를 한 화면에서 보는 실행 리포트
- `outputs/index.html`: 추천 학습 경로 진행표, Lab별 진행 요약, 실행 리포트, `Lesson` / `Next` 안내, 핵심 summary metric을 최신순으로 비교하는 목록 페이지
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
.\run_mclab.cmd
```

This opens the learner menu. From the menu, learners can launch Lab01-04 auto demos, comparison scenarios, interactive demos, and the Panda virtual wall demo with buttons. Type keywords such as `PID`, `noise`, `wall`, or `interactive` in the search box to filter scenarios. Each item includes `Try` / `Change` / `Watch` guidance so learners know what to try, which YAML parameters to edit, and what to observe. `Config` opens the matching YAML parameter file, and `Lesson` opens the lab notes. Each demo opens a MuJoCo viewer without side panels and, when needed, a separate `MCLab Interaction` window. That window shows the current demo's `Try` / `Change` / `Watch` guide, buttons, sliders, and live status. Run and batch buttons open `report.html` automatically after completion. After a run finishes, the menu status line shows the latest output folder and `Open latest report` reopens the run report directly. Use `Open all reports` to open `outputs/index.html` for previous runs.

Main comparison scenarios in the menu:

| Lab | Scenario examples |
|---|---|
| Lab01 | underdamped, overdamped, high/low stiffness, interactive pull |
| Lab02 | low/high P gain, PD damping, saturation, windup vs anti-windup, sensor noise, control delay, interactive disturbance |
| Lab03 | 2DOF joint-space, 2DOF task-space, singularity, interactive XY target tuning, step/trapezoidal/minimum-jerk/S-curve profiles |
| Lab04 | neutral hold, joint trajectories, hand X motion, Cartesian reach, soft/stiff virtual wall, joint target nudge, virtual wall |

First-time learners can follow the `Recommended learning path` at the top of the menu.
Each step reads the saved runs under `outputs/` and shows `Done` or `Not run yet`. The top of the path shows overall progress and the next recommended step, and `Run next` launches the first unfinished step. Use `Refresh path` if the status does not update immediately after a run.

| Step | Menu button | What it builds |
|---|---|---|
| 1 | `Feel 1D physics` | mass-spring-damper position, velocity, force, and energy |
| 2 | `Disturb and tune` | disturbance plus live mass/damping/stiffness tuning |
| 3 | `Close the loop` | PID tracking, error, and control force |
| 4 | `Tune PID live` | target/Kp/Ki/Kd/force limit tuning |
| 5 | `Move 2DOF joints` | 2DOF joint-space tracking |
| 6 | `Control the hand` | Jacobian-based task-space hand control |
| 7 | `Hold Panda` | 7DOF Panda neutral-hold baseline |
| 8 | `Touch virtual wall` | virtual wall stiffness/damping behavior |
| 9 | `Compare the course` | full batch comparison report set |

To launch individual labs directly:

```powershell
.\run_lab01.cmd
.\run_lab02.cmd
.\run_lab03.cmd
.\run_lab04.cmd
```

Each command opens the matching viewer without side panels, saves the lab's essential plots, and opens the run report after completion. If `.venv` is missing, it runs setup first. `run_lab04.cmd` also runs setup when MuJoCo Menagerie is missing.

| Command | Opens | Essential plots |
|---|---|---|
| `.\run_lab01.cmd` | mass-spring-damper viewer | `position`, `velocity`, `force` |
| `.\run_lab02.cmd` | PID viewer | `position`, `control_force`, `error` |
| `.\run_lab03.cmd` | 2DOF arm viewer | `position`, `end_effector`, `torque`, `error` |
| `.\run_lab04.cmd` | Panda viewer | `position`, `error` |

To compare several conditions at once, use the `Comparison batches` buttons in the menu or run a CLI batch:

```powershell
.\run_batch_lab01.cmd
.\run_batch_lab02.cmd
.\run_batch_lab03.cmd
.\run_batch_lab04.cmd
.\run_all_batches.cmd
```

To run the same batches directly through the CLI:

```powershell
python -m mclab batch lab01_msd_compare
python -m mclab batch lab02_pid_compare
python -m mclab batch lab03_2dof_compare
python -m mclab batch lab04_wall_compare
python -m mclab batch all
```

Batches run several configs without opening viewers and save a learner-facing comparison report to `outputs/<timestamp>_<batch_name>/report.html`. The `run_batch_*.cmd` launchers open this report automatically when the batch finishes. Add `--open-report` when running directly through the CLI to get the same behavior. The report includes learning questions, suggested next experiments, scenario cards, metric min/max highlights, metric changes from the baseline scenario, a YAML parameter difference table, comparison plots that overlay multiple scenarios on the same graph, a key metric table, and plot previews. The `index.html` in the same folder is the detailed list of every individual run report and artifact. The Lab01 batch compares damping/stiffness cases, Lab02 compares gain/saturation/windup/noise/delay cases, Lab03 compares joint-space/task-space/singularity cases, and Lab04 compares soft/stiff virtual wall cases. To generate the full course report set at once, run `.\run_all_batches.cmd` or `python -m mclab batch all --open-report`. This creates `outputs/<timestamp>_all_batches/report.html`, which links to all four batch reports.

Use the interactive launchers when learners should disturb the system and watch the physics respond:

```powershell
.\run_lab01_interactive.cmd
.\run_lab02_interactive.cmd
.\run_lab03_interactive.cmd
.\run_lab04_interactive.cmd
.\run_lab04_wall_interactive.cmd
```

Each interactive launcher opens the MuJoCo viewer without side panels plus a small `MCLab Interaction` window. In Lab01-03, `Pull Left` / `Push Right` applies short force pulses to the mass, and sliders tune key parameters while the simulation is running. Keyboard shortcuts also work when the viewer has focus: `A` or left arrow for left, `D` or right arrow for right. In Lab04, the buttons nudge the controlled joint target, and the wall demo adds virtual wall sliders. After changing sliders, use `Reset sliders` to return to the values from the start of the run. Press `Mark observation` at important moments to save the current slider and live status values. The `Live status` area shows only the key values learners should watch now, such as position, error, force, energy, and wall penetration. When learners use buttons or sliders, the run report adds an `Interaction Log` and saves the raw events in `interaction_events.json`.

What to observe:

| Command | Interaction | What to observe |
|---|---|---|
| `.\run_lab01_interactive.cmd` | left/right force pulse, `mass/damping/stiffness` sliders | free oscillation, damping, restoring force |
| `.\run_lab02_interactive.cmd` | left/right disturbance, `target/Kp/Ki/Kd/force limit` sliders | PID disturbance rejection |
| `.\run_lab03_interactive.cmd` | 2DOF arm `target X/Y`, `task stiffness/damping`, `torque limit` sliders | hand target motion, Jacobian control error, torque limits |
| `.\run_lab04_interactive.cmd` | Panda joint target nudge | target position changes and tracking error |
| `.\run_lab04_wall_interactive.cmd` | Panda joint target nudge, `wall X/stiffness/damping/retreat gain` sliders | virtual wall position, stiffness, and damping effects |

To run the full verification suite:

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
python -m mclab run lab03 --config configs/lab03_2dof/joint_space_2dof.yaml --headless --plot
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

Add `--open-report` when you want the run report to open automatically after a direct CLI run.

Without activating the virtual environment on Windows:

```powershell
.\.venv\Scripts\python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot
```

Use `--viewer --realtime` instead of `--headless` to open the MuJoCo viewer and pace motion close to wall-clock time. Add `--pause-at-end` to keep the window open after the simulation finishes. Viewer side panels are hidden by default; use `--show-viewer-ui` only when debugging the raw MuJoCo model.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot
```

To save only the plots you need, add `--plots`.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot --plots essential
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot --plots position,error,torque
```

For Lab04 `joint_pd.yaml`, check `q_3` versus `target_q_3` in `position.png` first, then the tracking error in `error.png`. This demo controls Panda joint 4, represented by `controlled_joint_index: 3`, with a minimum-jerk target position.

The MuJoCo viewer side panels are not the main control UI for this project. The Python loops write actuator `ctrl` values from YAML-based targets or controller outputs at every simulation step. If you change actuator values in the viewer side panel, they are overwritten during the run; after `--pause-at-end`, physics stepping has stopped, so slider edits do not move the robot. Viewer side panels are therefore hidden by default. Change experiment parameters in YAML under `configs/` or use the `MCLab Interaction` window, which also shows the live status values learners need during the demo.

CLI shape:

```bash
python -m mclab run <lab_name> --config <config_path> [--headless] [--viewer] [--show-viewer-ui] [--realtime] [--pause-at-end] [--plot] [--plots <preset_or_names>] [--output-dir <path>]
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
| Lab03 2DOF/Trajectory | `configs/lab03_2dof/*.yaml` | `mode`, `initial_q`, `target_q`, `target_xy`, `trajectory.type`, `tracking_controller.kp`, `tracking_controller.task_kp`, `tracking_controller.task_kd` |
| Lab04 Panda | `configs/lab04_panda/*.yaml` | `controlled_joint_index`, `trajectory.end`, `cartesian_target.position`, `virtual_wall.wall_x`, `virtual_wall.stiffness`, `virtual_wall.damping`, `virtual_wall.force_retreat_gain` |

Plot presets:

| Lab | Presets |
|---|---|
| Lab01 MSD | `essential`, `energy` |
| Lab02 PID | `essential`, `pid` |
| Lab03 2DOF/Trajectory | `essential`, `profile`, `joint`, `task`, `singularity`, `control` |
| Lab04 Panda | `essential`, `control`, `cartesian`, `cartesian_reach`, `wall`, `wall_compare` |

Lab02 PID example:

```yaml
controller:
  kp: 80.0
  ki: 0.0
  kd: 18.0
  output_limit: 100.0
  anti_windup: true
```

Lab03 2DOF task-space example:

```yaml
plant: two_link_arm
mode: task_space
target_xy: [0.62, 0.42]
trajectory:
  type: minimum_jerk
  start: 0.0
  end: 1.0
  duration: 2.6
  start_time: 0.4
tracking_controller:
  task_kp: 95.0
  task_kd: 18.0
  torque_limit: [50.0, 38.0]
```

Lab04 virtual wall example:

```yaml
virtual_wall:
  wall_x: 0.57
  stiffness: 260.0
  damping: 12.0
  force_retreat_gain: 0.00008
```

Lab04 Cartesian reach example:

```yaml
mode: cartesian_reach
cartesian_target:
  position: [0.60, 0.10, 0.59]
  gain: 1.0
  max_step: 0.06
```

### Reading Outputs

Each run writes artifacts under `outputs/`.

```text
outputs/
├── index.html
└── <run_name>/
    ├── config.yaml
    ├── log.csv
    ├── states.npz
    ├── summary.json
    ├── report.html
    ├── notes.md
    └── plots/
```

- `log.csv`: time-series signals such as position, velocity, control force, torque/current proxy
- `states.npz`: NumPy-friendly arrays
- `summary.json`: config name and metrics such as overshoot, settling time, tracking error
- `report.html`: a one-page run report with `Try` / `Change` / `Watch` learning guidance, reproduce commands, automatic result checks, summary values, notes, plot images, and plot interpretation guides
- `outputs/index.html`: a newest-first index with the recommended learning path, lab progress cards, run reports, `Lesson` / `Next` guidance, and key summary metrics
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

현재 구현됨:

- torque-actuated planar 2DOF MuJoCo arm
- FK, IK helper, analytic Jacobian
- joint-space trajectory tracking
- task-space Jacobian-transpose PD tracking
- interactive task target/stiffness/damping/torque tuning
- singularity demo with Jacobian determinant, manipulability, and condition number plots
- joint position, end-effector, torque, current proxy, error plots
- step, trapezoidal, quintic/minimum-jerk, S-curve trajectory generators
- legacy 1D trajectory profile configs for comparing target position/velocity/acceleration/jerk

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
