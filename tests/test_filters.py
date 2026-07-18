from datetime import UTC, datetime

import pytest
from test_folder_compare import STAMP, find, make_fs, run_compare

from shankompare.compare import (
    CompareFilters,
    CompareOptions,
    format_globs,
    parse_globs,
    parse_size,
)


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
    options = CompareOptions(filters=CompareFilters(exclude_globs=("*.log", "__pycache__")))
    root = run_compare(left, right, options)
    assert [c.name for c in root.children] == ["keep.txt"]
    assert root.status.value == "same"


def test_name_glob_is_case_insensitive():
    left = make_fs({"README.LOG": b"x"})
    right = make_fs({})
    options = CompareOptions(filters=CompareFilters(exclude_globs=("*.log",)))
    root = run_compare(left, right, options)
    assert root.children == []


def test_size_range_applies_to_files_only():
    left = make_fs({"small.txt": b"x", "big.txt": b"x" * 100, "dir": {"inner.txt": b"ok" * 10}})
    right = make_fs({"small.txt": b"x", "big.txt": b"x" * 100, "dir": {"inner.txt": b"ok" * 10}})
    options = CompareOptions(filters=CompareFilters(min_size=5, max_size=50))
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
    options = CompareOptions(filters=CompareFilters(modified_after=cutoff))
    root = run_compare(left, right, options)
    assert [c.name for c in root.children] == ["new.txt"]


def test_include_globs_keep_only_matching_files():
    spec = {"a.py": b"x", "notes.txt": b"y", "pkg": {"b.py": b"z", "data.bin": b"w"}}
    left = make_fs(spec)
    right = make_fs(spec)
    options = CompareOptions(filters=CompareFilters(include_globs=("*.py",)))
    root = run_compare(left, right, options)
    # folders always pass so subtrees are still walked
    assert [c.name for c in root.children] == ["a.py", "pkg"]
    assert [c.name for c in find(root, "pkg").children] == ["b.py"]


def test_empty_include_globs_include_everything():
    spec = {"a.py": b"x", "notes.txt": b"y"}
    root = run_compare(make_fs(spec), make_fs(spec), CompareOptions(filters=CompareFilters()))
    assert [c.name for c in root.children] == ["a.py", "notes.txt"]


def test_exclude_wins_over_include():
    spec = {"keep.py": b"x", "generated.py": b"y"}
    options = CompareOptions(
        filters=CompareFilters(include_globs=("*.py",), exclude_globs=("generated.*",))
    )
    root = run_compare(make_fs(spec), make_fs(spec), options)
    assert [c.name for c in root.children] == ["keep.py"]


def test_include_glob_is_case_insensitive():
    spec = {"README.PY": b"x"}
    options = CompareOptions(filters=CompareFilters(include_globs=("*.py",)))
    root = run_compare(make_fs(spec), make_fs(spec), options)
    assert [c.name for c in root.children] == ["README.PY"]


def test_include_glob_orphan_filtered_does_not_flag_parent():
    left = make_fs({"data": {"real.py": b"x", "junk.txt": b"t"}})
    right = make_fs({"data": {"real.py": b"x"}})
    options = CompareOptions(filters=CompareFilters(include_globs=("*.py",)))
    root = run_compare(left, right, options)
    assert find(root, "data").status.value == "same"


def test_parse_globs_separators_and_quotes():
    assert parse_globs("") == ()
    assert parse_globs("   ") == ()
    assert parse_globs("*.log,*.tmp; __pycache__") == ("*.log", "*.tmp", "__pycache__")
    assert parse_globs('*.log "My Documents" *.tmp') == ("*.log", "My Documents", "*.tmp")
    assert parse_globs('"weekly report*.xlsx"') == ("weekly report*.xlsx",)
    # a quoted pattern may itself contain the separators
    assert parse_globs('"a,b;c d"') == ("a,b;c d",)


def test_parse_globs_unclosed_quote_is_literal():
    assert parse_globs('"unclosed *.log') == ('"unclosed', "*.log")


@pytest.mark.parametrize(
    "globs",
    [
        ("*.log", "__pycache__"),
        ("My Documents", "*.tmp"),
        ("weekly report*.xlsx",),
        ("a,b", "c;d"),
        (),
    ],
)
def test_format_globs_roundtrips(globs):
    assert parse_globs(format_globs(globs)) == globs


def test_format_globs_only_quotes_when_needed():
    assert format_globs(("*.log", "My Documents")) == '*.log "My Documents"'


def test_whitespace_glob_matches_end_to_end():
    spec = {"My Documents": {"a.txt": b"x"}, "keep.txt": b"y"}
    options = CompareOptions(filters=CompareFilters(exclude_globs=parse_globs('"My Documents"')))
    root = run_compare(make_fs(spec), make_fs(spec), options)
    assert [c.name for c in root.children] == ["keep.txt"]


def test_excluded_orphan_does_not_flag_parent():
    left = make_fs({"data": {"real.txt": b"x", "junk.tmp": b"t"}})
    right = make_fs({"data": {"real.txt": b"x"}})
    options = CompareOptions(filters=CompareFilters(exclude_globs=("*.tmp",)))
    root = run_compare(left, right, options)
    assert find(root, "data").status.value == "same"
