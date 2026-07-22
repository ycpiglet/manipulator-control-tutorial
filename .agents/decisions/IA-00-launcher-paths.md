# IA-00 launcher-path decision

| Field | Value |
|---|---|
| Status | Proposed final decision; STATE-01 is accepted and IA-00 acceptance gates remain |
| Decision | **FREEZE** the current root launcher paths through the v0.1 line and B4 |
| IA-01 | Not required while this FREEZE remains in force |
| Date | 2026-07-22 KST |
| Subject commit | `6c06de439fbee22ee2591dc47846194484cad517` |
| Subject tree | `2749c852d5eaa04676bc2654af3634b5243b650f` |
| STATE-01 source / merge | `ba74114126ff875be2f11810c5a0064f50b49000` / `6c06de439fbee22ee2591dc47846194484cad517`; source/merge tree equivalence PASS |
| STATE-01 checks | Exact-head CI `29890342037`, desktop `29890341985`; post-merge CI `29891148900`, desktop `29891148887`; required checks 6/6 PASS at both SHAs |
| Inventory | 23 tracked root launchers: 20 `.cmd`, one `.command`, one `.sh`, one `.ps1` |
| Inventory digest | SHA-256 `879ecf4613b780aaaf777f0785a506103439d06bbeaac58fd9c9a944939e6807` over the C-locale-sorted, newline-terminated path list |

## Scope and authority

This record implements the no-move IA-00 decision required by the
[readiness execution plan](../READINESS_EXECUTION_PLAN.md). Its inventory was
prepared from the B2 safe-main baseline and revalidated unchanged at the exact
STATE-01 protected-main subject above after reading the
[current state](../CURRENT_STATE.md), the
[immutable readiness audit](../reviews/20260720_enterprise_readiness_audit.md),
and the execution plan in that order.

The selected disposition is **FREEZE**: keep all 23 current root launcher
paths stable through the v0.1 line and the B4 public-beta gate. IA-01 is a
conditional compatibility implementation PR and is therefore **not required**
for this disposition. PKG-01 may proceed after this decision is accepted and
the other prerequisites in the execution plan are satisfied.

This draft began at B2 and has been fast-forwarded onto the accepted STATE-01
merge. It becomes the accepted IA-00 record only after the normal IA-00 review,
exact-head, protected-merge, and post-merge controls have succeeded. It does
not edit a handoff, move a path, or change a consumer.

The B2 acknowledgment and this IA-00 draft do **not** authorize a public beta,
signed distribution, release or DOI publication, a real-output cleanup
dry-run, cleanup apply, external contact or participant recruitment, or any
repository move. Those remain governed by their separate gates and explicit
owner approvals.

## Canonical entry points

The root files are launch adapters, not 23 independent product interfaces.
Their current canonical targets are:

| Audience | Stable entry | Canonical target |
|---|---|---|
| Newcomer on Windows | `START_HERE.cmd` | `scripts/start_mclab.py`, then `python -m mclab app` |
| Newcomer on Linux | `start_here.sh` | `scripts/start_mclab.py`, then `python -m mclab app` |
| Newcomer on macOS | `START_HERE.command` | `scripts/start_mclab.py`, then `python -m mclab app` |
| Source-installed desktop user | `python -m mclab app` | `mclab.cli:main` and the integrated Qt app |
| Source-installed experiment user | `python -m mclab run ...` | `mclab.cli:main` and the selected lab/config |
| Installed console-script user | `mclab ...` | `[project.scripts] mclab = "mclab.cli:main"` |
| Existing Windows menu user | `run_mclab.cmd` | bootstrap guard, then `python -m mclab menu` |
| Existing Windows lab user | `run_lab*.cmd` | bootstrap guard, then `python -m mclab run ...` |
| Existing Windows comparison user | `run_batch*.cmd`, `run_all_batches.cmd` | bootstrap guard, then `python -m mclab batch ...` |
| Maintainer | `run_all.ps1` | `scripts/bootstrap_and_run.py --verify` |

