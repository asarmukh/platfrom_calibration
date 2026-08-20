"""The pad card: six load-cell channels laid out the way they sit on the plate."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

import theme
from .common import field, label, mono, readout, stepper_button
from .cop_plot import CopPlot

CORNER_MARK = 20  # orientation triangle in the card's top-left corner
SIDE_COLUMN = 108  # forces column and cop column width
FIELD_WIDTH = 96
FIELD_MIN_WIDTH = 62  # keeps the value readable when the card is squeezed


class ChannelBlock(QWidget):
    """One channel: name, calibration stepper row, factory GF readout."""

    def __init__(
        self,
        name: str,
        *,
        show_calibration: bool = True,
        show_factory: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(mono(name, size=10), 0, Qt.AlignmentFlag.AlignHCenter)

        if show_calibration:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            self.decrement = stepper_button("–")
            self.value = field("0.0", size=10, max_width=FIELD_WIDTH)
            self.value.setMinimumWidth(FIELD_MIN_WIDTH)
            self.value.setFixedHeight(24)
            self.increment = stepper_button("+")
            row.addWidget(self.decrement)
            row.addWidget(self.value, 1)
            row.addWidget(self.increment)
            column.addLayout(row)

        if show_factory:
            self.factory = readout("10", variant="readoutSoft", size=9, height=20)
            self.factory.setMaximumWidth(FIELD_WIDTH)
            column.addWidget(self.factory, 0, Qt.AlignmentFlag.AlignHCenter)


class PadCard(QWidget):
    """Framed channel map for a single pad."""

    def __init__(
        self,
        title: str,
        *,
        show_mark: bool = True,
        show_title: bool = True,
        show_calibration: bool = True,
        show_factory: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._show_mark = show_mark
        self.setMinimumHeight(230)
        self.setMinimumWidth(240)
        self.setMaximumWidth(520)

        grid = QGridLayout(self)
        grid.setContentsMargins(20, 18, 20, 18)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 100)
        grid.setColumnStretch(1, 105)
        grid.setColumnStretch(2, 100)
        grid.setRowStretch(1, 1)

        def block(name: str) -> ChannelBlock:
            return ChannelBlock(
                name,
                show_calibration=show_calibration,
                show_factory=show_factory,
            )

        self.channels: dict[str, ChannelBlock] = {}
        placement = {
            "ch2": (0, 0),
            "ch1": (0, 2),
            "ch4": (2, 0),
            "ch5": (2, 2),
        }
        for name, (row, column) in placement.items():
            widget = block(name)
            self.channels[name] = widget
            grid.addWidget(widget, row, column, Qt.AlignmentFlag.AlignTop)

        centre = QVBoxLayout()
        centre.setContentsMargins(0, 0, 0, 0)
        centre.setSpacing(8)
        for name in ("ch0", "ch6"):
            widget = block(name)
            self.channels[name] = widget
            centre.addWidget(widget)
        grid.addLayout(centre, 1, 1, Qt.AlignmentFlag.AlignVCenter)

        # With a single pad there is nothing to tell apart, so the name is only
        # worth the space in the double-platform layout.
        if show_title:
            grid.addWidget(
                label(
                    title.upper(),
                    role="display",
                    size=14,
                    color=theme.ACCENT,
                    weight=QFont.Weight.DemiBold,
                    tracking=0.2,
                    align=Qt.AlignmentFlag.AlignCenter,
                ),
                2,
                1,
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        frame = QPainterPath()
        frame.addRoundedRect(rect, 8, 8)
        painter.fillPath(frame, QColor(theme.PANEL))

        if self._show_mark:
            painter.save()
            painter.setClipPath(frame)
            mark = QPainterPath()
            mark.moveTo(rect.left(), rect.top())
            mark.lineTo(rect.left() + CORNER_MARK, rect.top())
            mark.lineTo(rect.left(), rect.top() + CORNER_MARK)
            mark.closeSubpath()
            painter.fillPath(mark, QColor(theme.ACCENT))
            painter.restore()

        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(frame)


class PadRow(QWidget):
    """A pad card flanked by its per-pad forces and its cop plot."""

    def __init__(
        self,
        title: str,
        *,
        show_mark: bool = True,
        show_title: bool = True,
        show_forces: bool = False,
        show_calibration: bool = True,
        show_factory: bool = True,
        cop: str | None = "pad",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        row.addWidget(self._forces_column(show_forces))
        self.card = PadCard(
            title,
            show_mark=show_mark,
            show_title=show_title,
            show_calibration=show_calibration,
            show_factory=show_factory,
        )
        row.addWidget(self.card, 1)
        row.addWidget(self._cop_column(cop))

    def _forces_column(self, visible: bool) -> QWidget:
        holder = QWidget()
        holder.setFixedWidth(SIDE_COLUMN)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 10, 0, 0)
        column.setSpacing(12)

        self.forces: dict[str, object] = {}
        for name in ("Fx", "Fy", "Fz"):
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.addWidget(mono(name, size=10), 0, Qt.AlignmentFlag.AlignHCenter)
            value = readout("0.0", size=10)
            cell.addWidget(value)
            self.forces[name] = value
            column.addLayout(cell)
        column.addStretch(1)

        holder.setVisible(visible)
        return holder

    def _cop_column(self, mode: str | None) -> QWidget:
        holder = QWidget()
        holder.setFixedWidth(SIDE_COLUMN)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 10, 0, 0)
        column.setSpacing(5)

        if mode is None:
            holder.setVisible(False)
            return holder

        total = mode == "total"
        column.addWidget(
            label(
                "total cop" if total else "cop",
                role="mono",
                size=8,
                color=theme.MUTED,
                tracking=0.08,
                align=Qt.AlignmentFlag.AlignCenter,
            )
        )
        self.cop = CopPlot(
            height=141 if total else 68,
            extra_gridlines=total,
        )
        column.addWidget(self.cop)
        column.addStretch(1)
        return holder
