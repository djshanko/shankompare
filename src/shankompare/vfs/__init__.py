"""Virtual file system: one interface over local disks, SFTP, and future backends."""

from .archive import ARCHIVE_SUFFIXES, ArchiveFileSystem, is_archive_name
from .base import EntryInfo, FileSystem, PathLike, normalize
from .errors import VfsAuthError, VfsConnectionError, VfsError, VfsNotFound, VfsPermissionError
from .local import LocalFileSystem
from .memory import InMemoryFileSystem
from .sftp import SftpFileSystem

__all__ = [
    "ARCHIVE_SUFFIXES",
    "ArchiveFileSystem",
    "EntryInfo",
    "FileSystem",
    "InMemoryFileSystem",
    "LocalFileSystem",
    "PathLike",
    "SftpFileSystem",
    "VfsAuthError",
    "VfsConnectionError",
    "VfsError",
    "VfsNotFound",
    "VfsPermissionError",
    "is_archive_name",
    "normalize",
]
