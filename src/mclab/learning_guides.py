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


def mission_prompt_for_guide(guide: RunGuide | None) -> str:
    if guide is None:
        return ""
    try_this = _short_sentence(guide.try_this)
    change = _short_sentence(guide.change)
    watch = _short_sentence(guide.watch)
    if watch and change and _is_live_change_hint(change):
        return f"Mission: Change {change}; prove it with {watch}."
    if watch and try_this:
        return f"Mission: {try_this}; prove it with {watch}."
    if watch and change:
        return f"Mission: Change {change}; prove it with {watch}."
    if try_this:
        return f"Mission: {try_this}."
    return ""


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


def playbook_for_guide(guide: RunGuide | None) -> str:
    if guide is None:
        return ""
    watch = _short_sentence(guide.watch, 72)
    change = _short_sentence(guide.change, 72)
    try_this = _short_sentence(guide.try_this, 72)
    context = " ".join((guide.title, guide.try_this, guide.change, guide.next_step)).lower()
    hands_on = any(term in context for term in ("interactive", "live", "slider", "preset", "button", "pulse", "nudge"))

    predict = _playbook_prediction_step(watch)
    if hands_on and change:
        action = f"change {change}"
    elif try_this:
        action = try_this
    elif change:
        action = f"isolate {change}"
    else:
        action = "run the scenario"

    watch_reference = _playbook_watch_reference(watch)
    if hands_on:
        evidence = (
            f"mark one observation with {watch_reference}" if watch_reference else "mark one observation with live evidence"
        )
    else:
        evidence = (
            f"review the saved plot and worksheet for {watch_reference}"
            if watch_reference
            else "review the saved plot and worksheet"
        )
    return f"Playbook: 1. {predict}; 2. {action}; 3. {evidence}."


def _playbook_prediction_step(watch: str) -> str:
    if not watch:
        return "predict the visible response"
    lowered = watch.lower()
    if lowered.startswith(("how ", "what ", "which ", "whether ")):
        return f"predict {_playbook_watch_reference(watch)}"
    return f"predict how {watch} will change"


def _playbook_watch_reference(watch: str) -> str:
    if not watch:
        return ""
    lowered = watch.lower()
    if lowered.startswith(("how ", "what ", "which ", "whether ")):
        return f"{watch[:1].lower()}{watch[1:]}"
    return watch


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
                    ("Orange bar", "Virtual wall force direction and relative magnitude."),
                    ("Red plane", "Virtual wall location."),
                ]
            )
        return items

    if "lab04" in context:
        return []

    if "2dof" in context:
        items = [
            ("Green sphere", "Target hand point."),
            ("Blue sphere", "Current hand point."),
            ("Orange sphere", "Singularity warning when Jacobian conditioning is poor."),
        ]
        if "retarget" in context or "waypoint" in context:
            items.insert(1, ("Small green spheres", "Planned target waypoint path."))
        return items

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


def _short_sentence(value: str, limit: int = 140) -> str:
    text = " ".join(str(value).split())
    if len(text) > limit:
        text = f"{text[: max(0, limit - 3)].rstrip()}..."
    if text.endswith("..."):
        return text
    return text.removesuffix(".")


