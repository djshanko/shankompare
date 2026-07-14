"""Main window: pick two sides, run a comparison, show the result tree."""

from dataclasses import replace

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QBrush, QCloseEvent, QColor
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shankompare.compare import CompareOptions, ContentMode, NodeResult, Status
from shankompare.sessions import AUTH_PASSWORD, ConnectionProfile, ProfileStore
from shankompare.vfs import EntryInfo

from .profile_dialog import ProfileDialog
from .worker import CompareWorker, LocalSide, SftpSide, SideSpec

_STATUS_LABEL = {
    Status.SAME: "Same",
    Status.DIFFERENT: "Different",
    Status.LEFT_ONLY: "Left only",
    Status.RIGHT_ONLY: "Right only",
    Status.UNKNOWN: "Unknown",
}

_STATUS_COLOR = {
    Status.DIFFERENT: QColor("#c62828"),
    Status.LEFT_ONLY: QColor("#1565c0"),
    Status.RIGHT_ONLY: QColor("#2e7d32"),
    Status.UNKNOWN: QColor("#9e6a03"),
}


def _fmt_size(entry: EntryInfo | None) -> str:
    if entry is None or entry.is_dir:
        return ""
    return f"{entry.size:,}"


def _fmt_mtime(entry: EntryInfo | None) -> str:
    if entry is None:
        return ""
    return entry.mtime.astimezone().strftime("%Y-%m-%d %H:%M:%S")


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

    def _on_source_changed(self, _index: int) -> None:
        profile = self.selected_profile()
        if profile is None:
            self._browse.setEnabled(True)
            self._path.setPlaceholderText("Local folder path")
        else:
            self._browse.setEnabled(False)
            self._path.setPlaceholderText("Remote path")
            self._path.setText(profile.initial_path)

    def _on_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder", self.path())
        if path:
            self._path.setText(path)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("shankompare")
        self.resize(1000, 700)

        self._store = ProfileStore()
        self._profiles = self._store.load()
        self._thread: QThread | None = None
        self._worker: CompareWorker | None = None

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

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(
            ["Name", "Size (L)", "Modified (L)", "Size (R)", "Modified (R)", "Status"]
        )
        self._tree.setColumnWidth(0, 320)
        self._tree.setColumnWidth(2, 150)
        self._tree.setColumnWidth(4, 150)

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

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(sides_row)
        layout.addLayout(options_row)
        layout.addWidget(self._tree, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

        self._left_picker.set_profiles(self._profiles)
        self._right_picker.set_profiles(self._profiles)

    # --- profiles -----------------------------------------------------------

    def _edit_profiles(self) -> None:
        dialog = ProfileDialog(self._store, self._profiles, self)
        if dialog.exec():
            self._profiles = dialog.profiles
            self._left_picker.set_profiles(self._profiles)
            self._right_picker.set_profiles(self._profiles)

    # --- running a comparison -------------------------------------------------

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
            secret, ok = QInputDialog.getText(
                self,
                "Password required",
                f"Password for {profile.username}@{profile.host}:",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return None
        return SftpSide(profile, secret or None)

    def _start(self) -> None:
        if self._thread is not None:
            return
        left = self._side_spec(self._left_picker)
        if left is None:
            return
        right = self._side_spec(self._right_picker)
        if right is None:
            return

        self._worker = CompareWorker(left, right, self._options())
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.statusBar().showMessage)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._compare_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._thread.start()

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel_event.set()
            self.statusBar().showMessage("Cancelling…")

    def _on_finished(self, root: NodeResult | None) -> None:
        if root is not None:
            self._populate(root)
            self.statusBar().showMessage("Comparison finished.")
        else:
            self.statusBar().showMessage("Comparison cancelled.")
        self._teardown()

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Comparison failed", message)
        self.statusBar().showMessage("Comparison failed.")
        self._teardown()

    def _teardown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None
        self._compare_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None:
            self._worker.cancel_event.set()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()

    # --- result tree ------------------------------------------------------------

    def _populate(self, root: NodeResult) -> None:
        self._tree.clear()
        for child in root.children:
            item = self._make_item(child)
            self._tree.addTopLevelItem(item)
            self._expand_diffs(item, child)

    def _make_item(self, node: NodeResult) -> QTreeWidgetItem:
        status_text = _STATUS_LABEL[node.status]
        if node.error:
            status_text += " ⚠"
        item = QTreeWidgetItem(
            [
                node.name,
                _fmt_size(node.left),
                _fmt_mtime(node.left),
                _fmt_size(node.right),
                _fmt_mtime(node.right),
                status_text,
            ]
        )
        color = _STATUS_COLOR.get(node.status)
        if color is not None:
            brush = QBrush(color)
            for col in range(item.columnCount()):
                item.setForeground(col, brush)
        if node.error:
            item.setToolTip(5, node.error)
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight)
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight)
        for child in node.children:
            item.addChild(self._make_item(child))
        return item

    def _expand_diffs(self, item: QTreeWidgetItem, node: NodeResult) -> None:
        if node.is_dir and node.status is not Status.SAME:
            item.setExpanded(True)
        for i, child in enumerate(node.children):
            self._expand_diffs(item.child(i), child)
