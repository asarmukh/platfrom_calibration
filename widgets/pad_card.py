"""The pad card: six load-cell channels laid out the way they sit on the plate."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from . import theme
from calc import DOUBLE_PLATE, DOUBLE_SENSORS, SINGLE_PLATE, SINGLE_SENSORS
from device.protocol import GF_MAX, GF_MIN
from .common import NumericField, field, label, mono, readout, stepper_button
from .cop_plot import CopPlot

GF_DEFAULT = 10  # what an untouched channel shows before a read
CAL_MIN = 10  # the steppers keep the calibration factor inside this range
CAL_MAX = 200
CAL_DEFAULT = CAL_MIN

CORNER_MARK = 20  # orientation triangle in the card's top-left corner
SIDE_COLUMN = 108  # forces column width
COP_COLUMN = 180  # wide enough for the load cells to carry a readable label

FIELD_WIDTH = 96
FIELD_MIN_WIDTH = 62  # keeps the value readable when the card is squeezed
FIELD_HEIGHT = 24
STEPPER_SIZE = 22  # matches common.stepper_button
ROW_SPACING = 6  # gap between a stepper and its field
BLOCK_HEIGHT = 67  # label + field row + factory field; keeps GF and CAL cards
                   # the same size even though GF has one row fewer


class ChannelBlock(QWidget):
    """One channel: name, and either its calibration row or its factory GF."""

    # A stepper moved the calibration factor; carries its new value.
    factorChanged = Signal(int)
    # A stepper was pressed at the end of the range; carries the limit reached.
    limitReached = Signal(int)

    def __init__(
        self,
        name: str,
        *,
        show_calibration: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumHeight(BLOCK_HEIGHT)
        # Only the CAL layout has somewhere to put a reading.
        self.value: QLineEdit | None = None

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(mono(name, size=10), 0, Qt.AlignmentFlag.AlignHCenter)

        if show_calibration:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(ROW_SPACING)
            self.decrement = stepper_button("–")
            self.value = field("0.0", size=10, max_width=FIELD_WIDTH)
            self.value.setMinimumWidth(FIELD_MIN_WIDTH)
            self.value.setFixedHeight(FIELD_HEIGHT)
            self.increment = stepper_button("+")
            row.addWidget(self.decrement)
            row.addWidget(self.value, 1)
            row.addWidget(self.increment)
            column.addLayout(row)

            # The factor the steppers are working on, under its own channel.
            self.calibration = readout(
                str(CAL_DEFAULT), variant="readoutSoft", size=9, height=20
            )
            self.calibration.setMaximumWidth(FIELD_WIDTH)
            column.addWidget(self.calibration, 0, Qt.AlignmentFlag.AlignHCenter)
            self.decrement.clicked.connect(lambda: self.step(-1))
            self.increment.clicked.connect(lambda: self.step(1))
        else:
            # In the GF view the factory gain factor is the field being set up,
            # so it is editable and takes the calibration input's footprint.
            # Committing it is what sends CMD_PADS_SAVE_FACTORY_GF, so it
            # accepts only values the protocol allows.
            self.factory = NumericField(
                GF_DEFAULT,
                minimum=GF_MIN,
                maximum=GF_MAX,
                size=10,
                max_width=FIELD_WIDTH,
            )
            self.factory.setFixedHeight(FIELD_HEIGHT)
            self.factory.setMaximumWidth(FIELD_WIDTH)
            # Reserve the stepper columns as well, so a GF card is as wide as a
            # CAL one instead of shrinking to the bare field.
            self.factory.setMinimumWidth(FIELD_MIN_WIDTH)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(ROW_SPACING)
            # The layout adds no spacing next to a spacer item, so the gap a
            # stepper would leave has to be part of the spacer itself.
            row.addSpacing(STEPPER_SIZE + ROW_SPACING)
            row.addWidget(self.factory, 1)
            row.addSpacing(STEPPER_SIZE + ROW_SPACING)
            column.addLayout(row)

        column.addStretch(1)

    def step(self, delta: int) -> None:
        """Move the calibration factor one notch, staying inside its range."""
        value = min(CAL_MAX, max(CAL_MIN, self.factor + delta))
        if value == self.factor:
            self.limitReached.emit(value)
            return
        self.set_factor(value)

    def set_factor(self, value: int) -> None:
        """Show a calibration factor, whatever its source."""
        self.calibration.setText(str(value))
        self.factorChanged.emit(value)

    def show_reading(self, value: float) -> None:
        """Show one channel's reading, already scaled by its factors."""
        if self.value is not None:
            self.value.setText(f"{value:.1f}")

    @property
    def factor(self) -> int:
        """The calibration factor currently shown."""
        return int(self.calibration.text())


