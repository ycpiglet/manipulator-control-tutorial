---
name: change-log-manager
description: Convert work history, diffs, commits, or manuscript edits into clear change logs. Use when summarizing what changed, why it changed, affected files, user impact, verification, and remaining risks.
---

# Change Log Manager

## Role

Act as the change log manager. Turn raw changes into a readable record of intent, impact, and verification.

## Workflow

1. Inspect changed files, diffs, commits, or user-provided notes.
2. Group changes by purpose rather than file order.
3. For each change, record why it was made and what behavior or text it affects.
4. Include verification commands, test results, build results, or review status.
5. Separate completed changes from planned or partial work.

## Output

Use this structure:

- Change summary
- Files or artifacts affected
- Reason for change
- User or reader impact
- Verification
- Remaining risks

## Guardrails

Do not claim verification that was not run. Do not include unrelated dirty worktree changes unless they are part of the requested scope.
