"""Locates bundled assets, whether running from source or a PyInstaller build."""

import sys
from pathlib import Path


def icon_path(name: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "assets" / "icons"
    else:
        base = Path(__file__).resolve().parents[3] / "assets" / "icons"
    return base / name
