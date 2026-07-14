"""Local disk backend (also covers mapped network drives and UNC paths)."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from stat import S_ISDIR
from typing import BinaryIO

from .base import EntryInfo, FileSystem, PathLike, normalize
from .errors import VfsError, VfsNotFound, VfsPermissionError


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
    except OSError as exc:
        raise VfsError(str(exc)) from exc


def _mtime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)


class LocalFileSystem(FileSystem):
    def __init__(self, root: str | Path):
        self._root = Path(root)
        if not self._root.is_dir():
            raise VfsNotFound(f"root directory does not exist: {root}")

    def _full(self, path: PathLike) -> Path:
        return self._root / normalize(path)

    def listdir(self, path: PathLike = ".") -> list[EntryInfo]:
        entries: list[EntryInfo] = []
        with _translate(), os.scandir(self._full(path)) as it:
            for entry in it:
                try:
                    st = entry.stat()
                    is_dir = entry.is_dir()
                except OSError:
                    # Broken symlink: report the link itself rather than fail the scan.
                    st = entry.stat(follow_symlinks=False)
                    is_dir = False
                entries.append(EntryInfo(entry.name, is_dir, st.st_size, _mtime(st.st_mtime), st))
        entries.sort(key=lambda e: e.name)
        return entries

    def stat(self, path: PathLike) -> EntryInfo:
        full = self._full(path)
        with _translate():
            st = full.stat()
        name = full.name or str(self._root)
        return EntryInfo(name, S_ISDIR(st.st_mode), st.st_size, _mtime(st.st_mtime), st)

    def open_read(self, path: PathLike) -> BinaryIO:
        with _translate():
            return self._full(path).open("rb")

    def open_write(self, path: PathLike) -> BinaryIO:
        with _translate():
            return self._full(path).open("wb")

    def mkdir(self, path: PathLike) -> None:
        with _translate():
            self._full(path).mkdir()

    def remove(self, path: PathLike) -> None:
        full = self._full(path)
        with _translate():
            if full.is_dir():
                full.rmdir()
            else:
                full.unlink()

    def rename(self, src: PathLike, dst: PathLike) -> None:
        with _translate():
            self._full(src).rename(self._full(dst))

    def set_mtime(self, path: PathLike, mtime: datetime) -> None:
        timestamp = mtime.timestamp()
        with _translate():
            os.utime(self._full(path), (timestamp, timestamp))

    def close(self) -> None:
        pass
