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
    # With the skip shortcut off, matching size+mtime still gets a content read,
    # so a same-size, same-mtime but different-content pair is caught.
    left = make_fs({"a.bin": b"AAAA"})
    right = make_fs({"a.bin": b"AAAB"})
    options = CompareOptions(content=mode, skip_content_if_metadata_matches=False)
    root = run_compare(left, right, options)
    assert find(root, "a.bin").status is Status.DIFFERENT


@pytest.mark.parametrize("mode", [ContentMode.CRC32, ContentMode.BYTES])
def test_content_equal(mode):
    left = make_fs({"a.bin": b"same bytes"})
    right = make_fs({"a.bin": b"same bytes"})
    options = CompareOptions(content=mode, skip_content_if_metadata_matches=False)
    root = run_compare(left, right, options)
    assert find(root, "a.bin").status is Status.SAME


def test_content_pass_skipped_when_size_already_differs():
    left = make_fs({"a.bin": b"tiny"})
    right = make_fs({"a.bin": b"much larger"})
    events = list(compare_folders(left, right, CompareOptions(content=ContentMode.BYTES)))
    assert not [e for e in events if isinstance(e, ContentChecked)]


def test_content_read_when_only_mtime_differs_reports_same():
    # Same size and bytes but a mtime beyond tolerance: the mtime difference
    # alone must not report DIFFERENT — content is read and confirms SAME.
    left = make_fs({"a.bin": b"identical"})
    right = make_fs({"a.bin": b"identical"})
    right.set_mtime("a.bin", datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC))
    options = CompareOptions(content=ContentMode.BYTES)  # skip shortcut on (default)
    events = list(compare_folders(left, right, options))
    assert [e for e in events if isinstance(e, ContentChecked)]  # it was read
    assert find(events[-1].root, "a.bin").status is Status.SAME


def test_skip_shortcut_takes_matching_metadata_as_equal_without_reading():
    # Size and mtime agree, but the bytes differ: with the skip shortcut on
    # (default) the pair is taken as SAME and never read.
    left = make_fs({"a.bin": b"AAAA"})
    right = make_fs({"a.bin": b"AAAB"})  # same size + mtime, different bytes
    events = list(compare_folders(left, right, CompareOptions(content=ContentMode.BYTES)))
    assert not [e for e in events if isinstance(e, ContentChecked)]
    assert find(events[-1].root, "a.bin").status is Status.SAME


def test_content_read_when_mtime_off_and_size_matches():
    # Modified time not a criterion: content is authoritative, so same-size
    # pairs are read regardless of mtime, and equal bytes report SAME.
    left = make_fs({"a.bin": b"same"})
    right = make_fs({"a.bin": b"same"})
    right.set_mtime("a.bin", datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC))
    options = CompareOptions(use_mtime=False, content=ContentMode.BYTES)
    events = list(compare_folders(left, right, options))
    assert [e for e in events if isinstance(e, ContentChecked)]
    assert find(events[-1].root, "a.bin").status is Status.SAME


def test_content_gated_by_size_even_when_size_check_off():
    # Size checkbox off, but content only reads pairs whose size matches;
    # a size mismatch is DIFFERENT without a content pass.
    left = make_fs({"a.bin": b"tiny"})
    right = make_fs({"a.bin": b"much larger"})
    options = CompareOptions(use_size=False, content=ContentMode.BYTES)
    events = list(compare_folders(left, right, options))
    assert not [e for e in events if isinstance(e, ContentChecked)]
    assert find(events[-1].root, "a.bin").status is Status.DIFFERENT


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


def _rewrite(fs: InMemoryFileSystem, path: str, content: bytes, mtime=STAMP) -> None:
    with fs.open_write(path) as f:
        f.write(content)
    fs.set_mtime(path, mtime)


def test_baseline_reuse_skips_unchanged_file():
    # Identical files → SAME baseline. Then change the left bytes but keep its
    # size and mtime; a refresh with the baseline must reuse SAME (no re-read),
    # while a plain compare would notice the byte difference.
    left = make_fs({"a.bin": b"AAAA"})
    right = make_fs({"a.bin": b"AAAA"})
    options = CompareOptions(content=ContentMode.BYTES, skip_content_if_metadata_matches=False)
    baseline = run_compare(left, right, options)
    assert find(baseline, "a.bin").status is Status.SAME

    _rewrite(left, "a.bin", b"BBBB")  # same size + mtime, different bytes

    refreshed = list(compare_folders(left, right, options, baseline=baseline))[-1].root
    assert find(refreshed, "a.bin").status is Status.SAME  # reused, content not re-read

    fresh = run_compare(left, right, options)
    assert find(fresh, "a.bin").status is Status.DIFFERENT  # a full compare sees it


def test_baseline_reuse_rechecks_modified_file():
    # A file whose mtime changed since the baseline is compared afresh.
    later = datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC)
    left = make_fs({"a.bin": b"AAAA"})
    right = make_fs({"a.bin": b"AAAB"})
    options = CompareOptions(content=ContentMode.BYTES, skip_content_if_metadata_matches=False)
    baseline = run_compare(left, right, options)
    assert find(baseline, "a.bin").status is Status.DIFFERENT

    _rewrite(left, "a.bin", b"AAAB", mtime=later)  # now equal content
    _rewrite(right, "a.bin", b"AAAB", mtime=later)

    events = list(compare_folders(left, right, options, baseline=baseline))
    root = events[-1].root
    assert find(root, "a.bin").status is Status.SAME
    # it went through the content pass rather than being reused
    assert any(isinstance(e, ContentChecked) and str(e.path) == "a.bin" for e in events)


def test_baseline_reuse_handles_new_and_removed_files():
    left = make_fs({"keep.bin": b"AAAA", "gone.bin": b"XXXX"})
    right = make_fs({"keep.bin": b"AAAA"})
    options = CompareOptions(content=ContentMode.BYTES)
    baseline = run_compare(left, right, options)

    _rewrite(right, "added.bin", b"YYYY")  # appears only after the baseline

    root = list(compare_folders(left, right, options, baseline=baseline))[-1].root
    assert find(root, "keep.bin").status is Status.SAME  # reused
    assert find(root, "gone.bin").status is Status.LEFT_ONLY
    assert find(root, "added.bin").status is Status.RIGHT_ONLY


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
