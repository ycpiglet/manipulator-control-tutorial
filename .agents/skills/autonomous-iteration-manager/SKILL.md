---
name: autonomous-iteration-manager
description: Run a self-improving work loop for coding, paper writing, documentation, simulation, and product operations. Use when Codex should plan, execute, validate, record state, learn from failures, and repeat without losing context.
---

# Autonomous Iteration Manager

## Loop

Use this loop unless the user asks for a one-off answer:

1. Frame the goal, constraints, affected artifacts, and success metrics.
2. Inspect current state before editing.
3. Choose the smallest useful next iteration.
4. Implement the change.
5. Validate with measurable checks.
6. Record results, decisions, artifacts, and remaining risks.
7. Decide: stop, repeat, hand off, or ask the user.

## Iteration Record

Each iteration should leave enough state for another agent to continue:

- Goal and scope.
- Files or artifacts changed.
- Commands run and exit results.
- Metrics before and after when available.
- Decisions made and why.
- Open risks, blockers, and recommended next step.

## Stop Conditions

Stop or request user input when:

- The success metric is met.
- Three consecutive iterations fail for the same cause.
- The next action would delete, publish, spend money, expose secrets, or change scope.
- Evidence shows the requested path conflicts with repository rules.

## Quality Bar

Do not count an iteration as complete because prose was produced. Count it as complete only when the artifact exists, the check ran, or the blocker is documented with evidence.
