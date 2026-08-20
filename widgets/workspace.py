"""Right-hand work area: the empty state and the pad calibration view."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import theme
from .common import SegmentedControl, label
from .pad_card import PadRow

CONTENT_MAX_WIDTH = 1000
PAD_COUNT = 1  # single platform; the double layout adds a second pad row

EMPTY = 0
PADS = 1


class Placeholder(QWidget):
    """Shown until a platform type and ID have been chosen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)

        panel = QLabel(
            "select platform type and device id\n"
            "factory gain factors and calibration will appear here"
        )
        panel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel.setFont(theme.font("mono", 10, tracking=0.08))
        panel.setStyleSheet(
            f"border: 1px dashed {theme.BORDER}; border-radius: 8px; "
            f"color: {theme.MUTED_SOFT}; padding: 120px 20px; line-height: 200%;"
        )
        box.addWidget(panel)
        box.addStretch(1)


class PadView(QWidget):
    """Section heading, view toggle and the pad rows themselves."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(16)
        column.addWidget(self._heading())

        # Pad names are only shown when there is more than one pad to tell apart.
        self.pads = [
            PadRow(
                f"Pad {index + 1}",
                show_mark=index == 0,
                show_title=PAD_COUNT > 1,
                show_forces=False,
                cop="pad",
            )
            for index in range(PAD_COUNT)
        ]
        for pad in self.pads:
            column.addWidget(pad)

        column.addStretch(1)

    def _heading(self) -> QWidget:
        # Title and toggle share one cell so the title stays optically centred
        # while the toggle hugs the right edge, as in the design.
        holder = QWidget()
        holder.setMinimumHeight(34)
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)

        self.title = label(
            "CALIBRATION FACTOR SETUP",
            role="display",
            size=15,
            color=theme.ACCENT,
            weight=QFont.Weight.DemiBold,
            tracking=0.2,
            align=Qt.AlignmentFlag.AlignCenter,
        )
        grid.addWidget(self.title, 0, 0)

        self.view_toggle = SegmentedControl(
            "GF",
            "CAL",
            active=1,
            role="mono",
            size=9,
            tracking=0.1,
            padding="8px 16px",
        )
        grid.addWidget(
            self.view_toggle,
            0,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        return holder


class Workspace(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 24, 28, 40)

        centred = QWidget()
        centred.setMaximumWidth(CONTENT_MAX_WIDTH)
        inner = QVBoxLayout(centred)
        inner.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.stack.addWidget(Placeholder())  # index EMPTY
        self.pad_view = PadView()
        self.stack.addWidget(self.pad_view)  # index PADS
        self.stack.setCurrentIndex(PADS)
        inner.addWidget(self.stack)

        outer.addWidget(centred, 0, Qt.AlignmentFlag.AlignHCenter)
        self.setWidget(page)
