# SAFE-01 — Recoverable Output Cleanup Evidence

- Updated: 2026-07-21 KST
- Status: **LOCAL AUTOMATION PASS AND INDEPENDENT SCOPED GO; REMOTE EXACT-HEAD GATES PENDING**
- Candidate branch: `agent/safe-output-cleanup`
- Exact base: `41be887f21bfb476507d94a089f98c0ef72453c8`
- Exact candidate commit: **not assigned yet**
- Real learner outputs modified: **no**

This record describes an unmerged candidate. It does not authorize
`mclab clean`, does not close SAFE-01, and is not B2 evidence. The candidate
must receive an exact commit, independent review, all six required exact-head
checks, the remote three-OS desktop matrix, merge through the active ruleset,
and post-merge verification before SAFE-01 can pass.

## Objective and Scope

SAFE-01 replaces direct recursive deletion with a fail-closed planner and a
recoverable quarantine flow. It covers bulk CLI retention cleanup and the Qt
single-result management action. It does not change course-completion
semantics, dependency locking, release retention policy, or B2 status.

## Safety Contract

### Root and selection boundary

- The requested output root must exactly match the configured canonical MCLab
  data root. Filesystem roots, home/project/temp roots and their ancestors,
  mounts, symlinks, junctions, and reparse components are rejected.
- The lexical root chain is opened without following links and held for the
  operation. Root, quarantine, receipt, and `entries/` access stays relative to
  pinned descriptors on POSIX and pinned ancestor/root handles on Windows.
- Bulk cleanup considers only physical direct child directories. Internal and
  reserved names, preserve markers, links/reparse points, invalid entries, and
  legacy summary-only directories are skipped.
- Bulk and single-result eligibility require a strict schema-version-1
  `manifest.json`. `schema_version` must be the JSON integer `1`; booleans,
  strings, and other values are rejected. Eligibility also requires a
  terminal `completed`, `stopped`, or `error` status, timezone-aware start and
  finish times with `finished_at >= started_at`, a valid resolved config, and
  safe relative artifact paths. A present but invalid manifest never falls
  back to a legacy summary, and legacy, incomplete, or `running` results are
  never quarantined.
- Retention order uses normalized UTC `finished_at` with a deterministic name
  tie-breaker; folder name and modification time do not decide recency.

### Intent and execution boundary

- `python -m mclab clean` is read-only by default and prints a deterministic
  plan ID. `--yes` by itself never changes a file.
- Bulk apply requires the unchanged dry-run identity and both
  `--apply PLAN_ID` and `--yes`. The planner and root/run identity tokens are
  rechecked immediately before movement; stale or changed plans fail closed.
- Planning, quarantine, and restore take one fail-fast physical-root operation
  lock. Receipt listing marks otherwise recoverable entries `busy` while a
  cleanup or restore owns that lock; a busy receipt cannot be restored.
- Selected runs are renamed into `.mclab-trash/<receipt-id>/entries/`; they are
  not recursively or permanently deleted. A receipt records the exact mapping.
- Every forward quarantine and restore rename rechecks the source's captured
  physical identity at the mutation boundary. POSIX holds a source descriptor,
  verifies the post-rename destination identity, and safely reverses an
  unexpected moved object when possible. Windows verifies the expected
  volume/file ID on the same delete-capable source handle used for its
  no-replace rename. An ambiguous committed move remains staged and
  recoverable instead of being reported as untouched.
- `--list-trash` reports full receipt history plus each current state;
  `--restore RECEIPT_ID` accepts only entries marked `restorable` and restores
  one receipt as a unit. Name collisions preserve both copies instead of
  overwriting either one.
- Staging and final-receipt failures trigger rollback. Receipts in `staging`,
  `rollback_failed`, or `restore_rollback_failed` states remain recoverable,
  including partially distributed entries after process interruption.
- Stable root identity is separate from inventory freshness: permission-only
  changes do not orphan receipts, while all direct-child classification and
  metadata changes invalidate an old plan. Receipt reads and writes share a
  2 MiB limit, quarantine and restore preflight the worst-case future payload
  before moving anything, and rollback verifies recorded identities before and
  after each reverse move.

### Qt single-result boundary

- The result-management dialog requires the exact visible folder name as typed
  confirmation and checks a stale identity token before movement.
- Legacy, incomplete, running, unknown-status, changed, or preserve-marked
  results are rejected. The dialog closes only when the backend confirms
  successful quarantine.
- The confirmation field is at least 44 px high, exposes the complete target
  through its accessible name, and has a visible focus ring; the prompt wraps
  long names anywhere instead of clipping them.

### Writer publication boundary

- New run and batch writers claim a unique output directory. An explicit
  non-empty directory is never reused; an explicit empty run directory is
  claimed atomically so concurrent writers have exactly one winner.
- Run writers expose `running` first, write data, plots, learner artifacts, and
  the report, then publish the strict terminal manifest last. A report failure
  leaves the run retryable as `running`; a finalized logger rejects later
  writes. Batch failures publish a hashed strict `error` manifest only after
  synchronous writers stop, while a failed completed-manifest write remains
  fail-closed rather than being rewritten.
- Standalone comparison batches follow the same terminal-last contract. The
  Qt parent treats any persisted strict terminal status as authoritative, so a
  late cancel cannot turn saved `completed` evidence into a `stopped` UI state.
- Desktop all-batch launch uses a 256-bit one-shot token. Its SHA-256 is stored
  in the running manifest; regular-file and link/reparse checks plus an atomic
  active-directory claim prevent duplicate or aliased writers. The token file
  is consumed on claim and the active claim is released before terminal
  publication.

## Local Validation Evidence