`python -m mclab app` and `python -m mclab menu` currently reach the same
integrated desktop application. The `app` spelling is the documented public
source entry; `menu` remains the compatibility target of `run_mclab.cmd`.
The console-script mapping is defined in [pyproject.toml](../../pyproject.toml).

## Exact controlled inventory

The inventory below is exact for the subject commit. “Public” means a
recommended newcomer path. “Compatibility” means an existing learner shortcut
whose path remains supported by this decision. “Internal” does not create a
public compatibility promise.

| # | Root path | Class | Current command or delegate | Static/consumer evidence |
|---:|---|---|---|---|
| 1 | `START_HERE.cmd` | Public | `python scripts\start_mclab.py %*` | C1, C2, T1 |
| 2 | `START_HERE.command` | Public | `python3 scripts/start_mclab.py "$@"` | C1, C2, T1 |
| 3 | `start_here.sh` | Public | `python3 scripts/start_mclab.py "$@"` | C1, C2, T1 |
| 4 | `run_mclab.cmd` | Compatibility | bootstrap, then `python -m mclab menu` | C1, C3, T2 |
| 5 | `run_all.ps1` | Internal | `scripts/bootstrap_and_run.py --verify` | C1, T3 |
| 6 | `run_all_batches.cmd` | Compatibility | batch `all` | C1, T2 |
| 7 | `run_batch_lab01.cmd` | Compatibility | batch `lab01_msd_compare` | T2 |
| 8 | `run_batch_lab02.cmd` | Compatibility | batch `lab02_pid_compare` | T2 |
| 9 | `run_batch_lab03.cmd` | Compatibility | batch `lab03_2dof_compare` | T2 |
| 10 | `run_batch_lab04.cmd` | Compatibility | batch `lab04_wall_compare` | T2 |
| 11 | `run_batch_lab04_cartesian.cmd` | Compatibility | batch `lab04_cartesian_compare` | T2 |
| 12 | `run_lab01.cmd` | Compatibility | lab01, `configs\lab01_msd\default.yaml`, plots `essential` | C3, T2 |
| 13 | `run_lab01_interactive.cmd` | Compatibility | lab01, `configs\lab01_msd\interactive_pull.yaml`, plots `essential` | C3, T2 |
| 14 | `run_lab02.cmd` | Compatibility | lab02, `configs\lab02_pid\default.yaml`, plots `essential` | C3, T2 |
| 15 | `run_lab02_interactive.cmd` | Compatibility | lab02, `configs\lab02_pid\interactive_disturbance.yaml`, plots `essential` | C3, T2 |
| 16 | `run_lab03.cmd` | Compatibility | lab03, `configs\lab03_2dof\joint_space_2dof.yaml`, plots `essential` | C3, T2 |
| 17 | `run_lab03_interactive.cmd` | Compatibility | lab03, `configs\lab03_2dof\interactive_2dof.yaml`, plots `task_disturbance` | C3, T2 |
| 18 | `run_lab03_dls_interactive.cmd` | Compatibility | lab03, `configs\lab03_2dof\dls_singularity_2dof.yaml`, plots `dls_disturbance` | C3, T2 |
| 19 | `run_lab03_condition_dls_interactive.cmd` | Compatibility | lab03, `configs\lab03_2dof\condition_aware_dls_2dof.yaml`, plots `dls_disturbance` | C3, T2 |
| 20 | `run_lab04.cmd` | Compatibility | lab04, `configs\lab04_panda\joint_pd.yaml`, plots `essential` | C3, T2 |
| 21 | `run_lab04_interactive.cmd` | Compatibility | lab04, `configs\lab04_panda\interactive_joint_hold.yaml`, plots `essential` | C3, T2 |
| 22 | `run_lab04_cartesian_interactive.cmd` | Compatibility | lab04, `configs\lab04_panda\interactive_cartesian_reach.yaml`, plots `cartesian_reach` | C3, T2 |
| 23 | `run_lab04_wall_interactive.cmd` | Compatibility | lab04, `configs\lab04_panda\interactive_virtual_wall.yaml`, plots `wall` | C3, T2 |

