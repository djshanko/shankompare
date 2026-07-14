"""Core VFS abstractions shared by all backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import BinaryIO

from .errors import VfsError, VfsNotFound

PathLike = str | PurePosixPath


@dataclass(frozen=True)
class EntryInfo:
    """Metadata for one directory entry.

    ``mtime`` is always timezone-aware UTC. ``raw`` carries the backend's
    native stat object for backend-specific consumers; portable code must
    not touch it.
    """

    name: str
    is_dir: bool
    size: int
    mtime: datetime
    raw: object = None


def normalize(path: PathLike) -> PurePosixPath:
    """Normalize to a root-relative POSIX path; ``.`` means the filesystem root.

    Leading slashes and ``.`` segments are dropped; ``..`` is rejected so a
    path can never escape the filesystem root.
    """
    parts = [p for p in PurePosixPath(path).parts if p not in ("/", ".")]
    if ".." in parts:
        raise VfsError(f"path may not contain '..': {path}")
    return PurePosixPath(*parts) if parts else PurePosixPath(".")


class FileSystem(ABC):
    """A rooted filesystem.

    All paths are POSIX-style and relative to the instance's root; ``.``
    (or ``""``) refers to the root itself. Implementations raise only
    ``VfsError`` subtypes. Instances are not thread-safe — use one per
    worker thread.

    Behaviour when ``rename`` targets an existing path is backend-dependent;
    callers that need overwrite semantics must ``remove`` the target first.
    """

    @abstractmethod
    def listdir(self, path: PathLike = ".") -> list[EntryInfo]:
        """Return the entries of a directory, sorted by name."""

    @abstractmethod
    def stat(self, path: PathLike) -> EntryInfo:
        """Return metadata for one path."""

    @abstractmethod
    def open_read(self, path: PathLike) -> BinaryIO:
        """Open a file for binary reading."""

    @abstractmethod
    def open_write(self, path: PathLike) -> BinaryIO:
        """Open a file for binary writing, truncating any existing content."""

    @abstractmethod
    def mkdir(self, path: PathLike) -> None:
        """Create a directory. The parent must exist; the path must not."""

    @abstractmethod
    def remove(self, path: PathLike) -> None:
        """Remove a file or an empty directory."""

    @abstractmethod
    def rename(self, src: PathLike, dst: PathLike) -> None:
        """Rename/move within this filesystem."""

    @abstractmethod
    def close(self) -> None:
        """Release backend resources (connections, handles)."""

    def exists(self, path: PathLike) -> bool:
        try:
            self.stat(path)
        except VfsNotFound:
            return False
        return True

    def __enter__(self) -> "FileSystem":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
