# Enterprise Readiness Audit and Handoff — 2026-07-20

Snapshot status: verified, read-only

Authoritative ref: `origin/main@44b1937f3d34dcb5672b5aedc1df13fa55dfeaad`

Audited local ref: `025ff738fc56f5e66877c72ffd6dfc64a768e56b`

Scope: product, code, QA, UX, security, compliance, release, operations,
pedagogy, publication, and documentation

## Current objective

1. Preserve this audit so a later session can resume without reconstructing it.
2. Improve the Korean and English README and newcomer information architecture.
3. Only then address the audit findings, starting with the P0 safety issues.

## Current state

| Intended use | Decision |
|---|---|
| Supervised Linux classroom/demo | Conditional GO |
| Limited technical preview | Conditional GO |
| General public beta | NO-GO |
| Signed multi-platform production release | NO-GO |
| Paper/DOI publication | Technical base ready; administrative and release work remains |

The supervised demo condition is: use a pre-verified machine and trusted
configs, prepare a headless/report fallback, and do not use `mclab clean`
until P0-01 is fixed.

## Completed since the previous snapshot

- Audited the latest remote main across product, code, QA, UX, security,
  compliance, release engineering, operations, pedagogy, publication, and
  documentation.
- Verified the latest main CI and three-OS unsigned desktop workflow.
- Reproduced the CLI cleanup selection logic without deleting files.
- Checked repository protection, dependency/security monitoring, release/tag
  state, bundled license files, local dependency health, type checking, and
  current worktree divergence.
- No source files were changed during the audit.

## Verified strengths

- Latest main CI passed: 437 passed, 2 skipped, 1,088 subtests, Ruff clean,
  81.02% reported statement coverage.
- The desktop matrix passed on Ubuntu 24.04, macOS 15, and Windows Server 2025:
  93 tests and 311 subtests per OS, plus packaged self-test and `doctor`.
- MuJoCo, YAML configuration, CSV/NPZ logging, plots, reports, worksheets, and
  replay form one consistent experiment pipeline.
- The Panda asset installer pins a Menagerie commit and archive SHA-256,
  rejects unsafe archive members, and preserves the model license.
- No committed credential candidate or remote application telemetry was found.
- Linux UI, report accessibility, restart, cancellation, and full-comparison
  automation are unusually extensive for a project at this stage.

## Blockers and risks

### P0-01 — Unsafe CLI cleanup

`src/mclab/cli.py::_clean_outputs` treats every direct child directory of an
arbitrary `--output-dir` as a run, sorts by name, and recursively deletes the
remainder with errors ignored. Its tests use only timestamp-named run folders.

Read-only simulation against the current `outputs/`:

- 491 directories total;
- default `--keep 20` selects 471 for deletion;
- all 18 learner-output directories are selected;
- the 20 retained directories are internal verification outputs.

Required fix:

1. Restrict cleanup to a validated MCLab outputs root or explicit marker.
2. Select only valid run manifests; exclude internal verification directories.
3. Reject home, workspace, repository, and other broad roots.
4. Add dry-run and exact-path confirmation.
5. Prefer recoverable deletion and verify each result instead of using
   `ignore_errors=True`.
6. Add mixed learner/internal/invalid-directory regression tests.

### P0-02 — Desktop course-completion evidence mismatch

`course_progress_payload` currently counts any saved manifest with
`status == "completed"`. The scenario catalog separately declares plot,
learner-control, and observation requirements, while the legacy learner-menu
path checks those evidence requirements. A hands-on run can therefore advance
desktop course progress without the evidence promised by the product.

Required fix: introduce one shared completion evaluator and use it in the
desktop app, learner menu, CLI, outputs index, reports, and tests.

### P0-03 — No clean release-candidate baseline

At audit time the active local branch was eight commits behind
`origin/main`, three behind its own upstream, and contained unrelated
uncommitted packaging and font work. Do not release or bulk-merge that
worktree. Reapply only intended changes onto a clean branch from current main.

### P0-04 — Distribution compliance and signing are incomplete

The desktop workflow deliberately uploads unsigned development folders for
seven days. There are no signed installers, macOS notarization, immutable
release artifacts, checksums, SBOM, provenance, or rollback package. The
bundle also lacks a complete third-party notice/license inventory, including
an explicit Qt/PySide LGPL compliance plan.

### P0-05 — Repository and supply-chain controls are incomplete

