"""Headless UI smoke tests: main window construction, a real compare streamed
through the worker into the folder view, and the text compare view."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication

from shankompare.compare import CompareOptions, Status, decode_bytes
from shankompare.ui.folder_view import FolderCompareView
from shankompare.ui.main_window import MainWindow
from shankompare.ui.text_compare import TextCompareView
from shankompare.ui.worker import CompareWorker, LocalSide


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def folder_pair(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "same.txt").write_text("same")
    (right / "same.txt").write_text("same")
    (left / "only-left.txt").write_text("x")
    (left / "sub").mkdir()
    (left / "sub" / "deep.txt").write_text("deep")
    (right / "sub").mkdir()
    (right / "sub" / "deep.txt").write_text("DIFFERENT CONTENT")
    return left, right


def test_main_window_constructs(app):
    window = MainWindow()
    window.show()
    window.close()


def test_worker_streams_into_folder_view(app, folder_pair):
    left, right = folder_pair
    view = FolderCompareView()

    worker = CompareWorker(LocalSide(str(left)), LocalSide(str(right)), CompareOptions())
    results = []
    worker.dir_scanned.connect(view.on_dir_scanned)
    worker.content_checked.connect(view.on_content_checked)
    worker.finished.connect(results.append)
    worker.failed.connect(lambda kind, side, message: pytest.fail(f"{kind}/{side}: {message}"))
    worker.run()  # direct call: signal connections on this thread are synchronous

    assert len(results) == 1
    root = results[0]
    statuses = {c.name: c.status for c in root.children}
    assert statuses == {
        "same.txt": Status.SAME,
        "only-left.txt": Status.LEFT_ONLY,
        "sub": Status.DIFFERENT,
    }

    view.set_result(root)
    proxy = view._proxy
    assert proxy.rowCount(QModelIndex()) == 3


def test_folder_view_filter_hides_same(app, folder_pair):
    from shankompare.ui.folder_model import FilterMode

    left, right = folder_pair
    view = FolderCompareView()
    worker = CompareWorker(LocalSide(str(left)), LocalSide(str(right)), CompareOptions())
    results = []
    worker.finished.connect(results.append)
    worker.run()
    view.set_result(results[0])

    view._proxy.set_mode(FilterMode.DIFFERENCES)
    names = {
        view._proxy.index(row, 0, QModelIndex()).data()
        for row in range(view._proxy.rowCount(QModelIndex()))
    }
    assert names == {"only-left.txt", "sub"}


def _start_text_worker_without_local_ref(parent, left, right, results, errors):
    """Mimics MainWindow._open_text_diff: no reference to the worker survives
    this function, which is exactly what regressed once (the worker was
    garbage-collected before its thread ran it)."""
    from shankompare.ui.worker import TextDiffWorker, start_worker

    worker = TextDiffWorker(LocalSide(str(left)), LocalSide(str(right)), "a.txt")
    worker.finished.connect(results.append)
    worker.failed.connect(errors.append)
    return start_worker(worker, parent, [worker.finished, worker.failed])


def test_text_worker_survives_gc_through_real_thread(app, tmp_path):
    import gc

    from PySide6.QtCore import QEventLoop, QObject, QTimer

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.txt").write_text("hello left")
    (right / "a.txt").write_text("hello right")

    parent = QObject()
    results: list = []
    errors: list = []
    thread = _start_text_worker_without_local_ref(parent, left, right, results, errors)
    gc.collect()  # would kill an unanchored worker

    loop = QEventLoop()
    thread.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)  # safety timeout
    if not thread.isFinished():
        loop.exec()
    thread.wait(5000)

    assert not errors
    assert len(results) == 1
    assert results[0].left.text == "hello left"
    assert results[0].right.text == "hello right"


def test_text_compare_view_renders(app):
    view = TextCompareView("left.txt", "right.txt")
    left = decode_bytes(b"one\ntwo\nthree\n")
    right = decode_bytes(b"one\nTWO\nthree\nfour\n")
    view.set_data(left, right)
    assert "difference" in view._status.text()
    assert view._left_pane.toPlainText().startswith("one")
    # only-differences mode
    view._only_diff.setChecked(True)
    assert "⋯" in view._left_pane.toPlainText() or view._left_pane.toPlainText()
