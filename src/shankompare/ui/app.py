"""Application bootstrap."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from shankompare.sessions import SettingsStore

from .main_window import MainWindow
from .resources import icon_path, log_dir
from .theme import apply_theme

_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _configure_logging() -> None:
    """Log to a rotating file so a windowed exe (no console) still records output.

    stderr is kept too, which is what you see when running from a terminal or
    ``python -m shankompare``; the file is the only record for the packaged app.
    """
    directory = log_dir()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                directory / "shankompare.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )
    except OSError:
        pass  # no writable log dir — carry on with stderr only
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    logging.getLogger(__name__).info("shankompare starting; log file at %s", directory)


def _load_app_icon() -> QIcon:
    icon = QIcon()
    for size in _ICON_SIZES:
        path = icon_path(f"shankompare_{size}.png")
        if path.exists():
            icon.addFile(str(path))
    return icon


def run() -> int:
    _configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("shankompare")
    app.setWindowIcon(_load_app_icon())
    apply_theme(SettingsStore().load().theme)
    window = MainWindow()
    window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()
