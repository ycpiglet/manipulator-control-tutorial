# B2 — Safe Main Candidate Evidence

- Status: **CANDIDATE — CHECKS, REVIEW, AND OWNER ACCEPTANCE PENDING AT RECORD CREATION**
- Baseline declaration: **NOT DECLARED**
- G1 result: **11/12 PASS; review topology pending**
- B2-scope code/config blockers: **0 known**
- Captured: 2026-07-22T07:58:00+09:00 / 2026-07-21T22:58:00Z
- Frozen subject: `ae4d40371b9a3fe4d7078822e1fc541a72defe2d`
- Frozen tree: `b5f4cb03abbf1e66c14c27c720c737ef2fc4f798`
- Subject ref: `refs/heads/main`
- Candidate branch: `agent/safe-main-baseline`
- Candidate pull request: pending at record creation; GitHub PR metadata is
  authoritative once created
- Machine-readable companion: [`B2-safe-main.json`](B2-safe-main.json)
- Real learner outputs modified: **no**
- Real-root cleanup dry-run/apply: **not run / not run**

This is a conservative BASE-01 candidate record, not a B2 declaration. It
freezes the clean safe-main subject and measures every G1 row, but B2 cannot be
declared until an unchanged candidate PR head passes all six required checks,
receives independent read-only review, and the owner accepts the documented
single-maintainer residual risk for both the frozen subject and that exact PR
head. Only that exact-SHA owner acceptance closes the pending review-topology
metric row; checks and independent review are separate workflow prerequisites.
The 11/12 result counts G1 metric rows and does not imply that any of those
three prerequisites is complete. General permission to continue, a PR merge,
or an earlier owner action does not count as that acceptance.

## Scope and Promotion Boundary

BASE-01 records the current development baseline after GOV-01, SAFE-01,
DOC-01, COMP-01, corrective COMP-02, and the durable COMP-02 handoff. This PR
may change only readiness records. It does not change product code, configs,
models, workflows, packaging, dependency resolution, learner artifacts, or
repository layout.

Even after exact-SHA owner acceptance, B2 means only a safe-main development
baseline. It does not authorize any of the following:

- public beta, signed distribution, release/tag creation, or DOI publication;
- a real learner-output cleanup dry-run or cleanup apply;
- distribution claims, license/notices approval, SBOM completion, or package
  independence claims;
- directory or launcher moves before IA-00 and a separate compatibility PR;
- merging B2-dependent implementation work before B2 is actually declared.

## Frozen Subject and Cleanliness

The subject was fetched into a new worktree from latest `origin/main`, not
reused from the historical dirty checkout or a COMP-02 worktree.

| Property | Recorded value | Result |
|---|---|---|
| Commit | `ae4d40371b9a3fe4d7078822e1fc541a72defe2d` | frozen |
| Tree | `b5f4cb03abbf1e66c14c27c720c737ef2fc4f798` | frozen |
| Parents | `a2266b4f21f9a794998a98e71fa93643cacd1b64`, `1399921a3d96f8a67a8b3d3ea5a44a56c6e94685` | two-parent protected merge |
| Commit timestamp | `2026-07-22T07:16:31+09:00` | recorded |
| `HEAD == origin/main` before candidate edits | true | PASS |
| `HEAD...origin/main` before candidate edits | ahead `0`, behind `0` | PASS |
| Tracked status/index/worktree diff before candidate edits | clean / clean / clean | PASS |
| Subject tree after ignored Panda provisioning | unchanged | PASS |

The ignored MuJoCo Menagerie Panda tree was provisioned only to make local
model-integrity tests executable. It did not change tracked status or the
frozen tree. The initial diagnostic run before provisioning failed only on the
absent Panda model and is not counted as acceptance evidence; the pinned asset
was installed and all accepted focused suites were rerun.

Frozen identity reproduction uses the immutable subject directly. The clean
status row above was captured before candidate edits; the detached worktree
step reproduces that clean checkout without asking the current candidate
branch to be clean:

