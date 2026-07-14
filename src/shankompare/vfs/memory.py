"""In-memory backend: reference implementation and test double.

Used by unit tests (comparer tests build trees here instead of on disk)
and by the VFS contract suite as the semantics baseline.
"""

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import BinaryIO

from .base import EntryInfo, FileSystem, PathLike, normalize
from .errors import VfsError, VfsNotFound


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _File:
    data: bytes = b""
    mtime: datetime = field(default_factory=_now)


@dataclass
class _Dir:
    children: dict[str, "_File | _Dir"] = field(default_factory=dict)
    mtime: datetime = field(default_factory=_now)


class _WriteBuffer(io.BytesIO):
    """BytesIO that commits its contents to the tree on close."""

    def __init__(self, commit: Callable[[bytes], None]):
        super().__init__()
        self._commit = commit

    def close(self) -> None:
        if not self.closed:
            self._commit(self.getvalue())
        super().close()


class InMemoryFileSystem(FileSystem):
    def __init__(self) -> None:
        self._root = _Dir()

    def _node(self, path: PathLike) -> "_File | _Dir":
        node: _File | _Dir = self._root
        for part in normalize(path).parts:
            if not isinstance(node, _Dir) or part not in node.children:
                raise VfsNotFound(f"no such path: {path}")
            node = node.children[part]
        return node

    def _dir(self, path: PathLike) -> _Dir:
        node = self._node(path)
        if not isinstance(node, _Dir):
            raise VfsError(f"not a directory: {path}")
        return node

    def _split(self, path: PathLike) -> tuple[_Dir, str]:
        rel = normalize(path)
        if rel == PurePosixPath("."):
            raise VfsError("operation not allowed on the filesystem root")
        return self._dir(rel.parent), rel.name

    @staticmethod
    def _entry(name: str, node: "_File | _Dir") -> EntryInfo:
        if isinstance(node, _Dir):
            return EntryInfo(name, True, 0, node.mtime)
        return EntryInfo(name, False, len(node.data), node.mtime)

    def listdir(self, path: PathLike = ".") -> list[EntryInfo]:
        directory = self._dir(path)
        entries = [self._entry(name, node) for name, node in directory.children.items()]
        entries.sort(key=lambda e: e.name)
        return entries

    def stat(self, path: PathLike) -> EntryInfo:
        node = self._node(path)
        return self._entry(normalize(path).name or ".", node)

    def open_read(self, path: PathLike) -> BinaryIO:
        node = self._node(path)
        if isinstance(node, _Dir):
            raise VfsError(f"is a directory: {path}")
        return io.BytesIO(node.data)

    def open_write(self, path: PathLike) -> BinaryIO:
        parent, name = self._split(path)
        if isinstance(parent.children.get(name), _Dir):
            raise VfsError(f"is a directory: {path}")

        def commit(data: bytes) -> None:
            parent.children[name] = _File(data)

        return _WriteBuffer(commit)

    def mkdir(self, path: PathLike) -> None:
        parent, name = self._split(path)
        if name in parent.children:
            raise VfsError(f"already exists: {path}")
        parent.children[name] = _Dir()

    def remove(self, path: PathLike) -> None:
        parent, name = self._split(path)
        node = parent.children.get(name)
        if node is None:
            raise VfsNotFound(f"no such path: {path}")
        if isinstance(node, _Dir) and node.children:
            raise VfsError(f"directory not empty: {path}")
        del parent.children[name]

    def rename(self, src: PathLike, dst: PathLike) -> None:
        src_parent, src_name = self._split(src)
        if src_name not in src_parent.children:
            raise VfsNotFound(f"no such path: {src}")
        dst_parent, dst_name = self._split(dst)
        if dst_name in dst_parent.children:
            raise VfsError(f"destination already exists: {dst}")
        dst_parent.children[dst_name] = src_parent.children.pop(src_name)

    def set_mtime(self, path: PathLike, mtime: datetime) -> None:
        self._node(path).mtime = mtime

    def close(self) -> None:
        pass
