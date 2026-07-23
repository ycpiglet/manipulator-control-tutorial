"""Standard plotting utilities for lab outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO
from math import isfinite
from pathlib import Path
from typing import Any

from mclab.output_publication import mutable_run_publication
from mclab.output_safety import MAX_METADATA_BYTES
from mclab.sim.reporting import write_run_report


PlotSpec = tuple[str, str, str, Sequence[str]]
PlotEventMarker = tuple[float, str]
PlotEventMarkers = Mapping[str, Sequence[PlotEventMarker]]
PlotSelection = str | Sequence[str] | None

SIGNAL_LABELS = {
    "en": {
        "position": "Current position [m]",
        "measured_position": "Measured position [m]",
        "target_position": "Target position [m]",
        "position_error": "Position error [m]",
        "velocity": "Velocity [m/s]",
        "control_force": "Control force [N]",
        "manual_force": "Disturbance force [N]",
        "total_force": "Total applied force [N]",
        "force_virtual_0": "Virtual-wall force X [N]",
        "wall_penetration": "Wall penetration [m]",
        "task_error_norm": "Hand tracking error [m]",
        "jacobian_condition": "Jacobian condition number",
        "manipulability": "Manipulability",
    },
    "ko": {
        "position": "현재 위치 [m]",
        "measured_position": "측정 위치 [m]",
        "target_position": "목표 위치 [m]",
        "position_error": "위치 오차 [m]",
        "velocity": "속도 [m/s]",
        "control_force": "제어 힘 [N]",
        "manual_force": "외란 힘 [N]",
        "total_force": "전체 작용 힘 [N]",
        "force_virtual_0": "가상 벽 X 힘 [N]",
        "wall_penetration": "벽 침투 깊이 [m]",
        "task_error_norm": "손끝 추종 오차 [m]",
        "jacobian_condition": "Jacobian 조건수",
        "manipulability": "조작성",
    },
}


def save_time_series_plots(
    output_path: str | Path,
    rows: Sequence[dict[str, Any]],
    specs: Sequence[PlotSpec],
    *,
    event_markers: PlotEventMarkers | None = None,
    write_report: bool = True,
) -> None:
    """Save simple time-series plots from logger rows."""

    if not rows:
        return

    try:
        import matplotlib

        matplotlib.use("Agg")
        configure_matplotlib_font(matplotlib)
        import matplotlib.pyplot as plt  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("matplotlib is required when --plot is used.") from exc

    output = Path(output_path)
    with mutable_run_publication(output) as publication:
        config_data = (
            publication.read_bytes(
                ("config.yaml",),
                description="plot config",
                max_bytes=MAX_METADATA_BYTES,
                allow_empty=True,
            )
            if publication.regular_file_exists(("config.yaml",))
            else b""
        )
        language = _plot_language(config_data)
        publication.ensure_directory(("plots",))
        marker_map = {
            _plot_name(plot_name): markers
            for plot_name, markers in (event_markers or {}).items()
        }

        time = [_as_float(row.get("time", index)) for index, row in enumerate(rows)]
        for filename, title, ylabel, keys in specs:
            available = [key for key in keys if any(key in row for row in rows)]
            if not available:
                continue
            fig, axis = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
            try:
                for key in available:
                    values = [_as_float(row.get(key)) for row in rows]
                    axis.plot(
                        time,
                        values,
                        label=_signal_label(key, language),
                        markevery=max(1, len(time) // 18),
                        **_signal_style(key),
                    )
                first_key = available[0]
                first_values = [_as_float(row.get(first_key)) for row in rows]
                _annotate_peak(axis, time, first_values, language)
                axis.set_title(title)
                axis.set_xlabel("시간 [초]" if language == "ko" else "Time [s]")
                axis.set_ylabel(ylabel)
                axis.grid(True, alpha=0.3)
                _apply_event_markers(axis, marker_map.get(_plot_name(filename), ()))
                axis.legend()
                buffer = BytesIO()
                fig.savefig(buffer, format="png", dpi=150)
                publication.write_bytes(("plots", filename), buffer.getvalue())
            finally:
                plt.close(fig)

    # The terminal manifest is published by RunLogger only after every
    # run-local artifact exists.  Updating the parent index here would expose a
    # stale running verdict, so finalization performs that refresh instead.
    if write_report:
        write_run_report(output, update_index=False)


def configure_matplotlib_font(matplotlib: Any) -> None:
    """Register the licensed bundled Korean font for plots and annotations."""

    from mclab.config import PROJECT_ROOT

    font_path = PROJECT_ROOT / "third_party" / "fonts" / "noto" / "NotoSansKR[wght].ttf"
    if not font_path.exists():
        return
    from matplotlib import font_manager

    font_manager.fontManager.addfont(str(font_path))
    family = font_manager.FontProperties(fname=str(font_path)).get_name()
    matplotlib.rcParams["font.family"] = family
    matplotlib.rcParams["axes.unicode_minus"] = False


def select_plot_specs(
    specs: Sequence[PlotSpec],
    selection: PlotSelection = None,
    *,
    presets: Mapping[str, Sequence[str]] | None = None,
) -> list[PlotSpec]:
    tokens = _selection_tokens(selection)
    if not tokens or "all" in tokens:
        return list(specs)

    preset_map = {
        _plot_name(name): [_plot_name(item) for item in names]
        for name, names in (presets or {}).items()
    }
    requested: list[str] = []
    for token in tokens:
        requested.extend(preset_map.get(token, [token]))

    available = {_plot_name(spec[0]) for spec in specs}
    unknown = sorted(set(requested) - available)
    if unknown:
        preset_names = sorted(preset_map)
        suffix = f" Presets: {', '.join(preset_names)}." if preset_names else ""
        raise ValueError(
            f"Unknown plot selection(s): {', '.join(unknown)}. "
            f"Available plots: {', '.join(sorted(available))}.{suffix}"
        )

    requested_set = set(requested)
    return [spec for spec in specs if _plot_name(spec[0]) in requested_set]


def _selection_tokens(selection: PlotSelection) -> list[str]:
    if selection is None:
        return []
    if isinstance(selection, str):
        values = selection.split(",")
    else:
        values = list(selection)
    return [_plot_name(value) for value in values if str(value).strip()]


def _plot_name(value: str) -> str:
    return Path(str(value).strip()).stem.lower().replace("-", "_")


def _apply_event_markers(axis: Any, markers: Sequence[PlotEventMarker]) -> None:
    clean_markers = [
        (float(time), str(label))
        for time, label in markers
        if isfinite(float(time)) and str(label).strip()
    ]
    if not clean_markers:
        return

    transform = axis.get_xaxis_transform()
    for index, (time, label) in enumerate(clean_markers):
        axis.axvline(time, color="#2f2f2f", linestyle="--", linewidth=1.0, alpha=0.45)
        axis.text(
            time,
            0.98 - 0.12 * (index % 3),
            label,
            rotation=90,
            va="top",
            ha="right",
            fontsize=7,
            color="#2f2f2f",
            transform=transform,
        )


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _plot_language(config_data: bytes) -> str:
    for line in config_data.decode("utf-8", errors="replace").splitlines():
        if line.strip().startswith("language:"):
            value = line.split(":", 1)[1].strip().lower()
            return "ko" if value == "ko" else "en"
    return "en"


def _signal_label(key: str, language: str) -> str:
    return SIGNAL_LABELS[language].get(key, key.replace("_", " ").title())


def _signal_style(key: str) -> dict[str, Any]:
    lowered = key.lower()
    if "target" in lowered or "reference" in lowered:
        return {"color": "#C084FC", "linestyle": "--", "marker": "D", "linewidth": 1.8}
    if "force" in lowered or "tau" in lowered or "disturbance" in lowered:
        return {"color": "#E44C65", "linestyle": "-.", "marker": ">", "linewidth": 1.6}
    if "wall" in lowered or "limit" in lowered or "saturat" in lowered:
        return {"color": "#B77900", "linestyle": ":", "marker": "s", "linewidth": 1.8}
    return {"color": "#008CA8", "linestyle": "-", "marker": "o", "linewidth": 1.8}


def _annotate_peak(
    axis: Any, time: Sequence[float], values: Sequence[float], language: str
) -> None:
    finite = [(index, value) for index, value in enumerate(values) if isfinite(value)]
    if not finite:
        return
    index, value = max(finite, key=lambda item: abs(item[1]))
    label = "최대값" if language == "ko" else "Peak"
    axis.annotate(
        f"{label}: {value:.3g}",
        xy=(time[index], value),
        xytext=(8, 12),
        textcoords="offset points",
        fontsize=8,
        color="#172033",
        arrowprops={"arrowstyle": "->", "color": "#5B6475", "linewidth": 0.8},
    )
