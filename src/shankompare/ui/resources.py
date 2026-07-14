"""Locates bundled assets, whether running from source or a PyInstaller build."""

import sys
from pathlib import Path


def _base_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[3]


def icon_path(name: str) -> Path:
    return _base_dir() / "assets" / "icons" / name


def doc_path(name: str) -> Path:
    return _base_dir() / "docs" / name
