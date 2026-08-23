"""Render the running UI with injected device traffic, for visual checking.

    python tests/render_views.py

Writes one PNG per state to tests/_views/. Not a test: it proves nothing on
its own, it just makes the layout and the section 6 readouts easy to eyeball
against a real platform.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

import app as app_module  # noqa: E402
from conftest import FakeConnection  # noqa: E402
from device.connection import CONNECTED  # noqa: E402
from device.settings import AppConfig  # noqa: E402
from widgets.workspace import CAL  # noqa: E402


def shot(window, name: str) -> None:
    QApplication.processEvents()
    folder = Path(__file__).parent / "_views"
    folder.mkdir(exist_ok=True)
    path = folder / f"{name}.png"
    window.grab().save(str(path))
    print(f"{name}: {path}")


def main() -> None:
    qt = QApplication(sys.argv)
    app_module.ConnectionController = FakeConnection
    window = app_module.MainWindow(AppConfig())
    window.resize(1280, 800)
    window.show()
    device = window.connection
    device.stateChanged.emit(CONNECTED, "connected to COM5 at 115200 baud")

    shot(window, "1_nothing_chosen")

    window.sidebar.platform_type.set_active(0)  # SINGLE
    shot(window, "2_type_but_no_id")

    window.sidebar.platform_id.setText("1")
    shot(window, "3_single_gf")

    window.sidebar.platform_type.set_active(1)  # DOUBLE
    window.workspace.pad_view.set_view(CAL)
    window.sidebar.read_button.click()
    device.factors(1, 1, [100] * 8)
    device.factors(1, 2, [100] * 8)
    QApplication.processEvents()

    window.sidebar.start_button.click()
    # A load towards the front-right of pad 1: ch1 heaviest, ch4 lightest.
    device.readings(1, 1, [120, 4000, 1500, 0, 500, 2000, -80, 0])
    device.readings(1, 2, [40, 900, 600, 0, 300, 700, -20, 0])
    QApplication.processEvents()
    window._render_readings()
    shot(window, "4_double_running")

    qt.quit()


if __name__ == "__main__":
    main()
