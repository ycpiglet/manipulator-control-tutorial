# Current State

Updated: 2026-07-22 KST

## Active Product and Release Handoff

The authoritative current audit is
`.agents/reviews/20260720_enterprise_readiness_audit.md`. Read it before
starting release, cleanup, completion-progress, packaging, README, or
repository-structure work.

The authoritative implementation order, validation gates, rollback rules, and
cross-session handoff are in `.agents/READINESS_EXECUTION_PLAN.md`. Do not start
from the historical sections below or from the stale dirty checkout.

Current release decision:

- supervised Linux classroom/demo: Conditional GO;
- limited technical preview: Conditional GO;
- general public beta: NO-GO;
- signed multi-platform production: NO-GO.

Immediate order of work:

1. preserve the completed COMP-01, DOC-01, and SAFE-01 exact-head and post-merge evidence
   without touching real learner outputs;
2. finish draft PR #53 on its current head, requiring all six exact-head checks
   and resolved review conversations before merge;
3. declare B2 only after GOV-01, SAFE-01, DOC-01, and COMP-01/02 all pass, then
   follow gates G2 through G5 for distribution,
   real-platform/human validation, signing, and publication.

Current exact next action: push this state-only handoff update to draft PR #53,
require all six checks again on that new exact head, resolve every review
conversation, and merge only if the protected gate remains green. The functional
candidate `7e54f8cffad7b82408c6352a130a1a463013dfc8` passed 6/6 in CI run
`29861932148` and desktop run `29861932100`. The candidate is based on clean
fetched `origin/main`
`edaeb340765b076e761f5cd23ac588dda6729ba3`. GOV-01, SAFE-01, DOC-01, and
COMP-01 are complete; PR #53 merge, post-merge evidence, COMP-02 completion,
and B2 are not. A
real-root cleanup dry-run is permitted only as a separate owner-reviewed
activity and is not a COMP-02 prerequisite.
Do not apply any plan to the real outputs root until the owner has reviewed
that exact dry-run and separately authorized apply.

### 2026-07-22 COMP-02 draft PR #53; merge gate pending

- Objective: connect desktop, menu, CLI, outputs index, report, worksheet,
  coverage, and path progress to the COMP-01 canonical evaluator without
  rewriting learner artifacts.
- Current exact base/head: clean fetched
  `origin/main@edaeb340765b076e761f5cd23ac588dda6729ba3`; frozen implementation
  commit `872ad7b7ce2949751873c47e7149300c4a521930` with tree
  `7eeffa92fb47d599bf751419c0bf612aba25d3b0`; reviewed functional head
  `7e54f8cffad7b82408c6352a130a1a463013dfc8` with tree
  `7daafd48b64c541f89e8907c6a1a4e82e45fb93c`.
- Completed local work: strict schema-1 pinned, bounded, no-link evidence
  reading; immutable terminal publication and fail-closed recovery; canonical
  batch rules; all learner-surface wiring; ordered Lab04 wall-preset evidence;
  digest-published read-only worksheet policy; and safe cumulative-index CLI
  discovery. Draft PR #53 is open.
- Changed areas: application repositories/presentation/QML, batch and CLI,
  completion progress, output inventory/root/publication, logging/plotting/
  reporting, and focused fixtures/regression tests. No model, config, launcher,
  dependency, directory-layout, or real learner-output change is included.
- Commands and measured results: final Python 3.10 full regression
  `825 passed, 7 skipped, 2,422 subtests`, coverage `82.45%`; focused
  publication/consumer regression `171 passed, 71 subtests`; catalog parity
  `78` targets and `292` cases with mismatch `0`; Ruff, KR/EN static and
  runtime README contracts, `14/14` Action pins, citation coverage, robotics
  foundations, and diff check PASS.
- Gate status: local independent final COMP-02/G1 review GO with no P0/P1.
  Functional head `7e54f8c` passed required 6/6 in CI `29861932148` and
  desktop matrix `29861932100`. Earlier heads exposed and then fixed one
  immutable audit-fixture publication error and one compact-card XCB
  overflow/focus regression. This state-only successor head must pass the same
  6/6 before merge; review conversations, merge, and post-merge checks remain
  pending and must not be assumed.
- Compatibility/rollback: schema-1 remains versioned and read-only; invalid or
  future schema does not fall back to legacy summaries; existing artifacts are
  never migrated. Revert the focused COMP-02 merge if consumer parity or
  publication semantics regress; do not repair by rewriting saved runs.
- Open risk: producer payload writes before terminal publication are not held
  under one long-lived pinned lease. The strict reader rejects any changed or
  redirected bytes, so this cannot grant false completion and is a nonblocking
  writer-hardening follow-up. Single-maintainer owner risk acceptance remains
  required for B2, which is not a public-beta GO.
- Single next action: push this state update to PR #53 and require six green
  checks plus resolved conversations on the resulting exact head.

### 2026-07-21 COMP-01 complete; COMP-02 next

- Objective: freeze one read-only, versioned truth function for run status,
  plot, learner-control, correlated prediction/note observation, ordered
  required-preset, and legacy completion evidence.
- Completed work and PR: PR #51 exact head
  `95e1be9069349be2c4140932f5f12b3deb99dabb` passed all six required checks
  and merged through ruleset `19209773` as
  `c742501de82a8e2500d02d501ecb492e3cf9edb4`. The merge tree equals the
  reviewed source-head tree.
- Changed areas: new dependency-light completion domain module, catalog rule
  re-export/declarations, immutable v1 and legacy fixtures, and exhaustive
  truth-contract tests. Desktop, learner menu, CLI, index, report, and worksheet
  consumers were not rewired; no saved artifact was migrated or rewritten.
- Local measured result: 17 contract tests and 1,076 subtests PASS; exhaustive
  1,024-case truth matrix PASS; focused boundary regression 204 passed, 3
  skipped, 1,840 subtests; full regression 691 passed, 9 skipped, 2,189
  subtests with 80.86% coverage; Python 3.10 floor 109 passed, 6 skipped, 20
  subtests; Ruff, README contracts, citation/formula gates, and 14/14 Action
  pins PASS.
