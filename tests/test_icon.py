"""Guards the checked-in icon assets: files exist, decode, and aren't blank."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from shankompare.ui.app import _ICON_SIZES, _load_app_icon
from shankompare.ui.resources import doc_path, icon_path


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("size", (16, 24, 32, 48, 64, 128, 256))
def test_icon_png_exists_and_has_content(size):
    path = icon_path(f"shankompare_{size}.png")
    assert path.exists(), path
    image = QImage(str(path))
    assert not image.isNull()
    assert image.width() == size
    assert image.height() == size
    # not fully transparent/blank
    assert image.pixelColor(size // 2, size // 2).alpha() > 0


def test_ico_exists():
    path = icon_path("shankompare.ico")
    assert path.exists()
    assert path.stat().st_size > 0


def test_load_app_icon_has_all_sizes(app):
    icon = _load_app_icon()
    assert not icon.isNull()
    sizes = {s.width() for s in icon.availableSizes()}
    assert sizes == set(_ICON_SIZES)


def test_resources_resolve_inside_the_package_when_not_frozen():
    # Not frozen in tests, so this must land in the package's own resources
    # directory — the layout that makes an installed wheel work too.
    import shankompare

    package_root = Path(shankompare.__file__).resolve().parent
    for path in (icon_path("shankompare.ico"), doc_path("MANUAL.md")):
        assert path.exists(), path
        assert path.is_relative_to(package_root / "resources"), path
