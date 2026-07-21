# COMP-02 — Canonical Completion Consumers Evidence

- Updated: 2026-07-22 KST
- Status: **PASS — CORRECTIVE EXACT-HEAD AND POST-MERGE 6/6 VERIFIED**
- Original branch: `agent/completion-consumers`
- Original exact base: `edaeb340765b076e761f5cd23ac588dda6729ba3`
- Frozen implementation commit: `872ad7b7ce2949751873c47e7149300c4a521930`
- Reviewed functional head: `7e54f8cffad7b82408c6352a130a1a463013dfc8`
- Original exact head: `b0468ad361e5313b3634245f23b640318d84680d`
- Original pull request: [#53](https://github.com/ycpiglet/manipulator-control-tutorial/pull/53)
- Original merge: `e7e3bdbd6552daed9b6c330656e2755f07f19593`
- Original source/merge tree: `a47ac3762103dfb3a989d2fe24b4a2c009282ec7`
- Corrective branch: `agent/comp02-legacy-parity-fix`
- Corrective exact base: `e7e3bdbd6552daed9b6c330656e2755f07f19593`
- Corrective exact head: `ca7a1c9195ff1d07b2b6df9ac5adb60861428bfa`
- Corrective pull request: [#54](https://github.com/ycpiglet/manipulator-control-tutorial/pull/54)
- Corrective merge: `a2266b4f21f9a794998a98e71fa93643cacd1b64`
- Corrective source/merge tree: `a0aafbd1b067719f43168523df56dd560dd52da3`
- Real learner outputs modified: **no**

This durable record covers the original COMP-02 implementation and the
corrective PR #54 required after late PR #53 review thread
`PRRT_kwDOTF1rrM6Stevd` / `discussion_r3625355867` found a desktop raw legacy
scenario-ID reason mismatch. The corrective exact-head pair and the merge-SHA
CI run `29869552669` plus desktop run `29869552662` each completed the required
six-check set 6/6, and the originating review thread is resolved. This document
closes COMP-02 and the completion-consumer portion of G1. It does not declare B2,
accept the single-maintainer residual risk, authorize public beta, authorize a
real-root cleanup dry-run or apply, move repository directories, or approve
distribution.

## Objective and Scope

COMP-02 connects desktop, learner menu, CLI discovery and review, the cumulative
outputs index, reports, worksheets, coverage, and the learning path to the
COMP-01 canonical completion evaluator. Consumers build evidence only from a
pinned, bounded, no-link, schema-validated view of actual regular artifacts.
Invalid, unsupported, missing, redirected, changed, or partially published
evidence fails closed with the same reason on every surface.

The change also makes terminal publication immutable, repairs coherent running
or error documents before publishing their marker, defines concrete and
course-level batch completion, exposes and persists the ordered Lab04 wall
preset sequence, and treats digest-published generated worksheets as read-only.
Corrective PR #54 normalizes legacy diagnostic scenario IDs before desktop
course-progress assessment, preserving older completed credit while associating
the latest legacy diagnostic correctly and applying the same rule to
`batch.all`. It changes no saved artifact.
No model, experiment config, launcher, dependency, repository layout, or real
learner output was changed.

The `configs/`, `models/`, and `third_party/` Git trees are identical at the
COMP-02 base and final corrective merged state:

| Path | Base and final Git tree |
|---|---|
| `configs/` | `fe2cbe3a402eaf12944f20198240e99cd246780e` |
| `models/` | `0e4f3ed4da2ed9d388cc81ac2c254fcfd4842dbd` |
| `third_party/` | `b91d29b1c5a0d8916c390a78c46046162bc796c6` |

## Contract Delivered

- Strict readers pin the output root and artifacts, reject links and non-regular
  files, enforce per-file and 256 MiB cumulative limits, validate the complete
  schema-1 inventory, and rehash before returning evidence.
- Terminal completion markers are immutable. A producer cannot rewrite a
  completed or error marker, and readers never infer completion from stale
  report text or legacy summaries when a schema-1 manifest is invalid.
- Run, concrete-batch, and all-batch producers publish coherent running/error
  documents before their manifest. Recovery and retry paths either restore a
  trusted Incomplete document or leave stale Complete text untrusted.
- Desktop, menu, CLI, outputs index, report, worksheet, coverage, and path
  aggregation use the canonical evaluator and stable `completion.v1.*` reasons.
- Legacy summary diagnostic identity is normalized consistently for desktop
  Results and course progress, learner menu, historical-credit diagnostics, and
  `batch.all`; non-legacy, invalid, unsupported, future, and unknown schema-1
  identities continue to fail closed without summary fallback.
- Course credit can use any qualifying historical run while latest-run
  diagnostics stay associated with the latest run.
- Catalog-wide parity covers 78 targets, 292 surface cases, and 12 strict axes
  with zero verdict or reason mismatch.
- Lab04 virtual-wall evidence persists the actual required `Close wall -> Back
  away -> Re-enter wall` sequence. None, partial, out-of-order, and complete
  interaction sequences are proven end to end.
- Generated worksheets are digest-published course artifacts and are read-only;
  learner answers belong in personal or course notes. Legacy checkbox parsing
  remains only for historical worksheets.
- CLI cumulative-index restoration accepts only a regular file discovered
  through `lstat`, preventing unsafe replacement by a link or special file.

## Local Validation Evidence

| Gate | Result | Measurement |
|---|---|---|
| Full Python 3.10 regression | PASS | 827 passed, 7 skipped, 2,422 subtests |
| Coverage | PASS | 82.45% locally; floor 80% |
| Corrective legacy-ID parity | PASS | 7 passed, 6 subtests |
| Publication/consumer regression | PASS | 171 passed, 71 subtests |
| Application + manifest integrity | PASS | 116 passed, 1 skipped, 315 subtests |
| Manifest integrity after CI fixture repair | PASS | 11 passed |
| Catalog-wide surface parity | PASS | 78 targets, 292 cases, 12 axes, mismatch 0 |
| Documentation contracts | PASS | KR/EN H2 9/9, quickstart 2/2, public commands 19/19, links 82/0, runtime CLI 9/9 |
| Other repository gates | PASS | Ruff 0; citations/formulas PASS; robotics foundations PASS; Action pins 14/14; diff check clean |
| Independent review | PASS | corrective diff GO; no P0/P1/P2/P3 finding after follow-up |
| Real outputs isolation | PASS | temporary output roots only; no real-root dry-run or apply |

The corrective exact-head and post-merge simulator jobs each recorded 822
passed, 12 skipped, 2,420 subtests, 82.20% coverage, and the Python 3.10
minimum-version result of 109 passed, 6 skipped, and 20 subtests. The remote
Linux environment skips tests that the final local environment can execute;
both verified runs remain above the 80% coverage floor.

Frozen SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `src/mclab/completion.py` | `8781ea476f63d62b92199423dbbe2d0e57e0157ba08ffbde7423335dae5957ca` |
| `src/mclab/application/completion_progress.py` | `6bd3a8e8ad4b6400675d5fd2262266218d77c438b0cedc2d05aa08fe62625dae` |
| `src/mclab/application/presentation.py` | `5589dc74895e878133a2e571ebcff631e9883a8df83cf10847ba1be73dd9eca0` |
| `src/mclab/output_inventory.py` | `830aafe257a9ee12113424ae55681a32a1a99392655208badbe5b3c203c18e51` |
| `src/mclab/output_publication.py` | `9dcf8fbb6b05aa7ede54d13c3580acdfa68a3ac9c66a3f6cb7638c34513ab86a` |
| `tests/fixtures/completion/v1_batch_cases.json` | `d292583398b9ab1890885d2fd5d2f2ce664b3cba254fd606d8153e81049eead6` |
| `tests/test_completion_surface_parity.py` | `fae9915bf93123b3f27ec09636c23ff68b25473163a788e07f09c4d683c3f665` |
| `tests/test_completion_publication.py` | `23762d91c752b61fdc9dd43b7953c797451d3233a6e971892adecd1e836df512` |
| `tests/test_desktop_presets.py` | `b338bf8e4f5645c90bd3f2b3b9abea43539a927df166d384d53841ae9adb237f` |

## Original PR #53 Exact-Head Remote Evidence

Original exact head: `b0468ad361e5313b3634245f23b640318d84680d`.

| Required check | Result | Evidence |
|---|---|---|
| Simulator lint and tests | PASS | [job 88743722848](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29862867817/job/88743722848) |
| Paper citation and formula gates | PASS | [job 88743722866](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29862867817/job/88743722866) |
| Paper LaTeX build | PASS | [job 88743722908](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29862867817/job/88743722908) |
| Windows desktop | PASS | [job 88743722913](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29862868087/job/88743722913) |
| Ubuntu desktop | PASS | [job 88743722852](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29862868087/job/88743722852) |
| macOS desktop | PASS | [job 88743722825](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29862868087/job/88743722825) |

The functional tree was first proven 6/6 at head `7e54f8c` in CI run
`29861932148` and desktop run `29861932100`. The state-only successor head was
then tested again rather than inheriting those results. Before merge, PR #53 was
up to date and CLEAN and all six checks were green. The pre-merge read found no
review threads, reviews, or comments, but late post-merge thread
`PRRT_kwDOTF1rrM6Stevd` / `discussion_r3625355867` subsequently identified the
legacy-ID desktop reason mismatch. Therefore the original 6/6 evidence remains
valid provenance but is not sufficient to close COMP-02. Formal independent
human approval remains unavailable under the recorded single-maintainer
topology.

Two remote failures on earlier heads are preserved as diagnosis evidence:

- head `70a8902f709be0735acc48d9fe7ed688bfd8e8f3`, desktop run
  `29860812198`, Ubuntu job `88736737686`, exposed the immutable terminal
  audit-fixture error; the superseded CI run `29860812069` was canceled;
- head `de213368f5cc838ef29fcb617226d59c54dd9e43`, desktop run
  `29861312955`, Ubuntu job `88738439592`, exposed the compact-card overflow
  and focus regression after the fixture repair; the superseded CI run
  `29861312975` was canceled.

Commit `7e54f8cffad7b82408c6352a130a1a463013dfc8` corrected the compact height
and added a static contract. Replacement heads were fully revalidated.

## Corrective PR #54 Exact-Head Remote Evidence

Corrective exact head: `ca7a1c9195ff1d07b2b6df9ac5adb60861428bfa`.

| Required check | Result | Evidence |
|---|---|---|
| Simulator lint and tests | PASS | [job 88759828842](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29867670314/job/88759828842) |
| Paper citation and formula gates | PASS | [job 88759828811](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29867670314/job/88759828811) |
| Paper LaTeX build | PASS | [job 88759828833](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29867670314/job/88759828833) |
| Windows desktop | PASS | [job 88759828590](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29867670323/job/88759828590) |
| Ubuntu desktop | PASS | [job 88759828648](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29867670323/job/88759828648) |
| macOS desktop | PASS | [job 88759828731](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29867670323/job/88759828731) |

Corrective source and merge trees are both
`a0aafbd1b067719f43168523df56dd560dd52da3`. Local independent review found
no P0/P1/P2/P3 after the final helper was aligned exactly with learner-menu
legacy normalization.

## Original PR #53 Post-Merge Remote Evidence

Merge commit: `e7e3bdbd6552daed9b6c330656e2755f07f19593`.

| Required check | Result | Evidence |
|---|---|---|
| Simulator lint and tests | PASS | [job 88747678523](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29864046326/job/88747678523) |
| Paper citation and formula gates | PASS | [job 88747678543](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29864046326/job/88747678543) |
| Paper LaTeX build | PASS | [job 88747678510](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29864046326/job/88747678510) |
| Windows desktop | PASS | [job 88747678800](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29864046340/job/88747678800) |
| Ubuntu desktop | PASS | [job 88747678852](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29864046340/job/88747678852) |
| macOS desktop | PASS | [job 88747678806](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29864046340/job/88747678806) |

The reviewed candidate tree and merge tree are both
`a47ac3762103dfb3a989d2fe24b4a2c009282ec7`.

These six jobs passed but predate the late parity finding and do not substitute
for corrective post-merge evidence.

## Corrective PR #54 Post-Merge Remote Evidence

Corrective merge commit: `a2266b4f21f9a794998a98e71fa93643cacd1b64`.

| Required check | Result | Evidence |
|---|---|---|
| Simulator lint and tests | PASS | [job 88766077704](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29869552669/job/88766077704) |
| Paper citation and formula gates | PASS | [job 88766077671](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29869552669/job/88766077671) |
| Paper LaTeX build | PASS | [job 88766077685](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29869552669/job/88766077685) |
| Windows desktop | PASS | [job 88766077528](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29869552662/job/88766077528) |
| Ubuntu desktop | PASS | [job 88766077497](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29869552662/job/88766077497) |
| macOS desktop | PASS | [job 88766077550](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29869552662/job/88766077550) |

The originating PR #53 thread
[`discussion_r3625355867`](https://github.com/ycpiglet/manipulator-control-tutorial/pull/53#discussion_r3625355867)
was re-read after these jobs completed and resolved. PR #54 still had zero
reviews, comments, or review threads on the final post-merge check.

## Compatibility, Rollback, and Residuals

Schema 1 remains versioned and read-only. Existing manifests, summaries,
interaction logs, reports, worksheets, and plots are never migrated to earn
completion. Legacy summaries remain readable for diagnostics but cannot bypass
strict evidence. Invalid or future schemas fail closed. Generated worksheet
answers remain outside digest-published artifacts.

If the corrective legacy diagnostic regresses, stop COMP-02 completion and fix
or revert PR #54 through protected main; note that reverting to original merge
`e7e3bdbd6552daed9b6c330656e2755f07f19593` restores the known parity gap and
therefore is not a COMP-02 PASS state. If broader surface parity, publication
ordering, or strict evidence verification regresses, retain the COMP-01
evaluator and use a focused protected-main corrective or revert; never repair
the regression by rewriting learner artifacts. The pre-COMP-02 safe main is
`edaeb340765b076e761f5cd23ac588dda6729ba3`.

One nonblocking P2 remains:
producer payload writes before terminal publication are not all held under one
long-lived pinned publication lease. A same-user path-swap or concurrent-writer
race can invalidate those pre-terminal bytes, but the strict reader revalidates
and fails closed, so it cannot grant false completion. Treat a producer-side
long-lived lease as later hardening, not as a reason to weaken the reader. The
late legacy-ID thread is corrected, verified, and resolved; it is not an
accepted residual.

GitHub-hosted checks also warn that pinned Actions which declare Node 20 are
forced through the Node 24 compatibility path. Dependency locking, the
Menagerie checkout residual, scans, and SBOM inputs remain SUP-01 work. The
single-maintainer exception still requires exact-SHA owner risk acceptance in
the BASE-01 declaration before B2. B2 will not authorize public beta, signing,
distribution, a real-output dry-run, or cleanup apply.

## Exact Next Action

Merge this durable handoff through the protected-main gate. Then create
`agent/safe-main-baseline` from a newly fetched clean latest `origin/main`,
collect the BASE-01 evidence manifest and live governance snapshot, and keep B2
candidate until the owner gives explicit risk acceptance bound to the exact
subject and PR-head SHAs. Do not move directories or touch real learner outputs.