- Gate status: final-head local contract and no-consumer-wiring reviews
  APPROVE with no unresolved P0-P3. Earlier GitHub automated reviews found two
  P1 issues on prior heads; both were fixed and their threads resolved.
  Exact-head CI `29836070679` and desktop matrix `29836070606` passed 6/6.
  Post-merge CI `29836511032` and desktop matrix `29836511019` passed the same
  6/6 on the merge SHA. The durable record is
  `.agents/baselines/COMP-01-completion-contract.md`.
- Compatibility/rollback: schema-1 and legacy files are read-only, the catalog
  import path remains compatible, and consumer behavior was deliberately held
  for COMP-02. Revert the focused COMP-01 merge through protected main if the
  unused contract itself is wrong; do not rewrite learner artifacts.
- Open risk: COMP-02 must perform complete schema-1 validation through a pinned,
  bounded, no-link reader, verify actual regular evidence files, preserve
  ordered wall-preset capability on every relevant surface, define batch rules,
  and prove desktop/menu/CLI/index/report/worksheet mismatch 0.
- Single next action: start `agent/completion-consumers` from fetched latest
  clean `origin/main` containing `c742501d` and implement COMP-02 only. B2,
  structure changes, real-root dry-run, and cleanup apply remain out of scope.

### 2026-07-21 DOC-01 complete; COMP-01 next

- Objective: make the KR/EN newcomer README, public command/CLI shape, links,
  launchers, quickstart evidence, and repository map deterministic PR gates.
- Completed work and PR: PR #49 exact head
  `74a77393761025462c3dcdea0c2bfcdfe62b315b` passed all six required checks
  and merged through ruleset `19209773` as
  `66eca7f666409336a6b9a6052828b3ae1c8b68d7`. The merge tree equals the
  reviewed source-head tree.
- Completed work: recovered the interrupted uncommitted files from the only
  surviving worktree, closed the prior Markdown/HTML and CLI-parser review
  findings, added the no-move compatibility inventory, and added actual
  Windows/Linux/macOS recommended-launcher setup checks. The audit snapshot was
  not rewritten.
- Changed areas: root KR/EN README and launcher, documentation map/structure
  guide, README contract checker/tests, artifact verifier/tests, CI/desktop
  workflows, contribution command, and validation metrics. No directory move,
  config/model change, learner output cleanup, or cleanup `--apply` is in scope.
- Local measured result on the frozen final candidate: README checker 25/25
  static metrics and 82 links PASS; installed runtime CLI 9/9 invocations PASS;
  676 passed, 7 skipped, 1,113 subtests; coverage 81.02%; Python 3.10/3.12
  static checker, Ruff, citation coverage, robotics foundations, 14/14 Action
  pins, workflow YAML, Linux recommended-launcher setup, and all four
  default-lab artifact checks PASS. The frozen checker and regression-test
  SHA-256 values are `b0098ea93cdab921bc3b61ed12a7bc746db8feabe8fb279f311e5a9752c298d7`
  and `9513987bce9ae14799e48c96ec52d4744b47e8e8a9a1f6b8fbb97fba05920acb`.
- Gate status: newcomer-truth, code-boundary, and final regression/performance
  reviews all APPROVE with no P0-P3 findings. Exact-head CI `29811793935` and
  desktop matrix `29811793927` passed 6/6. Post-merge CI `29812128233` and
  desktop matrix `29812128189` passed the same 6/6 on the merge SHA, including
  Tectonic and all three recommended-launcher paths. The durable record is
  `.agents/baselines/DOC-01-readme-contract.md`.
- Compatibility/rollback: all paths stay in place; `run_mclab.cmd`,
  `run_lab*.cmd`, `run_batch*.cmd`, and `run_all_batches.cmd` remain compatibility
  paths. `run_all.ps1` is explicitly internal. Revert the focused DOC-01 commit
  if the gate causes a false block; do not solve it with a directory move.
- Open risk: GitHub-hosted runners prove the automated source setup contract,
  not real newcomer comprehension or signed packaged-install independence.
  Those remain later G3/G4 gates.
- Single next action: start `agent/completion-contract` from the fetched latest
  clean `origin/main` containing the DOC-01 merge and implement COMP-01 without
  changing consumer behavior or rewriting legacy manifests.

### 2026-07-21 GOV-01 and SAFE-01 completion record

PR #39 merged the policy baseline as
`9f4169f60efb32d6b6d49b9f06d985d8de9c6f70` after 6/6 exact-head checks.
Before merge, Private Vulnerability Reporting was enabled and re-read as true.

Ruleset `Protect main (GOV-01B)` ID `19209773` is active for `main`. It blocks
deletion and force-push, requires a PR, conversation resolution, an up-to-date
branch, and six exact GitHub Actions checks. Admin bypass is PR-only. GitHub
API rechecks also show vulnerability alerts, Dependabot security updates,
private reporting, secret scanning, and push protection enabled. The single
direct-collaborator exception keeps required approvals at zero and is recorded
as an exception, not independent human approval.

PR #40 completed GOV-01C. Its exact head
`e26c1ab40d77af0d3744c217736477ef2592251c` passed 6/6 required checks and
merged as `41be887f21bfb476507d94a089f98c0ef72453c8`. Post-merge CI
`29749432294`, the three-OS desktop run `29749432322`, and Dependabot
activation run `29749436873` passed. Repository Action SHA enforcement was
enabled and read back as `sha_pinning_required=true`; GOV-01 verified 12/12
workflow Action references at that merge, while merged main now verifies 14/14
after SAFE-01 added one pinned setup step. Some pinned Action releases still declare
Node 20 internally and are currently run through GitHub's Node 24
compatibility path; replacing them with reviewed newer releases remains a
SUP-01 residual. Detailed evidence is in
`.agents/baselines/GOV-01-governance.md`.

