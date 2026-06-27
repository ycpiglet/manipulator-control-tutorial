"""HTML report generation for saved lab runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from mclab.config import load_config
from mclab.learning_guides import RunGuide, guide_for_run_summary

INDEX_METRIC_KEYS = (
    "max_abs_position",
    "overshoot_percent",
    "settling_time",
    "steady_state_error",
    "max_control_effort",
    "measurement_noise_std",
    "control_delay",
    "max_abs_measurement_error",
    "max_abs_tracking_error",
    "final_tracking_error",
    "max_abs_control_force",
    "max_joint_error_norm",
    "final_joint_error_norm",
    "max_task_error_norm",
    "final_task_error_norm",
    "min_manipulability",
    "max_jacobian_condition",
    "max_abs_tau_cmd",
    "max_dls_joint_speed",
    "max_cartesian_error_cm",
    "final_cartesian_error_cm",
    "max_wall_penetration_cm",
    "max_wall_retreat_cm",
    "max_abs_virtual_wall_force",
    "interaction_events",
)

CONFIG_HIGHLIGHT_KEYS = (
    "sim_time",
    "dt",
    "mode",
    "plant",
    "mass",
    "damping",
    "stiffness",
    "initial_position",
    "initial_velocity",
    "force_input.type",
    "force_input.magnitude",
    "force_input.start_time",
    "target.type",
    "target.start",
    "target.end",
    "target.start_time",
    "controller.kp",
    "controller.ki",
    "controller.kd",
    "controller.output_limit",
    "controller.anti_windup",
    "measurement_noise_std",
    "control_delay",
    "trajectory.type",
    "trajectory.start",
    "trajectory.end",
    "trajectory.duration",
    "trajectory.start_time",
    "tracking_controller.kp",
    "tracking_controller.kd",
    "tracking_controller.task_kp",
    "tracking_controller.task_kd",
    "tracking_controller.dls_gain",
    "tracking_controller.dls_damping",
    "tracking_controller.max_task_speed",
    "tracking_controller.max_joint_speed",
    "tracking_controller.force_limit",
    "tracking_controller.torque_limit",
    "link_lengths",
    "initial_q",
    "target_q",
    "target_xy",
    "controlled_joint_index",
    "cartesian_target.position",
    "cartesian_target.offset",
    "cartesian_target.gain",
    "cartesian_target.max_step",
    "virtual_wall.wall_x",
    "virtual_wall.stiffness",
    "virtual_wall.damping",
    "virtual_wall.force_retreat_gain",
    "interaction.key_force",
    "interaction.force",
    "interaction.duration",
    "interaction.target_nudge",
    "interaction.target_step",
    "interaction.target_limit",
    "interaction.live_tuning",
    "viewer_guides.enabled",
    "viewer_guides.condition_warning",
    "viewer_guides.condition_threshold",
)


@dataclass(frozen=True)
class IndexPathStep:
    title: str
    description: str
    config_path: str = ""
    batch_name: str = ""


INDEX_LEARNING_PATH: tuple[IndexPathStep, ...] = (
    IndexPathStep(
        "1. Feel 1D physics",
        "Mass-spring-damper baseline response.",
        "configs/lab01_msd/default.yaml",
    ),
    IndexPathStep(
        "2. Disturb and tune",
        "Push the mass and tune physical parameters.",
        "configs/lab01_msd/interactive_pull.yaml",
    ),
    IndexPathStep("3. Close the loop", "PID tracking, error, and control force.", "configs/lab02_pid/default.yaml"),
    IndexPathStep(
        "4. Tune PID live",
        "Tune target, gains, and force limit.",
        "configs/lab02_pid/interactive_disturbance.yaml",
    ),
    IndexPathStep(
        "5. Move 2DOF joints",
        "Joint-space tracking on the two-link arm.",
        "configs/lab03_2dof/joint_space_2dof.yaml",
    ),
    IndexPathStep(
        "6. Control the hand",
        "Task-space hand control with the Jacobian.",
        "configs/lab03_2dof/task_space_2dof.yaml",
    ),
    IndexPathStep("7. Hold Panda", "Stable neutral-hold baseline for Panda.", "configs/lab04_panda/neutral_hold.yaml"),
    IndexPathStep(
        "8. Reach in Cartesian",
        "Panda hand reaches an explicit XYZ target.",
        "configs/lab04_panda/cartesian_reach.yaml",
    ),
    IndexPathStep(
        "9. Touch virtual wall",
        "Interactive Panda virtual wall behavior.",
        "configs/lab04_panda/interactive_virtual_wall.yaml",
    ),
    IndexPathStep("10. Compare the course", "Full comparison report set.", batch_name="all"),
)


def write_run_report(output_path: str | Path) -> Path:
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    summary = _read_json(output / "summary.json")
    notes = _read_text(output / "notes.md")
    config = _read_config(output / "config.yaml")
    plots = sorted((output / "plots").glob("*.png"))
    interaction_events = _read_json_list(output / "interaction_events.json")

    html = _render_report(output, summary, notes, plots, interaction_events, config)
    report_path = output / "report.html"
    report_path.write_text(html, encoding="utf-8")
    write_outputs_index(output.parent)
    return report_path


def write_outputs_index(outputs_root: str | Path) -> Path:
    root = Path(outputs_root)
    root.mkdir(parents=True, exist_ok=True)
    runs = _discover_runs(root)
    index_path = root / "index.html"
    index_path.write_text(_render_outputs_index(root, runs), encoding="utf-8")
    return index_path


def _render_report(
    output: Path,
    summary: dict[str, Any],
    notes: str,
    plots: list[Path],
    interaction_events: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    title = _report_title(output, summary)
    learning_guide = _learning_guide_section(guide_for_run_summary(summary))
    reproduce_section = _reproduce_section(summary)
    config_highlights = _config_highlights_section(config)
    result_check = _result_check_section(summary)
    observation_markers = _observation_markers_section(interaction_events)
    interaction_section = _interaction_section(interaction_events)
    plot_guide = _plot_guide_section(plots)
    rows = "\n".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(_format_value(value))}</td></tr>"
        for key, value in summary.items()
    )
    if not rows:
        rows = '<tr><td colspan="2">No summary values were saved.</td></tr>'

    plot_cards = "\n".join(
        (
            '<figure class="plot">'
            f'<img src="{escape(_relative(output, plot))}" alt="{escape(plot.stem)} plot">'
            f"<figcaption>{escape(plot.name)}</figcaption>"
            "</figure>"
        )
        for plot in plots
    )
    if not plot_cards:
        plot_cards = '<p class="empty">No plots were saved for this run.</p>'

    file_links = "\n".join(
        f'<li><a href="{escape(name)}">{escape(name)}</a></li>'
        for name in (
            "config.yaml",
            "summary.json",
            "notes.md",
            "log.csv",
            "states.npz",
            "interaction_events.json",
        )
        if (output / name).exists()
    )
    if not file_links:
        file_links = "<li>No standard artifact files were found.</li>"

    notes_html = f"<pre>{escape(notes.strip())}</pre>" if notes.strip() else "<p>No notes were saved.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} report</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: "Segoe UI", Arial, sans-serif;
      color: #202124;
      background: #f6f7f9;
    }}
    body {{
      margin: 0;
      padding: 24px;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    h1, h2, h3 {{
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 28px;
    }}
    h2 {{
      font-size: 20px;
    }}
    h3 {{
      font-size: 16px;
    }}
    section {{
      background: #ffffff;
      border: 1px solid #d9dde3;
      border-radius: 8px;
      margin-top: 16px;
      padding: 16px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
    }}
    th, td {{
      border-bottom: 1px solid #edf0f3;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      width: 260px;
      color: #3f4752;
      font-weight: 600;
    }}
    .plots {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }}
    .plot-guide {{
      margin-bottom: 16px;
    }}
    .plot-guide-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .plot-guide-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .plot-guide-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .plot-guide-card span {{
      display: block;
      color: #596270;
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .guide-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px 18px;
    }}
    .guide-item {{
      border-top: 1px solid #edf0f3;
      padding-top: 8px;
    }}
    .guide-item strong {{
      display: block;
      color: #3f4752;
      margin-bottom: 4px;
    }}
    .guide-item span {{
      display: block;
      line-height: 1.4;
    }}
    .command-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 12px;
    }}
    .command-block {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .command-block strong {{
      display: block;
      margin-bottom: 8px;
    }}
    .config-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .config-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .config-card strong {{
      display: block;
      margin-bottom: 6px;
      overflow-wrap: anywhere;
    }}
    .config-card span {{
      color: #596270;
      overflow-wrap: anywhere;
    }}
    .check-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .check-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .check-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .marker-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .marker-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .marker-card > strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .marker-time {{
      display: block;
      color: #596270;
      font-size: 13px;
      margin-bottom: 10px;
    }}
    .marker-group {{
      margin-top: 10px;
    }}
    .marker-group ul {{
      list-style: none;
      padding: 0;
      margin: 6px 0 0;
    }}
    .marker-group li {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-top: 1px solid #edf0f3;
      padding: 5px 0;
    }}
    .marker-group span {{
      color: #596270;
    }}
    .check-state {{
      display: inline-block;
      margin-bottom: 8px;
      color: #3f4752;
      font-size: 13px;
      font-weight: 600;
    }}
    .plot {{
      margin: 0;
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      overflow: hidden;
      background: #ffffff;
    }}
    .plot img {{
      display: block;
      width: 100%;
      height: auto;
    }}
    figcaption {{
      border-top: 1px solid #e0e4ea;
      padding: 8px 10px;
      color: #596270;
      font-size: 13px;
    }}
    pre {{
      white-space: pre-wrap;
      margin: 0;
      line-height: 1.45;
    }}
    a {{
      color: #0b57d0;
    }}
    .empty {{
      margin: 0;
      color: #596270;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)} report</h1>
    {learning_guide}
    {reproduce_section}
    {config_highlights}
    {result_check}
    {observation_markers}
    {interaction_section}
    <section>
      <h2>Summary</h2>
      <table>{rows}</table>
    </section>
    <section>
      <h2>Plots</h2>
      {plot_guide}
      <div class="plots">{plot_cards}</div>
    </section>
    <section>
      <h2>Notes</h2>
      {notes_html}
    </section>
    <section>
      <h2>Files</h2>
      <ul>{file_links}</ul>
    </section>
  </main>
</body>
</html>
"""


