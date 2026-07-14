import pytest
from vfs_contract import FileSystemContractTests

from shankompare.vfs import LocalFileSystem, VfsNotFound


class TestLocalFileSystem(FileSystemContractTests):
    @pytest.fixture
    def fs(self, tmp_path):
        with LocalFileSystem(tmp_path) as fs:
            yield fs


def test_missing_root_raises(tmp_path):
    with pytest.raises(VfsNotFound):
        LocalFileSystem(tmp_path / "does-not-exist")
