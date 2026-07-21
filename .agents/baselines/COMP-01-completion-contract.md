# COMP-01 — Canonical Completion Contract Evidence

- Updated: 2026-07-21 KST
- Status: **PASS — EXACT-HEAD AND POST-MERGE 6/6 VERIFIED**
- Candidate branch: `agent/completion-contract`
- Exact base: `8b21b2441f3bfeb652430f5f555e5f5c29706298`
- Exact candidate commit: `95e1be9069349be2c4140932f5f12b3deb99dabb`
- Pull request: [#51](https://github.com/ycpiglet/manipulator-control-tutorial/pull/51)
- Merge commit: `c742501de82a8e2500d02d501ecb492e3cf9edb4`
- Merge tree equals source-head tree: **yes**
- Real learner outputs modified: **no**

This record closes COMP-01 after independent contract and boundary review, all
six required checks on one exact candidate head, merge through the active main
ruleset, and the same six checks on the merge commit. It freezes a read-only
versioned completion decision contract; it does not connect learner-facing
consumers, rewrite saved artifacts, declare B2, authorize a real-root cleanup
dry-run, or authorize cleanup apply.

## Objective and Scope

COMP-01 gives every later completion consumer one dependency-light truth
function and stable reason vocabulary. It covers declared run status, plot,
learner-control, correlated observation/prediction/note, ordered required-preset,
and optional outcome-review facts. It also fixes deterministic handling for
missing, invalid, unsupported, mismatched, and legacy summary-only records.

Consumer wiring remains COMP-02. Desktop, learner menu, CLI, outputs index,
run reports, worksheets, and coverage/path aggregation were intentionally not
changed in this PR. No output directory, manifest, summary, interaction log,
config, model, launcher, or repository path was moved or rewritten.

## Contract Delivered

- `src/mclab/completion.py` defines immutable rule, evidence, and decision
  records under `COMPLETION_CONTRACT_VERSION = 1`.
- `evaluate_completion()` returns a complete/incomplete verdict, deterministic
  ordered reasons with stable `completion.v1.*` wire values, pending outcome
  review state, and the next required preset when applicable.
- `summarize_interaction_events()` counts only learner-control buttons,
  sliders, and presets; pause, step, playback speed, note helpers, and other
  view/evidence helpers do not satisfy learner-control evidence.
- Prediction and note evidence must occur on the same qualifying observation
  marker. Whitespace-only evidence, malformed marker values, and malformed
  event collections fail closed for rules that require interaction evidence.
- Ordered required presets preserve the existing wall lesson policy and report
  the first missing preset deterministically.
- Exact manifest status is `completed`. Missing manifests, legacy
  summary-only records, invalid schema-1 inputs, unsupported schemas, and
  scenario mismatches never become complete by inference.
- `mclab.application.catalog.CompletionRule` remains import-compatible by
  re-exporting the canonical type. Catalog rules now declare prediction, note,
  and required-preset requirements, but no consumer reads the new evaluator
  until COMP-02.
- `tests/fixtures/completion/v1_cases.json` is the immutable v1 golden fixture;
  future contract versions add fixtures instead of rewriting it.

## Local Validation Evidence

| Gate | Result | Measurement |
|---|---|---|
| Canonical contract tests | PASS | 17 passed, 1,076 subtests |
| Exhaustive truth matrix | PASS | 1,024 declared/evidence combinations |
| Focused consumer-boundary regression | PASS | 204 passed, 3 skipped, 1,840 subtests |
| Full Python regression | PASS | 691 passed, 9 skipped, 2,189 subtests |
| Coverage | PASS | 80.86% locally; floor 80% |
| Python 3.10 floor | PASS | 109 passed, 6 skipped, 20 subtests |
| Documentation contracts | PASS | README 25/25 static metrics, 82 links/anchors, 9/9 runtime CLI invocations |
| Other repository gates | PASS | Ruff 0; citations/formulas PASS; Action pins 14/14; diff check clean |
| Independent reviews | PASS | final-head local contract re-review and no-consumer-wiring boundary review APPROVE; no unresolved P0-P3 |
| Real outputs isolation | PASS | no real-root dry-run, cleanup apply, or learner-output write |

The exact-head and post-merge simulator jobs each recorded 691 passed, 9
skipped, 2,189 subtests, 80.83% coverage, and the same Python 3.10 result of
109 passed, 6 skipped, and 20 subtests.

Frozen SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `src/mclab/completion.py` | `99f761cfe87f4ac4813c36794c6f0d070219810bb68f157dea742e05d6968b08` |
| `src/mclab/application/catalog.py` | `09edd81fd3eb5c7bf354400832dfde709a98191ef84e918ba4cd5065e2f5c968` |
| `tests/fixtures/completion/v1_cases.json` | `1365e32c960af3efc2b13c32eb3029ad949743945f19e82eb0a76e5e02346951` |
| `tests/fixtures/completion/legacy_summary.json` | `5e020492eb074a986a887478ffa83d878073f48a21f34f743ab7f4d6a45f2464` |
| `tests/test_completion.py` | `23e841d8d5fdb740cf50c7d55e5e0d06a6c2b55ee0ef7715b5adf4811e9e507a` |

## Exact-Head Remote Evidence

Exact candidate head: `95e1be9069349be2c4140932f5f12b3deb99dabb`.

| Required check | Result | Evidence |
|---|---|---|
| Simulator lint and tests | PASS | [job 88652616915](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836070679/job/88652616915) |
| Paper citation and formula gates | PASS | [job 88652617013](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836070679/job/88652617013) |
| Paper LaTeX build | PASS | [job 88652616875](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836070679/job/88652616875) |
| Windows desktop | PASS | [job 88652616380](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836070606/job/88652616380) |
| Ubuntu desktop | PASS | [job 88652616058](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836070606/job/88652616058) |
| macOS desktop | PASS | [job 88652615969](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836070606/job/88652615969) |

All review conversations were resolved before merge. GitHub automated review
found two P1 issues on earlier heads and both remain part of the diagnosis
record. [The first P1](https://github.com/ycpiglet/manipulator-control-tutorial/pull/51#discussion_r3622620535)
found that `f2573dd` declared required presets before the desktop could emit
preset events; `1def99fa8b4abdcbf4eb7343b10d7d5e71e5909b` fixed it.
[The second P1](https://github.com/ycpiglet/manipulator-control-tutorial/pull/51#discussion_r3622666336)
found that this deferral weakened the existing ordered wall policy. Final head
`95e1be9069349be2c4140932f5f12b3deb99dabb` restored that policy with an
explicit COMP-02 capability invariant. Final-head local agent contract and
boundary re-reviews then approved the result with no unresolved P0-P3; formal
independent human approval remains unavailable under the recorded
single-maintainer exception. COMP-02 must expose and record the same ordered
presets on every surface before it uses the rule for completion decisions.

## Post-Merge Remote Evidence

Merge commit: `c742501de82a8e2500d02d501ecb492e3cf9edb4`.

| Required check | Result | Evidence |
|---|---|---|
| Simulator lint and tests | PASS | [job 88654130995](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836511032/job/88654130995) |
| Paper citation and formula gates | PASS | [job 88654130912](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836511032/job/88654130912) |
| Paper LaTeX build | PASS | [job 88654130962](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836511032/job/88654130962) |
| Windows desktop | PASS | [job 88654130446](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836511019/job/88654130446) |
| Ubuntu desktop | PASS | [job 88654130516](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836511019/job/88654130516) |
| macOS desktop | PASS | [job 88654130425](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29836511019/job/88654130425) |

The reviewed candidate tree and merge tree are both
`fc0ad88809fc7546c096dd6da2398f60bee324a8`.

## Compatibility, Rollback, and Residuals

Schema-1 saved manifests remain unchanged, no completion metadata is persisted,
and legacy summaries remain readable but do not silently earn completion. The
catalog import path remains compatible. If the unused canonical contract
itself proves incorrect before COMP-02, revert PR #51 through the protected-main
PR flow; do not migrate or rewrite learner artifacts.

COMP-02 must add a pinned, bounded, no-link reader that validates the complete
schema-1 manifest and actual regular evidence files before constructing
`CompletionEvidence`. It must aggregate course credit from any qualifying
historical run while retaining the latest run's diagnostics, define batch
worksheet/plot rules explicitly, handle terminal report publication timing,
and prove zero verdict mismatch across desktop, menu, CLI, index, report, and
worksheet surfaces. It must also expose and record the catalog's ordered wall
presets on every relevant interactive surface before enabling that completion
rule.

GitHub-hosted checks continue to warn that some pinned Actions declare Node 20
and are forced through GitHub's Node 24 compatibility path. That is the existing
SUP-01 residual, not a COMP-01 failure.

## Exact Next Action

Start `agent/completion-consumers` from a fresh clean worktree based on fetched
`origin/main` containing merge `c742501de82a8e2500d02d501ecb492e3cf9edb4`.
Implement COMP-02 as the only completion-consumer integration PR and prove
cross-surface verdict mismatch 0. Do not declare B2, move directories, touch
real learner outputs, run a real-root dry-run, or run cleanup apply.
