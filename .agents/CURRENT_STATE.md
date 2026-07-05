# Current State

Updated: 2026-07-05 21:40 KST

## Current Objective

Iteratively improve the Korean review/tutorial paper on impedance, impedance control, Modern Robotics foundations, and the MuJoCo educational lab so that beginners can follow the history, intuition, equations, kinematics, trajectories, force/torque mapping, and control meaning before a later compression pass. Use multi-agent review, keep the simulator content untouched unless explicitly requested, reflect every manuscript version through `paper/main.tex`, and keep measurable validation, version logs, and state records durable.

## Current Manuscript State

- Main source: `paper/main.tex`
- Section sources: `paper/sections/*.tex`
- Current focus sources: `paper/sections/01_introduction.tex`, `paper/sections/02_impedance.tex`, `paper/sections/04_electric_system.tex`, `paper/sections/05_mechanical_system.tex`, `paper/sections/05b_robotics_foundations.tex`, `paper/sections/06_impedance_control.tex`, `paper/sections/07_mujoco_lab_design.tex`, `paper/sections/08_discussion.tex`, `paper/sections/09_conclusion.tex`, `paper/sections/A_notation_checklist.tex`, `paper/main.tex`, `paper/figures/*.tex`, and `.agents/*`
- Bibliography: `paper/references/refs.bib`
- Latest PDF: `paper/main.pdf`
- Current length: 120 PDF pages
- Latest PDF size: 976795 bytes

## Completed Since Last Snapshot

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

## Next Recommended Action

Continue the derivation-completeness loop from
`.agents/DERIVATION_COMPLETENESS_PLAN.md`: all High items and the top Medium
items (C2, B4, B6) are closed. The next iteration should take the remaining
Medium items (C3 trajectory product-rule step, C4 m_d normalization, A5-A8
complex-variable/convolution introductions), each hand-verified before
editing. Keep CI green as the standing gate. The later compression pass must carry the 15 new derivation anchors
into surviving text. Preserving reviewer full texts under `.agents/reviews/`
should start with the next review pass.
