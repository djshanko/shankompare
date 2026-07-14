"""Theme handling: follow the OS color scheme by default, allow override."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

THEMES = ("system", "light", "dark")

_SCHEMES = {
    "light": Qt.ColorScheme.Light,
    "dark": Qt.ColorScheme.Dark,
    "system": Qt.ColorScheme.Unknown,  # Unknown = revert to the platform scheme
}


def apply_theme(theme: str) -> None:
    QGuiApplication.styleHints().setColorScheme(_SCHEMES.get(theme, Qt.ColorScheme.Unknown))


def is_dark() -> bool:
    """Whether the effective palette is dark (drives diff/status colors)."""
    palette = QGuiApplication.palette()
    return palette.window().color().lightness() < 128
