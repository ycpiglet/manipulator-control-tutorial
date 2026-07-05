# Paper Version Log

This file records manuscript-facing draft states. It complements
`.agents/CURRENT_STATE.md` by keeping durable paper version labels, source/PDF
paths, change intent, verification, and open risks.

## draft-20260705-derivation-gaps-medium2

- Type: derivation-completeness pass (remaining Medium tier) over Sections
  2, 3, 4, 5b, 6
- Main source: `paper/sections/02_impedance.tex`, `03_lti_system.tex`,
  `04_electric_system.tex`, `05b_robotics_foundations.tex`,
  `06_impedance_control.tex`
- Main PDF: `paper/main.pdf`
- Plan/backlog record: `.agents/DERIVATION_COMPLETENESS_PLAN.md` (Iteration 3)
- Version purpose:
  - Exhaust the Medium tier of the derivation backlog: A5 (imaginary-unit
    first-use definition), A6 (sinusoid velocity derivative + RLC series-sum
    bridge), A7 (charge-current correspondence), B5 (undamped-solution
    substitution check), C3 (trajectory product-rule origin), C4 (impedance
    error normalization). A8 was already resolved by the iteration-1 Laplace
    definition insert.
- Major changes represented (additive only): 7 short derivation bridges,
  each anchored; 7 new `\vmark` anchors under
  `manuscript_derivation_gap_medium2_checkpoint`.
- Review: combined reviewer `Noether` — all 7 items CORRECT/FOLLOWABLE, no
  duplication (forward-first j definition accepted).
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0 (bundled Tectonic)
  - Final segment citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - PDF: `paper/main.pdf`, 120 pages (unchanged), 979698 bytes
  - PDF SHA-256: `22DBA0FD376B75EF99E4BB124A4266B2D02286DAA327EF5979CAB9480B47761C`
  - Validator: exit 0, failures 0 (7/7 new anchors present)

## draft-20260705-derivation-gaps-medium1

- Type: derivation-completeness pass (top Medium items) over Sections 4--6
- Main source: `paper/sections/04_electric_system.tex`,
  `05_mechanical_system.tex`, `06_impedance_control.tex`
- Main PDF: `paper/main.pdf`
- Plan/backlog record: `.agents/DERIVATION_COMPLETENESS_PLAN.md` (Iteration 2)
- Version purpose:
  - Continue the derivation-completeness loop: close backlog items C2
    (serial robot/environment stiffness force split), B4 (RLC damping-ratio
    isolation algebra), and B6 (overshoot substitution example).
- Audit verification before editing:
  - C2 confirmed (equations absent); B4 partially confirmed (only the zeta
    isolation step missing); B6 mostly a false positive (numeric examples
    and the ln 50 log step already exist; only the M_p(0.7) substitution
    was unexpanded).
- Major changes represented (additive only):
  - Section 6: series-stiffness balance equations, combined-stiffness
    derivation, and the 5 N / 10 N numeric contrast tied to the existing
    500 N/m, 2 cm example.
  - Section 4: four-step isolation of \(\zeta=(R/2)\sqrt{C/L}\) from the
    velocity-term comparison.
  - Section 5: explicit substitution chain for \(M_p(\zeta=0.7)\approx4.6\%\).
  - 4 new `\vmark` anchors under `manuscript_derivation_gap_medium_checkpoint`;
    numeric validator checkpoints `series_stiffness_checkpoint` and
    `overshoot_formula_checkpoint`.
