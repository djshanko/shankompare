"""Main window: side pickers, compare options, folder tab + text compare tabs."""

from dataclasses import replace

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shankompare.compare import CompareOptions, ContentMode, NodeResult
from shankompare.sessions import AUTH_PASSWORD, ConnectionProfile, ProfileStore

from .folder_view import FolderCompareView
from .profile_dialog import ProfileDialog
from .remote_browse import RemoteBrowseDialog
from .text_compare import TextCompareView
from .worker import (
    CompareWorker,
    LocalSide,
    SftpSide,
    SideSpec,
    TextDiffWorker,
    start_worker,
)


def prompt_secret(parent: QWidget, profile: ConnectionProfile) -> tuple[str | None, bool]:
    """Ask for a password; returns (secret, ok)."""
    secret, ok = QInputDialog.getText(
        parent,
        "Password required",
        f"Password for {profile.username}@{profile.host}:",
        QLineEdit.EchoMode.Password,
    )
    return (secret or None), ok


class SidePicker(QGroupBox):
    """One comparison side: a local folder path or an SFTP profile."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        self._profiles: list[ConnectionProfile] = []

        self._source = QComboBox()
        self._path = QLineEdit()
        self._browse = QPushButton("…")
        self._browse.setFixedWidth(30)
        self._browse.clicked.connect(self._on_browse)
        self._source.currentIndexChanged.connect(self._on_source_changed)

        layout = QHBoxLayout(self)
        layout.addWidget(self._source, 1)
        layout.addWidget(self._path, 2)
        layout.addWidget(self._browse)

        self.set_profiles([])

    def set_profiles(self, profiles: list[ConnectionProfile]) -> None:
        selected = self._source.currentText()
        self._profiles = profiles
        self._source.blockSignals(True)
        self._source.clear()
        self._source.addItem("Local folder")
        for profile in profiles:
            self._source.addItem(f"SFTP: {profile.name}")
        index = self._source.findText(selected)
        self._source.setCurrentIndex(index if index >= 0 else 0)
        self._source.blockSignals(False)
        self._on_source_changed(self._source.currentIndex())

    def selected_profile(self) -> ConnectionProfile | None:
        index = self._source.currentIndex() - 1
        return self._profiles[index] if index >= 0 else None

    def path(self) -> str:
        return self._path.text().strip()

    def set_path(self, path: str) -> None:
        self._path.setText(path)

    def _on_source_changed(self, _index: int) -> None:
        profile = self.selected_profile()
        if profile is None:
            self._path.setPlaceholderText("Local folder path")
        else:
            self._path.setPlaceholderText("Remote path")
            self._path.setText(profile.initial_path)

    def _on_browse(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            path = QFileDialog.getExistingDirectory(self, "Select folder", self.path())
            if path:
                self._path.setText(path)
            return
        secret = ProfileStore.get_secret(profile.name)
        if secret is None and profile.auth_method == AUTH_PASSWORD:
            secret, ok = prompt_secret(self, profile)
            if not ok:
                return
        dialog = RemoteBrowseDialog(profile, secret, start_path=self.path(), parent=self)
        if dialog.exec() and dialog.selected_path:
            self._path.setText(dialog.selected_path)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("shankompare")
        self.resize(1100, 750)

        self._store = ProfileStore()
        self._profiles = self._store.load()
        self._compare_thread: QThread | None = None
        self._compare_worker: CompareWorker | None = None
        self._text_threads: list[QThread] = []
        self._sides: tuple[SideSpec, SideSpec] | None = None

        self._left_picker = SidePicker("Left side")
        self._right_picker = SidePicker("Right side")

        self._size_check = QCheckBox("Size")
        self._size_check.setChecked(True)
        self._mtime_check = QCheckBox("Modified time")
        self._mtime_check.setChecked(True)
        self._tolerance = QDoubleSpinBox()
        self._tolerance.setRange(0.0, 86400.0)
        self._tolerance.setValue(2.0)
        self._tolerance.setSuffix(" s")
        self._tolerance.setToolTip("Modified-time tolerance")
        self._content_combo = QComboBox()
        self._content_combo.addItem("No content check", ContentMode.NONE)
        self._content_combo.addItem("Content: CRC32", ContentMode.CRC32)
        self._content_combo.addItem("Content: byte-by-byte", ContentMode.BYTES)
        self._case_check = QCheckBox("Case sensitive")
        self._case_check.setChecked(True)

        profiles_btn = QPushButton("Profiles…")
        profiles_btn.clicked.connect(self._edit_profiles)
        self._compare_btn = QPushButton("Compare")
        self._compare_btn.clicked.connect(self._start)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel)

        self._folder_view = FolderCompareView()
        self._folder_view.open_diff_requested.connect(self._open_text_diff)

        sides_row = QHBoxLayout()
        sides_row.addWidget(self._left_picker)
        sides_row.addWidget(self._right_picker)

        options_row = QHBoxLayout()
        for widget in (
            self._size_check,
            self._mtime_check,
            self._tolerance,
            self._content_combo,
            self._case_check,
        ):
            options_row.addWidget(widget)
        options_row.addStretch(1)
        options_row.addWidget(profiles_btn)
        options_row.addWidget(self._compare_btn)
        options_row.addWidget(self._cancel_btn)

        folders_tab = QWidget()
        folders_layout = QVBoxLayout(folders_tab)
        folders_layout.addLayout(sides_row)
        folders_layout.addLayout(options_row)
        folders_layout.addWidget(self._folder_view, 1)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.addTab(folders_tab, "Folders")
        # the folders tab itself is not closable
        self._tabs.tabBar().setTabButton(0, self._tabs.tabBar().ButtonPosition.RightSide, None)
        self._tabs.tabBar().setTabButton(0, self._tabs.tabBar().ButtonPosition.LeftSide, None)

        self.setCentralWidget(self._tabs)
        self.statusBar().showMessage("Ready")

        self._left_picker.set_profiles(self._profiles)
        self._right_picker.set_profiles(self._profiles)

    # --- profiles -------------------------------------------------------------

    def _edit_profiles(self) -> None:
        dialog = ProfileDialog(self._store, self._profiles, self)
        if dialog.exec():
            self._profiles = dialog.profiles
            self._left_picker.set_profiles(self._profiles)
            self._right_picker.set_profiles(self._profiles)

    # --- folder comparison ------------------------------------------------------

    def _options(self) -> CompareOptions:
        return CompareOptions(
            use_size=self._size_check.isChecked(),
            use_mtime=self._mtime_check.isChecked(),
            mtime_tolerance=self._tolerance.value(),
            content=self._content_combo.currentData(),
            case_sensitive=self._case_check.isChecked(),
        )

    def _side_spec(self, picker: SidePicker) -> SideSpec | None:
        profile = picker.selected_profile()
        if profile is None:
            path = picker.path()
            if not path:
                QMessageBox.warning(self, "shankompare", f"{picker.title()}: choose a folder.")
                return None
            return LocalSide(path)
        profile = replace(profile, initial_path=picker.path() or profile.initial_path)
        secret = ProfileStore.get_secret(profile.name)
        if secret is None and profile.auth_method == AUTH_PASSWORD:
            secret, ok = prompt_secret(self, profile)
            if not ok:
                return None
        return SftpSide(profile, secret)

    def _start(self) -> None:
        if self._compare_thread is not None:
            return
        left = self._side_spec(self._left_picker)
        if left is None:
            return
        right = self._side_spec(self._right_picker)
        if right is None:
            return
        self._launch(left, right)

    def _launch(self, left: SideSpec, right: SideSpec) -> None:
        self._sides = (left, right)
        self._folder_view.compare_started()

        worker = CompareWorker(left, right, self._options())
        worker.progress.connect(self.statusBar().showMessage)
        worker.dir_scanned.connect(self._folder_view.on_dir_scanned)
        worker.content_checked.connect(self._folder_view.on_content_checked)
        worker.finished.connect(self._on_compare_finished)
        worker.failed.connect(self._on_compare_failed)
        self._compare_worker = worker
        self._compare_thread = start_worker(worker, self, [worker.finished, worker.failed])
        self._compare_thread.finished.connect(self._on_compare_thread_done)
        self._compare_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)

    def _cancel(self) -> None:
        if self._compare_worker is not None:
            self._compare_worker.cancel_event.set()
            self.statusBar().showMessage("Cancelling…")

    def _on_compare_finished(self, root: NodeResult | None) -> None:
        if root is not None:
            self._folder_view.set_result(root)
            self.statusBar().showMessage("Comparison finished.")
        else:
            self.statusBar().showMessage("Comparison cancelled.")

    def _on_compare_failed(self, kind: str, side: str, message: str) -> None:
        if kind == "auth" and self._retry_auth(side, message):
            return
        if kind == "connection":
            answer = QMessageBox.question(
                self,
                "Connection failed",
                f"{message}\n\nRetry the comparison?",
                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Retry and self._sides is not None:
                left, right = self._sides
                self._relaunch_when_idle(left, right)
                return
        else:
            QMessageBox.critical(self, "Comparison failed", message)
        self.statusBar().showMessage("Comparison failed.")

    def _retry_auth(self, side: str, message: str) -> bool:
        """Re-prompt the failing side's password and restart. True if retrying."""
        if self._sides is None or side not in ("left", "right"):
            QMessageBox.critical(self, "Authentication failed", message)
            return False
        left, right = self._sides
        spec = left if side == "left" else right
        if not isinstance(spec, SftpSide):
            QMessageBox.critical(self, "Authentication failed", message)
            return False
        QMessageBox.warning(self, "Authentication failed", message)
        # a stored secret that failed is stale — drop it
        ProfileStore.delete_secret(spec.profile.name)
        secret, ok = prompt_secret(self, spec.profile)
        if not ok:
            return False
        new_spec = SftpSide(spec.profile, secret)
        if side == "left":
            left = new_spec
        else:
            right = new_spec
        self._relaunch_when_idle(left, right)
        return True

    def _relaunch_when_idle(self, left: SideSpec, right: SideSpec) -> None:
        """Restart once the previous worker thread has fully wound down."""
        thread = self._compare_thread
        if thread is not None and thread.isRunning():
            thread.finished.connect(lambda: self._launch(left, right))
        else:
            self._launch(left, right)

    def _on_compare_thread_done(self) -> None:
        self._compare_thread = None
        self._compare_worker = None
        self._compare_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)

    # --- text compare tabs ---------------------------------------------------------

    def _open_text_diff(self, node: NodeResult, rel_path: str) -> None:
        if self._sides is None:
            return
        left, right = self._sides
        view = TextCompareView(f"Left: {rel_path}", f"Right: {rel_path}")
        index = self._tabs.addTab(view, node.name)
        self._tabs.setCurrentIndex(index)

        worker = TextDiffWorker(left, right, rel_path)
        worker.finished.connect(lambda data, v=view: v.set_data(data.left, data.right))
        worker.failed.connect(lambda message, v=view: v.show_error(message))
        thread = start_worker(worker, self, [worker.finished, worker.failed])
        self._text_threads.append(thread)
        thread.finished.connect(lambda t=thread: self._text_threads.remove(t))

    def _close_tab(self, index: int) -> None:
        if index == 0:
            return
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        widget.deleteLater()

    # --- shutdown -------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._compare_worker is not None:
            self._compare_worker.cancel_event.set()
        for thread in [self._compare_thread, *self._text_threads]:
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(3000)
        event.accept()
