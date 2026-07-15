"""Background workers (QObjects driven on QThreads)."""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from shankompare.compare import (
    CompareCancelled,
    CompareDone,
    CompareOptions,
    ContentChecked,
    DecodedText,
    DirScanned,
    NodeResult,
    compare_folders,
    decode_bytes,
)
from shankompare.sessions import ConnectionProfile
from shankompare.vfs import (
    ArchiveFileSystem,
    FileSystem,
    LocalFileSystem,
    SftpFileSystem,
    VfsAuthError,
    VfsConnectionError,
    VfsError,
    is_archive_name,
)
from shankompare.vfs.archive import MAX_ARCHIVE_BYTES
from shankompare.vfs.ops import FileOp, OpsCancelled, execute_op

log = logging.getLogger(__name__)

MAX_TEXT_COMPARE_BYTES = 32 * 1024 * 1024
MAX_HEX_COMPARE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class LocalSide:
    path: str


@dataclass(frozen=True)
class SftpSide:
    profile: ConnectionProfile
    secret: str | None
    correct_clock_offset: bool = False


SideSpec = LocalSide | SftpSide


def _check_archive_size(size: int, name: str) -> None:
    if size > MAX_ARCHIVE_BYTES:
        raise VfsError(
            f"archive {name} is {size:,} bytes; the limit is {MAX_ARCHIVE_BYTES:,} bytes"
        )


def _open_local_side(path_text: str) -> FileSystem:
    path = Path(path_text)
    if path.is_file():
        if not is_archive_name(path.name):
            raise VfsError(f"{path_text} is a file, not a folder or a supported archive")
        _check_archive_size(path.stat().st_size, path.name)
        return ArchiveFileSystem(path.read_bytes(), path.name)
    return LocalFileSystem(path_text)


def _open_sftp_side(spec: SftpSide) -> FileSystem:
    profile = spec.profile
    fs = SftpFileSystem(
        profile.host,
        **profile.to_sftp_kwargs(spec.secret),
        measure_clock_offset=spec.correct_clock_offset,
    )
    try:
        info = fs.stat(".")
        if info.is_dir:
            return fs
        if not is_archive_name(info.name):
            raise VfsError(
                f"remote path is a file, not a folder or a supported archive: {info.name}"
            )
        _check_archive_size(info.size, info.name)
        with fs.open_read(".") as f:
            data = f.read()
        archive = ArchiveFileSystem(data, info.name)
        fs.close()
        return archive
    except VfsError:
        fs.close()
        raise


def open_side(spec: SideSpec) -> FileSystem:
    """Create the side's FileSystem. Call on the worker thread only (paramiko).

    A path that points at a .zip/.tar[.gz|bz2|xz] file (local or remote)
    opens read-only as a folder via ArchiveFileSystem.
    """
    if isinstance(spec, LocalSide):
        return _open_local_side(spec.path)
    return _open_sftp_side(spec)


def _error_kind(exc: VfsError) -> str:
    if isinstance(exc, VfsAuthError):
        return "auth"
    if isinstance(exc, VfsConnectionError):
        return "connection"
    return "vfs"