- Review: combined reviewer `Euler` — all technical items CORRECT, all
  passages FOLLOWABLE, no duplication with surrounding prose.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0 (bundled Tectonic)
  - Final segment citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - PDF: `paper/main.pdf`, 120 pages (was 119), 976795 bytes
  - PDF SHA-256: `70A0F58BED3A7DD74E8902DC76B7A3FE1FFFA6857DA33239CBEEADA02583FDF9`
  - Validator: exit 0, failures 0 (after widening the rigid-limit tolerance
    to absorb the finite 1e9 N/m proxy's ~5e-6 N asymptotic residual)

## draft-20260705-derivation-gaps-high

- Type: derivation-completeness pass (High-severity gaps) over Sections 2--6
- Main source: `paper/main.tex`, `paper/sections/02_impedance.tex`,
  `03_lti_system.tex`, `04_electric_system.tex`, `05_mechanical_system.tex`,
  `06_impedance_control.tex`
- Main PDF: `paper/main.pdf`
- Plan/backlog record: `.agents/DERIVATION_COMPLETENESS_PLAN.md`
- Version purpose:
  - Execute the standing beginner-accessibility goal: expand every
    High-severity derivation jump (steps a high-schooler/first-year/non-major
    cannot follow without external material) directly in-text.
- Audit findings (3 parallel read-only auditors, then hand-verified):
  - Confirmed High: Laplace integral definition absent from the whole paper
    and differentiation rule used underived (A1+B1); characteristic-root
    standard-form substitution skipped (B2); workspace inertia
    \(\bm{\Lambda}=(\bm{J}_v\bm{M}_q^{-1}\bm{J}_v^{\mathsf{T}})^{-1}\)
    presented without derivation (C1).
  - False positives closed without edits: telegrapher partial-derivative
    intuition (A2) and final-value-theorem conditions (A3) already exist.
  - Medium backlog (A5-A8, B4-B7, C2-C5) recorded for later iterations.
- Major changes represented (additive only; no prose deleted):
  - Section 3: new `\paragraph{라플라스 변환의 정의.}` with the integral
    definition, a product-rule derivation of
    \(\mathcal{L}\{\dot{x}\}=sX(s)-x(0)\), a constant-function check
    (\(X(s)=1/s\)), double application for \(\ddot{x}\), term-by-term
    substitution into the MSD equation, and a complex magnitude/angle
    explainer with the \(H=1-\jj\) example.
  - Section 2: forward pointer at first \(\mathcal{L}\) use; term-by-term
    velocity-based substitution before the mechanical impedance result.
  - Section 4: term-by-term Laplace substitution for the RLC equation.
  - Section 5: two-piece algebra expansion of the characteristic-root
    substitution (\(-b/2m=-\zeta\omega_n\); \(b^2-4mk=4mk(\zeta^2-1)\)),
    numeric check (m=1, b=2, k=4), and explicit
    \(\sqrt{\zeta^2-1}=\jj\sqrt{1-\zeta^2}\) factorization for \(\omega_d\).
  - Section 6: force-to-acceleration derivation of
    \(\bm{J}_v\bm{M}_q^{-1}\bm{J}_v^{\mathsf{T}}\) and a directional
    effective-mass toy check on the Section 5b two-link pose
    (\(m_{\mathrm{eff},x}=0.5\), \(m_{\mathrm{eff},y}=1\)).
  - 15 new `\vmark` anchors; new validator checkpoints
    `manuscript_derivation_gap_high_checkpoint`,
    `charroot_standard_form_checkpoint`,
    `effective_mass_direction_checkpoint`.
- Review: novice reviewer `Poincare` (4 findings, 3 applied), technical
  reviewer `Gauss` (all 6 items CORRECT).
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0 (bundled Tectonic)
  - Final segment citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0 (2 known Korean italic font warnings)
  - PDF: `paper/main.pdf`, 119 pages (was 118), 973262 bytes
  - PDF SHA-256: `16C0DD5892583640B5729FEE6D42CF62ECC5B2D7E44A6FDE66391BCC53EA7883`
  - Validator: exit 0, failures 0 (all 15 new anchors present, numeric
    checkpoint errors 0.0)
  - Citation coverage: 29/29 used keys, 0 duplicates
  - PDF content markers via pypdf: pages 17, 21, 51, 79
  - Visual layout: renderer unavailable this session; compensated by 0
    overfull/underfull boxes and additive-only edits

## draft-20260705-section5b-density-nav

- Type: page-density/navigation pass over Section 5b (PDF pages 55--68)
- Main source: `paper/main.tex`, `paper/sections/05b_robotics_foundations.tex`
- Main PDF: `paper/main.pdf`
- Version purpose:
  - Execute the standing next-action item: review Section 5b rendered pages
    for density and navigation before the compression pass.
- Review findings (rendered-page inspection of pages 55--68):
  - Overall layout healthy: tables 16--22 and figures 5--8 break up density;
    no clipping or overfull boxes.
  - The previously suggested small 2-link geometry figure already exists as
    Figure 6 (IK branches) and Figure 7 (Jacobian columns); no new figure
    needed.
  - Page 59 was the densest full-text page: IK branch caveats, calculation
    order, and the numeric example ran together without visual anchors.
  - The `IK에서 자코비안으로 넘어가는 다리` paragraph heading started two
    lines from the bottom of page 60 and broke across the page turn.
- Major changes represented (additive only; no prose reworded):
  - Added `\paragraph{계산 순서.}` and `\paragraph{숫자로 확인.}` signposts on
    page 59 with new anchors `ik-branch-calculation-order` and
    `ik-branch-numeric-example`.
  - Added `\usepackage{needspace}` and `\needspace{4\baselineskip}` before the
    IK-to-Jacobian bridge heading, which now starts complete at the top of
    page 61.
  - Added `manuscript_section5b_density_nav_checkpoint` to
    `validate_robotics_foundations.py` guarding the two new anchors.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0 (bundled Tectonic)
  - Final segment citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - PDF: `paper/main.pdf`, 118 pages (unchanged), 961293 bytes
  - Validation script exit 0 with the new density-nav checkpoint enforced
  - Rendered pages 59, 60, 61 inspected: signposts render, no stranded
    heading, no awkward bottom gap on page 60

## draft-20260705-vmark-stable-anchors

- Type: validation-harness migration with output-neutral manuscript anchors
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Convert all 85 required manuscript content markers in
    `validate_robotics_foundations.py` from exact Korean phrase counts to
    `\vmark{key}` anchor checks so the planned compression pass can reword
    prose without breaking validation.
  - Keep forbidden stale-phrase absence checks and the two
    vocabulary-frequency checks (`configuration space`, `C-space`) as literal
    text checks.
- Major changes represented:
  - Added `\newcommand{\vmark}[1]{}` to the `main.tex` preamble with a
    durability comment (anchors move with content; deletion requires retiring
    the corresponding gate).
  - Inserted 85 anchor lines (`\vmark{key}%`) directly below their tracked
    content: 69 in Section 5b, 13 in Section 6, 2 in Appendix A, 1 in the
    Introduction. No prose was changed.
  - Rewrote the ten `manuscript_*_marker_checkpoint` functions to count
    anchors instead of phrases; `main()` thresholds unchanged.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0 (bundled Tectonic)
  - Final segment citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: Korean italic bibliography substitutions only
  - PDF: `paper/main.pdf`, 118 pages (unchanged), 961208 bytes
  - Validation script exit 0; negative test: deleting one anchor makes the
    script exit 1, restoring it returns exit 0
  - Citation/provenance coverage: 29/29 used keys, 0 duplicates

## draft-20260703-section6-effort-torque-scope

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Carry the generalized joint-effort convention from Section 5b into the Section 6 Jacobian recap.
  - Prevent beginners from reading \(\bm{\tau}=\bm{J}_v^{\mathsf T}\bm f\) as torque-only before the text narrows to revolute-joint examples.
  - Preserve implementation-facing phrases such as `토크 제어 구현` and the Lab04 non-operational-space-validation caveat.
- Major changes represented:
  - Updated `paper/sections/01_introduction.tex` so the roadmap says `힘--관절 effort 변환`.
  - Added a Section 6 scope note: \(\bm{\tau}\) is generally generalized joint effort, while this section's revolute-joint torque-control implementation reads that effort as torque.
  - Changed the Section 6 Jacobian recap sentence and table row from force-to-torque wording to force-to-joint-effort wording.
  - Changed the following Cartesian-impedance paragraph so generic \(\bm{J}_v^{\mathsf T}\bm f\) output is `관절 effort`, then narrowed the 2-DoF revolute example back to joint torque.
  - Updated Appendix A's beginner glossary row from `힘--토크 변환` to `힘--관절 effort 변환`.
  - Added `.agents/validation/validate_robotics_foundations.py` checkpoint `manuscript_section6_effort_torque_scope_marker_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 118 pages, 961187 bytes
  - PDF SHA-256: `75EA71A0AE0F967A39C29EB65DF5D8967FAB16CC84869A7BF6E7C4CF7A0D99AD`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Section 6 effort/torque scope checkpoint: required markers present; old Section 6/appendix/introduction force-torque-transform markers absent; valid 6D wrench phrase preserved
  - PDF markers: Section 6 scope/table page 81, generalized-effort continuation page 82, Appendix A glossary page 110
  - Visual layout: rendered PDF pages 81, 82, 109, and 110 inspected; no clipping, overlap, or severe crowding
- Open issues:
  - The equation label `eq:cartesian_to_joint_torque` is preserved for compatibility, even though the surrounding explanation now scopes \(\bm{\tau}\) as generalized effort before narrowing to revolute torque.
  - Section 6 remains long and tutorial-style; compress only after a concrete reader-density finding.
- Next draft target:
  - Continue with small, measurable terminology/scope fixes if another concrete beginner confusion appears.
  - Otherwise plan a later Section 6 consolidation pass that preserves the new generalized-effort bridge.

## draft-20260703-generalized-effort-bridge

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Keep Section 5b consistent with its earlier definition of \(\bm{\tau}\) as generalized joint effort.
  - Prevent generic \(\bm{J}^{\mathsf T}\bm f\) bridge sentences from implying that every joint component is a torque.
  - Preserve the beginner intuition that revolute-joint effort is torque and prismatic-joint effort is axis force.
- Major changes represented:
  - Reworded generic force-mapping sentences in `paper/sections/05b_robotics_foundations.tex` from `관절 토크` / `힘-토크 변환` to `관절 effort` / `힘--관절 effort 관계`.
  - Reworded the final contact bridge flow to `\(\bm{J}^{\mathsf T}\)` through joint effort and `관절 effort 피크`.
  - Left explicitly qualified revolute-joint torque examples and the `힘과 토크` subsection title intact.
  - Added `.agents/validation/validate_robotics_foundations.py` checkpoint `manuscript_generalized_effort_bridge_marker_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Final float-specifier warnings: 0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 118 pages, 960358 bytes
  - PDF SHA-256: `A728EAEF6B6B6A4A06CBCB9CA522B9067FC7223FED63488F139810D57E6A0BE1`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Generalized-effort bridge marker checkpoint: 9 required markers present and 6 old generic torque-overreach markers absent in Section 5b
  - PDF markers: DLS force-effort handoff page 63, force/effort derivation page 64, closing bridge page 68
  - Visual layout: rendered PDF pages 63, 64, and 68 inspected; no clipping, overlap, or severe crowding
- Open issues:
  - Section 6 still uses torque-control wording in implementation-facing contexts. This pass intentionally scoped the cleanup to Section 5b, where revolute/prismatic generalized effort had just been defined.
  - Section 5b remains long; avoid adding more theory unless a concrete skipped-step issue is found.
- Next draft target:
  - If reviewing Section 6 next, decide whether its `힘-토크 변환` table should remain torque-control-specific or be split into generalized effort plus revolute torque wording.

## draft-20260702-dls-first-use-handoff-clarity

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Make the Section 5b opening roadmap self-contained by expanding the first use of DLS as `감쇠 최소제곱(DLS)`.
  - Remove a small over-precise handoff phrase that could imply IK first exactly solves a single hand position before Jacobian analysis begins.
  - Preserve the intended beginner chain: target and selected current branch/posture \(\bm q\) -> \(\bm J(\bm q)\) -> velocity and force translation.
- Major changes represented:
  - Changed the first roadmap DLS sentence in `paper/sections/05b_robotics_foundations.tex` to `감쇠 최소제곱(DLS)은 특이점 근처...`.
  - Replaced `손끝 위치 하나를 맞춘 다음` with a branch/pose framing: `손끝 목표와 선택된 현재 branch의 \(\bm{q}\)를 정한 뒤`.
  - Added validator checks for the expanded DLS first-use marker, the branch-pose handoff marker, and absence of the old exact-position handoff phrase.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Final float-specifier warnings: 0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 118 pages, 960174 bytes
  - PDF SHA-256: `04A91E9B02154567D1053C101EC437CDA3E54CE7DB172F1846027937A4EF49EB`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Section reading-map marker checkpoint: `dls_expanded_first_use_marker_count=1`, `dls_relief_marker_count=1`
  - IK-to-Jacobian handoff marker checkpoint: `branch_pose_framing_marker_count=1`, `old_exact_position_handoff_count=0`
  - PDF markers: expanded DLS first use appears on page 55; branch-pose handoff appears on page 61
  - Visual layout: rendered PDF pages 55, 60, and 61 inspected; no clipping, overlap, or severe crowding
- Open issues:
  - This pass is a targeted first-use/overclaim cleanup. It does not compress Section 5b or add new simulator metrics.
  - Section 5b remains long and should be compressed only after human beginner feedback or a concrete page-density failure.
- Next draft target:
  - Continue with small skipped-step fixes when reviewers identify concrete confusion; otherwise shift to consolidation planning before adding more theory.

## draft-20260702-ik-jacobian-handoff

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Reduce page-density/navigation fatigue between the IK branch discussion and the Jacobian subsection.
  - Make explicit that later Jacobian, DLS, force, and trajectory readings start from the actually selected current branch/posture \(\bm q\).
  - Preserve the technical boundary that DLS does not magically choose an IK branch and that \(\bm J^{\mathsf T}\bm f\) is a force-to-effort relation rather than velocity inversion.
- Major changes represented:
  - Split the dense opening roadmap sentence so DLS velocity-IK relief and \(\bm J^{\mathsf T}\bm f\) force-to-effort translation are easier to read separately.
  - Added `IK에서 자코비안으로 넘어가는 다리` after the IK branch/redundancy discussion in `paper/sections/05b_robotics_foundations.tex`.
  - Explained that \(\bm J(\bm q)\), DLS, and \(\bm J^{\mathsf T}\bm f\) are evaluated from the selected current branch/posture, so branch choice can affect condition number, joint speed, and effort.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `manuscript_ik_to_jacobian_handoff_marker_checkpoint`.
  - Changed the IK reachability table float specifier from `[h]` to `[!htbp]` to remove a final TeX float warning.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Final float-specifier warnings: 0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 118 pages, 960053 bytes
  - PDF SHA-256: `8D14B72035D5D3D5C4A02FAFD5EE3A92160D423B4618C57D0CC2D7D824F46DBF`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - IK-to-Jacobian handoff marker checkpoint: all required markers count 1
  - PDF markers: handoff paragraph appears on page 60
  - Visual layout: rendered PDF pages 60 and 61 inspected; no clipping or severe crowding, and the paragraph continues naturally into the Jacobian subsection
- Open issues:
  - This pass improves navigation; it does not compress Section 5b or add new simulator metrics.
  - Section 5b remains long and should be compressed only after human beginner feedback or a concrete page-density failure.
- Next draft target:
  - Continue with small skipped-step fixes only when reviewers identify a concrete reader confusion, or begin a consolidation/readability pass that preserves the beginner derivations.

## draft-20260702-state-configuration-bridge

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Distinguish geometric configuration from control/dynamics state before the manuscript moves from joint derivatives to effort.
  - Prevent beginners from treating \(\bm q,\dot{\bm q},\ddot{\bm q},\dddot{\bm q}\) as one large configuration coordinate list.
  - Preserve the technical caveat that \((\bm q,\dot{\bm q})\) is common for simple second-order robot models, not a universal state definition.
- Major changes represented:
  - Added a state-versus-configuration bridge after `tab:joint-variable-derivatives` in `paper/sections/05b_robotics_foundations.tex`.
  - Explained that configuration is geometric posture, while a common control/dynamics state uses \(\bm q\) and \(\dot{\bm q}\).
  - Clarified that \(\ddot{\bm q}\) is usually determined by dynamics/control input and that jerk is a trajectory smoothness demand rather than a new geometric coordinate.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `manuscript_state_configuration_marker_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 117 pages, 958294 bytes
  - PDF SHA-256: `2B42FDBAF9B713ADE40BFD8F37EE8B946E5339F3777430816A10DFE985238D5F`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - State/configuration marker checkpoint: all required markers count 1
  - PDF markers: state-versus-configuration bridge appears on page 56
  - Visual layout: rendered PDF page 56 inspected; dense but legible, with no clipping or severe crowding
- Open issues:
  - This pass does not introduce a full state-space control derivation.
  - A future compression pass should preserve the distinction while shortening local prose if Section 5b becomes too long.
- Next draft target:
  - Continue only with concrete skipped-step fixes or begin a consolidation/readability pass after human reader feedback.

## draft-20260702-configuration-space-bridge

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Bridge the Modern Robotics term `configuration space` or `C-space` to the existing joint-space/task-space/workspace explanation.
  - Prevent beginners from treating C-space as a completely unrelated fourth space or from assuming it is always identical to joint space.
  - Keep the distinction scoped: fixed-base serial manipulators can usually read joint variables \(\bm q\) as the configuration vector, while larger systems may include base/object pose and constraints.
- Major changes represented:
  - Added a short C-space bridge paragraph to `paper/sections/05b_robotics_foundations.tex` in the `관절공간, 작업공간, 작업영역` subsection.
  - Clarified that task space is the selected output-variable space and workspace is the reachable set of task positions.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `manuscript_configuration_space_marker_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 117 pages, 957447 bytes
  - PDF SHA-256: `5E10AD391F03D54A8722963B5E1A0AAA0983C34C6E98DD7BDBE0416FC878A2D5`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Configuration-space marker checkpoint: `configuration space` count 4, `C-space` count 1, fixed-base serial scope count 1, not-universal-identity caveat count 1, base/object constraints caveat count 1
  - PDF markers: C-space bridge appears on page 57
  - Visual layout: rendered PDF page 57 inspected; no clipping or severe crowding
- Open issues:
  - This pass is terminology scaffolding only. It intentionally does not add mobile-base planning, obstacle C-space, object-pose planning, or collision-configuration algorithms.
  - Section 5b remains tutorial-dense; a later compression pass should preserve this bridge if formal publication length becomes tight.
- Next draft target:
  - Continue with one concrete skipped-step or page-density issue per loop; otherwise begin a consolidation pass after human reader feedback.

## draft-20260702-prismatic-sanity-check

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Close the beginner gap where prismatic-joint generalized effort may be mistaken for torque.
  - Show the scalar slider sanity check `x=q`, `J=[1]`, and `tau=J^T f=f` before returning to the general `J^T f` relation.
  - Clarify that in a 3D +x slider, `j=[1 0 0]^T` projects a force to `f_x`; perpendicular force components do not disappear, they simply do no work in that ideal slider DoF.
- Major changes represented:
  - Added the 1D prismatic sanity-check paragraph to `paper/sections/05b_robotics_foundations.tex` after the revolute/prismatic unit example.
  - Reworded the column-dot-force explanation from generic joint torque to generalized joint effort, with revolute effort as torque and prismatic effort as axis force.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `manuscript_prismatic_sanity_marker_checkpoint` and strengthened `joint_effort_unit_checkpoint` with axis dot products, scalar slider checks, and perpendicular-force projection.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 117 pages, 955757 bytes
  - PDF SHA-256: `C6199DDBF7D84FE79CEEFE8A439A72EB2B2076715567702CB886CA5FF0C4F2E3`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Prismatic sanity marker checkpoint: all required source markers count 1
  - Joint-effort checkpoint: scalar slider `J=1`, prismatic axis projection 1.0, perpendicular projection 0.0, prismatic effort 10 N, revolute effort 4 N m, power error 0.0
  - PDF markers: prismatic sanity check starts on page 64; perpendicular-projection caveat and joint-effort wording continue on page 65
  - Visual layout: rendered PDF pages 64 and 65 inspected; no clipping or severe crowding
- Open issues:
  - This pass is a paper-only conceptual sanity check. It does not add simulator prismatic-joint demos or measured force validation.
  - Section 5b remains dense; later human-reader feedback should decide whether the generalized-effort subsection needs a figure or appendix move.
- Next draft target:
  - Continue with small skipped-step fixes found by reviewers, or begin a page-density/compression pass once the beginner foundation has stabilized.

## draft-20260702-acceleration-kinematics

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Expose the skipped step between \(\dot{\bm{x}}=\bm{J}\dot{\bm{q}}\) and \(\ddot{\bm{x}}=\bm{J}\ddot{\bm{q}}+\dot{\bm{J}}\dot{\bm{q}}\).
  - Help beginners understand that \(\dot{\bm{J}}\) is the time derivative of \(\bm{J}(\bm{q}(t))\), not an independent new matrix.
  - Keep the explanation in kinematics scope without drifting into dynamics, mass matrices, or Coriolis-force derivations.
- Major changes represented:
  - Expanded the acceleration-kinematics explanation in `paper/sections/05b_robotics_foundations.tex`.
  - Added fixed-frame translational-position scope, product-rule wording, \(\dot{\bm{J}}=\frac{\dd}{\dd t}\bm{J}(\bm{q}(t))\), unit checks, and sign/direction caveats.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `acceleration_kinematics_checkpoint` and `manuscript_acceleration_kinematics_marker_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 117 pages, 954379 bytes
  - PDF SHA-256: `0B5C4AAC0B769AA1961A1234A5A5529DCA015DBB7436F50CDC6922F3705DE6F6`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Acceleration kinematics checkpoint: max finite-difference identity error \(1.1720832559371311\times10^{-8}~\mathrm{m/s^2}\)
  - PDF markers: fixed-frame translational-position, non-fixed Jacobian table, and product-rule markers on page 61; non-independent \(\dot{\bm J}\) marker on page 62
  - Visual layout: rendered PDF pages 61 and 62 inspected; no clipping or severe crowding
- Open issues:
  - This remains translational acceleration kinematics for \(\bm{x}=f(\bm{q})\), not full 6D twist acceleration or robot dynamics.
  - A later appendix note could add the component formula \(\dot{\bm J}=\sum_i(\partial\bm J/\partial q_i)\dot q_i\) if a technical reader asks for it.
- Next draft target:
  - Continue with small skipped-step fixes only where a reviewer finds a concrete beginner gap.

## draft-20260702-section-reading-map

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Add a compact learning-navigation map at the start of Section 5b so beginners can track whether the text is translating position, velocity, force, or timing.
  - Reduce page-density fatigue without adding another long derivation or changing simulator scope.
  - Preserve the technical distinction between DLS velocity IK and the later \(\bm{J}^{\mathsf T}\bm f\) force-to-effort relation.
- Major changes represented:
  - Added `이 장을 읽는 순서` to `paper/sections/05b_robotics_foundations.tex`.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `manuscript_section_reading_map_checkpoint`.
  - Updated durable validation/state records for the Section 5b reading-map pass.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 117 pages, 952834 bytes
  - PDF SHA-256: `65A3DDF93E65AB247AD391350B84209D564BABD4C9B17D559E35A0A84C71133A`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Section reading-map marker checkpoint: required source markers 1 each
  - PDF markers: `이 장을 읽는 순서`, `학습 내비게이션`, `관절속도 폭주를 줄이는 완화식`, and `속도 역계산이 아니라 손끝 힘` appear on page 55
  - Visual layout: rendered PDF page 55 inspected; the reading map is legible at the Section 5b opening and does not create clipping or severe crowding
- Open issues:
  - Section 5b remains long and tutorial-dense. This pass adds navigation rather than compression.
  - A later human-reader pass should decide whether one numeric IK/Jacobian/trajectory checkpoint should move to an appendix.
- Next draft target:
  - Continue only with small navigation/compression passes unless a new theory gap is found by a reader.

## draft-20260702-trajectory-profile-selection

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Add a beginner-facing decision checkpoint after the trapezoidal/S-curve examples.
  - Make the practical default explicit: start with a trapezoidal profile, then consider jerk-limited or smoother profiles when transition vibration, noise, contact shock, or heavy-load behavior matters.
  - Prevent overclaiming `s_curve.yaml` or educational smooth targets as full online jerk-constrained trajectory generators or hardware validation.
- Major changes represented:
  - Added `프로파일 선택 체크포인트` to `paper/sections/05b_robotics_foundations.tex`.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `manuscript_trajectory_profile_marker_checkpoint`.
  - Updated durable validation/state records for the trajectory-profile selection pass.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 117 pages, 952587 bytes
  - PDF SHA-256: `A975EE1CED08FFA3B7A283D52E9F05A9C6C9FAA49C48997156780E5F0A8B3F63`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Trajectory-profile marker checkpoint: required source markers 1 each
  - PDF markers: `프로파일 선택 체크포인트`, `사다리꼴을 기본값`, `전환 순간의 진동, 소음, 접촉 충격`, and `S-curve-shaped smooth polynomial target` appear on page 66
  - Visual layout: rendered PDF page 66 inspected; the checkpoint paragraph is legible below the S-curve jerk-ramp example
- Open issues:
  - Page 66 is information-dense but still legible. A later layout pass may move part of the profile explanation to an appendix if human readers report fatigue.
  - Simulator-level max acceleration/jerk/contact-shock metrics remain optional future work and were intentionally not added in this paper-only pass.
- Next draft target:
  - Continue page-density/navigation review around Section 5b, or pause theory growth for human beginner feedback before compressing Section 6.

## draft-20260702-jacobian-navigation-checkpoint

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Reduce beginner confusion when the same \(\bm J\) symbol appears as velocity map, DLS velocity-IK operator, and \(\bm J^{\mathsf T}\bm f\) force-to-effort map.
  - Add a small reading checkpoint without adding another table or expanding the linear algebra burden.
  - Replace the less beginner-friendly phrase `작업공간 포트 방향` with `선택한 작업공간 방향`.
- Major changes represented:
  - Added a `체크포인트` paragraph before the force/torque subsection in `paper/sections/05b_robotics_foundations.tex`.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `manuscript_navigation_marker_checkpoint`.
  - Updated durable validation/state records for the checkpoint pass.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 116 pages, 950932 bytes
  - PDF SHA-256: `8257F51A609821206E3359CEAC3CEEE482BAAD797DD786EDEC7047BD2C0B87F3`
  - Formula/source validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Navigation marker checkpoint: required source markers 1 each; stale `작업공간 포트` count 0
  - PDF markers: `체크포인트`, `속도 IK 완화식`, and `선택한 작업공간 방향` appear on page 63
  - Visual layout: rendered PDF page 63 inspected; the checkpoint paragraph is legible between the DLS table and force/torque derivation
- Open issues:
  - Section 5b remains dense around pages 61--66. This pass improves navigation but does not shorten the section.
  - A later human-reader pass should decide whether page density should be reduced by moving one numeric checkpoint to the appendix.
- Next draft target:
  - Continue with a page-density/navigation pass for trajectory-profile pages, or pause theory growth and wait for human reader feedback before compressing Section 5b.

## draft-20260702-jacobian-column-figure

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Turn the normalized 2-link Jacobian numeric example into a visual bridge so beginners can read each matrix column as a hand-velocity arrow.
  - Make the distinction between \(q_1\)-only motion and \(q_2\)-only motion visible before the velocity-kinematics equation.
  - Preserve scope: the figure is a normalized teaching example \(l_1=l_2=1\), not the Lab03 simulator scale or a singularity example.
- Major changes represented:
  - Added `paper/figures/fig_two_link_jacobian_columns.tex`.
  - Updated `paper/sections/05b_robotics_foundations.tex` to reference and input `fig:two-link-jacobian-columns` after the numeric Jacobian matrix.
  - Updated `.agents/validation/validate_robotics_foundations.py` with `jacobian_column_geometry_checkpoint`.
  - Updated durable validation/state records for the new figure pass.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 116 pages, 949550 bytes
  - PDF SHA-256: `122F4E4F9724986BE45793D0A6EF3B568EE52CB7C1A662C2F0D0F2E2FE3F1A7A`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Jacobian column geometry: hand \((1,1)\), elbow \((1,0)\), \(\bm j_1=(-1,1)^{\mathsf T}\), \(\bm j_2=(-1,0)^{\mathsf T}\), determinant \(1.0\), condition number \(2.618033988749895\), finite-difference column errors \(7.071\times10^{-7}\) and \(5.000\times10^{-7}\)
  - PDF markers: figure title, normalized 2-link caption, instantaneous-velocity wording, and column-as-velocity-arrow wording on page 61
  - Visual layout: rendered PDF page 61 inspected; initial left-panel label overlap was corrected; final figure is legible
- Open issues:
  - Section 5b pages 58--66 are now more visual and beginner-friendly, but page density remains high around the IK/Jacobian/trajectory sequence.
  - A later human-reader pass should decide whether one of the numeric checkpoints should move to an appendix.
- Next draft target:
  - Continue page-density/navigation review around Section 5b, or start a targeted Section 6 compression pass while preserving the beginner scaffolding.

## draft-20260702-ik-branch-figure

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Convert the 2-link IK branch numeric example into a visual explanation so beginners can see that the same hand target can correspond to different elbow positions.
  - Make the signed-side convention \(s=x_d e_y-y_d e_x\) visible in the figure and reduce ambiguity around elbow-up/elbow-down wording.
  - Preserve scope: the figure shows two representative branches for the unconstrained 2R educational model, not a full numerical IK or joint-limit treatment.
- Major changes represented:
  - Added `paper/figures/fig_two_link_ik_branches.tex`.
  - Updated `paper/sections/05b_robotics_foundations.tex` to reference and input `fig:two-link-ik-branches` after the numeric IK branch example.
  - Updated `paper/figures/figure_plan.md` with `그림 10. 2링크 IK branch`.
  - Updated `.agents/validation/validate_robotics_foundations.py` so `two_link_ik_numeric_branch_checkpoint` also checks all four unit link lengths used by the figure.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 116 pages, 944146 bytes
  - PDF SHA-256: `623CC63E105BA63B6A45B90BEA5D9BB9083542987E8A34281F75D7E6CD145BE7`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - IK branch figure geometry: positive/negative branch FK closure errors 0; unit link lengths \(1,1,1,1\); signed sides \(-1,+1\)
  - PDF markers: figure title, target label, signed-side formula, and scoped caption on page 59
  - Visual layout: rendered PDF page 59 inspected; initial label overlap was corrected; final figure is dense but legible
- Open issues:
  - Section 5b page 59 is visually dense because the numeric IK example, figure, and explanatory prose share one page.
  - A later compression pass could move part of the numeric derivation or the signed-side explanation to an appendix if human readers find the page heavy.
- Next draft target:
  - Continue with a page-density/navigation pass around Section 5b pages 58--65, or begin a Section 6 compression pass once the beginner bridge stabilizes.

## draft-20260702-ik-branch-numeric-checkpoint

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Make 2-link inverse kinematics branch choice concrete enough for beginners to follow without filling in skipped algebra from another source.
  - Show that the cosine-law \(q_2\) step gives only branch candidates, and that \(q_1\) must then be computed with `atan2`.
  - Prevent ambiguous elbow-up/elbow-down wording by distinguishing \(q_2>0\), \(q_2<0\), and signed side of the shoulder-target ray.
- Major changes represented:
  - Section 5b now includes `tab:two-link-ik-reachability`, a distance-based no/one/two-branch reachability table.
  - Section 5b now includes `eq:two-link-ik-c-value`, `eq:two-link-ik-q2-branches`, and `eq:two-link-ik-q1-from-q2`.
  - Section 5b now includes a worked \((x_d,y_d)=(1,1)~\mathrm{m}\), \(l_1=l_2=1~\mathrm{m}\) IK example with `eq:two-link-ik-positive-branch` and `eq:two-link-ik-negative-branch`.
  - Section 5b now guards the boundary-solution statement with nondegenerate-geometry and joint-limit caveats.
  - `.agents/validation/validate_robotics_foundations.py` now checks `two_link_ik_numeric_branch_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 115 pages, 938394 bytes
  - PDF SHA-256: `76B5CCC6D093BB6FADF1D863018AC28B5B1B0B3B27A12D3FE24BD52FB62BC138`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - IK numeric branch checkpoint: \(c=0\), \(q_2^{(+)}=\pi/2\), \(q_1^{(+)}=0\), \(q_2^{(-)}=-\pi/2\), \(q_1^{(-)}=\pi/2\), both FK closure errors 0, signed sides \(-1\) and \(+1\), inner-boundary \(\cos q_2=-1\)
  - PDF markers: reachability table page 58; `atan2` and numeric branch example page 59
  - Visual layout: rendered PDF pages 58 and 59 inspected, no clipping or severe crowding; pages are dense but legible
- Open issues:
  - Section 5b is now longer by one page. A later compression/layout pass may move some IK checkpoint detail into an appendix if the main tutorial flow feels heavy.
  - This remains a 2-link educational IK checkpoint. General numerical IK, joint-limit handling, and null-space optimization are intentionally scoped as later/advanced topics.
- Next draft target:
  - Continue paper-only robotics-foundation refinement with page-density/navigation review, or wait for simulator scope before adding new run-level metrics.

## draft-20260702-trajectory-profile-numeric-checkpoint

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Make trapezoidal velocity profiles concrete by tying the graph area to travel distance.
  - Add a beginner numerical checkpoint for \(L=0.10~\mathrm{m}\), \(v_{\max}=0.05~\mathrm{m/s}\), and \(a_{\max}=0.10~\mathrm{m/s^2}\).
  - Explain S-curve intuition with only the first jerk-limited acceleration ramp, without claiming to validate a full S-curve trajectory.
- Major changes represented:
  - Section 5b now includes `eq:trapezoid-accel-time`, `eq:trapezoid-accel-distance`, and `eq:trapezoid-total-time`.
  - Section 5b now states that speed-graph area is distance and that if \(L<2d_{\mathrm{acc}}\), the velocity profile becomes triangular rather than trapezoidal.
  - Section 5b now includes `eq:s-curve-jerk-ramp-time`, `eq:s-curve-jerk-ramp-dv`, and `eq:s-curve-jerk-ramp-dx`.
  - `.agents/validation/validate_robotics_foundations.py` now checks `trapezoidal_velocity_profile_checkpoint` and `s_curve_jerk_ramp_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 114 pages, 931988 bytes
  - PDF SHA-256: `6C587C9F669DE3529A8599574680B7CC11B75B2E327A642BA2A2CB3DB6D7D207`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Trapezoidal checkpoint: \(t_{\mathrm{acc}}=0.5~\mathrm{s}\), \(d_{\mathrm{acc}}=0.0125~\mathrm{m}\), cruise distance \(0.075~\mathrm{m}\), cruise time \(1.5~\mathrm{s}\), total time \(2.5~\mathrm{s}\), profile type `trapezoidal`
  - S-curve jerk-ramp checkpoint: \(t_j=0.25~\mathrm{s}\), \(\Delta v_j=0.0125~\mathrm{m/s}\), \(\Delta x_j=0.0010416666666666667~\mathrm{m}\)
  - PDF markers: trapezoid area intuition on page 63; trapezoid and S-curve jerk-ramp equations on pages 63--64
  - Visual layout: rendered PDF pages 63 and 64 inspected, no clipping or severe crowding; page 64 is dense but legible
- Open issues:
  - Page 64 is formula-dense. A later figure/layout pass could move one profile checkpoint to an appendix or add a small diagram if the manuscript becomes too heavy.
  - The S-curve checkpoint validates only the first jerk ramp, not a complete multi-phase S-curve trajectory.
- Next draft target:
  - Continue paper-only work with a page-density/navigation pass, or wait for simulator scope before adding run-level trajectory/contact metrics.

## draft-20260702-dls-reading-checkpoint

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Make the DLS velocity-IK equation readable for beginners instead of leaving it as a dense matrix expression.
  - Prevent confusion between DLS velocity IK and the later \(\bm J^{\mathsf T}\bm f\) force-to-effort mapping.
  - Record a measurable DLS tradeoff check: higher damping reduces joint-speed norm but leaves a larger task-velocity residual.
- Major changes represented:
  - Section 5b now says `eq:dls-velocity-ik` is a velocity IK equation, not the same use of \(\bm J^{\mathsf T}\) as the force/torque section.
  - Section 5b now includes `tab:dls-velocity-ik-reading`, reading \(\dot{\bm{x}}_d\), \(\bm J\bm J^{\mathsf T}\), \(\lambda^2\bm I\), the inverse, and \(\bm J^{\mathsf T}\) from right to left.
  - Section 5b now includes `eq:dls-singular-value-gain`, explaining the DLS gain \(\sigma/(\sigma^2+\lambda^2)\) with the \(\sigma=0.05,\lambda=0.1\) example.
  - Section 7 now tells readers that a condition-number peak may remain; DLS is a computational buffer against excessive joint-speed commands, not a method that instantly fixes the robot posture.
  - `.agents/validation/validate_robotics_foundations.py` now checks `dls_velocity_ik_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 114 pages, 927835 bytes
  - PDF SHA-256: `6E88BE50A1BFCABCA8776B82BC2B340A7426F867B9DF9FA18B8F7AD93EB3CA02`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - DLS checkpoint: near \(q_2=0.001\), \(\dot{\bm{x}}_d=(0.05,0)\), low \(\lambda=10^{-4}\) gives \(\|\dot{\bm q}\|=132.4137576926826\) and residual \(0.0038866980860981907\); high \(\lambda=0.05\) gives \(\|\dot{\bm q}\|=0.008992344445032757\) and residual \(0.04899573149442604\)
  - DLS ratios: joint-speed reduction ratio \(14725.165222716316\), residual increase ratio \(12.606003967653754\)
  - PDF markers: DLS reading table and gain explanation on page 61; Lab03 DLS plot caveat on page 94
  - Visual layout: rendered PDF pages 61 and 94 inspected, no clipping or severe crowding
- Open issues:
  - Page 94 remains dense because Lab03 DLS, trajectory-profile, and Lab04 transition material share the page. It is readable, but a later compression/layout pass may move some lab-reading detail to an appendix.
  - This remains a 2D translational velocity-IK explanation. Full 6D twist DLS requires coordinate, reference-point, and scaling choices.
- Next draft target:
  - If continuing paper-only work, run a page-density/navigation pass around the robotics foundation pages 58--64 and lab pages 93--95.
  - If simulator scope opens, add run-level trajectory/contact metrics rather than treating manuscript prose as simulator evidence.

## draft-20260702-joint-effort-units

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Prevent the beginner mistake that every \(\tau_i\) is a pure torque in \(\mathrm{N\,m}\).
  - Explain that \(\bm{\tau}\) is a generalized joint effort whose unit follows the paired joint variable \(q_i\).
  - Connect revolute/prismatic joint units to \(\bm{J}^{\mathsf T}\bm{f}\), virtual work, and power equivalence.
- Major changes represented:
  - Section 5b now includes `tab:joint-type-units-generalized-effort`, defining revolute \(q_i\) in rad with \(\tau_i\) in \(\mathrm{N\,m}\), and prismatic \(q_i\) in m with \(\tau_i\) in \(\mathrm{N}\).
  - Section 5b now explains that prismatic Jacobian columns read as \(\mathrm{m/m}\) direction columns, while revolute columns read like moment arms in \(\mathrm{m/rad}\).
  - Section 5b now includes the virtual-displacement identity and `eq:joint-effort-unit-check`, plus the \(10~\mathrm{N}\), \(0.4~\mathrm{m}\rightarrow4~\mathrm{N\,m}\) revolute example and \(10~\mathrm{N}\) prismatic-axis example.
  - Appendix A now lists mixed revolute/prismatic units for \(\bm q\), \(\bm J_v\), and \(\bm\tau\) instead of implying all joint coordinates and efforts are rotational.
  - `.agents/validation/validate_robotics_foundations.py` now checks `joint_effort_unit_checkpoint`.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 113 pages, 923420 bytes
  - PDF SHA-256: `B6FDABA7006CDF6AA6EE016A685D3C909E812146BCAE7FE4A0837C830F641B2D`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Joint-effort checkpoint: revolute effort \(4.0~\mathrm{N\,m}\), prismatic effort \(10.0~\mathrm{N}\), revolute/prismatic power error 0.0
  - Existing formula gates remain below thresholds: FK/Jacobian finite-difference \(6.452\times10^{-7}\), velocity identity \(2.778\times10^{-8}\), virtual-work \(8.882\times10^{-16}\), determinant formula \(2.082\times10^{-17}\), timing ratios 5/25/125, yaw-only angular-velocity skew error \(2.220\times10^{-16}\)
  - PDF markers: joint effort table on page 56; generalized-effort prose and joint-effort unit equation on page 61; appendix mixed-unit rows on page 107
  - Visual layout: rendered PDF pages 56, 61, and 107 inspected, no clipping or severe crowding
- Open issues:
  - The new Section 5b page 61 is dense but readable. Revisit only if a human novice flags fatigue around the force/torque subsection.
  - The explanation remains an ideal instantaneous/virtual-work relation, not a claim that Lab04 realizes torque-level operational-space impedance.
- Next draft target:
  - Keep simulator files untouched unless the next loop explicitly opens simulator metric work.
  - A useful paper-only next pass would be a small beginner diagram or wording pass around moment arm, force projection, and \(j_i^{\mathsf T}f\) if readers still struggle.

## draft-20260702-angular-velocity-notation

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Prevent the beginner mistake that 6D pose is merely `[x y z roll pitch yaw]`.
  - Distinguish pose, twist, wrench, angular velocity, angular acceleration, and Euler/RPY angle rates without expanding the paper into full 6D pose impedance theory.
  - Preserve a deterministic angular-velocity checkpoint for the simple yaw-only case.
- Major changes represented:
  - Appendix A now shows \(T=\begin{bmatrix}R&\bm{p}\\ \bm{0}^{\mathsf T}&1\end{bmatrix}\), \(\bm{V}=[\bm{v};\bm{\omega}]\), and \(\bm{w}=[\bm{f};\bm{\mu}]\) as separate pose, velocity, and wrench objects.
  - `tab:pose-impedance-notation` now includes a row distinguishing roll--pitch--yaw coordinates from angular velocity.
  - Appendix prose now states that Euler/RPY time derivatives are generally not \(\bm{\omega}\), and angular acceleration is not simply the second derivative of Euler angles.
  - `.agents/validation/validate_robotics_foundations.py` now checks a yaw-only angular velocity checkpoint.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 112 pages, 919954 bytes
  - PDF SHA-256: `81111E7BECF5E3A448FE826DD425CC603F2330EA3B8D0C742C66ACA2C2CB79C7`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Angular velocity checkpoint: yaw rate 1.3 rad/s gives omega_z 1.3000000000000003 rad/s in the yaw-only special case, skew error \(2.220446049250313\times10^{-16}\)
  - Citation/provenance: 29 used citation keys, 31 BibTeX entries, missing used keys 0, duplicate keys 0, missing source records 0
  - PDF markers: pose/twist bridge and RPY/angular-velocity caveat on page 108; angular-acceleration caveat and Lab04 non-6D validation boundary on page 109
  - Visual layout: rendered PDF pages 108 and 109 inspected, no clipping or severe crowding
- Open issues:
  - This remains notation guidance, not a full Lie group or 6D operational-space derivation.
  - Human beginner feedback may still prefer a small orientation diagram later.
- Next draft target:
  - Keep the Lab04 boundary unchanged unless simulator scope explicitly expands to orientation/wrench metrics.
  - Consider a small beginner figure only if readers still confuse pose, twist, and wrench after this table.

## draft-20260702-trajectory-timing-checkpoint

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Add a beginner calculation checkpoint showing how the same path becomes different velocity, acceleration, and jerk demands when the time scaling is compressed.
  - Connect that checkpoint to actual Lab03 trajectory-profile configs and Lab04 slow/fast virtual-wall approach configs.
  - Preserve measurable validation for the new 5 s versus 1 s timing ratios.
- Major changes represented:
  - Section 5b now includes `eq:straight-path-time-scaling-checkpoint`, `eq:straight-path-time-derivatives`, and `tab:same-path-different-timing`.
  - Section 7 now includes `tab:trajectory-profile-lab-checkpoint` with Lab03 profile configs, Lab03 DLS/speed-limit comparisons, and Lab04 wall slow/fast approach comparisons.
  - `.agents/validation/validate_robotics_foundations.py` now checks the straight-path timing ratios: speed 5x, acceleration 25x, jerk 125x, derivative error 0.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 112 pages, 917798 bytes
  - PDF SHA-256: `835CC4A2A98421FDBEC0D10910CD206D67524E303E3523732885E536362B8271`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Timing checkpoint: 10 cm path, 5 s versus 1 s gives speed ratio 5, acceleration ratio 25, jerk ratio 125, straight-path derivative error 0
  - Citation/provenance: 29 used citation keys, 31 BibTeX entries, missing used keys 0, duplicate keys 0, missing source records 0
  - PDF markers: same-path timing checkpoint on page 62; Lab trajectory checkpoint and `wall_slow_approach.yaml` marker on page 93
  - Visual layout: rendered PDF pages 62 and 93 inspected, no clipping or severe crowding
- Open issues:
  - The paper still treats run-level max jerk/contact metrics as optional future simulator instrumentation.
  - The new Section 7 table is dense but readable; revisit if a human beginner reports page-density fatigue.
- Next draft target:
  - Add actual simulator summary metrics only in a simulator-scoped iteration.
  - Otherwise continue paper-only loops with one small beginner skipped-step fix per version.

## draft-20260702-robotics-foundations-main-validation

- Type: working draft validation and version record
- Main source: `paper/main.tex`
- Main PDF: `paper/main.pdf`
- Durable validation summary: `.agents/validation/robotics_foundations_validation_summary.yaml`
- Version purpose:
  - Confirm that the latest Modern Robotics foundation work is included through `paper/main.tex`.
  - Preserve validation evidence in a durable YAML artifact instead of relying on cleaned `tmp/` compile logs.
  - Record the current PDF, formula gates, citation/provenance checks, marker checks, and visual layout review as one manuscript state.
- Major changes represented:
  - Section 5b robotics foundations are reflected in the main manuscript.
  - Appendix notation and beginner glossary navigation are reflected in the main manuscript.
  - IK branch checkpoint and durable formula validation are part of the current working draft evidence.
  - Version, state, validation, and completion-audit records now point to a durable validation summary.
- Review or submission status: internal working draft, not submission-ready
- Verification:
  - LaTeX compile exit code: 0
  - Final citation/reference/rerun warnings: 0/0/0
  - Final overfull/underfull boxes: 0/0
  - Known residual font warnings: 2 Korean italic bibliography substitutions
  - PDF: `paper/main.pdf`, 111 pages, 911179 bytes
  - PDF SHA-256: `2E7934D8B45318524DC6DA918D1CB03E6FA8F02225C1EE97D159647B599205BC`
  - Formula validator: `python .agents/validation/validate_robotics_foundations.py`, failures 0
  - Citation/provenance: 29 used citation keys, 31 BibTeX entries, missing used keys 0, duplicate keys 0, missing source records 0
  - Forbidden overclaim check: 0 hits for full 6D Lab04 validation, measured contact force, hardware current, torque-level Cartesian impedance, operational-space validation, MuJoCo contact-force equality, or Lab04 null-space optimization validation claims
  - Visual layout: rendered PDF pages 57 and 58 inspected, no clipping or severe crowding
- Open issues:
  - Simulator-level trajectory/contact metrics remain future work unless the simulator scope is reopened.
  - DLS and appendix table density should be reviewed after human beginner feedback.
- Next draft target:
  - Maintain this version log and `.agents/validation/robotics_foundations_validation_summary.yaml` for every future manuscript version.
  - Add run-level simulator metrics only in a simulator-scoped iteration.

