# B2 — Safe Main Declaration

- Status: **DECLARED — G1 12/12 PASS**
- Declared: 2026-07-22T11:50:57+09:00 / 2026-07-22T02:50:57Z
- Recording authority: repository readiness process under the owner's exact-SHA
  risk acceptance
- Controlled B2 subject: `ae4d40371b9a3fe4d7078822e1fc541a72defe2d`
- Controlled subject tree: `b5f4cb03abbf1e66c14c27c720c737ef2fc4f798`
- Accepted candidate head: `370b10186864e6b9e2bc73978da13671a54628de`
- Candidate/merge tree: `b2ccf3ded8cfd43f15cf24fd9871779fc09e7426`
- Candidate-record merge: `ee5b89c4116e789c35c76ec82e61d63fd56e5bc8`
- Source PR: [#56](https://github.com/ycpiglet/manipulator-control-tutorial/pull/56)
- Owner acceptance: [exact-subject/exact-head statement](https://github.com/ycpiglet/manipulator-control-tutorial/pull/56#issuecomment-5041091056)
- Machine-readable companion: [`B2-safe-main-declaration.json`](B2-safe-main-declaration.json)
- Real learner outputs modified: **no**
- Real-root cleanup dry-run/apply: **not run / not run**

This append-only record declares B2 for the controlled subject above. The
candidate records remain immutable record-creation snapshots; their pending
and null fields were not rewritten after the fact. PR #56, its check rollup,
review evidence, owner comment, merge metadata, and merge-SHA checks provide
the later evidence that closes the candidate workflow.

B2 is a safe-main **development baseline** only. It allows separately reviewed
B2-dependent work to begin under the execution plan. It is not a public-beta,
signed-distribution, release, DOI, cleanup, or repository-move authorization.

## Declaration Basis and Ordering

The decision sequence is complete and correctly ordered:

1. PR #56 final head `370b1018` passed all six required checks.
2. Independent read-only agent reviews reported P0/P1/P2/P3 `0`; GitHub Codex
   also reported no major issues on that exact head.
3. Owner `ycpiglet` accepted the documented single-maintainer residual risk at
   2026-07-22T02:20:30Z, naming the controlled subject and exact candidate
   head. This is owner risk acceptance, not formal independent human approval.
4. PR #56 merged through protected main at 2026-07-22T02:21:03Z as
   `ee5b89c4`; the accepted source tree and merge tree are identical.
5. The merge SHA passed all six required checks. The last job completed at
   2026-07-22T02:35:26Z with no main-head drift.
6. A final live governance snapshot found no drift, and this declaration was
   captured only after all of those conditions were verified.

The controlled B2 subject stays `ae4d4037`, exactly as accepted by the owner.
The later merge `ee5b89c4` is declaration-evidence provenance and contains the
candidate records; it does not replace the accepted subject.

## Final Live Governance Revalidation

A final read-only API snapshot at 2026-07-22T02:46:52Z found no governance
drift:

- exactly one active ruleset, `Protect main (GOV-01B)` (`19209773`), targets
  `main` and blocks deletion and non-fast-forward updates;
- pull requests, resolved review threads, strict up-to-date branches, and all
  six exact required checks remain mandatory; required approvals remain `0`;
- the only direct collaborator is owner/admin `ycpiglet`, and CODEOWNERS remains
  `* @ycpiglet`;
- vulnerability alerts, Dependabot security updates, private vulnerability
  reporting, secret scanning, and push protection remain enabled;
- Actions remains enabled for all actions with immutable-SHA pinning required;
  default workflow permission remains read-only and workflows cannot approve
  pull requests;
- the only bypass is repository-role ID `5`, restricted to pull requests.

## Immutable Candidate Records

The following candidate files are preserved byte-for-byte at the candidate
merge:

| File | Git blob | Content SHA-256 |
|---|---|---|
| `.agents/baselines/B2-safe-main.md` | `1f4aad89b14551e15e9ccf843786360e7dfba25d` | `6d4dfb594d9fae56af520d691c8f325169cfc7467fffcf1ad229089d3fd75e6a` |
| `.agents/baselines/B2-safe-main.json` | `403a8d604e0eb6e6f639c178d0435cd71d08d372` | `404cab59c43c3f331394f990185317180ad9b70b297a412f7bec5d84c740ac2c` |

The read-only enterprise audit is also unchanged: blob
`ac963c1041636706ef40f3a80e56e796086d0ae8`, content SHA-256
`fffc946c3597ebc3255938fcee656a29117a9cd31db1f75d8420cb0261e349ec`.

## Exact-Head Evidence

PR #56 exact head `370b10186864e6b9e2bc73978da13671a54628de`
passed **6/6** required checks:

| Required check | Evidence | Measured result |
|---|---|---|
| Simulator lint and tests | [job 88793981071](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29878466416/job/88793981071) | 822 passed, 12 skipped, 2,420 subtests; coverage 82.20%; Ruff PASS |
| Paper citation and formula gates | [job 88793981035](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29878466416/job/88793981035) | PASS |
| Paper LaTeX build | [job 88793981049](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29878466416/job/88793981049) | PASS |
| Windows unsigned development build | [job 88793980937](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29878466425/job/88793980937) | 228 passed, 17 skipped, 389 subtests |
| Ubuntu unsigned development build | [job 88793980960](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29878466425/job/88793980960) | 238 passed, 7 skipped, 394 subtests; cleanup UI 18/18 |
| macOS unsigned development build | [job 88793980939](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29878466425/job/88793980939) | 238 passed, 7 skipped, 394 subtests |

The Python 3.10 floor was 109 passed, 6 skipped, and 20 subtests. The
[final exact-head checkpoint](https://github.com/ycpiglet/manipulator-control-tutorial/pull/56#issuecomment-5040323727)
records three read-only review passes and the
[GitHub Codex exact-head result](https://github.com/ycpiglet/manipulator-control-tutorial/pull/56#issuecomment-5040275964).
The late P2 prerequisite-wording thread was corrected, replied to, and left
resolved/outdated before acceptance and merge.

## Owner Acceptance and Review Topology

Owner `ycpiglet` recorded the required statement before merge, binding both:

- subject `ae4d40371b9a3fe4d7078822e1fc541a72defe2d`;
- candidate head `370b10186864e6b9e2bc73978da13671a54628de`.

Required approvals remain `0` because the repository has one direct
collaborator. There is no formal independent human approval. The accepted
single-maintainer exception closes the one formerly pending G1
`review_topology` row; it does not weaken any downstream review or release
gate.

## Merge and Post-Merge Evidence

PR #56 used a two-parent merge commit. Its parents are the controlled subject
and accepted candidate head. Source/merge tree equivalence is **PASS**:

```text
accepted head tree  b2ccf3ded8cfd43f15cf24fd9871779fc09e7426
merge commit tree   b2ccf3ded8cfd43f15cf24fd9871779fc09e7426
```

Merge SHA `ee5b89c4116e789c35c76ec82e61d63fd56e5bc8`
also passed **6/6** required checks:

| Required check | Evidence | Measured result |
|---|---|---|
| Simulator lint and tests | [job 88815333538](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29885579962/job/88815333538) | 822 passed, 12 skipped, 2,420 subtests; coverage 82.20%; Ruff PASS |
| Paper citation and formula gates | [job 88815333483](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29885579962/job/88815333483) | PASS |
| Paper LaTeX build | [job 88815333490](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29885579962/job/88815333490) | PASS |
| Windows unsigned development build | [job 88815333496](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29885580009/job/88815333496) | 228 passed, 17 skipped, 389 subtests |
| Ubuntu unsigned development build | [job 88815333509](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29885580009/job/88815333509) | 238 passed, 7 skipped, 394 subtests; cleanup UI 18/18 |
| macOS unsigned development build | [job 88815333543](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29885580009/job/88815333543) | 238 passed, 7 skipped, 394 subtests |

The post-merge Python 3.10 floor was 109 passed, 6 skipped, and 20 subtests.

## G1 Final Assessment

The candidate record measured 11/12 G1 rows passing. All three final-head
workflow prerequisites are now complete: exact-head checks, independent
read-only review, and exact-SHA owner acceptance. Owner acceptance directly
closes `review_topology`, producing the final G1 result:

| Metric rows | PASS | PENDING | FAIL |
|---:|---:|---:|---:|
| 12 | 12 | 0 | 0 |

Known B2-scope code/config blockers: **0**. P0-01, P0-02, and P0-03 are closed
for B2. The repository-rules, security-setting, and immutable-Action portions
of P0-05 are also closed for B2. Distribution/signing and the remaining
supply-chain portions stay in downstream gates.

## Residual Risks and Authorization Boundary

The declaration carries these non-B2 or deferred risks forward:

- COMP-02 producer writes are not held under one long-lived pinned lease;
  strict readers continue to revalidate and fail closed;
- cleanup retains documented fail-closed operability/platform limitations;
- some pinned Actions emit Node 20 compatibility warnings;
- dependency lock, pinned simulator-CI Menagerie checkout, vulnerability and
  license scans, SBOM, and third-party notices remain SUP-01/LIC-01 work;
- distribution remains unsigned, with zero tags/releases and no independent
  packaged-install, signing, notarization, hardware, accessibility, or pilot
  evidence;
- no real-output dry-run was performed; cleanup apply remains prohibited.

Authorized now:

- STATE-01 as the first merge lane;
- IA-00 no-move inventory/ADR drafting in parallel, with merge after STATE-01;
- downstream work only at its declared prerequisite: SUP/INT/OPS/EDU/MAINT
  after STATE-01; IA-01 only after IA-00 GO; LIC after SUP; PKG after the
  IA/INT decisions and conditional IA-01; E2E after merged SUP and PKG.

Still not authorized:

- public beta, signed distribution, tags/releases, or DOI publication;
- a real-output cleanup dry-run or cleanup apply;
- any repository structure mutation before IA-00 GO and a separate
  compatibility PR;
- bypassing downstream exact-head checks, external decisions, real-device
  validation, or release gates.

## Next Work and Rollback

Merge STATE-01 first. IA-00 may be drafted in parallel but must rebase after
STATE-01 if it touches the same handoff files. IA-00 records a no-move inventory
and decides whether to add a compatibility shim in separate IA-01 or freeze the
current launcher paths through v0.1. It does not move files. SUP-01 is the first
technical-baseline lane; old Draft PRs #37 and #38 must never be merged
wholesale and retain their separate evidence/owner gates.

If any declaration fact proves false, stop B2-dependent merges and correct or
revert this declaration through protected main. Preserve the candidate records,
the owner comment, and GitHub run history; never rewrite learner artifacts.
The Git history and PR metadata that introduce this file are authoritative for
the declaration-record commit itself, avoiding a self-referential SHA field.
