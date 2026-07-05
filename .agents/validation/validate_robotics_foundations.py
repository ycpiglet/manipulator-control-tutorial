"""Deterministic formula checks for the robotics-foundations manuscript.

This script intentionally uses only the Python standard library so another
agent can rerun the manuscript-level math checks without reconstructing a
temporary one-off command from conversation history.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROBOTICS_FOUNDATIONS_TEX = REPO_ROOT / "paper" / "sections" / "05b_robotics_foundations.tex"
INTRODUCTION_TEX = REPO_ROOT / "paper" / "sections" / "01_introduction.tex"
IMPEDANCE_CONTROL_TEX = REPO_ROOT / "paper" / "sections" / "06_impedance_control.tex"
NOTATION_CHECKLIST_TEX = REPO_ROOT / "paper" / "sections" / "A_notation_checklist.tex"
IMPEDANCE_TEX = REPO_ROOT / "paper" / "sections" / "02_impedance.tex"
LTI_SYSTEM_TEX = REPO_ROOT / "paper" / "sections" / "03_lti_system.tex"
ELECTRIC_SYSTEM_TEX = REPO_ROOT / "paper" / "sections" / "04_electric_system.tex"
MECHANICAL_SYSTEM_TEX = REPO_ROOT / "paper" / "sections" / "05_mechanical_system.tex"


def fk(q1: float, q2: float, l1: float = 0.84, l2: float = 0.67) -> tuple[float, float]:
    return (
        l1 * math.cos(q1) + l2 * math.cos(q1 + q2),
        l1 * math.sin(q1) + l2 * math.sin(q1 + q2),
    )


def jacobian(
    q1: float, q2: float, l1: float = 0.84, l2: float = 0.67
) -> tuple[tuple[float, float], tuple[float, float]]:
    return (
        (
            -l1 * math.sin(q1) - l2 * math.sin(q1 + q2),
            -l2 * math.sin(q1 + q2),
        ),
        (
            l1 * math.cos(q1) + l2 * math.cos(q1 + q2),
            l2 * math.cos(q1 + q2),
        ),
    )


def mat_vec(
    matrix: tuple[tuple[float, float], tuple[float, float]],
    vector: tuple[float, float],
) -> tuple[float, float]:
    return (
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1],
    )


def transpose_vec(
    matrix: tuple[tuple[float, float], tuple[float, float]],
    vector: tuple[float, float],
) -> tuple[float, float]:
    return (
        matrix[0][0] * vector[0] + matrix[1][0] * vector[1],
        matrix[0][1] * vector[0] + matrix[1][1] * vector[1],
    )


def dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def vec_norm(vector: tuple[float, float]) -> float:
    return math.sqrt(dot(vector, vector))


def determinant(matrix: tuple[tuple[float, float], tuple[float, float]]) -> float:
    return matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]


def manuscript_navigation_marker_checkpoint() -> dict[str, int]:
    """Check anchor markers for the Jacobian/DLS/J^T navigation checkpoint.

    Required content is tracked through \\vmark{...} anchors that survive
    prose rewording; forbidden stale phrases stay as literal text checks.
    """
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "jacobian_navigation_checkpoint_count": text.count("\\vmark{nav-jacobian-checkpoint}"),
        "dls_velocity_ik_relief_marker_count": text.count("\\vmark{nav-dls-velocity-ik-relief}"),
        "dls_jtranspose_distinction_marker_count": text.count(
            "\\vmark{nav-dls-jtranspose-distinction}"
        ),
        "same_frame_sign_marker_count": text.count("\\vmark{nav-same-frame-sign}"),
        "friendly_task_space_direction_marker_count": text.count(
            "\\vmark{nav-friendly-task-space-direction}"
        ),
        "old_task_space_port_count": text.count("작업공간 포트"),
    }


def manuscript_section_reading_map_checkpoint() -> dict[str, int]:
    """Check source markers for the Section 5b learning-navigation map."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "section_reading_map_count": text.count("\\vmark{map-section-reading-order}"),
        "learning_navigation_marker_count": text.count("\\vmark{map-learning-navigation}"),
        "not_pipeline_marker_count": text.count("\\vmark{map-not-pipeline}"),
        "joint_language_fk_marker_count": text.count("\\vmark{map-joint-language-fk}"),
        "jacobian_small_change_marker_count": text.count("\\vmark{map-jacobian-small-change}"),
        "dls_expanded_first_use_marker_count": text.count("\\vmark{map-dls-expanded-first-use}"),
        "dls_relief_marker_count": text.count("\\vmark{map-dls-relief}"),
        "jtf_force_translation_marker_count": text.count("\\vmark{map-jtf-force-translation}"),
        "path_trajectory_timetable_marker_count": text.count(
            "\\vmark{map-path-trajectory-timetable}"
        ),
    }


def manuscript_section5b_density_nav_checkpoint() -> dict[str, int]:
    """Check anchors for the Section 5b density/navigation signposts."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "ik_branch_calculation_order_marker_count": text.count(
            "\\vmark{ik-branch-calculation-order}"
        ),
        "ik_branch_numeric_example_marker_count": text.count(
            "\\vmark{ik-branch-numeric-example}"
        ),
    }


def manuscript_derivation_gap_high_checkpoint() -> dict[str, int]:
    """Check anchors for the 2026-07-05 High-severity derivation-gap fixes.

    Covers the Laplace definition/rule derivation (Sections 2-4), the
    characteristic-root standard-form substitution (Section 5), and the
    workspace-inertia force-to-acceleration derivation (Section 6).
    """
    impedance = IMPEDANCE_TEX.read_text(encoding="utf-8")
    lti = LTI_SYSTEM_TEX.read_text(encoding="utf-8")
    electric = ELECTRIC_SYSTEM_TEX.read_text(encoding="utf-8")
    mechanical = MECHANICAL_SYSTEM_TEX.read_text(encoding="utf-8")
    impedance_control = IMPEDANCE_CONTROL_TEX.read_text(encoding="utf-8")
    return {
        "laplace_definition_integral_marker_count": lti.count(
            "\\vmark{laplace-definition-integral}"
        ),
        "laplace_rule_product_rule_derivation_marker_count": lti.count(
            "\\vmark{laplace-rule-product-rule-derivation}"
        ),
        "laplace_rule_constant_check_marker_count": lti.count(
            "\\vmark{laplace-rule-constant-check}"
        ),
        "laplace_second_derivative_twice_marker_count": lti.count(
            "\\vmark{laplace-second-derivative-twice}"
        ),
        "laplace_term_by_term_msd_marker_count": lti.count(
            "\\vmark{laplace-term-by-term-msd}"
        ),
        "freq_magnitude_angle_complex_marker_count": lti.count(
            "\\vmark{freq-magnitude-angle-complex}"
        ),
        "laplace_forward_pointer_marker_count": impedance.count(
            "\\vmark{laplace-forward-pointer}"
        ),
        "msd_impedance_term_by_term_marker_count": impedance.count(
            "\\vmark{msd-impedance-term-by-term}"
        ),
        "rlc_laplace_term_by_term_marker_count": electric.count(
            "\\vmark{rlc-laplace-term-by-term}"
        ),
        "charroot_substitution_decay_piece_marker_count": mechanical.count(
            "\\vmark{charroot-substitution-decay-piece}"
        ),
        "charroot_substitution_radical_piece_marker_count": mechanical.count(
            "\\vmark{charroot-substitution-radical-piece}"
        ),
        "charroot_numeric_check_marker_count": mechanical.count(
            "\\vmark{charroot-numeric-check}"
        ),
        "charroot_imaginary_unit_factorization_marker_count": mechanical.count(
            "\\vmark{charroot-imaginary-unit-factorization}"
        ),
        "lambda_force_to_acceleration_derivation_marker_count": impedance_control.count(
            "\\vmark{lambda-force-to-acceleration-derivation}"
        ),
        "lambda_directional_mass_numeric_check_marker_count": impedance_control.count(
            "\\vmark{lambda-directional-mass-numeric-check}"
        ),
    }


def manuscript_derivation_gap_medium_checkpoint() -> dict[str, int]:
    """Check anchors for the 2026-07-05 Medium-severity derivation-gap fixes.

    Covers the serial robot/environment stiffness force split (Section 6),
    the RLC damping-ratio isolation algebra (Section 4), and the overshoot
    substitution example (Section 5).
    """
    electric = ELECTRIC_SYSTEM_TEX.read_text(encoding="utf-8")
    mechanical = MECHANICAL_SYSTEM_TEX.read_text(encoding="utf-8")
    impedance_control = IMPEDANCE_CONTROL_TEX.read_text(encoding="utf-8")
    return {
        "contact_series_stiffness_split_marker_count": impedance_control.count(
            "\\vmark{contact-series-stiffness-split}"
        ),
        "contact_series_stiffness_numeric_marker_count": impedance_control.count(
            "\\vmark{contact-series-stiffness-numeric}"
        ),
        "rlc_zeta_isolation_marker_count": electric.count(
            "\\vmark{rlc-zeta-isolation}"
        ),
        "overshoot_zeta07_substitution_marker_count": mechanical.count(
            "\\vmark{overshoot-zeta07-substitution}"
        ),
    }


def series_stiffness_checkpoint() -> dict[str, float]:
    """Verify the Section 6 serial-stiffness numeric example.

    k_d = k_env = 500 N/m with delta_d = 2 cm must give ~5 N, and a
    near-rigid environment must approach the k_d*delta_d = 10 N limit.
    """
    k_d, delta_d = 500.0, 0.02
    k_env_soft = 500.0
    k_env_rigid = 1.0e9
    f_soft = (k_d * k_env_soft) / (k_d + k_env_soft) * delta_d
    f_rigid = (k_d * k_env_rigid) / (k_d + k_env_rigid) * delta_d
    return {
        "soft_contact_force_n": f_soft,
        "rigid_limit_force_n": f_rigid,
        "max_series_stiffness_error": max(
            abs(f_soft - 5.0), abs(f_rigid - k_d * delta_d)
        ),
    }


def overshoot_formula_checkpoint() -> dict[str, float]:
    """Verify the Section 5 overshoot substitution examples.

    The manuscript claims M_p(zeta=0.7) ~ 4.6 percent and
    M_p(zeta=0.2) ~ 53 percent.
    """
    def m_p(zeta: float) -> float:
        return math.exp(-zeta * math.pi / math.sqrt(1.0 - zeta * zeta))

    return {
        "overshoot_zeta_07": m_p(0.7),
        "overshoot_zeta_02": m_p(0.2),
        "max_overshoot_claim_error": max(
            abs(m_p(0.7) - 0.046), abs(m_p(0.2) - 0.53)
        ),
    }


def charroot_standard_form_checkpoint() -> dict[str, float]:
    """Verify the Section 5 characteristic-root numeric check (m=1, b=2, k=4).

    The quadratic-formula roots and the standard-form roots
    -zeta*omega_n +/- j*omega_n*sqrt(1-zeta^2) must agree.
    """
    m, b, k = 1.0, 2.0, 4.0
    omega_n = math.sqrt(k / m)
    zeta = b / (2.0 * math.sqrt(m * k))
    quad_real = -b / (2.0 * m)
    quad_imag = math.sqrt(4.0 * m * k - b * b) / (2.0 * m)
    std_real = -zeta * omega_n
    std_imag = omega_n * math.sqrt(1.0 - zeta * zeta)
    return {
        "omega_n_rad_s": omega_n,
        "zeta": zeta,
        "max_root_component_error": max(
            abs(quad_real - std_real), abs(quad_imag - std_imag)
        ),
    }


def effective_mass_direction_checkpoint() -> dict[str, float]:
    """Verify the Section 6 directional effective-mass toy example.

    At l1=l2=1, q1=0, q2=pi/2 with unit joint inertia, the manuscript claims
    m_eff = 1/2 along x and m_eff = 1 along y.
    """
    j = jacobian(0.0, math.pi / 2.0, l1=1.0, l2=1.0)
    # J M^{-1} J^T with M = I reduces to J J^T.
    jjt = (
        (dot(j[0], j[0]), dot(j[0], j[1])),
        (dot(j[1], j[0]), dot(j[1], j[1])),
    )
    m_eff_x = 1.0 / jjt[0][0]
    m_eff_y = 1.0 / jjt[1][1]
    return {
        "m_eff_x_kg": m_eff_x,
        "m_eff_y_kg": m_eff_y,
        "max_effective_mass_error": max(abs(m_eff_x - 0.5), abs(m_eff_y - 1.0)),
    }


def manuscript_ik_to_jacobian_handoff_marker_checkpoint() -> dict[str, int]:
    """Check source markers for the IK-branch to Jacobian handoff."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "handoff_paragraph_count": text.count("\\vmark{handoff-ik-jacobian-bridge}"),
        "branch_reading_order_marker_count": text.count("\\vmark{handoff-branch-reading-order}"),
        "current_branch_q_marker_count": text.count("\\vmark{handoff-current-branch-q}"),
        "jacobian_at_that_q_marker_count": text.count("\\vmark{handoff-jacobian-at-that-q}"),
        "different_branch_metrics_marker_count": text.count(
            "\\vmark{handoff-different-branch-metrics}"
        ),
        "dls_not_branch_magic_marker_count": text.count("\\vmark{handoff-dls-not-branch-magic}"),
        "same_pose_effort_marker_count": text.count("\\vmark{handoff-same-pose-effort}"),
        "branch_pose_framing_marker_count": text.count("\\vmark{handoff-branch-pose-framing}"),
        "velocity_force_translation_marker_count": text.count(
            "\\vmark{handoff-velocity-force-translation}"
        ),
        "old_exact_position_handoff_count": text.count(
            "손끝 위치 하나를 맞춘 다음"
        ),
    }