def _learning_guide_section(guide: RunGuide | None) -> str:
    if guide is None:
        return ""
    items = (
        ("Focus", guide.focus),
        ("Try", guide.try_this),
        ("Change", guide.change),
        ("Watch", guide.watch),
        ("Next", guide.next_step),
    )
    body = "\n".join(
        (
            '<div class="guide-item">'
            f"<strong>{escape(label)}</strong>"
            f"<span>{escape(text)}</span>"
            "</div>"
        )
        for label, text in items
    )
    return (
        "<section>"
        f"<h2>{escape(guide.title)}</h2>"
        '<div class="guide-grid">'
        f"{body}"
        "</div>"
        "</section>"
    )


def _reproduce_section(summary: dict[str, Any]) -> str:
    config_path = str(summary.get("config_path") or "").strip()
    lab_name = _cli_lab_name(str(summary.get("lab_name") or ""))
    if not config_path or not lab_name:
        return ""
    viewer_command = (
        f"python -m mclab run {lab_name} --config {config_path} "
        "--viewer --realtime --pause-at-end --plot"
    )
    headless_command = f"python -m mclab run {lab_name} --config {config_path} --headless --plot"
    return (
        "<section>"
        "<h2>Reproduce This Run</h2>"
        '<div class="command-grid">'
        '<div class="command-block">'
        "<strong>Watch it live</strong>"
        f"<pre>{escape(viewer_command)}</pre>"
        "</div>"
        '<div class="command-block">'
        "<strong>Regenerate artifacts</strong>"
        f"<pre>{escape(headless_command)}</pre>"
        "</div>"
        "</div>"
        '<p class="empty">Edit the YAML config, rerun one command, then compare the new report and plots.</p>'
        "</section>"
    )


