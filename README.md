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

현재 `lab03`은 실제 2DOF planar arm을 포함합니다. `joint_space_2dof.yaml`은 어깨/팔꿈치 joint-space PD trajectory tracking을 보여주고, `task_space_2dof.yaml`은 FK/Jacobian 기반 end-effector task-space 제어를 보여줍니다. 기존 1D step, trapezoidal, minimum-jerk, S-curve trajectory 비교 config와 `1D trajectory tracking` interactive 데모도 profile/추종 학습용으로 유지됩니다.

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
    ├── worksheet.md
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

이 명령은 학습자용 메뉴를 엽니다. 메뉴에서 Lab01-04의 자동 데모, 비교 시나리오, interactive 데모, Panda virtual wall 데모를 버튼으로 실행할 수 있습니다. `Explore` 필터에서 `Intro`, `Build`, `Deep dive`, `Hands-on`, `Compare`, `PID`, `2DOF`, `Panda`, `Wall`, `Singularity`를 고르면 학습자가 바로 체험하고 싶은 범주만 볼 수 있습니다. 검색창에 `PID`, `noise`, `wall`, `hands on`, `Damped PD`, `Far target`, `intro`, `deep dive` 같은 키워드를 넣으면 관련 시나리오만 바로 볼 수 있습니다. 각 항목에는 `Setup` / `Badges` / `Plan` / `Course step` / `Done when` / `Mission` / `Playbook` / `Start steps` / `Challenge` / `Mission evidence` / `Challenge evidence` / `History` / `Evidence` / `Latest evidence` / `Preset evidence` / `Activity mix` / `Next cue` / `Plots` / `Plot review` / `Worksheet` / `Controls` / `Counts as control` / `Try` / `Change` / `Values` / `Prediction` / `Question` / `Next` / `Compare` / `Watch` 안내가 붙어 있고, interactive 항목에는 `Presets` 줄도 표시되어 학습자가 무엇을 해보고, 추천 경로의 몇 번째 단계인지 또는 optional exploration인지, 난이도와 체험 유형, 실행 길이, 완료 기준, 예측-조작-증거 확인을 어떤 순서로 할지, 첫 실행에서 바로 따라 할 짧은 시작 순서가 무엇인지, 어떤 visible-effect challenge를 풀어야 하는지, 어떤 조작을 어떤 evidence로 증명해야 하는지, 저장 산출물이 무엇인지, 최신 실행에 관찰 marker, prediction, outcome, 메모가 남아 있는지, outcome review가 남았는지, 첫 marker에서 최신 marker까지의 `Observation flow`, prediction/note/outcome을 어떻게 보완할지 알려주는 `Observation next step`, 마지막 prediction/outcome/note, `Note evidence` 항목, live status와 missing outcome review가 무엇인지, mission proof status와 challenge proof status가 준비됐는지, quick preset 비교가 충분했는지, 버튼/슬라이더/preset/marker를 얼마나 다양하게 사용했는지, 지금은 실행/프리셋 비교/관찰 기록/outcome review/replay/compare 중 무엇을 해야 하는지, 어떤 핵심 그래프와 worksheet가 저장되어 있는지, 그 그래프에서 무엇을 먼저 봐야 하는지, 실제로 어떤 버튼/슬라이더/preset을 조작할 수 있는지, 어떤 조작이 hands-on 완료 증거로 인정되는지, 어떤 YAML 파라미터나 preset을 바꾸고, 현재 핵심 값이 무엇인지, 무엇을 예측해야 하는지, 어떤 질문을 스스로 확인해야 하는지, 다음에 어떤 비교 실험을 해볼지, 어떤 batch 리포트로 묶어볼지, 무엇을 관찰해야 하는지 바로 알 수 있습니다. `prediction live target`, `question overshoot`, `pull push`, `pause step`, `counts as control`, `course step`, `done when`, `start steps`, `playbook mark observation`, `challenge evidence`, `challenge visible effect`처럼 예측/질문/조작/진행 순서/과제 키워드로도 검색할 수 있습니다. `Setup`이 `Missing model`이나 `Config error`이면 해당 실행 버튼은 비활성화되며, `Config`, `Lesson`, `Check setup`으로 원인을 확인합니다. 비교 batch도 포함된 모든 config와 model asset을 검사하므로 준비되지 않은 `Next` 또는 `Compare` 버튼은 비활성화됩니다. `Config`는 해당 YAML 파라미터 파일을 열고, `Lesson`은 랩 설명 문서를 열며, `Report`는 해당 시나리오의 최신 실행 리포트를 열고, `Plot`은 저장된 최신 핵심 그래프를 바로 열며, `Worksheet`는 최신 `worksheet.md` 복습지를 엽니다. `Comparison batches` 항목도 `Plan`, `Mission`, `Playbook`, `Start steps`, `Challenge`, `Mission evidence`, `Challenge evidence`, `History`, `Report`, `Handoff`, `Plot`, `Worksheet` 버튼을 제공하므로 batch 규모, 비교 과제, 최신 증거 상태, 최신 비교 리포트, 추천 viewer handoff, 핵심 comparison plot, worksheet를 바로 다시 확인할 수 있습니다. `Next` 버튼은 카드에 표시된 후속 시나리오나 전체 비교 batch를 바로 실행하고, `Compare` 버튼은 해당 랩의 비교 batch 리포트를 생성합니다. 아직 실행 기록이 없는 시나리오는 `History: Not run yet`으로 표시되고 `Report` / `Plot` / `Worksheet` 버튼이 비활성화됩니다. 각 데모는 사이드 패널 없는 MuJoCo viewer를 열고, 필요한 경우 `MCLab Interaction` 창을 함께 띄웁니다. 이 창에는 현재 데모의 `Mission` / `Playbook` / `Start steps` / `Challenge` / `Try` / `Change` / `Done when` / `Prediction` / `Question` / `Watch` 안내, 버튼, `-` / `+` step 버튼이 붙은 슬라이더, live status가 표시됩니다. run과 batch 버튼은 완료 후 `report.html`을 자동으로 엽니다. 실행이 끝나면 메뉴 상태줄에 최신 결과 폴더와 plot/worksheet/viewer handoff 저장 여부가 표시되고, `Open latest report`, `Open latest plot`, `Open latest worksheet`, batch 최신 결과에서만 켜지는 `Open handoff`, `Open latest folder`로 실행 리포트, 핵심 그래프, 복습지, 추천 viewer handoff, 원본 로그/config 폴더를 다시 열 수 있습니다. 여러 실행 결과를 다시 보려면 `Open all reports`로 `outputs/index.html`을 엽니다. CLI만 쓸 때는 `python -m mclab index --open`으로 같은 누적 결과 페이지를 재생성하고 바로 열 수 있습니다.

각 scenario, comparison batch, learning path 카드의 `Folder` 버튼은 해당 항목의 최신 output 디렉토리를 직접 엽니다. `Report`는 HTML 리포트, comparison batch의 `Handoff`는 최신 report의 `Viewer Handoff` 섹션, `Plot`은 우선순위 그래프, `Worksheet`는 복습지, `Replay`는 튜닝된 YAML 재실행용이며, `Folder`는 `log.csv`, `states.npz`, `config.yaml`, `summary.json`, `interaction_events.json`, `learner_snapshot.json`, `learner_tuned_config.yaml` 같은 원본 산출물을 확인할 때 사용합니다.

`Experience coverage`는 메뉴와 `outputs/index.html`에서 저장된 실행 기록을 읽어 Intro basics, Hands-on controls, Comparison batch, 2DOF/Jacobian, Singularity/DLS, Panda manipulator, Virtual wall 체험군 중 무엇을 이미 해봤는지 보여줍니다. interactive run은 실제 버튼, 슬라이더, preset 중 하나를 사용해야 hands-on 체험으로 인정되며, 메뉴는 7개 체험군의 `Coverage map`과 아직 비어 있는 다음 체험군을 바로 실행하는 `Run next` 버튼을 보여줍니다. CLI만 사용할 때는 `python -m mclab coverage`로 같은 coverage map, 다음 실행 명령, 다음 체험의 Plan/Mission/Try/Change/Values/Prediction/Question/Watch/Start steps/Challenge/Controls guide를 터미널에서 확인할 수 있습니다. `outputs/index.html`도 7개 체험군별 Done/Next/Missing 카드를 표시하고 각 체험을 실행할 CLI 명령을 함께 보여줍니다.

`MCLab Interaction` 창의 `Viewer legend`는 현재 데모에서 보이는 초록 목표, 작은 초록 waypoint 경로, 파란 현재 위치, 주황 힘/경고/접촉, 붉은 wall 가이드의 의미를 설명합니다.
메뉴 카드에도 같은 내용이 `Viewer:` 줄로 표시되며, `red plane`, `orange sphere`, `green marker` 같은 검색어로 해당 시나리오를 찾을 수 있습니다.
메뉴의 `Viewer:` 줄, 실행 중 `Viewer controls`, 실행 리포트의 `Control Surface`는 모두 MuJoCo 기본 사이드 패널이 숨겨져 있고 YAML 또는 `MCLab Interaction` 조작부를 써야 한다는 점을 다시 표시합니다.

수업 시작 전 환경을 빠르게 확인하려면 메뉴 하단의 `Check setup`을 누르거나 다음 명령을 실행합니다. Python 패키지, config 로딩, MuJoCo model asset, learner menu 시나리오/비교 batch 준비 상태, `outputs/` 쓰기 권한을 점검합니다. 모든 항목이 준비되면 CLI는 메뉴 열기, coverage 확인, 추천 경로 preview, 다음 경로 단계 실행 명령을 출력하고, 메뉴 상태줄은 `Run next` 또는 `python -m mclab next --preview`로 이어지라고 안내합니다.

```powershell
python -m mclab doctor
```

메뉴에 포함된 주요 비교 시나리오:

| Lab | Scenario examples |
|---|---|
| Lab01 | underdamped, overdamped, high/low stiffness, interactive pull |
| Lab02 | low/high P gain, PD damping, saturation, windup vs anti-windup, sensor noise, control delay, interactive disturbance |
| Lab03 | 2DOF joint-space, 2DOF task-space, singularity, DLS singularity with live damping presets, early/default/late, inner/edge-target, upper/lower-path, shoulder/elbow/staggered-disturbance recovery-time, low/high-torque, slow/fast-command, low/high-joint-speed, direct/inward-retarget, and fixed/adaptive-speed-retarget condition-aware DLS, interactive XY target tuning, 1D trajectory tracking, step/trapezoidal/minimum-jerk/S-curve profiles |
| Lab04 | neutral hold, 30s stability hold, joint trajectories, hand X motion, Cartesian reach, soft/stiff Cartesian reach, soft/stiff, low/high damping, near/far, slow/fast approach, shallow/deep target push, contact-cycle, and low/high retreat virtual wall, joint target nudge, virtual wall |

