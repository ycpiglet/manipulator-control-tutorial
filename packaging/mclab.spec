# PyInstaller one-folder desktop build. Run from the repository root.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from mclab.application.asset_readiness import classify_panda_asset_failure
from mclab.application.assets import verify_assets

try:
    PANDA_ASSETS = verify_assets(root=ROOT)
except ValueError as exc:
    readiness = classify_panda_asset_failure(ROOT, exc)
    if readiness.code == "missing_asset":
        repair = "Run `python -m mclab assets install` before packaging."
    else:
        repair = (
            "For an invalid physical tree, run `python -m mclab assets install --force`; "
            "inspect unsafe links or reparse points manually."
        )
    raise RuntimeError(
        "PyInstaller input blocked: Panda runtime asset verification failed: "
        f"{exc}. {repair}"
    ) from exc

datas = [
    (str(ROOT / "configs"), "configs"),
    (str(ROOT / "models"), "models"),
    (str(ROOT / "src/mclab/application/qml"), "mclab/application/qml"),
    (str(PANDA_ASSETS.target), "third_party/mujoco_menagerie/franka_emika_panda"),
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
        # QtTest is used only by source UI-audit actions. The packaged learner
        # app uses QGuiApplication and Qt Quick, so exclude QtTest and its
        # QtWidgets dependency while keeping both available to source audits.
        "PySide6.QtTest",
        "PySide6.QtWidgets",
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