def _cli_lab_name(lab_name: str) -> str:
    normalized = lab_name.lower()
    if "lab01" in normalized or "msd" in normalized:
        return "lab01"
    if "lab02" in normalized or "pid" in normalized:
        return "lab02"
    if "lab03" in normalized or "trajectory" in normalized or "2dof" in normalized:
        return "lab03"
    if "lab04" in normalized or "panda" in normalized:
        return "lab04"
    return ""


def _config_highlights_section(config: dict[str, Any]) -> str:
    pairs = _config_highlight_pairs(config)
    if not pairs:
        return ""
    cards = "\n".join(
        (
            '<article class="config-card">'
            f"<strong>{escape(key)}</strong>"
            f"<span>{escape(_format_value(value))}</span>"
            "</article>"
        )
        for key, value in pairs
    )
    return (
        "<section>"
        "<h2>Config Highlights</h2>"
        '<p class="empty">Edit these YAML values, rerun, then compare the response and report.</p>'
        '<div class="config-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _config_highlight_pairs(config: dict[str, Any]) -> list[tuple[str, Any]]:
    flattened = _flatten_config(config)
    if not flattened:
        return []
    pairs = [(key, flattened[key]) for key in CONFIG_HIGHLIGHT_KEYS if key in flattened]
    if not pairs:
        pairs = [
            (key, value)
            for key, value in flattened.items()
            if key not in {"model_path"} and not key.startswith("model_path.")
        ]
    return pairs[:28]


def _flatten_config(config: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in config.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_config(value, path))
        else:
            flattened[path] = value
    return flattened


def _result_check_section(summary: dict[str, Any]) -> str:
    checks = _result_checks(summary)
    if not checks:
        return ""
    cards = "\n".join(
        (
            '<article class="check-card">'
            f"<strong>{escape(title)}</strong>"
            f'<span class="check-state">{escape(state)}</span>'
            f'<p class="empty">{escape(detail)}</p>'
            "</article>"
        )
        for title, state, detail in checks
    )
    return (
        "<section>"
        "<h2>Result Check</h2>"
        '<p class="empty">These prompts are teaching aids, not pass/fail grades.</p>'
        '<div class="check-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _result_checks(summary: dict[str, Any]) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []
    samples = _number(summary.get("samples"))
    if samples is not None:
        state = "OK" if samples > 0 else "Review"
        checks.append(("Data saved", state, f"{_format_value(samples)} samples recorded."))

    duration = _number(summary.get("duration"))
    if duration is not None and duration > 0.0:
        checks.append(("Simulation time", "OK", f"{_format_value(duration)} seconds simulated."))

    _add_abs_limit_check(checks, summary, "final_tracking_error", "Final tracking error", 0.02, "m")
    _add_abs_limit_check(checks, summary, "final_joint_error_norm", "Final joint error", 0.1, "rad norm")
    _add_abs_limit_check(checks, summary, "final_task_error_norm", "Final hand error", 0.05, "m norm")
    _add_abs_limit_check(checks, summary, "final_cartesian_error_cm", "Final Cartesian error", 2.0, "cm")

    overshoot = _number(summary.get("overshoot_percent"))
    if overshoot is not None:
        state = "OK" if overshoot <= 20.0 else "Inspect"
        checks.append(("Overshoot", state, f"{_format_value(overshoot)} percent peak overshoot."))

    condition = _number(summary.get("max_jacobian_condition"))
    if condition is not None:
        state = "OK" if condition <= 100.0 else "Inspect"
        checks.append(("Jacobian condition", state, f"Maximum condition number {_format_value(condition)}."))

    wall_penetration = _number(summary.get("max_wall_penetration_cm"))
    if wall_penetration is not None and wall_penetration > 0.0:
        checks.append(("Virtual wall", "Inspect", f"Maximum penetration {_format_value(wall_penetration)} cm."))

    interaction_events = _number(summary.get("interaction_events"))
    if interaction_events is not None and interaction_events > 0.0:
        checks.append(("Learner actions", "Recorded", f"{_format_value(interaction_events)} interaction events saved."))

    return checks


def _add_abs_limit_check(
    checks: list[tuple[str, str, str]],
    summary: dict[str, Any],
    key: str,
    title: str,
    limit: float,
    unit: str,
) -> None:
    value = _number(summary.get(key))
    if value is None:
        return
    state = "OK" if abs(value) <= limit else "Inspect"
    checks.append((title, state, f"{_format_value(value)} {unit}; suggested limit {_format_value(limit)}."))


def _interaction_section(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    shown_events = events[-20:]
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{escape(_format_value(event.get('time')))}</td>"
            f"<td>{escape(str(event.get('kind', '')))}</td>"
            f"<td>{escape(str(event.get('label') or event.get('name') or ''))}</td>"
            f"<td>{escape(str(event.get('name', '')))}</td>"
            f"<td>{escape(_format_value(event.get('value')))}</td>"
            "</tr>"
        )
        for event in shown_events
    )
    count_text = (
        f"Showing the latest {len(shown_events)} of {len(events)} learner actions."
        if len(events) > len(shown_events)
        else f"{len(events)} learner action{'s' if len(events) != 1 else ''} recorded."
    )
    return (
        "<section>"
        "<h2>Interaction Log</h2>"
        f'<p class="empty">{escape(count_text)}</p>'
        "<table>"
        "<thead><tr><th>Time [s]</th><th>Type</th><th>Control</th><th>Name</th><th>Value</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        "</section>"
    )


def _observation_markers_section(events: list[dict[str, Any]]) -> str:
    markers = [event for event in events if _is_observation_marker(event)]
    if not markers:
        return ""
    shown_markers = markers[-12:]
    cards = "\n".join(
        _observation_marker_card(marker, marker_index + 1)
        for marker_index, marker in enumerate(shown_markers)
    )
    count_text = (
        f"Showing the latest {len(shown_markers)} of {len(markers)} marked observations."
        if len(markers) > len(shown_markers)
        else f"{len(markers)} marked observation{'s' if len(markers) != 1 else ''} saved."
    )
    return (
        "<section>"
        "<h2>Observation Markers</h2>"
        f'<p class="empty">{escape(count_text)}</p>'
        '<div class="marker-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _is_observation_marker(event: dict[str, Any]) -> bool:
    return str(event.get("kind", "")).lower() == "marker" and str(event.get("name", "")).lower() == "observation"


def _observation_marker_card(event: dict[str, Any], marker_index: int) -> str:
    payload = event.get("value")
    value = payload if isinstance(payload, dict) else {}
    sliders = _marker_value_group("Sliders", value.get("sliders"))
    status = _marker_value_group("Live status", value.get("status"))
    body = sliders + status
    if not body:
        body = '<p class="empty">No slider or status snapshot was saved for this marker.</p>'
    return (
        '<article class="marker-card">'
        f"<strong>Observation {marker_index}</strong>"
        f'<span class="marker-time">time {_format_value(event.get("time"))} s</span>'
        f"{body}"
        "</article>"
    )


def _marker_value_group(title: str, values: Any) -> str:
    if not isinstance(values, dict) or not values:
        return ""
    rows = "\n".join(
        (
            "<li>"
            f"<span>{escape(str(key))}</span>"
            f"<strong>{escape(_format_value(value))}</strong>"
            "</li>"
        )
        for key, value in values.items()
    )
    return (
        '<div class="marker-group">'
        f"<strong>{escape(title)}</strong>"
        f"<ul>{rows}</ul>"
        "</div>"
    )


def _plot_guide_section(plots: list[Path]) -> str:
    cards: list[str] = []
    for plot in plots:
        card = _plot_guide_card(plot)
        if card:
            cards.append(card)
    if not cards:
        return ""
    return (
        '<div class="plot-guide">'
        "<h3>Plot Guide</h3>"
        '<div class="plot-guide-grid">'
        f"{''.join(cards)}"
        "</div>"
        "</div>"
    )


def _plot_guide_card(plot: Path) -> str:
    guidance = _plot_guidance(plot.name)
    if guidance is None:
        return ""
    title, detail = guidance
    return (
        '<article class="plot-guide-card">'
        f"<strong>{escape(title)}</strong>"
        f"<span>{escape(plot.name)}</span>"
        f'<p class="empty">{escape(detail)}</p>'
        "</article>"
    )


def _plot_guidance(filename: str) -> tuple[str, str] | None:
    name = filename.lower()
    if "virtual_wall" in name:
        return (
            "Virtual Wall",
            "Watch penetration, wall force, and retreat. A useful wall demo shows contact response without runaway motion.",
        )
    if "wall_parameters" in name:
        return (
            "Wall Parameters",
            "Connect slider changes to wall position, stiffness, damping, and retreat settings used during the run.",
        )
    if "end_effector" in name:
        return (
            "End Effector",
            "Compare hand position against the target path. This is the clearest plot for task-space control behavior.",
        )
    if "cartesian_error" in name:
        return (
            "Cartesian Error",
            "Check whether hand error falls and stays small. Persistent error usually means target, gain, or actuator limits need attention.",
        )
    if "pid_terms" in name:
        return (
            "PID Terms",
            "Compare P, I, and D contributions. Large integral buildup or noisy derivative terms explain many controller surprises.",
        )
    if "dls" in name:
        return (
            "Damped Least Squares",
            "Compare task speed, joint speed, and damping. More damping usually calms joint motion near singularity but leaves more task error.",
        )
    if "current_proxy" in name:
        return (
            "Current Proxy",
            "Use this as an actuator effort proxy. Peaks show where the command would demand more motor current.",
        )
    if "singularity" in name:
        return (
            "Singularity",
            "Low manipulability or high condition number means the same hand motion can require much larger joint motion or torque.",
        )
    if "torque" in name:
        return (
            "Torque",
            "Look for peaks, clipping, and sign changes. High torque often comes from aggressive targets or gains.",
        )
    if "control_force" in name or "force" in name:
        return (
            "Force / Control Effort",
            "Compare effort against motion. Saturation, chatter, or delayed sign changes are good clues for tuning.",
        )
    if "energy" in name:
        return (
            "Energy",
            "Energy should decay with damping in passive demos. Slow decay means the system will keep oscillating longer.",
        )
    if "jerk" in name:
        return (
            "Jerk",
            "Jerk shows abrupt changes in acceleration. Smoother profiles are easier for actuators to track.",
        )
    if "acceleration" in name:
        return (
            "Acceleration",
            "Spikes indicate abrupt commands or aggressive gains. Smooth acceleration usually produces calmer effort plots.",
        )
    if "velocity" in name:
        return (
            "Velocity",
            "Use velocity to see oscillation and settling. A well damped run loses speed cleanly near the target.",
        )
    if "error" in name:
        return (
            "Error",
            "Check how quickly error shrinks and whether it settles near zero without repeated sign changes.",
        )
    if "position" in name:
        return (
            "Position",
            "Compare actual motion against target or reference. Look for overshoot, lag, oscillation, and steady-state error.",
        )
    return None


def _discover_runs(root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        summary = _read_json(child / "summary.json")
        report_path = child / "report.html"
        index_path = child / "index.html"
        if not summary and not report_path.exists() and not index_path.exists():
            continue
        guide = guide_for_run_summary(summary)
        modified = max(
            (
                path.stat().st_mtime
                for path in (report_path, index_path, child / "summary.json")
                if path.exists()
            ),
            default=child.stat().st_mtime,
        )
        runs.append(
            {
                "name": child.name,
                "lab_name": summary.get("lab_name", ""),
                "config_name": summary.get("config_name", ""),
                "config_path": summary.get("config_path", ""),
                "samples": summary.get("samples", ""),
                "duration": summary.get("duration", ""),
                "report": _run_link(child, report_path, index_path),
                "modified": modified,
                "summary": summary,
                "lesson_title": guide.title if guide is not None else "",
                "next_step": guide.next_step if guide is not None else "",
            }
        )
    return sorted(runs, key=lambda run: float(run["modified"]), reverse=True)


def _render_outputs_index(root: Path, runs: list[dict[str, Any]]) -> str:
    metric_keys = _index_metric_keys(runs)
    metric_headers = "".join(f"<th>{escape(_metric_label(key))}</th>" for key in metric_keys)
    learning_path = _learning_path_section(runs)
    progress_cards = _progress_cards(runs)
    rows = "\n".join(
        (
            "<tr>"
            f'<td><a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></td>'
            f"<td>{escape(str(run['lab_name']))}</td>"
            f"<td>{escape(_config_cell(run))}</td>"
            f"<td>{escape(str(run.get('lesson_title', '')))}</td>"
            f"<td>{escape(str(run.get('next_step', '')))}</td>"
            f"<td>{escape(_format_value(run['duration']))}</td>"
            f"<td>{escape(str(run['samples']))}</td>"
            + "".join(
                f"<td>{escape(_format_value(run.get('summary', {}).get(key, '')))}</td>"
                for key in metric_keys
            )
            + "</tr>"
        )
        for run in runs
    )
    if not rows:
        rows = f'<tr><td colspan="{7 + len(metric_keys)}">No run reports were found yet.</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MuJoCo Control Lab outputs</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: "Segoe UI", Arial, sans-serif;
      color: #202124;
      background: #f6f7f9;
    }}
    body {{
      margin: 0;
      padding: 24px;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    section {{
      background: #ffffff;
      border: 1px solid #d9dde3;
      border-radius: 8px;
      margin-top: 16px;
      padding: 16px;
    }}
    h1, p {{
      margin-top: 0;
      letter-spacing: 0;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    .progress-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .progress-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    .progress-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .path-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .path-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    .path-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .status {{
      display: inline-block;
      margin-top: 8px;
      color: #3f4752;
      font-size: 13px;
      font-weight: 600;
    }}
    .muted {{
      color: #596270;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid #edf0f3;
      padding: 9px 10px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      color: #3f4752;
      font-weight: 600;
    }}
    a {{
      color: #0b57d0;
    }}
  </style>
</head>
<body>
  <main>
    <h1>MuJoCo Control Lab outputs</h1>
    {learning_path}
    <section>
      <h2>Progress Snapshot</h2>
      <p>Open a run report to inspect the learning guide, summary values, notes, plots, and saved artifacts.</p>
      {progress_cards}
    </section>
    <section>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Run</th><th>Lab</th><th>Config</th><th>Lesson</th><th>Next</th><th>Duration [s]</th><th>Samples</th>{metric_headers}</tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def _learning_path_section(runs: list[dict[str, Any]]) -> str:
    items = [_learning_path_item(step, runs) for step in INDEX_LEARNING_PATH]
    completed = sum(1 for item in items if item["run"] is not None)
    next_item = next((item for item in items if item["run"] is None), None)
    if next_item is None:
        summary = f"{completed}/{len(items)} steps complete. Course path complete."
    else:
        summary = f"{completed}/{len(items)} steps complete. Next: {next_item['step'].title}"
    cards = "\n".join(_learning_path_card(item) for item in items)
    return (
        "<section>"
        "<h2>Learning Path</h2>"
        f'<p class="muted">{escape(summary)}</p>'
        '<div class="path-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _learning_path_item(step: IndexPathStep, runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"step": step, "run": _latest_learning_path_run(step, runs)}


def _learning_path_card(item: dict[str, Any]) -> str:
    step: IndexPathStep = item["step"]
    run = item["run"]
    if run is None:
        status = '<span class="status">Not run yet</span>'
    else:
        status = (
            '<span class="status">Done</span>'
            f'<p class="muted">Latest: <a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></p>'
        )
    return (
        '<article class="path-card">'
        f"<strong>{escape(step.title)}</strong>"
        f'<p class="muted">{escape(step.description)}</p>'
        f"{status}"
        "</article>"
    )


def _latest_learning_path_run(step: IndexPathStep, runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for run in runs:
        summary = run.get("summary", {})
        if step.batch_name:
            batch_name = str(summary.get("batch_name") or summary.get("config_name") or "")
            if batch_name == step.batch_name:
                return run
            continue
        if _normalize_path(str(summary.get("config_path") or run.get("config_path") or "")) == _normalize_path(
            step.config_path
        ):
            return run
    return None


def _progress_cards(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return '<p class="muted">No saved runs yet. Start with `run_mclab.cmd` or one of the `run_lab*.cmd` launchers.</p>'
    categories = (
        ("Lab01", "lab01"),
        ("Lab02", "lab02"),
        ("Lab03", "lab03"),
        ("Lab04", "lab04"),
        ("Batches", "batch"),
    )
    cards = []
    for label, key in categories:
        matches = [_run for _run in runs if _run_matches_category(_run, key)]
        latest = matches[0] if matches else None
        latest_link = (
            f'<a href="{escape(str(latest["report"]))}">{escape(str(latest["name"]))}</a>'
            if latest is not None
            else "Not run yet"
        )
        cards.append(
            "<div class=\"progress-card\">"
            f"<strong>{escape(label)}</strong>"
            f'<span class="muted">{len(matches)} saved run{"s" if len(matches) != 1 else ""}</span>'
            f'<p class="muted">Latest: {latest_link}</p>'
            "</div>"
        )
    return '<div class="progress-grid">' + "\n".join(cards) + "</div>"


def _run_matches_category(run: dict[str, Any], key: str) -> bool:
    text = " ".join(
        str(run.get(name, ""))
        for name in ("lab_name", "config_name", "config_path", "name")
    ).lower()
    return key in text


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./").lower()


def _index_metric_keys(runs: list[dict[str, Any]]) -> list[str]:
    summaries = [run.get("summary", {}) for run in runs]
    return [
        key
        for key in INDEX_METRIC_KEYS
        if any(_has_display_value(summary.get(key)) for summary in summaries)
    ]


def _has_display_value(value: Any) -> bool:
    return value is not None and value != ""


def _metric_label(key: str) -> str:
    return key.replace("_", " ")


def _report_title(output: Path, summary: dict[str, Any]) -> str:
    lab_name = str(summary.get("lab_name") or output.name)
    config_name = str(summary.get("config_name") or "")
    return f"{lab_name} - {config_name}" if config_name else lab_name


def _config_cell(run: dict[str, Any]) -> str:
    config_name = str(run.get("config_name") or "")
    config_path = str(run.get("config_path") or "")
    return config_path or config_name


def _run_link(child: Path, report_path: Path, index_path: Path) -> str:
    if report_path.exists():
        return f"{child.name}/report.html"
    if index_path.exists():
        return f"{child.name}/index.html"
    return child.name


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_config(path)
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _relative(root: Path, target: Path) -> str:
    return target.relative_to(root).as_posix()
