import pytest
from vfs_contract import FileSystemContractTests

from shankompare.vfs import LocalFileSystem, VfsError, VfsNotFound


class TestLocalFileSystem(FileSystemContractTests):
    @pytest.fixture
    def fs(self, tmp_path):
        with LocalFileSystem(tmp_path) as fs:
            yield fs


def test_missing_root_raises(tmp_path):
    with pytest.raises(VfsNotFound):
        LocalFileSystem(tmp_path / "does-not-exist")


# Names an SFTP server or an archive member can legally carry. On Windows these
# read as path syntax, so a copy could once write outside the root; on POSIX they
# are ordinary filenames. Either way the write must land inside the root.
_HOSTILE_NAMES = [
    "..\\..\\escaped.txt",
    "..\\escaped.txt",
    "sub\\..\\..\\escaped.txt",
    "C:escaped.txt",
    "\\\\server\\share\\escaped.txt",
]


@pytest.mark.parametrize("name", _HOSTILE_NAMES)
def test_write_never_escapes_the_root(tmp_path, name):
    root = tmp_path / "root"
    root.mkdir()
    fs = LocalFileSystem(root)
    try:
        with fs.open_write(name) as f:
            f.write(b"pwned")
    except VfsError:
        pass  # refused outright (Windows: the name is path syntax)
    assert list(tmp_path.iterdir()) == [root]  # nothing landed beside the root


@pytest.mark.parametrize("name", _HOSTILE_NAMES)
def test_read_never_escapes_the_root(tmp_path, name):
    """A hostile name must not reach a file outside the root — VfsError or not found."""
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "secret.txt").write_bytes(b"secret")
    fs = LocalFileSystem(root)
    with pytest.raises(VfsError):  # VfsNotFound on POSIX, plain VfsError on Windows
        fs.open_read(name.replace("escaped.txt", "secret.txt"))


def test_ordinary_nested_paths_still_work(tmp_path):
    """The escape check must not reject legitimate paths."""
    fs = LocalFileSystem(tmp_path)
    fs.mkdir("sub")
    with fs.open_write("sub/a.txt") as f:
        f.write(b"hello")
    assert fs.stat("sub/a.txt").size == 5
    assert fs.stat(".").is_dir
