"""Per-user desktop-process lock acquired before a second Qt GUI is created."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from mclab.application.i18n import Translator


@dataclass
class InstanceLease:
    lock: Any
    socket_name: str

    def unlock(self) -> None:
        self.lock.unlock()


def acquire_instance_lock(language: str | None) -> InstanceLease | None:
    """Return a held QLockFile, or report the existing app and return None."""

    from PySide6.QtCore import QLockFile, QStandardPaths

    override = os.environ.get("MCLAB_INSTANCE_LOCK", "").strip()
    if override:
        lock_path = Path(override)
    else:
        root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        )
        lock_path = Path(root) / "mclab-desktop.lock"
    socket_name = "mclab-" + sha256(str(lock_path).encode("utf-8")).hexdigest()[:16]
    translator = Translator(language)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"{translator.text('error.app_running')} ({exc})", file=sys.stderr)
        return None
    instance_lock = QLockFile(str(lock_path))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(0):
        activated = _request_existing_window(socket_name)
        key = "error.app_activated" if activated else "error.app_running"
        print(translator.text(key), file=sys.stderr)
        return None
    return InstanceLease(instance_lock, socket_name)


def start_activation_server(lease: InstanceLease, window: Any) -> Any | None:
    """Listen for later launches and bring the owned window to the foreground."""

    from PySide6.QtNetwork import QLocalServer

    QLocalServer.removeServer(lease.socket_name)
    server = QLocalServer(window)
    if not server.listen(lease.socket_name):
        return None
    activation_count = 0

    def activate() -> None:
        nonlocal activation_count
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            if connection is None:
                continue
            connection.waitForReadyRead(100)
            command = bytes(connection.readAll()).decode("utf-8", errors="replace").strip()
            if command == "activate":
                methods = ["showNormal", "requestActivate"]
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    methods.insert(1, "raise_")
                for method_name in methods:
                    method = getattr(window, method_name, None)
                    if callable(method):
                        method()
                activation_count += 1
                _record_activation(activation_count)
                connection.write(b"activated\n")
                connection.flush()
                connection.waitForBytesWritten(100)
            connection.disconnectFromServer()

    server.newConnection.connect(activate)
    return server


def _request_existing_window(socket_name: str) -> bool:
    from PySide6.QtNetwork import QLocalSocket

    deadline = time.monotonic() + 0.8
    while time.monotonic() < deadline:
        connection = QLocalSocket()
        connection.connectToServer(socket_name)
        if connection.waitForConnected(120):
            connection.write(b"activate\n")
            if connection.waitForBytesWritten(200):
                connection.waitForReadyRead(300)
                acknowledged = b"activated" in bytes(connection.readAll())
                connection.disconnectFromServer()
                return acknowledged
        connection.abort()
        time.sleep(0.04)
    return False


def _record_activation(count: int) -> None:
    destination = os.environ.get("MCLAB_ACTIVATION_PATH", "").strip()
    if not destination:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"activation_count": count}), encoding="utf-8")
