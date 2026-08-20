"""Centre-of-pressure mini plots drawn to the right of each pad card."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

import theme

CORNER_MARK = 10  # size of the red orientation triangle, in px


class CopPlot(QWidget):
    """Framed plot with a crosshair, an orientation mark and a marker dot.

    ``extra_gridlines`` adds the quarter lines used by the double-platform
    "total cop" plot.
    """

    def __init__(
        self,
        *,
        height: int = 68,
        extra_gridlines: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedHeight(height)
        self._extra_gridlines = extra_gridlines
        self._marker = QPointF(0.5, 0.5)  # normalised position within the frame

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        frame = QPainterPath()
        frame.addRoundedRect(rect, 3, 3)
        painter.fillPath(frame, QColor(theme.PLOT_BG))

        painter.save()
        painter.setClipPath(frame)

        painter.setPen(QPen(QColor(theme.FIELD_READONLY), 1))
        mid_y = rect.top() + rect.height() / 2
        mid_x = rect.left() + rect.width() / 2
        painter.drawLine(QPointF(rect.left(), mid_y), QPointF(rect.right(), mid_y))
        painter.drawLine(QPointF(mid_x, rect.top()), QPointF(mid_x, rect.bottom()))
        if self._extra_gridlines:
            for fraction in (0.25, 0.75):
                y = rect.top() + rect.height() * fraction
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        # orientation mark: filled triangle in the top-left corner
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

        centre = QPointF(
            rect.left() + rect.width() * self._marker.x(),
            rect.top() + rect.height() * self._marker.y(),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT))
        painter.drawEllipse(centre, 3.5, 3.5)
