"""Headless UI smoke tests: main window construction, a real compare streamed
through the worker into the folder view, and the text compare view."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication, QDialog

from shankompare.compare import CompareOptions, Status, decode_bytes
from shankompare.ui.folder_model import FILTERABLE_STATUSES
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


def _top_level_names(view):
    return {
        view._proxy.index(row, 0, QModelIndex()).data()
        for row in range(view._proxy.rowCount(QModelIndex()))
    }


def _compared_view(folder_pair):
    left, right = folder_pair
    view = FolderCompareView()
    worker = CompareWorker(LocalSide(str(left)), LocalSide(str(right)), CompareOptions())
    results = []
    worker.finished.connect(results.append)
    worker.run()
    view.set_result(results[0])
    return view


def test_folder_view_filter_hides_same(app, folder_pair):
    view = _compared_view(folder_pair)
    view._proxy.set_statuses(frozenset({Status.DIFFERENT, Status.LEFT_ONLY, Status.RIGHT_ONLY}))
    assert _top_level_names(view) == {"only-left.txt", "sub"}


def test_folder_view_filter_selects_multiple_statuses(app, folder_pair):
    view = _compared_view(folder_pair)

    # a single category: "sub" survives only because its child is DIFFERENT
    view._proxy.set_statuses(frozenset({Status.LEFT_ONLY}))
    assert _top_level_names(view) == {"only-left.txt"}

    view._proxy.set_statuses(frozenset({Status.SAME, Status.LEFT_ONLY}))
    assert _top_level_names(view) == {"same.txt", "only-left.txt"}

    view._proxy.set_statuses(FILTERABLE_STATUSES)
    assert _top_level_names(view) == {"same.txt", "only-left.txt", "sub"}

    view._proxy.set_statuses(frozenset())
    assert _top_level_names(view) == set()


def test_folder_view_filter_menu_drives_proxy(app, folder_pair):
    view = _compared_view(folder_pair)
    assert view._filter_btn.text() == "Show: All"

    view._filter_actions[Status.SAME].setChecked(False)  # fires toggled
    assert _top_level_names(view) == {"only-left.txt", "sub"}
    assert view._filter_btn.text() == "Show: Differences"

    view._filter_select_all()
    assert all(action.isChecked() for action in view._filter_actions.values())
    assert view._filter_btn.text() == "Show: All"

    view._filter_select_differences()
    assert not view._filter_actions[Status.SAME].isChecked()
    assert all(
        view._filter_actions[status].isChecked()
        for status in (Status.DIFFERENT, Status.LEFT_ONLY, Status.RIGHT_ONLY)
    )

    view._filter_select_all()
    view._filter_actions[Status.DIFFERENT].setChecked(False)
    assert view._filter_btn.text() == "Show: Unchanged + Left orphans + Right orphans"


def test_folder_view_filter_keeps_unscanned_rows_visible(app, folder_pair):
    """Rows still being compared show under every filter, so streaming results
    never blink out of the tree mid-scan."""
    from shankompare.compare import NodeResult
    from shankompare.ui.folder_model import FolderCompareModel

    view = FolderCompareView()
    root = NodeResult(name="", status=Status.UNKNOWN)
    root.children.append(NodeResult(name="pending.txt", status=Status.UNKNOWN))
    view.set_result(root)

    view._proxy.set_statuses(frozenset({Status.LEFT_ONLY}))
    assert _top_level_names(view) == {"pending.txt"}
    assert isinstance(view._model, FolderCompareModel)


def test_save_session_dialog_lists_and_labels(app):
    from shankompare.ui.session_dialog import SaveSessionDialog

    dialog = SaveSessionDialog(["nightly", "release"])
    ok = dialog._ok_button()
    assert not ok.isEnabled()  # nothing typed yet
    assert [dialog._list.item(row).text() for row in range(dialog._list.count())] == [
        "nightly",
        "release",
    ]

    dialog._name_edit.setText("nightly")
    assert ok.isEnabled() and ok.text() == "Overwrite"

    dialog._name_edit.setText("fresh")
    assert ok.isEnabled() and ok.text() == "Save"

    dialog._name_edit.setText("   ")
    assert not ok.isEnabled()

    dialog._list.setCurrentRow(1)  # picking from the list fills the name
    assert dialog.session_name() == "release"
    assert ok.text() == "Overwrite"


def test_save_session_dialog_confirms_overwrite(app, monkeypatch):
    from shankompare.ui import session_dialog as module
    from shankompare.ui.session_dialog import SaveSessionDialog

    asked: list[str] = []

    def answer(button):
        def question(_parent, _title, text):
            asked.append(text)
            return button

        return question

    dialog = SaveSessionDialog(["nightly"])
    dialog._name_edit.setText("nightly")

    monkeypatch.setattr(
        module.QMessageBox, "question", answer(module.QMessageBox.StandardButton.No)
    )
    dialog._on_accept()
    assert dialog.result() != QDialog.DialogCode.Accepted  # stays open for another name
    assert asked == ["Overwrite session 'nightly'?"]

    monkeypatch.setattr(
        module.QMessageBox, "question", answer(module.QMessageBox.StandardButton.Yes)
    )
    dialog._on_accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_save_session_dialog_skips_confirm_for_new_name(app, monkeypatch):
    from shankompare.ui import session_dialog as module
    from shankompare.ui.session_dialog import SaveSessionDialog

    def refuse(*args, **kwargs):
        pytest.fail("a new session name must not prompt for overwrite")

    monkeypatch.setattr(module.QMessageBox, "question", refuse)
    dialog = SaveSessionDialog(["nightly"])
    dialog._name_edit.setText("fresh")
    dialog._on_accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def _start_text_worker_without_local_ref(parent, left, right, results, errors):
    """Mimics MainWindow._start_diff_load: no reference to the worker survives
    this function, which is exactly what regressed once (the worker was
    garbage-collected before its thread ran it)."""
    from shankompare.ui.worker import DiffLoadWorker, start_worker

    worker = DiffLoadWorker(LocalSide(str(left)), LocalSide(str(right)), "a.txt")
    worker.text_ready.connect(results.append)
    worker.failed.connect(errors.append)
    return start_worker(worker, parent, [worker.text_ready, worker.hex_ready, worker.failed])


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


def test_diff_result_is_delivered_on_the_ui_thread(app, tmp_path):
    """Worker signals must reach the view as queued slot calls on the GUI
    thread. Regression: connecting them to lambdas ran set_data() on the
    worker thread, crashing the app intermittently on local↔SFTP diffs."""
    from PySide6.QtCore import QEventLoop, QThread, QTimer

    from shankompare.ui.worker import DiffLoadWorker, start_worker

    class ThreadRecordingView(TextCompareView):
        delivery_thread = None

        def on_diff_loaded(self, data):
            self.delivery_thread = QThread.currentThread()
            super().on_diff_loaded(data)

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.txt").write_text("one")
    (right / "a.txt").write_text("two")

    view = ThreadRecordingView("l", "r")
    worker = DiffLoadWorker(LocalSide(str(left)), LocalSide(str(right)), "a.txt")
    worker.text_ready.connect(view.on_diff_loaded)
    worker.failed.connect(view.show_error)
    thread = start_worker(worker, view, [worker.text_ready, worker.hex_ready, worker.failed])

    loop = QEventLoop()
    thread.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    if not thread.isFinished():
        loop.exec()
    thread.wait(5000)
    app.processEvents()  # flush the queued delivery

    assert view.delivery_thread is app.thread()
    assert view._left_data is not None and view._left_data.text == "one"


def test_text_compare_shows_current_line_marker(app):
    view = TextCompareView("l", "r")
    view.set_data(decode_bytes(b"same\ntext"), decode_bytes(b"same\ntext"))
    # even with zero diffs, each pane carries the current-line highlight
    assert len(view._left_pane.extraSelections()) == 1
    assert len(view._right_pane.extraSelections()) == 1
    view.set_data(decode_bytes(b"a\nb"), decode_bytes(b"a\nB"))
    assert len(view._left_pane.extraSelections()) > 1  # diff highlights + marker


def test_text_edit_mode_recompare_and_copy_section(app):
    from PySide6.QtGui import QTextCursor

    view = TextCompareView("left.txt", "right.txt")
    view.set_data(decode_bytes(b"one\ntwo\nthree"), decode_bytes(b"one\ntwo\nthree"))
    assert "identical" in view._status.text()

    view._edit_check.setChecked(True)
    view._left_pane.setPlainText("one\nCHANGED\nthree")  # simulate a user edit
    view._on_edited()  # bypass the debounce timer
    assert view._dirty["left"]
    assert "1 difference" in view._status.text()

    # copy the changed section left -> right
    cursor = QTextCursor(view._left_pane.document().findBlockByNumber(1))
    view._left_pane.setTextCursor(cursor)
    view._copy_section("ltr")
    assert view._right_data.text == "one\nCHANGED\nthree"
    assert view._dirty["right"]

    # saving emits the encoded bytes
    saved = []
    view.save_requested.connect(lambda side, data: saved.append((side, data)))
    view._save("right")
    assert saved == [("right", b"one\nCHANGED\nthree")]
    view.mark_saved("right")
    assert not view._dirty["right"]


def test_text_dirty_signal_and_undo(app):
    view = TextCompareView("left.txt", "right.txt")
    view.set_data(decode_bytes(b"one\ntwo\nthree"), decode_bytes(b"one\ntwo\nthree"))

    dirty_states: list[bool] = []
    view.dirty_changed.connect(dirty_states.append)

    view._edit_check.setChecked(True)
    assert view._undo_btn.isEnabled() and view._redo_btn.isEnabled()
    assert not view.has_unsaved_changes()

    # an interactive insert (undoable, unlike setPlainText) at end of the pane
    from PySide6.QtGui import QTextCursor

    cursor = view._left_pane.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    view._left_pane.setTextCursor(cursor)
    view._left_pane.insertPlainText(" EXTRA")
    view._on_edited()
    assert view.has_unsaved_changes()
    assert dirty_states == [True]  # a single edge, not one per keystroke

    # undo targets the focused pane and restores its content
    view._left_pane.setFocus()
    view._undo()
    assert view._left_pane.toPlainText() == "one\ntwo\nthree"

    # saving clears the dirty state and emits the falling edge
    view.mark_saved("left")
    assert not view.has_unsaved_changes()
    assert dirty_states == [True, False]


def test_text_tab_star_tracks_unsaved(app, tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.txt").write_text("one")
    (right / "a.txt").write_text("two")

    window = MainWindow()
    window._sides = (LocalSide(str(left)), LocalSide(str(right)))
    view = TextCompareView("Left: a.txt", "Right: a.txt")
    view.dirty_changed.connect(lambda dirty, v=view: window._set_tab_dirty(v, dirty))
    index = window._tabs.addTab(view, "a.txt")
    view.set_data(decode_bytes(b"one"), decode_bytes(b"two"))

    view._edit_check.setChecked(True)
    view._left_pane.setPlainText("edited")
    view._on_edited()
    assert window._tabs.tabText(index) == "* a.txt"

    view.mark_saved("left")
    assert window._tabs.tabText(index) == "a.txt"
    window.close()


def test_file_ops_worker_copy_and_delete(app, tmp_path):
    from shankompare.ui.worker import FileOpsWorker
    from shankompare.vfs.ops import FileOp, OpKind

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "new.txt").write_text("payload")
    (right / "obsolete.txt").write_text("x")

    worker = FileOpsWorker(
        LocalSide(str(left)),
        LocalSide(str(right)),
        [FileOp(OpKind.COPY_LTR, "new.txt"), FileOp(OpKind.DELETE_RIGHT, "obsolete.txt")],
    )
    results = []
    worker.finished.connect(lambda completed, errors: results.append((completed, errors)))
    worker.failed.connect(lambda message: pytest.fail(message))
    worker.run()

    assert results == [(2, [])]
    assert (right / "new.txt").read_text() == "payload"
    assert not (right / "obsolete.txt").exists()
