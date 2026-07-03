---
name: measurable-validation-manager
description: Define and run measurable validation gates for code, simulations, papers, documentation, operations, and agent workflows. Use when a task needs numeric pass/fail criteria, metrics, thresholds, evidence, or regression checks.
---

# Measurable Validation Manager

## Workflow

1. Translate the goal into observable metrics.
2. Define the measurement source: test output, summary JSON, log CSV, report HTML, PDF build log, citation list, or manual observation.
3. Set thresholds before reading results when possible.
4. Run the lightest sufficient check first, then expand if risk remains.
5. Report pass/fail, measured values, command or artifact path, and residual risk.

## Metric Design

Good metrics are:

- Observable from an artifact or command.
- Repeatable on another machine.
- Sensitive to the failure mode.
- Cheap enough to run at the intended cadence.
- Paired with an owner and an action when they fail.

## Validation Levels

- Smoke: proves the path runs.
- Functional: proves behavior matches expectation.
- Regression: proves a known failure stays fixed.
- Quality: proves readability, documentation, layout, or learning value.
- Release: proves enough evidence exists to ship or publish.

## Output

Return a validation table with metric, threshold, measured value, source, status, and next action. If a metric cannot be measured yet, define the instrumentation needed.
