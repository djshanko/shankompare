import threading
from datetime import UTC, datetime

import pytest

from shankompare.vfs import InMemoryFileSystem, VfsNotFound
from shankompare.vfs.ops import FileOp, OpKind, OpsCancelled, copy_entry, delete_entry, execute_op

STAMP = datetime(2021, 3, 4, 5, 6, 7, tzinfo=UTC)


def _fs_with(spec: dict, base: str = "") -> InMemoryFileSystem:
    fs = InMemoryFileSystem()
    _build(fs, spec, base)
    return fs


def _build(fs, spec, base):
    for name, value in spec.items():
        path = f"{base}/{name}" if base else name
        if isinstance(value, dict):
            fs.mkdir(path)
            _build(fs, value, path)
        else:
            with fs.open_write(path) as f:
                f.write(value)
            fs.set_mtime(path, STAMP)


def _read(fs, path) -> bytes:
    with fs.open_read(path) as f:
        return f.read()


def test_copy_file_preserves_content_and_mtime():
    src = _fs_with({"a.txt": b"payload"})
    dst = InMemoryFileSystem()
    copy_entry(src, dst, "a.txt")
    assert _read(dst, "a.txt") == b"payload"
    assert dst.stat("a.txt").mtime == STAMP


def test_copy_tree_recursive():
    src = _fs_with({"dir": {"inner": {"deep.txt": b"deep"}, "top.txt": b"top"}})
    dst = InMemoryFileSystem()
    copy_entry(src, dst, "dir")
    assert _read(dst, "dir/inner/deep.txt") == b"deep"
    assert _read(dst, "dir/top.txt") == b"top"


def test_copy_creates_missing_parent_dirs():
    src = _fs_with({"a": {"b": {"c.txt": b"x"}}})
    dst = InMemoryFileSystem()
    copy_entry(src, dst, "a/b/c.txt")
    assert _read(dst, "a/b/c.txt") == b"x"


def test_copy_overwrites_existing_file():
    src = _fs_with({"a.txt": b"new content"})
    dst = _fs_with({"a.txt": b"old"})
    copy_entry(src, dst, "a.txt")
    assert _read(dst, "a.txt") == b"new content"


def test_delete_tree():
    fs = _fs_with({"dir": {"inner": {"deep.txt": b"x"}, "top.txt": b"y"}, "keep.txt": b"z"})
    delete_entry(fs, "dir")
    assert not fs.exists("dir")
    assert fs.exists("keep.txt")


def test_cancel_raises():
    src = _fs_with({"a.txt": b"x"})
    dst = InMemoryFileSystem()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(OpsCancelled):
        copy_entry(src, dst, "a.txt", cancel=cancel)


def test_execute_rename_on_both_sides():
    left = _fs_with({"dir": {"old.txt": b"L"}})
    right = _fs_with({"dir": {"old.txt": b"R"}})
    execute_op(left, right, FileOp(OpKind.RENAME, "dir/old.txt", new_name="new.txt"))
    assert _read(left, "dir/new.txt") == b"L"
    assert _read(right, "dir/new.txt") == b"R"
    assert not left.exists("dir/old.txt")


def test_execute_rename_skips_missing_side():
    left = _fs_with({"only-left.txt": b"L"})
    right = InMemoryFileSystem()
    execute_op(left, right, FileOp(OpKind.RENAME, "only-left.txt", new_name="renamed.txt"))
    assert left.exists("renamed.txt")


def test_execute_mtime_sync():
    left = _fs_with({"a.txt": b"same"})
    right = _fs_with({"a.txt": b"same"})
    other = datetime(2022, 1, 1, tzinfo=UTC)
    right.set_mtime("a.txt", other)
    execute_op(left, right, FileOp(OpKind.MTIME_LTR, "a.txt"))
    assert right.stat("a.txt").mtime == STAMP


def test_execute_delete_right():
    left = _fs_with({"a.txt": b"x"})
    right = _fs_with({"a.txt": b"x"})
    execute_op(left, right, FileOp(OpKind.DELETE_RIGHT, "a.txt"))
    assert left.exists("a.txt")
    assert not right.exists("a.txt")


def test_copy_missing_source_raises():
    with pytest.raises(VfsNotFound):
        copy_entry(InMemoryFileSystem(), InMemoryFileSystem(), "nope.txt")


def test_progress_messages():
    src = _fs_with({"a.txt": b"x"})
    messages = []
    copy_entry(src, InMemoryFileSystem(), "a.txt", progress=messages.append)
    assert any("a.txt" in m for m in messages)
