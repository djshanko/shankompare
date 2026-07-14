"""Application bootstrap."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from shankompare.sessions import SettingsStore

from .main_window import MainWindow
from .theme import apply_theme


def run() -> int:
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setApplicationName("shankompare")
    apply_theme(SettingsStore().load().theme)
    window = MainWindow()
    window.show()
    return app.exec()
