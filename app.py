"""Application shell for the Platform Calibration UI.

The window owns the device conversation: it opens the port from config.ini on
a worker thread, turns button presses into the command frames of ТЗ section 2,
and renders what comes back — factors, and the reading stream a calibration
run produces.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
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
    CMD_PADS_SAVE_FACTORY_GF,
    GF_MAX,
    GF_MIN,
    ProtocolError,
    get_cf,
    get_factory_gf,
    hex_dump,
    is_ack,
    is_reading,
    parse_ack,
    parse_factors,
    parse_readings,
    save_cf,
    save_factory_gf,
    start_calibration,
    stop_calibration,
    write_factory_gf,
)
from device.serial_link import SerialLinkError
import calc
from widgets.common import label
from widgets.header_bar import HeaderBar, StatusDot
from widgets.pad_card import CAL_MAX, CAL_MIN
from widgets.sidebar import Sidebar
from widgets.workspace import CAL, Workspace

log = logging.getLogger(__name__)

WINDOW_TITLE = "Platform Calibration"
DEFAULT_SIZE = (1280, 800)
MINIMUM_SIZE = (1024, 680)
PAD_GAP = 200  # ms between per-pad command frames (ТЗ 4.2, 4.3, 5.2)
ACK_TIMEOUT = 500  # ms to wait for an acknowledgement before giving up
RENDER_INTERVAL = 50  # ms between repaints while readings stream in

STATE_COLORS = {
    CONNECTED: theme.ONLINE,
    CONNECTING: theme.ACCENT_SOFT,
    FAILED: theme.ACCENT,
}


@dataclass
class _Sequence:
    """A multi-frame exchange, driven one frame at a time.

    ``await_cmd`` set means the next frame waits for that command's
    acknowledgement; ``gap_ms`` is the pause the ТЗ requires between per-pad
    frames; ``freeze`` locks the GUI until the last answer, as sections 4.3
    and 5.1 demand.
    """

    steps: list[tuple[bytes, str]]
    done: str
    gap_ms: int = 0
    await_cmd: int | None = None
    freeze: bool = False
    index: int = 0

    @property
    def current(self) -> tuple[bytes, str]:
        return self.steps[self.index]


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, startup_error: str = "") -> None:
        super().__init__()
        self.config = config
        self._running = False  # latched by the Start button
        self._reverting = False  # guards the Start button's own undo
        self._frozen = False  # ТЗ 4.3 / 5.1: no GUI while a write is in flight
        # Multi-frame exchanges walk one frame at a time; the token lets a
        # pending gap tell whether the sequence it belongs to is still current.
        self._sequence: _Sequence | None = None
        self._sequence_token = 0
        # A 16-byte answer fits both GET_FACTORY_GF and GET_CF, so what a read
        # means is decided by the request still outstanding.
        self._pending_read: str | None = None
        self._reads_left = 0
        self._ack_timer = QTimer(self)
        self._ack_timer.setSingleShot(True)
        self._ack_timer.setInterval(ACK_TIMEOUT)
        self._ack_timer.timeout.connect(self._on_ack_timeout)
        # Readings arrive far faster than a screen refresh, so frames are
        # coalesced and the latest one is painted on a fixed beat.
        self._latest: dict[int, list[int]] = {}
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(RENDER_INTERVAL)
        self._render_timer.timeout.connect(self._render_readings)
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
        self.sidebar.platform_type.changed.connect(self._on_platform_type)
        self.workspace.pad_view.viewChanged.connect(self._on_view_changed)
        self.sidebar.start_button.toggled.connect(self._on_start_toggled)
        # Committing a GF field is a command to the device.
        self.workspace.pad_view.factoryChanged.connect(self._on_factory_gf)
        self.workspace.pad_view.factoryRejected.connect(self._on_factory_rejected)
        self.workspace.pad_view.calibrationLimit.connect(self._on_calibration_limit)
        self.sidebar.read_button.clicked.connect(self._on_read)
        self.sidebar.write_button.clicked.connect(self._on_write)
        # ТЗ 3: nothing at all is possible until a platform ID is entered.
        self.sidebar.platform_id.textChanged.connect(lambda _: self._apply_controls())

        self.setCentralWidget(root)
        self._build_status_bar()
        self.sidebar.clear_totals()  # no run yet, so no centre of pressure

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

    def _pads(self) -> list[int]:
        """Pad addresses of the selected platform type: [1] or [1, 2]."""
        return list(range(1, len(self.workspace.pad_view.pads) + 1))

    def _on_read(self) -> None:
        """READ: factory GFs in the GF section, calibration factors in CAL."""
        platform = self._platform_id()
        if platform is None:
            return
        pads = self._pads()
        calibrating = self.workspace.pad_view.view == CAL
        # ТЗ 4.2 / 5.2: one frame per pad, PAD_GAP apart, and no acknowledgement
        # for either — the answers are the 16-byte factor frames themselves.
        build = get_cf if calibrating else get_factory_gf
        kind = "cf" if calibrating else "gf"
        steps = self._steps(build, platform, pads, f"read {kind} pad")
        if steps is None:
            return
        self._pending_read = kind
        self._reads_left = len(pads)
        self._run(
            _Sequence(steps, f"{kind} read sent for {len(pads)} pad(s)", gap_ms=PAD_GAP)
        )

    def _on_write(self) -> None:
        """WRITE: commit factory GFs, or store every calibration factor."""
        if self.workspace.pad_view.view == CAL:
            self._write_calibration_factors()
        else:
            self._write_factory_gf()

    def _write_factory_gf(self) -> None:
        """ТЗ 4.3: one zeroed SAVE_FACTORY_GF per pad, GUI dead until the last ack."""
        platform = self._platform_id()
        if platform is None:
            return
        pads = self._pads()
        steps = self._steps(write_factory_gf, platform, pads, "write gf pad")
        if steps is None:
            return
        self._run(
            _Sequence(
                steps,
                "factory gf written",
                gap_ms=PAD_GAP,
                await_cmd=CMD_PADS_SAVE_FACTORY_GF,
                freeze=True,
            )
        )

    def _write_calibration_factors(self) -> None:
        """ТЗ 5.1: every channel of every pad, then a zeroed frame per pad.

        Channel-major, which is what "pad ID = 1 и 2 по-очереди" says inside a
        per-channel loop. Each frame waits for its own acknowledgement, and the
        GUI stays dead until the last one lands.
        """
        platform = self._platform_id()
        if platform is None:
            return

        view = self.workspace.pad_view
        pads = self._pads()
        steps: list[tuple[bytes, str]] = []
        try:
            for channel in view.channel_numbers(1):
                for pad in pads:
                    block = view.channel_block(pad, channel)
                    if block is None:
                        continue
                    factor = block.factor
                    steps.append(
                        (
                            save_cf(platform, pad, channel, factor),
                            f"pad {pad} ch{channel} cf={factor}",
                        )
                    )
            # ТЗ 5.1 writes one closing frame; it has to be one per pad, or the
            # second pad is never told to keep what it was just sent.
            for pad in pads:
                steps.append((save_cf(platform, pad, 0, 0), f"pad {pad} save"))
        except ProtocolError as exc:
            self._show_status(theme.ACCENT, f"write failed — {exc}", str(exc))
            return

        self._run(
            _Sequence(
                steps,
                "calibration factors written",
                await_cmd=CMD_PADS_SAVE_CF,
                freeze=True,
            )
        )

    def _steps(
        self,
        build: Callable[[int, int], bytes],
        platform: int,
        pads: list[int],
        what: str,
    ) -> list[tuple[bytes, str]] | None:
        """One frame per pad, or None if the protocol refused to build one."""
        try:
            return [(build(platform, pad), f"{what} {pad}") for pad in pads]
        except ProtocolError as exc:
            self._show_status(theme.ACCENT, f"{what} failed — {exc}", str(exc))
            return None

    # --- sequence engine ----------------------------------------------------

    def _run(self, sequence: _Sequence) -> None:
        """Begin a multi-frame exchange, unless one is already under way."""
        if self._sequence is not None:
            self._show_status(theme.ACCENT, "device is busy", "")
            return
        self._sequence = sequence
        self._sequence_token += 1
        if sequence.freeze:
            self._frozen = True
            self._apply_controls()
        self._send_step()

    def _send_step(self) -> None:
        """Put the sequence's current frame on the wire."""
        sequence = self._sequence
        if sequence is None:
            return
        frame, what = sequence.current
        try:
            self.connection.send(frame)
        except SerialLinkError as exc:
            self._end(theme.ACCENT, f"{what} failed — {exc}", str(exc))
            return
        self._show_status(theme.ACCENT_SOFT, f"{what} sent", hex_dump(frame))
        if sequence.await_cmd is None:
            self._advance()
        else:
            self._ack_timer.start()

    def _advance(self) -> None:
        """Move past the frame just dealt with, honouring the inter-pad gap."""
        sequence = self._sequence
        if sequence is None:
            return
        sequence.index += 1
        if sequence.index >= len(sequence.steps):
            self._end(theme.ONLINE, sequence.done)
            return
        if not sequence.gap_ms:
            self._send_step()
            return
        token = self._sequence_token
        QTimer.singleShot(
            sequence.gap_ms,
            lambda: self._send_step() if token == self._sequence_token else None,
        )

    def _end(self, color: str, message: str, detail: str = "") -> None:
        """Finish the sequence, successfully or not, and give the GUI back."""
        self._ack_timer.stop()
        self._sequence = None
        self._sequence_token += 1
        self._frozen = False
        self._apply_controls()
        self._show_status(color, message, detail)

    def _on_ack_timeout(self) -> None:
        """Nothing came back in time, so the rest of the sequence is dropped."""
        sequence = self._sequence
        if sequence is None:
            return
        _, what = sequence.current
        self._end(theme.ACCENT, f"no answer to {what} in {ACK_TIMEOUT}ms, stopped")

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

    def _on_frame(self, frame: bytes) -> None:
        """Route an answer by its length, as ТЗ 2.1.2 lays them out."""
        if is_ack(frame):
            self._on_ack_frame(frame)
        elif is_reading(frame):
            self._on_reading_frame(frame)
        else:
            self._on_factor_frame(frame)

    def _on_ack_frame(self, frame: bytes) -> None:
        try:
            platform, cmd = parse_ack(frame)
        except ProtocolError as exc:
            log.warning("rx %s — bad ack: %s", hex_dump(frame), exc)
            self._show_status(theme.ACCENT, f"bad ack — {exc}", hex_dump(frame))
            return
        if not self._ours(platform, frame):
            return
        log.info("rx %s | ack platform=%d cmd=%#04x", hex_dump(frame), platform, cmd)

        sequence = self._sequence
        if sequence is not None and cmd == sequence.await_cmd:
            self._ack_timer.stop()
            self._advance()

    def _on_factor_frame(self, frame: bytes) -> None:
        """A 16-byte answer: factory GFs or calibration factors, per the request."""
        try:
            platform, pad, values = parse_factors(frame)
        except ProtocolError as exc:
            log.warning("rx %s — bad answer: %s", hex_dump(frame), exc)
            self._show_status(theme.ACCENT, f"bad answer — {exc}", hex_dump(frame))
            return
        if not self._ours(platform, frame):
            return

        kind = self._pending_read
        log.info(
            "rx %s | %s platform=%d pad=%d %s",
            hex_dump(frame),
            kind or "factors",
            platform,
            pad,
            ", ".join(f"ch{ch}={value}" for ch, value in enumerate(values)),
        )
        if kind is None:
            return  # nothing asked for it; the ТЗ has no other source for one

        by_channel = dict(enumerate(values))
        if kind == "cf":
            self.workspace.pad_view.set_calibration_factors(pad, by_channel)
        else:
            self.workspace.pad_view.set_factory_gf(pad, by_channel)

        self._reads_left = max(0, self._reads_left - 1)
        if not self._reads_left:
            self._pending_read = None
        self._show_status(theme.ONLINE, f"pad {pad} {kind} read", hex_dump(frame))

    def _on_reading_frame(self, frame: bytes) -> None:
        """A 24-byte answer: one sample of a pad's eight channels."""
        try:
            platform, pad, values = parse_readings(frame)
        except ProtocolError as exc:
            log.warning("rx %s — bad readings: %s", hex_dump(frame), exc)
            return
        if not self._ours(platform, frame):
            return
        if not self._running:
            # The platform is still streaming from an earlier session; one stop
            # is cheaper than dropping frames for as long as the app is open.
            log.info("readings with no run in progress — sending stop")
            self._send_once(stop_calibration, "stop")
            return
        log.debug("rx %s | readings pad=%d %s", hex_dump(frame), pad, values)
        self._latest[pad] = values

    def _render_readings(self) -> None:
        """Paint the latest sample of every pad, and the section 6 sums with it."""
        if not self._latest:
            return
        view = self.workspace.pad_view
        for pad, raw in self._latest.items():
            scaled = view.set_readings(pad, raw)
            if len(view.pads) > 1:
                view.set_forces(pad, calc.pad_forces(scaled))

        if len(view.pads) > 1:
            totals = calc.double_totals(view.readings(1), view.readings(2))
        else:
            totals = calc.single_totals(view.readings(1))
        self.sidebar.set_totals(totals)
        view.set_cop(totals.xcop, totals.ycop)

    def _ours(self, platform: int, frame: bytes) -> bool:
        """False for an answer from a platform the operator is not addressing."""
        expected = self._platform_id()
        if expected is None or platform == expected:
            return True
        log.info("rx %s | ignored, platform %d", hex_dump(frame), platform)
        return False

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

    def _on_platform_type(self, index: int) -> None:
        self.workspace.set_pad_count(2 if index else 1)
        self._latest.clear()
        self.sidebar.clear_totals()
        self._apply_controls()

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

        if running:
            self._render_timer.start()
        else:
            self._render_timer.stop()
            self._latest.clear()
            self.workspace.pad_view.clear_readings()
            self.sidebar.clear_totals()
        self._apply_controls()

    def _apply_controls(self) -> None:
        """Enable the controls that make sense for the current state."""
        connected = self.connection.state == CONNECTED
        calibrating = self.workspace.pad_view.view == CAL
        # ТЗ 3б: the pads and their defaults belong on screen as soon as the
        # operator says how many there are — that is not an action.
        chosen = self.sidebar.platform_type.chosen
        self.workspace.show_pads(chosen)
        # ТЗ 3: but nothing can actually be done until the platform is
        # addressed, and ТЗ 4.3 / 5.1 take the GUI away during a write.
        ready = chosen and self._platform_id() is not None
        live = ready and not self._frozen

        # Read/Write talk to the device, so they are out while a run is on.
        self.sidebar.read_button.setEnabled(live and connected and not self._running)
        self.sidebar.write_button.setEnabled(live and connected and not self._running)
        self.sidebar.start_button.setEnabled(live and connected and calibrating)
        # The platform is chosen in the GF section and locked while calibrating.
        self.sidebar.platform_id.setEnabled(not calibrating and not self._frozen)
        self.sidebar.platform_type.setEnabled(not calibrating and not self._frozen)
        self.workspace.pad_view.setEnabled(live)
        self.workspace.pad_view.set_steppers_enabled(live and calibrating)

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
