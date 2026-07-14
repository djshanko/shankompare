"""Behavioural contract every FileSystem backend must satisfy.

Backend test modules subclass ``FileSystemContractTests`` and provide an
``fs`` fixture yielding an empty, writable filesystem rooted somewhere
disposable.
"""

import pytest

from shankompare.vfs import FileSystem, VfsError, VfsNotFound


def write(fs: FileSystem, path: str, data: bytes = b"hello") -> None:
    with fs.open_write(path) as f:
        f.write(data)


class FileSystemContractTests:
    @pytest.fixture
    def fs(self) -> FileSystem:
        raise NotImplementedError("backend test class must override the fs fixture")

    # --- listing and metadata -------------------------------------------------

    def test_root_starts_empty(self, fs):
        assert fs.listdir() == []

    def test_listdir_reports_files_and_dirs(self, fs):
        fs.mkdir("sub")
        write(fs, "a.txt", b"abc")
        entries = {e.name: e for e in fs.listdir()}
        assert set(entries) == {"sub", "a.txt"}
        assert entries["sub"].is_dir
        assert not entries["a.txt"].is_dir
        assert entries["a.txt"].size == 3

    def test_listdir_is_sorted_by_name(self, fs):
        for name in ("c.txt", "a.txt", "b.txt"):
            write(fs, name)
        assert [e.name for e in fs.listdir()] == ["a.txt", "b.txt", "c.txt"]

    def test_listdir_missing_raises(self, fs):
        with pytest.raises(VfsNotFound):
            fs.listdir("nope")

    def test_stat_file(self, fs):
        write(fs, "a.txt", b"abcd")
        info = fs.stat("a.txt")
        assert info.name == "a.txt"
        assert not info.is_dir
        assert info.size == 4

    def test_stat_directory(self, fs):
        fs.mkdir("sub")
        assert fs.stat("sub").is_dir

    def test_stat_missing_raises(self, fs):
        with pytest.raises(VfsNotFound):
            fs.stat("nope.txt")

    def test_mtime_is_timezone_aware(self, fs):
        write(fs, "a.txt")
        assert fs.stat("a.txt").mtime.tzinfo is not None

    def test_exists(self, fs):
        assert not fs.exists("a.txt")
        write(fs, "a.txt")
        assert fs.exists("a.txt")

    # --- reading and writing --------------------------------------------------

    def test_write_read_roundtrip(self, fs):
        write(fs, "a.txt", b"hello world")
        with fs.open_read("a.txt") as f:
            assert f.read() == b"hello world"

    def test_overwrite_replaces_content(self, fs):
        write(fs, "a.txt", b"long original content")
        write(fs, "a.txt", b"short")
        with fs.open_read("a.txt") as f:
            assert f.read() == b"short"
        assert fs.stat("a.txt").size == 5

    def test_open_read_missing_raises(self, fs):
        with pytest.raises(VfsNotFound):
            fs.open_read("nope.txt")

    def test_open_write_missing_parent_raises(self, fs):
        with pytest.raises(VfsNotFound):
            write(fs, "nope/a.txt")

    # --- directories ----------------------------------------------------------

    def test_nested_directories(self, fs):
        fs.mkdir("a")
        fs.mkdir("a/b")
        write(fs, "a/b/deep.txt", b"deep")
        assert fs.stat("a/b/deep.txt").size == 4
        assert [e.name for e in fs.listdir("a")] == ["b"]

    def test_mkdir_existing_raises(self, fs):
        fs.mkdir("sub")
        with pytest.raises(VfsError):
            fs.mkdir("sub")

    def test_mkdir_missing_parent_raises(self, fs):
        with pytest.raises(VfsNotFound):
            fs.mkdir("nope/sub")

    # --- remove and rename ----------------------------------------------------

    def test_remove_file(self, fs):
        write(fs, "a.txt")
        fs.remove("a.txt")
        assert not fs.exists("a.txt")

    def test_remove_empty_directory(self, fs):
        fs.mkdir("sub")
        fs.remove("sub")
        assert not fs.exists("sub")

    def test_remove_missing_raises(self, fs):
        with pytest.raises(VfsNotFound):
            fs.remove("nope.txt")

    def test_rename_file(self, fs):
        write(fs, "old.txt", b"payload")
        fs.rename("old.txt", "new.txt")
        assert not fs.exists("old.txt")
        with fs.open_read("new.txt") as f:
            assert f.read() == b"payload"

    def test_rename_into_subdirectory(self, fs):
        fs.mkdir("sub")
        write(fs, "a.txt", b"x")
        fs.rename("a.txt", "sub/a.txt")
        assert fs.exists("sub/a.txt")
        assert not fs.exists("a.txt")

    # --- unicode and path safety ----------------------------------------------

    def test_unicode_names_roundtrip(self, fs):
        name = "ünïcødé-文件-📄.txt"
        write(fs, name, b"data")
        assert [e.name for e in fs.listdir()] == [name]
        with fs.open_read(name) as f:
            assert f.read() == b"data"

    def test_parent_escape_rejected(self, fs):
        with pytest.raises(VfsError):
            fs.stat("../outside.txt")

    def test_leading_slash_is_root_relative(self, fs):
        write(fs, "a.txt", b"x")
        assert fs.stat("/a.txt").size == 1