| Gate | Result | Measurement |
|---|---|---|
| Python 3.12 full regression | PASS | 528 passed, 6 skipped, 1,109 subtests |
| Python 3.12 coverage | PASS | 80.92% total, 89% `src/mclab/output_cleanup.py`; floor 80% |
| Python 3.10 cleanup/CLI regression | PASS | 109 passed, 5 platform-only skipped, 20 subtests |
| Relevant Qt audit | PASS | 18/18 XCB cases; final exact-head remote rerun required |
| Ruff | PASS | 0 findings across required scopes |
| Workflow Action pin scan | PASS | 14/14 immutable references |
| Compileall | PASS | no compile errors |
| Whitespace/diff check | PASS | `git diff --check` clean |
| Real outputs isolation | PASS | repository's actual `outputs/` tree was not modified |

The 18 relevant Qt cases cover Korean result management, English at 200%,
wrong and exact confirmation, focus return, successful quarantine, running
batch/session guards, replay/rerun backend guards, and cleanup of an unrelated
saved run while a batch is active. They also cover keyboard retry after a
completed evidence run, including one-shot explicit-output consumption across
restart. The relevant runs reported no unnamed, undersized, or clipped
controls.

The local UI screenshots and JSON were generated under a temporary XCB display;
they are not durable release evidence. The SAFE-01 PR uses isolated Xvfb/X11
for the Linux dialog/window audit and must regenerate durable exact-head CI
evidence. Other desktop self-tests and builds remain offscreen.

## Threat and Fault Coverage

The regression set includes mixed eligible/internal/legacy/invalid children;
case-insensitive reserved names; broad roots and ancestors; root and child
symlinks; Windows reparse/junction guards; malformed, oversized, changing, and
unsafe manifests; exact-integer schema rejection including booleans; legacy,
incomplete, and running selection rejection; timezone and retention ordering;
plan/root/run staleness;
`--yes` without apply; staging, rollback, final-receipt, restore, and partial
interruption failures; corrupt receipts; restore collisions; and Qt typed
confirmation and active-session guards. Writer tests cover explicit-path reuse,
concurrent empty-directory claims, report failure and retry, terminal-last
publication, finalized-writer rejection, one-shot batch handoff races, late
cancel and process-error callbacks, and standalone completed/error batch
manifests.

Metadata reads are size-bounded and use descriptor/handle identity checks plus
no-link rooted access. Windows reparse attributes and volume/file IDs are
checked separately. The contract is designed for local filesystems on the
supported desktop platforms. Local Linux evidence exists; APFS and NTFS remain
pending until the exact-head macOS and Windows gates pass. Power-loss durability
beyond the underlying filesystem guarantee and network filesystems such as
NFS/SMB are outside SAFE-01; process-interruption recovery is in scope.

## Known Residuals

- Receipt listing is a read-only snapshot. An operation that starts just after
  its lock probe can make the displayed `restorable` label briefly stale, but
  restore takes the physical-root lock again and fails safely rather than
  moving data concurrently.
- One malformed receipt currently aborts the full list instead of returning an
  isolated `unsafe` row. This is fail-closed and does not delete data, but a
  future operability change should expose the corrupt ID without hiding valid
  history.
- Windows volume/file IDs, ancestor rename blocking, and the Xvfb workflow
  package set still require the remote exact-head platform gates. Local Linux
  evidence cannot close those platform contracts.
- A same-privilege hostile process is not required to honor the cooperative
  operation lock. The implementation pins and rechecks identities and records
  indeterminate post-commit moves conservatively, but it cannot make the final
  instruction boundary immune to arbitrary concurrent namespace mutation.
- The Windows target is the intended desktop NTFS contract, pending the remote
  exact-head Windows gate. ReFS-specific file-ID
  semantics are not claimed by SAFE-01 and require a separate platform contract.
- Abrupt batch-process termination can leave a running partial directory and
  internal handoff/active markers. Strict cleanup rejects that directory; a
  future recovery UX may classify and repair it without weakening eligibility.
- A failed first desktop adapter construction consumes the one-shot explicit
  output override. A retry safely uses a fresh default output instead of
  reusing the partial directory.

## Gate Status and Remaining Work

| Requirement | Status |
|---|---|
| Strict planner/quarantine implementation | local PASS |
| Mixed and fault-injection regression suite | local PASS |
| Independent final code review | scoped local GOs; no known P0/P1 in cleanup mutation, output claim, writer publication, batch handoff, or terminal callback paths |
| Exact candidate commit and PR | pending |
| Required exact-head checks | pending, 0/6 recorded |
| Remote Windows/Ubuntu/macOS validation | pending |
| Ruleset merge and post-merge main verification | pending |
| Real-root dry-run owner review | pending; only after post-merge verification and SAFE-01 PASS |
| Real-root quarantine apply | prohibited until owner reviews the same dry-run plan |

## Rollback and Recovery

- Before merge, a failed gate keeps the historical command disabled and the
  candidate is repaired or abandoned; no learner output migration is needed.
- After any real quarantine, a code regression is restored first with the
  receipt-aware SAFE exact commit. Only after identity/hash verification is the
  regression reverted through a PR; `.mclab-trash` receipts are never deleted.
- If an apply or restore fails, stop and use the recorded receipt state; do not
  manually delete staging or receipt directories.
- No real output cleanup was run while producing this evidence. The first
  real-root interaction after merge must be the default dry-run, followed by
  owner review. It must not be followed automatically by apply.

## Exact Next Action

Assign the exact candidate commit, open the SAFE-01 PR, and require the six
exact-head checks plus the three-OS desktop
matrix. Do not run `mclab clean` against the real outputs root during that
validation.