처음 학습자는 메뉴 상단의 `Recommended learning path`를 순서대로 따라가면 됩니다.
각 단계는 `outputs/`의 실행 기록을 읽어 `Done`, `Needs observation`, `Needs prediction`, `Needs note`, `Needs learner control`, `Not run yet` 상태를 보여줍니다. 카드의 `Done when` 줄은 자동 실행, hands-on 실행, batch 실행마다 완료 기준을 먼저 알려주고, `Start steps` 줄은 바로 누를 버튼/preset 순서를 보여주며, `Next cue`는 이전 실행에서 아직 부족한 learner-control evidence가 있으면 실제 버튼 라벨이나 slider/preset 이름으로 다음 행동을 알려줍니다. `Counts as control` 줄은 어떤 조작이 hands-on 완료 증거로 인정되는지 알려줍니다. Hands-on 단계는 실행만으로 완료되지 않고 버튼/슬라이더/preset 중 최소 하나를 실제로 조작한 뒤 prediction과 note가 포함된 `Mark observation`을 최소 한 번 남겨야 `Done`으로 계산되며, 완료된 hands-on 상태에는 가능한 경우 observation, prediction, outcome, note, control 개수도 함께 표시됩니다. Prediction은 있지만 outcome 판단이 아직 없으면 경로 완료는 유지하되 `Outcome review pending` 안내가 표시됩니다. 같은 기준과 `Start steps`, `Counts as control`은 `outputs/index.html`의 Learning Path 카드에도 적용되고, 메뉴와 index는 1D Dynamics, PID Control, 2DOF Control, Panda Manipulation, Course Compare `Milestones` 진행도도 함께 보여줍니다. CLI만 사용할 때는 `python -m mclab scenarios wall --filter wall --details`로 guided scenario를 검색하고 course step/Done when, Playbook, Try/Change/Values/Prediction/Question/Watch, Viewer/Counts-as-control, 최신 report/folder, history/evidence/activity/next cue, next/compare command, plot/worksheet/replay 상태와 replay command까지 확인할 수 있으며, 넓은 `wall` 검색은 hands-on `Virtual wall` 카드를 먼저 보여줍니다. `python -m mclab params wall --filter hands-on`은 해당 시나리오에서 바꿀 YAML/live-control 파라미터, 현재 config 값, controls, prediction prompt, start steps, 실행 명령을 바로 보여줍니다. `python -m mclab batches wall`로 comparison batch를 검색해 실행 명령을 확인할 수 있으며, `python -m mclab path`로 같은 추천 경로 요약, milestone 상태, 다음 단계, 다음 실행 명령, 다음 단계 guide를 확인하고, `python -m mclab path --all`로 12단계 상태 맵을 터미널에 출력할 수 있습니다. `python -m mclab next --preview`는 다음 단계를 실행하지 않고 Plan/Course/Mission/Try/Change/Values/Prediction/Question/Watch/Start steps/Challenge/Controls guide를 확인하며, hands-on 단계에서만 Viewer guide를 함께 보여주고 batch 단계에서는 worksheet/plot/plot-review cue도 함께 보여줍니다. `python -m mclab next`는 같은 guide를 보여준 뒤 자동 단계는 headless로, hands-on 단계는 side-panel-free viewer로 바로 실행합니다. 실행 후에는 `python -m mclab review`로 saved run review queue, 다음 report/worksheet, matched action, observation next step, plot review cue를 확인하고, `python -m mclab review --open`으로 다음 pending report를 바로 열 수 있습니다. outputs run table의 `Evidence` 칸은 최신 observation marker의 prediction, outcome, note, note evidence, live status와 첫 marker에서 최신 marker까지의 observation flow 및 다음 observation 보완 단계 요약을 보여주며, prediction/note와 learner-control evidence가 같이 부족하면 둘을 한 번에 보완하도록 실제 control 이름을 함께 안내합니다. `Activity` 칸은 button/slider/preset/marker 조작 다양성과 다음 activity 제안을, `Mission evidence` 칸은 mission proof status와 next proof step을, `Challenge evidence` 칸은 visible-effect challenge의 proof status/source/next step을 함께 보여줍니다. 완료된 단계는 옆의 `Report`, `Plot`, `Worksheet` 버튼으로 최신 리포트, 핵심 그래프, 복습용 `worksheet.md`를 바로 다시 열 수 있고, 최신 실행에 `learner_tuned_config.yaml`이 있으면 `Replay` 버튼으로 마지막 튜닝값을 즉시 다시 볼 수 있습니다. `outputs/index.html`의 run table과 Learning Path 카드도 `Folder` 링크를 제공하므로 원본 로그/config/snapshot 폴더를 브라우저에서 바로 열 수 있습니다. 메뉴 상단에는 관찰, 예측, 조작, 메모 증거가 빠진 hands-on 단계 수, outcome review가 남은 hands-on 단계 수, 다음 권장 단계, 실행 전 prediction/compare cue와 watch cue가 표시됩니다. 그 아래 `Review queue` 줄은 saved run 전체의 ready/pending 수, observation/prediction/outcome/note/control/artifact 부족 수, 다음에 열어볼 review 대상을 보여주며, `Open next review`는 그 run의 report를 바로 열고 `Open review queue`는 최신 `outputs/index.html`을 다시 생성해 엽니다. `Run next`를 누르면 아직 완료하지 않은 첫 단계를 바로 실행합니다. 실행 후 learning path, review queue, batch history, `Report` / `Plot` / `Worksheet` / `Replay` 버튼 상태가 바로 바뀌지 않으면 `Refresh menu`를 누릅니다.

CLI discovery 명령은 결과가 있을 때도 다음 검색 예시를 함께 보여줍니다. `scenarios`는 hands-on wall, singularity, prediction/live-target 예시를 안내하고, `params`는 wall/PID/DLS 파라미터 검색 예시를 안내하며, `batches`는 wall, 2DOF, all batch 예시를 안내합니다. Scenario 카드와 learning path의 `Command`는 필요한 것만 실행하는 기본 경로입니다. Hands-on 단계는 side-panel-free viewer를 열고, 자동/비교 단계는 headless로 plot/report/worksheet를 만든 뒤 필요할 때만 `Viewer rerun` 명령으로 live 확인을 합니다.

| Step | Menu button | What it builds |
|---|---|---|
| 1 | `Feel 1D physics` | mass-spring-damper의 위치, 속도, 힘, 에너지 |
| 2 | `Disturb and tune` | 외란과 mass/damping/stiffness live tuning |
| 3 | `Close the loop` | PID tracking, error, control force |
| 4 | `Tune PID live` | target/Kp/Ki/Kd/force limit 조정 |
| 5 | `Move 2DOF joints` | 2DOF joint-space tracking |
| 6 | `Control the hand` | Jacobian 기반 task-space hand control |
| 7 | `Handle singularity` | condition-aware DLS와 Jacobian conditioning |
| 8 | `Compare DLS retarget` | adaptive task-speed schedule과 retarget path 비교 |
| 9 | `Hold Panda` | 7DOF Panda neutral hold baseline |
| 10 | `Reach in Cartesian` | Panda 손끝 XYZ 목표 추종 |
| 11 | `Touch virtual wall` | virtual wall stiffness/damping 체험 |
| 12 | `Compare the course` | 모든 batch 비교 리포트 생성 |

개별 랩을 바로 실행하고 싶으면:

```powershell
.\run_lab01.cmd
.\run_lab02.cmd
.\run_lab03.cmd
.\run_lab03_dls_interactive.cmd
.\run_lab03_condition_dls_interactive.cmd
.\run_lab04.cmd
```

각 명령은 해당 viewer를 사이드 패널 없이 열고, 랩별 핵심 그래프를 저장한 뒤 실행 리포트를 자동으로 엽니다. `.venv`가 없으면 먼저 자동 setup을 실행합니다. `run_lab04.cmd`는 MuJoCo Menagerie가 없을 때도 setup을 실행합니다.

| Command | Opens | Essential plots |
|---|---|---|
| `.\run_lab01.cmd` | mass-spring-damper viewer | `position`, `velocity`, `force` |
| `.\run_lab02.cmd` | PID viewer | `position`, `control_force`, `error` |
| `.\run_lab03.cmd` | 2DOF arm viewer | `position`, `end_effector`, `torque`, `error` |
| `.\run_lab03_dls_interactive.cmd` | 2DOF DLS singularity viewer | `dls_joint_speed`, `dls_damping`, `condition_number`, `tau_disturbance` |
| `.\run_lab03_condition_dls_interactive.cmd` | 2DOF condition-aware DLS viewer | `dls_condition_scale`, `dls_damping`, `dls_joint_speed`, `tau_disturbance` |
| `.\run_lab04.cmd` | Panda viewer | `position`, `error` |

여러 조건을 한 번에 비교하려면 메뉴의 `Comparison batches` 버튼을 누르거나 CLI batch를 실행합니다.
Batch 카드와 `python -m mclab batches ... --details` 출력도 `Course step`과 `Done when`을 보여줍니다. `All compare`는 추천 경로의 12/12 단계로 표시되고, 개별 Lab 비교 batch는 optional comparison으로 표시됩니다.

```powershell
.\run_batch_lab01.cmd
.\run_batch_lab02.cmd
.\run_batch_lab03.cmd
.\run_batch_lab04_cartesian.cmd
.\run_batch_lab04.cmd
.\run_all_batches.cmd
```

동일한 작업을 CLI로 직접 실행하려면:

```powershell
python -m mclab batch lab01_msd_compare
python -m mclab batch lab02_pid_compare
python -m mclab batch lab03_2dof_compare
python -m mclab batch lab04_cartesian_compare
python -m mclab batch lab04_wall_compare
python -m mclab batch all
```

batch는 viewer 없이 여러 config를 순서대로 실행하고, `outputs/<timestamp>_<batch_name>/report.html`에 학습자용 비교 리포트를 저장합니다. `run_batch_*.cmd` 런처는 완료 후 이 리포트를 자동으로 엽니다. CLI에서 직접 열고 싶으면 `--open-report`를 추가합니다. 리포트에는 학습 질문, 다음 실험 제안, 전체 batch와 개별 scenario headless 재현 명령 및 viewer 재실행 명령, report/핵심 plot/개별 worksheet/folder 바로가기, priority plot guidance, baseline 대비 설정/metric 변화 및 interactive rerun 때 쓸 수 있는 `Control surface` cue가 붙은 scenario 카드, start steps/challenge/prediction/question/watch 안내, automatic comparison takeaways, `Prediction Check` outcome table, metric min/max highlights, baseline 대비 metric 변화량, YAML parameter difference table, 여러 시나리오를 한 그래프에 겹친 comparison plots, 핵심 metric table, plot preview가 포함됩니다. Lab04 wall batch는 `wall_key_moment_timing_compare.png`로 contact와 peak force/damping/hand-speed 시점도 비교합니다. 같은 폴더의 `worksheet.md`는 시나리오별 핵심 metric, start steps/challenge, prediction outcome check, priority plot guidance, 개별 scenario worksheet와 folder 링크, headless/viewer 재실행 명령, 비교 체크리스트, 다음 실험 아이디어를 Markdown으로 정리합니다. 같은 폴더의 `index.html`은 모든 개별 실행 report, 핵심 plot 바로가기, artifact를 여는 상세 목록입니다. Lab01 batch는 damping/stiffness 차이, Lab02 batch는 gain/saturation/windup/noise/delay 차이, Lab03 batch는 joint-space/task-space/singularity/DLS singularity, early/default/late condition-aware damping schedule, inner/edge target position, upper/lower path branch, shoulder/elbow/staggered disturbance recovery와 `disturbance_recovery_duration`, low/high torque limit, slow/fast command speed, low/high joint-speed limit, direct/inward retargeting path 차이, fixed/adaptive task-speed retarget schedule 차이, Lab04 batch는 soft/stiff Cartesian reach, soft/stiff virtual wall, fixed-stiffness low/high wall damping, near/far wall position, slow/fast wall approach speed, shallow/deep target push depth, contact-cycle target crossing, low/high force-to-retreat gain 차이를 한 번에 비교할 때 씁니다. 전체 코스 자료를 한 번에 만들려면 `.\run_all_batches.cmd` 또는 `python -m mclab batch all --open-report`를 실행합니다. 이 명령은 `outputs/<timestamp>_all_batches/report.html` 상위 리포트와 course-level `worksheet.md`를 만들고, 둘 다 batch별 focus/question과 다섯 개 batch 리포트/worksheet/folder 링크를 제공합니다.

