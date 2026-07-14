"""Folder comparison engine.

``compare_folders`` walks two ``FileSystem`` trees breadth-first and yields
progress events, so a consumer (e.g. a UI worker) can stream partial results.
Cheap criteria (size, mtime) are applied during the walk; content comparison
runs as a second pass so the tree shape appears quickly. No Qt here.
"""

import threading
import zlib
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath

from shankompare.vfs import EntryInfo, FileSystem, VfsError

_CHUNK_SIZE = 64 * 1024


class Status(Enum):
    SAME = "same"
    DIFFERENT = "different"
    LEFT_ONLY = "left_only"
    RIGHT_ONLY = "right_only"
    UNKNOWN = "unknown"


class ContentMode(Enum):
    NONE = "none"
    CRC32 = "crc32"
    BYTES = "bytes"


@dataclass(frozen=True)
class CompareOptions:
    """Comparison criteria.

    With ``case_sensitive=False``, entries are aligned by casefolded name;
    if one side contains two names differing only in case, only one of them
    is aligned (the other appears as an orphan).
    """

    use_size: bool = True
    use_mtime: bool = True
    mtime_tolerance: float = 2.0
    content: ContentMode = ContentMode.NONE
    case_sensitive: bool = True


@dataclass
class NodeResult:
    """One row of the comparison result tree."""

    name: str
    status: Status
    left: EntryInfo | None = None
    right: EntryInfo | None = None
    children: list["NodeResult"] = field(default_factory=list)
    error: str | None = None

    @property
    def is_dir(self) -> bool:
        entry = self.left or self.right
        return bool(entry and entry.is_dir)


class CompareCancelled(Exception):
    """Raised inside the generator when the cancel event is set."""


@dataclass(frozen=True)
class DirScanned:
    """A directory's entries were listed and cheap criteria applied."""

    path: PurePosixPath
    node: NodeResult


@dataclass(frozen=True)
class ContentChecked:
    """One file pair finished its content comparison."""

    path: PurePosixPath
    node: NodeResult


@dataclass(frozen=True)
class CompareDone:
    """Final event; ``root`` is the complete result tree."""

    root: NodeResult


CompareEvent = DirScanned | ContentChecked | CompareDone


def compare_folders(
    left_fs: FileSystem,
    right_fs: FileSystem,
    options: CompareOptions | None = None,
    cancel: threading.Event | None = None,
) -> Iterator[CompareEvent]:
    """Compare two rooted filesystems; yields events, ending with CompareDone."""
    options = options or CompareOptions()
    root = NodeResult("", Status.UNKNOWN, left_fs.stat("."), right_fs.stat("."))
    pending_content: list[tuple[PurePosixPath, NodeResult]] = []
    queue: deque[tuple[PurePosixPath, NodeResult]] = deque([(PurePosixPath("."), root)])

    while queue:
        _check_cancel(cancel)
        rel, node = queue.popleft()
        _scan_dir(left_fs, right_fs, rel, node, options, queue, pending_content)
        yield DirScanned(rel, node)

    for rel, node in pending_content:
        _check_cancel(cancel)
        _compare_content(left_fs, right_fs, rel, node, options)
        yield ContentChecked(rel, node)

    _finalize(root)
    yield CompareDone(root)


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise CompareCancelled


def _scan_dir(
    left_fs: FileSystem,
    right_fs: FileSystem,
    rel: PurePosixPath,
    node: NodeResult,
    options: CompareOptions,
    queue: deque[tuple[PurePosixPath, NodeResult]],
    pending_content: list[tuple[PurePosixPath, NodeResult]],
) -> None:
    try:
        left_entries = left_fs.listdir(rel) if node.left is not None else []
        right_entries = right_fs.listdir(rel) if node.right is not None else []
    except VfsError as exc:
        node.error = str(exc)
        return

    def key(name: str) -> str:
        return name if options.case_sensitive else name.casefold()

    left_by_key = {key(e.name): e for e in left_entries}
    right_by_key = {key(e.name): e for e in right_entries}

    for k in sorted(left_by_key.keys() | right_by_key.keys()):
        left = left_by_key.get(k)
        right = right_by_key.get(k)
        entry = left or right
        assert entry is not None
        child = NodeResult(entry.name, Status.UNKNOWN, left, right)
        node.children.append(child)
        child_rel = rel / entry.name

        if left is not None and right is not None:
            if left.is_dir and right.is_dir:
                queue.append((child_rel, child))
            elif left.is_dir != right.is_dir:
                child.status = Status.DIFFERENT
                child.error = "directory on one side, file on the other"
            else:
                child.status = _compare_cheap(left, right, options)
                if child.status is Status.UNKNOWN:
                    pending_content.append((child_rel, child))
        elif left is not None:
            child.status = Status.LEFT_ONLY
            if left.is_dir:
                queue.append((child_rel, child))
        else:
            assert right is not None
            child.status = Status.RIGHT_ONLY
            if right.is_dir:
                queue.append((child_rel, child))


def _compare_cheap(left: EntryInfo, right: EntryInfo, options: CompareOptions) -> Status:
    if options.use_size and left.size != right.size:
        return Status.DIFFERENT
    if options.use_mtime:
        delta = abs((left.mtime - right.mtime).total_seconds())
        if delta > options.mtime_tolerance:
            return Status.DIFFERENT
    if options.content is not ContentMode.NONE:
        return Status.UNKNOWN  # needs the content pass
    return Status.SAME


def _compare_content(
    left_fs: FileSystem,
    right_fs: FileSystem,
    rel: PurePosixPath,
    node: NodeResult,
    options: CompareOptions,
) -> None:
    try:
        if options.content is ContentMode.CRC32:
            equal = _crc32(left_fs, rel) == _crc32(right_fs, rel)
        else:
            equal = _bytes_equal(left_fs, right_fs, rel)
    except VfsError as exc:
        node.error = str(exc)  # status stays UNKNOWN
        return
    node.status = Status.SAME if equal else Status.DIFFERENT


def _crc32(fs: FileSystem, rel: PurePosixPath) -> int:
    checksum = 0
    with fs.open_read(rel) as f:
        while chunk := f.read(_CHUNK_SIZE):
            checksum = zlib.crc32(chunk, checksum)
    return checksum


def _bytes_equal(left_fs: FileSystem, right_fs: FileSystem, rel: PurePosixPath) -> bool:
    with left_fs.open_read(rel) as lf, right_fs.open_read(rel) as rf:
        while True:
            left_chunk = lf.read(_CHUNK_SIZE)
            right_chunk = rf.read(_CHUNK_SIZE)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def _finalize(node: NodeResult) -> None:
    """Derive directory-pair statuses bottom-up once all children are known."""
    for child in node.children:
        _finalize(child)
    if node.status is Status.UNKNOWN and node.left is not None and node.right is not None:
        if node.error is not None:
            return  # scan failed; leave UNKNOWN
        if any(child.status is not Status.SAME for child in node.children):
            node.status = Status.DIFFERENT
        else:
            node.status = Status.SAME
