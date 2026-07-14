import threading
from datetime import UTC, datetime

import pytest

from shankompare.compare import (
    CompareCancelled,
    CompareDone,
    CompareOptions,
    ContentChecked,
    ContentMode,
    DirScanned,
    NodeResult,
    Status,
    compare_folders,
)
from shankompare.vfs import InMemoryFileSystem, VfsPermissionError

STAMP = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

# Tree specs are nested dicts: bytes = file content, dict = subdirectory.
TreeSpec = dict


def make_fs(spec: TreeSpec) -> InMemoryFileSystem:
    fs = InMemoryFileSystem()
    _build(fs, spec, "")
    _stamp_all(fs, "")
    return fs


def _build(fs: InMemoryFileSystem, spec: TreeSpec, base: str) -> None:
    for name, value in spec.items():
        path = f"{base}/{name}" if base else name
        if isinstance(value, dict):
            fs.mkdir(path)
            _build(fs, value, path)
        else:
            with fs.open_write(path) as f:
                f.write(value)


def _stamp_all(fs: InMemoryFileSystem, base: str) -> None:
    for entry in fs.listdir(base or "."):
        path = f"{base}/{entry.name}" if base else entry.name
        fs.set_mtime(path, STAMP)
        if entry.is_dir:
            _stamp_all(fs, path)


def run_compare(left, right, options=None) -> NodeResult:
    events = list(compare_folders(left, right, options))
    assert isinstance(events[-1], CompareDone)
    return events[-1].root


def find(root: NodeResult, path: str) -> NodeResult:
    node = root
    for part in path.split("/"):
        node = next(c for c in node.children if c.name == part)
    return node


def test_identical_trees_are_same():
    spec = {"a.txt": b"one", "sub": {"b.txt": b"two"}}
    root = run_compare(make_fs(spec), make_fs(spec))
    assert root.status is Status.SAME
    assert find(root, "a.txt").status is Status.SAME
    assert find(root, "sub").status is Status.SAME
    assert find(root, "sub/b.txt").status is Status.SAME


def test_empty_trees_are_same():
    root = run_compare(make_fs({}), make_fs({}))
    assert root.status is Status.SAME
    assert root.children == []


def test_size_difference():
    root = run_compare(make_fs({"a.txt": b"short"}), make_fs({"a.txt": b"longer text"}))
    assert find(root, "a.txt").status is Status.DIFFERENT
    assert root.status is Status.DIFFERENT


def test_mtime_difference_beyond_tolerance():
    left = make_fs({"a.txt": b"x"})
    right = make_fs({"a.txt": b"x"})
    right.set_mtime("a.txt", datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC))
    root = run_compare(left, right)
    assert find(root, "a.txt").status is Status.DIFFERENT


def test_mtime_difference_within_tolerance_is_same():
    left = make_fs({"a.txt": b"x"})
    right = make_fs({"a.txt": b"x"})
    right.set_mtime("a.txt", datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC))
    root = run_compare(left, right, CompareOptions(mtime_tolerance=2.0))
    assert find(root, "a.txt").status is Status.SAME


def test_orphans():
    left = make_fs({"only-left.txt": b"x", "both.txt": b"y"})
    right = make_fs({"both.txt": b"y", "only-right": {"inner.txt": b"z"}})
    root = run_compare(left, right)
    assert find(root, "only-left.txt").status is Status.LEFT_ONLY
    assert find(root, "only-right").status is Status.RIGHT_ONLY
    assert find(root, "only-right/inner.txt").status is Status.RIGHT_ONLY
    assert find(root, "both.txt").status is Status.SAME


def test_dir_vs_file_mismatch():
    root = run_compare(make_fs({"thing": {}}), make_fs({"thing": b"a file"}))
    node = find(root, "thing")
    assert node.status is Status.DIFFERENT
    assert node.error is not None


@pytest.mark.parametrize("mode", [ContentMode.CRC32, ContentMode.BYTES])
def test_content_difference_with_equal_size_and_mtime(mode):
    left = make_fs({"a.bin": b"AAAA"})
    right = make_fs({"a.bin": b"AAAB"})
    options = CompareOptions(content=mode)
    root = run_compare(left, right, options)
    assert find(root, "a.bin").status is Status.DIFFERENT


@pytest.mark.parametrize("mode", [ContentMode.CRC32, ContentMode.BYTES])
def test_content_equal(mode):
    left = make_fs({"a.bin": b"same bytes"})
    right = make_fs({"a.bin": b"same bytes"})
    root = run_compare(left, right, CompareOptions(content=mode))
    assert find(root, "a.bin").status is Status.SAME


def test_content_pass_skipped_when_size_already_differs():
    left = make_fs({"a.bin": b"tiny"})
    right = make_fs({"a.bin": b"much larger"})
    events = list(compare_folders(left, right, CompareOptions(content=ContentMode.BYTES)))
    assert not [e for e in events if isinstance(e, ContentChecked)]


def test_case_insensitive_alignment():
    left = make_fs({"README.txt": b"x"})
    right = make_fs({"readme.txt": b"x"})
    root = run_compare(left, right, CompareOptions(case_sensitive=False))
    assert len(root.children) == 1
    assert root.children[0].status is Status.SAME

    root = run_compare(left, right, CompareOptions(case_sensitive=True))
    statuses = {c.name: c.status for c in root.children}
    assert statuses == {"README.txt": Status.LEFT_ONLY, "readme.txt": Status.RIGHT_ONLY}


def test_events_stream_per_directory():
    spec = {"sub1": {"a.txt": b"x"}, "sub2": {}}
    events = list(compare_folders(make_fs(spec), make_fs(spec)))
    scanned = [str(e.path) for e in events if isinstance(e, DirScanned)]
    assert scanned == [".", "sub1", "sub2"]


def test_cancellation():
    cancel = threading.Event()
    cancel.set()
    gen = compare_folders(make_fs({"a.txt": b"x"}), make_fs({}), cancel=cancel)
    with pytest.raises(CompareCancelled):
        next(gen)


class _FailingListdirFs(InMemoryFileSystem):
    def __init__(self, fail_path: str):
        super().__init__()
        self._fail_path = fail_path

    def listdir(self, path="."):
        if str(path) == self._fail_path:
            raise VfsPermissionError(f"permission denied: {path}")
        return super().listdir(path)


def test_listdir_error_marks_node_and_compare_continues():
    spec = {"locked": {}, "ok.txt": b"x"}
    left = _FailingListdirFs("locked")
    _build(left, spec, "")
    right = make_fs(spec)
    root = run_compare(left, right)
    locked = find(root, "locked")
    assert locked.status is Status.UNKNOWN
    assert "permission denied" in (locked.error or "")
    assert find(root, "ok.txt").status is not None  # walk completed
