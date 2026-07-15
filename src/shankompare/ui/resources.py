"""Locates bundled assets, whether running from source or a PyInstaller build."""

import sys
from pathlib import Path

from platformdirs import user_log_dir


def _base_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[3]


def log_dir() -> Path:
    """Directory holding ``shankompare.log`` (per-user; not created here)."""
    return Path(user_log_dir("shankompare", appauthor=False))


def icon_path(name: str) -> Path:
    return _base_dir() / "assets" / "icons" / name


def doc_path(name: str) -> Path:
    return _base_dir() / "docs" / name
