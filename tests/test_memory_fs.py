from datetime import UTC, datetime

import pytest
from vfs_contract import FileSystemContractTests, write

from shankompare.vfs import InMemoryFileSystem


class TestInMemoryFileSystem(FileSystemContractTests):
    @pytest.fixture
    def fs(self):
        with InMemoryFileSystem() as fs:
            yield fs


def test_set_mtime_helper():
    fs = InMemoryFileSystem()
    write(fs, "a.txt")
    stamp = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    fs.set_mtime("a.txt", stamp)
    assert fs.stat("a.txt").mtime == stamp