All 12 lab shortcuts add `--viewer --realtime --pause-at-end --plot`, a
specific `--plots` selection, and `--open-report`. All six comparison
shortcuts are headless batch adapters with `--open-report`. `run_mclab.cmd`,
all lab shortcuts, and all batch shortcuts use
`scripts/bootstrap_and_run.py --setup-only` when their prerequisites are
missing. The Lab04-dependent shortcuts also guard the Franka Panda scene.

### Evidence key

- **C1 — declared interface:** [repository_structure.md](../../docs/repository_structure.md)
  classifies the three newcomer paths, compatibility launcher groups, and the
  internal PowerShell helper. The root KR/EN
  [README](../../README.md) and [English README](../../README.en.md) present the
  three newcomer launchers.
- **C2 — cross-platform consumer:**
  [desktop.yml](../../.github/workflows/desktop.yml) calls each recommended
  launcher with `--setup-only`; [installation.md](../../docs/installation.md)
  documents the same OS mapping.
- **C3 — lesson consumer:** the Lab01–Lab04 guides link the applicable exact
  Windows shortcuts:
  [Lab01](../../docs/lab01_mass_spring_damper.md),
  [Lab02](../../docs/lab02_pid_control.md),
  [Lab03](../../docs/lab03_trajectory_planning.md), and
  [Lab04](../../docs/lab04_panda_manipulator.md).
- **T1 — newcomer contract tests:**
  [check_readme_contract.py](../validation/check_readme_contract.py) and
  [test_readme_contract.py](../../tests/test_readme_contract.py) verify the
  three files, their delegates, README references, and POSIX executable modes.
- **T2 — compatibility static tests:**
  [test_launch_scripts.py](../../tests/test_launch_scripts.py) names
  `run_mclab.cmd`, all 12 lab shortcuts, and all six batch shortcuts, and checks
  their expected commands, configs, flags, setup guards, and Panda guards.
- **T3 — sparse internal check:** the README contract checks that
  `run_all.ps1` exists and is classified as internal, but does not verify its
  command or execute it.

## Package evidence and impact

The one-folder desktop package does not consume any of the 23 root launchers.
[build_desktop.py](../../scripts/build_desktop.py) invokes
[mclab.spec](../../packaging/mclab.spec), whose analysis entry is
[packaging/entrypoint.py](../../packaging/entrypoint.py). That entry calls
`mclab.cli:main`; the spec's explicit data list includes configs, models, QML,
licensed assets, fonts, and the license, but no root launcher.

Consequently, moving the root launchers has no demonstrated package-size,
cold-start, or runtime benefit. Adding them to a package would be a new package
contract and is outside IA-00. PKG-01 should measure and align the existing
packaged entry rather than assume a launcher move.

The source launchers are nevertheless path-sensitive consumers. The `.cmd`
files change to `%~dp0` and use repository-relative `.venv`, config, helper,
and Menagerie paths. The POSIX newcomer launchers derive the repository root
from their own location. `run_all.ps1` derives its helper path from
`$PSScriptRoot`. A direct move would therefore change behavior unless the
implementation were rewritten and the old root path retained as a shim.

## Decision and rationale

**Decision: FREEZE.** Keep the exact 23-path inventory in place through v0.1
and B4. Do not open IA-01 under this decision.

The reasons are:

1. The three public newcomer launchers already share one cross-platform
   bootstrap, and all learner shortcuts converge on the same CLI. There is no
   competing product implementation to consolidate.
2. Existing READMEs, lesson guides, classroom material, tests, and CI consume
   the root paths. A move would spend compatibility budget without a measured
   learner, maintenance, package, or safety gain.
3. The files contain location-dependent working-directory logic. Moving their
   bodies is not a mechanical directory cleanup.
4. Static coverage is strongest for the newcomer trio and named Windows lab
   and batch adapters, but gaps remain around exact inventory control,
   PowerShell behavior, and real Windows execution. Those gaps make a
   pre-B4 move harder to prove and roll back safely.
