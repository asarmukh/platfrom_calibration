"""Qt wrapper around SerialLink: connects on a worker thread and reports state.

Connecting can block for as long as the retry policy allows, so it must not run
on the GUI thread. Everything Qt-specific lives here; serial_link.py stays
plain Python.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal

from settings import RetrySettings, SerialSettings
from .serial_link import SerialLink, SerialLinkError, available_ports

# connection states
DISCONNECTED = "disconnected"
CONNECTING = "connecting"
CONNECTED = "connected"
FAILED = "failed"


class _ConnectWorker(QObject):
    """Runs SerialLink.connect() off the GUI thread."""

    attempted = Signal(int, int, str)  # attempt, total, error text
    finished = Signal(bool, str, str)  # success, short message, full detail

    def __init__(self, link: SerialLink, cancel: threading.Event) -> None:
        super().__init__()
        self._link = link
        self._cancel = cancel

    def run(self) -> None:
        settings = self._link.settings
        try:
            self._link.connect(
                cancel=self._cancel,
                on_attempt=lambda attempt, total, error: self.attempted.emit(
                    attempt, total, str(error)
                ),
            )
        except SerialLinkError as exc:
            # Keep the bar readable; the driver's full complaint goes to the
            # tooltip and the log.
            ports = ", ".join(available_ports()) or "none"
            self.finished.emit(
                False,
                f"could not open {settings.port} — ports available: {ports}",
                str(exc),
            )
        else:
            self.finished.emit(
                True, f"connected to {settings.port} at {settings.baudrate} baud", ""
            )


class ConnectionController(QObject):
    """Owns the link and the thread it is opened on.

    Emits `stateChanged(state, message)` for every transition, so the window can
    just render whatever it is told.
    """

    stateChanged = Signal(str, str)

    def __init__(
        self,
        settings: SerialSettings,
        retry: RetrySettings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.link = SerialLink(settings, retry)
        self.state = DISCONNECTED
        self.last_error = ""  # full driver message behind a FAILED state
        self._cancel = threading.Event()
        self._thread: QThread | None = None
        self._worker: _ConnectWorker | None = None

    @property
    def is_connected(self) -> bool:
        return self.link.is_open

    def start(self) -> None:
        """Begin connecting. Ignored if a connection or attempt already exists."""
        if self.state == CONNECTING or self.link.is_open:
            return

        self._cancel.clear()
        self._set_state(CONNECTING, f"connecting to {self.link.settings.port}…")

        self._thread = QThread(self)
        self._worker = _ConnectWorker(self.link, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.attempted.connect(self._on_attempt)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def cancel(self) -> None:
        """Ask an in-flight attempt to stop; takes effect between retries."""
        self._cancel.set()

    def shutdown(self) -> None:
        """Stop retrying, wait for the thread and close the port."""
        self.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread = None
        self._worker = None
        self.link.close()
        self._set_state(DISCONNECTED, "disconnected")

    # --- worker callbacks (delivered on the GUI thread) --------------------

    def _on_attempt(self, attempt: int, total: int, error: str) -> None:
        self.last_error = error
        suffix = ", retrying…" if attempt < total else ""
        self._set_state(CONNECTING, f"attempt {attempt}/{total} failed{suffix}")

    def _on_finished(self, ok: bool, message: str, detail: str) -> None:
        self.last_error = detail
        self._set_state(CONNECTED if ok else FAILED, message)

    def _set_state(self, state: str, message: str) -> None:
        self.state = state
        self.stateChanged.emit(state, message)
