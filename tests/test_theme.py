"""Theme must produce a visibly different palette regardless of the native
style's support for QStyleHints.colorScheme (e.g. Windows 10's "windowsvista"
style ignores it entirely — see theme.py's module docstring)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from shankompare.ui.theme import apply_theme, is_dark


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_light_and_dark_produce_different_palettes(app):
    apply_theme("light")
    assert not is_dark()
    apply_theme("dark")
    assert is_dark()
    apply_theme("light")
    assert not is_dark()


def test_dark_forces_fusion_style(app):
    apply_theme("dark")
    assert app.style().objectName().lower() == "fusion"


def test_system_restores_the_original_style_and_palette(app):
    apply_theme("system")
    original_style = app.style().objectName()
    original_palette = app.palette()

    apply_theme("dark")
    assert is_dark()

    apply_theme("system")
    assert app.style().objectName() == original_style
    assert app.palette() == original_palette
