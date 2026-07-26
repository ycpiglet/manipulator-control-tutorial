"""QSettings selection for normal launches and explicit startup probes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def create_application_settings(settings_type: Any) -> Any:
    """Use one explicit INI only for the packaged startup self-test."""

    startup_self_test = (
        os.environ.get("MCLAB_SELF_TEST") == "1"
        and os.environ.get("MCLAB_SMOKE_ACTION") == "startup_probe"
    )
    if not startup_self_test:
        return settings_type("MCLab", "MCLab")

    raw_path = os.environ.get("MCLAB_STARTUP_SETTINGS_PATH", "").strip()
    settings_path = Path(raw_path)
    if not raw_path or not settings_path.is_absolute():
        raise RuntimeError(
            "Packaged startup self-test requires an absolute MCLAB_STARTUP_SETTINGS_PATH."
        )
    settings = settings_type(
        os.fspath(settings_path),
        settings_type.Format.IniFormat,
    )
    settings.setFallbacksEnabled(False)
    return settings
