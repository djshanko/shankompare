"""The SFTP file-handle wrapper turns streaming failures into VfsError.

No server required: a fake handle stands in for paramiko's SFTPFile. What
matters is that an error raised *after* open — mid-read or mid-write, where
paramiko talks to the socket directly — still reaches callers as a VfsError,
since the compare engine and the file-operations queue handle nothing else.
"""

import paramiko
import pytest

from shankompare.vfs import VfsConnectionError, VfsError, VfsNotFound, VfsPermissionError
from shankompare.vfs.sftp import _TranslatedFile


class _FakeHandle:
    def __init__(self, error: Exception | None = None):
        self._error = error
        self.closed = False
        self.written = b""

    def read(self, size=-1):
        if self._error is not None:
            raise self._error
        return b"data"[:size] if size >= 0 else b"data"

    def write(self, data):
        if self._error is not None:
            raise self._error
        self.written += data

    def close(self):
        if self._error is not None:
            raise self._error
        self.closed = True


def test_passes_data_through_when_healthy():
    handle = _FakeHandle()
    with _TranslatedFile(handle) as f:
        assert f.read() == b"data"
        assert f.read(2) == b"da"
        f.write(b"xy")
    assert handle.written == b"xy"
    assert handle.closed  # the context manager closes the underlying handle


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (paramiko.SSHException("connection lost"), VfsConnectionError),
        (ConnectionResetError("reset"), VfsConnectionError),
        (TimeoutError("timed out"), VfsConnectionError),
        (PermissionError("denied"), VfsPermissionError),
        (FileNotFoundError("gone"), VfsNotFound),
        (OSError("disk full"), VfsError),
    ],
)
def test_read_errors_become_vfs_errors(raised, expected):
    with pytest.raises(expected):
        _TranslatedFile(_FakeHandle(raised)).read(1024)


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (paramiko.SSHException("connection lost"), VfsConnectionError),
        (OSError("disk full"), VfsError),
    ],
)
def test_write_errors_become_vfs_errors(raised, expected):
    with pytest.raises(expected):
        _TranslatedFile(_FakeHandle(raised)).write(b"x")


def test_close_errors_become_vfs_errors():
    """close() flushes buffered writes, so a failure there is a failed write."""
    with pytest.raises(VfsConnectionError):
        _TranslatedFile(_FakeHandle(paramiko.SSHException("lost"))).close()