def manuscript_generalized_effort_bridge_marker_checkpoint() -> dict[str, int]:
    """Check source markers that keep J^T f as generalized joint effort."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "dls_force_effort_handoff_marker_count": text.count("\\vmark{effort-dls-force-handoff}"),
        "force_effort_intro_marker_count": text.count("\\vmark{effort-force-intro}"),
        "generalized_effort_power_marker_count": text.count("\\vmark{effort-generalized-power}"),
        "effort_sharing_marker_count": text.count("\\vmark{effort-sharing}"),
        "actuator_effort_limit_marker_count": text.count("\\vmark{effort-actuator-limit}"),
        "closing_joint_effort_tau_marker_count": text.count("\\vmark{effort-closing-joint-tau}"),
        "closing_force_effort_relation_marker_count": text.count(
            "\\vmark{effort-closing-relation}"
        ),
        "closing_jtf_joint_effort_flow_marker_count": text.count(
            "\\vmark{effort-closing-jtf-flow}"
        ),
        "closing_effort_peak_marker_count": text.count("\\vmark{effort-closing-peak}"),
        "old_force_joint_torque_handoff_count": text.count(
            "손끝 힘을 관절 토크로"
        ),
        "old_force_joint_torque_intro_count": text.count(
            "손끝 힘과 관절 토크도"
        ),
        "old_motor_torque_power_count": text.count(
            "모터 토크 \\(\\bm{\\tau}\\)"
        ),
        "old_force_torque_transform_count": text.count("힘-토크 변환"),
        "old_jtf_joint_torque_flow_count": text.count(
            "\\bm{J}^{\\mathsf{T}}\\text{를 통한 관절 토크}"
        ),
        "old_torque_peak_phrase_count": text.count("구동기 부담 또는 토크 피크"),
    }


def manuscript_section6_effort_torque_scope_marker_checkpoint() -> dict[str, int]:
    """Check that Section 6 scopes torque wording to revolute-joint implementations."""
    introduction = INTRODUCTION_TEX.read_text(encoding="utf-8")
    section6 = IMPEDANCE_CONTROL_TEX.read_text(encoding="utf-8")
    notation = NOTATION_CHECKLIST_TEX.read_text(encoding="utf-8")
    combined_scope_text = "\n".join((introduction, section6, notation))
    return {
        "intro_force_effort_transform_marker_count": introduction.count(
            "\\vmark{scope-intro-force-effort-transform}"
        ),
        "section6_general_tau_effort_scope_marker_count": section6.count(
            "\\vmark{scope-s6-general-tau-effort}"
        ),
        "section6_revolute_torque_context_marker_count": section6.count(
            "\\vmark{scope-s6-revolute-torque-context}"
        ),
        "section6_jtf_effort_back_marker_count": section6.count(
            "\\vmark{scope-s6-jtf-effort-back}"
        ),
        "section6_revolute_read_as_torque_marker_count": section6.count(
            "\\vmark{scope-s6-read-as-torque}"
        ),
        "section6_effort_table_label_marker_count": section6.count(
            "\\vmark{scope-s6-effort-table-label}"
        ),
        "section6_generalized_effort_contribution_marker_count": section6.count(
            "\\vmark{scope-s6-generalized-contribution}"
        ),
        "section6_revolute_table_torque_marker_count": section6.count(
            "\\vmark{scope-s6-revolute-table-torque}"
        ),
        "section6_actual_joint_effort_marker_count": section6.count(
            "\\vmark{scope-s6-actual-joint-effort}"
        ),
        "section6_force_to_generalized_effort_marker_count": section6.count(
            "\\vmark{scope-s6-force-to-generalized}"
        ),
        "section6_n_joint_effort_marker_count": section6.count(
            "\\vmark{scope-s6-n-joint-effort}"
        ),
        "section6_torque_control_ladder_preserved_marker_count": section6.count(
            "\\vmark{scope-s6-torque-ladder-preserved}"
        ),
        "section6_lab04_caveat_preserved_marker_count": section6.count(
            "\\vmark{scope-s6-lab04-caveat}"
        ),
        "notation_effort_transform_marker_count": notation.count(
            "\\vmark{scope-notation-effort-transform}"
        ),
        "notation_generalized_effort_marker_count": notation.count(
            "\\vmark{scope-notation-generalized-effort}"
        ),
        "old_section6_force_torque_transform_count": section6.count("힘-토크 변환"),
        "old_section6_joint_torque_back_count": section6.count(
            "관절 토크 쪽으로 되돌린다"
        ),
        "old_notation_force_torque_transform_count": notation.count("힘--토크 변환"),
        "old_intro_force_torque_transform_count": introduction.count("힘-토크 변환"),
        "combined_valid_pose_wrench_phrase_count": combined_scope_text.count(
            "\\vmark{scope-pose-wrench}"
        ),
    }


def manuscript_configuration_space_marker_checkpoint() -> dict[str, int]:
    """Check source markers for the configuration-space bridge."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "configuration_space_marker_count": text.count("configuration space"),
        "c_space_marker_count": text.count("C-space"),
        "fixed_base_serial_marker_count": text.count("\\vmark{cspace-fixed-base-serial}"),
        "configuration_joint_space_scope_marker_count": text.count(
            "\\vmark{cspace-joint-space-scope}"
        ),
        "not_universal_identity_marker_count": text.count(
            "\\vmark{cspace-not-universal-identity}"
        ),
        "base_object_constraints_marker_count": text.count(
            "\\vmark{cspace-base-object-constraints}"
        ),
        "task_space_output_marker_count": text.count("\\vmark{cspace-task-space-output}"),
        "workspace_reachable_marker_count": text.count("\\vmark{cspace-workspace-reachable}"),
        "q_space_x_space_translation_marker_count": text.count(
            "\\vmark{cspace-q-x-translation}"
        ),
    }


