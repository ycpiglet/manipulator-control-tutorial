"""OS integration kept outside simulation and UI code."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path


class PlatformServices:
    def open_path(self, path: str | Path) -> None:
        target = Path(path).resolve()
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def viewer_python(self) -> str:
        """Return the supported MuJoCo viewer executable for this platform."""

        if sys.platform == "darwin":
            sibling = Path(sys.executable).with_name("mjpython")
            return str(sibling) if sibling.exists() else "mjpython"
        return sys.executable

    def viewer_command(self, arguments: list[str]) -> list[str]:
        return [self.viewer_python(), "-m", "mclab", *arguments]
