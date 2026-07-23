# Educator and novice pilot protocol

## Status and authorization boundary

**Status: not run. Authorization: not authorized.** This file is a
repository-only protocol draft for EDU-01A. It is not evidence that a pilot,
accessibility study, educator adoption test, or G4 validation occurred.

Do not recruit or contact participants, collect consent, schedule a study, or
record participant data until the repository owner explicitly authorizes that
separate work and the responsible owner or institution resolves:

- consent and any institutional-review requirement;
- the participant and educator coordinator;
- storage location, access, retention, export, and deletion for pilot data;
- the supported real-device and assistive-technology matrix.

EDU-01A can make this protocol reviewable, but actual execution belongs to
HUM-01 after its prerequisites and a fresh explicit authorization.

## Purpose

The future pilot would test whether a newcomer can understand and complete the
core predict → manipulate → observe → replay flow, and whether an educator can
prepare and run Lab01 using only repository guides. It would not test robot
hardware, clinical safety, or industrial digital-twin accuracy.

## Required sample and roles

- One fixed primary cohort of exactly **6 novices**, screened against an
  owner-approved definition of novice. Six meets G4's minimum sample count;
  additional participants belong to a separately reported exploratory cohort
  and are never pooled into the primary denominator.
- At least **1 educator** who did not author the guide under test.
- A named coordinator who administers consent, eligibility, identifiers,
  storage, access, retention, deletion, and stop decisions, but does not score a
  participant they coached.
- A named observer-assessor who starts/stops the timer, records hints and
  checklist results, and applies the frozen binary rules below. The assessor
  must not be the guide author and must not provide directive help.
- A named data custodian responsible for access logs, approved aggregate export,
  the retention deadline, and deletion confirmation. One person may hold the
  coordinator and custodian roles if the approved plan permits it.

Recruitment counts are currently zero. No individual has been contacted or
enrolled by this repository work.

## Frozen test materials

Before an authorized session, record the exact commit and freeze:

- `docs/educator_guide.md` and `docs/educator_kit.json`;
- the Korean and English newcomer READMEs and installation guide;
- the learning-path commands/configs and applicable dependency locks;
- the application/package identity used on each device;
- the anonymous observation sheet, hint taxonomy, SUS form, and issue-severity
  definitions approved for the study.

The primary novice task is frozen to these exact targets and commands:

```text
lab01.default
python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot --plots essential --open-report

lab01.interactive-pull
python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml --viewer --realtime --pause-at-end --plot --plots essential --open-report
```

The educator task uses the same two target IDs and commands. Any command,
target, completion rule, prompt, timer rule, or checklist change creates a new
protocol version and requires a new cohort; it is not an in-session repair.

Do not silently edit a guide or repair a machine during a measured task. Record
the deviation, stop or restart under the approved protocol, and keep cohorts
separable.

## Novice procedure

The owner or institution must approve the exact participant-facing wording and
collected fields without changing these measurement rules:

1. Give the participant only the frozen newcomer entry point and explain the
   think-aloud method without teaching the product flow.
2. Start a monotonic timer when the assessor says “begin” and exposes the frozen
   newcomer entry point. Setup, environment activation, command discovery, and
   the `lab01.default` run are inside the timed interval.
3. Stop the timer when the participant first opens a **valid Lab01 default
   report**. Valid means the trusted repository reader accepts one manifest-v1
   record for target `lab01.default`, its status is exactly `completed`, it has
   at least one trusted plot, `report.html` is digest-valid, and the canonical
   completion decision is complete. A missing report or any unmet condition is
   not assigned an invented time and fails the novice-sample gate.
4. Ask the participant to run target `lab01.interactive-pull`. Score core flow
   as pass only when one independently saved run satisfies every item: canonical
   hands-on completion; a prediction recorded before the first counted learner
   control; at least one counted button, slider, or preset action; one correlated
   observation marker containing prediction and note; report review; and a
   correct identification of replay when a tuned config exists or rerun from
   the controlled config otherwise.
5. Record every hint. A non-directive hint may repeat or clarify the task but
   must not name the next button, command, parameter, evidence location, or
   answer. Core-flow success allows zero or one non-directive hint and no
   directive hint.
6. Score comprehension as pass only when the participant explains all four
   frozen items in their own words and ties them to saved evidence: **predict**
   is a testable pre-run claim; **manipulate** is an attributable controlled
   change; **observe** is evidence used to judge the claim; **replay or rerun**
   repeats the saved tuned state when available or repeats the controlled config
   and correctly distinguishes the two paths. Partial or prompted explanations
   fail this binary measure.
