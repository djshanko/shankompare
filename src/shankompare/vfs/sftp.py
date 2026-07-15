"""SFTP backend built on paramiko.

paramiko clients are not thread-safe: create one ``SftpFileSystem`` per
worker thread, never share one across threads.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from stat import S_ISDIR
from typing import BinaryIO
from uuid import uuid4

import paramiko

from .base import EntryInfo, FileSystem, PathLike, normalize
from .errors import VfsAuthError, VfsConnectionError, VfsError, VfsNotFound, VfsPermissionError

log = logging.getLogger(__name__)


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


def _apply_offset(timestamp: float | None, offset: timedelta) -> datetime:
    """A raw server mtime translated into the local clock frame."""
    return datetime.fromtimestamp(timestamp or 0, tz=UTC) - offset


def _remove_offset(mtime: datetime, offset: timedelta) -> int:
    """A local-frame mtime translated back to the server clock (whole seconds)."""
    return int((mtime + offset).timestamp())


def _clock_offset(server_now: float, local_before: float, local_after: float) -> timedelta:
    """server_now minus the midpoint of the local interval that bracketed it.

    Positive means the server clock runs ahead of the local clock.
    """
    return timedelta(seconds=server_now - (local_before + local_after) / 2)


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
        measure_clock_offset: bool = False,
    ):
        # Difference between the server clock and this machine's clock. All
        # mtimes this backend reports are shifted by ``-clock_offset`` so they
        # line up with local files even when the server's clock is skewed;
        # ``set_mtime`` shifts back. Zero (and ``clock_offset_known`` False)
        # until a probe succeeds, which reproduces the pre-offset behaviour.
        self.clock_offset: timedelta = timedelta(0)
        self.clock_offset_known: bool = False
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
        if measure_clock_offset:
            self._probe_clock_offset()

    def _probe_clock_offset(self) -> None:
        """Measure server-vs-local clock skew by timestamping a temp file.

        Best effort: any failure (e.g. a read-only root) leaves the offset at
        zero and ``clock_offset_known`` False. SFTP has no clock request, so
        the server's ``now`` is read as the mtime it stamps on a fresh file.
        """
        probe = str(self._root / f".shankompare-clockcheck-{uuid4().hex}")
        server_now: float | None = None
        try:
            local_before = time.time()
            self._sftp.open(probe, "w").close()
            server_now = self._sftp.stat(probe).st_mtime
            local_after = time.time()
        except (OSError, paramiko.SSHException) as exc:
            log.warning(
                "clock-offset probe failed (remote mtimes will NOT be adjusted): "
                "could not write %s: %s",
                probe,
                exc,
            )
            return
        finally:
            try:
                self._sftp.remove(probe)
            except (OSError, paramiko.SSHException):
                log.debug("could not remove clock-offset probe file %s", probe)
        if server_now is None:
            log.warning("clock-offset probe: server returned no mtime; not adjusting")
            return
        self.clock_offset = _clock_offset(server_now, local_before, local_after)
        self.clock_offset_known = True
        log.info(
            "SFTP clock offset measured: %+.1f s (server vs local)",
            self.clock_offset.total_seconds(),
        )

    def _full(self, path: PathLike) -> str:
        return str(self._root / normalize(path))

    def listdir(self, path: PathLike = ".") -> list[EntryInfo]:
        with _translate():
            attrs = self._sftp.listdir_attr(self._full(path))
        entries = [
            EntryInfo(
                a.filename,
                S_ISDIR(a.st_mode or 0),
                a.st_size or 0,
                _apply_offset(a.st_mtime, self.clock_offset),
                a,
            )
            for a in attrs
        ]
        entries.sort(key=lambda e: e.name)
        return entries

    def stat(self, path: PathLike) -> EntryInfo:
        with _translate():
            attr = self._sftp.stat(self._full(path))
        name = normalize(path).name or self._root.name or "/"
        is_dir = S_ISDIR(attr.st_mode or 0)
        mtime = _apply_offset(attr.st_mtime, self.clock_offset)
        return EntryInfo(name, is_dir, attr.st_size or 0, mtime, attr)

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

    def set_mtime(self, path: PathLike, mtime: datetime) -> None:
        # Undo the local-frame shift so the stored value round-trips through
        # stat/listdir. SFTP mtimes are whole seconds.
        timestamp = _remove_offset(mtime, self.clock_offset)
        with _translate():
            self._sftp.utime(self._full(path), (timestamp, timestamp))

    def resolve(self, path: str) -> str:
        """Server-absolute form of ``path`` (SFTP realpath). Used for browsing."""
        with _translate():
            return self._sftp.normalize(path)

    def close(self) -> None:
        try:
            self._sftp.close()
        finally:
            self._client.close()
