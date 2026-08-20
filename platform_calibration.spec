# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build: pyinstaller platform_calibration.spec

Produces a single dist/PlatformCalibration.exe. config.ini is deliberately not
bundled — the app writes it next to the executable on first run, so the port
and baud rate stay editable.
"""

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    # Read-only assets, unpacked beside the app at runtime (see paths.py).
    datas=[
        ("logo.svg", "."),
        ("logo.jpeg", "."),
    ],
    hiddenimports=["serial.tools.list_ports"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc_data",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtMultimedia",
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PlatformCalibration",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # console=True prints the connection log; flip it when debugging a port.
    console=False,
    disable_windowed_traceback=False,
    icon="logo.ico",
)
