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
- Lab03 DLS singularity viewer supports live Low/Balanced/High DLS damping presets
- Lab03 DLS singularity has a one-line `run_lab03_dls_interactive.cmd` launcher
- Lab03 condition-aware DLS supports live schedule presets and a one-line `run_lab03_condition_dls_interactive.cmd` launcher
- Lab03 condition-aware DLS inner/edge target comparison configs for target-position conditioning lessons
- Lab03 condition-aware DLS upper/lower path comparison configs for mirrored IK-branch lessons
- Lab03 condition-aware DLS shoulder/elbow/staggered disturbance comparison configs for recovery lessons
- Lab03 condition-aware DLS low/high torque-limit comparison configs for actuator-limit lessons
- Lab03 condition-aware DLS slow/fast command-speed comparison configs for target-speed lessons
- Lab03 condition-aware DLS low/high joint-speed-limit comparison configs for speed-clipping lessons
- Lab03 condition-aware DLS direct/inward retargeting comparison configs for target-path lessons
- Lab03 retargeting DLS viewer guides show small green waypoint path markers for target-path lessons
- Learner menu exposes Lab03 upper/lower path, shoulder/elbow disturbance, low/high torque-limit, slow/fast command-speed, low/high joint-speed-limit, and direct/inward retargeting DLS scenario cards with compare/search/filter support
- Lab04 Franka Emika Panda manipulator using MuJoCo Menagerie
- Lab04 30-second neutral-hold stability check config and report checks
- Lab04 Cartesian reach with damped-least-squares Jacobian target offsets
- Lab04 soft/stiff Cartesian reach comparison configs and batch report
- Lab04 Cartesian interactive one-line launcher for live XYZ target tuning
- Lab04 Cartesian/wall interactive demos use Target X nudge buttons; wall mode labels them as away/into-wall contact controls
- Lab04 deterministic virtual wall with soft/stiff stiffness-damping comparison configs
- Lab04 virtual wall interactive demo supports live hand target X/Y/Z tuning plus wall parameter tuning
- Lab04 virtual wall interactive demo includes Close wall, Back away, and Re-enter wall required presets for one-click contact, release, and repeated-contact observation
- Lab04 virtual wall live status and logs include Target-Wall gap, Wall phase, target crossing, and contact release for clearer wall-contact lessons
- Lab04 virtual wall live status separates total wall force, spring force, damping force, and retreat distance during live interaction
- Lab04 wall plot preset includes `wall_target.png` for target/wall/gap interpretation
- Lab04 low/high damping virtual wall configs that isolate damping with fixed stiffness and retreat gains
- Lab04 near/far virtual wall configs that isolate wall position with fixed stiffness, damping, and retreat gains
- Lab04 slow/fast approach virtual wall configs that isolate velocity-dependent damping force with fixed wall gains
- Lab04 shallow/deep target-push virtual wall configs that isolate commanded target depth with fixed wall gains
- Lab04 contact-cycle virtual wall config that uses Cartesian waypoints for repeated target crossing, contact, and release lessons
- Lab04 low/high retreat-gain virtual wall configs that isolate force-to-retreat mapping with fixed wall force settings
- Lab04 viewer visual guides for Cartesian target, current hand position, contact state, wall-force direction, and virtual wall
- YAML configs, MuJoCo XML models, docs, and tests for the implemented labs
- Run reports with domain-specific checks for singularity, DLS speed, virtual wall response, and actuator effort
- Batch comparison reports with scenario cards, priority plot guidance, automatic comparison takeaways, min/max highlights, baseline deltas, parameter differences, and comparison plots
- Batch comparison runs generate `worksheet.md` review artifacts with scenario metrics, priority plot guidance, scenario worksheet links, reproduce commands, and comparison checklists
- Batch comparison reports and worksheets include `Prediction Check` outcome prompts so learners can mark whether evidence matched, partly matched, or surprised their prediction
- The full `all` batch run generates a course-level report and `worksheet.md` that show each batch focus/question and link batch reports and batch worksheets
- Batch scenario cards include per-config prediction, reflection question, and watch cues from the run guides
- Batch reports include whole-batch and per-scenario reproduce commands for learner handoff
- Batch scenario cards include run-report, priority-plot, and scenario-worksheet quick links when artifacts are available
- Batch scenario cards summarize the first few YAML changes from the baseline scenario
- Batch scenario cards summarize the largest metric changes from the baseline scenario
- Batch scenario cards include a `Control surface` cue for available live controls when the scenario is rerun interactively
- MuJoCo viewer side panels are always hidden for learner demos; use the `MCLab Interaction` panel and YAML configs as the control surface
- Interactive `MCLab Interaction` quick presets, purpose/value previews, and per-slider step buttons for representative damping, PID, 2DOF reach, Panda reach, and virtual wall parameter sets
- Lab03 2DOF interactive viewer demos include Shoulder/Elbow pulse buttons for live joint-disturbance recovery observations
- Interactive preset groups show a compare-in-order hint so learners try multiple parameter regimes before marking an observation
- Interactive preset status shows live preset comparison progress and the next preset to try
- Interactive preset hover and apply previews keep preset progress, the next required preset, and the remaining required path visible
- Interactive preset choices save purpose text into `interaction_events.json` and the run report `Preset choices` card
- Run reports show `Preset comparison progress` for interactive runs so learners know whether they tried enough preset regimes
- Generated `worksheet.md` artifacts include preset comparison progress for interactive runs with multiple presets
- Run reports and generated `worksheet.md` artifacts include a `Hands-on activity mix` summary for button, slider, preset, and observation-marker variety
- Run reports and generated `worksheet.md` artifacts include a chronological `Activity path` for the learner's button, slider, preset, and observation-marker sequence
- Generated `worksheet.md` artifacts include a control coverage checklist for preset, slider, button, and prediction-plus-note observation evidence
- Activity mix and control coverage prompts only require control families that are available in the run config
- Interactive `MCLab Interaction` changed-values summary shows slider parameters changed from run start
- Interactive `MCLab Interaction` panel is scrollable and resizable so dense demos keep observation and live-status controls reachable
- Interactive `MCLab Interaction` panel and run reports show a `Viewer legend` for visible target/current/waypoint/force/singularity/wall markers
- Interactive `MCLab Interaction` panel, run reports, and worksheets show a shared `Mission` prompt so the learner sees the same evidence-focused task during launch, live tuning, and review
- Interactive `MCLab Interaction` panel shows a `Done when` evidence criterion before Prediction and Mark observation controls, naming available learner-control families when possible
- Interactive `MCLab Interaction` panel shows a `Counts as control` cue that separates learner-control actions from view/evidence helpers such as Pause, Playback speed, and Use live status
- Interactive `MCLab Interaction` observation area shows a live `Evidence checklist` for learner-control, prediction, preset comparison, outcome, and note readiness before marking
- Interactive `MCLab Interaction` observation area shows a live `Evidence quality` cue for incomplete, control-missing, ready-to-mark, and review-ready observations
- Interactive `MCLab Interaction` observation area shows a live `Challenge proof` cue that tells whether the visible-effect challenge still needs prediction, learner control, preset evidence, note/live-status evidence, or outcome review
- Interactive `MCLab Interaction` observation area shows a live `Next action` cue so learners know whether to write a prediction, use a button/slider/preset, try a required preset, use live status, choose an outcome, or mark the observation
- Interactive `MCLab Interaction` observation status and `Next action` cues name the available learner-control families when a scenario exposes experiment buttons, live sliders, or Quick presets
- Interactive `MCLab Interaction` observation area shows a live `Activity mix` cue that counts button, slider, preset, and marker use and recommends the next missing control family
- Interactive `MCLab Interaction` observation area shows a live `Action log` cue confirming the latest learner button, slider, preset, or marker event
- Interactive `MCLab Interaction` observation area shows a wrapped `Note preview` so accumulated evidence is readable before `Mark observation`
- Hands-on mission evidence and learning-path completion require at least one learner control event (`button`, `slider`, or `preset`) plus a prediction-and-note observation marker
- Evidence helper buttons such as `Use live status` and `Use changed values`, plus view/pacing controls such as pause, step, and playback speed, do not satisfy the learner-control requirement by themselves
- Run reports and worksheets include `Mission Evidence` status with observation, prediction, outcome, note, learner-control, plot counts, and the next proof step
- Run reports and worksheets include `Challenge Evidence` status that maps the visible-effect challenge to proof status, proof source, mission evidence status, and next challenge step
- Learner menu cards and outputs index learning-path/run-table views summarize `Challenge evidence` proof status, proof source, and next challenge step from the latest saved run
- Learner menu scenario cards include a `Viewer` marker legend and marker-name search support
- Learner menu scenario cards include a `Controls` summary of actual buttons, sliders, presets, pause/step, reset, and observation controls
- Learner menu scenario cards include a `Counts as control` cue matching the live panel so learners know which controls satisfy hands-on evidence before launch
- Learner menu and outputs index `Needs learner control` states name the available learner-control families, such as experiment buttons, live sliders, and Quick presets
- Learner menu scenario and batch cards include a `Plan` line with level, mode, run length, and saved artifacts
- Learner menu scenario, batch, and learning-path cards include a `Mission` line that turns Try/Change/Watch guidance into one evidence-focused task
- Learner menu scenario and batch cards, the live interaction panel, run reports, and worksheets include a `Playbook` line that turns each demo into predict, manipulate, and evidence-review steps
- Learner menu scenario and batch cards, the live interaction panel, run reports, and worksheets include a compact `Start steps` line for the shortest predict-run-control-review sequence before learners read the longer card
- `Start steps` uses concrete configured preset names and required-preset order when available, such as `Close wall -> Back away -> Re-enter wall`
- Batch `Start steps` wording is shared between the learner menu and `outputs/index.html`, including the course-level `Run all comparison batches` path
- Learner menu scenario and batch cards, the live interaction panel, run reports, and worksheets include a `Challenge` line that gives learners an active visible-effect task to prove with plots or observation evidence
- Learner menu scenario and batch cards include `Mission evidence` proof status from the latest run before opening the report
- Learner menu batch cards include a `Prediction check` cue that points learners to the saved worksheet outcome table
- Learner menu scenario cards include a `Latest evidence` summary from the latest observation marker prediction, outcome, note, and live status
- Learner menu scenario cards include an `Activity mix` summary from the latest hands-on run's button, slider, preset, and observation-marker events
- Learner menu cards and outputs index activity summaries include a compact latest `Activity path`
- Learner menu scenario cards include a `Next cue` that points learners toward the next best action: run, try another preset, mark observation, review outcome, replay, or compare
- Interactive `Playback speed` slider controls realtime viewer pacing from slow-motion to faster skim
- Interactive `Pause / Resume` button pauses physics stepping and logging while keeping viewer and sliders responsive
- Interactive `Step once` button advances exactly one physics step while staying paused for frame-by-frame observation
- Interactive `Reset plant` button restores mass/arm/robot state while preserving current slider and preset values for repeated observations
- Interactive `Use live status` button appends current live dashboard values to the observation note before `Mark observation`
- Interactive `Use changed values` button appends slider changes from run start to the observation note before `Mark observation`
- Interactive `Mark observation` saves the current challenge-proof status plus an optional prediction outcome such as Matched, Partly matched, or Surprised
- Interactive runs save `learner_snapshot.json` and a report `Learner Snapshot` section with final slider, live status, playback, and nudge state
- Interactive runs save replayable `learner_tuned_config.yaml` files and a report `Replay Tuned Config` section
- Learner menu scenario cards enable `Replay` only when the latest run has `learner_tuned_config.yaml`
- Learner menu preset labels and purpose summaries for interactive cards, including preset-name and preset-purpose search
- Learner menu preset comparison hints for interactive cards, including preset-comparison search
- Learner menu scenario cards show latest preset comparison evidence after interactive runs with quick presets
- Learner menu Explore filters for Intro, Build, Deep dive, hands-on, comparison, PID, 2DOF, Panda, wall, and singularity scenario discovery
- Learner menu scenario cards show readable `Badges` for hands-on, compare, PID, 2DOF, Panda, wall, singularity, trajectory, Cartesian, tuning, and dynamics modes
- Learner menu and CLI setup diagnostics through `python -m mclab doctor`
- Learner menu scenario readiness checks that disable run buttons when config or model assets are missing
- Learner menu scenario history labels and per-scenario latest-report buttons
- Learner menu scenario, batch, and learning-path plot buttons that open the latest prioritized plot when one exists
- Learner menu scenario and batch cards show `Plot review` guidance for the latest prioritized plot
- Learner menu scenario, batch, and learning-path `Worksheet` buttons that open the latest `worksheet.md` when one exists
- Learner menu bottom bar includes `Open latest worksheet` for the most recently completed run or batch
- Learner menu refreshes batch history, report, and plot state after comparison runs complete
- Learner menu scenario evidence labels for latest observation markers, predictions, learner notes, and pending outcome review
- Learner menu and outputs index latest-evidence summaries flag missing prediction outcome review
- Learner menu and outputs index latest-evidence summaries split multi-part learner notes into `Note evidence` items
- Learner menu and outputs index show an `Observation flow` summary from first marker state to latest marker state
- Learner menu and outputs index show an `Observation next step` cue for missing predictions, notes, outcomes, or review-ready markers
- Learner menu and outputs index show `Milestones` progress for 1D Dynamics, PID Control, 2DOF Control, Panda Manipulation, and Course Compare
- Recommended learning path progress in the menu and outputs index requires prediction-bearing observation markers for hands-on steps
- Recommended learning path cards show a `Done when` completion criterion for auto, hands-on, and batch steps
- Recommended learning path summary flags completed hands-on steps that still need prediction outcome review
- Recommended learning path summary shows the next action plus prediction/compare and watch cues before launch
- Recommended learning path includes a Lab03 condition-aware DLS singularity step before moving to Panda
- Learner menu scenario value previews for key YAML parameters, searchable from the menu
- Learner menu, interaction panel, and run report reflection questions, searchable from the menu
- Learner menu, interaction panel, and run report prediction prompts, searchable from the menu
- Interaction panel marks whether an observation includes prediction-bearing learning-path evidence
- Learner menu scenario follow-up guidance and `Next` buttons for guided comparison flow
- Learner menu scenario-to-batch comparison guidance and `Compare` buttons
- Learner menu batch readiness checks that disable unavailable comparison launches
- Learner menu batch history labels and per-batch latest-report buttons
- Learner menu learning-path step report buttons for completed course steps
- Learner menu learning-path step `Worksheet` buttons for completed course steps with saved review artifacts
- Learner menu learning-path step `Replay` buttons for latest replayable `learner_tuned_config.yaml` runs
- `python -m mclab doctor` checks learner menu scenario and comparison-batch readiness
- Run reports include suggested next-run cards with reflection questions, key parameter changes, and ready-to-run commands for every guided config
- Run reports and worksheets show `Course Position` with the matching milestone, learning-path step, focus, completion rule, and repeat command
- Run reports include a top-level `Next Actions` shortcut section for evidence review, priority plot opening, tuned replay, suggested next run, and comparison batch
- Run reports include a `Control Surface` section and suggested-run control summaries for available buttons, sliders, presets, learner-control credit, and evidence controls
- Run reports include a relevant comparison batch command for the current lab or Panda wall/reach mode
- Observation markers capture the active learning question, learner predictions, evidence prompt, learner notes, changed sliders, full slider snapshots, and live status snapshots
- Run reports show hands-on evidence completion status for interactive runs
- Run reports summarize observation marker questions, predictions, prediction outcomes, learner notes, and prediction-review prompts
- Run report review prompts surface the latest `Learner note evidence` items before the individual marker cards
- Run reports and worksheets split semicolon-separated learner notes into `Learner note evidence` items for easier review
- Run reports and worksheets include an `Observation Timeline` that compares marker time, prediction, outcome, challenge proof, note evidence, and live status in order
- Run reports show an evidence review cue that counts review-ready prediction-observation pairs and incomplete markers
- Run reports and generated `worksheet.md` artifacts show run-level `Done when` completion criteria plus prediction outcomes, pending outcome review, notes, live status, key parameters, priority plot review prompts, checklist prompts, suggested next experiments, and comparison batch commands
- Outputs index learning path cards include evidence status, latest evidence summaries, latest report/worksheet/priority-plot/replay links, and ready-to-run or repeat commands for each course step
- Outputs index learning path cards show `Done when` completion criteria matching the learner menu
- Outputs index learning path cards show `Start steps` launch sequences matching the learner menu, including concrete required-preset order when configured
- Outputs index learning path cards show `Counts as control` learner-control criteria for hands-on configs
- Outputs index batch learning-path cards include the same `Prediction check` cue used by the learner menu
- Outputs index learning path summary flags evidence-pending and outcome-review-pending hands-on steps
- Outputs index learning path cards show prediction/compare and watch cues before each ready-to-run or repeat command
- Outputs index progress snapshot includes an evidence quality card with prediction outcome coverage and outcome mix
- Outputs index progress snapshot includes a mission review queue with ready/pending totals, evidence gap counts, and the next review link
- Learner menu top panel includes the same review queue summary, an `Open next review` button for the next pending run, and an `Open review queue` button that regenerates `outputs/index.html`
- Outputs index run table summarizes observation, prediction, outcome, and learner note evidence per saved run
- Outputs index run table and learning-path cards summarize latest hands-on activity mix before opening individual reports
- Outputs index run table and learning-path cards summarize `Mission evidence` proof status and next proof step per saved run
- Outputs index run table shows the latest observation marker prediction, outcome, note, and live status summary per saved run
- Outputs index run table links directly to each run's `worksheet.md` when available
- Outputs index run table links replayable `learner_tuned_config.yaml` files when available
- Outputs index run table links directly to each run's prioritized plot images
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
- condition-aware DLS singularity comparison with automatic damping schedule logging/plotting
- early/default/late condition-aware DLS schedule comparison configs for Lab03
- inner/edge target-position condition-aware DLS comparison configs for Lab03
- upper/lower path condition-aware DLS comparison configs for mirrored IK-branch lessons
- shoulder/elbow/staggered disturbance condition-aware DLS comparison configs for recovery lessons
- low/high torque-limit condition-aware DLS comparison configs for Lab03
- slow/fast command-speed condition-aware DLS comparison configs for Lab03
- low/high joint-speed-limit condition-aware DLS comparison configs for Lab03
- direct/inward retargeting-path condition-aware DLS comparison configs for Lab03
- standard logs and plots for joint position, end-effector position, torque, current proxy, and error

Remaining likely extension:

- richer condition-aware task-control comparisons, such as adaptive speed schedules under changing targets

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
- low/high damping wall comparison using fixed stiffness to isolate damping effects
- slow/fast approach wall comparison using hand speed and damping-force metrics
- shallow/deep target-push wall comparison using target-wall gap, penetration, and force metrics
- contact-cycle wall comparison using Cartesian waypoints and contact/release episode metrics
- low/high retreat-gain wall comparison using fixed wall force settings to isolate target retreat
- interactive wall position/stiffness/damping/retreat tuning
- viewer visual guides for target point, current hand point, contact hand point, wall-force direction bar, and wall plane
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