5. FREEZE keeps PKG-01 and E2E-01 focused on the actual packaged and learner
   workflows and avoids mixing information architecture with release evidence.

FREEZE is a path decision, not an indefinite API promise. The v0.1/B4 boundary
is the earliest reconsideration point, not an automatic removal date.

## Allowed changes while frozen

The following changes may use the normal protected-branch process without an
IA-01, provided they keep all 23 paths and their documented roles stable:

1. A focused correctness, quoting, security, or error-reporting fix in place.
2. A documentation correction that continues to name the same stable path.
3. Stronger exact-inventory, delegate, mode, or platform tests.
4. A CLI, app, lab, batch, or bootstrap implementation improvement below the
   adapters that preserves their argument forwarding, working directory,
   exit-code behavior, and learner-visible command intent.
5. A package-only change proven by PKG-01 that leaves this source-launcher
   boundary unchanged.

Any such change still needs its own scope, validation, and rollback evidence.

## Required in-place launcher hardening

The inventory review found one concrete clean-setup defect below the frozen
path boundary. On a fresh checkout, `run_mclab.cmd` invokes
`scripts/bootstrap_and_run.py --setup-only`. That helper installs `.[dev]`,
while `PySide6-Essentials` is present only in the `app` optional dependency;
the launcher then invokes `python -m mclab menu`, whose Qt application requires
PySide6. The current text-only launcher test checks the delegate and failure
guard but cannot prove that this dependency chain launches the menu.

A separate focused correctness PR must reconcile that bootstrap dependency
path before PKG-01/E2E-01 acceptance. It may install the required app extra or
route setup through the shared desktop bootstrap, but it must keep
`run_mclab.cmd` at the root, preserve its learner-visible menu intent and exit
code behavior. Its regression matrix must cover both a clean environment and
an existing dev-only venv where the venv and Panda scene are present but
PySide6 is absent. The latter currently skips setup entirely, so changing only
the helper's install extra is insufficient unless the launcher guard or
delegate also re-enters dependency repair. This is allowed in-place hardening
under FREEZE; it is not IA-01 and does not authorize a path move. Until that PR
passes, clean-checkout and pre-existing-environment execution of
`run_mclab.cmd` remain unproven and must not be cited as package or E2E
evidence.

## Forbidden changes while frozen

Until a superseding decision is accepted, do not:

1. rename, move, delete, or replace any of the 23 paths;
2. add another root launcher or split an existing launcher into a new public
   path;
3. redirect a public newcomer launcher away from `scripts/start_mclab.py`, or
   silently change the compatibility launchers' lab, config, plot, batch, or
   desktop intent;
4. reclassify `run_all.ps1` as learner-facing;
5. remove compatibility in anticipation of a future release;
6. add the root launchers to the desktop bundle without a separate package
   contract and measured justification;
7. move config, model, third-party, paper, JOSE, outreach, or other publication
   paths as part of launcher work; or
8. treat this record as authorization for IA-01, cleanup, distribution,
   signing, release, DOI, external contact or recruitment, or publication
   action.

## Static validation gaps

These gaps are recorded for later hardening; they do not require IA-01 and are
not permission to change a launcher path.

1. There is no single gate asserting the exact 23-path set, count, extensions,
   and absence of additional tracked root launchers. The README checker's
   `ROOT_LAUNCHER_INVENTORY` names only `run_mclab.cmd`,
   `run_all_batches.cmd`, and `run_all.ps1`; its grouped `run_lab*.cmd` and
   `run_batch*.cmd` documentation markers are not a filesystem inventory.
2. `test_launch_scripts.py` exactly covers `run_mclab.cmd`, 12 lab shortcuts,
   and six batch shortcuts. Its root `*.cmd` setup-guard scan skips any file
   that does not already contain the recognized setup command, so an unrelated
   added `.cmd` could escape that check.
3. `run_all.ps1` has no command/delegate assertion and is not executed by the
   launcher test suite.
