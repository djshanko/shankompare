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
from datetime import datetime
from enum import Enum
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

from shankompare.vfs import EntryInfo, FileSystem, VfsError

_CHUNK_SIZE = 64 * 1024

_SIZE_SUFFIXES = {"": 1, "b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}


def parse_size(text: str) -> int | None:
    """Parse a human size like ``"10M"``, ``"500k"``, ``"1024"``; "" -> None."""
    text = text.strip().lower().removesuffix("ib")
    if not text:
        return None
    number = text
    suffix = ""
    if text and text[-1] in "bkmg":
        number, suffix = text[:-1], text[-1]
        if suffix == "b":
            suffix = ""
    try:
        value = float(number)
    except ValueError:
        raise ValueError(f"not a size: {text!r}") from None
    if value < 0:
        raise ValueError(f"not a size: {text!r}")
    return int(value * _SIZE_SUFFIXES[suffix])


@dataclass(frozen=True)
class ExcludeFilters:
    """Entries removed from a comparison before alignment.

    ``name_globs`` exclude files *and* folders by name (case-insensitive
    fnmatch). The size and mtime bounds are include-ranges applied to files
    only: a file outside the range is excluded; folders always pass them.
    """

    name_globs: tuple[str, ...] = ()
    min_size: int | None = None
    max_size: int | None = None
    modified_after: datetime | None = None
    modified_before: datetime | None = None

    def passes(self, entry: EntryInfo) -> bool:
        name = entry.name.casefold()
        for pattern in self.name_globs:
            if fnmatchcase(name, pattern.casefold()):
                return False
        if entry.is_dir:
            return True
        if self.min_size is not None and entry.size < self.min_size:
            return False
        if self.max_size is not None and entry.size > self.max_size:
            return False
        if self.modified_after is not None and entry.mtime < self.modified_after:
            return False
        return self.modified_before is None or entry.mtime <= self.modified_before


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

    When ``content`` is not ``NONE`` the bytes are authoritative: a size
    mismatch means DIFFERENT without a read, but a mtime difference alone does
    not — the files are read and their contents decide (so an identical file
    with a shifted timestamp, common after an SFTP copy, is reported the same).
    ``skip_content_if_metadata_matches`` is a shortcut: when it is true a pair
    whose size *and* mtime already agree is taken as equal without reading;
    set it false to force a content read even for metadata-matching pairs.
    """

    use_size: bool = True
    use_mtime: bool = True
    mtime_tolerance: float = 2.0
    content: ContentMode = ContentMode.NONE
    skip_content_if_metadata_matches: bool = True
    case_sensitive: bool = True
    exclude: ExcludeFilters = field(default_factory=ExcludeFilters)


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
    baseline: NodeResult | None = None,
) -> Iterator[CompareEvent]:
    """Compare two rooted filesystems; yields events, ending with CompareDone.

    ``baseline`` is the result tree of a previous comparison. When given, a
    file pair whose size and mtime on both sides are unchanged from the
    baseline reuses the baseline's status instead of re-reading content — a
    "refresh" that only pays the content cost for files modified since then.
    """
    options = options or CompareOptions()
    root = NodeResult("", Status.UNKNOWN, left_fs.stat("."), right_fs.stat("."))
    baseline_index = _index_by_path(baseline) if baseline is not None else {}
    pending_content: list[tuple[PurePosixPath, NodeResult]] = []
    queue: deque[tuple[PurePosixPath, NodeResult]] = deque([(PurePosixPath("."), root)])

    while queue:
        _check_cancel(cancel)
        rel, node = queue.popleft()
        _scan_dir(left_fs, right_fs, rel, node, options, queue, pending_content)
        yield DirScanned(rel, node)

    for rel, node in pending_content:
        _check_cancel(cancel)
        if not _reuse_baseline(node, baseline_index.get(str(rel))):
            _compare_content(left_fs, right_fs, rel, node, options)
        yield ContentChecked(rel, node)

    _finalize(root)
    yield CompareDone(root)


def _index_by_path(root: NodeResult) -> dict[str, NodeResult]:
    """Map every node in a result tree to its relative path (as compare_folders keys them)."""
    index: dict[str, NodeResult] = {}
    stack: list[tuple[PurePosixPath, NodeResult]] = [(PurePosixPath("."), root)]
    while stack:
        rel, node = stack.pop()
        index[str(rel)] = node
        for child in node.children:
            stack.append((rel / child.name, child))
    return index


def _stat_unchanged(current: EntryInfo | None, previous: EntryInfo | None) -> bool:
    if current is None or previous is None:
        return current is None and previous is None
    return current.size == previous.size and current.mtime == previous.mtime


def _reuse_baseline(node: NodeResult, base: NodeResult | None) -> bool:
    """Adopt the baseline status for an unchanged pair; True if reused."""
    if base is None or base.error is not None:
        return False
    if base.status not in (Status.SAME, Status.DIFFERENT):
        return False
    if _stat_unchanged(node.left, base.left) and _stat_unchanged(node.right, base.right):
        node.status = base.status
        return True
    return False


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

    left_entries = [e for e in left_entries if options.exclude.passes(e)]
    right_entries = [e for e in right_entries if options.exclude.passes(e)]

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
    size_same = left.size == right.size
    mtime_same = abs((left.mtime - right.mtime).total_seconds()) <= options.mtime_tolerance
    if options.use_size and not size_same:
        return Status.DIFFERENT
    if options.content is not ContentMode.NONE:
        # Content is authoritative when read. Differing sizes already prove the
        # bytes differ, so never read those. A differing mtime does not: read
        # and let the contents decide (an identical file copied over SFTP often
        # gets a fresh timestamp). As a shortcut, a pair whose size and mtime
        # already agree is taken as equal without reading — unless the user
        # turned that off to force a full content check on every pair.
        if not size_same:
            return Status.DIFFERENT
        if options.skip_content_if_metadata_matches and options.use_mtime and mtime_same:
            return Status.SAME
        return Status.UNKNOWN  # needs the content pass
    if options.use_mtime and not mtime_same:
        return Status.DIFFERENT
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
