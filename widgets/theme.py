"""Design tokens for the Platform Calibration UI.

Values mirror the source design (Platform Calibration v2). Colours are kept as
plain hex strings so they can be dropped straight into Qt style sheets.
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

# --- colour ----------------------------------------------------------------

BG = "#0A0E1A"          # app background
PANEL = "#0D1220"       # header, sidebar, pad card
BORDER = "#2A3347"      # hairline dividers and panel borders
BORDER_STRONG = "#38425A"

TEXT = "#C7D0E0"        # body copy
TEXT_BRIGHT = "#E8EDF7" # channel labels, headings
TEXT_INPUT = "#D6DEEC"
MUTED = "#6D7A96"       # section captions
MUTED_DIM = "#5B6782"
MUTED_SOFT = "#4E5A73"  # placeholder / footnote
VALUE_DIM = "#94A0B6"   # read-only figures
VALUE_SOFT = "#7E8AA1"  # factory GF figures
BTN_TEXT = "#9AA6BD"

ACCENT = "#E5432E"
ACCENT_SOFT = "#F0937F"
ONLINE = "#4CC38A"

FIELD = "#2B3446"       # editable field background
FIELD_READONLY = "#232B3B"
FIELD_LIGHT = "#F2F5FA" # total Fx/Fy/Fz readout
BTN = "#1B2334"
BTN_HOVER = "#26314A"
BTN_QUIET = "#131A28"
BTN_QUIET_HOVER = "#1B2334"
STEPPER_HOVER = "#3A4560"
PLOT_BG = "#131A28"

# --- type ------------------------------------------------------------------

_FAMILIES: dict[str, list[str]] = {
    # Barlow Condensed / Barlow / JetBrains Mono are the design fonts; the rest
    # are fallbacks so the app still looks right on a machine without them.
    "display": ["Barlow Condensed", "Oswald", "Segoe UI Semibold", "Segoe UI"],
    "body": ["Barlow", "Segoe UI", "DejaVu Sans"],
    "mono": ["JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New"],
}

_resolved: dict[str, str] = {}


def family(role: str) -> str:
    """First installed family for ``role``. Requires a live QApplication."""
    if role not in _resolved:
        installed = set(QFontDatabase.families())
        candidates = _FAMILIES[role]
        _resolved[role] = next(
            (name for name in candidates if name in installed), candidates[-1]
        )
    return _resolved[role]


def font(
    role: str,
    size: int,
    *,
    weight: QFont.Weight = QFont.Weight.Normal,
    tracking: float = 0.0,
) -> QFont:
    """Build a font. ``tracking`` is letter-spacing in em, as in the design."""
    f = QFont(family(role), size)
    f.setWeight(weight)
    if tracking:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + tracking * 100)
    return f


# --- global style sheet ----------------------------------------------------

STYLE_SHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
}}

QFrame#panel {{
    background: {PANEL};
}}

QFrame#rule {{
    background: {BORDER};
    border: none;
}}

/* editable numeric field */
QLineEdit {{
    background: {FIELD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 4px;
    color: {TEXT_INPUT};
    padding: 4px;
    selection-background-color: {ACCENT};
    selection-color: {BG};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled {{
    background: {BTN_QUIET};
    border: 1px solid {BORDER};
    color: {MUTED_SOFT};
}}

/* read-only figures */
QLineEdit#readout {{
    background: {FIELD_READONLY};
    border: none;
    color: {VALUE_DIM};
}}
QLineEdit#readoutSoft {{
    background: {FIELD_READONLY};
    border: none;
    color: {VALUE_SOFT};
}}
QLineEdit#readoutLight {{
    background: {FIELD_LIGHT};
    border: none;
    border-radius: 3px;
    color: {BG};
}}

/* device actions */
QPushButton#action {{
    background: {BTN};
    border: 1px solid {BORDER_STRONG};
    border-radius: 5px;
    color: #DCE3F0;
    padding: 12px 16px;
}}
QPushButton#action:hover {{
    background: {BTN_HOVER};
}}
QPushButton#action:disabled {{
    background: {BTN_QUIET};
    border: 1px solid {BORDER};
    color: {MUTED_SOFT};
}}
QPushButton#actionPrimary {{
    background: {BTN};
    border: 1px solid {ACCENT};
    border-radius: 5px;
    color: {ACCENT_SOFT};
    padding: 12px 16px;
}}
QPushButton#actionPrimary:hover {{
    background: {BTN_HOVER};
}}
QPushButton#actionPrimary:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: {BG};
}}
QPushButton#actionPrimary:checked:hover {{
    background: #F0563F;
}}
QPushButton#actionPrimary:disabled {{
    background: {BTN_QUIET};
    border: 1px solid #5C2A22;
    color: #7A4438;
}}
QPushButton#actionQuiet {{
    background: {BTN_QUIET};
    border: 1px solid {BORDER};
    border-radius: 5px;
    color: {BTN_TEXT};
    padding: 12px 16px;
}}
QPushButton#actionQuiet:hover {{
    background: {BTN_QUIET_HOVER};
}}

/* +/- steppers */
QPushButton#stepper {{
    background: {FIELD};
    border: none;
    border-radius: 4px;
    color: {TEXT};
}}
QPushButton#stepper:hover {{
    background: {STEPPER_HOVER};
}}
QPushButton#stepper:disabled {{
    background: {FIELD_READONLY};
    color: {MUTED_SOFT};
}}

QStatusBar {{
    background: {PANEL};
    border-top: 1px solid {BORDER};
}}
QStatusBar::item {{
    border: none;
}}
QPushButton#statusAction {{
    background: {BTN};
    border: 1px solid {BORDER_STRONG};
    border-radius: 4px;
    color: #DCE3F0;
    padding: 3px 12px;
}}
QPushButton#statusAction:hover {{
    background: {BTN_HOVER};
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    border: none;
}}
QScrollBar:vertical {{
    background: {BG};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar:horizontal {{
    background: {BG};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: {BG};
}}
"""
