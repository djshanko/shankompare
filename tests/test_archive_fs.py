import io
import tarfile
import zipfile
from datetime import UTC, datetime

import pytest
from test_folder_compare import run_compare

from shankompare.vfs import ArchiveFileSystem, VfsError, VfsNotFound, VfsPermissionError
from shankompare.vfs.archive import is_archive_name


def make_zip(members: dict[str, bytes], with_dir_entries: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if with_dir_entries:
            dirs = {str(p) for name in members for p in _parents(name)}
            for d in sorted(dirs):
                zf.writestr(d + "/", "")
        for name, data in members.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 7, 14, 12, 0, 0))
            zf.writestr(info, data)
    return buf.getvalue()


def _parents(name: str):
    from pathlib import PurePosixPath

    return [p for p in PurePosixPath(name).parents if str(p) != "."]


def make_tar(members: dict[str, bytes], compression: str = "") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=f"w:{compression}") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = int(datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC).timestamp())
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


MEMBERS = {"top.txt": b"top", "docs/readme.md": b"# hi", "docs/deep/leaf.bin": b"\x00\x01"}


@pytest.fixture(params=["zip", "zip-no-dirs", "tar", "tar-gz"])
def fs(request):
    if request.param == "zip":
        data, name = make_zip(MEMBERS), "sample.zip"
    elif request.param == "zip-no-dirs":
        data, name = make_zip(MEMBERS, with_dir_entries=False), "sample.zip"
    elif request.param == "tar":
        data, name = make_tar(MEMBERS), "sample.tar"
    else:
        data, name = make_tar(MEMBERS, "gz"), "sample.tar.gz"
    with ArchiveFileSystem(data, name) as fs:
        yield fs


def test_listdir_root(fs):
    assert [(e.name, e.is_dir) for e in fs.listdir()] == [("docs", True), ("top.txt", False)]


def test_listdir_nested_and_stat(fs):
    assert [e.name for e in fs.listdir("docs")] == ["deep", "readme.md"]
    info = fs.stat("docs/readme.md")
    assert not info.is_dir
    assert info.size == 4
    assert info.mtime.tzinfo is not None


def test_open_read(fs):
    with fs.open_read("docs/deep/leaf.bin") as f:
        assert f.read() == b"\x00\x01"


def test_missing_path_raises(fs):
    with pytest.raises(VfsNotFound):
        fs.stat("nope.txt")
    with pytest.raises(VfsNotFound):
        fs.listdir("docs/nope")


def test_write_operations_raise(fs):
    with pytest.raises(VfsPermissionError):
        fs.open_write("new.txt")
    with pytest.raises(VfsPermissionError):
        fs.mkdir("newdir")
    with pytest.raises(VfsPermissionError):
        fs.remove("top.txt")
    with pytest.raises(VfsPermissionError):
        fs.rename("top.txt", "other.txt")
    with pytest.raises(VfsPermissionError):
        fs.set_mtime("top.txt", datetime.now(UTC))


def test_corrupt_archive_raises_vfs_error():
    with pytest.raises(VfsError):
        ArchiveFileSystem(b"definitely not an archive", "broken.tar.gz")


def test_is_archive_name():
    assert is_archive_name("a.zip")
    assert is_archive_name("A.TAR.GZ")
    assert is_archive_name("b.tgz")
    assert not is_archive_name("a.txt")
    assert not is_archive_name("zipper.txt")


def test_two_archives_compare_like_folders():
    left = ArchiveFileSystem(make_zip(MEMBERS), "left.zip")
    changed = dict(MEMBERS)
    changed["docs/readme.md"] = b"# hi there, changed"
    right = ArchiveFileSystem(make_tar(changed, "gz"), "right.tar.gz")
    root = run_compare(left, right)
    from shankompare.compare import Status

    statuses = {}

    def collect(node, prefix=""):
        for child in node.children:
            path = f"{prefix}{child.name}"
            statuses[path] = child.status
            collect(child, path + "/")

    collect(root)
    assert statuses["top.txt"] is Status.SAME
    assert statuses["docs/readme.md"] is Status.DIFFERENT
    assert statuses["docs/deep/leaf.bin"] is Status.SAME
