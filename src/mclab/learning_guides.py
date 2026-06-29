"""Learner-facing guidance for saved run reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunGuide:
    title: str
    focus: str
    try_this: str
    change: str
    watch: str
    next_step: str
    question: str = ""


def question_for_guide(guide: RunGuide | None) -> str:
    if guide is None:
        return ""
    if guide.question.strip():
        return _question_prefix(guide.question)
    return reflection_question_for_context(title=guide.title)


def observation_prompt_for_guide(guide: RunGuide | None) -> str:
    if guide is None:
        return ""
    watch = guide.watch.strip()
    if not watch:
        return ""
    return f"Evidence to capture: {watch}"


def prediction_prompt_for_guide(guide: RunGuide | None) -> str:
    if guide is None:
        return ""
    change = guide.change.strip()
    watch = guide.watch.strip().rstrip(".")
    if change and watch:
        return f"Prediction: Before changing {change}, predict how {watch} will change."
    if watch:
        return f"Prediction: Before the run, predict what you expect to see in {watch}."
    if change:
        return f"Prediction: Before the run, predict what will change when you adjust {change}."
    return ""


def viewer_legend_for_guide(guide: RunGuide | None) -> list[tuple[str, str]]:
    if guide is None:
        return []
    context = " ".join(
        (
            guide.title,
            guide.focus,
            guide.try_this,
            guide.change,
            guide.watch,
            guide.next_step,
        )
    ).lower()

    if "lab04" in context and any(term in context for term in ("cartesian", "wall", "impedance")):
        items = [
            ("Green sphere", "Cartesian hand target."),
            ("Blue sphere", "Current Panda hand position."),
        ]
        if "wall" in context or "impedance" in context:
            items.extend(
                [
                    ("Orange sphere", "Hand point used to show wall contact or retreat."),
                    ("Red plane", "Virtual wall location."),
                ]
            )
        return items

    if "lab04" in context:
        return []

    if "2dof" in context:
        return [
            ("Green sphere", "Target hand point."),
            ("Blue sphere", "Current hand point."),
            ("Orange sphere", "Singularity warning when Jacobian conditioning is poor."),
        ]

    if any(term in context for term in ("lab01", "lab02", "pid", "mass-spring", "1d", "trajectory")):
        return [
            ("Gray marker", "Equilibrium or track reference on the slider axis."),
            ("Green marker", "Target position."),
            ("Orange bar", "Applied force direction or manual disturbance."),
        ]

    return []


def reflection_question_for_context(
    *,
    lab_name: str = "",
    title: str = "",
    label: str = "",
    config_path: str = "",
    config_name: str = "",
) -> str:
    label_text = label.lower()
    config_text = f"{Path(config_path).name.lower()} {config_name.lower()}"
    title_text = title.lower()
    lab_text = lab_name.lower()
    context = f"{lab_text} {title_text} {label_text} {config_text}"

    if "lab01" in context or "mass-spring" in context:
        if "interactive" in context:
            return "Question: Which slider change most clearly changes oscillation, settling, or energy?"
        if "damped" in context:
            return "Question: How does damping change overshoot and settling time?"
        if "stiffness" in context:
            return "Question: How does stiffness change motion frequency and peak force?"
        return "Question: What baseline motion should later damping and stiffness cases be compared against?"

    if "lab02" in context or "pid" in context:
        if "interactive" in context:
            return "Question: Which live gain change improves tracking without making force noisy or excessive?"
        if "windup" in context:
            return "Question: What does integral action do after the actuator has saturated?"
        if "noise" in context:
            return "Question: How does noisy measurement appear in the force and error plots?"
        if "delay" in context:
            return "Question: How does delayed feedback change overshoot and settling?"
        if "gain" in context or "pd damping" in context:
            return "Question: Which gain change trades speed for overshoot or smoother force?"
        return "Question: How do error, effort, and settling define a good PID response?"

    if "lab03" in context or "2dof" in context or "trajectory" in context:
        if "singularity" in context:
            return "Question: What warning signs show that the arm is near a singular configuration?"
        if "task" in context or "interactive_2dof" in context:
            return "Question: How do hand error, joint motion, and torque change when the target moves?"
        if any(term in context for term in ("step", "trapezoid", "minimum jerk", "s-curve")):
            return "Question: Which trajectory profile gives smoother effort while still tracking well?"
        if "joint-space" in context or "joint space" in context:
            return "Question: How does joint-space tracking differ from controlling the hand target directly?"
        return "Question: Which signal best reveals tracking quality: position error, hand error, or effort?"

    if "lab04" in context or "panda" in context:
        if "wall" in context:
            return "Question: How do wall stiffness and damping change penetration, retreat, and actuator effort?"
        if "cartesian" in context or "reach" in context:
            return "Question: How does Cartesian target tuning trade hand error against actuator effort?"
        if "joint target" in context:
            return "Question: How far can the joint target be nudged before tracking error becomes obvious?"
        if "neutral hold" in context:
            return "Question: What does a stable full-manipulator baseline look like before motion starts?"
        return "Question: How does changing a single joint target move the Panda hand?"

    return "Question: What changed, and which plot proves it?"


def _question_prefix(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("Question:"):
        return stripped
    return f"Question: {stripped}"


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
        "Use Pull/Push, then try Quick presets for lightly damped, heavy damping, and stiff spring cases.",
        "live sliders/presets: mass, damping, stiffness; YAML: interaction.force, viewer_guides.enabled",
        "Live position, velocity, applied force, total energy, and viewer force direction.",
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
        "Move the target slider or use Quick presets for gentle P, damped PD, and aggressive PID.",
        "live sliders/presets: target, Kp, Ki, Kd, force limit; YAML: controller.*, viewer_guides.enabled",
        "Live target, position, error, PID force, disturbance force, and orange force bar.",
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
        "Open the viewer and try Low DLS damping, Balanced DLS, and High DLS damping presets.",
        "live sliders/presets: target_xy, tracking_controller.dls_gain, tracking_controller.dls_damping",
        "DLS joint speed, hand tracking error, damping, condition number, and torque.",
        "Run condition-aware DLS next and compare the damping schedule.",
    ),
    "configs/lab03_2dof/condition_aware_dls_2dof.yaml": RunGuide(
        "Lab03 2DOF Condition-Aware DLS",
        "DLS damping rises automatically as the arm approaches a poorly conditioned posture.",
        "Open the viewer and try Early damping, Balanced schedule, and Late damping presets.",
        (
            "live sliders/presets: target_xy, tracking_controller.dls_damping, "
            "tracking_controller.condition_damping_threshold, tracking_controller.condition_damping_full, "
            "tracking_controller.max_dls_damping"
        ),
        "DLS damping, condition scale, joint speed, condition number, and task error.",
        "Lower max_dls_damping or raise the threshold to see when joint speed grows.",
    ),
    "configs/lab03_2dof/condition_aware_dls_early_2dof.yaml": RunGuide(
        "Lab03 2DOF Early Condition-Aware DLS",
        "Condition-aware damping starts earlier and can rise higher before the arm reaches the edge.",
        "Compare against late condition-aware DLS with the same target.",
        (
            "tracking_controller.condition_damping_threshold, "
            "tracking_controller.condition_damping_full, tracking_controller.max_dls_damping"
        ),
        "Earlier DLS damping, condition scale, joint speed, condition number, and task error.",
        "Run late condition-aware DLS and compare how much task error changes.",
    ),
    "configs/lab03_2dof/condition_aware_dls_late_2dof.yaml": RunGuide(
        "Lab03 2DOF Late Condition-Aware DLS",
        "Condition-aware damping waits until conditioning is worse and uses a lower damping ceiling.",
        "Compare against early condition-aware DLS with the same target.",
        (
            "tracking_controller.condition_damping_threshold, "
            "tracking_controller.condition_damping_full, tracking_controller.max_dls_damping"
        ),
        "Later DLS damping, joint speed demand, condition number, and hand tracking error.",
        "Run the Lab03 comparison batch to see early, default, and late schedules together.",
    ),
    "configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml": RunGuide(
        "Lab03 2DOF Low-Torque Condition-Aware DLS",
        "The same condition-aware DLS target is constrained by a lower shoulder and elbow torque limit.",
        "Compare against the high-torque condition-aware DLS run with the same target and damping schedule.",
        "tracking_controller.torque_limit",
        "Torque clipping, larger task error, DLS joint speed, and condition number.",
        "Run the high-torque condition-aware DLS case and compare task error against actuator effort.",
    ),
    "configs/lab03_2dof/condition_aware_dls_high_torque_2dof.yaml": RunGuide(
        "Lab03 2DOF High-Torque Condition-Aware DLS",
        "The same condition-aware DLS target is allowed more actuator effort.",
        "Compare directly against the low-torque condition-aware DLS run.",
        "tracking_controller.torque_limit",
        "Whether task error shrinks, torque peaks grow, and DLS damping timing stays the same.",
        "Lower the torque limit gradually and find where the hand can no longer follow the target well.",
    ),
    "configs/lab03_2dof/interactive_2dof.yaml": RunGuide(
        "Lab03 2DOF Interactive",
        "Tune hand target and task-space gains while the 2DOF arm runs.",
        "Move Target X/Y sliders or use Quick presets for soft, default, and near-edge reach.",
        "live sliders/presets: Target X/Y, task stiffness, task damping, torque limit; YAML: viewer_guides.*",
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
    "configs/lab04_panda/neutral_hold_30s.yaml": RunGuide(
        "Lab04 Panda 30s Stability Hold",
        "Hold the Panda at the neutral pose long enough to check live-demo stability.",
        "Run headless first, then inspect velocity and error plots before using the viewer in class.",
        "home_q, sim_time, dt",
        "Max joint speed, joint drift, final joint error, and actuator effort.",
        "Use this as the readiness check before Lab04 live demos.",
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
        "Move Target X/Y/Z sliders or use Quick presets for soft, default, and farther reach.",
        "live sliders/presets: Target X/Y/Z, Cartesian gain; YAML: cartesian_target.*",
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
    "configs/lab04_panda/wall_low_damping.yaml": RunGuide(
        "Lab04 Low-Damping Virtual Wall",
        "Wall stiffness and retreat gain stay fixed while damping is low.",
        "Run before the high-damping wall and compare virtual_wall.png.",
        "virtual_wall.damping, virtual_wall.stiffness, virtual_wall.force_retreat_gain",
        "Wall penetration, virtual force, retreat, and hand X response.",
        "Run high-damping wall and compare how the same stiffness feels calmer or stronger.",
    ),
    "configs/lab04_panda/wall_high_damping.yaml": RunGuide(
        "Lab04 High-Damping Virtual Wall",
        "Wall stiffness and retreat gain stay fixed while damping is high.",
        "Compare directly against the low-damping wall.",
        "virtual_wall.damping, virtual_wall.stiffness, virtual_wall.force_retreat_gain",
        "Wall penetration, virtual force, retreat, and hand X response.",
        "Lower damping gradually and inspect whether penetration or force changes first.",
    ),
    "configs/lab04_panda/wall_near.yaml": RunGuide(
        "Lab04 Near Virtual Wall",
        "Wall stiffness and damping stay fixed while the wall is placed closer to the hand path.",
        "Run before the far wall and compare virtual_wall.png.",
        "virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping",
        "Earlier contact, larger penetration, virtual force, retreat, and hand X response.",
        "Run far wall and compare how much less contact the same motion produces.",
    ),
    "configs/lab04_panda/wall_far.yaml": RunGuide(
        "Lab04 Far Virtual Wall",
        "Wall stiffness and damping stay fixed while the wall is placed farther along the hand path.",
        "Compare directly against the near wall.",
        "virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping",
        "Later contact, smaller penetration, virtual force, retreat, and hand X response.",
        "Move wall_x closer gradually and find when the hand starts producing a visible wall response.",
    ),
    "configs/lab04_panda/wall_low_retreat.yaml": RunGuide(
        "Lab04 Low-Retreat Virtual Wall",
        "Wall force settings stay fixed while force-to-retreat gain is low.",
        "Run before the high-retreat wall and compare wall_retreat_compare.png.",
        "virtual_wall.force_retreat_gain, virtual_wall.cartesian_retreat_gain",
        "Wall retreat, penetration, hand X response, and virtual force.",
        "Run high-retreat wall and compare whether stronger retreat lowers penetration.",
    ),
    "configs/lab04_panda/wall_high_retreat.yaml": RunGuide(
        "Lab04 High-Retreat Virtual Wall",
        "The same wall force maps into a stronger Cartesian target retreat.",
        "Compare directly against the low-retreat wall.",
        "virtual_wall.force_retreat_gain, virtual_wall.cartesian_retreat_gain",
        "Larger retreat, reduced penetration, hand X response, and actuator effort.",
        "Lower force_retreat_gain gradually and find where penetration becomes visible again.",
    ),
    "configs/lab04_panda/interactive_virtual_wall.yaml": RunGuide(
        "Lab04 Virtual Wall Interactive",
        "Tune the hand target and virtual wall parameters while the Panda moves toward the wall.",
        "Move Target X through the wall, then use Quick presets for soft wall, stiff wall, and close wall cases.",
        "live sliders/presets: Target X/Y/Z, Cartesian gain, wall X, stiffness, damping, retreat gain",
        "Target-Wall gap, Wall penetration, wall force, hand X, green target marker, and orange contact hand marker.",
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
