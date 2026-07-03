---
name: test-automation-manager
description: Plan, write, review, and organize automated tests across unit, smoke, integration, regression, and end-to-end scopes. Use when deciding test coverage, adding test commands, reducing flakiness, or defining release evidence.
---

# Test Automation Manager

## Workflow

1. Identify the behavior under test, the risk of regression, and the cheapest reliable test level.
2. Prefer deterministic unit and smoke tests before heavier integration or viewer/manual tests.
3. Keep tests readable as executable documentation; name the condition, action, and expected result clearly.
4. Preserve existing test style, fixtures, and naming conventions.
5. Record commands that prove the change, including skipped or unavailable checks.

## Test Levels

- Unit tests: pure logic, controllers, math helpers, parsers, validators, metrics.
- Smoke tests: importability, CLI command shape, short headless runs, model loading.
- Integration tests: cross-module flows, generated artifacts, config-to-output behavior.
- Regression tests: known bug reproduction before the fix.
- Manual checks: viewer behavior, visual layout, hardware, or long-running demos that should not block fast CI.

## Quality Rules

- Avoid brittle sleeps, external network dependence, and tests that require a visible UI unless the user explicitly requests them.
- Use fixed seeds, small time horizons, and stable tolerances for simulation tests.
- Assert outputs that matter to users, not incidental implementation details.
- If a failure is flaky, isolate it and explain the likely source instead of simply relaxing assertions.

## Output

Return the added or recommended tests, the commands to run them, the risk each test covers, and any remaining blind spots.
