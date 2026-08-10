"""Headless smoke tests for the M4 UI features: hex compare, auto binary
detection, archive sides, and the filters dialog."""

import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from shankompare.compare import CompareOptions, Status
from shankompare.ui.hex_compare import HexCompareView
from shankompare.ui.worker import CompareWorker, DiffLoadWorker, LocalSide


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _run_diff_load(left_dir, right_dir, name, mode="auto"):
    worker = DiffLoadWorker(LocalSide(str(left_dir)), LocalSide(str(right_dir)), name, mode)
    got = {"text": [], "hex": [], "failed": []}
    worker.text_ready.connect(got["text"].append)
    worker.hex_ready.connect(got["hex"].append)
    worker.failed.connect(got["failed"].append)
    worker.run()
    return got


@pytest.fixture
def pair_dirs(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    return left, right


def test_auto_mode_picks_text_for_text(app, pair_dirs):
    left, right = pair_dirs
    (left / "a.txt").write_text("hello")
    (right / "a.txt").write_text("world")
    got = _run_diff_load(left, right, "a.txt")
    assert got["text"] and not got["hex"] and not got["failed"]


def test_auto_mode_picks_hex_for_binary(app, pair_dirs):
    left, right = pair_dirs
    (left / "a.bin").write_bytes(b"\x00\x01\x02same")
    (right / "a.bin").write_bytes(b"\x00\x01\x02diff")
    got = _run_diff_load(left, right, "a.bin")
    assert got["hex"] and not got["text"] and not got["failed"]


def test_forced_hex_mode_on_text_file(app, pair_dirs):
    left, right = pair_dirs
    (left / "a.txt").write_text("hello")
    (right / "a.txt").write_text("hello")
    got = _run_diff_load(left, right, "a.txt", mode="hex")
    assert got["hex"] and not got["text"]


def test_hex_view_renders_and_condenses(app, pair_dirs):
    left, right = pair_dirs
    payload = bytes(range(256)) * 4
    changed = bytearray(payload)
    changed[500] ^= 0xFF
    (left / "blob.bin").write_bytes(payload)
    (right / "blob.bin").write_bytes(bytes(changed))
    got = _run_diff_load(left, right, "blob.bin", mode="hex")

    view = HexCompareView("l", "r")
    view.on_hex_loaded(got["hex"][0])
    assert "1 differing byte(s)" in view._status.text()
    assert view._left_pane.blockCount() == 64  # 1024 bytes / 16 per row

    view._only_diff.setChecked(True)
    assert view._left_pane.blockCount() < 64
    assert "⋯" in view._left_pane.toPlainText()


def test_compare_zip_archive_against_folder(app, tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "same.txt").write_text("same")
    (folder / "extra.txt").write_text("extra")

    zip_path = tmp_path / "snapshot.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("same.txt", "same")
        zf.writestr("changed.txt", "archived version")

    worker = CompareWorker(
        LocalSide(str(zip_path)),
        LocalSide(str(folder)),
        CompareOptions(use_mtime=False),  # zip timestamps won't match the folder's
    )
    results = []
    worker.finished.connect(results.append)
    worker.failed.connect(lambda kind, side, message: pytest.fail(f"{kind}/{side}: {message}"))
    worker.run()

    statuses = {c.name: c.status for c in results[0].children}
    assert statuses == {
        "same.txt": Status.SAME,
        "changed.txt": Status.LEFT_ONLY,
        "extra.txt": Status.RIGHT_ONLY,
    }


def test_folder_view_select_by_status(app, pair_dirs):
    from shankompare.ui.folder_model import FILTERABLE_STATUSES
    from shankompare.ui.folder_view import FolderCompareView

    left, right = pair_dirs
    (left / "same.txt").write_text("x")
    (right / "same.txt").write_text("x")
    (left / "diff.txt").write_text("short")
    (right / "diff.txt").write_text("a much longer body")  # differing size ⇒ DIFFERENT
    (left / "only_left.txt").write_text("l")
    (right / "only_right.txt").write_text("r")

    worker = CompareWorker(LocalSide(str(left)), LocalSide(str(right)), CompareOptions())
    results = []
    worker.finished.connect(results.append)
    worker.failed.connect(lambda kind, side, message: pytest.fail(f"{kind}/{side}: {message}"))
    worker.run()

    view = FolderCompareView()
    view.set_result(results[0])

    view._select_by_statuses(frozenset({Status.DIFFERENT}))
    assert [i.node.name for i in view._selected_items()] == ["diff.txt"]

    view._select_by_statuses(FILTERABLE_STATUSES - {Status.SAME})
    assert sorted(i.node.name for i in view._selected_items()) == [
        "diff.txt",
        "only_left.txt",
        "only_right.txt",
    ]

    # Unchanged selects only the identical file; a status with no matches clears.
    view._select_by_statuses(frozenset({Status.SAME}))
    assert [i.node.name for i in view._selected_items()] == ["same.txt"]


def test_text_compare_word_wrap_toggle(app):
    from PySide6.QtWidgets import QPlainTextEdit

    from shankompare.compare.text import DecodedText
    from shankompare.ui.text_compare import TextCompareView

    view = TextCompareView("left", "right")
    view.set_data(
        DecodedText("a long line here", "utf-8", "LF"),
        DecodedText("another long line", "utf-8", "LF"),
    )
    assert view._left_pane.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap

    view._wrap.setChecked(True)
    assert view._left_pane.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    assert view._right_pane.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth

    view._wrap.setChecked(False)
    assert view._left_pane.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
    assert view._right_pane.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


def test_filters_dialog_roundtrip(app):
    from datetime import UTC, datetime

    from shankompare.compare import CompareFilters
    from shankompare.ui.filters_dialog import FiltersDialog

    initial = CompareFilters(
        exclude_globs=("*.log", "node_modules", "My Documents"),
        include_globs=("*.py", "weekly report*.xlsx"),
        min_size=1024,
        max_size=10 * 1024**2,
        modified_after=datetime(2026, 1, 15, 8, 30, tzinfo=UTC),
    )
    dialog = FiltersDialog(initial)
    dialog._on_accept()
    result = dialog.filters()
    # patterns containing spaces survive the display → parse round trip
    assert result.exclude_globs == initial.exclude_globs
    assert result.include_globs == initial.include_globs
    assert result.min_size == initial.min_size
    assert result.max_size == initial.max_size
    # QDateTimeEdit has minute granularity; compare at that precision in UTC
    assert result.modified_after is not None
    assert result.modified_after.astimezone(UTC).replace(second=0, microsecond=0) == (
        initial.modified_after
    )
    assert result.modified_before is None


def test_filters_dialog_clear(app):
    from shankompare.compare import CompareFilters
    from shankompare.ui.filters_dialog import FiltersDialog

    dialog = FiltersDialog(
        CompareFilters(exclude_globs=("*.tmp",), include_globs=("*.py",), min_size=5)
    )
    dialog._clear()
    dialog._on_accept()
    assert dialog.filters() == CompareFilters()
