"""Application shell for the Platform Calibration UI.

The calibration widgets are still presentation-only, but the device connection
is live: the window opens the port from config.ini on startup, retrying on a
worker thread, and reports progress in the status bar.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Callable

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

from widgets import theme
from device.settings import AppConfig
from device.connection import (
    CONNECTED,
    CONNECTING,
    ConnectionController,
    FAILED,
)
from device.protocol import (
    CMD_PADS_SAVE_CF,
    GF_MAX,
    GF_MIN,
    ProtocolError,
    get_factory_gf,
    hex_dump,
    is_ack,
    parse_ack,
    parse_response,
    save_cf,
    save_factory_gf,
    start_calibration,
    stop_calibration,
    write_factory_gf,
)
from device.serial_link import SerialLinkError
from widgets.common import label
from widgets.header_bar import HeaderBar, StatusDot
from widgets.pad_card import CAL_MAX, CAL_MIN
from widgets.sidebar import Sidebar
from widgets.workspace import CAL, Workspace

log = logging.getLogger(__name__)

WINDOW_TITLE = "Platform Calibration"
DEFAULT_SIZE = (1280, 800)
MINIMUM_SIZE = (1024, 680)
PAD_GAP = 0.2  # seconds between per-pad command frames
ACK_TIMEOUT = 200  # ms to wait for a stored value to be acknowledged

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
        self._reverting = False  # guards the Start button's own undo
        # Write in the CAL section walks its frames one acknowledgement at a
        # time, so the queue and its timer live here rather than in a loop.
        self._cf_queue: list[tuple[bytes, str]] = []
        self._cf_timer = QTimer(self)
        self._cf_timer.setSingleShot(True)
        self._cf_timer.setInterval(ACK_TIMEOUT)
        self._cf_timer.timeout.connect(self._on_cf_timeout)
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
        # Committing a GF field is a command to the device.
        self.workspace.pad_view.factoryChanged.connect(self._on_factory_gf)
        self.workspace.pad_view.factoryRejected.connect(self._on_factory_rejected)
        self.workspace.pad_view.calibrationLimit.connect(self._on_calibration_limit)
        self.sidebar.read_button.clicked.connect(self._on_read)
        self.sidebar.write_button.clicked.connect(self._on_write)

        self.setCentralWidget(root)
        self._build_status_bar()

        self.connection = ConnectionController(config.serial, config.retry, self)
        self.connection.stateChanged.connect(self._on_connection_state)
        self.connection.frameReceived.connect(self._on_frame)

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

    def _show_status(self, color: str, message: str, detail: str | None = None) -> None:
        self.status_dot.set_color(color)
        self.status_label.setText(message)
        # The driver's full complaint is too long for the bar; keep it reachable.
        self.status_label.setToolTip(
            self.connection.last_error if detail is None else detail
        )

    def _on_status_action(self) -> None:
        if self.connection.state == CONNECTING:
            self.connection.cancel()
        else:
            self.connection.start()

    # --- commands ----------------------------------------------------------

    def _platform_id(self) -> int | None:
        """The sidebar's platform ID as a frame byte, or None if unusable."""
        try:
            value = int(self.sidebar.platform_id.text().strip())
        except ValueError:
            return None
        return value if 0 <= value <= 0xFF else None

    def _on_factory_gf(self, pad: int, channel: int, value: int) -> None:
        """A GF field was committed — store that channel on the device."""
        platform = self._platform_id()
        if platform is None:
            self._undo_factory(pad, channel)
            self._show_status(theme.ACCENT, "set a platform ID first", "")
            return
        try:
            frame = save_factory_gf(platform, pad, channel, value)
            self.connection.send(frame)
        except (ProtocolError, SerialLinkError) as exc:
            self._undo_factory(pad, channel)
            self._show_status(theme.ACCENT, f"gf not sent — {exc}", str(exc))
            return
        self._show_status(
            theme.ONLINE,
            f"pad {pad} ch{channel} gf={value} sent",
            hex_dump(frame),
        )

    def _on_read(self) -> None:
        """Ask the device for its stored factory GFs."""
        self._send_per_pad(get_factory_gf, "read")

    def _on_write(self) -> None:
        """Store what the current section is set up for."""
        if self.workspace.pad_view.view == CAL:
            self._write_calibration_factors()
        else:
            self._send_per_pad(write_factory_gf, "write")

    def _write_calibration_factors(self) -> None:
        """Send every shown calibration factor, one acknowledgement at a time.

        Each channel is stored on its own; once the device has confirmed them
        all, each pad is told to keep them with a zeroed frame.
        """
        if self._cf_queue:
            self._show_status(theme.ACCENT, "write already in progress", "")
            return
        platform = self._platform_id()
        if platform is None:
            self._show_status(theme.ACCENT, "set a platform ID first", "")
            return

        view = self.workspace.pad_view
        pads = range(1, len(view.pads) + 1)
        queue: list[tuple[bytes, str]] = []
        try:
            for pad in pads:
                for channel in view.channel_numbers(pad):
                    factor = view.channel_block(pad, channel).factor
                    queue.append(
                        (
                            save_cf(platform, pad, channel, factor),
                            f"pad {pad} ch{channel} cf={factor}",
                        )
                    )
            for pad in pads:
                queue.append((save_cf(platform, pad, 0, 0), f"pad {pad} save"))
        except ProtocolError as exc:
            self._show_status(theme.ACCENT, f"write failed — {exc}", str(exc))
            return

        self._cf_queue = queue
        self._send_next_cf()

    def _send_next_cf(self) -> None:
        """Put the next frame of the write sequence on the wire."""
        if not self._cf_queue:
            self._show_status(theme.ONLINE, "calibration factors written", "")
            return
        frame, what = self._cf_queue[0]
        try:
            self.connection.send(frame)
        except SerialLinkError as exc:
            self._cf_queue.clear()
            self._show_status(theme.ACCENT, f"write failed — {exc}", str(exc))
            return
        self._show_status(theme.ACCENT_SOFT, f"{what} sent", hex_dump(frame))
        self._cf_timer.start()

    def _on_cf_ack(self, cmd: int) -> None:
        """One frame of the write sequence was acknowledged."""
        if not self._cf_queue or cmd != CMD_PADS_SAVE_CF:
            return
        self._cf_timer.stop()
        self._cf_queue.pop(0)
        self._send_next_cf()

    def _on_cf_timeout(self) -> None:
        """Nothing came back in time, so the rest of the sequence is dropped."""
        _, what = self._cf_queue[0]
        self._cf_queue.clear()
        self._show_status(
            theme.ACCENT, f"no answer to {what} in {ACK_TIMEOUT}ms, write stopped", ""
        )

    def _send_once(self, build: Callable[[int], bytes], action: str) -> bool:
        """Send one frame addressed to the platform rather than to a pad."""
        platform = self._platform_id()
        if platform is None:
            self._show_status(theme.ACCENT, "set a platform ID first", "")
            return False
        try:
            frame = build(platform)
            self.connection.send(frame)
        except (ProtocolError, SerialLinkError) as exc:
            self._show_status(theme.ACCENT, f"{action} failed — {exc}", str(exc))
            return False
        self._show_status(theme.ONLINE, f"{action} sent", hex_dump(frame))
        return True

    def _send_per_pad(self, build: Callable[[int, int], bytes], action: str) -> bool:
        """Send one frame per pad, as the sheet spells out for Read."""
        platform = self._platform_id()
        if platform is None:
            self._show_status(theme.ACCENT, "set a platform ID first", "")
            return False

        pads = len(self.workspace.pad_view.pads)
        frames: list[bytes] = []
        for pad in range(1, pads + 1):
            if pad > 1:
                # The device needs a breather between per-pad frames.
                # ponytail: blocks the GUI for PAD_GAP; move to a QTimer chain
                # if the gap ever grows past a blink.
                time.sleep(PAD_GAP)
            try:
                frame = build(platform, pad)
                self.connection.send(frame)
            except (ProtocolError, SerialLinkError) as exc:
                self._show_status(
                    theme.ACCENT, f"{action} failed on pad {pad} — {exc}", str(exc)
                )
                return False
            frames.append(frame)

        self._show_status(
            theme.ONLINE,
            f"{action} sent for {pads} pad(s)",
            "\n".join(hex_dump(frame) for frame in frames),
        )
        return True

    def _on_frame(self, frame: bytes) -> None:
        """An answer arrived: readings during a run, gain factors otherwise."""
        if is_ack(frame):
            try:
                platform, cmd = parse_ack(frame)
            except ProtocolError as exc:
                log.warning("bad ack %s — %s", hex_dump(frame), exc)
                self._show_status(theme.ACCENT, f"bad ack — {exc}", hex_dump(frame))
                return
            expected = self._platform_id()
            if expected is not None and platform != expected:
                return
            log.info("platform %d ack for cmd %#04x", platform, cmd)
            self._on_cf_ack(cmd)
            return

        readings = self._running  # a run is the only thing that sends readings
        try:
            platform, pad, values = parse_response(frame, signed=readings)
        except ProtocolError as exc:
            log.warning("bad answer %s — %s", hex_dump(frame), exc)
            self._show_status(theme.ACCENT, f"bad answer — {exc}", hex_dump(frame))
            return

        expected = self._platform_id()
        if expected is not None and platform != expected:
            log.info("ignoring answer from platform %d (expected %d)", platform, expected)
            return

        # Value i belongs to ch<i>; the card only shows some of the eight.
        if readings:
            # One frame per sample, so this is far too busy for the status bar.
            log.debug("platform %d pad %d readings %s", platform, pad, values)
            for channel, reading in enumerate(values):
                self.workspace.pad_view.set_reading(pad, channel, reading)
            return

        log.info(
            "platform %d pad %d gf %s | %s",
            platform,
            pad,
            ", ".join(f"ch{ch}={value}" for ch, value in enumerate(values)),
            hex_dump(frame),
        )
        self.workspace.pad_view.set_factors(pad, dict(enumerate(values)))
        self._show_status(
            theme.ONLINE, f"pad {pad} gf read", hex_dump(frame)
        )

    def _undo_factory(self, pad: int, channel: int) -> None:
        """Nothing reached the device, so the field must not count as delivered."""
        editor = self.workspace.pad_view.factory_field(pad, channel)
        if editor is not None:
            editor.rollback()

    def _on_calibration_limit(self, pad: int, channel: int, limit: int) -> None:
        edge = "lowest" if limit == CAL_MIN else "highest"
        self._show_status(
            theme.ACCENT,
            f"pad {pad} ch{channel} is at its {edge} calibration factor "
            f"({CAL_MIN}–{CAL_MAX})",
            "",
        )

    def _on_factory_rejected(self, text: str) -> None:
        what = f"'{text}'" if text else "an empty field"
        self._show_status(
            theme.ACCENT, f"gf must be {GF_MIN}–{GF_MAX}, {what} ignored", ""
        )

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
        # No port, no run: the button is only a latch then, and a dropped
        # connection unlatches it here rather than sending into a closed port.
        if not self._reverting and self.connection.state == CONNECTED:
            action = "start" if running else "stop"
            build = start_calibration if running else stop_calibration
            if not self._send_once(build, action) and running:
                self._reverting = True
                self.sidebar.start_button.setChecked(False)  # nothing went out
                self._reverting = False
                return
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
        self.sidebar.platform_type.setEnabled(not calibrating)
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


if __name__ == "__main__":
    sys.exit(main())
