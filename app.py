"""Application shell for the Platform Calibration UI.

The calibration widgets are still presentation-only, but the device connection
is live: the window opens the port from config.ini on startup, retrying on a
worker thread, and reports progress in the status bar.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import theme
from settings import AppConfig
from device.connection import (
    CONNECTED,
    CONNECTING,
    ConnectionController,
    FAILED,
)
from widgets.common import label
from widgets.header_bar import HeaderBar, StatusDot
from widgets.sidebar import Sidebar
from widgets.workspace import CAL, Workspace

WINDOW_TITLE = "Platform Calibration"
DEFAULT_SIZE = (1280, 800)
MINIMUM_SIZE = (1024, 680)

STATE_COLORS = {
    CONNECTED: theme.ONLINE,
    CONNECTING: theme.ACCENT_SOFT,
    FAILED: theme.ACCENT,
}


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, startup_error: str = "") -> None:
        super().__init__()
        self.config = config
        self._running = False  # latched by the Start button
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*DEFAULT_SIZE)
        self.setMinimumSize(*MINIMUM_SIZE)

        root = QWidget()
        column = QVBoxLayout(root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        self.header = HeaderBar()
        column.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = Sidebar()
        self.workspace = Workspace()
        body.addWidget(self.sidebar)
        body.addWidget(self.workspace, 1)
        column.addLayout(body, 1)

        # SINGLE / DOUBLE drives how many pads the workspace shows.
        self.sidebar.platform_type.changed.connect(
            lambda index: self.workspace.set_pad_count(2 if index else 1)
        )
        self.workspace.pad_view.viewChanged.connect(self._on_view_changed)
        self.sidebar.start_button.toggled.connect(self._on_start_toggled)

        self.setCentralWidget(root)
        self._build_status_bar()

        self.connection = ConnectionController(config.serial, config.retry, self)
        self.connection.stateChanged.connect(self._on_connection_state)

        self._apply_controls()

        if startup_error:
            self._show_status(theme.ACCENT, startup_error)
        # Connect once the window is on screen, so the first paint is not held
        # up by the port opening.
        QTimer.singleShot(0, self.connection.start)

    # --- status bar --------------------------------------------------------

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        self.setStatusBar(bar)

        self.status_dot = StatusDot()
        self.status_label = label(
            "", role="mono", size=9, color=theme.MUTED, tracking=0.06
        )

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(18, 2, 0, 2)
        row.setSpacing(8)
        row.addWidget(self.status_dot)
        row.addWidget(self.status_label)
        bar.addWidget(holder, 1)

        self.status_action = QPushButton("RETRY")
        self.status_action.setObjectName("statusAction")
        self.status_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_action.setFont(theme.font("mono", 8, tracking=0.1))
        self.status_action.clicked.connect(self._on_status_action)
        self.status_action.hide()
        bar.addPermanentWidget(self.status_action)

    def _show_status(self, color: str, message: str) -> None:
        self.status_dot.set_color(color)
        self.status_label.setText(message)
        # The driver's full complaint is too long for the bar; keep it reachable.
        self.status_label.setToolTip(self.connection.last_error)

    def _on_status_action(self) -> None:
        if self.connection.state == CONNECTING:
            self.connection.cancel()
        else:
            self.connection.start()

    # --- control availability ----------------------------------------------

    def _on_view_changed(self, view: str) -> None:
        # Start belongs to the CAL section, so leaving it ends the run rather
        # than stranding a latched button the user can no longer press.
        if view != CAL and self._running:
            self.sidebar.start_button.setChecked(False)
        self._apply_controls()

    def _on_start_toggled(self, running: bool) -> None:
        self._running = running
        self.sidebar.start_button.setText("STOP" if running else "START")
        self._apply_controls()

    def _apply_controls(self) -> None:
        """Enable the controls that make sense for the current state."""
        connected = self.connection.state == CONNECTED
        calibrating = self.workspace.pad_view.view == CAL

        # Read/Write talk to the device, so they are out while a run is on.
        self.sidebar.read_button.setEnabled(connected and not self._running)
        self.sidebar.write_button.setEnabled(connected and not self._running)
        self.sidebar.start_button.setEnabled(connected and calibrating)
        # The platform is chosen in the GF section and locked while calibrating.
        self.sidebar.platform_id.setEnabled(not calibrating)
        self.workspace.pad_view.set_steppers_enabled(self._running)

    # --- connection --------------------------------------------------------

    def _on_connection_state(self, state: str, message: str) -> None:
        self._show_status(STATE_COLORS.get(state, theme.MUTED_DIM), message)
        if state != CONNECTED and self._running:
            self.sidebar.start_button.setChecked(False)  # drops _running too
        self._apply_controls()

        if state == CONNECTING:
            self.status_action.setText("CANCEL")
            self.status_action.show()
        elif state == CONNECTED:
            self.status_action.hide()
        else:
            self.status_action.setText("RETRY")
            self.status_action.show()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt naming)
        self.connection.shutdown()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    # Connection attempts and failures are logged here, so a run from a terminal
    # shows why the port would not open.
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(WINDOW_TITLE)
    app.setFont(theme.font("body", 10))
    app.setStyleSheet(theme.STYLE_SHEET)

    startup_error = ""
    try:
        config = AppConfig.load()
    except (OSError, ValueError) as exc:
        # A broken config must not stop the app from opening.
        config = AppConfig()
        startup_error = f"config error, using defaults — {exc}"

    window = MainWindow(config, startup_error)
    window.show()
    return app.exec()
