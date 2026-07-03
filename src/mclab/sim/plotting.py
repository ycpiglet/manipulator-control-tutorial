"""Standard plotting utilities for lab outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from pathlib import Path
from typing import Any

from mclab.sim.reporting import write_run_report


PlotSpec = tuple[str, str, str, Sequence[str]]
PlotEventMarker = tuple[float, str]
PlotEventMarkers = Mapping[str, Sequence[PlotEventMarker]]
PlotSelection = str | Sequence[str] | None


def save_time_series_plots(
    output_path: str | Path,
    rows: Sequence[dict[str, Any]],
    specs: Sequence[PlotSpec],
    *,
    event_markers: PlotEventMarkers | None = None,
) -> None:
    """Save simple time-series plots from logger rows."""

    if not rows:
        return

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("matplotlib is required when --plot is used.") from exc

    output = Path(output_path)
    plot_dir = output / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
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
        for key in available:
            values = [_as_float(row.get(key)) for row in rows]
            axis.plot(time, values, label=key)
        axis.set_title(title)
        axis.set_xlabel("time [s]")
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.3)
        _apply_event_markers(axis, marker_map.get(_plot_name(filename), ()))
        axis.legend()
        fig.savefig(plot_dir / filename, dpi=150)
        plt.close(fig)

    write_run_report(output)


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