```bash
BASE01_SUBJECT=ae4d40371b9a3fe4d7078822e1fc541a72defe2d
BASE01_TREE=b5f4cb03abbf1e66c14c27c720c737ef2fc4f798
BASE01_REPRO_ROOT=$(mktemp -d /tmp/mclab-base01-identity.XXXXXX)
git cat-file -e "$BASE01_SUBJECT^{commit}"
test "$(git rev-parse "$BASE01_SUBJECT^{tree}")" = "$BASE01_TREE"
git show -s --format='%H%n%T%n%P%n%cI' "$BASE01_SUBJECT"
git worktree add --detach "$BASE01_REPRO_ROOT/repo" "$BASE01_SUBJECT"
test -z "$(git -C "$BASE01_REPRO_ROOT/repo" \
  status --porcelain=v2 --untracked-files=all)"
git -C "$BASE01_REPRO_ROOT/repo" diff --check
git -C "$BASE01_REPRO_ROOT/repo" diff --cached --check
git worktree remove "$BASE01_REPRO_ROOT/repo"
rmdir "$BASE01_REPRO_ROOT"
```

## Durable Handoff Provenance

PR [#55](https://github.com/ycpiglet/manipulator-control-tutorial/pull/55)
carried only the final COMP-02 evidence and active handoff into protected main.

| Property | Value |
|---|---|
| Exact source head | `1399921a3d96f8a67a8b3d3ea5a44a56c6e94685` |
| Merge commit / frozen subject | `ae4d40371b9a3fe4d7078822e1fc541a72defe2d` |
| Source and merge tree | `b5f4cb03abbf1e66c14c27c720c737ef2fc4f798` |
| Source/merge tree equivalence | PASS |
| Reviews / comments / review threads | `0 / 0 / 0` |
| Exact-head required checks | 6/6 PASS |
| Post-merge required checks | 6/6 PASS |

### Exact-head jobs

| Required check | Evidence |
|---|---|
| Simulator lint and tests | [job 88772870420](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29871635697/job/88772870420) |
| Paper citation and formula gates | [job 88772870454](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29871635697/job/88772870454) |
| Paper LaTeX build | [job 88772870379](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29871635697/job/88772870379) |
| Windows unsigned development build | [job 88772870588](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29871635771/job/88772870588) |
| Ubuntu unsigned development build | [job 88772870631](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29871635771/job/88772870631) |
| macOS unsigned development build | [job 88772870813](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29871635771/job/88772870813) |

### Frozen-subject post-merge jobs

| Required check | Evidence |
|---|---|
| Simulator lint and tests | [job 88777768364](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29873178744/job/88777768364) |
| Paper citation and formula gates | [job 88777768308](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29873178744/job/88777768308) |
| Paper LaTeX build | [job 88777768293](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29873178744/job/88777768293) |
| Windows unsigned development build | [job 88777768052](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29873178702/job/88777768052) |
| Ubuntu unsigned development build | [job 88777768079](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29873178702/job/88777768079) |
| macOS unsigned development build | [job 88777768116](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29873178702/job/88777768116) |

Both simulator jobs recorded 822 passed, 12 skipped, 2,420 subtests, 82.20%
coverage, Ruff 0, workflow pins 14/14, and a Python 3.10 floor of 109 passed,
6 skipped, and 20 subtests. The frozen-subject desktop jobs recorded Windows
228 passed, 17 skipped, 389 subtests; Ubuntu 238 passed, 7 skipped, 394
subtests; and macOS 238 passed, 7 skipped, 394 subtests. Ubuntu also passed all
18 cleanup UI audit cases. These are unsigned development-build checks, not
packaged-install or production evidence.

## G1 Assessment

| Metric | Threshold | Measured evidence | Result |
|---|---|---|---|
| Cleanup selection | valid learner runs 100%; invalid/internal/link/canary 0 | Mixed 30-child fixture selected 4/4 valid entries, at least 23 skipped, and 0 invalid/internal/link entries; 48 deterministic property cases and 16 strict mutation cases | PASS |
| Protected roots | broad roots and ancestors rejected 100% | File, home, filesystem root, repository root/ancestor, temp root, symlink parent/root, mount, macOS alias, Windows junction/handle coverage; three-OS PR #55 matrix PASS | PASS |
| Cleanup intent | default dry-run; exact plan plus `--yes`; movement before both 0 | `--yes` alone, wrong plan ID, and apply without `--yes` all produce zero movement | PASS |
| Cleanup result | selected/executed set equal; failures explicit; receipt/list/restore/interruption recover | Quarantine, rollback, collision, interruption, receipt, list, and restore tests; SAFE union 286 passed, 7 skipped, 396 subtests | PASS |
| Completion truth | declared evidence truth table 100% | Exhaustive 1,024/1,024 combinations plus immutable golden/legacy cases | PASS |
| Surface parity | verdict/reason mismatch 0 across catalog | 78 targets, 292 surface cases, 12 strict axes, mismatch 0 | PASS |
| Legacy data | existing artifact rewrite 0; deterministic reason 100% | Fixture bytes and inventory unchanged; rewrite count 0; focused legacy-ID parity 7 passed, 6 subtests | PASS |
| Repository rules | one active main ruleset; PR/conversation/up-to-date; destructive refs blocked; checks 6/6 | Live ruleset `19209773`, effective-rules read-back, exact required contexts | PASS |
| Security settings | alerts, Dependabot security updates, private reporting 3/3 | Live API 3/3; secret scanning and push protection also enabled | PASS |
| Workflow provenance | reviewed third-party references immutable 100%; checks 6/6 | 14/14 full 40-hex Action references; repository SHA enforcement true; exact/post-merge runs PASS | PASS |
| Review topology | one-maintainer exception plus exact subject/head owner acceptance recorded 100% | One direct admin collaborator; approvals remain 0; exact-SHA owner acceptance absent | **PENDING** |
| Base quality | Ruff 0, pytest failure 0, coverage at least 80% | Remote 822 passed, 12 skipped, 2,420 subtests; coverage 82.20%; local focused suites and contracts PASS | PASS |

The aggregate remains 11/12. There is no known B2-scope code/config blocker,
but the pending review-topology row is itself a B2 declaration blocker.

## Local Reproduction

Environment: Ubuntu 22.04.5 LTS, Linux 6.8.0-134-generic x86_64, Git 2.34.1,
Python 3.10.12, GCC 11.4, Bash 5.1.16, GNU coreutils 8.32, and `LC_ALL=C` for
inventory hashing. Validation used temporary root
`/tmp/mclab-base01-validation.j1QyGV`; the repository's real `outputs/` was not
used.

| Check | Result |
|---|---|
| SAFE focused union | 286 passed, 7 skipped, 396 subtests |
| Cleanup-only suite | 62 passed, 6 skipped, 16 subtests |
| Completion accepted union | 145 passed, 1,306 subtests |
| Completion plus full learner-menu expansion | 231 passed, 1,756 subtests |
| Completion core plus surface parity | 24 passed, 1,082 subtests |
| README static contract | 25/25 metrics; 82 links; 0 errors |
| Workflow Action pin scan | 14/14 PASS |
| Ruff | 0 findings |
| Diff checks before candidate edits | clean |

The following recipe avoids the historical `/tmp/mclab-comp02` environment
path. It extracts the exact frozen tree without registering another persistent
Git worktree, creates a fresh Python 3.10 environment, and installs the required
checksum-verified Panda asset. Because
SUP-01 has not produced a dependency lock, the editable install still resolves
the dependencies declared by the frozen `pyproject.toml`; that limitation is
recorded below and the durable CI runs remain the authoritative remote
environment evidence.

```bash
BASE01_SUBJECT=ae4d40371b9a3fe4d7078822e1fc541a72defe2d
BASE01_CALLER_ROOT=$(pwd -P)
BASE01_REPRO_ROOT=$(mktemp -d /tmp/mclab-base01-validation.XXXXXX)
mkdir "$BASE01_REPRO_ROOT/repo"
git archive "$BASE01_SUBJECT" | tar -x -C "$BASE01_REPRO_ROOT/repo"
python3.10 -m venv "$BASE01_REPRO_ROOT/venv"
BASE01_PYTHON="$BASE01_REPRO_ROOT/venv/bin/python"
"$BASE01_PYTHON" -m pip install -e \
  "$BASE01_REPRO_ROOT/repo[app,dev]"
cd "$BASE01_REPRO_ROOT/repo"
env MCLAB_DATA_DIR="$BASE01_REPRO_ROOT/data" PYTHONPATH=src \
  "$BASE01_PYTHON" -m mclab assets install --force
```

Accepted command groups, run after the setup above:

```bash
env MCLAB_DATA_DIR="$BASE01_REPRO_ROOT/data" PYTHONPATH=src \
  "$BASE01_PYTHON" -m pytest -q \
  tests/test_output_cleanup.py tests/test_application.py tests/test_batch.py \
  tests/test_cli_imports.py tests/test_logging.py tests/test_workflow_security.py

env MCLAB_DATA_DIR="$BASE01_REPRO_ROOT/data" PYTHONPATH=src \
  "$BASE01_PYTHON" -m pytest -q tests/test_output_cleanup.py

completion_tests=(
  tests/test_completion.py tests/test_completion_batches.py \
  tests/test_completion_cli_snapshot.py tests/test_completion_inventory.py \
  tests/test_completion_publication.py tests/test_completion_reporting.py \
  tests/test_completion_surface_parity.py tests/test_manifest_integrity.py \
  tests/test_learner_menu_completion.py tests/test_desktop_presets.py
)
env MCLAB_DATA_DIR="$BASE01_REPRO_ROOT/data" PYTHONPATH=src \
  "$BASE01_PYTHON" -m pytest -q "${completion_tests[@]}"

env MCLAB_DATA_DIR="$BASE01_REPRO_ROOT/data" PYTHONPATH=src \
  "$BASE01_PYTHON" -m pytest -q \
  "${completion_tests[@]}" tests/test_learner_menu.py

env MCLAB_DATA_DIR="$BASE01_REPRO_ROOT/data" PYTHONPATH=src \
  "$BASE01_PYTHON" -m pytest -q \
  tests/test_completion.py tests/test_completion_surface_parity.py

"$BASE01_PYTHON" .agents/validation/check_workflow_action_pins.py
"$BASE01_PYTHON" .agents/validation/check_readme_contract.py
"$BASE01_PYTHON" -m ruff check src tests scripts \
  .agents/validation
```

After preserving any desired console evidence, remove only the exact temporary
root created above. The prefix guard and `-xdev` keep this cleanup bounded:

```bash
cd "$BASE01_CALLER_ROOT"
case "$BASE01_REPRO_ROOT" in
  /tmp/mclab-base01-validation.*)
    find "$BASE01_REPRO_ROOT" -xdev -depth -delete
    ;;
  *)
    printf 'Refusing unexpected reproduction root: %s\n' \
      "$BASE01_REPRO_ROOT" >&2
    exit 1
    ;;
esac
```

## Live Governance Snapshot

Read-only API window: 2026-07-22T07:35:43+09:00 through
2026-07-22T07:37:47+09:00 (2026-07-21T22:35:43Z through
2026-07-21T22:37:47Z).

| Control | Live value | Result |
|---|---|---|
| Main ruleset | exactly one active: `Protect main (GOV-01B)`, ID `19209773` | PASS |
| Ref safety | deletion and non-fast-forward blocked | PASS |
| Pull-request rule | PR, conversation resolution, strict/up-to-date required; approvals `0` | PASS with documented single-maintainer exception |
| Admin bypass | repository-role ID 5; PR-only | PASS |
| Required checks | six exact contexts, all GitHub Actions app ID `15368` | PASS |
| Direct collaborators | exactly one: `ycpiglet`, admin | exception recorded; no formal independent human approval |
| CODEOWNERS | `* @ycpiglet` | PASS |
| Vulnerability alerts | enabled | PASS |
| Dependabot security updates | enabled and not paused | PASS |
| Private vulnerability reporting | enabled | PASS |
| Secret scanning / push protection | enabled / enabled | PASS |
| Actions policy | enabled; allowed all; `sha_pinning_required=true` | PASS |
| Workflow token | default read; workflows cannot approve PRs | PASS |

The six required contexts are:

1. `Simulator lint and tests`
2. `Paper citation and formula gates`
3. `Paper LaTeX build`
4. `Unsigned development build (windows-2025)`
5. `Unsigned development build (ubuntu-24.04)`
6. `Unsigned development build (macos-15)`

No governance drift or B2-scope governance blocker was found. The zero-approval
configuration is an explicit exception forced by the single direct
collaborator topology; it is not presented as independent human approval.

## Controlled-Item Fingerprints

Each inventory hash is the SHA-256 of one canonical `git ls-tree` invocation
for the complete path set in that row. Do not hash or concatenate separate
invocations:

```bash
LC_ALL=C git ls-tree -r --full-tree \
  ae4d40371b9a3fe4d7078822e1fc541a72defe2d -- <all-row-paths> | sha256sum
```

| Area | Entries | Git tree/blob OID | Inventory SHA-256 |
|---|---:|---|---|
| Product `src/mclab` | 113 | `2a951a41394d5021f0a0fc0c49d130be89728b5a` | `8d722c57efe216a0c015c05cd06b8e3c8a11c7a09db4973904a4a8b3c0ba38ad` |
| Configs | 78 | `fe2cbe3a402eaf12944f20198240e99cd246780e` | `b1108fd870d5368ab21afda9cdce8f1dd9d87759dab0e283fe6bb5bfcf624a99` |
| Models | 8 | `0e4f3ed4da2ed9d388cc81ac2c254fcfd4842dbd` | `1de2bc233d7f36c07c831b9a74a525a4328fee0b53f1fde002912d151b1ac052` |
| Third-party | 5 | `b91d29b1c5a0d8916c390a78c46046162bc796c6` | `fb986ed36f21f275caf0515b236ffbc41c00d74f8cd0a4bc8625d8c9d2152106` |
| Validation: `tests scripts .agents/validation .github/workflows` | 55 | tests `4e82ebbe`; scripts `48f90d2f`; validation `219e37a9`; workflows `f917ce6e` | `afa476d6ad8d78bb15f4b986ac14f8a08db5f97cf75265505130326b45bde855` |
| Distribution: `packaging pyproject.toml` | 4 | packaging `a5b1a9ec`; pyproject `5cdb5afd` | `45d3c4ab3a067f0d3d2caeb343888f4204c447747ee840118e319be25872ad00` |
| Newcomer/public contract: `README.md README.en.md docs .github/SECURITY.md .github/SUPPORT.md` | 20 | README KR `763a13b4`; README EN `43486a41`; docs `72f47481`; security `770b6640`; support `c81d8e6c` | `97e9e285c93e9c1727797a072c71e33312bbf7f1914735096f149a871fa34fb2` |
| Publication: `paper jose CITATION.cff` | 43 | paper `8afc23e0`; JOSE `54945f77`; CFF `bd41048c` | `a907013c7f35d8892078e33cb591d511416aa78a551ec3c192d18c5e8d8099e1` |
| All controlled paths above | 326 | multiple | `622cb98bba31dae38bdab0d480ccdb019afe0295f4b4245c54771ad595811ec9` |

Additional reproducibility values:

- workflow-only inventory: 2 entries,
  `b40e6b37c4d25c9563416bb055a80a5b485c68349bb3bf5eb497b6630d2e43d9`;
- `pyproject.toml` content SHA-256:
  `9feb516ebc54f9b7bc220574cc87cbc8f9013d71c15edb2b0c6ba48becc256ca`;
- dependency lock/constraints: **`N/A — SUP-01 pending`**, 0 tracked files;
- third-party notice inventory: **absent**, 0 tracked notice files; LIC-01 pending;
- `LICENSE` blob `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`, content
  `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`;
- `LICENSE-docs` blob `590b9d45401387639cb53808d8afa06dc914accc`, content
  `a0992f79d9b2ce39263b9369ed7dbdc68b40be7191636c063fc19fb3045e38d3`.

The installer in `src/mclab/application/assets.py` pins MuJoCo Menagerie commit
`71f066ad0be9cd271f7ed58c030243ef157af9f4` and archive SHA-256
`000b9f51abb404efb1de2b88b3c738674c472a85b6c4143168859abc4c98d423`.
That source file has blob `b7f4fa26711c48f00645043051759b2160d678f2`
and content SHA-256
`c4b0604dbf64a984bb56628080ef5f2fbdfb6a95ab6e80f74f21122ef2abb5fa`.
The desktop workflow uses the pinned installer. Simulator CI still makes a
shallow sparse clone of mutable Menagerie default HEAD with a static cache key;
that is a recorded SUP-01 residual, not a B2-scope closure claim.

## Enterprise-Audit P0 Disposition

The original audit remains read-only. This append-only ledger records current
gate disposition without rewriting the finding text.

| Finding | BASE-01 disposition |
|---|---|
| P0-01 unsafe cleanup | Closed for B2 by SAFE-01. Real-root dry-run/apply remains separately authorized work. |
| P0-02 completion mismatch | Closed for B2 by COMP-01 plus corrective COMP-02. Original PR #53 alone is not closure evidence. |
| P0-03 no clean baseline | Technical condition satisfied at clean `ae4d4037`; formal closure pending candidate exact-head checks/review and owner acceptance. |
| P0-04 distribution compliance/signing | Deferred to LIC/PKG/REL and G3/G4; not a B2 blocker, still blocks public beta/production. |
| P0-05 repository/supply chain | Rules, security settings, and immutable Action refs closed for B2. Lock, CI Menagerie pin, scans/SBOM, tags/releases remain SUP/REL and G3/G4 work. |

## Deferred Residuals and Rollback

Residuals that must remain visible but do not block the B2-scoped technical
baseline:

- review topology is the sole pending G1 metric row and remains open because
  exact-SHA owner acceptance is absent; exact-head checks and independent
  review are separate same-final-head workflow prerequisites;
- COMP-02 producer payload writes are not all held under one long-lived pinned
  publication lease; strict readers revalidate and fail closed (P2);
- SAFE-01 retains documented fail-closed operability/platform residuals;
- some immutable Action versions emit Node 20 compatibility warnings;
- no dependency lock, pinned simulator-CI Menagerie checkout, vulnerability/
  license scan bundle, SBOM, or third-party notices exists yet;
- the repository has 0 tags and 0 releases; distribution is unsigned and has
  not passed independent packaged-install E2E, signing, or notarization;
- no real-output dry-run was performed, and apply remains prohibited until the
  owner reviews the same exact plan and separately authorizes apply.

This candidate is documentation-only. If its evidence is wrong, close or
revert the candidate through protected main and regenerate it from a newly
fetched clean subject. If any review correction changes the candidate head,
rerun all six required checks and obtain acceptance for the new exact head. Do
not repair baseline evidence by rewriting learner artifacts. No output restore
procedure is needed because this work performed no output mutation.

## Owner Acceptance Gate

The machine-readable candidate deliberately leaves PR-head and acceptance
fields null. Embedding the current commit SHA inside the same tracked commit is
self-referential. At acceptance time, the authoritative candidate head is
GitHub `PullRequest.headRefOid`; its check rollup, an independent read-only
review record, and an owner comment on the same PR bind the decision without
changing that accepted head. A later append-only declaration record may refer
to the accepted candidate head, merge SHA, and owner comment; this candidate
record itself is never rewritten to fabricate prior acceptance.

Required owner statement, with both placeholders replaced by full 40-hex SHAs:

> I reviewed B2 subject `<main-sha>` and BASE-01 PR head `<head-sha>`. I
> acknowledge that required approvals are 0 because there is one direct
> collaborator and that no formal independent human approval exists. I accept
> the documented residual risks solely for the B2 safe-main development
> baseline. This does not authorize public beta, signed distribution,
> release/DOI publication, real-output cleanup dry-run, or cleanup apply.

Pending fields:

- accepted subject SHA: `null`;
- accepted candidate PR head SHA: `null`;
- owner actor/time/comment URL: `null`;
- candidate exact-head check runs/jobs: pending;
- independent final candidate review record: pending;
- B2 declaration and merge record: not declared / pending.

These are three distinct final-head workflow prerequisites: exact-head checks,
independent review, and exact-SHA owner acceptance. Only the acceptance closes
the sole pending G1 metric row. Checks and review are separate prerequisites;
none of the three is implied complete by the 11/12 score.

## Exact Next Action

Open the documentation-only BASE-01 candidate PR, freeze its exact head,
complete independent read-only review and all six required checks, then request
the owner statement above for the frozen subject and final PR head. Do not
merge or declare B2 before that acceptance, and do not start real-output or
B2-dependent merge work.