At audit time:

- main branch protection/rulesets were absent;
- Dependabot vulnerability alerts were disabled;
- no dependency lock/constraints file existed;
- Actions used mutable major-version tags instead of commit SHAs;
- the simulator CI cloned the current Menagerie HEAD rather than using the
  pinned verified installer;
- there were no GitHub tags or releases.

## Important non-blocking work

### P1 — Public-beta readiness

- Run packaged end-to-end flows on each target OS: experiment, evidence,
  report, replay, next step, comparison cancellation, and child cleanup.
- Test actual Windows 11 and macOS arm64/Intel hardware, real GPU drivers,
  200% OS scaling, and repeated restarts.
- Complete NVDA, VoiceOver, Orca, keyboard-focus, low-vision, and color-vision
  human checks.
- Conduct a beginner think-aloud/SUS study with at least six participants.
- Lock runtime/build dependencies and add vulnerability and license scanning.
- Add branch protection, required checks/review, CODEOWNERS, SECURITY.md, and
  commit-SHA-pinned Actions.
- Resolve the documented 300 MB compressed target versus the 400 MB
  uncompressed build gate and its stale 300 MB error text.

### P2 — Maintainability, teaching operations, and publication

- Current local mypy baseline: 225 errors across 20 files; adopt an incremental
  gate instead of enabling it all at once.
- Split very large modules such as `sim/reporting.py` and
  `learner_menu.py` along tested boundaries.
- Reconcile the Pydantic recommendation in the development specification with
  the current dict/manual YAML validation approach.
- Complete Korean report localization and correct fixed English HTML language
  metadata.
- Expand the educator guide with lesson plans, timing, rubric, accessibility
  fallback, and submission-verification guidance.
- Add local-data/privacy guidance for learner notes and shared classroom PCs.
- Update stale publication/state claims, the JOSE test count and submission
  date, then create a release before requesting a Zenodo DOI.

## Open decisions

1. Target distribution level: supervised classroom, public beta, or signed
   production.
2. Whether Windows and Apple signing credentials will be acquired now.
3. Whether to recruit the first beginner usability cohort before public beta.
4. Whether course completion means “run succeeded” or “required learning
   evidence was saved.” The existing product language supports the latter.
5. Timing of journal inquiries and the first immutable GitHub/Zenodo release.

## Artifacts and paths

- CLI cleanup: `src/mclab/cli.py`
- Cleanup tests: `tests/test_cli_imports.py`
- Internal-output filter: `src/mclab/output_filters.py`
- Desktop progress: `src/mclab/application/presentation.py`
- Completion rules: `src/mclab/application/catalog.py`
- Existing strict evidence logic: `src/mclab/learner_menu.py`
- Evidence entry rules: `src/mclab/application/qt_evidence.py`
- Desktop workflow: `.github/workflows/desktop.yml`
- Main CI: `.github/workflows/ci.yml`
- Packaging policy: `docs/installation.md`
- UI validation and remaining human gates: `docs/ui_validation.md`
- User/external actions: `.agents/USER_ACTIONS.md`

GitHub evidence:

- CI: <https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29713313435>
- Desktop matrix: <https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29713313420>

## Revalidation commands

```bash
git fetch --prune origin
git status --short --branch
git rev-list --left-right --count HEAD...origin/main

gh run view 29713313435 --repo ycpiglet/manipulator-control-tutorial
gh run view 29713313420 --repo ycpiglet/manipulator-control-tutorial
gh api repos/ycpiglet/manipulator-control-tutorial/branches/main/protection
gh api repos/ycpiglet/manipulator-control-tutorial/dependabot/alerts
gh release list --repo ycpiglet/manipulator-control-tutorial

python -m pytest -q --cov=mclab
python -m mypy src/mclab
python -m pip check
pipx run pip-audit --path .venv/lib/python3.10/site-packages --skip-editable
```

Do not run `mclab clean` as part of revalidation before P0-01 is fixed.

## Ordered next actions

1. Improve the Korean and English README and newcomer-facing repository map.
2. Fix P0-01 and P0-02 with regression tests.
3. Create a clean release-candidate branch from current main.
4. Add packaged end-to-end release gates.
5. Complete third-party notices, dependency locking, supply-chain controls,
   signing/notarization, immutable releases, and rollback.
6. Run real-platform accessibility and beginner learning validation.
