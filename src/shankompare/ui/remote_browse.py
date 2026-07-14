"""Modal dialog for picking a directory on an SFTP server.

The connection lives on a dedicated thread; navigation requests and results
cross over via signals, so the UI stays responsive while listing.
"""

import posixpath

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from shankompare.sessions import ConnectionProfile
from shankompare.vfs import SftpFileSystem, VfsError


class _BrowseWorker(QObject):
    listed = Signal(str, list)  # absolute path, sorted dir names
    failed = Signal(str)

    def __init__(self, profile: ConnectionProfile, secret: str | None):
        super().__init__()
        self._profile = profile
        self._secret = secret
        self._fs: SftpFileSystem | None = None

    @Slot(str)
    def list_dir(self, path: str) -> None:
        try:
            if self._fs is None:
                kwargs = self._profile.to_sftp_kwargs(self._secret)
                kwargs["root"] = "/"  # browse the whole server; paths stay absolute
                self._fs = SftpFileSystem(self._profile.host, **kwargs)
            absolute = self._fs.resolve(path or ".")
            names = sorted(
                (entry.name for entry in self._fs.listdir(absolute) if entry.is_dir),
                key=str.casefold,
            )
            self.listed.emit(absolute, list(names))
        except VfsError as exc:
            self.failed.emit(str(exc))

    def shutdown(self) -> None:
        if self._fs is not None:
            self._fs.close()
            self._fs = None


class RemoteBrowseDialog(QDialog):
    _navigate = Signal(str)

    def __init__(
        self,
        profile: ConnectionProfile,
        secret: str | None,
        start_path: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Browse {profile.name}")
        self.resize(420, 480)

        self._path_edit = QLineEdit()
        go_btn = QPushButton("Go")
        up_btn = QPushButton("Up")
        self._list = QListWidget()
        self._info = QLabel("Connecting…")
        self._info.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(self._path_edit, 1)
        top.addWidget(go_btn)
        top.addWidget(up_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._info)
        layout.addWidget(buttons)

        self._thread = QThread(self)
        self._worker = _BrowseWorker(profile, secret)
        self._worker.moveToThread(self._thread)
        self._navigate.connect(self._worker.list_dir)
        self._worker.listed.connect(self._on_listed)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

        go_btn.clicked.connect(self._on_go)
        up_btn.clicked.connect(self._on_up)
        self._path_edit.returnPressed.connect(self._on_go)
        self._list.itemDoubleClicked.connect(self._on_descend)

        self._request(start_path or profile.initial_path or ".")

    @property
    def selected_path(self) -> str:
        return self._path_edit.text().strip()

    def _request(self, path: str) -> None:
        self._info.setText("Loading…")
        self._list.setEnabled(False)
        self._navigate.emit(path)

    def _on_listed(self, path: str, names: list) -> None:
        self._path_edit.setText(path)
        self._list.clear()
        for name in names:
            QListWidgetItem(name, self._list)
        self._list.setEnabled(True)
        self._info.setText(f"{len(names)} folder(s)")

    def _on_failed(self, message: str) -> None:
        self._list.setEnabled(True)
        self._info.setText(message)

    def _on_go(self) -> None:
        self._request(self._path_edit.text().strip() or "/")

    def _on_up(self) -> None:
        current = self._path_edit.text().strip() or "/"
        self._request(posixpath.dirname(current.rstrip("/")) or "/")

    def _on_descend(self, item: QListWidgetItem) -> None:
        current = self._path_edit.text().strip() or "/"
        self._request(posixpath.join(current, item.text()))

    def done(self, result: int) -> None:
        self._thread.quit()
        self._thread.wait(3000)
        self._worker.shutdown()
        super().done(result)