Batch 카드의 `Prediction check` 줄은 실행 전에는 예측을 먼저 쓰라고 안내하고, 실행 후에는 `worksheet.md`의 `Prediction Check` 표에서 `Matched`, `Partly matched`, `Surprised` outcome을 표시하라고 알려줍니다. CLI에서 `python -m mclab batches <query> --details`로 batch를 찾으면 최신 history, worksheet, plot, plot review, prediction check, 그리고 최신 worksheet에서 뽑은 handoff viewer 재실행 명령까지 함께 표시됩니다. `all` course batch는 연결된 개별 batch worksheet까지 따라가 첫 viewer rerun 명령을 보여줍니다. CLI에서 batch를 실행해도 완료 출력에 `Prediction check`와 추천 `Viewer handoff` 재실행 명령이 함께 표시되어, 리포트를 연 뒤 바로 side-panel-free viewer에서 가장 차이가 큰 시나리오를 다시 관찰할 수 있습니다.

직접 외란을 주며 물리 현상을 보고 싶으면 interactive launcher를 사용합니다.

```powershell
.\run_lab01_interactive.cmd
.\run_lab02_interactive.cmd
.\run_lab03_interactive.cmd
.\run_lab03_dls_interactive.cmd
.\run_lab03_condition_dls_interactive.cmd
.\run_lab04_interactive.cmd
.\run_lab04_cartesian_interactive.cmd
.\run_lab04_wall_interactive.cmd
```

Interactive launcher는 사이드 패널 없는 MuJoCo viewer와 함께 작은 `MCLab Interaction` 창을 엽니다. Lab01-02 viewer에는 회색 평형점, 초록 목표점, 주황 힘 방향 막대가 표시됩니다. Lab01-02에서는 `Pull Left` / `Push Right` 버튼이 mass에 짧은 힘 펄스를 넣고, Lab03 2DOF interactive viewer에서는 `Shoulder pulse` / `Elbow pulse` 버튼이 각 관절에 짧은 외란 토크를 넣습니다. 슬라이더로 주요 파라미터를 실행 중에 바꾸며, 키보드는 viewer 창에 포커스가 있을 때 `A` 또는 왼쪽 화살표, `D` 또는 오른쪽 화살표도 지원합니다. Lab03 2DOF viewer에는 초록 목표 손끝, 파란 현재 손끝, 주황 singularity 경고 손끝이 표시됩니다. Lab04 joint 데모에서는 버튼으로 제어 중인 관절 목표를 이동하고, Cartesian/wall 데모에서는 `Target X -` / `Target X +` 버튼으로 손끝 목표를 좌우로 밀며, wall 데모의 `Target X + into wall`은 목표를 붉은 wall 안쪽으로 밀어 넣습니다. Lab04 Cartesian/wall viewer에는 초록 목표점, 파란 현재 손끝, 주황 접촉 손끝, 주황 wall-force 방향 막대, 붉은 반투명 wall 가이드가 자동으로 표시됩니다. `MCLab Interaction` 창은 스크롤과 크기 조절을 지원하므로 Lab04 wall처럼 컨트롤이 많은 데모에서도 아래쪽의 observation과 live status 영역까지 접근할 수 있습니다. `Quick presets` 버튼은 `Soft reach`, `Stiff wall`, `Damped PD`처럼 대표 파라미터 조합을 한 번에 적용하며, 마우스를 올리거나 preset을 누른 뒤에도 preset progress, 다음 required preset, 남은 required path가 패널에 계속 표시됩니다. Lab04 wall의 required preset 순서는 `Close wall -> Back away -> Re-enter wall`이고 이 순서대로 눌러야 완료 증거로 인정되므로, 학습자가 접촉, 해제, 재접촉을 한 번의 viewer 실행에서 직접 만들 수 있습니다. 슬라이더 옆의 `-` / `+` 버튼은 resolution 단위로 값을 한 단계씩 정밀하게 바꾸고, `Changed values` 줄은 실행 시작값 대비 지금 바뀐 파라미터를 즉시 요약합니다. `Playback speed`는 realtime viewer 속도를 0.25x-2.0x로 조절해 빠른 응답을 천천히 보거나 긴 안정화 구간을 빠르게 훑게 합니다. `Pause / Resume`은 물리 step과 logging을 멈춰 viewer를 살펴보고, 슬라이더를 조정하고, 예측을 적은 뒤 같은 시간 지점에서 이어 보게 합니다. 멈춘 상태에서 `Step once`를 누르면 한 physics step만 진행하고 다시 멈추므로 빠른 접촉이나 진동 변화를 한 프레임씩 볼 수 있습니다. 슬라이더를 여러 번 바꾼 뒤에는 `Reset sliders`로 실행 시작값으로 되돌릴 수 있고, `Reset plant`로 현재 슬라이더 값은 유지한 채 mass나 robot을 초기 상태로 되돌려 같은 조건을 다시 관찰할 수 있습니다. 중요한 순간에는 버튼/슬라이더/preset 중 하나를 실제로 조작한 뒤 짧은 예측을 적고 결과가 `Matched`, `Partly matched`, `Surprised` 중 어디에 가까운지 고른 뒤, `Use live status`로 현재 핵심 숫자를 메모에 넣거나 관찰 메모를 직접 쓰고 `Mark observation`을 눌러 현재 학습 질문, 예측, prediction outcome, evidence prompt, challenge proof 상태, 메모, 초기값 대비 바뀐 슬라이더, 현재 슬라이더, live status 값을 저장할 수 있으며, 실행 리포트의 `Observation Markers` 카드에서 다시 볼 수 있습니다. `Use live status`와 `Use changed values`는 메모를 채우는 증거 보조 버튼이고, `Pause / Resume`, `Step once`, `Playback speed`는 보기/속도 보조 조작이므로, 이것만 눌러서는 learner control 완료 조건을 만족하지 않습니다. Observation 영역의 `Evidence checklist`는 표시 전부터 learner control, prediction, preset 비교, outcome, note가 준비됐는지 즉시 보여줍니다. `Prediction` 필드가 비어 있거나 learner control을 아직 쓰지 않았으면 패널 상태줄이 learning path 완료 증거로는 부족하다고 알려주며, `Mark observation` 뒤에도 부족한 버튼/슬라이더/preset 조작을 실제 이름으로 다시 안내합니다. 창 아래쪽의 `Live status` 영역은 Run time, Remaining, 위치, 오차, 힘, 외란 토크, Target X nudge, Target-Wall gap, Wall phase, wall penetration처럼 지금 관찰해야 할 핵심 숫자만 보여주고, 종료 1초 전에는 필요하면 `Pause / Resume`으로 붙잡으라는 Run clock 안내를 표시합니다. Wall phase의 `Target past wall`은 초록 목표가 벽을 넘었다는 뜻이고, `Contact: wall pushing back`은 실제 손끝이 벽에 들어가 가상 벽 힘이 작동 중이라는 뜻입니다. 실행 리포트의 `Key Moments`는 Target crosses wall, First wall contact, Wall contact release, Target backs away를 따로 남겨 목표 crossing과 실제 접촉/해제를 구분해 복습하게 합니다. 버튼, preset, 슬라이더를 사용한 경우 실행 리포트의 `Learner Action Summary`, `Learner Snapshot`, `Replay Tuned Config`, `Interaction Log`가 채워집니다. `learner_snapshot.json`에는 최종 슬라이더/상태 값, `learner_tuned_config.yaml`에는 최종 슬라이더 값을 반영한 재실행용 YAML, `interaction_events.json`에는 시간순 조작 이력이 저장됩니다. 메뉴의 `Replay` 버튼은 최신 `learner_tuned_config.yaml`이 있는 시나리오에서만 켜지며, 학습자가 마지막으로 맞춘 값을 live control 없이 바로 다시 관찰하게 해줍니다.

패널 상단, 실행 리포트, `worksheet.md`, `outputs/index.html`의 `Done when`과 `Counts as control` 줄은 완료 증거로 인정되는 실제 버튼 라벨, live slider, Quick preset을 보조 버튼과 분리해 보여줍니다. required preset이 있는 demo에서는 `Done when`이 `Close wall -> Back away -> Re-enter wall`처럼 눌러야 하는 순서를 직접 표시합니다. `Pull/Push`, `Joint Target`, `Target X`, `Shoulder/Elbow pulse`처럼 config에 맞는 버튼 이름이 저장 산출물에도 남고, `Pause`, `Playback speed`, `Use live status` 같은 보기/증거 보조 기능은 학습 메모를 돕지만 learner-control 완료 조건으로 세지 않습니다.

Lab04 wall live status는 total wall force뿐 아니라 spring force, damping force, wall retreat도 따로 보여주므로 stiffness와 damping이 각각 무엇을 바꾸는지 실행 중에 구분할 수 있습니다.

Observation 영역의 `Next action` 줄은 현재 상태에서 바로 해야 할 일을 한 문장으로 보여줍니다. 예측이 비어 있으면 prediction 입력을 먼저 안내하고, button evidence가 필요하면 `Pull Left` / `Push Right`, `Target X -` / `Target X +`처럼 실제 패널 버튼 라벨을 알려주며, required preset이 남아 있으면 다음 preset을 이름으로 알려줍니다. note가 없으면 `Use live status`나 짧은 observation note를 권장한 뒤 `Mark observation`으로 넘어가게 합니다.

`Evidence quality` 줄은 observation이 incomplete인지, outcome 없이도 mark 가능한 상태인지, review-ready 상태인지 저장 전에 바로 알려주고, control evidence가 빠졌을 때는 필요한 버튼/슬라이더/preset 조작을 함께 보여줍니다.

`Challenge proof` 줄은 visible-effect challenge를 증명하려면 prediction, learner control, preset evidence, note/live-status evidence, outcome review 중 무엇이 아직 필요한지 바로 알려주며, learner control이 빠졌으면 실제 패널 버튼이나 control family를 이름으로 안내합니다.

Observation 영역의 live `Activity mix` 줄은 현재 실행에서 버튼, 슬라이더, preset, observation marker를 몇 번 썼는지 계속 갱신하고, 아직 빠진 조작군이 있으면 다음에 시도할 행동을 바로 제안합니다.