class PadCard(QWidget):
    """Framed channel map for a single pad."""

    def __init__(
        self,
        title: str,
        *,
        show_mark: bool = True,
        show_title: bool = True,
        show_calibration: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._show_mark = show_mark
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
        # Floor for the middle row instead of a minimum height on the card: an
        # explicit widget minimum would override the grid's own minimum and let
        # the channel blocks be squeezed into each other.
        grid.setRowMinimumHeight(1, 120)

        def block(name: str) -> ChannelBlock:
            return ChannelBlock(
                name,
                show_calibration=show_calibration,
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

        # Wrapped in a widget rather than added as a bare layout: an aligned
        # nested layout does not contribute its minimum height to the grid, and
        # the two channel blocks end up drawn on top of each other.
        centre = QWidget()
        # Plain QWidgets pick up the app background from the style sheet, which
        # would paint a dark block over the card.
        centre.setObjectName("padCentre")
        centre.setStyleSheet("QWidget#padCentre { background: transparent; }")
        centre_column = QVBoxLayout(centre)
        centre_column.setContentsMargins(0, 0, 0, 0)
        centre_column.setSpacing(8)
        for name in ("ch0", "ch6"):
            widget = block(name)
            self.channels[name] = widget
            centre_column.addWidget(widget)
        grid.addWidget(centre, 1, 1, Qt.AlignmentFlag.AlignVCenter)

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
        cop: str | None = "pad",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.forces_visible = show_forces
        self.cop_mode = cop

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        row.addWidget(self._forces_column(show_forces))
        self.card = PadCard(
            title,
            show_mark=show_mark,
            show_title=show_title,
            show_calibration=show_calibration,
        )
        row.addWidget(self.card, 1)
        row.addWidget(self._cop_column(cop))

    def _forces_column(self, visible: bool) -> QWidget:
        # The side columns keep their width even when empty, so pad rows stay
        # aligned with each other whatever the view shows.
        holder = QWidget()
        holder.setFixedWidth(SIDE_COLUMN)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 10, 0, 0)
        column.setSpacing(12)

        self.forces: dict[str, QLineEdit] = {}
        if not visible:
            return holder

        for name in ("Fx", "Fy", "Fz"):
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.addWidget(mono(name, size=10), 0, Qt.AlignmentFlag.AlignHCenter)
            value = readout("0.0", size=10)
            cell.addWidget(value)
            self.forces[name] = value
            column.addLayout(cell)
        column.addStretch(1)
        return holder

    def set_forces(self, fx: float, fy: float, fz: float) -> None:
        """Show this pad's own forces; a no-op unless the column is visible."""
        for name, value in (("Fx", fx), ("Fy", fy), ("Fz", fz)):
            cell = self.forces.get(name)
            if cell is not None:
                cell.setText(f"{value:.1f}")

    def clear_forces(self) -> None:
        self.set_forces(0.0, 0.0, 0.0)

    def _cop_column(self, mode: str | None) -> QWidget:
        holder = QWidget()
        holder.setFixedWidth(COP_COLUMN)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 10, 0, 0)
        column.setSpacing(5)

        self.cop: CopPlot | None = None
        if mode is None:
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
        # The plot is the plate itself, drawn to scale with its load cells on
        # it, so the marker can be read against the hardware.
        self.cop = CopPlot(
            plate=DOUBLE_PLATE if total else SINGLE_PLATE,
            sensors=DOUBLE_SENSORS if total else SINGLE_SENSORS,
            width=COP_COLUMN,
            pads=2 if total else 1,
        )
        column.addWidget(self.cop)
        column.addStretch(1)
        return holder