The merged SAFE-01 implementation provides strict configured-root and manifest
selection, UTC retention, default dry-run, exact `--apply PLAN_ID --yes`
authorization, recoverable quarantine receipts/list/restore, move rollback and
interruption recovery, exact typed Qt confirmation, lexical root/ancestor
pinning, a cross-process physical-root operation lock, bounded future receipt
preflight, identity-checked forward moves, and identity-checked rollback. Both
bulk and single-result cleanup now require an exact-integer schema-1 terminal
manifest. New run and batch writers use unique claims, publish artifacts and
reports before the terminal manifest, reject output reuse, and preserve strict
completed/error evidence across retry, late-cancel, and process-error paths.
The desktop all-batch handoff is token-bound and one-shot.
Independent fault-injection and writer-boundary reviews found no P0/P1 in the
reviewed source-swap, post-commit, rollback, root-identity, output-claim, or
terminal-publication paths and issued scoped local GO decisions. Frozen-tree
Python 3.12 validation passed 528 tests with 7 platform skips and 1,109
subtests; coverage is 80.92% overall and 89% for `output_cleanup.py`. Python
3.10 cleanup/CLI validation passed 109 tests with 6 platform-only skips and 20
subtests. The relevant XCB Qt audit passed 18/18 cases; Ruff, compileall, 14/14
Action pin scanning, and diff checks also passed. PR #46 opened from
initial head `a56e308f2c82b3d346801905fd3bba686ab7da4b`: simulator and both paper
gates passed, while the three desktop jobs exposed macOS temp-path aliases,
Windows rename-buffer/path/pin behavior, and missing Ubuntu XCB runtime
dependencies. Second head `7e9fcf701121069be924b220510ab7a107099c0b`
passed CI 3/3 and the full Ubuntu desktop job, then isolated one remaining
macOS fixture alias and one Windows junction-selection expectation. Final head
`cca1655dbc4b1d133959df6ad1b77fc3e9e499e9` repaired those two gaps. An
independent final review found no P0/P1/P2 in the focused changes. Exact-head
CI `29778661706` and desktop matrix `29778661771` passed 6/6, including
Ubuntu 18/18 XCB and all three packaged diagnostics. PR #46 merged through
ruleset `19209773` as
`0fb77a026206f4b25360ace36d70d265a93a9366`; post-merge CI `29779125693`
and desktop matrix `29779125685` passed all six checks again. SAFE-01 is PASS.
The failed run IDs `29776388375` and `29778026653` remain preserved as
diagnosis history rather than acceptance evidence. The real `outputs/` tree
was not modified, no real-root dry-run or apply ran, and the temporary Panda
link was removed. The full record is `.agents/baselines/SAFE-01-cleanup.md`.

### 2026-07-20 B1 baseline and worktree cleanup

PR #35 was rebased after PR #36 advanced main, passed all six checks again,
and merged as `f04cca16848316e227df18fe129229b515ae01c7`. The merge tree is
identical to the reviewed PR head. The exact controlled-item fingerprints and
G0 evidence are recorded in `.agents/baselines/B1-newcomer-baseline.md`.

The stale root checkout contained two package-size changes. They were copied
byte-for-byte onto current main, verified, and preserved remotely in draft PR
#37 before the local copies were restored. The root worktree is now clean,
checked out at `main`, and equal to `origin/main`. PR #37 remains a WIP and is
not approved for merge. Its six exact-head checks and three packaged
self-test/doctor runs now pass; the remaining decision needs a structural
exclusion test and same-workflow package-size baseline deltas.

The separately recovered static-font WIP is preserved in draft PR #38 as two
commits: an exact recovery baseline and a current-main integration/test
adjustment. Local regeneration produced all six pinned hashes and the full
suite passed 444 tests. Same-workflow three-OS evidence records a 24.5–24.6 MB
one-folder increase and all builds remain below the 400 MiB development gate.
It remains unapproved pending real Windows Korean glyph inspection, packaged
font-hash/OFL checks, registration-failure handling, and licensing/install
scope decisions.

### 2026-07-20 Newcomer documentation and repository IA

PR #35 was created from a clean `origin/main@44b1937` worktree. Its
first commit preserves the enterprise readiness audit; its documentation pass
rewrites `README.md` and `README.en.md` with one shared information
architecture, adds `docs/README.md`, and makes the integrated Qt app the
explicit primary entry point in every Lab guide.

The same PR now carries the durable readiness execution plan and an active
work-order pointer in `AGENTS.md`, so later sessions can recover the exact
dependency order, gates, and rollback policy without reconstructing this
conversation.

Repository-structure decision:

- keep `src/`, `configs/`, `models/`, `tests/`, `third_party/`,
  `paper/`, `jose/`, and `.agents/` in place for now;
- treat the current clutter as presentation and transition debt, not a reason
  for a wholesale architecture move;
- later consolidate root `run_lab*.cmd` and `run_batch*.cmd` launchers
  behind compatibility shims in a dedicated PR;
- do not move config/model or publication paths merely for aesthetics because
  they are embedded in reproducibility records, tests, CI, and LaTeX tooling.

The sections below are retained as historical manuscript and implementation
context. If they conflict with the 2026-07-20 audit, the audit takes
precedence.

## Current Objective

Iteratively improve the Korean review/tutorial paper on impedance, impedance control, Modern Robotics foundations, and the MuJoCo educational lab so that beginners can follow the history, intuition, equations, kinematics, trajectories, force/torque mapping, and control meaning before a later compression pass. Use multi-agent review, keep the simulator content untouched unless explicitly requested, reflect every manuscript version through `paper/main.tex`, and keep measurable validation, version logs, and state records durable.

## Current Manuscript State

- Main source: `paper/main.tex`
- Section sources: `paper/sections/*.tex`
- Current focus sources: `paper/sections/01_introduction.tex`, `paper/sections/02_impedance.tex`, `paper/sections/04_electric_system.tex`, `paper/sections/05_mechanical_system.tex`, `paper/sections/05b_robotics_foundations.tex`, `paper/sections/06_impedance_control.tex`, `paper/sections/07_mujoco_lab_design.tex`, `paper/sections/08_discussion.tex`, `paper/sections/09_conclusion.tex`, `paper/sections/A_notation_checklist.tex`, `paper/main.tex`, `paper/figures/*.tex`, and `.agents/*`
- Bibliography: `paper/references/refs.bib`
- Latest PDF: `paper/main.pdf`
- Current length: 122 PDF pages
- Latest PDF size: 1002110 bytes