Observation 영역의 live `Action log` 줄은 기록된 이벤트 수, learner-control로 인정된 조작 수, 마지막 learner-control, 마지막 전체 action을 분리해서 보여줍니다. 그래서 `Use live status`, `Clear note`, `Pause` 같은 helper를 눌러도 마지막으로 인정된 물리 실험 조작이 무엇인지 계속 확인할 수 있습니다.

`Use live status`와 `Use changed values` 버튼은 기존 observation note를 덮어쓰지 않고 현재 live status나 실행 시작값 대비 바뀐 slider 값을 뒤에 이어 붙이므로, 학습자가 상태와 파라미터 변경 근거를 한 메모에 함께 남길 수 있습니다. Observation note는 여러 줄 입력을 지원하고, 수동 줄바꿈도 저장 시 evidence item으로 정리됩니다.

`Note preview` 줄은 누적된 observation note를 evidence item 개수와 `|` 구분자로 나눠 보여주므로, `Mark observation`을 누르기 전에 실제 저장될 메모와 증거 항목을 확인할 수 있습니다.

`Mark observation`을 누른 뒤에는 prediction, outcome, note item, learner control, preset comparison 중 무엇이 저장됐는지 status 메시지가 바로 요약합니다.

`Saved observation` 줄은 마지막으로 저장한 observation marker의 prediction, outcome, note item 수, learner-control evidence, preset comparison 저장 여부와 다음 review/보완 단계를 계속 보여주며, control이 빠졌을 때는 가능한 실제 버튼/슬라이더/preset 이름으로 보완 행동을 알려줍니다. 그래서 메모 칸이 비워진 뒤에도 방금 남긴 증거와 다음 행동을 확인할 수 있습니다.

`Clear note`는 `Mark observation` 전에 누적된 observation note를 비우는 보조 버튼입니다. 자동으로 붙인 live status나 changed values가 너무 길어졌을 때 메모를 다시 정리하는 용도이며 learner-control 완료 증거로 세지지 않습니다.

프리셋 선택 기록은 적용 목적과 실제 slider 값을 함께 저장하므로, 실행 후 `Preset choices` 카드에서 학습자가 어떤 의도로 어떤 파라미터 조합을 시험했는지 복기할 수 있습니다. 프리셋이 여러 개인 데모는 `Compare presets` 안내로 권장 비교 순서를 보여주므로, 한 가지 값만 눌러보고 끝내지 않고 여러 파라미터 regime을 관찰한 뒤 `Mark observation`으로 남기게 유도합니다. 실행 중에도 preset status가 지금까지 몇 개를 눌렀고 다음에 어떤 preset을 눌러야 하는지 보여줍니다. 리포트와 `worksheet.md`의 `Preset comparison progress`는 전체 프리셋 중 서로 다른 regime을 몇 개 시험했는지와 다음에 눌러볼 프리셋을 알려줍니다.

리포트와 `worksheet.md`의 `Hands-on activity mix`는 버튼, 슬라이더, preset, observation marker를 각각 몇 번 사용했는지와 조작 다양성을 요약합니다. `Activity path`는 preset, slider, button, observation을 실제로 사용한 순서로 보여주며, learner menu 카드와 `outputs/index.html`에도 짧게 표시됩니다. `worksheet.md`의 control coverage checklist는 해당 config에서 실제로 제공되는 preset, slider, button, 그리고 prediction과 note가 함께 들어간 observation evidence만 `[x]` / `[ ]`로 남깁니다. 그래서 학습자가 preset만 누르고 끝냈는지, 슬라이더 미세 조정이나 버튼형 외란/정지/리셋까지 써봤는지 바로 확인할 수 있습니다.
누적된 observation note는 리포트와 `worksheet.md`에서 `Learner note evidence` 항목으로 나뉘어 보여서, live status와 changed values가 한 문장에 묻히지 않습니다.
리포트와 `worksheet.md`의 `Observation Timeline`은 marker 시간, prediction, outcome, challenge proof, note evidence, live status를 순서대로 비교해 한 실행 안에서 관찰이 어떻게 바뀌었는지 빠르게 복습하게 합니다.
리포트의 review prompt도 최신 `Learner note evidence`를 먼저 보여주므로, 개별 marker 카드를 모두 펼쳐 읽기 전에 가장 최근 증거를 빠르게 확인할 수 있습니다.

실행 중에도 같은 `Course step`, `Mission`, `Playbook`, `Start steps`, `Challenge`, `Viewer legend`, `Done when` 완료 기준이 패널 상단에 표시되므로, MuJoCo 기본 사이드 패널 없이도 현재 추천 경로 위치, 화면의 색상 마커, 학습 증거 조건을 바로 해석할 수 있습니다. `Start steps`는 `Pull Left` / `Push Right`, `Target X -` / `Target X +` 같은 실제 패널 버튼 라벨을 우선 보여주고, required preset이 있는 demo에서는 `Close wall -> Back away -> Re-enter wall`처럼 실제 눌러야 하는 preset 이름과 순서를 표시합니다. 실행 후 생성되는 `report.html`과 `worksheet.md`에도 같은 `Start steps`, `Playbook`, `Challenge`가 남아 예측-조작-증거 확인 순서와 visible-effect 과제를 복습할 수 있습니다.

무엇을 보면 되는지:

| Command | Interaction | What to observe |
|---|---|---|
| `.\run_lab01_interactive.cmd` | mass에 좌/우 힘 펄스, `mass/damping/stiffness` 슬라이더, 감쇠/강성 preset | 자유 진동, 감쇠, 복원력 |
| `.\run_lab02_interactive.cmd` | PID plant에 좌/우 외란, `target/Kp/Ki/Kd/force limit` 슬라이더, PID preset | PID가 목표 위치로 복원하는 과정 |
| `.\run_lab03_interactive.cmd` | 2DOF arm의 `target X/Y`, `task stiffness/damping`, `torque limit` 슬라이더, reach preset | 손끝 목표 위치, Jacobian 제어 오차, 토크 제한 |
| `.\run_lab03_dls_interactive.cmd` | 2DOF DLS의 `target X/Y`, `DLS task gain`, `DLS damping`, `torque limit` 슬라이더, DLS damping preset | singularity 근처 joint speed와 hand error tradeoff |
| `.\run_lab03_condition_dls_interactive.cmd` | 2DOF condition-aware DLS의 damping threshold/full/max damping 슬라이더, schedule preset | 자동 damping schedule이 joint speed와 hand error를 바꾸는 시점 |
| `.\run_lab04_interactive.cmd` | Panda 관절 목표 nudge | 목표 관절 위치 변화와 tracking error |
| `.\run_lab04_cartesian_interactive.cmd` | Panda 손끝 `target X/Y/Z`, `Cartesian gain` 슬라이더, reach preset | 초록 목표점, 파란 손끝, Cartesian tracking error |
| `.\run_lab04_wall_interactive.cmd` | Panda 손끝 `target X/Y/Z`, `wall X/stiffness/damping/retreat gain` 슬라이더, required `Close wall`/`Back away`/`Re-enter wall` preset | 목표를 벽 안쪽으로 밀고, 다시 빼고, 재진입시킬 때 Wall phase, penetration, spring/damping force, retreat, release가 바뀌는 과정 |

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
- 각 실행의 필수 artifact와 report 섹션 검증

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

Viewer를 띄우고 움직임을 실제 시간에 가깝게 보려면 `--headless` 대신 `--viewer --realtime`을 사용합니다. `--viewer`와 `--headless`는 동시에 쓸 수 없으며, 함께 넣으면 CLI가 바로 사용법 오류를 냅니다. `--realtime`과 `--pause-at-end`는 viewer 전용 옵션이므로 `--viewer` 없이 쓰면 CLI가 바로 멈춥니다. 실행이 끝난 뒤 창을 유지하려면 `--pause-at-end`를 함께 붙입니다. Viewer 사이드 패널은 항상 숨겨지며, 실험 조작은 YAML config나 `MCLab Interaction` 창에서 합니다.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot
```

필요한 그래프만 저장하려면 `--plots`를 붙입니다.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot --plots essential
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot --plots position,error,torque
```

Lab04 `joint_pd.yaml`에서 가장 먼저 확인할 것은 `position.png`의 `q_3`와 `target_q_3`, 그리고 `error.png`의 tracking error입니다. 현재 데모는 Panda의 4번째 관절, 즉 `controlled_joint_index: 3`을 minimum-jerk 목표 위치로 움직이는 조인트 위치 제어 예제입니다. 라이브 강의 전에 `configs/lab04_panda/neutral_hold_30s.yaml`을 `--headless --plots stability`로 실행하면, 리포트가 30초 동안의 최대 관절 속도와 관절 drift를 안정성 체크로 보여줍니다.

MuJoCo viewer 양옆 패널은 이 프로젝트의 주 제어 UI가 아닙니다. 현재 랩들은 Python loop가 매 step마다 actuator `ctrl` 값을 YAML 기반 target이나 controller output으로 다시 넣습니다. 따라서 viewer side panel에서 actuator 값을 바꿔도 실행 중에는 곧바로 덮어써지고, `--pause-at-end`로 멈춘 뒤에는 물리 step이 진행되지 않아 움직임이 보이지 않습니다. 그래서 viewer 사이드 패널은 항상 숨겨집니다. 실험 값은 `configs/`의 YAML이나 `MCLab Interaction` 창으로 제어하고, 실행 중 핵심 상태도 그 창에서 확인합니다.

CLI 형식:

```bash
python -m mclab run <lab_name> --config <config_path> [--headless | --viewer] [--realtime] [--pause-at-end] [--plot [--plots <preset_or_names>]] [--output-dir <path>]
```

`--plots`는 어떤 plot preset이나 plot 이름을 저장할지 고르는 옵션이므로 `--plot`과 함께 써야 합니다.

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
| Lab01 MSD | `configs/lab01_msd/*.yaml` | `mass`, `damping`, `stiffness`, `initial_position`, `force_input.magnitude`, `interaction.tuning_presets`, `interaction.playback_speed`, `interaction.pause_resume`, `interaction.reset_plant` |
| Lab02 PID | `configs/lab02_pid/*.yaml` | `controller.kp`, `controller.ki`, `controller.kd`, `controller.output_limit`, `measurement_noise_std`, `control_delay`, `interaction.tuning_presets`, `interaction.playback_speed`, `interaction.pause_resume`, `interaction.reset_plant` |
| Lab03 2DOF/Trajectory | `configs/lab03_2dof/*.yaml` | `mode`, `initial_q`, `target_q`, `target_xy`, `target_xy_waypoints`, `trajectory.type`, `tracking_controller.kp`, `tracking_controller.task_kp`, `tracking_controller.task_kd`, `tracking_controller.dls_damping`, `tracking_controller.condition_damping_threshold`, `tracking_controller.condition_damping_full`, `tracking_controller.max_dls_damping`, `tracking_controller.max_task_speed_schedule`, `interaction.tuning_presets`, `interaction.playback_speed`, `interaction.pause_resume`, `interaction.reset_plant`, `viewer_guides.enabled`, `viewer_guides.target_path` |
| Lab04 Panda | `configs/lab04_panda/*.yaml` | `controlled_joint_index`, `trajectory.end`, `trajectory.duration`, `cartesian_target.position`, `cartesian_target.waypoints`, `cartesian_target.gain`, `cartesian_target.max_step`, `virtual_wall.wall_x`, `virtual_wall.stiffness`, `virtual_wall.damping`, `virtual_wall.force_retreat_gain`, `interaction.tuning_presets`, `interaction.playback_speed`, `interaction.pause_resume`, `interaction.reset_plant`, `viewer_guides.enabled`, `viewer_guides.force` |

