"""Headless tests for the folder-view refresh/expand controls and the
text-view line-number gutter."""

import os
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from shankompare.compare import NodeResult, Status, decode_bytes
from shankompare.ui.folder_view import FolderCompareView
from shankompare.ui.panes import DiffPane
from shankompare.ui.text_compare import TextCompareView
from shankompare.vfs import EntryInfo

STAMP = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _dir(name: str) -> EntryInfo:
    return EntryInfo(name, True, 0, STAMP)


def _file(name: str, size: int) -> EntryInfo:
    return EntryInfo(name, False, size, STAMP)


def _sample_tree() -> NodeResult:
    child = NodeResult("a.txt", Status.DIFFERENT, _file("a.txt", 1), _file("a.txt", 2))
    return NodeResult("", Status.DIFFERENT, _dir("."), _dir("."), children=[child])


def test_refresh_button_enables_after_result_and_emits(app):
    view = FolderCompareView()
    assert not view._refresh_btn.isEnabled()

    view.set_result(_sample_tree())
    assert view._refresh_btn.isEnabled()

    fired = []
    view.refresh_requested.connect(lambda: fired.append(True))
    view._refresh_btn.click()
    assert fired == [True]


def test_expand_and_collapse_all(app):
    view = FolderCompareView()
    view.set_result(_sample_tree())
    # exercised for crash-safety; the tree has a collapsible root row
    view._tree_expand_all()
    assert view._tree.isExpanded(view._proxy.index(0, 0))
    view._tree_collapse_all()
    assert not view._tree.isExpanded(view._proxy.index(0, 0))


def test_text_view_aligned_line_numbers(app):
    view = TextCompareView("left", "right")
    view.set_data(decode_bytes(b"a\nb\nc\n"), decode_bytes(b"a\nX\nc\n"))
    assert view._left_pane.line_number_area_width() > 0
    # rows map 1:1 to source lines here, numbered from 1
    assert view._left_pane._numbers[:3] == [1, 2, 3]
    assert view._right_pane._numbers[:3] == [1, 2, 3]


def test_text_view_padding_rows_have_blank_number(app):
    view = TextCompareView("left", "right")
    # right side gains an extra line → a padding row on the left
    view.set_data(decode_bytes(b"a\nc\n"), decode_bytes(b"a\nb\nc\n"))
    left_nums = view._left_pane._numbers
    assert None in left_nums  # padding row carries no left line number
    assert all(n is not None for n in view._right_pane._numbers)


def test_edit_mode_uses_sequential_numbering(app):
    view = TextCompareView("left", "right")
    view.set_data(decode_bytes(b"a\nb\n"), decode_bytes(b"a\nb\n"))
    view._edit_check.setChecked(True)
    assert view._left_pane._sequential
    assert view._left_pane.line_number_area_width() > 0


def test_hex_style_pane_has_no_gutter(app):
    pane = DiffPane()  # neither numbering mode set (as used by the hex view)
    pane.setPlainText("00\n01\n02")
    assert pane.line_number_area_width() == 0