def manuscript_state_configuration_marker_checkpoint() -> dict[str, int]:
    """Check source markers for the state-versus-configuration bridge."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "configuration_pose_coordinate_marker_count": text.count(
            "\\vmark{state-configuration-pose-coordinate}"
        ),
        "fixed_base_q_configuration_marker_count": text.count(
            "\\vmark{state-fixed-base-q-configuration}"
        ),
        "state_q_qdot_marker_count": text.count("\\vmark{state-q-qdot}"),
        "future_motion_position_velocity_marker_count": text.count(
            "\\vmark{state-future-motion}"
        ),
        "qddot_input_dynamics_marker_count": text.count("\\vmark{state-qddot-input-dynamics}"),
        "minimal_first_order_state_marker_count": text.count(
            "\\vmark{state-minimal-first-order}"
        ),
        "augmented_state_caveat_marker_count": text.count("\\vmark{state-augmented-caveat}"),
        "jerk_smoothness_requirement_marker_count": text.count(
            "\\vmark{state-jerk-smoothness}"
        ),
        "not_geometric_coordinate_marker_count": text.count(
            "\\vmark{state-not-geometric-coordinate}"
        ),
    }


def manuscript_acceleration_kinematics_marker_checkpoint() -> dict[str, int]:
    """Check source markers for the acceleration-kinematics explanation."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "fixed_frame_translation_marker_count": text.count(
            "\\vmark{accel-fixed-frame-translation}"
        ),
        "jacobian_not_fixed_table_marker_count": text.count(
            "\\vmark{accel-jacobian-not-fixed-table}"
        ),
        "product_rule_marker_count": text.count("\\vmark{accel-product-rule}"),
        "jdot_definition_marker_count": text.count("\\vmark{accel-jdot-definition}"),
        "jdot_not_independent_marker_count": text.count("\\vmark{accel-jdot-not-independent}"),
        "acceleration_unit_marker_count": text.count("\\vmark{accel-unit-check}"),
        "sign_direction_caveat_marker_count": text.count(
            "\\vmark{accel-sign-direction-caveat}"
        ),
    }


