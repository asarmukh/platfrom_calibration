"""Serial connection to the calibration device, with retry on failure.

Deliberately free of Qt imports so it can be unit-tested and driven from a
worker thread.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - depends on the environment
    serial = None
    list_ports = None

from settings import RetrySettings, SerialSettings

log = logging.getLogger(__name__)

# Called as (attempt, attempts, error) after every failed attempt; `error` is
# the exception that caused it.
AttemptHook = Callable[[int, int, Exception], None]


class SerialLinkError(RuntimeError):
    """Raised when the device could not be reached within the retry budget."""


def available_ports() -> list[str]:
    """Device names of the serial ports currently present, e.g. ``["COM5"]``."""
    if list_ports is None:
        return []
    return [port.device for port in list_ports.comports()]


class SerialLink:
    """Owns one pyserial handle and the policy for (re)opening it."""

    def __init__(
        self,
        settings: SerialSettings,
        retry: RetrySettings | None = None,
    ) -> None:
        self.settings = settings
        self.retry = retry or RetrySettings()
        self._port: "serial.Serial | None" = None
        # connect() runs on a worker thread while the GUI sends commands.
        self._write_lock = threading.Lock()

    # --- state -------------------------------------------------------------

    @property
    def port(self) -> "serial.Serial | None":
        """The open pyserial handle, or None while disconnected."""
        return self._port

    @property
    def is_open(self) -> bool:
        return self._port is not None and self._port.is_open

    # --- connection --------------------------------------------------------

    def connect(
        self,
        *,
        cancel: threading.Event | None = None,
        on_attempt: AttemptHook | None = None,
    ) -> "serial.Serial":
        """Open the port, retrying with a backing-off delay between attempts.

        Passing a `cancel` event makes both the wait and the retry loop
        interruptible, so a UI can abort a connection that is still backing off.
        Returns the open handle; raises SerialLinkError if every attempt failed.
        """
        if serial is None:
            raise SerialLinkError(
                "pyserial is not installed — run: pip install -r requirements.txt"
            )
        if self.is_open:
            return self._port

        attempts = max(1, int(self.retry.attempts))
        delay = max(0.0, float(self.retry.delay))
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            if cancel is not None and cancel.is_set():
                raise SerialLinkError("connection cancelled")

            try:
                self._port = self._open()
            except (OSError, ValueError) as exc:
                # pyserial raises SerialException (an OSError) for a missing or
                # busy port, and ValueError for bad parameters.
                last_error = exc
                log.warning(
                    "connect to %s failed (attempt %d/%d): %s",
                    self.settings.port,
                    attempt,
                    attempts,
                    exc,
                )
                if on_attempt is not None:
                    on_attempt(attempt, attempts, exc)
            else:
                log.info(
                    "connected to %s at %d baud (attempt %d/%d)",
                    self.settings.port,
                    self.settings.baudrate,
                    attempt,
                    attempts,
                )
                return self._port

            if attempt < attempts:
                if self._wait(delay, cancel):
                    raise SerialLinkError("connection cancelled")
                delay = min(
                    float(self.retry.max_delay), delay * max(1.0, float(self.retry.backoff))
                )

        raise SerialLinkError(
            f"could not open {self.settings.port} after {attempts} attempt(s): "
            f"{last_error}"
        ) from last_error

    def reconnect(self, **kwargs) -> "serial.Serial":
        """Drop any existing handle and connect again."""
        self.close()
        return self.connect(**kwargs)

    # --- traffic -----------------------------------------------------------

    def write(self, data: bytes) -> int:
        """Send a command frame. Raises SerialLinkError if the port is gone."""
        if not self.is_open:
            raise SerialLinkError(f"{self.settings.port} is not open")
        try:
            with self._write_lock:
                written = self._port.write(data)
                self._port.flush()
        except (OSError, ValueError) as exc:
            raise SerialLinkError(f"write to {self.settings.port} failed: {exc}") from exc
        log.debug("wrote %d byte(s) to %s", written, self.settings.port)
        return written or 0

    def read_available(self) -> bytes:
        """Whatever the device has sent, waiting up to the port's read timeout."""
        if not self.is_open:
            raise SerialLinkError(f"{self.settings.port} is not open")
        try:
            chunk = self._port.read(1)  # blocks until data or timeout
            if chunk and self._port.in_waiting:
                chunk += self._port.read(self._port.in_waiting)
        except (OSError, ValueError) as exc:
            raise SerialLinkError(f"read from {self.settings.port} failed: {exc}") from exc
        return chunk

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            except Exception:  # pragma: no cover - closing must never raise
                log.debug("ignoring error while closing %s", self.settings.port, exc_info=True)
            finally:
                self._port = None

    # --- internals ---------------------------------------------------------

    def _open(self) -> "serial.Serial":
        s = self.settings
        return serial.Serial(
            port=s.port,
            baudrate=s.baudrate,
            bytesize=s.bytesize,
            parity=s.parity,
            stopbits=s.stopbits,
            timeout=s.timeout,
            write_timeout=s.write_timeout,
        )

    @staticmethod
    def _wait(delay: float, cancel: threading.Event | None) -> bool:
        """Sleep between attempts. Returns True if cancelled during the wait."""
        if cancel is None:
            if delay > 0:
                threading.Event().wait(delay)
            return False
        return cancel.wait(delay)

    # --- context manager ---------------------------------------------------

    def __enter__(self) -> "SerialLink":
        self.connect()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