## Completed Since Last Snapshot

### 2026-07-19 Desktop app merge (PR #32) + F2 menu exposure

PR #32 landed the Qt Quick desktop application (`src/mclab/application/`,
~25k added lines, 112 files): bilingual ko/en UI with bundled Noto fonts,
single-instance lock with window activation, in-process simulation worker,
replay recording/playback, scenario catalog derived from
`learner_menu.MENU_ACTIONS`, PyInstaller one-folder packaging
(`scripts/build_desktop.py`, 400 MB bloat gate; Windows build 263.1 MB,
Linux 342.8 MB), and a new 3-OS `desktop.yml` CI workflow. Merged only
after three CI-fix rounds turned all six checks green (per the recorded
never-merge-red lesson): Linux `libegl1` runtime install; the
QFontDatabase font-directory warning treated as benign during
`app --self-test` (pre-fix exit 4 reproduced locally on Windows offscreen);
Qt view-shell modules omitted from the simulator coverage gate (floor holds
at 81%); `encoding="utf-8"` on every test `read_text()` (Windows CI runs
cp1252 and the QML contains Korean); and the custom QtQml hook now mirrors
the wheel QML layout (`PySide6/qml` on Windows vs `PySide6/Qt/qml` on
Unix) — the packaged Windows app previously failed with
"QtQuick.Controls is not installed", exit 3.

Follow-up on the same day: the F2 stored-energy failure-gallery pair
(`f2_launch_high_energy.yaml` / `f2_launch_precheck.yaml`) is now exposed
as learner menu cards (Lab01 group, chained Interactive -> launch ->
precheck -> Lab02), closing the safety-north-star gap where menu-only
learners never met the failure gallery. Menu/catalog counts moved
70 -> 72. Full UX/fidelity assessment with verified metrics recorded in
`.agents/SIM_UX_FIDELITY_ASSESSMENT.md` (measured pre-#32; scores: paper-sim
fidelity 4.8/5, freedom 4.0/5, UI/UX, convenience, friendliness 3.5/5 each).
UX backlog A (auto-repeat) and C (button delay) from
`.agents/UX_IMPROVEMENTS.md` remain open for the Tk menu path; B (single
window) is solved in the desktop app via the instance lock.

### 2026-07-11 Launcher and install UX (PRs #26-#31)

