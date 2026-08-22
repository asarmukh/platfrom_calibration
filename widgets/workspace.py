"""Right-hand work area: the empty state and the pad calibration view."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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
from .common import NumericField, SegmentedControl, label
from .pad_card import PadRow

CONTENT_MAX_WIDTH = 1000

EMPTY = 0
PADS = 1

# views
GF = "gf"
CAL = "cal"

SECTION_TITLES = {
    CAL: "CALIBRATION FACTOR SETUP",
    GF: "FACTORY GF SETUP",
}


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

    viewChanged = Signal(str)
    # A GF field was committed: pad number (1-based), channel number, value.
    factoryChanged = Signal(int, int, int)
    # Text that could not be accepted as a GF value.
    factoryRejected = Signal(str)
    # A stepper hit the end of its range: pad, channel, the limit reached.
    calibrationLimit = Signal(int, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pad_count = 1
        self._view = GF  # the factory values are set up first
        self._steppers_enabled = False
        # (pad, channel) -> gain factor, kept here because switching view
        # recreates the widgets that show it.
        self._factors: dict[tuple[int, int], int] = {}
        self.pads: list[PadRow] = []

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(16)
        column.addWidget(self._heading())

        self.pad_area = QVBoxLayout()
        self.pad_area.setContentsMargins(0, 0, 0, 0)
        self.pad_area.setSpacing(16)
        column.addLayout(self.pad_area)
        column.addStretch(1)

        self._rebuild()

    # --- state -------------------------------------------------------------

    @property
    def view(self) -> str:
        return self._view

    def set_pad_count(self, count: int) -> None:
        """1 for a single platform, 2 for a double one."""
        count = max(1, count)
        if count != self._pad_count:
            self._pad_count = count
            self._rebuild()

    def set_view(self, view: str) -> None:
        # The toggle is the single source of truth; it calls back into
        # _on_view_changed, and does nothing if the view is already current.
        self.view_toggle.set_active(0 if view == GF else 1)

    def set_steppers_enabled(self, enabled: bool) -> None:
        """+/- are only usable while a run is active."""
        self._steppers_enabled = enabled
        self._apply_stepper_state()

    def _on_view_changed(self, index: int) -> None:
        self._view = GF if index == 0 else CAL
        self._rebuild()
        self.viewChanged.emit(self._view)

    def _apply_stepper_state(self) -> None:
        for pad in self.pads:
            for block in pad.card.channels.values():
                for name in ("decrement", "increment"):
                    button = getattr(block, name, None)
                    if button is not None:
                        button.setEnabled(self._steppers_enabled)

    # --- construction ------------------------------------------------------

    def _rebuild(self) -> None:
        """Recreate the pad rows for the current platform type and view."""
        while self.pad_area.count():
            item = self.pad_area.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        calibrating = self._view == CAL
        double = self._pad_count > 1
        self.title.setText(SECTION_TITLES[self._view])

        self.pads = []
        for index in range(self._pad_count):
            first = index == 0
            # A single platform gets its own cop plot; a double one shows the
            # combined plot once, beside the first pad.
            if not calibrating:
                cop = None
            elif double:
                cop = "total" if first else None
            else:
                cop = "pad"

            pad = PadRow(
                f"Pad {index + 1}",
                show_mark=first,
                show_title=double,  # names only matter when there are two
                show_forces=double and calibrating,
                show_calibration=calibrating,
                cop=cop,
            )
            self.pads.append(pad)
            self.pad_area.addWidget(pad)
            self._connect_channels(pad, index + 1)

        self._apply_stepper_state()  # the rows were just recreated
        self._apply_factors()

    def set_factors(self, pad_id: int, values: dict[int, int]) -> None:
        """Show the gain factors a pad reported, by channel number."""
        for channel, value in values.items():
            self._factors[(pad_id, channel)] = value
            editor = self.factory_field(pad_id, channel)
            if editor is not None:  # only the GF view shows them
                editor.set_value(value)

    def _apply_factors(self) -> None:
        for (pad_id, channel), value in self._factors.items():
            editor = self.factory_field(pad_id, channel)
            if editor is not None:
                editor.set_value(value)

    def factory_field(self, pad_id: int, channel: int) -> NumericField | None:
        """The editable GF field of one channel, or None if this view has none."""
        index = pad_id - 1
        if not 0 <= index < len(self.pads):
            return None
        block = self.pads[index].card.channels.get(f"ch{channel}")
        editor = getattr(block, "factory", None)
        return editor if isinstance(editor, NumericField) else None

    def _connect_channels(self, pad: PadRow, pad_id: int) -> None:
        """Relay what a channel's widgets report as (pad, channel, ...)."""
        for name, block in pad.card.channels.items():
            channel = int(name.removeprefix("ch"))
            block.limitReached.connect(
                lambda limit, p=pad_id, c=channel: self.calibrationLimit.emit(p, c, limit)
            )
            editor = getattr(block, "factory", None)
            if not isinstance(editor, NumericField):
                continue  # the CAL view has no editable GF field
            editor.committed.connect(
                lambda value, p=pad_id, c=channel: self._on_committed(p, c, value)
            )
            editor.rejected.connect(self.factoryRejected)

    def _on_committed(self, pad_id: int, channel: int, value: int) -> None:
        self._factors[(pad_id, channel)] = value
        self.factoryChanged.emit(pad_id, channel, value)

    def _heading(self) -> QWidget:
        # Title and toggle share one cell so the title stays optically centred
        # while the toggle hugs the right edge, as in the design.
        holder = QWidget()
        holder.setMinimumHeight(34)
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)

        self.title = label(
            SECTION_TITLES[self._view],
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
            active=0 if self._view == GF else 1,
            role="mono",
            size=9,
            tracking=0.1,
            padding="8px 16px",
        )
        self.view_toggle.changed.connect(self._on_view_changed)
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
        self.set_pad_count = self.pad_view.set_pad_count

        outer.addWidget(centred, 0, Qt.AlignmentFlag.AlignHCenter)
        self.setWidget(page)
