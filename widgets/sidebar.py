"""Left rail: platform selection, device actions and the summed readout."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .common import (
    SegmentedControl,
    action_button,
    caption,
    field,
    mono,
    readout,
    rule,
)

SIDEBAR_WIDTH = 264
ACTION_HEIGHT = 44


class SidebarPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setStyleSheet(f"QFrame#panel {{ background: {theme.PANEL}; }}")

        column = QVBoxLayout(self)
        column.setContentsMargins(22, 24, 22, 20)
        column.setSpacing(22)

        column.addLayout(self._platform_type())
        column.addLayout(self._platform_id())
        column.addWidget(rule())
        column.addLayout(self._device_actions())
        column.addStretch(1)
        column.addWidget(rule())
        column.addLayout(self._totals())

    def _platform_type(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(9)
        box.addWidget(caption("Platform type"))
        self.platform_type = SegmentedControl("SINGLE", "DOUBLE", active=0)
        box.addWidget(self.platform_type)
        return box

    def _platform_id(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(9)
        box.addWidget(caption("Platform ID"))
        self.platform_id = field(placeholder="—", size=11)
        self.platform_id.setFixedHeight(38)
        # It travels as one byte of every command frame.
        self.platform_id.setValidator(QIntValidator(0, 255, self.platform_id))
        box.addWidget(self.platform_id)
        return box

    def _device_actions(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(10)
        self.read_button = action_button("Read")
        self.write_button = action_button("Write")
        # Start latches: pressing it again stops the run.
        self.start_button = action_button("Start", variant="actionPrimary")
        self.start_button.setCheckable(True)

        self.device_buttons = (self.read_button, self.write_button, self.start_button)
        for btn in self.device_buttons:
            btn.setFixedHeight(ACTION_HEIGHT)
            btn.setEnabled(False)  # until the device is connected
            box.addWidget(btn)
        return box

    def _totals(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(10)
        box.setContentsMargins(0, 8, 0, 0)
        box.addWidget(caption("Total"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, 34)
        grid.setColumnStretch(1, 1)

        self.totals: dict[str, object] = {}
        for row, name in enumerate(("Fx", "Fy", "Fz")):
            grid.addWidget(mono(name, size=10), row, 0, Qt.AlignmentFlag.AlignLeft)
            value = readout("0.0", variant="readoutLight", size=11, height=30)
            grid.addWidget(value, row, 1)
            self.totals[name] = value

        for offset, name in enumerate(("xcop", "ycop")):
            row = 3 + offset
            grid.addWidget(
                mono(name, size=9, color=theme.VALUE_DIM),
                row,
                0,
                Qt.AlignmentFlag.AlignLeft,
            )
            value = readout("0.00", size=10, height=26)
            grid.addWidget(value, row, 1)
            self.totals[name] = value

        box.addLayout(grid)
        return box


class Sidebar(QScrollArea):
    """Fixed-width left rail; scrolls rather than squashing on short windows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.panel = SidebarPanel()
        self.setWidget(self.panel)
        self.setWidgetResizable(True)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            f"QScrollArea {{ background: {theme.PANEL}; "
            f"border-right: 1px solid {theme.BORDER}; }}"
        )

    def __getattr__(self, name: str):
        # Expose the panel's controls (platform_id, read_button, totals, ...)
        # directly on the rail, so callers need not reach through .panel.
        panel = self.__dict__.get("panel")
        if panel is None:
            raise AttributeError(name)
        return getattr(panel, name)
