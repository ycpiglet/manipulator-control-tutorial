"""Configuration loading and validation helpers."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def is_frozen_bundle() -> bool:
    """Return whether MCLab is running from a packaged desktop build."""

    return bool(getattr(sys, "frozen", False))


def default_outputs_root() -> Path:
    """Return a writable output location without moving source-tree runs."""

    override = os.environ.get("MCLAB_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve() / "outputs"
    if not is_frozen_bundle():
        return PROJECT_ROOT / "outputs"
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData/Local"
        return base / "MCLab" / "outputs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MCLab" / "outputs"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local/share"
    return base / "mclab" / "outputs"


def resolve_output_path(path: str | Path) -> Path:
    """Resolve a user-selected output path against a writable runtime root."""

    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    if is_frozen_bundle():
        return default_outputs_root().parent / candidate
    return PROJECT_ROOT / candidate


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file.

    PyYAML is used when installed. A small fallback parser keeps basic tests and
    config inspection usable before the optional runtime dependencies are
    installed.
    """

    config_path = resolve_project_path(path)
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        data = _load_simple_yaml(text)
    else:
        loaded = yaml.safe_load(text)
        data = loaded if loaded is not None else {}

    if not isinstance(data, dict):
        raise ValueError(f"Config must contain a mapping at the top level: {config_path}")
    return data


def resolve_project_path(path: str | Path) -> Path:
    """Resolve a path relative to the repository root."""

    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _load_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            raise ValueError(f"Unsupported YAML syntax at line {line_number}: {raw_line}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValueError(f"Invalid indentation at line {line_number}: {raw_line}")

        parent = stack[-1][1]
        if not value:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)

    return root


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [item.strip() for item in value[1:-1].split(",") if item.strip()]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        if any(marker in value for marker in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value
