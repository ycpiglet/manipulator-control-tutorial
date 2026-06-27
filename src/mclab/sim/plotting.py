"""Standard plotting utilities for lab outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mclab.sim.reporting import write_run_report


PlotSpec = tuple[str, str, str, Sequence[str]]
PlotSelection = str | Sequence[str] | None


def save_time_series_plots(
    output_path: str | Path,
    rows: Sequence[dict[str, Any]],
    specs: Sequence[PlotSpec],
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


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")