def manuscript_prismatic_sanity_marker_checkpoint() -> dict[str, int]:
    """Check source markers for the 1D prismatic joint sanity check."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "one_dimensional_slider_marker_count": text.count(
            "\\vmark{prism-one-dimensional-slider}"
        ),
        "scalar_x_equals_q_marker_count": text.count("\\vmark{prism-scalar-x-equals-q}"),
        "scalar_j_equals_one_marker_count": text.count("\\vmark{prism-scalar-j-equals-one}"),
        "scalar_tau_equals_force_marker_count": text.count(
            "\\vmark{prism-scalar-tau-equals-force}"
        ),
        "three_dimensional_axis_marker_count": text.count(
            "\\vmark{prism-three-dimensional-axis}"
        ),
        "projection_fx_marker_count": text.count("\\vmark{prism-projection-fx}"),
        "perpendicular_projection_marker_count": text.count(
            "\\vmark{prism-perpendicular-projection}"
        ),
        "joint_effort_not_torque_marker_count": text.count(
            "\\vmark{prism-joint-effort-reading}"
        ),
    }


def manuscript_trajectory_profile_marker_checkpoint() -> dict[str, int]:
    """Check source markers for the trajectory-profile selection checkpoint."""
    text = ROBOTICS_FOUNDATIONS_TEX.read_text(encoding="utf-8")
    return {
        "profile_selection_checkpoint_count": text.count(
            "\\vmark{traj-profile-selection-checkpoint}"
        ),
        "trapezoid_default_marker_count": text.count("\\vmark{traj-trapezoid-default}"),
        "transition_shock_marker_count": text.count("\\vmark{traj-transition-shock}"),
        "s_curve_not_always_generator_marker_count": text.count(
            "\\vmark{traj-scurve-not-always-generator}"
        ),
        "smooth_polynomial_target_marker_count": text.count(
            "\\vmark{traj-smooth-polynomial-target}"
        ),
        "diagnostic_not_hardware_marker_count": text.count(
            "\\vmark{traj-diagnostic-not-hardware}"
        ),
    }


def finite_difference_jacobian_error() -> float:
    eps = 1.0e-6
    cases = [
        (0.2, 0.7),
        (-0.5, 1.1),
        (1.0, -0.8),
        (0.0, math.pi / 2.0),
    ]
    max_error = 0.0
    for q1, q2 in cases:
        j = jacobian(q1, q2)
        for col, dq in enumerate(((eps, 0.0), (0.0, eps))):
            x0 = fk(q1, q2)
            x1 = fk(q1 + dq[0], q2 + dq[1])
            fd = ((x1[0] - x0[0]) / eps, (x1[1] - x0[1]) / eps)
            analytic = (j[0][col], j[1][col])
            max_error = max(
                max_error,
                abs(fd[0] - analytic[0]),
                abs(fd[1] - analytic[1]),
            )
    return max_error


def velocity_identity_error() -> float:
    eps = 1.0e-7
    cases = [
        (0.3, 0.6, 0.4, -0.2),
        (-0.7, 1.2, -0.5, 0.3),
        (1.1, -0.4, 0.2, 0.8),
    ]
    max_error = 0.0
    for q1, q2, q1dot, q2dot in cases:
        j = jacobian(q1, q2)
        predicted = mat_vec(j, (q1dot, q2dot))
        x0 = fk(q1, q2)
        x1 = fk(q1 + eps * q1dot, q2 + eps * q2dot)
        fd = ((x1[0] - x0[0]) / eps, (x1[1] - x0[1]) / eps)
        max_error = max(
            max_error,
            abs(fd[0] - predicted[0]),
            abs(fd[1] - predicted[1]),
        )
    return max_error


def acceleration_kinematics_checkpoint() -> dict[str, float]:
    """Check xddot = J qddot + Jdot qdot with finite differences of FK."""
    h = 3.0e-4
    eps = 1.0e-6
    cases = [
        (0.4, 0.7, 0.3, -0.2, 0.5, 0.1),
        (-0.6, 1.1, -0.4, 0.25, 0.2, -0.3),
        (1.0, -0.8, 0.1, 0.45, -0.2, 0.15),
    ]
    max_error = 0.0
    sample: dict[str, float] = {}
    for index, (q1, q2, qd1, qd2, qdd1, qdd2) in enumerate(cases):
        qdot = (qd1, qd2)
        qddot = (qdd1, qdd2)

        def q_at(t: float) -> tuple[float, float]:
            return (
                q1 + qd1 * t + 0.5 * qdd1 * t * t,
                q2 + qd2 * t + 0.5 * qdd2 * t * t,
            )

        x0 = fk(q1, q2)
        xp = fk(*q_at(h))
        xm = fk(*q_at(-h))
        finite_difference_acc = (
            (xp[0] - 2.0 * x0[0] + xm[0]) / (h * h),
            (xp[1] - 2.0 * x0[1] + xm[1]) / (h * h),
        )

        j_now = jacobian(q1, q2)
        j_plus = jacobian(q1 + eps * qd1, q2 + eps * qd2)
        j_minus = jacobian(q1 - eps * qd1, q2 - eps * qd2)
        jdot = tuple(
            tuple(
                (j_plus[row][col] - j_minus[row][col]) / (2.0 * eps)
                for col in range(2)
            )
            for row in range(2)
        )
        joint_acceleration_part = mat_vec(j_now, qddot)
        changing_jacobian_part = mat_vec(jdot, qdot)
        predicted_acc = (
            joint_acceleration_part[0] + changing_jacobian_part[0],
            joint_acceleration_part[1] + changing_jacobian_part[1],
        )
        error = vec_norm(
            (
                finite_difference_acc[0] - predicted_acc[0],
                finite_difference_acc[1] - predicted_acc[1],
            )
        )
        max_error = max(max_error, error)
        if index == 0:
            sample = {
                "sample_q1_rad": q1,
                "sample_q2_rad": q2,
                "sample_qdot_norm": vec_norm(qdot),
                "sample_qddot_norm": vec_norm(qddot),
                "sample_finite_difference_acc_x_m_s2": finite_difference_acc[0],
                "sample_finite_difference_acc_y_m_s2": finite_difference_acc[1],
                "sample_predicted_acc_x_m_s2": predicted_acc[0],
                "sample_predicted_acc_y_m_s2": predicted_acc[1],
                "sample_joint_acceleration_part_norm": vec_norm(joint_acceleration_part),
                "sample_changing_jacobian_part_norm": vec_norm(changing_jacobian_part),
                "sample_error_m_s2": error,
            }
    return {
        "max_acceleration_identity_error_m_s2": max_error,
        **sample,
    }


def jacobian_column_geometry_checkpoint() -> dict[str, float]:
    """Check the printed Jacobian-column geometry figure for q1=0, q2=pi/2."""
    q1 = 0.0
    q2 = math.pi / 2.0
    l1 = 1.0
    l2 = 1.0
    hand = fk(q1, q2, l1, l2)
    elbow = (l1 * math.cos(q1), l1 * math.sin(q1))
    j = jacobian(q1, q2, l1, l2)
    col1 = (j[0][0], j[1][0])
    col2 = (j[0][1], j[1][1])
    eps = 1.0e-6
    base = fk(q1, q2, l1, l2)
    fd_q1_point = fk(q1 + eps, q2, l1, l2)
    fd_q2_point = fk(q1, q2 + eps, l1, l2)
    fd_col1 = ((fd_q1_point[0] - base[0]) / eps, (fd_q1_point[1] - base[1]) / eps)
    fd_col2 = ((fd_q2_point[0] - base[0]) / eps, (fd_q2_point[1] - base[1]) / eps)
    fd_col1_error = vec_norm((fd_col1[0] - col1[0], fd_col1[1] - col1[1]))
    fd_col2_error = vec_norm((fd_col2[0] - col2[0], fd_col2[1] - col2[1]))
    qdot_col1 = (0.1, 0.0)
    qdot_col2 = (0.0, 0.1)
    v_col1 = mat_vec(j, qdot_col1)
    v_col2 = mat_vec(j, qdot_col2)
    det_j = determinant(j)
    a = col1[0] * col1[0] + col1[1] * col1[1]
    b = col1[0] * col2[0] + col1[1] * col2[1]
    d = col2[0] * col2[0] + col2[1] * col2[1]
    trace = a + d
    disc = max(0.0, (a - d) ** 2 + 4.0 * b * b)
    lambda_max = 0.5 * (trace + math.sqrt(disc))
    lambda_min = 0.5 * (trace - math.sqrt(disc))
    condition = math.sqrt(lambda_max / lambda_min)

    shoulder_radius = hand
    elbow_radius = (hand[0] - elbow[0], hand[1] - elbow[1])

    return {
        "q1_rad": q1,
        "q2_rad": q2,
        "hand_x_m": hand[0],
        "hand_y_m": hand[1],
        "elbow_x_m": elbow[0],
        "elbow_y_m": elbow[1],
        "j_col1_x_m_per_rad": col1[0],
        "j_col1_y_m_per_rad": col1[1],
        "j_col2_x_m_per_rad": col2[0],
        "j_col2_y_m_per_rad": col2[1],
        "fd_col1_error": fd_col1_error,
        "fd_col2_error": fd_col2_error,
        "velocity_col1_x_m_s": v_col1[0],
        "velocity_col1_y_m_s": v_col1[1],
        "velocity_col2_x_m_s": v_col2[0],
        "velocity_col2_y_m_s": v_col2[1],
        "col1_tangent_dot": dot(col1, shoulder_radius),
        "col2_tangent_dot": dot(col2, elbow_radius),
        "determinant": det_j,
        "condition_number": condition,
    }


def virtual_work_error() -> float:
    cases = [
        (0.3, 0.6, 0.4, -0.2, 5.0, -3.0),
        (-0.7, 1.2, -0.5, 0.3, -1.0, 2.0),
        (1.1, -0.4, 0.2, 0.8, 0.5, 7.0),
    ]
    max_error = 0.0
    for q1, q2, q1dot, q2dot, fx, fy in cases:
        j = jacobian(q1, q2)
        qdot = (q1dot, q2dot)
        force = (fx, fy)
        xdot = mat_vec(j, qdot)
        tau = transpose_vec(j, force)
        max_error = max(max_error, abs(dot(force, xdot) - dot(tau, qdot)))
    return max_error


def determinant_formula_error(l1: float = 0.84, l2: float = 0.67) -> float:
    max_error = 0.0
    for q1, q2 in [(0.0, 0.001), (0.2, 0.1), (-0.5, 1.1), (1.0, math.pi / 2.0)]:
        det_j = determinant(jacobian(q1, q2, l1, l2))
        expected = l1 * l2 * math.sin(q2)
        max_error = max(max_error, abs(det_j - expected))
    return max_error


def singularity_probe(l1: float = 0.84, l2: float = 0.67) -> dict[str, float]:
    # For a 2x2 Jacobian, manipulability is abs(det(J)).
    near_q2 = 0.001
    farther_q2 = 0.1
    near_manip = abs(determinant(jacobian(0.2, near_q2, l1, l2)))
    farther_manip = abs(determinant(jacobian(0.2, farther_q2, l1, l2)))

    def condition_number(q2: float) -> float:
        j = jacobian(0.2, q2, l1, l2)
        a = j[0][0] ** 2 + j[1][0] ** 2
        b = j[0][0] * j[0][1] + j[1][0] * j[1][1]
        d = j[0][1] ** 2 + j[1][1] ** 2
        trace = a + d
        disc = max(0.0, (a - d) ** 2 + 4.0 * b * b)
        lambda_max = 0.5 * (trace + math.sqrt(disc))
        lambda_min = 0.5 * (trace - math.sqrt(disc))
        return math.sqrt(lambda_max / lambda_min)

    return {
        "near_q2": near_q2,
        "near_manipulability": near_manip,
        "near_condition": condition_number(near_q2),
        "farther_q2": farther_q2,
        "farther_manipulability": farther_manip,
        "farther_condition": condition_number(farther_q2),
    }


def dls_velocity_ik_checkpoint() -> dict[str, float]:
    """Check the DLS speed/residual tradeoff near a singular posture."""

    def dls_solution(
        j: tuple[tuple[float, float], tuple[float, float]],
        xdot_desired: tuple[float, float],
        damping: float,
    ) -> tuple[float, float]:
        # qdot = J^T (J J^T + lambda^2 I)^-1 xdot_desired for a 2x2 J.
        a = j[0][0] * j[0][0] + j[0][1] * j[0][1] + damping * damping
        b = j[0][0] * j[1][0] + j[0][1] * j[1][1]
        d = j[1][0] * j[1][0] + j[1][1] * j[1][1] + damping * damping
        det = a * d - b * b
        y = (
            (d * xdot_desired[0] - b * xdot_desired[1]) / det,
            (-b * xdot_desired[0] + a * xdot_desired[1]) / det,
        )
        return transpose_vec(j, y)

    q1 = 0.2
    near_q2 = 0.001
    xdot_desired = (0.05, 0.0)
    low_lambda = 1.0e-4
    high_lambda = 5.0e-2
    j = jacobian(q1, near_q2)

    low_qdot = dls_solution(j, xdot_desired, low_lambda)
    high_qdot = dls_solution(j, xdot_desired, high_lambda)
    low_achieved = mat_vec(j, low_qdot)
    high_achieved = mat_vec(j, high_qdot)
    low_residual = (
        xdot_desired[0] - low_achieved[0],
        xdot_desired[1] - low_achieved[1],
    )
    high_residual = (
        xdot_desired[0] - high_achieved[0],
        xdot_desired[1] - high_achieved[1],
    )

    return {
        "near_q2_rad": near_q2,
        "desired_xdot_x_m_s": xdot_desired[0],
        "desired_xdot_y_m_s": xdot_desired[1],
        "low_lambda": low_lambda,
        "high_lambda": high_lambda,
        "low_joint_speed_norm": vec_norm(low_qdot),
        "high_joint_speed_norm": vec_norm(high_qdot),
        "low_task_velocity_residual_norm": vec_norm(low_residual),
        "high_task_velocity_residual_norm": vec_norm(high_residual),
        "joint_speed_reduction_ratio": vec_norm(low_qdot) / vec_norm(high_qdot),
        "residual_increase_ratio": vec_norm(high_residual) / vec_norm(low_residual),
    }


def ik_branch_classification(l1: float = 1.0, l2: float = 1.0) -> dict[str, float | str]:
    examples = {
        "outside": (2.2, 0.0),
        "boundary": (2.0, 0.0),
        "two_branch": (1.0, 1.0),
    }
    result: dict[str, float | str] = {}
    for name, (xd, yd) in examples.items():
        r2 = xd * xd + yd * yd
        cos_q2 = (r2 - l1 * l1 - l2 * l2) / (2.0 * l1 * l2)
        if cos_q2 < -1.0 or cos_q2 > 1.0:
            classification = "no_solution"
        elif abs(cos_q2 - 1.0) < 1.0e-12 or abs(cos_q2 + 1.0) < 1.0e-12:
            classification = "one_boundary_solution"
        else:
            classification = "two_branch_solution"
        result[f"{name}_cos_q2"] = cos_q2
        result[f"{name}_classification"] = classification
    return result


def two_link_ik_numeric_branch_checkpoint() -> dict[str, float]:
    """Check the printed two-branch IK example for target (1, 1)."""
    l1 = 1.0
    l2 = 1.0
    xd = 1.0
    yd = 1.0
    r2 = xd * xd + yd * yd
    cos_q2 = (r2 - l1 * l1 - l2 * l2) / (2.0 * l1 * l2)

    q2_positive = math.acos(cos_q2)
    q2_negative = -math.acos(cos_q2)

    def q1_from_q2(q2: float) -> float:
        return math.atan2(yd, xd) - math.atan2(l2 * math.sin(q2), l1 + l2 * math.cos(q2))

    q1_positive = q1_from_q2(q2_positive)
    q1_negative = q1_from_q2(q2_negative)

    fk_positive = fk(q1_positive, q2_positive, l1, l2)
    fk_negative = fk(q1_negative, q2_negative, l1, l2)
    positive_error = vec_norm((fk_positive[0] - xd, fk_positive[1] - yd))
    negative_error = vec_norm((fk_negative[0] - xd, fk_negative[1] - yd))

    elbow_positive = (l1 * math.cos(q1_positive), l1 * math.sin(q1_positive))
    elbow_negative = (l1 * math.cos(q1_negative), l1 * math.sin(q1_negative))
    elbow_branch_distance = vec_norm(
        (
            elbow_positive[0] - elbow_negative[0],
            elbow_positive[1] - elbow_negative[1],
        )
    )
    positive_link1_length = vec_norm(elbow_positive)
    positive_link2_length = vec_norm((xd - elbow_positive[0], yd - elbow_positive[1]))
    negative_link1_length = vec_norm(elbow_negative)
    negative_link2_length = vec_norm((xd - elbow_negative[0], yd - elbow_negative[1]))
    positive_signed_side = xd * elbow_positive[1] - yd * elbow_positive[0]
    negative_signed_side = xd * elbow_negative[1] - yd * elbow_negative[0]

    inner_l1 = 1.0
    inner_l2 = 0.6
    inner_xd = 0.4
    inner_yd = 0.0
    inner_r2 = inner_xd * inner_xd + inner_yd * inner_yd
    inner_boundary_cos_q2 = (
        inner_r2 - inner_l1 * inner_l1 - inner_l2 * inner_l2
    ) / (2.0 * inner_l1 * inner_l2)

    return {
        "target_x_m": xd,
        "target_y_m": yd,
        "cos_q2": cos_q2,
        "q1_positive_rad": q1_positive,
        "q2_positive_rad": q2_positive,
        "q1_negative_rad": q1_negative,
        "q2_negative_rad": q2_negative,
        "positive_elbow_x_m": elbow_positive[0],
        "positive_elbow_y_m": elbow_positive[1],
        "negative_elbow_x_m": elbow_negative[0],
        "negative_elbow_y_m": elbow_negative[1],
        "positive_fk_error_m": positive_error,
        "negative_fk_error_m": negative_error,
        "elbow_branch_distance_m": elbow_branch_distance,
        "positive_link1_length_m": positive_link1_length,
        "positive_link2_length_m": positive_link2_length,
        "negative_link1_length_m": negative_link1_length,
        "negative_link2_length_m": negative_link2_length,
        "positive_signed_side_m2": positive_signed_side,
        "negative_signed_side_m2": negative_signed_side,
        "inner_boundary_l1_m": inner_l1,
        "inner_boundary_l2_m": inner_l2,
        "inner_boundary_target_x_m": inner_xd,
        "inner_boundary_cos_q2": inner_boundary_cos_q2,
    }


def time_scaling_checkpoint() -> dict[str, float]:
    """Check the straight-path timing ratios added to Section 5b."""
    slow_duration = 5.0
    fast_duration = 1.0
    path_length_m = 0.10
    speed_ratio = slow_duration / fast_duration
    acceleration_ratio = (slow_duration / fast_duration) ** 2
    jerk_ratio = (slow_duration / fast_duration) ** 3

    # For x(s)=x0+s*delta_x, derivatives are delta_x times derivatives of s.
    sdot = 0.4
    sddot = -0.3
    sdddot = 0.2
    delta_x = (path_length_m, 0.0)
    xdot = (delta_x[0] * sdot, delta_x[1] * sdot)
    xddot = (delta_x[0] * sddot, delta_x[1] * sddot)
    xdddot = (delta_x[0] * sdddot, delta_x[1] * sdddot)
    derivative_error = max(
        abs(xdot[0] - path_length_m * sdot),
        abs(xddot[0] - path_length_m * sddot),
        abs(xdddot[0] - path_length_m * sdddot),
        abs(xdot[1]),
        abs(xddot[1]),
        abs(xdddot[1]),
    )
    return {
        "path_length_m": path_length_m,
        "slow_duration_s": slow_duration,
        "fast_duration_s": fast_duration,
        "speed_ratio_fast_over_slow": speed_ratio,
        "acceleration_ratio_fast_over_slow": acceleration_ratio,
        "jerk_ratio_fast_over_slow": jerk_ratio,
        "straight_path_derivative_error": derivative_error,
    }


def trapezoidal_velocity_profile_checkpoint() -> dict[str, float | str]:
    """Check the beginner trapezoidal velocity-profile example."""
    distance_m = 0.10
    vmax_m_s = 0.05
    amax_m_s2 = 0.10
    accel_time_s = vmax_m_s / amax_m_s2
    accel_distance_m = 0.5 * amax_m_s2 * accel_time_s * accel_time_s
    min_distance_for_cruise_m = 2.0 * accel_distance_m
    if distance_m > min_distance_for_cruise_m:
        profile_type = "trapezoidal"
        cruise_distance_m = distance_m - min_distance_for_cruise_m
        cruise_time_s = cruise_distance_m / vmax_m_s
        total_time_s = 2.0 * accel_time_s + cruise_time_s
    else:
        profile_type = "triangular"
        cruise_distance_m = 0.0
        cruise_time_s = 0.0
        total_time_s = 2.0 * math.sqrt(distance_m / amax_m_s2)
    distance_from_area_m = (
        2.0 * accel_distance_m + cruise_distance_m
        if profile_type == "trapezoidal"
        else distance_m
    )
    return {
        "distance_m": distance_m,
        "vmax_m_s": vmax_m_s,
        "amax_m_s2": amax_m_s2,
        "accel_time_s": accel_time_s,
        "accel_distance_m": accel_distance_m,
        "min_distance_for_cruise_m": min_distance_for_cruise_m,
        "cruise_distance_m": cruise_distance_m,
        "cruise_time_s": cruise_time_s,
        "total_time_s": total_time_s,
        "distance_from_area_m": distance_from_area_m,
        "profile_type": profile_type,
    }


def s_curve_jerk_ramp_checkpoint() -> dict[str, float]:
    """Check the first jerk-limited acceleration ramp example."""
    jmax_m_s3 = 0.4
    amax_m_s2 = 0.10
    jerk_ramp_time_s = amax_m_s2 / jmax_m_s3
    ramp_end_acceleration_m_s2 = jmax_m_s3 * jerk_ramp_time_s
    ramp_delta_velocity_m_s = 0.5 * jmax_m_s3 * jerk_ramp_time_s**2
    ramp_delta_position_m = (1.0 / 6.0) * jmax_m_s3 * jerk_ramp_time_s**3
    return {
        "jmax_m_s3": jmax_m_s3,
        "amax_m_s2": amax_m_s2,
        "jerk_ramp_time_s": jerk_ramp_time_s,
        "ramp_end_acceleration_m_s2": ramp_end_acceleration_m_s2,
        "ramp_delta_velocity_m_s": ramp_delta_velocity_m_s,
        "ramp_delta_position_m": ramp_delta_position_m,
    }


def angular_velocity_checkpoint() -> dict[str, float]:
    """Check the easy yaw-only case used to explain angular velocity."""
    theta = 0.7
    theta_dot = 1.3
    c = math.cos(theta)
    s = math.sin(theta)
    r = (
        (c, -s, 0.0),
        (s, c, 0.0),
        (0.0, 0.0, 1.0),
    )
    rdot = (
        (-s * theta_dot, -c * theta_dot, 0.0),
        (c * theta_dot, -s * theta_dot, 0.0),
        (0.0, 0.0, 0.0),
    )
    # For a rotation matrix mapping body axes into the base frame,
    # Rdot * R^T is the skew matrix of base-frame angular velocity.
    skew = tuple(
        tuple(sum(rdot[i][k] * r[j][k] for k in range(3)) for j in range(3))
        for i in range(3)
    )
    expected = (
        (0.0, -theta_dot, 0.0),
        (theta_dot, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    )
    max_error = max(
        abs(skew[i][j] - expected[i][j])
        for i in range(3)
        for j in range(3)
    )
    return {
        "yaw_rate_rad_s": theta_dot,
        "omega_z_rad_s": skew[1][0],
        "yaw_skew_error": max_error,
    }


def joint_effort_unit_checkpoint() -> dict[str, float]:
    """Check revolute/prismatic generalized effort units through power."""
    force_n = 10.0

    revolute_moment_arm_m = 0.4
    revolute_qdot_rad_s = 0.5
    revolute_effort_nm = revolute_moment_arm_m * force_n
    revolute_endpoint_speed_m_s = revolute_moment_arm_m * revolute_qdot_rad_s
    revolute_task_power_w = force_n * revolute_endpoint_speed_m_s
    revolute_joint_power_w = revolute_effort_nm * revolute_qdot_rad_s

    prismatic_axis = (1.0, 0.0, 0.0)
    prismatic_jacobian_column = prismatic_axis
    force_parallel = (force_n, 0.0, 0.0)
    force_perpendicular = (0.0, force_n, 0.0)
    prismatic_qdot_m_s = 0.2
    prismatic_xdot = tuple(prismatic_axis[i] * prismatic_qdot_m_s for i in range(3))
    prismatic_effort_n = dot(prismatic_jacobian_column, force_parallel)
    prismatic_task_power_w = dot(force_parallel, prismatic_xdot)
    prismatic_joint_power_w = prismatic_effort_n * prismatic_qdot_m_s

    prismatic_axis_projection = dot(prismatic_axis, force_parallel) / force_n
    perpendicular_axis_projection = dot(prismatic_axis, force_perpendicular) / force_n
    perpendicular_effort_n = dot(prismatic_jacobian_column, force_perpendicular)
    scalar_slider_j = 1.0
    scalar_slider_effort_n = scalar_slider_j * force_n
    scalar_slider_xdot_m_s = scalar_slider_j * prismatic_qdot_m_s

    max_power_error = max(
        abs(revolute_task_power_w - revolute_joint_power_w),
        abs(prismatic_task_power_w - prismatic_joint_power_w),
    )
    return {
        "force_n": force_n,
        "revolute_moment_arm_m": revolute_moment_arm_m,
        "revolute_expected_effort_nm": revolute_effort_nm,
        "revolute_task_power_w": revolute_task_power_w,
        "revolute_joint_power_w": revolute_joint_power_w,
        "prismatic_axis_projection": prismatic_axis_projection,
        "prismatic_jacobian_col_x": prismatic_jacobian_column[0],
        "prismatic_jacobian_col_y": prismatic_jacobian_column[1],
        "prismatic_jacobian_col_z": prismatic_jacobian_column[2],
        "prismatic_expected_effort_n": prismatic_effort_n,
        "prismatic_expected_xdot_x_m_s": prismatic_xdot[0],
        "prismatic_scalar_j": scalar_slider_j,
        "prismatic_scalar_effort_n": scalar_slider_effort_n,
        "prismatic_scalar_xdot_m_s": scalar_slider_xdot_m_s,
        "prismatic_task_power_w": prismatic_task_power_w,
        "prismatic_joint_power_w": prismatic_joint_power_w,
        "perpendicular_axis_projection": perpendicular_axis_projection,
        "perpendicular_expected_effort_n": perpendicular_effort_n,
        "max_power_error": max_power_error,
    }


def main() -> int:
    metrics = {
        "max_fk_jacobian_fd_error": finite_difference_jacobian_error(),
        "max_velocity_identity_error": velocity_identity_error(),
        "manuscript_section_reading_map_checkpoint": manuscript_section_reading_map_checkpoint(),
        "manuscript_ik_to_jacobian_handoff_marker_checkpoint": (
            manuscript_ik_to_jacobian_handoff_marker_checkpoint()
        ),
        "manuscript_section5b_density_nav_checkpoint": (
            manuscript_section5b_density_nav_checkpoint()
        ),
        "manuscript_derivation_gap_high_checkpoint": (
            manuscript_derivation_gap_high_checkpoint()
        ),
        "charroot_standard_form_checkpoint": charroot_standard_form_checkpoint(),
        "effective_mass_direction_checkpoint": effective_mass_direction_checkpoint(),
        "manuscript_derivation_gap_medium_checkpoint": (
            manuscript_derivation_gap_medium_checkpoint()
        ),
        "series_stiffness_checkpoint": series_stiffness_checkpoint(),
        "overshoot_formula_checkpoint": overshoot_formula_checkpoint(),
        "manuscript_generalized_effort_bridge_marker_checkpoint": (
            manuscript_generalized_effort_bridge_marker_checkpoint()
        ),
        "manuscript_section6_effort_torque_scope_marker_checkpoint": (
            manuscript_section6_effort_torque_scope_marker_checkpoint()
        ),
        "manuscript_configuration_space_marker_checkpoint": (
            manuscript_configuration_space_marker_checkpoint()
        ),
        "manuscript_state_configuration_marker_checkpoint": (
            manuscript_state_configuration_marker_checkpoint()
        ),
        "manuscript_acceleration_kinematics_marker_checkpoint": (
            manuscript_acceleration_kinematics_marker_checkpoint()
        ),
        "manuscript_prismatic_sanity_marker_checkpoint": (
            manuscript_prismatic_sanity_marker_checkpoint()
        ),
        "manuscript_navigation_marker_checkpoint": manuscript_navigation_marker_checkpoint(),
        "manuscript_trajectory_profile_marker_checkpoint": manuscript_trajectory_profile_marker_checkpoint(),
        "jacobian_column_geometry_checkpoint": jacobian_column_geometry_checkpoint(),
        "acceleration_kinematics_checkpoint": acceleration_kinematics_checkpoint(),
        "max_virtual_work_error": virtual_work_error(),
        "max_determinant_formula_error": determinant_formula_error(),
        "singularity_probe": singularity_probe(),
        "dls_velocity_ik_checkpoint": dls_velocity_ik_checkpoint(),
        "ik_branch_classification": ik_branch_classification(),
        "two_link_ik_numeric_branch_checkpoint": two_link_ik_numeric_branch_checkpoint(),
        "time_scaling_checkpoint": time_scaling_checkpoint(),
        "trapezoidal_velocity_profile_checkpoint": trapezoidal_velocity_profile_checkpoint(),
        "s_curve_jerk_ramp_checkpoint": s_curve_jerk_ramp_checkpoint(),
        "angular_velocity_checkpoint": angular_velocity_checkpoint(),
        "joint_effort_unit_checkpoint": joint_effort_unit_checkpoint(),
    }
    thresholds = {
        "max_fk_jacobian_fd_error": 1.0e-5,
        "max_velocity_identity_error": 1.0e-5,
        "acceleration_kinematics_checkpoint.max_acceleration_identity_error_m_s2": 1.0e-5,
        "max_virtual_work_error": 1.0e-12,
        "max_determinant_formula_error": 1.0e-12,
        "charroot_standard_form_checkpoint.max_root_component_error": 1.0e-12,
        "effective_mass_direction_checkpoint.max_effective_mass_error": 1.0e-12,
        # The rigid-limit branch uses a finite 1e9 N/m proxy for k_env -> inf,
        # which leaves an expected ~5e-6 N asymptotic residual.
        "series_stiffness_checkpoint.max_series_stiffness_error": 1.0e-4,
        "overshoot_formula_checkpoint.max_overshoot_claim_error": 5.0e-3,
    }
    failures: list[str] = []
    for key, threshold in thresholds.items():
        if "." in key:
            metric_key, nested_key = key.split(".", maxsplit=1)
            value = metrics[metric_key][nested_key]
        else:
            value = metrics[key]
        if float(value) > threshold:
            failures.append(f"{key}={value} > {threshold}")
    navigation_markers = metrics["manuscript_navigation_marker_checkpoint"]
    if not isinstance(navigation_markers, dict):
        failures.append("manuscript_navigation_marker_checkpoint did not return a dictionary")
    else:
        required_navigation_markers = {
            "jacobian_navigation_checkpoint_count": 1,
            "dls_velocity_ik_relief_marker_count": 1,
            "dls_jtranspose_distinction_marker_count": 1,
            "same_frame_sign_marker_count": 1,
            "friendly_task_space_direction_marker_count": 1,
        }
        for key, minimum in required_navigation_markers.items():
            if int(navigation_markers[key]) < minimum:
                failures.append(f"{key}={navigation_markers[key]} < {minimum}")
        if int(navigation_markers["old_task_space_port_count"]) != 0:
            failures.append(
                f"old_task_space_port_count={navigation_markers['old_task_space_port_count']} != 0"
            )
    ik_handoff_markers = metrics[
        "manuscript_ik_to_jacobian_handoff_marker_checkpoint"
    ]
    if not isinstance(ik_handoff_markers, dict):
        failures.append(
            "manuscript_ik_to_jacobian_handoff_marker_checkpoint did not return a dictionary"
        )
    else:
        required_ik_handoff_markers = {
            "handoff_paragraph_count": 1,
            "branch_reading_order_marker_count": 1,
            "current_branch_q_marker_count": 1,
            "jacobian_at_that_q_marker_count": 1,
            "different_branch_metrics_marker_count": 1,
            "dls_not_branch_magic_marker_count": 1,
            "same_pose_effort_marker_count": 1,
            "branch_pose_framing_marker_count": 1,
            "velocity_force_translation_marker_count": 1,
        }
        for key, minimum in required_ik_handoff_markers.items():
            if int(ik_handoff_markers[key]) < minimum:
                failures.append(f"{key}={ik_handoff_markers[key]} < {minimum}")
        if int(ik_handoff_markers["old_exact_position_handoff_count"]) != 0:
            failures.append(
                "old_exact_position_handoff_count="
                f"{ik_handoff_markers['old_exact_position_handoff_count']} != 0"
            )
    density_nav_markers = metrics["manuscript_section5b_density_nav_checkpoint"]
    if not isinstance(density_nav_markers, dict):
        failures.append(
            "manuscript_section5b_density_nav_checkpoint did not return a dictionary"
        )
    else:
        for key in (
            "ik_branch_calculation_order_marker_count",
            "ik_branch_numeric_example_marker_count",
        ):
            if int(density_nav_markers[key]) < 1:
                failures.append(f"{key}={density_nav_markers[key]} < 1")
    derivation_gap_markers = metrics["manuscript_derivation_gap_high_checkpoint"]
    if not isinstance(derivation_gap_markers, dict):
        failures.append(
            "manuscript_derivation_gap_high_checkpoint did not return a dictionary"
        )
    else:
        for key, value in derivation_gap_markers.items():
            if int(value) < 1:
                failures.append(f"{key}={value} < 1")
    derivation_gap_medium_markers = metrics["manuscript_derivation_gap_medium_checkpoint"]
    if not isinstance(derivation_gap_medium_markers, dict):
        failures.append(
            "manuscript_derivation_gap_medium_checkpoint did not return a dictionary"
        )
    else:
        for key, value in derivation_gap_medium_markers.items():
            if int(value) < 1:
                failures.append(f"{key}={value} < 1")
    effort_bridge_markers = metrics[
        "manuscript_generalized_effort_bridge_marker_checkpoint"
    ]
    if not isinstance(effort_bridge_markers, dict):
        failures.append(
            "manuscript_generalized_effort_bridge_marker_checkpoint did not return a dictionary"
        )
    else:
        required_effort_bridge_markers = {
            "dls_force_effort_handoff_marker_count": 1,
            "force_effort_intro_marker_count": 1,
            "generalized_effort_power_marker_count": 1,
            "effort_sharing_marker_count": 1,
            "actuator_effort_limit_marker_count": 1,
            "closing_joint_effort_tau_marker_count": 1,
            "closing_force_effort_relation_marker_count": 1,
            "closing_jtf_joint_effort_flow_marker_count": 1,
            "closing_effort_peak_marker_count": 1,
        }
        for key, minimum in required_effort_bridge_markers.items():
            if int(effort_bridge_markers[key]) < minimum:
                failures.append(f"{key}={effort_bridge_markers[key]} < {minimum}")
        forbidden_effort_bridge_markers = {
            "old_force_joint_torque_handoff_count": 0,
            "old_force_joint_torque_intro_count": 0,
            "old_motor_torque_power_count": 0,
            "old_force_torque_transform_count": 0,
            "old_jtf_joint_torque_flow_count": 0,
            "old_torque_peak_phrase_count": 0,
        }
        for key, expected in forbidden_effort_bridge_markers.items():
            if int(effort_bridge_markers[key]) != expected:
                failures.append(f"{key}={effort_bridge_markers[key]} != {expected}")
    section6_scope_markers = metrics[
        "manuscript_section6_effort_torque_scope_marker_checkpoint"
    ]
    if not isinstance(section6_scope_markers, dict):
        failures.append(
            "manuscript_section6_effort_torque_scope_marker_checkpoint did not return a dictionary"
        )
    else:
        required_section6_scope_markers = {
            "intro_force_effort_transform_marker_count": 1,
            "section6_general_tau_effort_scope_marker_count": 1,
            "section6_revolute_torque_context_marker_count": 1,
            "section6_jtf_effort_back_marker_count": 1,
            "section6_revolute_read_as_torque_marker_count": 1,
            "section6_effort_table_label_marker_count": 1,
            "section6_generalized_effort_contribution_marker_count": 1,
            "section6_revolute_table_torque_marker_count": 1,
            "section6_actual_joint_effort_marker_count": 1,
            "section6_force_to_generalized_effort_marker_count": 1,
            "section6_n_joint_effort_marker_count": 1,
            "section6_torque_control_ladder_preserved_marker_count": 1,
            "section6_lab04_caveat_preserved_marker_count": 1,
            "notation_effort_transform_marker_count": 1,
            "notation_generalized_effort_marker_count": 1,
            "combined_valid_pose_wrench_phrase_count": 1,
        }
        for key, minimum in required_section6_scope_markers.items():
            if int(section6_scope_markers[key]) < minimum:
                failures.append(f"{key}={section6_scope_markers[key]} < {minimum}")
        forbidden_section6_scope_markers = {
            "old_section6_force_torque_transform_count": 0,
            "old_section6_joint_torque_back_count": 0,
            "old_notation_force_torque_transform_count": 0,
            "old_intro_force_torque_transform_count": 0,
        }
        for key, expected in forbidden_section6_scope_markers.items():
            if int(section6_scope_markers[key]) != expected:
                failures.append(f"{key}={section6_scope_markers[key]} != {expected}")
    configuration_markers = metrics["manuscript_configuration_space_marker_checkpoint"]
    if not isinstance(configuration_markers, dict):
        failures.append(
            "manuscript_configuration_space_marker_checkpoint did not return a dictionary"
        )
    else:
        required_configuration_markers = {
            "configuration_space_marker_count": 2,
            "c_space_marker_count": 1,
            "fixed_base_serial_marker_count": 1,
            "configuration_joint_space_scope_marker_count": 1,
            "not_universal_identity_marker_count": 1,
            "base_object_constraints_marker_count": 1,
            "task_space_output_marker_count": 1,
            "workspace_reachable_marker_count": 1,
            "q_space_x_space_translation_marker_count": 1,
        }
        for key, minimum in required_configuration_markers.items():
            if int(configuration_markers[key]) < minimum:
                failures.append(f"{key}={configuration_markers[key]} < {minimum}")
    state_configuration_markers = metrics["manuscript_state_configuration_marker_checkpoint"]
    if not isinstance(state_configuration_markers, dict):
        failures.append(
            "manuscript_state_configuration_marker_checkpoint did not return a dictionary"
        )
    else:
        required_state_configuration_markers = {
            "configuration_pose_coordinate_marker_count": 1,
            "fixed_base_q_configuration_marker_count": 1,
            "state_q_qdot_marker_count": 1,
            "future_motion_position_velocity_marker_count": 1,
            "qddot_input_dynamics_marker_count": 1,
            "minimal_first_order_state_marker_count": 1,
            "augmented_state_caveat_marker_count": 1,
            "jerk_smoothness_requirement_marker_count": 1,
            "not_geometric_coordinate_marker_count": 1,
        }
        for key, minimum in required_state_configuration_markers.items():
            if int(state_configuration_markers[key]) < minimum:
                failures.append(f"{key}={state_configuration_markers[key]} < {minimum}")
    acceleration_markers = metrics["manuscript_acceleration_kinematics_marker_checkpoint"]
    if not isinstance(acceleration_markers, dict):
        failures.append(
            "manuscript_acceleration_kinematics_marker_checkpoint did not return a dictionary"
        )
    else:
        required_acceleration_markers = {
            "fixed_frame_translation_marker_count": 1,
            "jacobian_not_fixed_table_marker_count": 1,
            "product_rule_marker_count": 1,
            "jdot_definition_marker_count": 1,
            "jdot_not_independent_marker_count": 1,
            "acceleration_unit_marker_count": 1,
            "sign_direction_caveat_marker_count": 1,
        }
        for key, minimum in required_acceleration_markers.items():
            if int(acceleration_markers[key]) < minimum:
                failures.append(f"{key}={acceleration_markers[key]} < {minimum}")
    prismatic_markers = metrics["manuscript_prismatic_sanity_marker_checkpoint"]
    if not isinstance(prismatic_markers, dict):
        failures.append(
            "manuscript_prismatic_sanity_marker_checkpoint did not return a dictionary"
        )
    else:
        required_prismatic_markers = {
            "one_dimensional_slider_marker_count": 1,
            "scalar_x_equals_q_marker_count": 1,
            "scalar_j_equals_one_marker_count": 1,
            "scalar_tau_equals_force_marker_count": 1,
            "three_dimensional_axis_marker_count": 1,
            "projection_fx_marker_count": 1,
            "perpendicular_projection_marker_count": 1,
            "joint_effort_not_torque_marker_count": 1,
        }
        for key, minimum in required_prismatic_markers.items():
            if int(prismatic_markers[key]) < minimum:
                failures.append(f"{key}={prismatic_markers[key]} < {minimum}")
    reading_map_markers = metrics["manuscript_section_reading_map_checkpoint"]
    if not isinstance(reading_map_markers, dict):
        failures.append("manuscript_section_reading_map_checkpoint did not return a dictionary")
    else:
        required_reading_map_markers = {
            "section_reading_map_count": 1,
            "learning_navigation_marker_count": 1,
            "not_pipeline_marker_count": 1,
            "joint_language_fk_marker_count": 1,
            "jacobian_small_change_marker_count": 1,
            "dls_expanded_first_use_marker_count": 1,
            "dls_relief_marker_count": 1,
            "jtf_force_translation_marker_count": 1,
            "path_trajectory_timetable_marker_count": 1,
        }
        for key, minimum in required_reading_map_markers.items():
            if int(reading_map_markers[key]) < minimum:
                failures.append(f"{key}={reading_map_markers[key]} < {minimum}")
    trajectory_markers = metrics["manuscript_trajectory_profile_marker_checkpoint"]
    if not isinstance(trajectory_markers, dict):
        failures.append("manuscript_trajectory_profile_marker_checkpoint did not return a dictionary")
    else:
        required_trajectory_markers = {
            "profile_selection_checkpoint_count": 1,
            "trapezoid_default_marker_count": 1,
            "transition_shock_marker_count": 1,
            "s_curve_not_always_generator_marker_count": 1,
            "smooth_polynomial_target_marker_count": 1,
            "diagnostic_not_hardware_marker_count": 1,
        }
        for key, minimum in required_trajectory_markers.items():
            if int(trajectory_markers[key]) < minimum:
                failures.append(f"{key}={trajectory_markers[key]} < {minimum}")
    probe = metrics["singularity_probe"]
    if not isinstance(probe, dict):
        failures.append("singularity_probe did not return a dictionary")
    else:
        if not (probe["near_manipulability"] < probe["farther_manipulability"]):
            failures.append("manipulability did not decrease near q2=0")
        if not (probe["near_condition"] > probe["farther_condition"]):
            failures.append("condition number did not increase near q2=0")
    column_geometry = metrics["jacobian_column_geometry_checkpoint"]
    if not isinstance(column_geometry, dict):
        failures.append("jacobian_column_geometry_checkpoint did not return a dictionary")
    else:
        expected_column_geometry = {
            "q1_rad": 0.0,
            "q2_rad": math.pi / 2.0,
            "hand_x_m": 1.0,
            "hand_y_m": 1.0,
            "elbow_x_m": 1.0,
            "elbow_y_m": 0.0,
            "j_col1_x_m_per_rad": -1.0,
            "j_col1_y_m_per_rad": 1.0,
            "j_col2_x_m_per_rad": -1.0,
            "j_col2_y_m_per_rad": 0.0,
            "velocity_col1_x_m_s": -0.1,
            "velocity_col1_y_m_s": 0.1,
            "velocity_col2_x_m_s": -0.1,
            "velocity_col2_y_m_s": 0.0,
            "col1_tangent_dot": 0.0,
            "col2_tangent_dot": 0.0,
            "determinant": 1.0,
            "condition_number": 2.618033988749895,
        }
        for key, value in expected_column_geometry.items():
            if abs(float(column_geometry[key]) - value) > 1.0e-12:
                failures.append(f"{key}={column_geometry[key]} expected {value}")
        if float(column_geometry["fd_col1_error"]) > 1.0e-5:
            failures.append(f"fd_col1_error={column_geometry['fd_col1_error']} > 1e-5")
        if float(column_geometry["fd_col2_error"]) > 1.0e-5:
            failures.append(f"fd_col2_error={column_geometry['fd_col2_error']} > 1e-5")
    dls = metrics["dls_velocity_ik_checkpoint"]
    if not isinstance(dls, dict):
        failures.append("dls_velocity_ik_checkpoint did not return a dictionary")
    else:
        if not (dls["low_joint_speed_norm"] > dls["high_joint_speed_norm"] * 100.0):
            failures.append("DLS high lambda did not strongly reduce joint-speed norm")
        if not (
            dls["high_task_velocity_residual_norm"]
            > dls["low_task_velocity_residual_norm"] * 10.0
        ):
            failures.append("DLS high lambda did not increase task-velocity residual")
    ik = metrics["ik_branch_classification"]
    if not isinstance(ik, dict):
        failures.append("ik_branch_classification did not return a dictionary")
    else:
        expected = {
            "outside_classification": "no_solution",
            "boundary_classification": "one_boundary_solution",
            "two_branch_classification": "two_branch_solution",
        }
        for key, value in expected.items():
            if ik.get(key) != value:
                failures.append(f"{key}={ik.get(key)!r}, expected {value!r}")
    ik_numeric = metrics["two_link_ik_numeric_branch_checkpoint"]
    if not isinstance(ik_numeric, dict):
        failures.append("two_link_ik_numeric_branch_checkpoint did not return a dictionary")
    else:
        expected_ik_numeric = {
            "cos_q2": 0.0,
            "q1_positive_rad": 0.0,
            "q2_positive_rad": math.pi / 2.0,
            "q1_negative_rad": math.pi / 2.0,
            "q2_negative_rad": -math.pi / 2.0,
            "positive_elbow_x_m": 1.0,
            "positive_elbow_y_m": 0.0,
            "negative_elbow_x_m": 0.0,
            "negative_elbow_y_m": 1.0,
            "elbow_branch_distance_m": math.sqrt(2.0),
            "positive_link1_length_m": 1.0,
            "positive_link2_length_m": 1.0,
            "negative_link1_length_m": 1.0,
            "negative_link2_length_m": 1.0,
            "positive_signed_side_m2": -1.0,
            "negative_signed_side_m2": 1.0,
            "inner_boundary_cos_q2": -1.0,
        }
        for key, value in expected_ik_numeric.items():
            if abs(float(ik_numeric[key]) - value) > 1.0e-12:
                failures.append(f"{key}={ik_numeric[key]} expected {value}")
        if abs(float(ik_numeric["positive_fk_error_m"])) > 1.0e-12:
            failures.append(f"positive IK FK error={ik_numeric['positive_fk_error_m']} > 1e-12")
        if abs(float(ik_numeric["negative_fk_error_m"])) > 1.0e-12:
            failures.append(f"negative IK FK error={ik_numeric['negative_fk_error_m']} > 1e-12")
    timing = metrics["time_scaling_checkpoint"]
    if not isinstance(timing, dict):
        failures.append("time_scaling_checkpoint did not return a dictionary")
    else:
        expected_timing = {
            "speed_ratio_fast_over_slow": 5.0,
            "acceleration_ratio_fast_over_slow": 25.0,
            "jerk_ratio_fast_over_slow": 125.0,
            "straight_path_derivative_error": 0.0,
        }
        for key, value in expected_timing.items():
            if abs(float(timing[key]) - value) > 1.0e-12:
                failures.append(f"{key}={timing[key]} expected {value}")
    trapezoid = metrics["trapezoidal_velocity_profile_checkpoint"]
    if not isinstance(trapezoid, dict):
        failures.append("trapezoidal_velocity_profile_checkpoint did not return a dictionary")
    else:
        if trapezoid.get("profile_type") != "trapezoidal":
            failures.append(f"profile_type={trapezoid.get('profile_type')!r}, expected trapezoidal")
        expected_trapezoid = {
            "accel_time_s": 0.5,
            "accel_distance_m": 0.0125,
            "min_distance_for_cruise_m": 0.025,
            "cruise_distance_m": 0.075,
            "cruise_time_s": 1.5,
            "total_time_s": 2.5,
            "distance_from_area_m": 0.10,
        }
        for key, value in expected_trapezoid.items():
            if abs(float(trapezoid[key]) - value) > 1.0e-12:
                failures.append(f"{key}={trapezoid[key]} expected {value}")
    s_curve = metrics["s_curve_jerk_ramp_checkpoint"]
    if not isinstance(s_curve, dict):
        failures.append("s_curve_jerk_ramp_checkpoint did not return a dictionary")
    else:
        expected_s_curve = {
            "jerk_ramp_time_s": 0.25,
            "ramp_end_acceleration_m_s2": 0.10,
            "ramp_delta_velocity_m_s": 0.0125,
            "ramp_delta_position_m": 0.0010416666666666667,
        }
        for key, value in expected_s_curve.items():
            if abs(float(s_curve[key]) - value) > 1.0e-12:
                failures.append(f"{key}={s_curve[key]} expected {value}")
    angular = metrics["angular_velocity_checkpoint"]
    if not isinstance(angular, dict):
        failures.append("angular_velocity_checkpoint did not return a dictionary")
    else:
        if abs(float(angular["yaw_skew_error"])) > 1.0e-12:
            failures.append(f"yaw_skew_error={angular['yaw_skew_error']} > 1e-12")
        if abs(float(angular["omega_z_rad_s"]) - float(angular["yaw_rate_rad_s"])) > 1.0e-12:
            failures.append("yaw-only omega_z did not match yaw rate")
    effort = metrics["joint_effort_unit_checkpoint"]
    if not isinstance(effort, dict):
        failures.append("joint_effort_unit_checkpoint did not return a dictionary")
    else:
        expected_effort = {
            "revolute_expected_effort_nm": 4.0,
            "revolute_task_power_w": 2.0,
            "revolute_joint_power_w": 2.0,
            "prismatic_axis_projection": 1.0,
            "prismatic_jacobian_col_x": 1.0,
            "prismatic_jacobian_col_y": 0.0,
            "prismatic_jacobian_col_z": 0.0,
            "prismatic_expected_effort_n": 10.0,
            "prismatic_expected_xdot_x_m_s": 0.2,
            "prismatic_scalar_j": 1.0,
            "prismatic_scalar_effort_n": 10.0,
            "prismatic_scalar_xdot_m_s": 0.2,
            "prismatic_task_power_w": 2.0,
            "prismatic_joint_power_w": 2.0,
            "perpendicular_axis_projection": 0.0,
            "perpendicular_expected_effort_n": 0.0,
        }
        for key, value in expected_effort.items():
            if abs(float(effort[key]) - value) > 1.0e-12:
                failures.append(f"{key}={effort[key]} expected {value}")
        if abs(float(effort["max_power_error"])) > 1.0e-12:
            failures.append(f"joint effort power error={effort['max_power_error']} > 1e-12")

    print(json.dumps({"metrics": metrics, "failures": failures}, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
