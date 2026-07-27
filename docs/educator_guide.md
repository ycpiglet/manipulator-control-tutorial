# Educator guide

This guide turns the repository's recommended 12-step learning path into a
classroom plan. It is a repository-only teaching kit: the timing values are
planning estimates, not measured learner results, and no novice or educator
pilot has been run or authorized.

The machine-readable source for the exact path, outcomes, timing, canonical
completion evidence, separate educator-review evidence, and formative rubric
is [educator_kit.json](educator_kit.json). The guarded human-study procedure is
[educator_pilot_protocol.md](educator_pilot_protocol.md).

## Teaching model

Use the same loop in every lesson:

1. **Predict** one visible or measurable effect before running.
2. **Manipulate** one YAML value, live control, or required preset path.
3. **Observe** the viewer state, priority plot, and saved metrics.
4. **Replay or rerun** from saved settings and explain what the evidence does
   and does not prove.

Ask learners to change one variable at a time. A faster, larger, or smoother
response is not yet an explanation: the learner should name the changed
parameter, identify the evidence, and connect the effect to the dynamics or
controller.

## Learning outcomes

By the end of the planned sequence, learners should be able to:

- **LO-01 — 1D dynamics:** predict and explain how mass, damping, and
  stiffness change a mass-spring-damper response.
- **LO-02 — feedback:** tune PID terms and explain tracking, overshoot,
  settling, saturation, and actuator-effort tradeoffs.
- **LO-03 — kinematics and singularity:** connect joint-space and task-space
  control through the Jacobian and explain the effect of damped least squares.
- **LO-04 — manipulator interaction:** interpret Panda Cartesian tracking and
  virtual-wall target gap, penetration, force components, and retreat.
- **LO-05 — reproducible evidence:** identify the controlled config, manifest,
  report, worksheet, plot, and appropriate replay or rerun path.

The kit's `steps` links show where an outcome is introduced or practiced;
`summative_steps` identifies where the rubric can assess it with the listed
evidence. In particular, LO-05 is practiced throughout the path but is
summatively assessed at Step 12. A path link does not imply that every evidence
item for an outcome exists in every linked step.

## Before class

Use a clean supported checkout and follow [installation.md](installation.md).
Do not copy a prepared `outputs/` tree between learners. Confirm setup without
creating or deleting learner evidence:

```bash
python -m mclab doctor
python -m mclab path --all
```

For a classroom machine, also confirm that the configured output location is
appropriate for the class. The repository currently has unresolved owner or
institution decisions for pilot consent, participant coordination, pilot-data
retention/access, and the real assistive-technology device matrix. Do not
collect participant data until those decisions and the pilot itself are
explicitly authorized.

Prepare these fallbacks. If the viewer or GPU path is unavailable, use the
matching repository-only command:

```bash
python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml --headless --plot --plots essential --open-report
python -m mclab run lab02 --config configs/lab02_pid/interactive_disturbance.yaml --headless --plot --plots essential --open-report
python -m mclab run lab03 --config configs/lab03_2dof/condition_aware_dls_2dof.yaml --headless --plot --plots dls_disturbance --open-report
python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml --headless --plot --plots wall --open-report
```

These commands can provide simulation, report, worksheet, and plot material for
review, but they cannot provide counted learner-control events, live viewer
observation, or the required wall-preset path. Record those hands-on and viewer
outcomes as `not_assessed`; do not grant canonical hands-on completion from a
headless fallback.

- Review the fallback report, worksheet, and priority plot only for outcomes
  that the saved evidence actually supports.
- A headless run demonstrates the simulation and reporting path only. It does
  **not** prove viewer usability, keyboard access, 200% scaling, screen-reader
  behavior, or any other real accessibility result.
- If class time is short, stop after the current session boundary below. Do not
  mark an interactive step complete using an automatic run.
- Preserve the original YAML and use a copied config for an extension task so
  the baseline remains reproducible.

## Four-session lesson plan

The total is **210 planned minutes**. These values have not been measured with
learners and must not be reported as completion-time evidence.

### Session 1 — From free response to feedback (50 planned minutes)

| Step | Planned time | Activity | Evidence to review |
|---|---:|---|---|
| 1. Feel 1D physics | 10 min | Run the Lab01 automatic baseline and identify position, velocity, force, and energy. | Manifest, report, worksheet, priority plot |
| 2. Disturb and tune | 15 min | Predict a damping or stiffness effect; use Pull/Push, a live slider, or a quick preset; mark a prediction-backed observation. | Learner control, prediction, note, outcome, report, plot |
| 3. Close the loop | 10 min | Run the PID baseline and connect error to controller force. | Manifest, error/force plot, report, worksheet |
| 4. Tune PID live | 15 min | Predict a gain or force-limit effect, manipulate one control, and compare the observation with the prediction. | Learner control, observation marker, report, plot |