START_HERE.cmd one-click launcher (PR #27), cmd-parser-safe encoding fix
(PR #28), 64x lighter install via Panda-only sparse checkout 2.3 GB ->
44 MB plus `mclab clean` retention command (PR #29), launcher setup-guard
fix after a red-main incident (PR #30), and the recorded CI-guard lesson
(PR #31).

### 2026-07-07 Night Autonomous Run (PRs #22-#25) + Track C

While the owner slept, the loop exhausted all work not requiring user
input: author identity applied everywhere (Youncheol Jung, ORCID
0009-0000-5282-881X — C4 resolved); free-first cost re-baseline (CSM
primary for U5, MDPI demoted to approved-only); send-ready inquiry
package with web-verified channels (journal@kros.org / CSM EIC / JOSE);
weekly deadline-watch scheduled task; Track C zero-cost portfolio
(CITATION.cff, publish-ready KR+EN failure-gallery blog posts,
PORTFOLIO_PACKAGE.md with verified free venues — engrXiv/EdArXiv/Zenodo;
Papers-with-Code defunct warning); U7 KRoC 1-page short-paper draft
(simulator axis, compiles 0/0); U5-EN part 1 English review (11 pages,
0 warnings, fidelity reviewer Turing: CLEAN); KROS template discovered to
be Word/HWP behind author login → U3 final step re-scoped to DOCX
conversion (user action A4). All merges CI-green.

Critical path is now entirely user actions (A1-A4, P1-P3, B1) and
external events (KRoC CFP, inquiry replies).

### 2026-07-06 MILESTONE: Manuscript Definition of Done (M1-M7) complete

Across PRs #7-#15 (all CI-green merges), the autonomous two-track loop
closed every manuscript DoD item in `.agents/MISSION.md`:

- M1 selection guide (env-stiffness axis + starting values) — PR #11
- M2 failure gallery F1/F2/F3 from the owner's real failures, each with
  reproducible sim evidence and numeric gates — PRs #7, #9, #10
- M3 low derivation bundle (4 bridges + recorded rejections) — PR #13
- M4 full-manuscript dual review, residual HIGH=0, review texts preserved
  under `.agents/reviews/` — PR #15
- M5 notation sweep (one genuine finding fixed) — PR #14
- M7 first-read skip permission + shortest path — PR #12
- Track A in parallel: JOSE package (README.en.md, CC BY 4.0, jose/paper.md,
  CONTRIBUTING) — PR #8

Manuscript: 122 pages, 1002110 bytes, SHA-256
`29E47B3F6C29B00CF7A2DFCB4DC2DC98039A2327364D2D7F491EB9E6B576168A`.
Validator: 13 marker checkpoints + 9 numeric checkpoints, exit 0.
Anchors: 130+ (all enforced). Version labels for every pass in
PAPER_VERSION_LOG.

Remaining blocked-on-user items live in `.agents/USER_ACTIONS.md`
(inquiry sends A1-A3, KROS membership B1, JOSE author name/ORCID C4).

### 2026-07-06 Selection Guide M1 Pass + Gallery F1 (Track B)

`draft-20260706-failure-gallery-f1` completed the M2 gallery (parameter-sweep
case; reviewer Curie 4/4; merged as PR #10 with CI green). Then
`draft-20260706-selection-guide-m1` closed M1: source verification showed the
audit had overstated the gap (two selection tables already existed), so the
pass added only the genuinely missing axes — environment stiffness
(impedance/admittance duality) and per-method starting-value principles
(k_d ~ f_allow/delta_tol, 10 N / 2 cm -> 500 N/m example; zeta ~ 0.7;
admittance static-feel inversion; force-loop gain vs environment stiffness).
Reviewer Astrom 4/4 PASS. PDF 122 pages. Validator gains
manuscript_selection_guide_checkpoint + stiffness_starting_value_checkpoint
(error 0.0). Remaining DoD: M3 (Low derivation bundles), M4 (full-manuscript
dual review), M5 (notation sweep), M7 (shortest first-read path); S4 author
TODO is a user action (C4).

### 2026-07-06 Failure Gallery F3 Pass (Track B / M2)

Version label: `draft-20260706-failure-gallery-f3` (details in
PAPER_VERSION_LOG). Second gallery case from the owner's real failures:
"commanded a displacement, robot stopped short" reframed as the loaded
equilibrium x_ss = x_d + f_ext/k_d working as designed; Lab04
impedance_wall run measured 3.32 cm penetration with 8.629 N wall force =
k_wall*delta exactly (wall_balance_checkpoint error 0.0). Reviewer `Bode`:
4/4 PASS. PDF 121 pages. Also merged this date: PR #7 (F2 case) and PR #8
(JOSE package: README.en.md, LICENSE-docs CC BY 4.0, jose/paper.md draft,
CONTRIBUTING.md).

### 2026-07-05 Failure Gallery F2 Pass (Track B / M2)

Version label: `draft-20260705-failure-gallery-f2` (full details in
PAPER_VERSION_LOG). Opened the mission's failure gallery with the owner's
stored-elastic-energy launch case: new `sec:failure-gallery` subsection in
Section 6, two reproducible Lab01 scenarios (dangerous vs safe energy
budget), guide/next-run registrations required by the simulator's own test
gates, 4 anchors + config-existence + numeric checkpoints in the validator.
Simulation evidence: predicted 10 m/s vs measured 9.81 m/s peak; 13x stored
energy contrast. Reviewer `Feynman`: 4/4 PASS with independent
decay-envelope cross-check. This pass intentionally edited simulator
registries (learning_guides.py, reporting.py) — scenario metadata only, no
control logic.

| Gate | Threshold | Measured |
|---|---:|---:|
| LaTeX compile / final warnings | 0, 0/0/0, 0 boxes | pass |
| PDF | generated | 120 pages, 986095 bytes, SHA-256 `B0217366...C9E1776` |
| Validator | failures 0 | exit 0 (anchors 4/4, launch numeric error 0.0) |
| Targeted tests (guides/logging) | exit 0 | 53 passed + 74 subtests |
| Ruff (src, tests, .agents) | exit 0 | pass |
| Full pytest | exit 0 | 340 passed + 764 subtests (230 s) |

### 2026-07-05 Compression Pass Tier 1

Version label: `draft-20260705-compression-tier1`. New standing plan:
`.agents/COMPRESSION_PASS_PLAN.md` (tier definitions, hard constraints,
K1-K6 metrics, full disposition tables, lessons). Three duplication auditors
(Occam-A/B/C) swept Sections 2-6; after hand-verification only 3 Section 6
duplications were genuine and compressed (stiffness-first recommendation,
nominal-mass damping caveat back-reference, joint/Cartesian classification
merge); all Section 2-5 candidates were rejected as deliberate parallel
structure, protected bridges, or auditor errors — dispositions recorded.
Reviewer `Hilbert`: 3/3 PASS. All 113 anchors preserved (validator exit 0).
Tier 2 (relocation/reorganization) stays blocked on a venue/length decision.

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| LaTeX compile | exit 0 | 0 | `tmp/latex_compile_derivation_gaps/compile_comp1.json` |
| Final segment warnings | all 0 | 0/0/0, 0 over/underfull | same log |
| PDF | generated | 120 pages, 979540 bytes, SHA-256 `7B86A33D...F99779B0` | `Get-FileHash` |
| Anchor preservation | 113/113 | validator exit 0, failures 0 | `validate_robotics_foundations.py` |
| K1 dispositions | 100% processed | 3 compressed + 12 rejected with reasons | `.agents/COMPRESSION_PASS_PLAN.md` |
| Meaning/flow/beginner review | all PASS | 3/3 PASS | reviewer `Hilbert` |

### 2026-07-05 Derivation-Gap Medium Pass 2 (Iteration 3)

Version label: `draft-20260705-derivation-gaps-medium2`. Exhausted the
Medium tier of the derivation backlog: A5 (j first-use definition), A6
(sinusoid velocity derivative + RLC series-sum bridge), A7 (i = q-dot
correspondence), B5 (undamped-solution substitution check), C3 (trajectory
product-rule origin of the two q-double-dot terms), C4 (impedance error
normalization and coefficient matching, cross-checked against the original
equation at 06:360). A8 confirmed already resolved by iteration 1. Reviewer
`Noether`: all 7 CORRECT/FOLLOWABLE, no duplication. Guarded by
`manuscript_derivation_gap_medium2_checkpoint` (7 anchors). Only Low-tier
bundles (B7, C5) remain in the backlog.

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| LaTeX compile | exit 0 | 0 | `tmp/latex_compile_derivation_gaps/compile_iter3.json` |
| Final segment warnings | all 0 | 0/0/0, 0 over/underfull | same log |
| PDF | generated | 120 pages (unchanged), 979698 bytes, SHA-256 `22DBA0FD...B47761C` | `Get-FileHash` |
| Validation script | failures 0 | exit 0 (7/7 new anchors) | `validate_robotics_foundations.py` |
| Ruff (.agents) | exit 0 | all checks passed | `.venv/Scripts/ruff.exe check .agents` |

### 2026-07-05 Derivation-Gap Medium Pass (Iteration 2)

Version label: `draft-20260705-derivation-gaps-medium1`. Closed backlog items
C2 (serial stiffness force split with combined-stiffness derivation and
5 N / 10 N numeric contrast), B4 (RLC zeta isolation algebra), B6 (overshoot
substitution chain; verified as mostly false positive first). Reviewer
`Euler`: all CORRECT/FOLLOWABLE, no duplication. Guarded by
`manuscript_derivation_gap_medium_checkpoint` (4 anchors) plus
`series_stiffness_checkpoint` and `overshoot_formula_checkpoint`.

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| LaTeX compile | exit 0 | 0 | `tmp/latex_compile_derivation_gaps/compile_iter2.json` |
| Final segment warnings | all 0 | 0/0/0, 0 over/underfull | same log |
| PDF | generated | 120 pages (+1), 976795 bytes, SHA-256 `70A0F58B...2583FDF9` | `Get-FileHash` |
| Validation script | failures 0 | exit 0 | `validate_robotics_foundations.py` |
| Ruff (.agents) | exit 0 | all checks passed | `.venv/Scripts/ruff.exe check .agents` |

### 2026-07-05 Derivation-Gap High-Severity Pass

Executed the standing beginner-accessibility goal (derivation steps fully
decomposed, especially Jacobian-adjacent math). Version label:
`draft-20260705-derivation-gaps-high`. New standing plan/backlog:
`.agents/DERIVATION_COMPLETENESS_PLAN.md` (reader model, D1-D4 metrics,
severity rubric, iteration loop, compound lessons).

- Multi-agent flow: 3 parallel read-only auditors (Sections 2-3, 4-5, 6+5b)
  -> owner hand-verified every High finding against the source (2 of 5
  auditor "High" findings were false positives; recorded as a lesson) ->
  additive fixes -> novice (`Poincare`) + technical (`Gauss`) dual review ->
  3 review fixes applied -> revalidate/recompile.
- Fixed (all confirmed High gaps closed):
  - Section 3: Laplace integral definition, product-rule derivation of the
    differentiation rule, constant-function check, double application for
    second derivatives, term-by-term MSD substitution, complex
    magnitude/angle explainer.
  - Sections 2/4: term-by-term Laplace substitutions + forward pointer.
  - Section 5: characteristic-root standard-form substitution in two algebra
    pieces + numeric check + imaginary-unit factorization for omega_d.
  - Section 6: force-to-acceleration derivation of J M^-1 J^T and a
    directional effective-mass toy check (x: 0.5 kg, y: 1 kg) on the 5b pose.
- Guarded: 15 new `\vmark` anchors under
  `manuscript_derivation_gap_high_checkpoint`; two new numeric checkpoints
  (`charroot_standard_form_checkpoint`, `effective_mass_direction_checkpoint`)
  keep the manuscript's numeric examples machine-verified.
- Registry: added `paper_tutorial.derivation_step_completeness` durable gate
  to `.agents/VALIDATION_METRICS.yaml`.

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| LaTeX compile | exit 0 | 0 | bundled Tectonic, `tmp/latex_compile_derivation_gaps/compile_final.json` |
| Final segment warnings | all 0 | 0 citation/reference/rerun, 0 overfull/underfull | same log |
| PDF | generated | 119 pages (+1), 973262 bytes, SHA-256 `16C0DD58...53EA7883` | pypdf page count, `Get-FileHash` |
| Validation script | failures 0 | exit 0 (15/15 anchors, numeric errors 0.0) | `validate_robotics_foundations.py` |
| Citation coverage | exit 0 | 29/29 used keys, 0 duplicates | `check_citation_coverage.py` |
| Ruff (.agents) | exit 0 | all checks passed | `.venv/Scripts/ruff.exe check .agents` |
| PDF content markers | present | pages 17, 21, 51, 79 | pypdf text search |
| Visual layout | no breakage | not run (no renderer); compensated by 0 over/underfull | recorded in validation summary |
| High-severity gaps | 0 open | 0 open (4 closed by edits, 2 closed as false positives) | `.agents/DERIVATION_COMPLETENESS_PLAN.md` |

### 2026-07-05 Section 5b Density/Navigation Pass

Reviewed all rendered Section 5b pages (55--68) and applied additive-only
navigation fixes. Version label: `draft-20260705-section5b-density-nav`
(details in `.agents/PAPER_VERSION_LOG.md`).

- Finding: layout healthy overall; the suggested 2-link geometry figure
  already exists (Figures 6 and 7), so that standing suggestion is closed.
- Fixed: page 59 text wall split with `\paragraph{계산 순서.}` and
  `\paragraph{숫자로 확인.}` signposts (anchored); stranded IK-to-Jacobian
  bridge heading moved whole to page 61 top via `needspace`.
- Guarded: new `manuscript_section5b_density_nav_checkpoint` in the
  validation script.

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| LaTeX compile | exit 0 | 0 | bundled Tectonic, `tmp/latex_compile_s5b_density/compile.json` |
| Final segment warnings | all 0 | 0 citation/reference/rerun, 0 overfull/underfull | same log |
| PDF | 118 pages | 118 pages, 961293 bytes | bundled pypdf |
| Validation script | failures 0 | exit 0 (incl. new checkpoint) | `validate_robotics_foundations.py` |
| Visual layout | no stranded heading, no clipping | pages 59/60/61 rendered and inspected | Poppler PNG inspection |

### 2026-07-05 Test Coverage Baseline Pass

Measured the simulator coverage baseline and turned it into an enforced
regression floor.

- Baseline: 84 percent statement coverage of `src/mclab` (11,212 statements,
  1,795 missed) with all 340 tests + 760 subtests passing.
- Added `pytest-cov` to the dev extras in `pyproject.toml`.
- CI simulator job now runs `pytest --cov=mclab --cov-fail-under=80`; the
  floor is 80 percent to absorb platform-specific branch differences on
  Linux runners while still catching real regressions.
- Registered the gate in `.agents/VALIDATION_METRICS.yaml` under
  `code_quality.coverage`.

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| Coverage baseline | recorded | 84 percent (11,212 stmts) | `pytest --cov=mclab --cov-report=term` |
| Coverage floor | >= 80 percent | enforced in CI | `.github/workflows/ci.yml` simulator job |
| Tests | exit 0 | 340 passed + 760 subtests | same run |

### 2026-07-05 Stable Marker Anchor Migration Pass

Converted the fragile phrase-count manuscript gates to durable anchors,
unblocking the planned compression pass. Version label:
`draft-20260705-vmark-stable-anchors` (details in
`.agents/PAPER_VERSION_LOG.md` and
`.agents/validation/robotics_foundations_validation_summary.yaml`).

- Added `\newcommand{\vmark}[1]{}` to `paper/main.tex` with a durability
  comment; anchors expand to nothing in the PDF.
- Inserted 85 anchor lines (`\vmark{key}%`) directly below their tracked
  content (69 in Section 5b, 13 in Section 6, 2 in Appendix A, 1 in the
  Introduction). No prose changed; PDF stays 118 pages.
- Rewrote the ten `manuscript_*_marker_checkpoint` functions in
  `validate_robotics_foundations.py` to count anchors; forbidden stale-phrase
  absence checks and the `configuration space`/`C-space` vocabulary-frequency
  checks stay literal.

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| Anchor migration | 85 anchors, 0 missing phrases | 85 inserted, 0 missing | migration script output |
| LaTeX compile | exit 0 | 0 | bundled Tectonic via `compile_latex.py` |
| Final segment warnings | 0 citation/reference/rerun, 0 overfull/underfull | 0/0/0, 0/0 | `tmp/latex_compile_vmark_migration/compile.json` |
| PDF | 118 pages | 118 pages, 961208 bytes | bundled pypdf page count |
| Validation script | failures 0 | exit 0 | `validate_robotics_foundations.py` |
| Negative test | deleting one anchor fails the gate | delete -> exit 1, restore -> exit 0 | scratch negative test on `traj-trapezoid-default` |
| Citation coverage | exit 0 | 29/29 used keys, 0 duplicates | `check_citation_coverage.py` |
| Ruff | exit 0 | 0 errors | `python -m ruff check .agents` |

### 2026-07-04 Agent System Hardening Pass

This pass reviewed and hardened the agent operating system itself (skills,
harness, guardrails, records). Full review: `.agents/AGENT_SYSTEM_REVIEW.md`.

Implemented:

- Added GitHub Actions CI (`.github/workflows/ci.yml`) with three jobs:
  `simulator` (ruff + pytest with sparse-checkout Menagerie Panda cache),
  `paper-gates` (citation coverage + formula/marker validation),
  `paper-build` (Tectonic build + PDF artifact upload).
- Added portable `.agents/validation/check_citation_coverage.py` (stdlib only)
  replacing the PowerShell-only citation check; wired into CI and paper/README.md.
- Split records: `.agents/CURRENT_STATE.md` now keeps only the latest snapshot;
  the full previous content is archived verbatim in
  `.agents/archive/CURRENT_STATE_ARCHIVE_20260704.md`. `VALIDATION_METRICS.yaml`
  was trimmed from 557 to 183 lines (durable gates only); historical
  pass-specific gates live in `.agents/archive/VALIDATION_METRICS_HISTORY.yaml`.
- Mirrored the 48 agent skills from `~/.codex/skills` into `.agents/skills/`
  (vendor `.system` excluded; secret scan clean) so the operating system is
  self-contained after a clone. Fixed the `C:/Users/...` evidence path in the
  metrics registry.
- Documented skills location, state-record policy, and CI enforcement in
  `.agents/OPERATING_SYSTEM.md`; added portable `tectonic` build command to
  `paper/README.md`.
- Removed the single ruff F841 in `validate_robotics_foundations.py`.
- Cross-platform fixes found by the first CI run (this pass intentionally
  edited simulator source and tests here, scoped to portability):
  `_discover_runs` in `src/mclab/sim/reporting.py` now skips sibling
  directories that raise `OSError` (unreadable systemd private /tmp trees on
  Linux made outputs-index generation crash); two `test_learner_menu.py`
  path-parsing tests now build their input with `pathlib.Path` instead of
  hard-coded Windows backslash strings.
- Intentionally deferred: converting manuscript marker checks from phrase
  counting to stable keys (needs a manuscript+rebuild iteration before the
  compression pass); preserving reviewer full texts from future review passes.

Validation evidence:

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| Ruff (whole repo) | exit 0 | 0 errors | `python -m ruff check .` |
| Citation/provenance coverage | exit 0 | 29/29 used keys present, 0 duplicates | `python .agents/validation/check_citation_coverage.py` |
| Formula/marker validation | failures 0 | exit 0 | `python .agents/validation/validate_robotics_foundations.py` |
| Pytest | exit 0 | 340 passed + 760 subtests | `python -m pytest -q` |
| Metrics registry YAML | parses | valid, 13 top-level sections | `yaml.safe_load` |
| Skills mirror | 48 skills, no secrets | 48 dirs / 96 files, secret scan clean | `.agents/skills/` |

Latest robotics-foundation Section 6 Effort/Torque Scope Pass used two focused read-only review agents:

- Novice reviewer `Poincare`: found that a beginner could be mildly confused when Section 6 returns to torque-only wording after Section 5b generalized \(\bm\tau\) as joint effort.
- Technical reviewer `Gauss`: recommended preserving torque-control implementation wording while changing the generic Jacobian recap wording to `관절 effort`.

Implemented in this iteration:

- Updated `paper/sections/01_introduction.tex`:
  - Changed the robotics-foundation roadmap item from `힘-토크 변환` to `힘--관절 effort 변환`.
- Updated `paper/sections/06_impedance_control.tex`:
  - Added a scope note that \(\bm\tau\) is generally generalized joint effort, while this section's revolute-joint implementation reads that effort as torque.
  - Changed the Jacobian recap sentence and table row to force-to-joint-effort wording.
  - Changed the generic Cartesian-impedance mapping paragraph to `관절 effort`, then narrowed the 2-DoF revolute example back to joint torque.
  - Preserved `토크 제어 구현`, `eq:cartesian_to_joint_torque`, and the Lab04 caveat that it is not complete operational-space impedance validation.
- Updated `paper/sections/A_notation_checklist.tex`:
  - Changed the beginner glossary row to `자코비안 전치와 힘--관절 effort 변환`.
- Updated `.agents/validation/validate_robotics_foundations.py`:
  - Added `manuscript_section6_effort_torque_scope_marker_checkpoint`.
  - Checks Section 6 effort-scope markers, preserved torque-control context, and absence of old Section 6/appendix/introduction force-torque-transform markers.
- Updated `.agents/validation/robotics_foundations_validation_summary.yaml`, `.agents/PAPER_VERSION_LOG.md`, `.agents/VALIDATION_METRICS.yaml`, `.agents/ROBOTICS_FOUNDATIONS_TRACEABILITY.md`, `.agents/ROBOTICS_FOUNDATIONS_COMPLETION_AUDIT.md`, and `.agents/ROBOTICS_FOUNDATIONS_PLAN.md` for this version.
- This pass intentionally edited paper text and `.agents/` validation/state/version records only. Simulator source, configs, models, and tests were not intentionally edited.

Latest validation evidence:

| Gate | Threshold | Measured | Evidence |
|---|---:|---:|---|
| Main reflection | latest paper version reflected through main | `paper/main.tex` includes introduction, Section 5b, Section 6, and Appendix A; source has Section 6 effort/torque scope markers | `.agents/validation/robotics_foundations_validation_summary.yaml` |
| LaTeX compile | exit code 0 | 0 | bundled Tectonic via `compile_latex.py --compiler tectonic` |
| Final citation/reference/rerun warnings | 0 | 0/0/0 | final TeX segment parsed from `tmp\latex_compile_section6_effort_scope_pass\compile.json` before cleanup |
| Final overfull/underfull boxes | 0 | overfull 0, underfull 0 | final TeX segment |
| Remaining font warning | known residual only | 2 | Korean italic substitution in bibliography |
| PDF generated | present | 118 pages, 961187 bytes, SHA-256 `75EA71A0AE0F967A39C29EB65DF5D8967FAB16CC84869A7BF6E7C4CF7A0D99AD` | `paper/main.pdf`; `Get-FileHash`; Poppler `pdfinfo.exe` |
| Durable formula/source script | failures 0 | 0 | `.agents/validation/validate_robotics_foundations.py` |
| Section 6 effort/torque scope markers | required present, forbidden absent | required markers >= 1; old Section 6/appendix/introduction force-torque markers 0; valid 6D wrench caveat preserved | `manuscript_section6_effort_torque_scope_marker_checkpoint` |
| PDF markers | present | Section 6 scope/table page 81; generalized-effort continuation page 82; Appendix A glossary page 110 | bundled Python/pypdf marker check |
| Visual layout | no clipping, overlap, or severe crowding | rendered PDF pages 81, 82, 109, and 110 inspected | Poppler `pdftoppm.exe` PNG inspection before cleanup |
| Version record | current manuscript state labeled | `draft-20260703-section6-effort-torque-scope` | `.agents/PAPER_VERSION_LOG.md` |

### Commands run

```powershell
python .agents\validation\validate_robotics_foundations.py
python C:\Users\ycpig\.codex\plugins\cache\openai-bundled\latex\0.2.4\scripts\compile_latex.py C:\Users\ycpig\manipulator-control-tutorial\paper\main.tex --compiler tectonic --output-directory C:\Users\ycpig\manipulator-control-tutorial\paper --json > tmp\latex_compile_section6_effort_scope_pass\compile.json 2> tmp\latex_compile_section6_effort_scope_pass\compile.err
Bundled Python/pypdf marker checks for latest paper/main.pdf pages 81, 82, and 110
Poppler pdftoppm.exe for latest paper/main.pdf pages 81, 82, 109, and 110
```


## Archived Records

Older pass records (2026-06-27 through 2026-07-03) were moved verbatim to
`.agents/archive/CURRENT_STATE_ARCHIVE_20260704.md`. Keep this live file at the
latest snapshot only; archive before it grows past roughly 500 lines.

## Known Residual Risks

- Tectonic's JSON output can include first-pass undefined-citation and undefined-reference warnings before the automatic rerun; the final PDF is generated successfully.
- Korean italic font substitution remains in bibliography output from the default font shape.
- Section 6 is intentionally long and tutorial-style. A later compression pass should tighten repetition, shorten tables, and move some explanatory material to an appendix if targeting formal publication.
- The paper figures are conceptual teaching figures, not simulator validation outputs.
- `paper/` and `.agents/` are now tracked in git (commit `8b3b7aa`, merged to main via PR #1). Generated `paper/main.pdf`, LaTeX intermediates, and `paper/references/papers/*.pdf` remain ignored.
- Manuscript content gates now use `\vmark{key}` anchors (85 total). Anchors
  must move with their content during rewrites; deleting one without retiring
  its gate fails validation. Editors compressing sections must carry anchors
  into the surviving text.
- The two vocabulary-frequency checks (`configuration space` >= 2, `C-space`
  >= 1) are still literal term counts by design; heavy compression of that
  subsection could underrun them.
- Paper validation scratch such as `tmp/latex_compile_*` and `tmp/pdfs/*_review` is local-only. Remove only artifacts created by the active pass after path verification. Existing local `tmp/index.html` and Lab03 retarget-check artifacts remain because they were not created by this pass and may be user-authored or from another workflow.
- Two BibTeX entries remain uncited intentionally for possible advanced related-work expansion or later pruning: `howell2022predictivesampling` and `mistry2011operationalspace`.

## Historical Next Recommended Action (2026-07-04)

The manuscript DoD is complete, so per `.agents/SUBMISSION_PLAN.md` the
derivative-writing track is unblocked. Next loop iteration: draft U3 (the
KROS-targeted Korean review, 10-15 pages derived from Sections 2-5) as a
separate LaTeX document — submission itself still waits on the A1 editorial
inquiry and B1 membership (user actions). JOSE submission waits only on C4
(author name/ORCID) plus the A3 policy check. Keep CI green; carry no
anchors into derivative files (anchor gates apply to the canonical
manuscript only, per plan G6).
