# PyInstaller one-folder desktop build. Run from the repository root.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

datas = [
    (str(ROOT / "configs"), "configs"),
    (str(ROOT / "models"), "models"),
    (str(ROOT / "src/mclab/application/qml"), "mclab/application/qml"),
    (str(ROOT / "third_party/mujoco_menagerie/franka_emika_panda/assets"),
     "third_party/mujoco_menagerie/franka_emika_panda/assets"),
    (str(ROOT / "third_party/mujoco_menagerie/franka_emika_panda/panda.xml"),
     "third_party/mujoco_menagerie/franka_emika_panda"),
    (str(ROOT / "third_party/mujoco_menagerie/franka_emika_panda/panda_nohand.xml"),
     "third_party/mujoco_menagerie/franka_emika_panda"),
    (str(ROOT / "third_party/mujoco_menagerie/franka_emika_panda/hand.xml"),
     "third_party/mujoco_menagerie/franka_emika_panda"),
    (str(ROOT / "third_party/mujoco_menagerie/franka_emika_panda/scene.xml"),
     "third_party/mujoco_menagerie/franka_emika_panda"),
    (str(ROOT / "third_party/mujoco_menagerie/franka_emika_panda/LICENSE"),
     "third_party/mujoco_menagerie/franka_emika_panda"),
    (str(ROOT / "third_party/fonts/noto"), "third_party/fonts/noto"),
    (str(ROOT / "LICENSE"), "."),
]

hiddenimports = [
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
]

a = Analysis(
    [str(ROOT / "packaging/entrypoint.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging/hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtCharts",
        "PySide6.Qt3DCore",
        "matplotlib.backends.backend_qt5agg",
        "matplotlib.backends.backend_tkagg",
    ],
    noarchive=False,
    optimize=1,
)

# English is Qt's built-in source language; keep only Korean catalogs for the
# app's other supported locale.  MCLab's own text is translated independently.
a.datas = [
    entry
    for entry in a.datas
    if not entry[0].startswith("PySide6/Qt/translations/")
    or entry[0].endswith("_ko.qm")
]

if sys.platform.startswith("linux"):
    # Basic Qt Quick controls do not use GTK's optional native widget theme.
    linux_omissions = {
        "PySide6/Qt/plugins/platformthemes/libqgtk3.so",
        "libgtk-3.so.0",
    }
    a.binaries = [entry for entry in a.binaries if entry[0] not in linux_omissions]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MCLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MCLab",
)
