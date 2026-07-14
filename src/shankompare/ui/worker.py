"""Background workers (QObjects driven on QThreads)."""

import logging
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from shankompare.compare import (
    CompareCancelled,
    CompareDone,
    CompareOptions,
    ContentChecked,
    DecodedText,
    DirScanned,
    compare_folders,
    decode_bytes,
)
from shankompare.sessions import ConnectionProfile
from shankompare.vfs import (
    FileSystem,
    LocalFileSystem,
    SftpFileSystem,
    VfsAuthError,
    VfsConnectionError,
    VfsError,
)

log = logging.getLogger(__name__)

MAX_TEXT_COMPARE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class LocalSide:
    path: str


@dataclass(frozen=True)
class SftpSide:
    profile: ConnectionProfile
    secret: str | None


SideSpec = LocalSide | SftpSide


def open_side(spec: SideSpec) -> FileSystem:
    """Create the side's FileSystem. Call on the worker thread only (paramiko)."""
    if isinstance(spec, LocalSide):
        return LocalFileSystem(spec.path)
    profile = spec.profile
    return SftpFileSystem(profile.host, **profile.to_sftp_kwargs(spec.secret))


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

    def __init__(self, left: SideSpec, right: SideSpec, options: CompareOptions):
        super().__init__()
        self._left = left
        self._right = right
        self._options = options
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
            dirs = files = 0
            root = None
            for event in compare_folders(left_fs, right_fs, self._options, self.cancel_event):
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


class TextDiffWorker(QObject):
    """Loads one file pair from both sides and decodes it for the text view."""

    finished = Signal(object)  # TextDiffData
    failed = Signal(str)

    def __init__(self, left: SideSpec, right: SideSpec, rel_path: str):
        super().__init__()
        self._left = left
        self._right = right
        self._rel_path = rel_path

    def run(self) -> None:
        try:
            with open_side(self._left) as left_fs, open_side(self._right) as right_fs:
                data = TextDiffData(
                    left=decode_bytes(self._read(left_fs)),
                    right=decode_bytes(self._read(right_fs)),
                )
            self.finished.emit(data)
        except VfsError as exc:
            self.failed.emit(str(exc))
        except Exception:
            log.exception("text diff worker crashed")
            self.failed.emit("Unexpected error; see the log output for details.")

    def _read(self, fs: FileSystem) -> bytes:
        info = fs.stat(self._rel_path)
        if info.size > MAX_TEXT_COMPARE_BYTES:
            raise VfsError(
                f"{self._rel_path} is {info.size:,} bytes; "
                f"text compare is limited to {MAX_TEXT_COMPARE_BYTES:,} bytes"
            )
        with fs.open_read(self._rel_path) as f:
            return f.read()
