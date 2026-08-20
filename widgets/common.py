"""Small building blocks shared by the panels of the calibration window."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

import theme


def label(
    text: str,
    *,
    role: str = "body",
    size: int = 12,
    color: str = theme.TEXT,
    weight: QFont.Weight = QFont.Weight.Normal,
    tracking: float = 0.0,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
) -> QLabel:
    lab = QLabel(text)
    lab.setFont(theme.font(role, size, weight=weight, tracking=tracking))
    lab.setStyleSheet(f"color: {color}; background: transparent;")
    lab.setAlignment(align)
    return lab


def caption(text: str) -> QLabel:
    """The small uppercase section headings used down the sidebar."""
    return label(
        text.upper(),
        role="display",
        size=10,
        color=theme.MUTED,
        weight=QFont.Weight.Medium,
        tracking=0.2,
    )


def mono(text: str, *, size: int = 11, color: str = theme.TEXT_BRIGHT) -> QLabel:
    return label(
        text,
        role="mono",
        size=size,
        color=color,
        align=Qt.AlignmentFlag.AlignCenter,
    )


def field(
    value: str = "",
    *,
    placeholder: str = "",
    size: int = 10,
    max_width: int | None = None,
) -> QLineEdit:
    """Editable, centre-aligned numeric field."""
    edit = QLineEdit(value)
    edit.setPlaceholderText(placeholder)
    edit.setFont(theme.font("mono", size))
    edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if max_width is not None:
        edit.setMaximumWidth(max_width)
    return edit


def readout(
    value: str = "",
    *,
    variant: str = "readout",
    size: int = 10,
    height: int = 24,
) -> QLineEdit:
    """Read-only figure. ``variant`` picks one of the styles in theme.py."""
    edit = QLineEdit(value)
    edit.setObjectName(variant)
    edit.setReadOnly(True)
    edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    edit.setFont(theme.font("mono", size))
    edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
    edit.setFixedHeight(height)
    return edit


def action_button(text: str, *, variant: str = "action") -> QPushButton:
    btn = QPushButton(text.upper())
    btn.setObjectName(variant)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    weight = (
        QFont.Weight.Bold if variant == "actionPrimary" else QFont.Weight.DemiBold
    )
    btn.setFont(theme.font("display", 11, weight=weight, tracking=0.2))
    return btn


def stepper_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("stepper")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(22, 22)
    btn.setFont(theme.font("mono", 12))
    return btn


def rule(horizontal: bool = True) -> QFrame:
    line = QFrame()
    line.setObjectName("rule")
    if horizontal:
        line.setFixedHeight(1)
    else:
        line.setFixedWidth(1)
    return line


class SegmentedControl(QFrame):
    """Two-button toggle with a single shared outline, as in the design.

    Emits `changed` with the index of the newly selected segment.
    """

    changed = Signal(int)

    def __init__(
        self,
        left: str,
        right: str,
        *,
        active: int = 0,
        role: str = "display",
        size: int = 11,
        tracking: float = 0.16,
        padding: str = "10px 8px",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._role = role
        self._padding = padding
        self._active = active
        self.setStyleSheet(
            f"QFrame {{ border: 1px solid {theme.BORDER}; border-radius: 6px; "
            f"background: {theme.BTN_QUIET}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(1, 1, 1, 1)
        row.setSpacing(0)

        self.buttons: list[QPushButton] = []
        for index, text in enumerate((left, right)):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            weight = (
                QFont.Weight.DemiBold if role == "display" else QFont.Weight.Normal
            )
            btn.setFont(theme.font(role, size, weight=weight, tracking=tracking))
            btn.clicked.connect(lambda _=False, i=index: self.set_active(i))
            row.addWidget(btn, 1)
            self.buttons.append(btn)

        self._restyle()

    @property
    def active(self) -> int:
        return self._active

    def set_active(self, index: int) -> None:
        """Select a segment. Emits `changed` only when the selection moves."""
        if index == self._active or not 0 <= index < len(self.buttons):
            return
        self._active = index
        self._restyle()
        self.changed.emit(index)

    def _restyle(self) -> None:
        for index, btn in enumerate(self.buttons):
            btn.setStyleSheet(self._segment_style(index))

    def _segment_style(self, index: int) -> str:
        radii = (
            "border-top-left-radius: 5px; border-bottom-left-radius: 5px;"
            if index == 0
            else "border-top-right-radius: 5px; border-bottom-right-radius: 5px;"
        )
        divider = f"border-left: 1px solid {theme.BORDER};" if index == 1 else ""

        if index == self._active:
            bg, fg = (
                (theme.ACCENT, theme.BG)
                if self._role == "display"
                else (theme.FIELD, theme.TEXT_BRIGHT)
            )
            hover = bg
        else:
            bg, fg = (
                (theme.BTN, theme.BTN_TEXT)
                if self._role == "display"
                else (theme.BTN_QUIET, theme.MUTED)
            )
            hover = theme.BTN_HOVER

        return (
            f"QPushButton {{ background: {bg}; color: {fg}; border: none; "
            f"{divider} {radii} padding: {self._padding}; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
        )
