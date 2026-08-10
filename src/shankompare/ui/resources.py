"""Locates bundled resources, whatever the install shape."""

import sys
from pathlib import Path

from platformdirs import user_log_dir


def _base_dir() -> Path:
    """Directory holding the bundled icons and user documentation.

    They live *inside* the package (``shankompare/resources``) rather than
    beside it, so every install shape finds them by the same relative path: a
    source checkout, a wheel unpacked into site-packages, and a PyInstaller
    bundle, which extracts its data under ``_MEIPASS`` keeping that layout.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "shankompare" / "resources"
    return Path(__file__).resolve().parents[1] / "resources"


def log_dir() -> Path:
    """Directory holding ``shankompare.log`` (per-user; not created here)."""
    return Path(user_log_dir("shankompare", appauthor=False))


def icon_path(name: str) -> Path:
    return _base_dir() / "icons" / name


def doc_path(name: str) -> Path:
    return _base_dir() / "docs" / name
