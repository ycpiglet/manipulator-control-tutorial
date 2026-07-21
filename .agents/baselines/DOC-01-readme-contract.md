# DOC-01 — Bilingual Newcomer README Contract Evidence

- Updated: 2026-07-21 KST
- Status: **PASS — EXACT-HEAD AND POST-MERGE 6/6 VERIFIED**
- Candidate branch: `agent/readme-contract-gates`
- Exact base: `6a6632ab97c018779da8a0e404529db43a7706ca`
- Exact candidate commit: `74a77393761025462c3dcdea0c2bfcdfe62b315b`
- Pull request: [#49](https://github.com/ycpiglet/manipulator-control-tutorial/pull/49)
- Merge commit: `66eca7f666409336a6b9a6052828b3ae1c8b68d7`
- Merge tree equals source-head tree: **yes**
- Real learner outputs modified: **no**

This record closes DOC-01 after three independent read-only reviews, all six
required checks on one exact candidate head, merge through the active main
ruleset, and the same six checks on the merge commit. It does not declare B2,
change course-completion semantics, authorize cleanup apply, or approve a
public or signed distribution.

## Objective and Scope

DOC-01 makes the newcomer documentation a reproducible contract instead of a
manual convention. It covers the Korean and English README information
architecture, public commands and CLI shape, local links and anchors,
cross-platform source launchers, the repository map, and the files promised by
the automated quickstart.

The implementation intentionally does not move directories, remove legacy
launcher paths, change configs or models, rewrite the immutable readiness audit,
or touch the real `outputs/` tree. Repository restructuring remains deferred to
IA-00 after B2.

## Contract Delivered

- `README.md` and `README.en.md` share nine ordered semantic H2 sections,
  reciprocal language links, the same public command sequence, and the same
  required local targets.
- The automated quickstart names evidence-bounded success criteria and an exact
  core artifact set. Cleanup apply remains explicitly outside that quickstart
  and requires separate owner review and authorization.
- `.agents/validation/check_readme_contract.py` is a standard-library-only
  fail-closed checker for headings, commands, CLI hierarchy/options/arguments,
  runtime parsing, files, launchers, repository rows, links, anchors, and the
  supported one-line Markdown-link grammar.
- `docs/repository_structure.md` records the current no-move inventory,
  compatibility launchers, internal paths, deferred decisions, and rollback
  boundary.
- CI runs the static contract before package installation, the installed
  runtime CLI contract on Python 3.11, and the runtime contract again at the
  Python 3.10 floor.
- The desktop matrix invokes the actual recommended Windows, Linux, and macOS
  launcher with `--setup-only`, then verifies doctor, runtime README commands,
  the app self-test, Lab01, every README core artifact, and at least one real
  plot file.

## Local Validation Evidence

| Gate | Result | Measurement |
|---|---|---|
| Static README contract | PASS | 25/25 metrics; 82 local links/anchors; 0 errors |
| Installed runtime CLI contract | PASS | 9/9 documented invocations; 0 argparse errors |
| Full Python 3.10 regression | PASS | 676 passed, 7 skipped, 1,113 subtests |
| Coverage | PASS | 81.02%; floor 80% |
| Focused README/artifact regression | PASS | 152 passed, 4 subtests |
| Python syntax/static portability | PASS | checker on Python 3.10 and 3.12 |
| Other repository gates | PASS | Ruff 0; citations 29/29; robotics failures 0; Action pins 14/14; workflow YAML valid; diff check clean |
| Source launcher/artifact probes | PASS | Linux recommended setup plus Lab01-Lab04 default runs in temporary roots |
| Independent reviews | PASS | newcomer truth, code boundary, and final regression/performance; no P0-P3 findings |

Frozen SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `README.md` | `44a06ee697b3912c719c014b04be640702535d5c3fddc84c748da5a7670c90f8` |
| `README.en.md` | `3f5e37fabcae9b264bf1e57247fc9a70e0234ab596dd3f63069efdc4a55fe49b` |
| `docs/repository_structure.md` | `fc292c6f27d1a313b2fcc43536b9ab6fdf34d3b4a32346b059f0738d5a32c7d8` |
| README checker | `b0098ea93cdab921bc3b61ed12a7bc746db8feabe8fb279f311e5a9752c298d7` |
| README checker tests | `9513987bce9ae14799e48c96ec52d4744b47e8e8a9a1f6b8fbb97fba05920acb` |
| Artifact verifier | `7700adafc3b41f9acf8d918924cbec6bd41c2d9791a30cd59596971b49979995` |
| Artifact verifier tests | `eb4623b7f7627803b14ebb9cb5b7639656b98e0bee3bda5a15c6c07d8924128b` |

## Exact-Head Remote Evidence

Exact candidate head: `74a77393761025462c3dcdea0c2bfcdfe62b315b`.

| Required check | Result | Evidence |
|---|---|---|
| Simulator lint and tests | PASS | [job 88574174221](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29811793935/job/88574174221) |
| Paper citation and formula gates | PASS | [job 88574174293](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29811793935/job/88574174293) |
| Paper LaTeX build | PASS | [job 88574174177](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29811793935/job/88574174177) |
| Windows desktop | PASS | [job 88574174038](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29811793927/job/88574174038) |
| Ubuntu desktop | PASS | [job 88574174075](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29811793927/job/88574174075) |
| macOS desktop | PASS | [job 88574174068](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29811793927/job/88574174068) |

The exact-head simulator recorded 674 passed, 9 platform skips, 1,113
subtests, and 80.61% coverage on Python 3.11. Its Python 3.10 floor recorded
109 passed, 6 platform skips, and 20 subtests.

## Post-Merge Remote Evidence

Merge commit: `66eca7f666409336a6b9a6052828b3ae1c8b68d7`.

| Required check | Result | Evidence |
|---|---|---|
| Simulator lint and tests | PASS | [job 88575223249](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29812128233/job/88575223249) |
| Paper citation and formula gates | PASS | [job 88575223262](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29812128233/job/88575223262) |
| Paper LaTeX build | PASS | [job 88575223332](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29812128233/job/88575223332) |
| Windows desktop | PASS | [job 88575222763](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29812128189/job/88575222763) |
| Ubuntu desktop | PASS | [job 88575222814](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29812128189/job/88575222814) |
| macOS desktop | PASS | [job 88575222804](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29812128189/job/88575222804) |

The post-merge simulator repeated 674 passed, 9 platform skips, 1,113 subtests,
and 80.61% coverage on Python 3.11; the Python 3.10 floor repeated 109 passed,
6 platform skips, and 20 subtests.

## Compatibility, Rollback, and Residuals

All public paths remain in place. Root `run_mclab.cmd`, `run_lab*.cmd`,
`run_batch*.cmd`, and `run_all_batches.cmd` remain compatibility paths;
`run_all.ps1` remains explicitly internal. If the documentation gate proves
falsely blocking, revert the focused DOC-01 merge through the protected-main
PR flow instead of moving paths or weakening thresholds.

GitHub-hosted runners validate the automated source setup contract, not a
signed packaged install, arbitrary real hardware, assistive technology, or
newcomer comprehension. Those claims remain in later G2-G4 gates. Existing
pinned Actions that declare Node 20 continue on GitHub's Node 24 compatibility
path and remain a SUP-01 residual.

The next single implementation action is COMP-01 from a fresh clean worktree
based on the fetched latest `origin/main` containing this merge commit. It must
add a read-only canonical completion evaluator, versioned reasons, and
legacy/golden contract fixtures without rewriting saved manifests or changing
consumer behavior; COMP-02 follows in a separate PR.
