"""A MainWindow wired to a fake device, so the command logic can be driven."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Signal

import app as app_module
from device import protocol as p
from device.connection import CONNECTED
from device.settings import AppConfig

# Segment indexes of the platform-type control.
SINGLE = 0
DOUBLE = 1


class FakeConnection(QObject):
    """Stands in for ConnectionController: records frames, injects answers."""

    stateChanged = Signal(str, str)
    frameReceived = Signal(bytes)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        self.state = CONNECTED
        self.last_error = ""
        self.sent: list[bytes] = []

    # -- the interface MainWindow uses
    def send(self, frame: bytes) -> None:
        self.sent.append(frame)

    def start(self) -> None:
        self.stateChanged.emit(CONNECTED, "connected")

    def cancel(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    # -- what a test drives it with
    def receive(self, frame: bytes) -> None:
        self.frameReceived.emit(frame)

    def ack(self, platform: int, cmd: int) -> None:
        self.receive(wrap(bytes((platform, cmd, p.ACK))))

    def factors(self, platform: int, pad: int, values: list[int]) -> None:
        self.receive(wrap(bytes((platform, pad)) + bytes(values)))

    def readings(self, platform: int, pad: int, values: list[int]) -> None:
        body = bytes((platform, pad)) + b"".join(
            v.to_bytes(2, "little", signed=True) for v in values
        )
        self.receive(wrap(body))

    @property
    def commands(self) -> list[tuple[int, int, int, int, int]]:
        """Every frame sent, as (platform, pad, cmd, extra1, extra2)."""
        return [tuple(frame[2:7]) for frame in self.sent]


def wrap(body: bytes) -> bytes:
    """Wrap an answer body in its header, CRC and terminator."""
    crc = p.crc16(body)
    return p.RESPONSE_HEADER + body + bytes((crc & 0xFF, crc >> 8)) + p.EOT


@pytest.fixture(autouse=True)
def instant_gap(monkeypatch):
    """Collapse the 200 ms inter-pad pause; one test puts it back to check it."""
    monkeypatch.setattr(app_module, "PAD_GAP", 0)


@pytest.fixture
def window(qtbot, monkeypatch):
    """A MainWindow talking to a FakeConnection instead of a serial port."""
    monkeypatch.setattr(app_module, "ConnectionController", FakeConnection)
    win = app_module.MainWindow(AppConfig())
    qtbot.addWidget(win)
    win.connection.stateChanged.emit(CONNECTED, "connected")
    return win


@pytest.fixture
def device(window):
    return window.connection


@pytest.fixture
def identified(window):
    """Platform type and ID chosen — ТЗ 3's precondition for doing anything."""
    window.sidebar.platform_type.set_active(SINGLE)
    window.sidebar.platform_id.setText("1")
    return window
