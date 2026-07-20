"""Keyboard-path input helpers for explicit Qt self-test actions."""

from __future__ import annotations

from typing import Any


def activate_object(root: Any, object_name: str, label: str) -> None:
    """Activate one named QML control through its keyboard interaction path."""

    from PySide6.QtCore import QObject, Qt
    from PySide6.QtTest import QTest

    control = root.findChild(QObject, object_name)
    if control is None:
        raise RuntimeError(f"{label} control was not found.")
    control.forceActiveFocus()
    QTest.keyClick(root, Qt.Key.Key_Return)


def type_into(root: Any, object_name: str, value: str) -> None:
    """Enter beta-task text through Qt's keyboard path, not property injection."""

    from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt
    from PySide6.QtGui import QGuiApplication, QInputMethodEvent, QKeyEvent

    control = root.findChild(QObject, object_name)
    if control is None:
        raise RuntimeError(f"Evidence input was not found: {object_name}")
    control.forceActiveFocus()
    if not value.isascii():
        event = QInputMethodEvent()
        event.setCommitString(value)
        if not QCoreApplication.sendEvent(control, event):
            raise RuntimeError(f"IME text commit was rejected: {object_name}")
        return
    target = QGuiApplication.focusObject() or control
    special = {
        " ": (Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier),
        ".": (Qt.Key.Key_Period, Qt.KeyboardModifier.NoModifier),
        ",": (Qt.Key.Key_Comma, Qt.KeyboardModifier.NoModifier),
        "-": (Qt.Key.Key_Minus, Qt.KeyboardModifier.NoModifier),
        "_": (Qt.Key.Key_Minus, Qt.KeyboardModifier.ShiftModifier),
    }
    for character in value:
        modifier = Qt.KeyboardModifier.NoModifier
        if character.isalpha():
            key = Qt.Key.Key_A + ord(character.lower()) - ord("a")
            if character.isupper():
                modifier = Qt.KeyboardModifier.ShiftModifier
        elif character.isdigit():
            key = Qt.Key.Key_0 + int(character)
        elif character in special:
            key, modifier = special[character]
        else:
            raise RuntimeError(f"Unsupported beta-task character: {character!r}")
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            event = QKeyEvent(event_type, int(key), modifier, character)
            QCoreApplication.sendEvent(target, event)
