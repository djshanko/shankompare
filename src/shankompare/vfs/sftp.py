"""SFTP backend built on paramiko.

paramiko clients are not thread-safe: create one ``SftpFileSystem`` per
worker thread, never share one across threads.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import PurePosixPath
from stat import S_ISDIR
from typing import BinaryIO

import paramiko

from .base import EntryInfo, FileSystem, PathLike, normalize
from .errors import VfsAuthError, VfsConnectionError, VfsError, VfsNotFound, VfsPermissionError


@contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except VfsError:
        raise
    except FileNotFoundError as exc:
        raise VfsNotFound(str(exc)) from exc
    except PermissionError as exc:
        raise VfsPermissionError(str(exc)) from exc
    except paramiko.AuthenticationException as exc:
        raise VfsAuthError(str(exc)) from exc
    except (ConnectionError, TimeoutError, paramiko.SSHException) as exc:
        raise VfsConnectionError(str(exc)) from exc
    except OSError as exc:
        raise VfsError(str(exc)) from exc


def _mtime(timestamp: float | None) -> datetime:
    return datetime.fromtimestamp(timestamp or 0, tz=UTC)


class SftpFileSystem(FileSystem):
    def __init__(
        self,
        host: str,
        *,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        key_file: str | None = None,
        key_passphrase: str | None = None,
        root: str = ".",
        timeout: float = 15.0,
    ):
        self._client = paramiko.SSHClient()
        self._client.load_system_host_keys()
        # Trust-on-first-use; revisit (known-hosts prompt) before wider distribution.
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            with _translate():
                pkey = None
                if key_file is not None:
                    passphrase = key_passphrase.encode() if key_passphrase else None
                    pkey = paramiko.PKey.from_path(key_file, passphrase=passphrase)
                self._client.connect(
                    host,
                    port=port,
                    username=username,
                    password=password,
                    pkey=pkey,
                    timeout=timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
                self._sftp = self._client.open_sftp()
                self._root = PurePosixPath(self._sftp.normalize(root))
        except VfsError:
            self._client.close()
            raise

    def _full(self, path: PathLike) -> str:
        return str(self._root / normalize(path))

    def listdir(self, path: PathLike = ".") -> list[EntryInfo]:
        with _translate():
            attrs = self._sftp.listdir_attr(self._full(path))
        entries = [
            EntryInfo(a.filename, S_ISDIR(a.st_mode or 0), a.st_size or 0, _mtime(a.st_mtime), a)
            for a in attrs
        ]
        entries.sort(key=lambda e: e.name)
        return entries

    def stat(self, path: PathLike) -> EntryInfo:
        with _translate():
            attr = self._sftp.stat(self._full(path))
        name = normalize(path).name or self._root.name or "/"
        is_dir = S_ISDIR(attr.st_mode or 0)
        return EntryInfo(name, is_dir, attr.st_size or 0, _mtime(attr.st_mtime), attr)

    def open_read(self, path: PathLike) -> BinaryIO:
        with _translate():
            return self._sftp.open(self._full(path), "rb")

    def open_write(self, path: PathLike) -> BinaryIO:
        with _translate():
            return self._sftp.open(self._full(path), "wb")

    def mkdir(self, path: PathLike) -> None:
        with _translate():
            self._sftp.mkdir(self._full(path))

    def remove(self, path: PathLike) -> None:
        with _translate():
            if S_ISDIR(self._sftp.stat(self._full(path)).st_mode or 0):
                self._sftp.rmdir(self._full(path))
            else:
                self._sftp.remove(self._full(path))

    def rename(self, src: PathLike, dst: PathLike) -> None:
        with _translate():
            self._sftp.rename(self._full(src), self._full(dst))

    def close(self) -> None:
        try:
            self._sftp.close()
        finally:
            self._client.close()