7. Administer the unchanged standard 10-item System Usability Scale and its
   standard 0–100 scoring. A missing item or participant total fails the primary
   SUS gate; it is not imputed as zero or omitted from the mean.
8. Record issues without names or free-form identifiers; stop on a safety,
   privacy, or severity-1 condition.

## Educator procedure

Give the independent educator only the repository guides and approved test
machine. Educator adoption passes only if, without author assistance, the same
educator completes every frozen checklist item:

1. identifies the Lab01 automatic and interactive target IDs and exact commands;
2. states a learning objective and a predict–manipulate–observe–replay activity;
3. prepares and successfully runs both frozen Lab01 commands;
4. finds the trusted manifest, priority plot, report, and worksheet;
5. correctly separates canonical completion from educator-review evidence,
   including pending outcome review; and
6. correctly states that a headless fallback cannot earn hands-on credit or
   prove accessibility.

Record the binary checklist, questions, hints or assistance, and guide defects.
Do not count the guide author or anyone receiving author assistance as the
independent educator success.

## Severity taxonomy

- **Sev1:** actual or credible risk of harm; unauthorized participant contact,
  data collection, access, disclosure, retention, or deletion failure;
  destructive learner-output loss; or a false authorization/G4/completion claim.
  Stop the session immediately and keep the finding unresolved until the owner
  and responsible institution approve its disposition.
- **Sev2:** on the frozen supported setup, a defect that blocks the first valid
  report, canonical core flow, educator checklist, or assessed accessibility
  flow; or materially directs a learner/educator to the wrong command, evidence,
  completion rule, or interpretation. Stop the affected task and require a new
  authorized cohort after correction.

Cosmetic or preference findings may be recorded below Sev2, but must not be
used to downgrade a Sev1 or Sev2 condition.

## G4-aligned pilot thresholds

The pilot portion is GO only when all of these measured results exist:

| Metric | Threshold |
|---|---|
| Novice sample | All 6 novices in the fixed primary cohort supply a recorded result (pass or fail) for every required measure; a withdrawal or missing measure fails this gate |
| Core flow | At least 5 of the fixed 6 pass every frozen core-flow item with at most one non-directive hint and no directive hint |
| First report | With valid times for all 6, the conventional median (mean of the third and fourth ordered values) is at most 10 minutes |
| SUS | With complete standard scores for all 6, the arithmetic mean is at least 68 |
| Learning comprehension | At least 5 of the fixed 6 pass all four frozen comprehension items |
| Educator adoption | At least 1 independent educator passes every frozen Lab01 adoption checklist item using only the guides |
| Severity | Zero unresolved severity-1 or severity-2 findings |

These thresholds cover only the human teaching pilot. They do not by themselves
satisfy G4. Signing, real OS/GPU/restart, 200% scaling, assistive technology,
rollback, and release-retention evidence remain separate requirements.

## Evidence record

Only after authorization, create an owner-approved, access-controlled evidence
record containing aggregate or pseudonymous fields needed for the thresholds:

- frozen commit/material identifiers and device/platform matrix;
- recruited/completed counts and protocol deviations;
- for each of the six opaque primary participant IDs: task start/stop timestamps,
  valid-report result and elapsed seconds, each binary core-flow item,
  non-directive/directive hint counts, each binary comprehension item, and the
  complete SUS total;
- each binary educator-adoption checklist item and overall result;
- anonymized issue IDs and severity/disposition;
- aggregate median, mean, and pass counts with the calculation method;
- consent/review authority, custodian, retention deadline, access list, and
  deletion confirmation.

Never commit participant notes, names, contact details, consent forms, raw
screen recordings, or learner `outputs/` to this repository. The final approved
data-handling plan must define where those records live and how they are
exported, deleted, and audited.

## Analysis and decision

The primary denominator is exactly the six enrolled novices who start the
protocol. A withdrawal, missing required measure, invalid report, or directive
hint remains in that denominator and fails the applicable sample or outcome; do
not replace the participant. Do not pool an exploratory participant, replacement
participant, prior cohort, or later fixed cohort into the primary six. Report
missing values as missing, not as passes or score zero. Separate deviations and
assisted completion from qualifying completion. Publish only approved anonymized
aggregates after separate publication authority exists.

If any threshold fails, record a pilot NO-GO, fix the teaching or product flow,
and test a new authorized cohort. Never combine old and new cohorts for the
primary thresholds; compare them only as separately labeled cohorts. A
successful pilot still cannot authorize public beta, signing, production,
release publication, or DOI work.
