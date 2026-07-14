"""SFTP contract tests against a real server — skipped unless configured.

Quick local server:
    docker run --rm -p 2222:22 atmoz/sftp testuser:testpass:::upload

Then:
    SHANKOMPARE_TEST_SFTP_HOST=localhost
    SHANKOMPARE_TEST_SFTP_PORT=2222
    SHANKOMPARE_TEST_SFTP_USER=testuser
    SHANKOMPARE_TEST_SFTP_PASSWORD=testpass
    SHANKOMPARE_TEST_SFTP_ROOT=upload
"""

import os
import uuid

import pytest
from vfs_contract import FileSystemContractTests

from shankompare.vfs import FileSystem, SftpFileSystem

HOST = os.environ.get("SHANKOMPARE_TEST_SFTP_HOST")

pytestmark = pytest.mark.skipif(
    HOST is None,
    reason="set SHANKOMPARE_TEST_SFTP_* environment variables to run (see module docstring)",
)


def _connect(root: str) -> SftpFileSystem:
    assert HOST is not None
    return SftpFileSystem(
        HOST,
        port=int(os.environ.get("SHANKOMPARE_TEST_SFTP_PORT", "22")),
        username=os.environ.get("SHANKOMPARE_TEST_SFTP_USER"),
        password=os.environ.get("SHANKOMPARE_TEST_SFTP_PASSWORD"),
        root=root,
    )


def _rmtree(fs: FileSystem, path: str) -> None:
    for entry in fs.listdir(path):
        child = f"{path}/{entry.name}"
        if entry.is_dir:
            _rmtree(fs, child)
        else:
            fs.remove(child)
    fs.remove(path)


class TestSftpFileSystem(FileSystemContractTests):
    @pytest.fixture
    def fs(self):
        base = os.environ.get("SHANKOMPARE_TEST_SFTP_ROOT", ".")
        scratch = f"contract-{uuid.uuid4().hex}"
        with _connect(base) as admin:
            admin.mkdir(scratch)
            try:
                with _connect(f"{base}/{scratch}") as fs:
                    yield fs
            finally:
                _rmtree(admin, scratch)
