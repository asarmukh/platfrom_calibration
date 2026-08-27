"""Centre-of-pressure plot: the plate drawn to scale, with the load cells on it.

Everything is positioned in centimetres from the platform centre, exactly as the
ТЗ section 1 figure gives them, and mapped to pixels by one scale factor. So the
marker lands where the platform says the load is — over a load cell when the
weight sits on that cell, which is what makes the plot worth looking at during
calibration.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme

CORNER_MARK = 12  # size of the red orientation triangle, in px
MARKER_RADIUS = 4.0  # px
LABEL_SIZE = 8  # pt
LABEL_BOX = (28.0, 12.0)  # px the channel label is centred in


class CopPlot(QWidget):
    """The platform seen from above: plate outline, channel marks and the cop dot.

    ``plate`` is the plate's size in cm and fixes the widget's aspect ratio.
    ``sensors`` are the four Fz load cells of each pad, keyed by the channel
    label written at their position; a ``#2`` suffix marks the second pad, so a
    label repeats as it does in the ТЗ figure. ``pads`` above one draws the two
    plates a double platform is made of.
    """

    def __init__(
        self,
        *,
        plate: tuple[float, float],
        sensors: dict[str, tuple[float, float]],
        width: int,
        pads: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._plate = plate
        self._sensors = sensors
        self._pads = pads
        self._marker: tuple[float, float] | None = None
        # One scale for both axes, so the plate keeps its proportions.
        self.setFixedSize(width, round(width * plate[1] / plate[0]))

    # --- data ---------------------------------------------------------------

    def set_point(self, x: float | None, y: float | None) -> None:
        """Plot a centre of pressure in cm, or clear it when there is none."""
        self._marker = None if x is None or y is None else (x, y)
        self.update()

    def clear(self) -> None:
        self.set_point(None, None)

    # --- painting -----------------------------------------------------------

    def plate_rect(self) -> QRectF:
        """The plate's outline in widget coordinates."""
        return QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

    def point_at(self, x: float, y: float) -> QPointF:
        """Centimetres from the platform centre to a point in the widget.

        One scale for both axes, so the plate keeps its proportions; it is the
        tighter of the two fits, because integer widget sizes cannot hold the
        ratio exactly. Screen y grows downwards, the platform's y axis upwards.
        """
        rect = self.plate_rect()
        scale = min(rect.width() / self._plate[0], rect.height() / self._plate[1])
        return QPointF(
            rect.center().x() + x * scale, rect.center().y() - y * scale
        )

    def label_at(self, x: float, y: float) -> QRectF:
        """The box a channel label is centred in, at a cm position."""
        centre = self.point_at(x, y)
        return QRectF(
            centre.x() - LABEL_BOX[0] / 2,
            centre.y() - LABEL_BOX[1] / 2,
            LABEL_BOX[0],
            LABEL_BOX[1],
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.plate_rect()
        at = self.point_at

        outline = self._draw_plate(painter, rect, at)
        painter.save()
        painter.setClipPath(outline)
        self._draw_axes(painter, rect, at)
        self._draw_cells(painter)
        self._draw_mark(painter, rect)
        painter.restore()
        self._draw_outline(painter, outline)
        self._draw_marker(painter, at)

    def _draw_plate(self, painter, rect, at) -> QPainterPath:
        """Fill the plate, and split it when two pads share the plot."""
        outline = QPainterPath()
        outline.addRoundedRect(rect, 3, 3)
        painter.fillPath(outline, QColor(theme.PLOT_BG))

        if self._pads > 1:
            # The two plates butt against each other along the x axis; the
            # figure draws the seam as a double line.
            painter.setPen(QPen(QColor(theme.BORDER), 1))
            for offset in (-1.0, 1.0):
                y = at(0, 0).y() + offset
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        return outline

    def _draw_axes(self, painter, rect, at) -> None:
        painter.setPen(QPen(QColor(theme.FIELD_READONLY), 1))
        centre = at(0, 0)
        painter.drawLine(
            QPointF(rect.left(), centre.y()), QPointF(rect.right(), centre.y())
        )
        painter.drawLine(
            QPointF(centre.x(), rect.top()), QPointF(centre.x(), rect.bottom())
        )

    def _draw_cells(self, painter) -> None:
        """Each Fz load cell marked by its channel number, at its position."""
        painter.setFont(theme.font("mono", LABEL_SIZE))
        painter.setPen(QColor(theme.VALUE_DIM))
        for label, (x, y) in self._sensors.items():
            painter.drawText(
                self.label_at(x, y),
                Qt.AlignmentFlag.AlignCenter,
                _name(label),
            )

    def _draw_mark(self, painter, rect) -> None:
        """Orientation triangle: the physical corner mark on the plate."""
        mark = QPainterPath()
        mark.moveTo(rect.left(), rect.top())
        mark.lineTo(rect.left() + CORNER_MARK, rect.top())
        mark.lineTo(rect.left(), rect.top() + CORNER_MARK)
        mark.closeSubpath()
        painter.fillPath(mark, QColor(theme.ACCENT))

    def _draw_outline(self, painter, outline) -> None:
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(outline)

    def _draw_marker(self, painter, at) -> None:
        if self._marker is None:
            return  # no load, no centre of pressure
        # Full deflection parks the marker on a load cell, so it needs a rim to
        # stay legible over the cell it is sitting on.
        painter.setPen(QPen(QColor(theme.BG), 1.5))
        painter.setBrush(QColor(theme.ACCENT))
        painter.drawEllipse(at(*self._marker), MARKER_RADIUS, MARKER_RADIUS)


def _name(label: str) -> str:
    """Channel name without the second-pad suffix: ``ch1#2`` -> ``ch1``."""
    return label.split("#")[0]
