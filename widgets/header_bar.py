"""Top bar: brand mark and product title."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from . import theme
from paths import bundle_dir

from .common import label, rule

LOGO_SVG = bundle_dir() / "assets" / "logo.svg"
LOGO_RASTER = bundle_dir() / "assets" / "logo.jpeg"
LOGO_HEIGHT = 24  # sized so the mark reads level with the product title

# Alpha keying thresholds for the raster fallback: how far a pixel must differ
# from the background colour to count as artwork. The band between them keeps
# antialiased edges.
_KEY_LOW = 18
_KEY_HIGH = 70


def load_logo(
    height: int = LOGO_HEIGHT,
    *,
    svg_path: Path = LOGO_SVG,
    raster_path: Path = LOGO_RASTER,
) -> QPixmap | None:
    """Brand mark scaled to `height`, or None if no usable file was found.

    The vector is preferred: it carries real transparency and stays sharp at
    any size or screen scale. The keyed JPEG is the fallback.
    """
    return _render_svg(svg_path, height) or _key_raster(raster_path, height)


def _render_svg(path: Path, height: int) -> QPixmap | None:
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return None

    size = renderer.defaultSize()
    if size.height() <= 0:
        return None
    width = round(size.width() * height / size.height())

    # Render at the screen's pixel density so the mark is sharp on hi-dpi
    # displays, then tell Qt the pixmap is that much denser than it looks.
    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen is not None else 1.0

    pixmap = QPixmap(round(width * ratio), round(height * ratio))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, width * ratio, height * ratio))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def _key_raster(path: Path, height: int) -> QPixmap | None:
    """Load a raster mark, dropping its flat background to transparency.

    A JPEG carries an opaque backdrop that would show as a lighter box on the
    header. The corner pixel is taken as that backdrop and every pixel close to
    it is made transparent, with a soft band so the edges stay smooth.
    """
    image = QImage(str(path))
    if image.isNull():
        return None

    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    backdrop = image.pixel(0, 0)
    br, bg, bb = (backdrop >> 16) & 0xFF, (backdrop >> 8) & 0xFF, backdrop & 0xFF

    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixel(x, y)
            r, g, b = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF
            distance = max(abs(r - br), abs(g - bg), abs(b - bb))
            if distance <= _KEY_LOW:
                alpha = 0
            elif distance >= _KEY_HIGH:
                alpha = 255
            else:
                alpha = round(255 * (distance - _KEY_LOW) / (_KEY_HIGH - _KEY_LOW))
            image.setPixel(x, y, (alpha << 24) | (r << 16) | (g << 8) | b)

    return QPixmap.fromImage(
        image.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
    )


class StatusDot(QWidget):
    """7px round indicator; grey when no platform is linked."""

    def __init__(self, color: str = theme.MUTED_DIM, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(7, 7)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._color))
        painter.drawEllipse(self.rect())


class HeaderBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setStyleSheet(
            f"QFrame#panel {{ background: {theme.PANEL}; "
            f"border-bottom: 1px solid {theme.BORDER}; }}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(28, 12, 28, 12)
        row.setSpacing(16)

        self.logo = QLabel()
        # Without this the label paints the app background over the header,
        # leaving a slightly darker box around the mark.
        self.logo.setStyleSheet("background: transparent;")
        logo = load_logo()
        if logo is not None:
            self.logo.setPixmap(logo)
        else:
            self.logo.hide()

        self.title = label(
            "PLATFORM CALIBRATION",
            role="display",
            size=14,
            color=theme.TEXT_BRIGHT,
            weight=QFont.Weight.DemiBold,
            tracking=0.22,
        )

        # Hairline between the brand mark and the product title, so the two
        # wordmarks do not read as one.
        self.divider = rule(horizontal=False)
        self.divider.setFixedHeight(LOGO_HEIGHT)

        row.addWidget(self.logo)
        row.addWidget(self.divider)
        row.addWidget(self.title)
        row.addStretch(1)
