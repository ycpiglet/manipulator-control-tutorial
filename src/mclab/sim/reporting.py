"""HTML report generation for saved lab runs."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

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
    "max_cartesian_error_cm",
    "final_cartesian_error_cm",
    "max_wall_penetration_cm",
    "max_wall_retreat_cm",
    "max_abs_virtual_wall_force",
)


def write_run_report(output_path: str | Path) -> Path:
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    summary = _read_json(output / "summary.json")
    notes = _read_text(output / "notes.md")
    plots = sorted((output / "plots").glob("*.png"))

    html = _render_report(output, summary, notes, plots)
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


def _render_report(output: Path, summary: dict[str, Any], notes: str, plots: list[Path]) -> str:
    title = _report_title(output, summary)
    learning_guide = _learning_guide_section(guide_for_run_summary(summary))
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
        for name in ("config.yaml", "summary.json", "notes.md", "log.csv", "states.npz")
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
    h1, h2 {{
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 28px;
    }}
    h2 {{
      font-size: 20px;
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
    <section>
      <h2>Summary</h2>
      <table>{rows}</table>
    </section>
    <section>
      <h2>Plots</h2>
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
            }
        )
    return sorted(runs, key=lambda run: float(run["modified"]), reverse=True)


def _render_outputs_index(root: Path, runs: list[dict[str, Any]]) -> str:
    metric_keys = _index_metric_keys(runs)
    metric_headers = "".join(f"<th>{escape(_metric_label(key))}</th>" for key in metric_keys)
    rows = "\n".join(
        (
            "<tr>"
            f'<td><a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></td>'
            f"<td>{escape(str(run['lab_name']))}</td>"
            f"<td>{escape(_config_cell(run))}</td>"
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
        rows = f'<tr><td colspan="{5 + len(metric_keys)}">No run reports were found yet.</td></tr>'

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
    <section>
      <p>Open a run report to inspect summary values, notes, plots, and saved artifacts.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Run</th><th>Lab</th><th>Config</th><th>Duration [s]</th><th>Samples</th>{metric_headers}</tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


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


def _relative(root: Path, target: Path) -> str:
    return target.relative_to(root).as_posix()