def _is_live_change_hint(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in ("live", "slider", "preset", "button", "target -/+"))


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
    "configs/lab03_2dof/condition_aware_dls_inner_target_2dof.yaml": RunGuide(
        "Lab03 2DOF Inner-Target Condition-Aware DLS",
        "The target stays inside the comfortable workspace, away from the near-singular edge.",
        "Run before the edge-target case and compare dls_condition_scale.",
        "target_xy with the same condition-aware damping schedule",
        "Low condition scale, small task error, and modest DLS damping.",
        "Run the edge-target condition-aware DLS case to see when damping becomes necessary.",
    ),
    "configs/lab03_2dof/condition_aware_dls_edge_target_2dof.yaml": RunGuide(
        "Lab03 2DOF Edge-Target Condition-Aware DLS",
        "The target is near the arm's workspace edge, where Jacobian conditioning becomes poor.",
        "Compare directly against the inner-target case with the same controller schedule.",
        "target_xy with the same condition-aware damping schedule",
        "Higher condition scale, increased DLS damping, task error, and joint-speed limiting.",
        "Move target_xy slightly inward and compare how quickly DLS damping disappears.",
    ),
    "configs/lab03_2dof/condition_aware_dls_upper_path_2dof.yaml": RunGuide(
        "Lab03 2DOF Upper-Path Condition-Aware DLS",
        "The arm reaches the same near-edge target from an elbow-down posture, so the hand approaches from above.",
        "Compare directly against the lower-path case and watch the arm branch in the viewer.",
        "initial_q with the same target_xy and condition-aware damping schedule",
        "Hand Y motion, torque sign changes, DLS damping, condition number, and task error.",
        "Run the lower-path condition-aware DLS case to compare the mirrored branch.",
    ),
    "configs/lab03_2dof/condition_aware_dls_lower_path_2dof.yaml": RunGuide(
        "Lab03 2DOF Lower-Path Condition-Aware DLS",
        "The arm reaches the same near-edge target from an elbow-up posture, so the hand approaches from below.",
        "Compare directly against the upper-path case with the same target and damping schedule.",
        "initial_q with the same target_xy and condition-aware damping schedule",
        "Hand Y motion, torque sign changes, DLS damping, condition number, and task error.",
        "Run the upper-path condition-aware DLS case, then compare hand_y and elbow torque plots.",
    ),
    "configs/lab03_2dof/condition_aware_dls_shoulder_disturbance_2dof.yaml": RunGuide(
        "Lab03 2DOF Shoulder-Disturbance Condition-Aware DLS",
        "A short shoulder torque pulse disturbs the same near-edge DLS reach.",
        "Compare against the elbow-disturbance case and the undisturbed condition-aware DLS run.",
        "disturbance_torque.start_time, disturbance_torque.duration, disturbance_torque.torque",
        "Disturbance torque, total torque, task error during the pulse, DLS damping, and recovery.",
        "Run the elbow-disturbance case to compare which joint disturbance is easier to reject.",
    ),
    "configs/lab03_2dof/condition_aware_dls_elbow_disturbance_2dof.yaml": RunGuide(
        "Lab03 2DOF Elbow-Disturbance Condition-Aware DLS",
        "A short elbow torque pulse disturbs the same near-edge DLS reach.",
        "Compare against the shoulder-disturbance case and the undisturbed condition-aware DLS run.",
        "disturbance_torque.start_time, disturbance_torque.duration, disturbance_torque.torque",
        "Disturbance torque, total torque, task error during the pulse, DLS damping, and recovery.",
        "Run the shoulder-disturbance case, then compare disturbance and task-error plots.",
    ),
    "configs/lab03_2dof/condition_aware_dls_staggered_disturbance_2dof.yaml": RunGuide(
        "Lab03 2DOF Staggered-Disturbance Condition-Aware DLS",
        "A shoulder pulse followed by an elbow pulse disturbs the same near-edge DLS reach.",
        "Compare against the single-joint disturbance cases and inspect whether the second pulse recovers differently.",
        "disturbance_torque.pulses, tracking_controller.condition_damping_threshold, tracking_controller.max_dls_damping",
        "Disturbance timing, total torque, task error after each pulse, DLS damping, and recovery duration.",
        "Run the shoulder and elbow single-pulse cases to isolate which joint made the staggered sequence harder.",
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
    "configs/lab03_2dof/condition_aware_dls_slow_command_2dof.yaml": RunGuide(
        "Lab03 2DOF Slow-Command Condition-Aware DLS",
        "The same near-edge hand target is commanded slowly so task-speed demand stays modest.",
        "Run before fast-command DLS and compare dls_task_speed and task error.",
        "trajectory.duration, tracking_controller.max_task_speed",
        "Lower task speed, DLS joint speed, damping schedule, and final hand error.",
        "Run fast-command DLS next to see how the same target becomes harder when rushed.",
    ),
    "configs/lab03_2dof/condition_aware_dls_fast_command_2dof.yaml": RunGuide(
        "Lab03 2DOF Fast-Command Condition-Aware DLS",
        "The same near-edge hand target is commanded quickly to expose speed limits and task lag.",
        "Compare directly against slow-command DLS with the same target and damping schedule.",
        "trajectory.duration, tracking_controller.max_task_speed",
        "Task-speed clipping, DLS joint speed, task error, condition scale, and torque peaks.",
        "Slow the command down until task error drops without changing the target.",
    ),
    "configs/lab03_2dof/condition_aware_dls_low_joint_speed_2dof.yaml": RunGuide(
        "Lab03 2DOF Low-Joint-Speed Condition-Aware DLS",
        "The same near-edge hand target is constrained by a tight DLS joint-speed limit.",
        "Compare against high-joint-speed DLS with the same target, timing, and damping schedule.",
        "tracking_controller.max_joint_speed",
        "Joint-speed clipping, larger task error, DLS damping, condition scale, and torque.",
        "Run high-joint-speed DLS next and compare how much hand tracking improves.",
    ),
    "configs/lab03_2dof/condition_aware_dls_high_joint_speed_2dof.yaml": RunGuide(
        "Lab03 2DOF High-Joint-Speed Condition-Aware DLS",
        "The same near-edge hand target is allowed a relaxed DLS joint-speed limit.",
        "Compare directly against low-joint-speed DLS.",
        "tracking_controller.max_joint_speed",
        "Higher DLS joint speed, smaller task error, DLS damping timing, and actuator effort.",
        "Tighten max_joint_speed gradually and find where tracking error becomes visible.",
    ),
    "configs/lab03_2dof/condition_aware_dls_direct_retarget_2dof.yaml": RunGuide(
        "Lab03 2DOF Direct-Retarget Condition-Aware DLS",
        "The hand target moves directly from the start pose to the near-edge DLS target.",
        "Run before inward-retarget DLS and compare how the direct path loads the same damping schedule.",
        "target_xy_waypoints with the same condition-aware damping schedule",
        "Condition scale, DLS damping, joint speed, task error, and torque during the retarget.",
        "Run inward-retarget DLS next and compare whether the detour reduces conditioning cost or raises command effort.",
    ),
    "configs/lab03_2dof/condition_aware_dls_inward_retarget_2dof.yaml": RunGuide(
        "Lab03 2DOF Inward-Retarget Condition-Aware DLS",
        "The hand target first moves through an inner waypoint, then returns to the near-edge DLS target.",
        "Compare directly against direct-retarget DLS with the same controller limits.",
        "target_xy_waypoints with the same condition-aware damping schedule",
        "DLS task speed, joint speed, torque, condition scale, and final hand error.",
        "Move the inner waypoint or timing to see when retargeting helps versus simply asking for faster motion.",
    ),
    "configs/lab03_2dof/interactive_2dof.yaml": RunGuide(
        "Lab03 2DOF Interactive",
        "Tune hand target and task-space gains, then disturb the shoulder or elbow while the 2DOF arm runs.",
        "Move Target X/Y sliders, click a reach preset, then use Shoulder pulse or Elbow pulse to test recovery.",
        "live sliders/presets: Target X/Y, task stiffness, task damping, torque limit; buttons: Shoulder/Elbow pulse; YAML: viewer_guides.*, interaction.joint_disturbance_torque",
        "Live hand position, error norm, max torque, disturbance torque, and target/current markers.",
        "Mark one observation comparing target/gain tuning with a shoulder or elbow disturbance.",
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
        "Move Target X/Y/Z sliders, use Quick presets, or nudge Target X with A/D.",
        "live sliders/presets: Target X/Y/Z, Cartesian gain; buttons: Target X -/+; YAML: cartesian_target.*, interaction.target_step",
        "Live hand error, Target X nudge, and end-effector position.",
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
    "configs/lab04_panda/wall_slow_approach.yaml": RunGuide(
        "Lab04 Slow-Approach Virtual Wall",
        "The same wall is approached slowly so velocity-dependent damping stays modest.",
        "Run before the fast-approach wall and compare force_virtual_damping_0.",
        "trajectory.duration with fixed virtual_wall.stiffness, virtual_wall.damping, and virtual_wall.wall_x",
        "Lower hand X speed, damping force, contact duration, and penetration.",
        "Run fast-approach wall next to see the same wall feel stronger when rushed.",
    ),
    "configs/lab04_panda/wall_fast_approach.yaml": RunGuide(
        "Lab04 Fast-Approach Virtual Wall",
        "The same wall is approached quickly to expose velocity-dependent damping.",
        "Compare directly against slow-approach wall with the same wall settings.",
        "trajectory.duration with fixed virtual_wall.stiffness, virtual_wall.damping, and virtual_wall.wall_x",
        "Higher hand X speed, damping force, retreat, and actuator effort.",
        "Slow trajectory.duration down until the damping-force spike becomes easier to control.",
    ),
    "configs/lab04_panda/wall_shallow_push.yaml": RunGuide(
        "Lab04 Shallow-Push Virtual Wall",
        "The Cartesian hand target moves just past the virtual wall while wall settings stay fixed.",
        "Run before the deep-push wall and compare target-wall gap against actual penetration.",
        "cartesian_target.waypoints with fixed virtual_wall.wall_x, stiffness, damping, and retreat gains",
        "Small target-wall gap, wall contact timing, penetration, wall force, and retreat.",
        "Run the deep-push wall next to separate commanded target depth from actual hand penetration.",
    ),
    "configs/lab04_panda/wall_deep_push.yaml": RunGuide(
        "Lab04 Deep-Push Virtual Wall",
        "The Cartesian hand target moves deeper through the same virtual wall.",
        "Compare directly against shallow-push wall with the same wall settings.",
        "cartesian_target.waypoints with fixed virtual_wall.wall_x, stiffness, damping, and retreat gains",
        "Larger target-wall gap, hand penetration, wall force, retreat, and hand X response.",
        "Reduce target waypoint X until wall force and penetration become comfortable for live demos.",
    ),
    "configs/lab04_panda/wall_contact_cycle.yaml": RunGuide(
        "Lab04 Contact-Cycle Virtual Wall",
        "The hand target crosses the same virtual wall, backs away, then crosses again.",
        "Compare against slow/fast approach walls and inspect contact/release episodes.",
        "cartesian_target.waypoints with fixed virtual_wall.wall_x, stiffness, damping, and retreat gain",
        "Target crossing episodes, wall contact episodes, release timing, spring/damping force, and retreat.",
        "Adjust waypoint timing or wall_x to see when repeated target crossings stop producing real contact.",
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
        "Use Target X + into wall, sliders, or Quick presets including Back away to compare contact and release.",
        "live sliders/presets: Target X/Y/Z, Cartesian gain, wall X, stiffness, damping, retreat gain; presets: Soft/Stiff/Close wall and Back away; buttons: Target X into/away from wall; YAML: virtual_wall.*, interaction.target_step",
        "Target X nudge, Target-Wall gap, Wall phase, Wall penetration, total/spring/damping force, retreat, hand X, and contact markers.",
        "Mark observations after pushing into the wall and using Back away to release contact.",
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