4. Compatibility `.cmd` files are checked as text, not executed on Windows.
   The desktop workflow executes only the recommended `START_HERE.cmd` setup
   path, not every viewer or comparison shortcut.
5. There is no explicit package test asserting that root launchers remain out
   of the PyInstaller analysis/data manifest.
6. Exact per-file documentation references are distributed across lab guides;
   the structure checker accepts wildcard group labels instead of reconciling
   every documented launcher with the tracked inventory.
7. The `run_mclab.cmd` setup path installs `.[dev]` rather than the `app` extra
   needed by its subsequent Qt menu target. Its venv-and-scene guard also
   treats an existing Qt-missing dev-only venv as ready. No clean or
   pre-existing-environment Windows execution test currently exercises that
   compatibility path; the required in-place hardening above owns this gap.

A future hardening PR may add an exact manifest test, validate the PowerShell
delegate, reconcile docs against the manifest, and assert the package boundary.
Those tests should derive expected paths from a reviewed constant, fail on both
addition and removal, and avoid launching viewers in CI.

## Reconsideration triggers

Reconsider FREEZE only when at least one of the following produces recorded,
measurable evidence:

1. newcomer or instructor testing shows that root launcher density causes a
   material task-completion or wrong-entry problem;
2. recurring launcher defects demonstrate unmanageable duplication despite
   the shared Python bootstraps and CLI;
3. a supported OS, security control, distribution channel, or packaging design
   requires a different entry arrangement;
4. v0.2 or a later compatibility policy intentionally changes the supported
   source-checkout interface;
5. an incident or support trend shows that the current location prevents safe
   diagnosis or recovery; or
6. an exact-inventory gate, cross-platform compatibility plan, deprecation
   window, package-impact proof, and rollback rehearsal are ready for review.

A trigger opens review of a **superseding IA decision**. It does not itself
authorize a move. The superseding record must identify the owner, release
boundary, user communication, and evidence that outweighs the compatibility
cost.

## GO alternative retained for comparison

The following mapping is deliberately non-operative. It records a bounded GO
alternative so a future reviewer can compare it with FREEZE without
rediscovering the path set. Adopting any row requires a superseding IA decision
and a separate IA-01 PR before PKG-01/E2E-01 on that release line.

| Current path | GO-only candidate canonical implementation | Required compatibility treatment |
|---|---|---|
| `START_HERE.cmd` | unchanged at repository root | Keep public path and current Python delegate |
| `START_HERE.command` | unchanged at repository root | Keep public path, executable mode, and argument forwarding |
| `start_here.sh` | unchanged at repository root | Keep public path, executable mode, and argument forwarding |
| `run_mclab.cmd` | `scripts/launchers/windows/run_mclab.cmd` | Root file becomes a forwarding shim |
| `run_all.ps1` | `scripts/launchers/maintainer/run_all.ps1` | Update maintainer refs; keep a transition shim if any external caller is found |
| `run_all_batches.cmd` | `scripts/launchers/windows/run_all_batches.cmd` | Root file becomes a forwarding shim |
| `run_batch_lab01.cmd` | `scripts/launchers/windows/run_batch_lab01.cmd` | Root file becomes a forwarding shim |
| `run_batch_lab02.cmd` | `scripts/launchers/windows/run_batch_lab02.cmd` | Root file becomes a forwarding shim |
| `run_batch_lab03.cmd` | `scripts/launchers/windows/run_batch_lab03.cmd` | Root file becomes a forwarding shim |
| `run_batch_lab04.cmd` | `scripts/launchers/windows/run_batch_lab04.cmd` | Root file becomes a forwarding shim |
| `run_batch_lab04_cartesian.cmd` | `scripts/launchers/windows/run_batch_lab04_cartesian.cmd` | Root file becomes a forwarding shim |
| `run_lab01.cmd` | `scripts/launchers/windows/run_lab01.cmd` | Root file becomes a forwarding shim |
| `run_lab01_interactive.cmd` | `scripts/launchers/windows/run_lab01_interactive.cmd` | Root file becomes a forwarding shim |
| `run_lab02.cmd` | `scripts/launchers/windows/run_lab02.cmd` | Root file becomes a forwarding shim |
| `run_lab02_interactive.cmd` | `scripts/launchers/windows/run_lab02_interactive.cmd` | Root file becomes a forwarding shim |
| `run_lab03.cmd` | `scripts/launchers/windows/run_lab03.cmd` | Root file becomes a forwarding shim |
| `run_lab03_interactive.cmd` | `scripts/launchers/windows/run_lab03_interactive.cmd` | Root file becomes a forwarding shim |
| `run_lab03_dls_interactive.cmd` | `scripts/launchers/windows/run_lab03_dls_interactive.cmd` | Root file becomes a forwarding shim |
| `run_lab03_condition_dls_interactive.cmd` | `scripts/launchers/windows/run_lab03_condition_dls_interactive.cmd` | Root file becomes a forwarding shim |
| `run_lab04.cmd` | `scripts/launchers/windows/run_lab04.cmd` | Root file becomes a forwarding shim |
| `run_lab04_interactive.cmd` | `scripts/launchers/windows/run_lab04_interactive.cmd` | Root file becomes a forwarding shim |
| `run_lab04_cartesian_interactive.cmd` | `scripts/launchers/windows/run_lab04_cartesian_interactive.cmd` | Root file becomes a forwarding shim |
| `run_lab04_wall_interactive.cmd` | `scripts/launchers/windows/run_lab04_wall_interactive.cmd` | Root file becomes a forwarding shim |

