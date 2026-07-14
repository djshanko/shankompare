"""Read-only archive backend: browse zip/tar files as folders.

The whole archive is read into memory once (works uniformly for local and
SFTP sources); write operations raise ``VfsPermissionError``.
"""

import io
import tarfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import BinaryIO

from .base import EntryInfo, FileSystem, PathLike, normalize
from .errors import VfsError, VfsNotFound, VfsPermissionError

ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024

_EPOCH = datetime.fromtimestamp(0, tz=UTC)


def is_archive_name(name: str) -> bool:
    return name.lower().endswith(ARCHIVE_SUFFIXES)


@dataclass
class _Member:
    is_dir: bool
    size: int = 0
    mtime: datetime = _EPOCH
    key: str | None = None  # member name inside the archive (None for implicit dirs)
    children: dict[str, "_Member"] = field(default_factory=dict)


class ArchiveFileSystem(FileSystem):
    def __init__(self, data: bytes, name: str):
        self._name = name
        self._zip: zipfile.ZipFile | None = None
        self._tar: tarfile.TarFile | None = None
        self._root = _Member(is_dir=True)
        try:
            if name.lower().endswith(".zip") or data[:4] == b"PK\x03\x04":
                self._zip = zipfile.ZipFile(io.BytesIO(data))
                self._index_zip()
            else:
                # the handle stays open for the filesystem's lifetime; close() owns it
                self._tar = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")  # noqa: SIM115
                self._index_tar()
        except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
            raise VfsError(f"cannot open archive {name}: {exc}") from exc

    # --- index construction -----------------------------------------------------

    def _index_zip(self) -> None:
        assert self._zip is not None
        for info in self._zip.infolist():
            mtime = datetime(*info.date_time, tzinfo=UTC)  # zip times lack a zone; assume UTC
            self._register(info.filename, info.is_dir(), info.file_size, mtime, info.filename)

    def _index_tar(self) -> None:
        assert self._tar is not None
        for member in self._tar.getmembers():
            if not (member.isfile() or member.isdir()):
                continue  # skip links/devices
            mtime = datetime.fromtimestamp(member.mtime, tz=UTC)
            self._register(member.name, member.isdir(), member.size, mtime, member.name)

    def _register(self, raw_path: str, is_dir: bool, size: int, mtime: datetime, key: str) -> None:
        parts = [p for p in PurePosixPath(raw_path).parts if p not in ("/", ".", "..")]
        if not parts:
            return
        node = self._root
        for part in parts[:-1]:
            child = node.children.get(part)
            if child is None or not child.is_dir:
                child = _Member(is_dir=True)  # implicit parent directory
                node.children[part] = child
            child.mtime = max(child.mtime, mtime)
            node = child
        leaf = parts[-1]
        if is_dir:
            existing = node.children.get(leaf)
            if existing is not None and existing.is_dir:
                existing.key = key
                existing.mtime = max(existing.mtime, mtime)
            else:
                node.children[leaf] = _Member(is_dir=True, mtime=mtime, key=key)
        else:
            node.children[leaf] = _Member(is_dir=False, size=size, mtime=mtime, key=key)

    # --- lookup -------------------------------------------------------------------

    def _node(self, path: PathLike) -> _Member:
        node = self._root
        for part in normalize(path).parts:
            if not node.is_dir or part not in node.children:
                raise VfsNotFound(f"no such path in archive: {path}")
            node = node.children[part]
        return node

    @staticmethod
    def _entry(name: str, node: _Member) -> EntryInfo:
        return EntryInfo(name, node.is_dir, node.size, node.mtime)

    # --- FileSystem API -------------------------------------------------------------

    def listdir(self, path: PathLike = ".") -> list[EntryInfo]:
        node = self._node(path)
        if not node.is_dir:
            raise VfsError(f"not a directory: {path}")
        entries = [self._entry(name, child) for name, child in node.children.items()]
        entries.sort(key=lambda e: e.name)
        return entries

    def stat(self, path: PathLike) -> EntryInfo:
        node = self._node(path)
        return self._entry(normalize(path).name or self._name, node)

    def open_read(self, path: PathLike) -> BinaryIO:
        node = self._node(path)
        if node.is_dir:
            raise VfsError(f"is a directory: {path}")
        assert node.key is not None
        try:
            if self._zip is not None:
                return io.BytesIO(self._zip.read(node.key))
            assert self._tar is not None
            stream = self._tar.extractfile(node.key)
            if stream is None:
                raise VfsNotFound(f"no such file in archive: {path}")
            with stream:
                return io.BytesIO(stream.read())
        except (zipfile.BadZipFile, tarfile.TarError, KeyError, OSError) as exc:
            raise VfsError(f"cannot read {path} from archive: {exc}") from exc

    def _read_only(self) -> VfsPermissionError:
        return VfsPermissionError(f"archive is read-only: {self._name}")

    def open_write(self, path: PathLike) -> BinaryIO:
        raise self._read_only()

    def mkdir(self, path: PathLike) -> None:
        raise self._read_only()

    def remove(self, path: PathLike) -> None:
        raise self._read_only()

    def rename(self, src: PathLike, dst: PathLike) -> None:
        raise self._read_only()

    def set_mtime(self, path: PathLike, mtime: datetime) -> None:
        raise self._read_only()

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
        if self._tar is not None:
            self._tar.close()