Plot preset:

| Lab | Presets |
|---|---|
| Lab01 MSD | `essential`, `energy` |
| Lab02 PID | `essential`, `pid` |
| Lab03 2DOF/Trajectory | `essential`, `profile`, `joint`, `task`, `singularity`, `dls`, `control` |
| Lab04 Panda | `essential`, `control`, `cartesian`, `cartesian_reach`, `wall`, `wall_target`, `wall_compare` |

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
    ├── learner_snapshot.json
    ├── learner_tuned_config.yaml
    ├── report.html
    ├── worksheet.md
    ├── notes.md
    └── plots/
```

- `log.csv`: 시간별 position, velocity, control force, torque/current proxy 등
- `states.npz`: NumPy로 읽기 좋은 배열 데이터
- `summary.json`: config 이름, overshoot, settling time, tracking error 같은 요약 지표
- `learner_snapshot.json`: interactive 실행의 최종 슬라이더 값, 변경된 슬라이더, live status, playback speed를 복기하기 위한 JSON
- `learner_tuned_config.yaml`: interactive 최종 슬라이더 값을 반영하고 live control을 끈 재실행용 YAML
- `report.html`: `Mission` / `Playbook` / `Start steps` / `Challenge` / `Try` / `Change` / `Prediction` / `Question` / `Watch` 학습 가이드, run-level `Done when` 완료 기준, 현재 run이 어느 milestone과 learning-path step에 속하는지 보여주는 `Course Position`, 7개 핵심 체험군의 Done/Next/Missing 상태와 다음 체험 명령을 보여주는 `Course Experience Coverage`, mission proof status와 next proof step을 보여주는 `Mission Evidence`, visible-effect challenge를 proof status/source/next step으로 바꾸는 `Challenge Evidence`, 바로 다음에 할 일을 묶은 `Next Actions`, output folder/raw artifact shortcut, 재현 실행 명령, replay tuned config 명령, 다음 실험 prediction/question/start steps/challenge/key parameter/control surface 요약이 포함된 suggested next runs, 관련 comparison batch 명령, 현재 실행의 버튼/슬라이더/preset/evidence control과 `Counts as control` learner-control 기준을 보여주는 `Control Surface`, config highlights, configured preset cards, singularity/DLS/wall/effort를 포함한 자동 결과 점검, Lab04 wall/contact plot을 바로 읽기 위한 `Key Moments` 타임스탬프와 plot marker, hands-on evidence 완료 상태, learner action summary, learner snapshot, preset choices와 preset comparison progress, prediction review, prediction-observation pair review cue, learner-control 누락 시 config 기반 control 이름을 보여주는 `Evidence Review Cue`, `Observation Timeline`, prediction outcome, prediction/evidence/note가 포함된 observation marker review prompt, 요약값, notes, plot 이미지와 plot 해석 가이드를 한 화면에서 보는 실행 리포트
- `worksheet.md`: `Mission`, `Playbook`, `Start steps`, `Challenge`, `Done when` 완료 기준, `Course Position`, `Course Experience Coverage`의 다음 체험 명령과 coverage map, mission evidence status와 next proof step, challenge evidence status/proof source, 예측, prediction outcome, pending outcome review, learner note, observation timeline, observation `Evidence Review Cue`, live status, 핵심 파라미터, Lab04 `Key Moments`, priority plot review, review checklist, suggested next experiment의 start steps/challenge, comparison batch 명령을 Markdown으로 정리한 복습/제출용 워크시트
- `outputs/index.html`: setup 확인, learner menu, coverage 확인, 추천 경로 preview, 첫 headless run, 첫 hands-on viewer, 첫 comparison batch까지 바로 실행하는 `Starter Commands`, Intro/hands-on/compare/2DOF/singularity/Panda/wall 체험군을 Done/Next/Missing 카드와 CLI 명령으로 추적하는 `Experience Coverage`, 추천 학습 경로 진행표, milestone 진행도, 단계별 `Done when` 완료 기준, 단계별 `Start steps` 실행 순서, 단계별 `Counts as control` learner-control 기준, evidence/outcome pending 상단 요약, hands-on evidence 상태, 단계별 prediction/compare/watch cue, 최신 evidence, `Note evidence` 항목, observation flow와 observation next step, mission evidence와 challenge evidence 요약, report/worksheet/priority plot/replay 바로가기, evidence quality와 outcome mix 요약, mission review queue의 ready/pending 및 observation/prediction/outcome/note/control/artifact 부족 카운트와 다음 review 링크, run별 `Next cue`, batch run에서 worksheet Prediction Check 다음 report `Viewer Handoff`로 이어지는 안내와 직접 링크, `Repeat command`, `Plot review`, observation/prediction/outcome/note 요약, 최신 prediction outcome 요약, 단계별 실행/반복 명령, Lab별 진행 요약, 실행 리포트, worksheet, replayable tuned-config 바로가기, plot 바로가기, `Lesson` / `Next` 안내, 핵심 summary metric을 최신순으로 비교하는 목록 페이지
- `plots/`: 강의 자료에 바로 쓰기 좋은 PNG plot

CLI는 run이나 batch가 끝나면 `report.html`, `worksheet.md`, `outputs/index.html`, `plots/` 또는 `comparison_plots/`처럼 바로 열어볼 주요 산출물 경로를 터미널에 요약합니다.

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

This opens the learner menu. From the menu, learners can launch Lab01-04 auto demos, comparison scenarios, interactive demos, and the Panda virtual wall demo with buttons. Use the `Explore` filters for `Intro`, `Build`, `Deep dive`, `Hands-on`, `Compare`, `PID`, `2DOF`, `Panda`, `Wall`, or `Singularity` to show only the kind of experience a learner wants next. Type keywords such as `PID`, `noise`, `wall`, `hands on`, `Damped PD`, `Far target`, `intro`, or `deep dive` in the search box to filter scenarios. Each item includes `Setup` / `Badges` / `Plan` / `Course step` / `Done when` / `Mission` / `Playbook` / `Start steps` / `Challenge` / `Mission evidence` / `Challenge evidence` / `History` / `Evidence` / `Latest evidence` / `Preset evidence` / `Activity mix` / `Next cue` / `Plots` / `Plot review` / `Worksheet` / `Controls` / `Counts as control` / `Try` / `Change` / `Values` / `Prediction` / `Question` / `Next` / `Compare` / `Watch` guidance, and interactive items also show a `Presets` line so learners know what to try, whether the scenario is a recommended-path step or optional exploration, the rough level, what type of experience it is, how long it runs, the completion rule, which predict-manipulate-evidence sequence to follow, the shortest first-run steps to take, which visible-effect challenge to solve, which manipulation they should prove with which evidence, which artifacts it saves, whether the latest run has observation markers, predictions, outcomes, notes, and pending outcome review, what the `Observation flow` from first marker to latest marker and `Observation next step` for missing prediction/note/outcome evidence said, what the latest prediction/outcome/note, note-evidence items, live status, and missing outcome review said, whether the mission and challenge proof statuses are ready, whether quick preset comparison is complete enough, how varied the button/slider/preset/marker activity was, whether the next best step is to run, try another preset, mark an observation, review an outcome, replay, or compare, which priority graph and worksheet were saved, what to inspect first in that graph, which buttons/sliders/presets they can actually use, which controls count as hands-on completion evidence, which YAML parameters or presets to edit, what the current key values are, what to predict, what question to answer, what follow-up comparison to run next, which batch report to generate, and what to observe. Searches such as `prediction live target`, `question overshoot`, `pull push`, `pause step`, `counts as control`, `course step`, `done when`, `start steps`, `playbook mark observation`, `challenge evidence`, or `challenge visible effect` also find scenarios by their prediction, reflection, controls, and guided action sequence. If `Setup` says `Missing model` or `Config error`, the run button is disabled and learners can use `Config`, `Lesson`, or `Check setup` to diagnose it. Comparison batches also check every included config and model asset, so unavailable `Next` or `Compare` buttons are disabled before launch. `Config` opens the matching YAML parameter file, `Lesson` opens the lab notes, `Report` opens that scenario's latest run report, `Plot` opens the latest saved priority plot, and `Worksheet` opens the latest `worksheet.md` review sheet. `Comparison batches` items also show `Plan`, `Mission`, `Playbook`, `Start steps`, `Challenge`, `Mission evidence`, `Challenge evidence`, `History`, `Report`, `Handoff`, `Plot`, and `Worksheet` buttons, so learners can inspect the batch size, comparison task, latest proof status, latest comparison report, recommended viewer handoff, priority comparison plot, or worksheet directly. The `Next` button launches the follow-up scenario or course comparison batch shown on the card, and the `Compare` button generates the relevant comparison batch report for that lab. Scenarios with no saved run show `History: Not run yet`, and their `Report` / `Plot` / `Worksheet` buttons are disabled. Each demo opens a MuJoCo viewer without side panels and, when needed, a separate `MCLab Interaction` window. That window shows the current demo's `Mission` / `Playbook` / `Challenge` / `Try` / `Change` / `Done when` / `Prediction` / `Question` / `Watch` guide, buttons, sliders with `-` / `+` step buttons, and live status. Run and batch buttons open `report.html` automatically after completion. After a run finishes, the menu status line shows the latest output folder and whether a plot, worksheet, or viewer handoff is available; `Open latest report`, `Open latest plot`, `Open latest worksheet`, batch-only `Open handoff`, and `Open latest folder` reopen the run report, priority graph, review sheet, recommended viewer handoff, or raw log/config artifact folder directly. Use `Open all reports` to open `outputs/index.html` for previous runs. CLI-only users can run `python -m mclab index --open` to regenerate and open the same cumulative review page.

The `Folder` button on each scenario, comparison batch, and learning-path card opens that item's latest output directory. Use `Report` for the HTML report, comparison-batch `Handoff` for the latest report's `Viewer Handoff` section, `Plot` for the prioritized graph, `Worksheet` for the review sheet, `Replay` for tuned YAML reruns, and `Folder` for raw artifacts such as `log.csv`, `states.npz`, `config.yaml`, `summary.json`, `interaction_events.json`, `learner_snapshot.json`, and `learner_tuned_config.yaml`.

`Experience coverage` appears in the menu and `outputs/index.html`. It reads saved outputs and shows which core experience types have evidence: Intro basics, Hands-on controls, Comparison batch, 2DOF/Jacobian, Singularity/DLS, Panda manipulator, and Virtual wall. Interactive runs count as hands-on only after the learner uses at least one button, slider, or preset, the menu shows a seven-item `Coverage map` plus a `Run next` button for the next missing experience, CLI-only learners can run `python -m mclab coverage` to print the same map, next command, and next-experience Plan/Mission/Try/Change/Values/Prediction/Question/Watch/Start steps/Challenge/Controls guide in the terminal, and `outputs/index.html` shows Done/Next/Missing cards with the matching CLI command for each experience.

The `Viewer legend` in the `MCLab Interaction` window explains the green target, small green waypoint path, blue current position, orange force/warning/contact, and red wall markers used by the current demo.
Menu cards show the same information in a `Viewer:` line, and searches such as `red plane`, `orange sphere`, or `green marker` find matching scenarios.
The menu `Viewer:` line, live `Viewer controls`, and run-report `Control Surface` all repeat that MuJoCo side panels are hidden and learners should use YAML or the `MCLab Interaction` controls instead.

Before class, click `Check setup` at the bottom of the menu or run the command below. It checks Python packages, config loading, MuJoCo model assets, learner menu scenario/comparison-batch readiness, and whether `outputs/` is writable. When everything is ready, the CLI prints the launcher, coverage, recommended-path preview, and next path-step commands, while the menu status points learners to `Run next` or `python -m mclab next --preview`.

```powershell
python -m mclab doctor
```

Main comparison scenarios in the menu:

| Lab | Scenario examples |
|---|---|
| Lab01 | underdamped, overdamped, high/low stiffness, interactive pull |
| Lab02 | low/high P gain, PD damping, saturation, windup vs anti-windup, sensor noise, control delay, interactive disturbance |
| Lab03 | 2DOF joint-space, 2DOF task-space, singularity, DLS singularity with live damping presets, early/default/late, inner/edge-target, upper/lower-path, shoulder/elbow/staggered-disturbance recovery-time, low/high-torque, slow/fast-command, low/high-joint-speed, direct/inward-retarget, and fixed/adaptive-speed-retarget condition-aware DLS, interactive XY target tuning, 1D trajectory tracking, step/trapezoidal/minimum-jerk/S-curve profiles |
| Lab04 | neutral hold, 30s stability hold, joint trajectories, hand X motion, Cartesian reach, soft/stiff Cartesian reach, soft/stiff, low/high damping, near/far, slow/fast approach, shallow/deep target push, contact-cycle, and low/high retreat virtual wall, joint target nudge, virtual wall |

First-time learners can follow the `Recommended learning path` at the top of the menu.
Each step reads the saved runs under `outputs/` and shows `Done`, `Needs observation`, `Needs prediction`, `Needs note`, `Needs learner control`, or `Not run yet`. The `Done when` line tells learners the completion criterion for auto-run, hands-on, and batch steps before they launch, the `Start steps` line shows the immediate button/preset order to try, and `Next cue` names the actual button label, slider, or preset to use when the latest run still needs learner-control evidence. The `Counts as control` line names which controls count as hands-on completion evidence. Hands-on steps are not counted as done until the learner uses at least one button, slider, or preset and then saves at least one `Mark observation` entry with both a prediction and a note, and completed hands-on statuses include observation, prediction, outcome, note, and control counts when available. If a prediction exists but the outcome is still missing, the path remains complete but shows an `Outcome review pending` cue. The same evidence rule, `Start steps`, and `Counts as control` are used by the Learning Path cards in `outputs/index.html`; the menu and index also show `Milestones` progress for 1D Dynamics, PID Control, 2DOF Control, Panda Manipulation, and Course Compare. CLI-only learners can run `python -m mclab scenarios wall --filter wall --details` to search guided scenarios and print course step/Done when context, Playbook, Try/Change/Values/Prediction/Question/Watch, Viewer, Counts-as-control, latest report/folder, history/evidence/activity/next cue, next and compare commands, plot/worksheet/replay state, and replay command; broad `wall` searches now put the hands-on `Virtual wall` card first. They can run `python -m mclab params wall --filter hands-on` to print editable YAML/live-control parameters, current config values, controls, prediction prompt, start steps, and the ready-to-run command before choosing a scenario. They can also run `python -m mclab batches wall` to search comparison batches and copy ready-to-run commands, `python -m mclab path` to print the same recommended-path summary, milestone status, next step, next command, and next-step guide, or `python -m mclab path --all` to print a 12-step status map in the terminal. `python -m mclab next --preview` shows the next step plus a Plan/Course/Mission/Try/Change/Values/Prediction/Question/Watch/Start steps/Challenge/Controls guide without running it, adds the Viewer guide only for hands-on steps, and includes worksheet, plot, and plot-review cues for batch steps. `python -m mclab next` prints the same guide, then runs automatic steps headless and hands-on steps in the side-panel-free viewer. After running, `python -m mclab review` prints the saved-run review queue, next report/worksheet, matched action, observation next step, and plot review cue, while `python -m mclab review --open` opens the next pending report directly. The outputs run table's `Evidence` cell shows the latest-observation prediction, outcome, note, note-evidence, live-status summary, the observation flow from first marker state to latest marker state, and the next observation fix to make; when prediction/note evidence and learner-control evidence are both missing, it names the actual controls to use while repairing both gaps. The `Activity` cell shows button/slider/preset/marker variety plus the next activity suggestion, the `Mission evidence` cell shows mission proof status plus the next proof step, and the `Challenge evidence` cell shows the visible-effect challenge proof status/source/next step. Completed steps can reopen their latest report, priority plot, or `worksheet.md` with the adjacent `Report`, `Plot`, and `Worksheet` buttons, and steps whose latest run has `learner_tuned_config.yaml` can use `Replay` to watch the final tuned values again. The `outputs/index.html` run table and Learning Path cards also include `Folder` links so learners can open raw log/config/snapshot directories directly from the browser. The top of the path shows overall progress, how many hands-on steps still need observation, prediction, learner-control, or note evidence, how many still need outcome review, the next recommended step, and a prediction/compare cue plus watch cue before launch. The `Review queue` line below it summarizes ready/pending saved runs, observation/prediction/outcome/note/control/artifact gaps, and the next run to review; `Open next review` opens that run's report directly, while `Open review queue` regenerates and opens the latest `outputs/index.html`. `Run next` launches the first unfinished step. Use `Refresh menu` if the learning path, review queue, batch history, or `Report` / `Plot` / `Worksheet` / `Replay` button state does not update immediately after a run.

CLI discovery commands now print example searches even when matches are found. `scenarios` suggests hands-on wall, singularity, and prediction/live-target searches, `params` suggests wall/PID/DLS parameter searches, and `batches` suggests wall, 2DOF, and all-batch searches. A scenario card or learning-path `Command` is the minimal default path: hands-on steps open the side-panel-free viewer, while auto/comparison steps run headless to generate plots, reports, and worksheets; use `Viewer rerun` only when live inspection is useful.

| Step | Menu button | What it builds |
|---|---|---|
| 1 | `Feel 1D physics` | mass-spring-damper position, velocity, force, and energy |
| 2 | `Disturb and tune` | disturbance plus live mass/damping/stiffness tuning |
| 3 | `Close the loop` | PID tracking, error, and control force |
| 4 | `Tune PID live` | target/Kp/Ki/Kd/force limit tuning |
| 5 | `Move 2DOF joints` | 2DOF joint-space tracking |
| 6 | `Control the hand` | Jacobian-based task-space hand control |
| 7 | `Handle singularity` | condition-aware DLS and Jacobian conditioning |
| 8 | `Compare DLS retarget` | adaptive task-speed schedule and retarget-path comparison |
| 9 | `Hold Panda` | 7DOF Panda neutral-hold baseline |
| 10 | `Reach in Cartesian` | Panda hand XYZ target tracking |
| 11 | `Touch virtual wall` | virtual wall stiffness/damping behavior |
| 12 | `Compare the course` | full batch comparison report set |

To launch individual labs directly:

```powershell
.\run_lab01.cmd
.\run_lab02.cmd
.\run_lab03.cmd
.\run_lab03_dls_interactive.cmd
.\run_lab03_condition_dls_interactive.cmd
.\run_lab04.cmd
```

Each command opens the matching viewer without side panels, saves the lab's essential plots, and opens the run report after completion. If `.venv` is missing, it runs setup first. `run_lab04.cmd` also runs setup when MuJoCo Menagerie is missing.

| Command | Opens | Essential plots |
|---|---|---|
| `.\run_lab01.cmd` | mass-spring-damper viewer | `position`, `velocity`, `force` |
| `.\run_lab02.cmd` | PID viewer | `position`, `control_force`, `error` |
| `.\run_lab03.cmd` | 2DOF arm viewer | `position`, `end_effector`, `torque`, `error` |
| `.\run_lab03_dls_interactive.cmd` | 2DOF DLS singularity viewer | `dls_joint_speed`, `dls_damping`, `condition_number`, `tau_disturbance` |
| `.\run_lab03_condition_dls_interactive.cmd` | 2DOF condition-aware DLS viewer | `dls_condition_scale`, `dls_damping`, `dls_joint_speed`, `tau_disturbance` |
| `.\run_lab04.cmd` | Panda viewer | `position`, `error` |

To compare several conditions at once, use the `Comparison batches` buttons in the menu or run a CLI batch:
Batch cards and `python -m mclab batches ... --details` also show `Course step` and `Done when`. `All compare` appears as recommended path step 12/12, while individual lab comparison batches appear as optional comparisons.

```powershell
.\run_batch_lab01.cmd
.\run_batch_lab02.cmd
.\run_batch_lab03.cmd
.\run_batch_lab04_cartesian.cmd
.\run_batch_lab04.cmd
.\run_all_batches.cmd
```

To run the same batches directly through the CLI:

```powershell
python -m mclab batch lab01_msd_compare
python -m mclab batch lab02_pid_compare
python -m mclab batch lab03_2dof_compare
python -m mclab batch lab04_cartesian_compare
python -m mclab batch lab04_wall_compare
python -m mclab batch all
```

Batches run several configs without opening viewers and save a learner-facing comparison report to `outputs/<timestamp>_<batch_name>/report.html`. The `run_batch_*.cmd` launchers open this report automatically when the batch finishes. Add `--open-report` when running directly through the CLI to get the same behavior. The report includes learning questions, suggested next experiments, whole-batch commands plus per-scenario headless reproduce and viewer rerun commands, scenario cards with report/priority-plot/scenario-worksheet/folder quick links, priority plot guidance, baseline config and metric change summaries, a `Control surface` cue for controls available when rerunning the scenario interactively, and start steps/challenge/prediction/question/watch cues, automatic comparison takeaways, a `Prediction Check` outcome table, metric min/max highlights, metric changes from the baseline scenario, a YAML parameter difference table, comparison plots that overlay multiple scenarios on the same graph, a key metric table, and plot previews. The Lab04 wall batch also writes `wall_key_moment_timing_compare.png` to compare contact and peak force/damping/hand-speed timing. The `worksheet.md` in the same folder summarizes per-scenario key metrics, start steps/challenges, prediction outcome checks, priority plot guidance, scenario worksheet and folder links, headless/viewer rerun commands, comparison checklist prompts, and next-experiment ideas in Markdown. The `index.html` in the same folder is the detailed list of every individual run report, priority plot shortcut, and artifact. The Lab01 batch compares damping/stiffness cases, Lab02 compares gain/saturation/windup/noise/delay cases, Lab03 compares joint-space/task-space/singularity/DLS singularity cases plus early/default/late condition-aware damping schedules, inner/edge target positions, upper/lower path branches, shoulder/elbow/staggered disturbance recovery with `disturbance_recovery_duration`, low/high torque limits, slow/fast command speeds, low/high joint-speed limits, direct/inward retargeting paths, and fixed/adaptive task-speed retarget schedules, and Lab04 compares soft/stiff Cartesian reach plus soft/stiff virtual wall, fixed-stiffness low/high wall damping, near/far wall position, slow/fast wall approach speed, shallow/deep target push depth, contact-cycle target crossing, and low/high force-to-retreat gain cases. To generate the full course report set at once, run `.\run_all_batches.cmd` or `python -m mclab batch all --open-report`. This creates `outputs/<timestamp>_all_batches/report.html` and a course-level `worksheet.md`; both show each batch focus/question and link to all five batch reports, batch worksheets, and batch folders.

Each batch report and worksheet also includes a `Viewer Handoff` section. It recommends the scenario with the largest baseline metric change, shows why that scenario was picked, links its report, priority plot, worksheet, and folder, and gives the exact side-panel-free `--viewer --realtime --pause-at-end` rerun command for live inspection. The full course-level `all` report links each batch card directly to that batch's `Viewer Handoff` anchor.

The `Prediction check` line on batch cards asks learners to write a prediction before running the batch, then points them to the `Prediction Check` table in `worksheet.md` to mark `Matched`, `Partly matched`, or `Surprised`. CLI learners can run `python -m mclab batches <query> --details` to see the latest history, worksheet, plot, plot review, prediction check, and the handoff viewer rerun command parsed from the latest worksheet before choosing the next batch. For the `all` course batch, the CLI follows the linked child batch worksheet and prints the first available viewer rerun command.

Use the interactive launchers when learners should disturb the system and watch the physics respond:

```powershell
.\run_lab01_interactive.cmd
.\run_lab02_interactive.cmd
.\run_lab03_interactive.cmd
.\run_lab03_dls_interactive.cmd
.\run_lab03_condition_dls_interactive.cmd
.\run_lab04_interactive.cmd
.\run_lab04_cartesian_interactive.cmd
.\run_lab04_wall_interactive.cmd
```

Each interactive launcher opens the MuJoCo viewer without side panels plus a small `MCLab Interaction` window. Lab01-02 viewers show a gray equilibrium marker, green target marker, and orange force-direction bar. In Lab01-02, `Pull Left` / `Push Right` applies short force pulses to the mass; in the Lab03 2DOF interactive viewer, `Shoulder pulse` / `Elbow pulse` applies short disturbance torque pulses to each joint. Sliders tune key parameters while the simulation is running. Keyboard shortcuts also work when the viewer has focus: `A` or left arrow for left/shoulder, `D` or right arrow for right/elbow. Lab03 2DOF viewers show a green target hand point, blue current hand point, and orange singularity-warning hand point. In Lab04 joint mode, buttons nudge the controlled joint target; in Cartesian/wall mode, `Target X -` / `Target X +` nudge the green hand target, and `Target X + into wall` pushes it deeper through the virtual wall. Lab04 Cartesian/wall viewers automatically show a green target point, blue current hand point, orange contact hand point, orange wall-force direction bar, and translucent red wall guide. The `MCLab Interaction` window is scrollable and resizable, so dense demos such as the Lab04 wall still keep the lower observation and live-status controls reachable. `Quick presets` apply representative parameter sets such as `Soft reach`, `Stiff wall`, and `Damped PD` with one click; hovering or applying a preset keeps preset progress, the next required preset, and the remaining required path visible in the panel. In the Lab04 wall demo, the required preset path is `Close wall -> Back away -> Re-enter wall`; learners must use that order for completion evidence, so they can create contact, release, and a second contact in one viewer run. Use the `-` / `+` buttons next to a slider for one-resolution-step adjustments; the `Changed values` line immediately summarizes parameters changed from the run's starting values. `Playback speed` changes realtime viewer pacing from 0.25x to 2.0x, so learners can slow down fast responses or skim long settling behavior. `Pause / Resume` stops physics stepping and logging so learners can inspect the viewer, adjust sliders, write a prediction, and continue from the same simulation time. While paused, `Step once` advances exactly one physics step and pauses again, which is useful for fast contact, oscillation, and singularity moments. After changing sliders, use `Reset sliders` to return to the values from the start of the run, or `Reset plant` to return the mass or robot to its initial state while keeping the current slider values for another observation. After using at least one button, slider, or preset, type a short prediction, choose whether the outcome was `Matched`, `Partly matched`, or `Surprised`, then either press `Use live status` to copy the current dashboard values into the note or write an observation note manually before pressing `Mark observation`. This saves the current learning question, prediction, prediction outcome, evidence prompt, challenge proof state, note, changed sliders, current slider values, and live status values for review in the run report's `Observation Markers` cards. `Use live status` and `Use changed values` are evidence-helper buttons for filling notes, while `Pause / Resume`, `Step once`, and `Playback speed` are view/pacing helpers, so they do not satisfy the learner-control requirement by themselves. The observation area's `Evidence checklist` shows whether learner control, prediction, preset comparison, outcome, and note fields are ready before marking. If the `Prediction` field is empty or no learner control has been used yet, the panel status line warns that the marker is not enough to complete the learning path, and after `Mark observation` it repeats the missing button, slider, or preset action by name. The `Live status` area shows only the key values learners should watch now, such as Run time, Remaining, position, error, force, energy, disturbance torque, Target X nudge, Target-Wall gap, Wall phase, and wall penetration; during the final second it shows a Run clock cue telling learners to press `Pause / Resume` if they need more inspection time. In Lab04 wall runs, `Target past wall` means the green target crossed the wall, while `Contact: wall pushing back` means the hand is actually penetrating and the virtual wall force is active. The run report `Key Moments` also separates Target crosses wall, First wall contact, Wall contact release, and Target backs away so learners can review target crossing apart from physical contact and release. When learners use buttons, presets, or sliders, the run report adds a `Learner Action Summary`, `Learner Snapshot`, `Replay Tuned Config`, and raw `Interaction Log`; final slider/status values are saved in `learner_snapshot.json`, the final slider values are folded into replayable `learner_tuned_config.yaml`, and time-ordered events are saved in `interaction_events.json`. In the learner menu, the `Replay` button is enabled only when the latest scenario output has `learner_tuned_config.yaml`, so learners can immediately watch their final tuned values again without live controls.

The panel's `Done when` and `Counts as control` lines separate actual panel button labels, live sliders, and Quick presets from helper controls. When required presets exist, `Done when` names the required order directly, such as `Close wall -> Back away -> Re-enter wall`. View/evidence helpers such as `Pause`, `Playback speed`, and `Use live status` help learners inspect and write notes, but they do not satisfy the learner-control completion requirement.

Lab04 wall live status separates total wall force, spring force, damping force, and wall retreat so learners can tell what stiffness and damping are changing while the run is still moving.

The observation area's `Next action` line names the immediate learner step from the current state. It asks for a prediction first, names actual panel button labels such as `Pull Left` / `Push Right` or `Target X -` / `Target X +` when button evidence is missing, names the next required preset when one is missing, recommends `Use live status` or a short note when evidence is thin, and then moves the learner toward `Mark observation`.

The `Evidence quality` line tells learners before saving whether the observation is incomplete, ready to mark without an outcome, or review-ready, and it names the needed button, slider, or preset action when control evidence is missing.

The `Challenge proof` line tells learners whether the visible-effect challenge still needs a prediction, learner control, preset evidence, note/live-status evidence, or outcome review, and it names the actual panel button or control family when learner control is missing.

The observation area's live `Activity mix` line continuously counts button, slider, preset, and observation-marker use during the current run, then recommends the next missing control family to try.

The observation area's live `Action log` line separates total events, counted learner-control events, the latest learner-control action, and the latest overall action. Helper actions such as `Use live status`, `Clear note`, or `Pause` can be recorded without hiding the last physical experiment control that counts toward completion.

The `Use live status` and `Use changed values` buttons append to the existing observation note instead of replacing it, so learners can keep both live-state evidence and slider changes in one note. Observation notes support multiline entry, and manual line breaks are normalized into evidence items when saved.

The `Note preview` line splits the accumulated observation note into evidence-item counts and `|`-separated items so learners can check exactly what will be saved before pressing `Mark observation`.

After `Mark observation`, the status message immediately summarizes which evidence was saved: prediction, outcome, note items, learner control, and preset comparison.

The `Saved observation` line keeps the latest marker recap visible after saving, including prediction, outcome, note-item count, learner-control evidence, preset-comparison evidence, and the next review or repair step. When control evidence is missing, it names the available button, slider, or preset controls, so learners can confirm what was recorded and what to do next even after the note box clears.

`Clear note` clears the accumulated observation note before `Mark observation`. Use it to clean up overly long live-status or changed-value notes; it is an evidence-editing helper and does not count as learner-control completion evidence.

Preset choice events save both the preset purpose and the applied slider values, so the report's `Preset choices` card shows why a learner tried that parameter set. Demos with multiple presets also show a `Compare presets` hint so learners try more than one parameter regime before saving a `Mark observation`. During a live run, the preset status also shows how many presets have been tried and which preset to try next. The report and `worksheet.md` `Preset comparison progress` entries show how many distinct regimes were tried and which preset to try next.

The report and `worksheet.md` `Hands-on activity mix` summarize button, slider, preset, and observation-marker usage. `Activity path` shows the actual preset, slider, button, and observation sequence, and a compact version also appears on learner menu cards and `outputs/index.html`. The `worksheet.md` control coverage checklist marks only the preset, slider, button, and prediction-plus-note observation evidence available in that config with `[x]` / `[ ]`. This makes it easy to see whether learners only clicked a preset or also tried fine slider tuning and button-based disturbances, pauses, nudges, or resets.
Accumulated observation notes are also split into `Learner note evidence` items in the report and `worksheet.md`, so live status and changed values do not disappear inside one long sentence.
The report and `worksheet.md` `Observation Timeline` compare marker time, prediction, outcome, challenge proof, note evidence, and live status in order, so learners can review how their observations changed within one run.
The report review prompt also surfaces the latest `Learner note evidence` before the individual marker cards, making the newest saved evidence faster to inspect.

The same `Course step`, `Mission`, `Playbook`, `Start steps`, `Challenge`, `Viewer legend`, and `Done when` completion criterion appear near the top of the panel during a live run, so learners can read the current recommended-path position, colored scene markers, and evidence requirement without opening the MuJoCo side panels. `Start steps` names actual panel buttons such as `Pull Left` / `Push Right` or `Target X -` / `Target X +`, and for demos with required presets it names the exact preset order learners should press, such as `Close wall -> Back away -> Re-enter wall`. The generated `report.html` and `worksheet.md` keep the same `Start steps`, `Playbook`, and `Challenge` so learners can review the predict-manipulate-evidence sequence and visible-effect task after the run.

What to observe:

| Command | Interaction | What to observe |
|---|---|---|
| `.\run_lab01_interactive.cmd` | left/right force pulse, `mass/damping/stiffness` sliders, damping/stiffness presets | free oscillation, damping, restoring force |
| `.\run_lab02_interactive.cmd` | left/right disturbance, `target/Kp/Ki/Kd/force limit` sliders, PID presets | PID disturbance rejection |
| `.\run_lab03_interactive.cmd` | 2DOF arm `target X/Y`, `task stiffness/damping`, `torque limit` sliders, reach presets | hand target motion, Jacobian control error, torque limits |
| `.\run_lab03_dls_interactive.cmd` | 2DOF DLS `target X/Y`, `DLS task gain`, `DLS damping`, `torque limit` sliders, DLS damping presets | joint-speed and hand-error tradeoff near a singularity |
| `.\run_lab03_condition_dls_interactive.cmd` | 2DOF condition-aware DLS damping threshold/full/max damping sliders, schedule presets | when automatic damping changes joint speed and hand error |
| `.\run_lab04_interactive.cmd` | Panda joint target nudge | target position changes and tracking error |
| `.\run_lab04_cartesian_interactive.cmd` | Panda hand `target X/Y/Z`, `Cartesian gain` sliders, reach presets | green target point, blue hand point, Cartesian tracking error |
| `.\run_lab04_wall_interactive.cmd` | Panda hand `target X/Y/Z`, `wall X/stiffness/damping/retreat gain` sliders, required `Close wall`/`Back away`/`Re-enter wall` presets | how Wall phase, penetration, spring/damping force, retreat, and release change when the target moves through, backs out of, and re-enters the wall |

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
- verifies required artifacts and report sections for each run

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

Use `--viewer --realtime` instead of `--headless` to open the MuJoCo viewer and pace motion close to wall-clock time. `--viewer` and `--headless` are mutually exclusive; using both makes the CLI stop with a usage error. `--realtime` and `--pause-at-end` are viewer-only flags, so the CLI stops if they are used without `--viewer`. Add `--pause-at-end` to keep the window open after the simulation finishes. Viewer side panels are always hidden; change experiments through YAML configs or the `MCLab Interaction` window.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot
```

