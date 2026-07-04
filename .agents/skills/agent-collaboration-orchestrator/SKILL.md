---
name: agent-collaboration-orchestrator
description: Coordinate multiple specialized agents and skills across research, writing, code, testing, operations, and review. Use when splitting work, defining handoffs, avoiding duplicate effort, or synthesizing specialist feedback.
---

# Agent Collaboration Orchestrator

## Routing

1. Identify the work type: research, design, implementation, validation, review, release, maintenance, or cleanup.
2. Select the minimum set of specialist skills needed.
3. Give each role a bounded task, input artifacts, expected output, and validation criterion.
4. Merge outputs through a single owner who resolves conflicts.
5. Record handoff state so another agent can resume without reading the full thread.

## Collaboration Pattern

- Director: defines goal, scope, acceptance criteria, and role order.
- Producer: writes code, prose, figures, configs, or artifacts.
- Reviewer: checks correctness, clarity, safety, and missing evidence.
- Validator: runs measurable checks and reports pass/fail with numbers.
- State manager: records decisions, versions, artifacts, and next steps.

## Handoff Packet

Every handoff should include:

- Objective.
- Current state.
- Relevant files or artifacts.
- Constraints and non-negotiable rules.
- Metrics or acceptance criteria.
- Commands already run.
- Known risks and next recommended action.

## Conflict Resolution

Prefer measured evidence over preference, repository rules over generic best practice, and user intent over role-local optimization.
