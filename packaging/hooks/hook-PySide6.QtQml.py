"""Collect only the QML modules used by the MCLab interface.

PyInstaller's general QtQml hook deliberately bundles every QML module in the
installed Qt distribution.  That is useful for unknown applications but adds
unrelated controls styles, a virtual keyboard, test tooling, and Wayland
compositor modules to this fixed UI.
"""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

qml_root = Path(pyside6_library_info.location["QmlImportsPath"])
modules = (
    "QtQml/Models",
    "QtQml/WorkerScript",
    "QtQuick/Layouts",
    "QtQuick/Templates",
    "QtQuick/Window",
    "QtQuick/Controls/Basic",
    "QtQuick/Controls/impl",
)


def _add_file(source: Path) -> None:
    destination = Path("PySide6/Qt/qml") / source.relative_to(qml_root).parent
    entry = (str(source), str(destination))
    if source.suffix in {".so", ".dll", ".dylib"}:
        binaries.append(entry)
    else:
        datas.append(entry)


for source in qml_root.glob("QtQml/*"):
    if source.is_file():
        _add_file(source)
for source in qml_root.glob("QtQuick/*"):
    if source.is_file():
        _add_file(source)
for source in qml_root.glob("QtQuick/Controls/*"):
    if source.is_file():
        _add_file(source)
for module in modules:
    for source in (qml_root / module).rglob("*"):
        if source.is_file():
            _add_file(source)
