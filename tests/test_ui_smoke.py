"""Headless UI smoke test: builds the main window and runs one real compare
through the worker (local ↔ local) with signals delivered on this thread."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from shankompare.compare import CompareOptions, Status
from shankompare.ui.main_window import MainWindow
from shankompare.ui.worker import CompareWorker, LocalSide


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_main_window_constructs(app):
    window = MainWindow()
    window.show()
    window.close()


def test_worker_compares_local_folders(app, tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "same.txt").write_text("same")
    (right / "same.txt").write_text("same")
    (left / "only-left.txt").write_text("x")

    worker = CompareWorker(LocalSide(str(left)), LocalSide(str(right)), CompareOptions())
    results = []
    worker.finished.connect(results.append)
    worker.failed.connect(lambda message: pytest.fail(message))
    worker.run()  # direct call: signal connections on this thread are synchronous

    assert len(results) == 1
    statuses = {c.name: c.status for c in results[0].children}
    assert statuses == {"same.txt": Status.SAME, "only-left.txt": Status.LEFT_ONLY}