Under that alternative, IA-01 would have to make each canonical implementation
resolve the repository root independently of its new directory. A root shim
must forward every argument, preserve quoting, current working directory,
stdout/stderr, and the exact child exit code. Public and compatibility root
paths must remain functional for at least one released version; documentation,
CI, package checks, and classroom material must be updated in the same bounded
compatibility program. The candidate directories above are comparison targets,
not approved architecture.

## Compatibility and rollback

### FREEZE compatibility contract

- All 23 tracked paths remain present with their current classification.
- The three newcomer adapters continue to delegate to
  `scripts/start_mclab.py` and accept the current setup/app options.
- Compatibility shortcuts keep their current lab/config/plot/batch intent and
  continue to propagate setup or command failure.
- Relative config and model paths remain valid from a repository checkout.
- POSIX launcher executable modes remain set.
- `run_all.ps1` remains internal and may not be advertised as a learner path.

Because FREEZE moves no code, its immediate rollback is the independent revert
of this decision document. If later evidence invalidates the decision, a
superseding ADR can replace it without first repairing path breakage.

### Rollback requirement for any future GO

An IA-01 implementation must be independently revertible. Before merge it must
record the old and new file hashes, callers, docs, CI, package impact, and an
OS-specific smoke matrix. During the compatibility window, rollback restores
the implementation bodies at the root paths or repoints the root shims to the
last known-good implementation; it must not delete the shims first. If argument
forwarding, working-directory resolution, setup failure, exit-code propagation,
or a learner command regresses, stop promotion, restore the old bodies, and
re-run the newcomer, launcher-contract, package, and E2E gates.

Shim removal is a later release decision after at least one released-version
window and evidence that supported callers have migrated. It cannot be bundled
into the initial move.

## Acceptance gate

Before this draft can merge as IA-00:

1. STATE-01 must be accepted first, including post-merge evidence, and this
   branch must remain based on its resulting protected-main baseline.
2. The exact 23-path inventory must still reconcile with the new baseline; any
   delta requires re-review rather than silent regeneration.
3. Local links, the README contract, and focused launcher tests must pass.
4. Review must confirm that FREEZE, “IA-01 not required,” the v0.1/B4 boundary,
   and all non-authorizations remain explicit.
5. The merge must contain this decision record only, apart from conflict-only
   rebase metadata that does not alter another handoff.

Acceptance of IA-00 closes the launcher-path decision for the stated boundary;
it does not advance B4 or any release, signing, cleanup, external-contact,
recruitment, or publication gate.
