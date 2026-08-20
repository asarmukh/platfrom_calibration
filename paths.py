"""Filesystem locations, aware of the PyInstaller bundle layout.

Running from source both directories are the project root. Inside a built exe
they differ: assets are unpacked to a temporary folder, while anything the user
edits has to sit next to the executable to survive a restart.
"""

from __future__ import annotations

import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True when running from a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Read-only assets shipped with the app (logo files).

    One-file builds unpack them to `sys._MEIPASS`; one-folder builds keep them
    beside the executable.
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return SOURCE_ROOT


def app_dir() -> Path:
    """Where user-editable files live, such as config.ini."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return SOURCE_ROOT
