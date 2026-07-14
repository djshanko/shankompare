"""Cross-filesystem file operations (copy, delete, rename, timestamp sync).

Pure core logic: operations work on any two ``FileSystem`` instances and are
driven by the UI's operations worker. Copies preserve the source mtime.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from .base import FileSystem

_CHUNK_SIZE = 256 * 1024

Progress = Callable[[str], None]


class OpsCancelled(Exception):
    """Raised between steps when the cancel event is set."""


class OpKind(Enum):
    COPY_LTR = "copy_ltr"
    COPY_RTL = "copy_rtl"
    DELETE_LEFT = "delete_left"
    DELETE_RIGHT = "delete_right"
    RENAME = "rename"
    MTIME_LTR = "mtime_ltr"  # stamp the right side with the left side's mtime
    MTIME_RTL = "mtime_rtl"


@dataclass(frozen=True)
class FileOp:
    kind: OpKind
    path: str  # rel path within the compared roots
    new_name: str | None = None  # RENAME only

    def describe(self) -> str:
        labels = {
            OpKind.COPY_LTR: "Copy to right",
            OpKind.COPY_RTL: "Copy to left",
            OpKind.DELETE_LEFT: "Delete on left",
            OpKind.DELETE_RIGHT: "Delete on right",
            OpKind.RENAME: f"Rename to {self.new_name}",
            OpKind.MTIME_LTR: "Copy timestamp to right",
            OpKind.MTIME_RTL: "Copy timestamp to left",
        }
        return f"{labels[self.kind]}: {self.path}"


def _check(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise OpsCancelled


def _report(progress: Progress | None, message: str) -> None:
    if progress is not None:
        progress(message)


def execute_op(
    left_fs: FileSystem,
    right_fs: FileSystem,
    op: FileOp,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
) -> None:
    _check(cancel)
    if op.kind is OpKind.COPY_LTR:
        copy_entry(left_fs, right_fs, op.path, progress=progress, cancel=cancel)
    elif op.kind is OpKind.COPY_RTL:
        copy_entry(right_fs, left_fs, op.path, progress=progress, cancel=cancel)
    elif op.kind is OpKind.DELETE_LEFT:
        delete_entry(left_fs, op.path, progress=progress, cancel=cancel)
    elif op.kind is OpKind.DELETE_RIGHT:
        delete_entry(right_fs, op.path, progress=progress, cancel=cancel)
    elif op.kind is OpKind.RENAME:
        if not op.new_name:
            raise ValueError("RENAME requires new_name")
        target = str(PurePosixPath(op.path).parent / op.new_name)
        for fs in (left_fs, right_fs):
            if fs.exists(op.path):
                _report(progress, f"Renaming {op.path} → {op.new_name}")
                fs.rename(op.path, target)
    elif op.kind is OpKind.MTIME_LTR:
        _report(progress, f"Copying timestamp of {op.path} to right")
        right_fs.set_mtime(op.path, left_fs.stat(op.path).mtime)
    elif op.kind is OpKind.MTIME_RTL:
        _report(progress, f"Copying timestamp of {op.path} to left")
        left_fs.set_mtime(op.path, right_fs.stat(op.path).mtime)


def copy_entry(
    src_fs: FileSystem,
    dst_fs: FileSystem,
    path: str,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Copy a file or directory tree to the same relative path on ``dst_fs``."""
    _ensure_parents(dst_fs, path)
    info = src_fs.stat(path)
    if info.is_dir:
        _copy_tree(src_fs, dst_fs, path, progress, cancel)
    else:
        _copy_file(src_fs, dst_fs, path, progress, cancel)


def _copy_tree(src_fs, dst_fs, path, progress, cancel) -> None:
    _check(cancel)
    if not dst_fs.exists(path):
        dst_fs.mkdir(path)
    for entry in src_fs.listdir(path):
        child = str(PurePosixPath(path) / entry.name)
        if entry.is_dir:
            _copy_tree(src_fs, dst_fs, child, progress, cancel)
        else:
            _copy_file(src_fs, dst_fs, child, progress, cancel)


def _copy_file(src_fs, dst_fs, path, progress, cancel) -> None:
    _check(cancel)
    _report(progress, f"Copying {path}")
    with src_fs.open_read(path) as src, dst_fs.open_write(path) as dst:
        while chunk := src.read(_CHUNK_SIZE):
            _check(cancel)
            dst.write(chunk)
    dst_fs.set_mtime(path, src_fs.stat(path).mtime)


def _ensure_parents(dst_fs: FileSystem, path: str) -> None:
    parents = [p for p in PurePosixPath(path).parents if str(p) != "."]
    for parent in reversed(parents):
        if not dst_fs.exists(parent):
            dst_fs.mkdir(parent)


def delete_entry(
    fs: FileSystem,
    path: str,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Delete a file or an entire directory tree."""
    _check(cancel)
    info = fs.stat(path)
    if info.is_dir:
        for entry in fs.listdir(path):
            delete_entry(fs, str(PurePosixPath(path) / entry.name), progress, cancel)
    _report(progress, f"Deleting {path}")
    fs.remove(path)
