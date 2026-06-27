"""Learner-facing guidance for saved run reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunGuide:
    title: str
    focus: str
    try_this: str
    change: str
    watch: str
    next_step: str


RUN_GUIDES: dict[str, RunGuide] = {
    "configs/lab01_msd/default.yaml": RunGuide(
        "Lab01 Baseline",
        "Use the basic mass-spring-damper response as the reference case.",
        "Compare position, velocity, force, and energy plots.",
        "mass, damping, stiffness, initial_position, force_input.magnitude",
        "How quickly the mass returns near zero and how much energy remains.",
        "Run underdamped, overdamped, high stiffness, and low stiffness next.",
    ),
    "configs/lab01_msd/underdamped.yaml": RunGuide(
        "Lab01 Underdamped",
        "Low damping makes the mass oscillate before it settles.",
        "Count how many swings occur before the position becomes small.",
        "damping, stiffness, initial_position",
        "Overshoot, repeated zero crossings, and slow energy decay.",
        "Increase damping until the oscillation disappears.",
    ),
    "configs/lab01_msd/over_damped.yaml": RunGuide(
        "Lab01 Overdamped",
        "High damping removes oscillation but slows the return.",
        "Compare settling behavior against the underdamped run.",
        "damping, stiffness, initial_position",
        "Little overshoot, lower velocity, and slower return to zero.",
        "Lower damping gradually and find the fastest non-oscillatory response.",
    ),
    "configs/lab01_msd/high_stiffness.yaml": RunGuide(
        "Lab01 High Stiffness",
        "A stiffer spring creates faster motion and larger restoring force.",
        "Compare the position frequency and force plot against low stiffness.",
        "stiffness, damping, initial_position",
        "Higher oscillation frequency and sharper force changes.",
        "Change mass and observe how the natural frequency shifts.",
    ),
    "configs/lab01_msd/low_stiffness.yaml": RunGuide(
        "Lab01 Low Stiffness",
        "A softer spring responds more slowly with smaller restoring force.",
        "Compare against high stiffness using the same initial condition.",
        "stiffness, damping, initial_position",
        "Lower motion frequency and slower return.",
        "Raise stiffness one step at a time and compare peak force.",
    ),
    "configs/lab01_msd/interactive_pull.yaml": RunGuide(
        "Lab01 Interactive",
        "Push the mass and tune physical parameters while the viewer runs.",
        "Use Pull/Push, then move mass, damping, and stiffness sliders.",
        "live sliders: mass, damping, stiffness; YAML: interaction.force",
        "Live position, velocity, applied force, and total energy.",
        "After closing the viewer, compare the saved plots with the slider choices.",
    ),
    "configs/lab02_pid/default.yaml": RunGuide(
        "Lab02 PID Baseline",
        "Use the baseline PID response as the reference for gain changes.",
        "Compare position tracking, control force, and error.",
        "target.end, controller.kp, controller.ki, controller.kd, controller.output_limit",
        "Rise time, overshoot, settling time, and force peaks.",
        "Run low/high P, PD damping, saturation, windup, noise, and delay cases.",
    ),
    "configs/lab02_pid/p_low_gain.yaml": RunGuide(
        "Lab02 Low P Gain",
        "Low proportional gain responds gently but slowly.",
        "Compare against high P gain with the same target.",
        "controller.kp, target.end",
        "Slow rise and persistent tracking error.",
        "Raise Kp until the response becomes fast enough, then watch overshoot.",
    ),
    "configs/lab02_pid/p_high_gain.yaml": RunGuide(
        "Lab02 High P Gain",
        "High proportional gain reacts strongly and can overshoot.",
        "Compare error and force against low P gain.",
        "controller.kp, controller.kd, target.end",
        "Overshoot, oscillation, and larger control effort.",
        "Add derivative damping and compare the same target again.",
    ),
    "configs/lab02_pid/pd_damped.yaml": RunGuide(
        "Lab02 PD Damping",
        "Derivative action damps the high-gain proportional response.",
        "Compare against the high P gain run.",
        "controller.kp, controller.kd",
        "Reduced overshoot and smoother force.",
        "Increase Kd until noise or force jitter becomes visible.",
    ),
    "configs/lab02_pid/saturation_limit.yaml": RunGuide(
        "Lab02 Saturation",
        "Force limits cap the controller output and slow the response.",
        "Look for clipped control_force values.",
        "controller.output_limit, target.end",
        "Slower tracking and flat control-force plateaus.",
        "Lower the force limit and compare rise time and steady-state error.",
    ),
    "configs/lab02_pid/pid_with_windup.yaml": RunGuide(
        "Lab02 Windup",
        "Integral windup can keep pushing after saturation.",
        "Run this before the anti-windup case.",
        "controller.ki, controller.anti_windup, controller.output_limit",
        "Overshoot after the error changes sign.",
        "Enable anti-windup and compare overshoot and settling time.",
    ),
    "configs/lab02_pid/pid_anti_windup.yaml": RunGuide(
        "Lab02 Anti-Windup",
        "Anti-windup limits integral buildup under saturation.",
        "Compare directly against the windup run.",
        "controller.ki, controller.anti_windup, controller.output_limit",
        "Less overshoot and cleaner settling.",
        "Change the output limit and see when anti-windup matters most.",
    ),
    "configs/lab02_pid/measurement_noise.yaml": RunGuide(
        "Lab02 Sensor Noise",
        "Noisy measurement makes the controller push unevenly.",
        "Compare true position, measured position, error, and PID force.",
        "measurement_noise_std, controller.kp, controller.kd",
        "Force jitter and measured tracking error.",
        "Lower Kd or noise and compare how the force plot changes.",
    ),
    "configs/lab02_pid/control_delay.yaml": RunGuide(
        "Lab02 Control Delay",
        "Delayed force reacts to old error and can destabilize an aggressive controller.",
        "Compare against the baseline with the same target.",
        "control_delay, controller.kp, controller.kd",
        "Slower correction, overshoot, and longer settling.",
        "Reduce Kp or add damping to recover a calmer response.",
    ),
    "configs/lab02_pid/interactive_disturbance.yaml": RunGuide(
        "Lab02 Interactive",
        "Disturb the mass and tune PID gains while the viewer runs.",
        "Click Pull/Push, then tune target, Kp, Ki, Kd, and force limit.",
        "live sliders: target, Kp, Ki, Kd, force limit; YAML: controller.*",
        "Live target, position, error, PID force, and disturbance force.",
        "Close the viewer and use the report to connect slider changes to plots.",
    ),
    "configs/lab03_2dof/default.yaml": RunGuide(
        "Lab03 Trajectory Baseline",
        "Use the 1D trajectory tracker to compare motion profiles.",
        "Inspect target and actual position, velocity, effort, and error.",
        "trajectory.type, trajectory.duration, tracking_controller.kp, tracking_controller.kd",
        "Tracking error and force/current proxy during acceleration changes.",
        "Run step, trapezoid, minimum jerk, and S-curve profiles next.",
    ),
    "configs/lab03_2dof/step.yaml": RunGuide(
        "Lab03 Step Profile",
        "A sudden target step demands abrupt effort.",
        "Run this before smoother trajectory profiles.",
        "trajectory.duration, tracking_controller.kp, tracking_controller.kd, tracking_controller.force_limit",
        "Force spike and large initial tracking error.",
        "Switch to trapezoid or minimum jerk and compare force peaks.",
    ),
    "configs/lab03_2dof/trapezoidal.yaml": RunGuide(
        "Lab03 Trapezoid Profile",
        "A trapezoidal profile limits velocity and acceleration.",
        "Compare against the step profile.",
        "trajectory.duration, trajectory.max_velocity, trajectory.max_acceleration",
        "Lower force peaks and smoother velocity transitions.",
        "Shorten duration and observe how effort grows.",
    ),
    "configs/lab03_2dof/minimum_jerk.yaml": RunGuide(
        "Lab03 Minimum Jerk",
        "Minimum-jerk motion starts and stops smoothly.",
        "Compare against trapezoid and S-curve.",
        "trajectory.duration, trajectory.start, trajectory.end",
        "Smooth position and velocity with small tracking error.",
        "Reduce duration until the controller starts to lag.",
    ),
    "configs/lab03_2dof/s_curve.yaml": RunGuide(
        "Lab03 S-Curve",
        "S-curve motion smooths jerk transitions.",
        "Compare against step and trapezoid profiles.",
        "trajectory.duration, trajectory.start, trajectory.end",
        "Reduced abruptness in effort and error.",
        "Compare current_proxy across all profile types.",
    ),
    "configs/lab03_2dof/interactive_tracking.yaml": RunGuide(
        "Lab03 1D Interactive",
        "Disturb the trajectory tracker and tune gains live.",
        "Pull or push the mass, then change target offset, Kp, Kd, and force limit.",
        "live sliders: target offset, Kp, Kd, force limit",
        "Live target, error, and control force.",
        "Use the saved report to compare how tuning affected tracking error.",
    ),
    "configs/lab03_2dof/joint_space_2dof.yaml": RunGuide(
        "Lab03 2DOF Joint Space",
        "A two-link arm tracks shoulder and elbow joint targets.",
        "Use this as the baseline 2DOF manipulator response.",
        "initial_q, target_q, trajectory.duration, tracking_controller.kp, tracking_controller.kd",
        "Joint error, end-effector motion, and torque.",
        "Run task-space and singularity cases next.",
    ),
    "configs/lab03_2dof/task_space_2dof.yaml": RunGuide(
        "Lab03 2DOF Task Space",
        "The hand moves toward an XY target through the Jacobian.",
        "In the viewer, compare the blue hand point with the green target point.",
        "target_xy, tracking_controller.task_kp, tracking_controller.task_kd",
        "End-effector X/Y motion, task error, and torque distribution.",
        "Move target_xy closer to the workspace edge and rerun.",
    ),
    "configs/lab03_2dof/singularity_2dof.yaml": RunGuide(
        "Lab03 2DOF Singularity",
        "The arm approaches a nearly straight, poorly conditioned posture.",
        "Watch for the orange hand marker, then compare manipulability and condition number.",
        "initial_q, target_q, trajectory.duration, tracking_controller.kp, tracking_controller.kd",
        "Manipulability falling while Jacobian condition number rises.",
        "Change target_q to approach the singularity more or less aggressively.",
    ),
    "configs/lab03_2dof/dls_singularity_2dof.yaml": RunGuide(
        "Lab03 2DOF DLS Singularity",
        "Damped least-squares limits the inverse-Jacobian command near a poorly conditioned target.",
        "Watch the hand marker near the workspace edge, then compare DLS plots.",
        "target_xy, tracking_controller.dls_gain, tracking_controller.dls_damping",
        "DLS joint speed, task speed, damping, condition number, and tracking error.",
        "Lower dls_damping carefully and watch whether joint speed and torque rise.",
    ),
    "configs/lab03_2dof/interactive_2dof.yaml": RunGuide(
        "Lab03 2DOF Interactive",
        "Tune hand target and task-space gains while the 2DOF arm runs.",
        "Move Target X/Y sliders and watch the green target point move.",
        "live sliders: Target X/Y, task stiffness, task damping, torque limit; YAML: viewer_guides.*",
        "Live hand position, error norm, and max torque.",
        "Close the viewer and compare hand error against the chosen target.",
    ),
    "configs/lab04_panda/neutral_hold.yaml": RunGuide(
        "Lab04 Panda Neutral Hold",
        "Hold the Panda at a stable neutral pose.",
        "Use this as the manipulator baseline before moving joints or the hand.",
        "home_q, sim_time",
        "Joint error norm should stay small.",
        "Run joint trajectory or Cartesian reach next.",
    ),
    "configs/lab04_panda/joint_pd.yaml": RunGuide(
        "Lab04 Panda Joint Path",
        "Move one Panda joint with a smooth target.",
        "Compare q_3 against target_q_3 in the position plot.",
        "controlled_joint_index, trajectory.start, trajectory.end, trajectory.duration",
        "Tracking error during motion and actuator force/current proxy.",
        "Change trajectory.end and watch how hand position changes.",
    ),
    "configs/lab04_panda/trajectory_tracking.yaml": RunGuide(
        "Lab04 Panda S-Curve Joint Path",
        "Move another Panda joint with an S-curve target.",
        "Compare against the joint_pd run.",
        "controlled_joint_index, trajectory.start, trajectory.end, trajectory.duration",
        "Which joint moves and how end-effector position changes.",
        "Switch controlled_joint_index and rerun a small motion.",
    ),
    "configs/lab04_panda/reach_x.yaml": RunGuide(
        "Lab04 Reach X",
        "Move a joint that visibly changes the Panda hand X position.",
        "Open end_effector.png after the run.",
        "controlled_joint_index, trajectory.start, trajectory.end",
        "Hand X/Y/Z motion and joint error.",
        "Run Cartesian reach to target hand position more directly.",
    ),
    "configs/lab04_panda/cartesian_reach.yaml": RunGuide(
        "Lab04 Cartesian Reach",
        "Move the Panda hand toward an explicit XYZ target.",
        "In the viewer, compare the blue hand point with the green target point.",
        "cartesian_target.position, cartesian_target.gain, cartesian_target.max_step",
        "Cartesian error, actuator force, and joint tracking error.",
        "Move the target by a few centimeters and rerun.",
    ),
    "configs/lab04_panda/cartesian_soft.yaml": RunGuide(
        "Lab04 Soft Cartesian Reach",
        "A softer Cartesian reach command moves calmly but may leave more hand error.",
        "Run before the stiff reach case and compare cartesian_error.png.",
        "cartesian_target.gain, cartesian_target.max_step, cartesian_target.damped_least_squares",
        "Final Cartesian error, hand path smoothness, and actuator force traces.",
        "Raise gain gradually and compare the error-effort tradeoff.",
    ),
    "configs/lab04_panda/cartesian_stiff.yaml": RunGuide(
        "Lab04 Stiff Cartesian Reach",
        "A stiffer Cartesian reach command pursues the same hand target more aggressively.",
        "Compare directly against the soft reach case.",
        "cartesian_target.gain, cartesian_target.max_step, cartesian_target.max_joint_offset",
        "Lower Cartesian error, actuator force traces, and joint tracking error.",
        "Lower max_step to calm the response without changing the target.",
    ),
    "configs/lab04_panda/interactive_cartesian_reach.yaml": RunGuide(
        "Lab04 Cartesian Interactive",
        "Tune hand target and Cartesian gain while the viewer runs.",
        "Move Target X/Y/Z sliders and watch the green target point move.",
        "live sliders: Target X/Y/Z, Cartesian gain; YAML: cartesian_target.*",
        "Live hand error and end-effector position.",
        "Use the saved report to compare target and actual hand motion.",
    ),
    "configs/lab04_panda/interactive_joint_hold.yaml": RunGuide(
        "Lab04 Joint Target Interactive",
        "Nudge a Panda joint target and watch tracking response.",
        "Click Joint Target -/+ several times while the viewer runs.",
        "interaction.target_step, interaction.target_limit, trajectory.end",
        "Live target offset, joint error norm, and hand X position.",
        "Increase target_step carefully and watch the error plot.",
    ),
    "configs/lab04_panda/wall_soft.yaml": RunGuide(
        "Lab04 Soft Virtual Wall",
        "A lower-stiffness virtual wall allows more penetration.",
        "Run before the stiff wall case and compare virtual_wall.png.",
        "virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping, virtual_wall.force_retreat_gain",
        "Wall penetration, virtual wall force, and hand X retreat.",
        "Raise wall stiffness gradually and compare penetration.",
    ),
    "configs/lab04_panda/wall_stiff.yaml": RunGuide(
        "Lab04 Stiff Virtual Wall",
        "A higher-stiffness virtual wall retreats more aggressively.",
        "Compare directly against the soft wall case.",
        "virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping, virtual_wall.force_retreat_gain",
        "Lower penetration, higher force, and larger retreat.",
        "Lower damping and inspect whether force spikes increase.",
    ),
    "configs/lab04_panda/interactive_virtual_wall.yaml": RunGuide(
        "Lab04 Virtual Wall Interactive",
        "Tune virtual wall parameters while the Panda moves toward the wall.",
        "Move wall X and watch the translucent red wall guide move.",
        "live sliders: wall X, stiffness, damping, retreat gain",
        "Wall penetration, wall force, hand X, and orange contact hand marker.",
        "Close the viewer and compare virtual_wall.png with the live settings.",
    ),
    "configs/lab04_panda/impedance_wall.yaml": RunGuide(
        "Lab04 Impedance Wall",
        "Inspect a Cartesian impedance-style virtual wall response.",
        "Compare hand X, virtual force, and retreat over time.",
        "virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping, virtual_wall.force_retreat_gain",
        "Penetration depth, virtual force, and actuator effort.",
        "Run soft and stiff wall configs as a controlled comparison.",
    ),
}


LAB_FALLBACK_GUIDES: tuple[tuple[str, RunGuide], ...] = (
    (
        "lab01",
        RunGuide(
            "Lab01 Mass-Spring-Damper",
            "Study how physical parameters shape a 1D dynamic response.",
            "Inspect position, velocity, force, and energy plots.",
            "mass, damping, stiffness, initial_position",
            "Overshoot, oscillation, settling, and energy decay.",
            "Change one physical parameter at a time and rerun.",
        ),
    ),
    (
        "lab02",
        RunGuide(
            "Lab02 PID Control",
            "Study how controller gains and limits shape tracking response.",
            "Inspect position, error, and control force.",
            "controller.kp, controller.ki, controller.kd, controller.output_limit",
            "Overshoot, settling time, steady-state error, and force peaks.",
            "Change one gain at a time and compare the report.",
        ),
    ),
    (
        "lab03",
        RunGuide(
            "Lab03 Trajectory and 2DOF Control",
            "Bridge motion profiles, joint-space control, and task-space control.",
            "Inspect target tracking, torque/current proxy, and end-effector plots.",
            "trajectory.*, target_q, target_xy, tracking_controller.*",
            "Tracking error, torque demand, manipulability, and task error.",
            "Compare joint-space, task-space, and singularity cases.",
        ),
    ),
    (
        "lab04",
        RunGuide(
            "Lab04 Panda Manipulator",
            "Study how manipulator targets and virtual wall parameters affect the Panda response.",
            "Inspect joint, end-effector, torque/current, and wall plots.",
            "trajectory.*, cartesian_target.*, virtual_wall.*",
            "Joint error, Cartesian error, actuator force, and wall penetration.",
            "Compare neutral hold, Cartesian reach, and wall demos.",
        ),
    ),
)


def guide_for_run_summary(summary: dict[str, Any]) -> RunGuide | None:
    config_path = str(summary.get("config_path") or "")
    config_name = str(summary.get("config_name") or "")
    lab_name = str(summary.get("lab_name") or "")
    return guide_for_config(config_path=config_path, config_name=config_name, lab_name=lab_name)


def guide_for_config(
    *,
    config_path: str = "",
    config_name: str = "",
    lab_name: str = "",
) -> RunGuide | None:
    normalized_path = _normalize_config_path(config_path)
    if normalized_path in RUN_GUIDES:
        return RUN_GUIDES[normalized_path]

    if config_name:
        for path, guide in RUN_GUIDES.items():
            if path.endswith(f"/{config_name}.yaml"):
                return guide

    lookup_text = f"{normalized_path} {config_name.lower()} {lab_name.lower()}"
    for key, guide in LAB_FALLBACK_GUIDES:
        if key in lookup_text:
            return guide
    return None


def _normalize_config_path(config_path: str) -> str:
    return config_path.replace("\\", "/").lstrip("./").lower()