To save only the plots you need, add `--plots`.

```bash
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --viewer --realtime --pause-at-end --plot --plots essential
python -m mclab run lab04 --config configs/lab04_panda/joint_pd.yaml --headless --plot --plots position,error,torque
```

For Lab04 `joint_pd.yaml`, check `q_3` versus `target_q_3` in `position.png` first, then the tracking error in `error.png`. This demo controls Panda joint 4, represented by `controlled_joint_index: 3`, with a minimum-jerk target position. Before a live class demo, run `configs/lab04_panda/neutral_hold_30s.yaml` headless with `--plots stability`; the report checks maximum joint speed and joint drift for the 30-second hold.

The MuJoCo viewer side panels are not the main control UI for this project. The Python loops write actuator `ctrl` values from YAML-based targets or controller outputs at every simulation step. If you change actuator values in the viewer side panel, they are overwritten during the run; after `--pause-at-end`, physics stepping has stopped, so slider edits do not move the robot. Viewer side panels are therefore always hidden. Change experiment parameters in YAML under `configs/` or use the `MCLab Interaction` window, which also shows the live status values learners need during the demo.

CLI shape:

```bash
python -m mclab run <lab_name> --config <config_path> [--headless | --viewer] [--realtime] [--pause-at-end] [--plot [--plots <preset_or_names>]] [--output-dir <path>]
```

