"""Background comparison worker (QObject driven on a QThread)."""

import logging
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from shankompare.compare import (
    CompareCancelled,
    CompareDone,
    CompareOptions,
    ContentChecked,
    DirScanned,
    compare_folders,
)
from shankompare.sessions import ConnectionProfile
from shankompare.vfs import FileSystem, LocalFileSystem, SftpFileSystem, VfsError

log = logging.getLogger(__name__)


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


class CompareWorker(QObject):
    """Runs one comparison; results cross threads only via signals."""

    progress = Signal(str)
    finished = Signal(object)  # NodeResult, or None when cancelled
    failed = Signal(str)

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
        except VfsError as exc:
            self.failed.emit(str(exc))
        except Exception:  # the worker must never let an exception escape the thread
            log.exception("comparison worker crashed")
            self.failed.emit("Unexpected error; see the log output for details.")

    def _run(self) -> None:
        self.progress.emit("Connecting…")
        with open_side(self._left) as left_fs, open_side(self._right) as right_fs:
            dirs = files = 0
            root = None
            for event in compare_folders(left_fs, right_fs, self._options, self.cancel_event):
                if isinstance(event, DirScanned):
                    dirs += 1
                    self.progress.emit(f"Scanned {dirs} folders — {event.path}")
                elif isinstance(event, ContentChecked):
                    files += 1
                    self.progress.emit(f"Compared content of {files} files — {event.path}")
                elif isinstance(event, CompareDone):
                    root = event.root
            self.finished.emit(root)
