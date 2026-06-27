"""Standard plotting utilities for lab outputs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any


PlotSpec = tuple[str, str, str, Sequence[str]]


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


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")