`python -m mclab --help` prints the learner workflow for setup checking, opening the menu, checking coverage, looking up editable parameters, previewing the next path step, and launching the next path step.

`--plots` selects which plot preset or plot names to save, so it must be used with `--plot`.

List learner entry points plus available labs and batches:

```bash
python -m mclab list
```

Running `python -m mclab` with no subcommand prints the same entry points for `doctor`, `menu`, `coverage`, `params`, `next --preview`, and `next`.

To see what a learner can change before running a scenario:

```bash
python -m mclab params wall --filter hands-on
python -m mclab params PID
python -m mclab params DLS --limit 0
```

`params` prints the matching scenario config, key YAML/live-control parameters, current YAML values, available controls, prediction prompt, start steps, and the ready-to-run command. Use it when a learner asks which parameter to change or why MuJoCo side panels are hidden.

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
| Lab01 MSD | `configs/lab01_msd/*.yaml` | `mass`, `damping`, `stiffness`, `initial_position`, `force_input.magnitude`, `interaction.tuning_presets`, `interaction.playback_speed`, `interaction.pause_resume`, `interaction.reset_plant` |
| Lab02 PID | `configs/lab02_pid/*.yaml` | `controller.kp`, `controller.ki`, `controller.kd`, `controller.output_limit`, `measurement_noise_std`, `control_delay`, `interaction.tuning_presets`, `interaction.playback_speed`, `interaction.pause_resume`, `interaction.reset_plant` |
| Lab03 2DOF/Trajectory | `configs/lab03_2dof/*.yaml` | `mode`, `initial_q`, `target_q`, `target_xy`, `target_xy_waypoints`, `trajectory.type`, `tracking_controller.kp`, `tracking_controller.task_kp`, `tracking_controller.task_kd`, `tracking_controller.dls_damping`, `tracking_controller.condition_damping_threshold`, `tracking_controller.condition_damping_full`, `tracking_controller.max_dls_damping`, `tracking_controller.max_task_speed_schedule`, `interaction.tuning_presets`, `interaction.playback_speed`, `interaction.pause_resume`, `interaction.reset_plant`, `viewer_guides.enabled`, `viewer_guides.target_path` |
| Lab04 Panda | `configs/lab04_panda/*.yaml` | `controlled_joint_index`, `trajectory.end`, `trajectory.duration`, `cartesian_target.position`, `cartesian_target.waypoints`, `cartesian_target.gain`, `cartesian_target.max_step`, `virtual_wall.wall_x`, `virtual_wall.stiffness`, `virtual_wall.damping`, `virtual_wall.force_retreat_gain`, `interaction.tuning_presets`, `interaction.playback_speed`, `interaction.pause_resume`, `interaction.reset_plant`, `viewer_guides.enabled`, `viewer_guides.force` |

