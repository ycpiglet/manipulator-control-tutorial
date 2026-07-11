# Agent Operating System

This repository uses a local-first agent operating system: each agent works in short iterations, leaves measurable evidence, and hands off with enough state for another agent or human to continue.

## Core Loop

```text
Intake -> Plan -> Implement -> Validate -> Review -> Record -> Next Iteration
```

| Phase | Lead Skill | Supporting Skills | Required Output |
|---|---|---|---|
| Intake | `project-state-manager` | `traceability-manager` | Goal, scope, constraints, affected files |
| Plan | `autonomous-iteration-manager` | `agent-collaboration-orchestrator` | Iteration plan and acceptance metrics |
| Implement | Task-specific skill | `configuration-control-manager` | Code, paper, config, doc, or artifact change |
| Validate | `measurable-validation-manager` | `test-automation-manager`, `paper-technical-reviewer` | Pass/fail table with measured values |
| Review | Domain reviewer | `security-operations-reviewer`, `paper-internal-reviewer` | Findings, risks, missing evidence |
| Record | `project-state-manager` | `change-log-manager`, `artifact-provenance-manager` | State snapshot, changed artifacts, next action |
| Repeat | `autonomous-iteration-manager` | `release-readiness-manager` | Stop, repeat, hand off, or release decision |

## Collaboration Model

Use one owner per iteration and multiple reviewers only when their responsibilities are different.

| Role | Responsibility | Typical Skills |
|---|---|---|
| Director | Defines the target, scope, and stop condition | `paper-research-director`, `project-state-manager` |
| Producer | Creates the concrete artifact | `paper-manuscript-writer`, `paper-latex-editor`, task coding agent |
| Domain Reviewer | Checks technical truth and field fit | `paper-technical-reviewer`, `paper-domain-expert-reviewer` |
| Beginner Reviewer | Checks whether an entry-level reader can follow | `paper-novice-reader` |
| Operations Reviewer | Checks release, CI, security, cleanup, and costs | `cicd-pipeline-manager`, `security-operations-reviewer`, `garbage-collection-manager` |
| Validator | Converts claims into measured checks | `measurable-validation-manager`, `test-automation-manager` |
| Archivist | Records versions, state, provenance, and decisions | `paper-version-manager`, `product-version-manager`, `artifact-provenance-manager` |

## Handoff Packet

Every non-trivial handoff should include this packet:

```text
Objective:
Current state:
Files/artifacts:
Constraints:
Acceptance metrics:
Commands already run:
Measured results:
Open risks:
Next recommended action:
```

## Iteration Rules

- Run at most one primary goal per iteration.
- Make the smallest change that can be validated.
- Prefer repository commands over invented checks.
- Do not call a task complete until evidence exists.
- Record both successful checks and checks that could not be run.
- If the same blocker appears in three consecutive iterations, stop and mark the blocker explicitly.
- PR merges require confirmed-green CI. Do not chain `gh pr checks --watch`
  immediately after `gh pr create` in one command: checks may not be
  registered yet, the watch returns "no checks reported", and the chain
  merges unguarded (observed 2026-07-06, PR #9 — harmless but wrong).
  Verify checks are listed, then watch, then merge.
- NEVER chain `gh pr merge` in the same command as `gh pr checks --watch`.
  `--watch` exits 0 when checks *finish*, not when they *pass*, so a chained
  merge fires even on failure — this merged a red PR to main (2026-07-11,
  PR #29: a launcher test failed and main went red). Watch, read the final
  pass/fail for every job, and only then issue `gh pr merge` as a separate
  command. This repo has no branch protection, so `gh pr merge` will happily
  merge a red PR — the green check is the agent's responsibility.
- When adding or editing a `*.cmd` launcher, run `pytest
  tests/test_launch_scripts.py` locally: it requires the exact single-line
  guard `if errorlevel 1 exit /b %errorlevel%` and pure-ASCII content.
- `gh pr merge --delete-branch` leaves the working tree on `main`. The very
  first command of the next iteration must be `git checkout -b <branch>`;
  committing while still on main forces a branch-move + hard-reset repair
  (observed 2026-07-06 before the M1 push — repaired without pushing to
  main, but avoid it).

## Validation Gate

Use `.agents/VALIDATION_METRICS.yaml` as the metric registry. Each task should choose the smallest relevant subset and report:

```text
Metric | Threshold | Measured value | Evidence path/command | Status | Next action
```

The registry keeps only durable, currently-enforced gates. Pass-specific
historical gates are archived in `.agents/archive/VALIDATION_METRICS_HISTORY.yaml`
and are not re-enforced.

Core gates are also enforced automatically by GitHub Actions
(`.github/workflows/ci.yml`): simulator lint/tests, paper citation and formula
checks, and the paper LaTeX build. A change is not done while CI is red.

## Skills Location

The skill definitions referenced in this document are mirrored into the
repository at `.agents/skills/<skill>/` so the operating system is
self-contained after a clone. The working copy used by the local agent harness
lives at `~/.codex/skills/`. When a skill changes, update the machine copy and
re-mirror it into `.agents/skills/` in the same iteration.

## State Record Policy

`.agents/CURRENT_STATE.md` keeps only the latest snapshot: objective, current
manuscript/simulator state, the most recent pass records, residual risks, and
the next recommended action. Older pass records move verbatim to dated files in
`.agents/archive/`. Do not let the live state file grow without bound.

## Recommended Agent Chains

For simulator code:

```text
project-state-manager -> autonomous-iteration-manager -> implementation -> test-automation-manager -> measurable-validation-manager -> change-log-manager
```

For paper/tutorial writing:

```text
paper-research-director -> paper-manuscript-writer -> paper-technical-reviewer -> paper-novice-reader -> paper-language-editor -> paper-version-manager
```

For release or demo readiness:

```text
release-readiness-manager -> cicd-pipeline-manager -> observability-sre-manager -> garbage-collection-manager -> measurable-validation-manager
```

For cleanup:

```text
garbage-collection-manager -> artifact-provenance-manager -> configuration-control-manager -> project-state-manager
```
