"""Machine-checkable colors and redundant shapes for educational scene markers."""

from __future__ import annotations

from itertools import combinations

import numpy as np

SEMANTIC_COLORS = {
    "background": "#111827",
    "current": "#22D3EE",
    "target": "#C084FC",
    "force": "#FB7185",
    "wall": "#FBBF24",
    "spring": "#FBBF24",
    "workspace": "#386BAD",
}

SEMANTIC_SHAPES = {
    "current": "circle-solid",
    "target": "diamond-dashed",
    "force": "arrow",
    "wall": "hatched-grid",
    "spring": "zigzag",
    "workspace": "circle-outline",
}

CVD_MATRICES = {
    "protanopia": np.asarray(
        ((0.567, 0.433, 0.0), (0.558, 0.442, 0.0), (0.0, 0.242, 0.758))
    ),
    "deuteranopia": np.asarray(
        ((0.625, 0.375, 0.0), (0.700, 0.300, 0.0), (0.0, 0.300, 0.700))
    ),
    "tritanopia": np.asarray(
        ((0.950, 0.050, 0.0), (0.0, 0.433, 0.567), (0.0, 0.475, 0.525))
    ),
}


def rgb(color: str) -> np.ndarray:
    """Convert a CSS hex color to a three-channel float vector."""

    value = color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"Expected a six-digit hex color, got {color!r}.")
    return np.asarray([int(value[index : index + 2], 16) for index in (0, 2, 4)], dtype=float)


def color_vision_separation() -> dict[str, dict[str, float]]:
    """Return worst-case token and background distances under common CVD transforms."""

    names = ("current", "target", "force", "wall")
    values = {name: rgb(SEMANTIC_COLORS[name]) for name in names}
    background = rgb(SEMANTIC_COLORS["background"])
    results: dict[str, dict[str, float]] = {}
    for condition, matrix in CVD_MATRICES.items():
        transformed = {name: matrix @ value for name, value in values.items()}
        transformed_background = matrix @ background
        token_distance = min(
            float(np.linalg.norm(transformed[first] - transformed[second]))
            for first, second in combinations(names, 2)
        )
        background_distance = min(
            float(np.linalg.norm(value - transformed_background))
            for value in transformed.values()
        )
        results[condition] = {
            "minimum_token_distance": token_distance,
            "minimum_background_distance": background_distance,
        }
    return results