Plot presets:

| Lab | Presets |
|---|---|
| Lab01 MSD | `essential`, `energy` |
| Lab02 PID | `essential`, `pid` |
| Lab03 2DOF/Trajectory | `essential`, `profile`, `joint`, `task`, `singularity`, `dls`, `control` |
| Lab04 Panda | `essential`, `control`, `cartesian`, `cartesian_reach`, `wall`, `wall_target`, `wall_compare` |

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
    ├── learner_snapshot.json
    ├── learner_tuned_config.yaml
    ├── report.html
    ├── worksheet.md
    ├── notes.md
    └── plots/
```

- `log.csv`: time-series signals such as position, velocity, control force, torque/current proxy
- `states.npz`: NumPy-friendly arrays
- `summary.json`: config name and metrics such as overshoot, settling time, tracking error
- `learner_snapshot.json`: final interactive slider values, changed sliders, live status, and playback speed for reviewing the hands-on state
- `learner_tuned_config.yaml`: replayable YAML with final interactive slider values applied and live controls disabled
- `report.html`: a one-page run report with `Mission` / `Playbook` / `Start steps` / `Challenge` / `Try` / `Change` / `Prediction` / `Question` / `Watch` learning guidance, run-level `Done when` completion criteria, `Course Position` for the matching milestone and learning-path step, `Course Experience Coverage` for the Done/Next/Missing state of the seven core experience types plus the next-experience command, `Mission Evidence` proof status and next proof step, `Challenge Evidence` that turns the visible-effect challenge into a proof status/source/next step, a `Next Actions` shortcut section with raw artifact and output-folder links, reproduce commands, replay tuned config commands, suggested next runs with their own prediction prompts, questions, start steps, challenges, key parameter changes, and control-surface summaries, a relevant comparison batch command, a `Control Surface` section for the current run's buttons/sliders/presets/evidence controls plus `Counts as control` learner-control criteria, config highlights, configured preset cards, automatic result checks for signals such as singularity, DLS speed, wall response, and actuator effort, `Key Moments` timestamps and plot markers for reading Lab04 wall/contact plots quickly, hands-on evidence completion status, learner action summary, learner snapshot, preset choices and preset comparison progress, prediction review, prediction-observation pair review cues, an `Evidence Review Cue` that names configured controls when learner-control evidence is missing, `Observation Timeline`, prediction outcomes, observation marker review prompts with predictions/evidence/notes, summary values, notes, plot images, and plot interpretation guides
- `worksheet.md`: a Markdown review/submission worksheet with `Mission`, `Playbook`, `Start steps`, `Challenge`, `Done when` completion criteria, `Course Position`, `Course Experience Coverage` next-experience command and coverage map, mission evidence status and next proof step, challenge evidence status/proof source, predictions, prediction outcomes, pending outcome review, learner notes, observation timeline, observation `Evidence Review Cue`, live status, key parameters, Lab04 `Key Moments`, priority plot review prompts, a review checklist, suggested next experiments with start steps and challenges, and comparison batch commands. Auto-run worksheets use Plot Review and Challenge Evidence checklist items instead of asking for unavailable `Mark observation` controls; interactive worksheets keep the learner-control and observation-marker checklist.
- `outputs/index.html`: a newest-first index with first-use `Starter Commands` for setup checking, the learner menu, coverage checking, editable-parameter lookup, recommended-path preview, the first headless run, the first hands-on viewer, and the first comparison batch, `Experience Coverage` Done/Next/Missing cards with CLI commands for Intro/hands-on/compare/2DOF/singularity/Panda/wall evidence, the recommended learning path, milestone progress, per-step `Done when` completion criteria, per-step `Start steps` launch sequence, per-step `Counts as control` learner-control criteria, top-level evidence/outcome pending summaries, hands-on evidence status, per-step prediction/compare/watch cues, batch `Prediction Check` cues, latest evidence, note-evidence items, observation flow, observation next step, mission evidence and challenge evidence summaries plus report/worksheet/priority-plot/replay links, evidence-quality and outcome-mix summaries, a mission review queue with ready/pending totals, observation/prediction/outcome/note/control/artifact gap counts, and the next review link, per-run `Next cue` text plus a direct link that sends completed batches from the worksheet Prediction Check to the report `Viewer Handoff`, `Repeat command`, and `Plot review`, observation/prediction/outcome/note summaries, latest prediction-outcome snippets, per-step run/repeat commands, lab progress cards, run reports, worksheets, replayable tuned-config shortcuts, plot shortcuts, `Lesson` / `Next` guidance, and key summary metrics
- `plots/`: PNG plots suitable for quick inspection or lecture slides

After each run or batch, the CLI prints the key artifact paths to open next, including `report.html`, `worksheet.md`, `outputs/index.html`, `plots/`, or `comparison_plots/` when they exist. When `worksheet.md` includes review guidance, the CLI also prints the priority plot, review focus, next proof step, and first checklist item. Batch worksheets also surface `Prediction check` and the recommended `Viewer handoff` rerun command so learners can judge their prediction and reopen the strongest scenario in the side-panel-free viewer. When the worksheet includes course coverage, it also prints the next experience and ready-to-run next command.

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
- singularity demo with Jacobian determinant, manipulability, condition number plots, and condition-aware DLS damping comparison
- joint position, end-effector, torque, current proxy, error plots
- step, trapezoidal, quintic/minimum-jerk, S-curve trajectory generators
- legacy 1D trajectory profile configs plus a live 1D trajectory tracking demo for comparing target position/velocity/acceleration/jerk and tracking error

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