class _SideFailure(Exception):
    def __init__(self, kind: str, side: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.side = side


def start_worker(worker: QObject, parent: QObject, done_signals: list[Signal]) -> QThread:
    """Move ``worker`` to a fresh QThread wired for automatic teardown."""
    thread = QThread(parent)
    # A moved-to-thread QObject must be parentless, so nothing owns the Python
    # wrapper; anchor it to the thread or it is garbage-collected (killing the
    # C++ object and every connection) before run() ever fires.
    thread._worker = worker
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    for signal in done_signals:
        signal.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return thread


class CompareWorker(QObject):
    """Runs one folder comparison, streaming results via signals."""

    progress = Signal(str)
    dir_scanned = Signal(object)  # NodeResult
    content_checked = Signal(object)  # NodeResult
    finished = Signal(object)  # NodeResult, or None when cancelled
    failed = Signal(str, str, str)  # kind ("auth"/"connection"/...), side, message

    def __init__(
        self,
        left: SideSpec,
        right: SideSpec,
        options: CompareOptions,
        baseline: NodeResult | None = None,
    ):
        super().__init__()
        self._left = left
        self._right = right
        self._options = options
        self._baseline = baseline
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            self._run()
        except CompareCancelled:
            self.finished.emit(None)
        except _SideFailure as exc:
            self.failed.emit(exc.kind, exc.side, str(exc))
        except VfsError as exc:
            self.failed.emit(_error_kind(exc), "", str(exc))
        except Exception:  # the worker must never let an exception escape the thread
            log.exception("comparison worker crashed")
            self.failed.emit("internal", "", "Unexpected error; see the log output for details.")

    def _report_clock_offset(self, side: str, fs: FileSystem) -> None:
        offset = getattr(fs, "clock_offset", None)
        if not getattr(fs, "clock_offset_known", False) or offset is None:
            return
        seconds = offset.total_seconds()
        if abs(seconds) < 1.0:
            return  # negligible; not worth a message
        ahead = "ahead of" if seconds > 0 else "behind"
        self.progress.emit(
            f"Remote clock ({side}) is {abs(seconds):.0f}s {ahead} local; adjusting modified times."
        )

    def _open(self, spec: SideSpec, side: str) -> FileSystem:
        try:
            return open_side(spec)
        except VfsError as exc:
            raise _SideFailure(_error_kind(exc), side, str(exc)) from exc

    def _run(self) -> None:
        self.progress.emit("Connecting…")
        with (
            self._open(self._left, "left") as left_fs,
            self._open(self._right, "right") as right_fs,
        ):
            self._report_clock_offset("left", left_fs)
            self._report_clock_offset("right", right_fs)
            dirs = files = 0
            root = None
            for event in compare_folders(
                left_fs, right_fs, self._options, self.cancel_event, baseline=self._baseline
            ):
                if isinstance(event, DirScanned):
                    dirs += 1
                    self.dir_scanned.emit(event.node)
                    self.progress.emit(f"Scanned {dirs} folders — {event.path}")
                elif isinstance(event, ContentChecked):
                    files += 1
                    self.content_checked.emit(event.node)
                    self.progress.emit(f"Compared content of {files} files — {event.path}")
                elif isinstance(event, CompareDone):
                    root = event.root
            self.finished.emit(root)


@dataclass(frozen=True)
class TextDiffData:
    left: DecodedText
    right: DecodedText


@dataclass(frozen=True)
class HexDiffData:
    left: bytes
    right: bytes


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


class DiffLoadWorker(QObject):
    """Loads one file pair and presents it as text or hex.

    ``mode``: "text" or "hex" force the view; "auto" picks hex when either
    file contains NUL bytes near the start.
    """

    text_ready = Signal(object)  # TextDiffData
    hex_ready = Signal(object)  # HexDiffData
    failed = Signal(str)

    def __init__(self, left: SideSpec, right: SideSpec, rel_path: str, mode: str = "auto"):
        super().__init__()
        self._left = left
        self._right = right
        self._rel_path = rel_path
        self._mode = mode

    def run(self) -> None:
        try:
            with open_side(self._left) as left_fs, open_side(self._right) as right_fs:
                left = self._read(left_fs)
                right = self._read(right_fs)
            mode = self._mode
            if mode == "auto":
                mode = "hex" if _looks_binary(left) or _looks_binary(right) else "text"
            if mode == "hex":
                if max(len(left), len(right)) > MAX_HEX_COMPARE_BYTES:
                    self.failed.emit(
                        f"{self._rel_path}: hex compare is limited to "
                        f"{MAX_HEX_COMPARE_BYTES:,} bytes per file"
                    )
                    return
                self.hex_ready.emit(HexDiffData(left, right))
            else:
                self.text_ready.emit(TextDiffData(decode_bytes(left), decode_bytes(right)))
        except VfsError as exc:
            self.failed.emit(str(exc))
        except Exception:
            log.exception("diff load worker crashed")
            self.failed.emit("Unexpected error; see the log output for details.")

    def _read(self, fs: FileSystem) -> bytes:
        info = fs.stat(self._rel_path)
        if info.size > MAX_TEXT_COMPARE_BYTES:
            raise VfsError(
                f"{self._rel_path} is {info.size:,} bytes; "
                f"file compare is limited to {MAX_TEXT_COMPARE_BYTES:,} bytes"
            )
        with fs.open_read(self._rel_path) as f:
            return f.read()


class TextSaveWorker(QObject):
    """Writes one edited file back to its side."""

    finished = Signal(str)  # side
    failed = Signal(str)

    def __init__(self, spec: SideSpec, rel_path: str, data: bytes, side: str):
        super().__init__()
        self._spec = spec
        self._rel_path = rel_path
        self._data = data
        self._side = side

    def run(self) -> None:
        try:
            with open_side(self._spec) as fs, fs.open_write(self._rel_path) as f:
                f.write(self._data)
            self.finished.emit(self._side)
        except VfsError as exc:
            self.failed.emit(str(exc))
        except Exception:
            log.exception("text save worker crashed")
            self.failed.emit("Unexpected error while saving; see the log output.")


class FileOpsWorker(QObject):
    """Executes a batch of file operations sequentially on one connection pair."""

    progress = Signal(str)
    finished = Signal(int, list)  # completed count, error messages
    failed = Signal(str)  # could not even open the sides

    def __init__(self, left: SideSpec, right: SideSpec, ops: list[FileOp]):
        super().__init__()
        self._left = left
        self._right = right
        self._ops = ops
        self.cancel_event = threading.Event()

    def run(self) -> None:
        errors: list[str] = []
        completed = 0
        try:
            with open_side(self._left) as left_fs, open_side(self._right) as right_fs:
                for op in self._ops:
                    if self.cancel_event.is_set():
                        errors.append("Remaining operations cancelled.")
                        break
                    try:
                        execute_op(
                            left_fs,
                            right_fs,
                            op,
                            progress=self.progress.emit,
                            cancel=self.cancel_event,
                        )
                        completed += 1
                    except OpsCancelled:
                        errors.append(f"Cancelled during: {op.describe()}")
                        break
                    except VfsError as exc:
                        errors.append(f"{op.describe()} — {exc}")
            self.finished.emit(completed, errors)
        except VfsError as exc:
            self.failed.emit(str(exc))
        except Exception:
            log.exception("file ops worker crashed")
            self.failed.emit("Unexpected error during file operations; see the log output.")
