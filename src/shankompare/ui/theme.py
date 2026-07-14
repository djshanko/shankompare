"""Theme handling: follow the OS color scheme by default, allow override.

The native style Qt picks per platform ("windowsvista" pre-Windows 11,
"windows11" from Qt 6.7+ on Windows 11 itself, various GTK/Breeze styles on
Linux) is the only one that reliably reacts to QStyleHints.colorScheme —
and only on the platforms/Qt versions that actually implement that hook.
Windows 10's "windowsvista" style ignores it entirely, so an explicit
light/dark override would have no visual effect there. To make an explicit
choice work everywhere, switch to Qt's "Fusion" style — it is palette-driven
and ignores OS theming — and apply a matching QPalette. "System" restores
whatever native style/palette the app started with and lets the OS decide.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

THEMES = ("system", "light", "dark")

_SCHEMES = {
    "light": Qt.ColorScheme.Light,
    "dark": Qt.ColorScheme.Dark,
    "system": Qt.ColorScheme.Unknown,  # Unknown = revert to the platform scheme
}

_native_style_name: str | None = None
_native_palette: QPalette | None = None


def _dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor(45, 45, 45)
    base = QColor(30, 30, 30)
    text = QColor(220, 220, 220)
    disabled_text = QColor(127, 127, 127)
    highlight = QColor(42, 130, 218)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipBase, text)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    return palette


def _fusion_light_palette() -> QPalette:
    style = QStyleFactory.create("Fusion")
    return style.standardPalette()


def apply_theme(theme: str) -> None:
    QGuiApplication.styleHints().setColorScheme(_SCHEMES.get(theme, Qt.ColorScheme.Unknown))

    app = QApplication.instance()
    if app is None:
        return  # nothing to restyle yet (e.g. called before QApplication exists)

    global _native_style_name, _native_palette
    if _native_style_name is None:
        _native_style_name = app.style().objectName()
        _native_palette = app.palette()

    if theme == "system":
        app.setStyle(_native_style_name)
        app.setPalette(_native_palette)
    else:
        app.setStyle("Fusion")
        app.setPalette(_dark_palette() if theme == "dark" else _fusion_light_palette())


def is_dark() -> bool:
    """Whether the effective palette is dark (drives diff/status colors)."""
    palette = QGuiApplication.palette()
    return palette.window().color().lightness() < 128