Checkpoint: learners should distinguish the plant's physical parameters from
the feedback controller's gains and cite one saved artifact for each claim.

### Session 2 — Joint space, task space, and DLS (65 planned minutes)

| Step | Planned time | Activity | Evidence to review |
|---|---:|---|---|
| 5. Move 2DOF joints | 15 min | Track shoulder and elbow targets and locate joint error and torque evidence. | Joint plot, report, worksheet |
| 6. Control the hand | 15 min | Relate XY hand error to Jacobian-transpose control. | Task-space plot, report, worksheet |
| 7. Handle singularity | 20 min | Predict near-edge behavior, use a DLS preset/slider or Shoulder/Elbow pulse, then mark the result. | Condition, damping, speed, disturbance, and torque evidence |
| 8. Compare DLS retarget | 15 min | Inspect the adaptive-speed retarget evidence and explain the speed/conditioning tradeoff. | DLS priority plot, report, worksheet |

Checkpoint: learners should explain why a small task-space command can demand
large joint motion near poor conditioning and how damping changes that demand.

### Session 3 — Panda reach and virtual-wall evidence (50 planned minutes)

| Step | Planned time | Activity | Evidence to review |
|---|---:|---|---|
| 9. Hold Panda | 10 min | Establish the neutral-hold stability baseline. | Pose/error plot, report, worksheet |
| 10. Reach in Cartesian | 15 min | Compare target, current hand position, Cartesian error, and effort. | Cartesian-reach plot, report, worksheet |
| 11. Touch virtual wall | 25 min | Predict contact/release behavior and use **Close wall → Back away → Re-enter wall** before marking the observation. | Required-preset sequence, target-wall gap, phase, force components, retreat, report, wall plot |

Checkpoint: learners should distinguish target crossing from actual wall
response and separate spring, damping, total force, and retreat evidence.

### Session 4 — Compare and defend a claim (45 planned minutes)

Run the final course comparison:

```bash
python -m mclab batch all --open-report
```

Canonical Step 12 completion requires the course report, course worksheet, and
all five completed child batch targets. The linked Prediction Check tables are
read-only prompts, not saved answers. After canonical completion, learners copy
selected prompts into an approved personal or course record, answer them,
select a priority plot, and defend one cross-lab claim. Those answers are
educator-review evidence and are not inferred from prompt availability.

## Exact learning-path commands

The commands below are the checked command contract. Automatic steps run
headless; hands-on steps open the side-panel-free viewer; the last step is a
comparison batch.

```bash
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot --plots essential --open-report
python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml --viewer --realtime --pause-at-end --plot --plots essential --open-report
python -m mclab run lab02 --config configs/lab02_pid/default.yaml --headless --plot --plots essential --open-report
python -m mclab run lab02 --config configs/lab02_pid/interactive_disturbance.yaml --viewer --realtime --pause-at-end --plot --plots essential --open-report
python -m mclab run lab03 --config configs/lab03_2dof/joint_space_2dof.yaml --headless --plot --plots essential --open-report
python -m mclab run lab03 --config configs/lab03_2dof/task_space_2dof.yaml --headless --plot --plots task --open-report
python -m mclab run lab03 --config configs/lab03_2dof/condition_aware_dls_2dof.yaml --viewer --realtime --pause-at-end --plot --plots dls_disturbance --open-report
python -m mclab run lab03 --config configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml --headless --plot --plots dls --open-report
python -m mclab run lab04 --config configs/lab04_panda/neutral_hold.yaml --headless --plot --plots essential --open-report
python -m mclab run lab04 --config configs/lab04_panda/cartesian_reach.yaml --headless --plot --plots cartesian_reach --open-report
python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml --viewer --realtime --pause-at-end --plot --plots wall --open-report
python -m mclab batch all --open-report
```

Use the application or these CLI commands to orient and review a submission:

```bash
python -m mclab path --all
python -m mclab review
python -m mclab index --open
```

There is no `mclab verify` command. Verification means checking the canonical
course status and then opening the saved evidence; it is not a single
attestation command.

## Completion and submission checks

Keep canonical completion and educator review separate:

- **Automatic canonical completion:** require a trusted manifest-v1 record with
  exact status `completed` and at least one trusted plot. The generated report
  and worksheet belong to the educator submission packet, but are not extra
  canonical `CompletionRule` requirements.
- **Hands-on canonical completion:** additionally require a counted learner
  control (button, slider, or quick preset) and one observation marker that
  contains both a prediction and a note. Step 11 also requires **Close wall →
  Back away → Re-enter wall** in order. Outcome review is post-completion
  educator evidence; a pending outcome does not make the canonical decision
  incomplete.
- **Course-comparison canonical completion:** require exact status `completed`,
  the course report and worksheet artifacts, and completed child targets
  `batch.lab01_msd_compare`, `batch.lab02_pid_compare`,
  `batch.lab03_2dof_compare`, `batch.lab04_wall_compare`, and
  `batch.lab04_cartesian_compare`.
- **Educator review:** require only the separate `educator_review_evidence`
  listed in the kit. Never infer an answered Prediction Check or defended claim
  merely because its read-only prompt exists.

For a learner submission:

1. Run `python -m mclab path --all` and note incomplete steps.
2. Run `python -m mclab review` and distinguish learner-action repairs from
   artifact-only repairs.
3. Open `python -m mclab index --open` and follow the credited report,
   worksheet, plot, and replay/rerun links.
4. Match the manifest's scenario/config identity to the claimed path step.
5. For hands-on work, confirm the saved prediction, note, counted
   learner-control event, and any required preset sequence. Record whether the
   separate post-completion outcome review is present or still pending.
6. For Step 12, confirm all five completed child batch target IDs. Treat answers
   copied to an approved personal or course record as separate review evidence.
7. Score only the evidence actually present. Use `not_assessed` when required
   evidence was not collected; do not turn missing evidence into a zero.

## Learning-outcome rubric

This is a formative submission rubric, not a canonical completion rule, G4
metric, or aggregate mastery score. Score each applicable dimension from 0 to
3. Record `not_assessed` separately when the required evidence is missing; do
not calculate a total score.

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Prediction and causal reasoning | No relevant prediction | Direction named with little causal reasoning | Testable direction connected to mostly correct dynamics/control reasoning | Testable causal claim, competing effect/tradeoff, and disconfirming evidence stated |
| Controlled manipulation | No attributable control or unjustified multi-variable change | Relevant change but effect not isolated | One controlled change or required preset path, recorded | Reproducible controlled comparison with held variables justified |
| Evidence interpretation | No relevant saved evidence | Evidence described without resolving the prediction | Relevant metric/event used to judge the prediction | Plot, observation, and comparison triangulated with uncertainty or an alternative |
| Reproducibility and reflection | Run/settings cannot be identified | Some artifacts found but config/outcome/replay distinction incomplete | Manifest, config, report, worksheet, and replay/rerun path identified | Provenance audited and a bounded next experiment proposed |

Do not average `not_assessed` as zero. Report the dimension scores alongside the
evidence links and note which learning outcomes were assessed.

Use these outcome-specific anchors when deciding whether evidence is relevant:

| Outcome | Summative evidence anchor |
|---|---|
| LO-01 | One isolated mass, damping, or stiffness change; a correctly predicted response direction; and a cited response plot or observation |
| LO-02 | One PID gain or limit change; tracking and effort evidence; and an explained speed, overshoot, saturation, or noise tradeoff |
| LO-03 | Joint/task-space evidence plus a conditioning or DLS claim tied to damping, speed, disturbance, or torque evidence |
| LO-04 | Cartesian or wall evidence that distinguishes target crossing, penetration/gap, spring/damping/total force, and retreat where applicable |
| LO-05 | Manifest/config identity, trusted report/worksheet/plot, correct replay-versus-rerun reasoning, and the Step 12 cross-lab defense |

## Accessibility and privacy boundary

The kit provides a fallback plan; it does not provide human accessibility
evidence. Automated checks and headless success cannot substitute for the real
Windows 11 + NVDA, macOS + VoiceOver, Ubuntu + Orca, keyboard-focus, low-vision,
color-vision, 200% scaling, GPU, and restart checks required later by HUM-01.

Learner notes and run artifacts can contain free text and local interaction
history. Before any authorized pilot, the owner or institution must decide
consent/review, coordinator identity, retention/access/deletion rules, and the
supported real-device matrix. Answers copied from read-only Prediction Check
prompts are participant data when collected for a study; any external personal
or course record therefore requires the approved privacy, access, retention,
and deletion plan. Until then, keep this kit repository-only and do not recruit,
contact, or collect data from participants.
