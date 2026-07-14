"""Application bootstrap."""

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from shankompare.sessions import SettingsStore

from .main_window import MainWindow
from .resources import icon_path
from .theme import apply_theme

_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _load_app_icon() -> QIcon:
    icon = QIcon()
    for size in _ICON_SIZES:
        path = icon_path(f"shankompare_{size}.png")
        if path.exists():
            icon.addFile(str(path))
    return icon


def run() -> int:
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setApplicationName("shankompare")
    app.setWindowIcon(_load_app_icon())
    apply_theme(SettingsStore().load().theme)
    window = MainWindow()
    window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()
