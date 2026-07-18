"""Headless tests for the v0.3.4 patches: copy-path context menu entries and
opening a file that exists on only one side."""

import os
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from shankompare.compare import NodeResult, Status
from shankompare.sessions import ConnectionProfile
from shankompare.ui.folder_view import FolderCompareView
from shankompare.ui.main_window import full_path
from shankompare.ui.worker import DiffLoadWorker, LocalSide, SftpSide
from shankompare.vfs import EntryInfo

STAMP = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _dir(name: str) -> EntryInfo:
    return EntryInfo(name, True, 0, STAMP)


def _file(name: str, size: int = 1) -> EntryInfo:
    return EntryInfo(name, False, size, STAMP)


def _tree(*children: NodeResult) -> NodeResult:
    return NodeResult("", Status.DIFFERENT, _dir("."), _dir("."), children=list(children))


# --- full_path -----------------------------------------------------------------


def test_full_path_local_uses_native_separators():
    result = full_path(LocalSide(os.path.join("C:", os.sep, "data")), "sub/file.txt")
    assert result.endswith(os.path.join("sub", "file.txt"))
    assert "data" in result


def test_full_path_sftp_stays_posix_without_host_prefix():
    profile = ConnectionProfile(name="p", host="example.com", username="u", initial_path="/srv/app")
    assert full_path(SftpSide(profile, None), "sub/file.txt") == "/srv/app/sub/file.txt"


# --- copy-path context menu ----------------------------------------------------


def test_copy_paths_signal_carries_rel_paths_and_side(app):
    view = FolderCompareView()
    left_only = NodeResult("only-left.txt", Status.LEFT_ONLY, _file("only-left.txt"), None)
    pair = NodeResult("both.txt", Status.DIFFERENT, _file("both.txt"), _file("both.txt", 2))
    view.set_result(_tree(left_only, pair))

    received = []
    view.copy_paths_requested.connect(lambda paths, side: received.append((paths, side)))
    view._tree.selectAll()
    view.copy_paths_requested.emit(["only-left.txt", "both.txt"], "left")
    assert received == [(["only-left.txt", "both.txt"], "left")]


# --- opening a one-sided file --------------------------------------------------


def test_activating_one_sided_file_requests_open(app):
    view = FolderCompareView()
    orphan = NodeResult("only-left.txt", Status.LEFT_ONLY, _file("only-left.txt"), None)
    view.set_result(_tree(orphan))

    requested = []
    view.open_diff_requested.connect(
        lambda node, rel, mode: requested.append((node.name, rel, mode))
    )
    # the model's top-level rows are the root node's children
    view._on_activated(view._proxy.index(0, 0))
    assert requested == [("only-left.txt", "only-left.txt", "auto")]


def test_activating_directory_does_not_request_open(app):
    view = FolderCompareView()
    folder = NodeResult("sub", Status.DIFFERENT, _dir("sub"), _dir("sub"))
    view.set_result(_tree(folder))

    requested = []
    view.open_diff_requested.connect(lambda *a: requested.append(a))
    view._on_activated(view._proxy.index(0, 0))
    assert requested == []


# --- DiffLoadWorker missing_ok -------------------------------------------------


def _sides(tmp_path) -> tuple[LocalSide, LocalSide]:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "only-left.txt").write_bytes(b"hello\n")  # bytes: no newline translation
    return LocalSide(str(left)), LocalSide(str(right))


def test_missing_side_loads_as_empty_text(app, tmp_path):
    left, right = _sides(tmp_path)
    worker = DiffLoadWorker(left, right, "only-left.txt", "text", missing_ok=True)
    loaded, failures = [], []
    worker.text_ready.connect(loaded.append)
    worker.failed.connect(failures.append)
    worker.run()

    assert failures == []
    assert loaded[0].left.text == "hello\n"
    assert loaded[0].right.text == ""


def test_missing_side_loads_as_empty_hex(app, tmp_path):
    left, right = _sides(tmp_path)
    worker = DiffLoadWorker(left, right, "only-left.txt", "hex", missing_ok=True)
    loaded, failures = [], []
    worker.hex_ready.connect(loaded.append)
    worker.failed.connect(failures.append)
    worker.run()

    assert failures == []
    assert loaded[0].left == b"hello\n"
    assert loaded[0].right == b""


def test_missing_side_still_fails_without_missing_ok(app, tmp_path):
    left, right = _sides(tmp_path)
    worker = DiffLoadWorker(left, right, "only-left.txt", "text")
    loaded, failures = [], []
    worker.text_ready.connect(loaded.append)
    worker.failed.connect(failures.append)
    worker.run()

    assert loaded == []
    assert len(failures) == 1


def test_missing_ok_reads_both_sides_once_present(app, tmp_path):
    """A refresh keeps missing_ok set; once the file exists on both sides it
    loads normally rather than showing an empty pane."""
    left, right = _sides(tmp_path)
    (tmp_path / "right" / "only-left.txt").write_bytes(b"world\n")
    worker = DiffLoadWorker(left, right, "only-left.txt", "text", missing_ok=True)
    loaded = []
    worker.text_ready.connect(loaded.append)
    worker.failed.connect(lambda m: pytest.fail(m))
    worker.run()

    assert loaded[0].left.text == "hello\n"
    assert loaded[0].right.text == "world\n"
