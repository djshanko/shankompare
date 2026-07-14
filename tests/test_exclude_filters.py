from datetime import UTC, datetime

import pytest
from test_folder_compare import STAMP, find, make_fs, run_compare

from shankompare.compare import CompareOptions, ExcludeFilters, parse_size


def test_parse_size():
    assert parse_size("") is None
    assert parse_size("  ") is None
    assert parse_size("123") == 123
    assert parse_size("10k") == 10 * 1024
    assert parse_size("10K") == 10 * 1024
    assert parse_size("2M") == 2 * 1024**2
    assert parse_size("1g") == 1024**3
    assert parse_size("1.5k") == 1536
    assert parse_size("100b") == 100
    assert parse_size("10MiB") == 10 * 1024**2


@pytest.mark.parametrize("bad", ["abc", "-5", "10x", "k"])
def test_parse_size_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_size(bad)


def test_name_glob_excludes_files_and_dirs():
    spec = {"keep.txt": b"x", "skip.log": b"y", "__pycache__": {"a.pyc": b"z"}}
    left = make_fs(spec)
    right = make_fs({"keep.txt": b"x"})
    options = CompareOptions(exclude=ExcludeFilters(name_globs=("*.log", "__pycache__")))
    root = run_compare(left, right, options)
    assert [c.name for c in root.children] == ["keep.txt"]
    assert root.status.value == "same"


def test_name_glob_is_case_insensitive():
    left = make_fs({"README.LOG": b"x"})
    right = make_fs({})
    options = CompareOptions(exclude=ExcludeFilters(name_globs=("*.log",)))
    root = run_compare(left, right, options)
    assert root.children == []


def test_size_range_applies_to_files_only():
    left = make_fs({"small.txt": b"x", "big.txt": b"x" * 100, "dir": {"inner.txt": b"ok" * 10}})
    right = make_fs({"small.txt": b"x", "big.txt": b"x" * 100, "dir": {"inner.txt": b"ok" * 10}})
    options = CompareOptions(exclude=ExcludeFilters(min_size=5, max_size=50))
    root = run_compare(left, right, options)
    names = [c.name for c in root.children]
    assert names == ["dir"]  # small/big filtered; dir passes size bounds
    assert find(root, "dir/inner.txt").name == "inner.txt"


def test_mtime_window():
    left = make_fs({"old.txt": b"x", "new.txt": b"y"})
    right = make_fs({"old.txt": b"x", "new.txt": b"y"})
    left.set_mtime("old.txt", datetime(2020, 1, 1, tzinfo=UTC))
    right.set_mtime("old.txt", datetime(2020, 1, 1, tzinfo=UTC))
    cutoff = STAMP.replace(year=STAMP.year - 1)
    options = CompareOptions(exclude=ExcludeFilters(modified_after=cutoff))
    root = run_compare(left, right, options)
    assert [c.name for c in root.children] == ["new.txt"]


def test_excluded_orphan_does_not_flag_parent():
    left = make_fs({"data": {"real.txt": b"x", "junk.tmp": b"t"}})
    right = make_fs({"data": {"real.txt": b"x"}})
    options = CompareOptions(exclude=ExcludeFilters(name_globs=("*.tmp",)))
    root = run_compare(left, right, options)
    assert find(root, "data").status.value == "same"
