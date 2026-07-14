"""Application bootstrap."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def run() -> int:
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setApplicationName("shankompare")
    window = MainWindow()
    window.show()
    return app.exec()
