"""Main window: side pickers, compare options, folder tab + text compare tabs."""

from dataclasses import replace

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QActionGroup, QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from shankompare import __version__
from shankompare.compare import (
    CompareOptions,
    ContentMode,
    ExcludeFilters,
    NodeResult,
    SyncPlan,
    plan_mirror,
    plan_update_both,
)
from shankompare.sessions import (
    AUTH_PASSWORD,
    SIDE_LOCAL,
    SIDE_SFTP,
    ConnectionProfile,
    ProfileStore,
    Session,
    SessionSide,
    SessionStore,
    SettingsStore,
)
from shankompare.vfs import ARCHIVE_SUFFIXES
from shankompare.vfs.ops import FileOp, OpKind

from .filters_dialog import FiltersDialog
from .folder_view import FolderCompareView
from .help_dialog import HelpDialog
from .hex_compare import HexCompareView
from .profile_dialog import ProfileDialog
from .remote_browse import RemoteBrowseDialog
from .resources import doc_path
from .text_compare import TextCompareView
from .theme import THEMES, apply_theme
from .worker import (
    CompareWorker,
    DiffLoadWorker,
    FileOpsWorker,
    LocalSide,
    SftpSide,
    SideSpec,
    TextSaveWorker,
    start_worker,
)


class _LoadingTab(QWidget):
    """Placeholder tab shown while a diff loads (swapped out on arrival)."""

    def __init__(self, rel_path: str):
        super().__init__()
        self._label = QLabel(f"Loading {rel_path}…")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)

    def show_error(self, message: str) -> None:
        self._label.setText(message)


def prompt_secret(parent: QWidget, profile: ConnectionProfile) -> tuple[str | None, bool]:
    """Ask for a password; returns (secret, ok)."""
    secret, ok = QInputDialog.getText(
        parent,
        "Password required",
        f"Password for {profile.username}@{profile.host}:",
        QLineEdit.EchoMode.Password,
    )
    return (secret or None), ok


class _FolderOrArchiveDialog(QFileDialog):
    """Native-look file dialog that accepts either a folder or an archive file.

    QFileDialog has no built-in mode for "directory or matching file", so this
    shows both (FileMode.Directory + ShowDirsOnly=False, only possible with the
    non-native dialog) and skips QFileDialog's own accept() validation, which
    would otherwise reject a selected file because the mode is Directory.
    """

    def __init__(self, parent: QWidget | None, caption: str, directory: str):
        super().__init__(parent, caption, directory)
        self.setFileMode(QFileDialog.FileMode.Directory)
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setOption(QFileDialog.Option.ShowDirsOnly, False)
        patterns = " ".join(f"*{suffix}" for suffix in ARCHIVE_SUFFIXES)
        self.setNameFilter(f"Folders and archives ({patterns})")

    def accept(self) -> None:
        QDialog.accept(self)


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

    def to_session_side(self) -> SessionSide:
        profile = self.selected_profile()
        if profile is None:
            return SessionSide(SIDE_LOCAL, self.path())
        return SessionSide(SIDE_SFTP, self.path(), profile=profile.name)

    def apply_session_side(self, side: SessionSide) -> bool:
        """Returns False when the side references a profile that no longer exists."""
        if side.kind == SIDE_LOCAL:
            self._source.setCurrentIndex(0)
            self._path.setText(side.path)
            return True
        for offset, profile in enumerate(self._profiles):
            if profile.name == side.profile:
                self._source.setCurrentIndex(offset + 1)
                self._path.setText(side.path)
                return True
        return False

    def _on_browse(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            dialog = _FolderOrArchiveDialog(self, "Select folder or archive", self.path())
            if dialog.exec() and dialog.selectedFiles():
                self._path.setText(dialog.selectedFiles()[0])
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
        self._session_store = SessionStore()
        self._sessions = self._session_store.load()
        self._settings_store = SettingsStore()
        self._settings = self._settings_store.load()
        self._compare_thread: QThread | None = None
        self._compare_worker: CompareWorker | None = None
        self._text_threads: list[QThread] = []
        self._sides: tuple[SideSpec, SideSpec] | None = None
        self._ops_thread: QThread | None = None
        self._ops_worker: FileOpsWorker | None = None
        self._ops_pending: list[FileOp] = []
        self._pending_relaunch: tuple[SideSpec, SideSpec] | None = None
        self._exclude = ExcludeFilters()
        self._last_root: NodeResult | None = None
        self._pending_diffs: dict[object, tuple[QWidget, str]] = {}

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

        self._filters_btn = QPushButton("Filters…")
        self._filters_btn.clicked.connect(self._edit_filters)
        self._sync_btn = QToolButton()
        self._sync_btn.setText("Sync")
        self._sync_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._sync_btn.setEnabled(False)
        self._sync_btn.setToolTip("Run a comparison first")
        sync_menu = QMenu(self._sync_btn)
        sync_menu.addAction("Mirror left → right…").triggered.connect(
            lambda: self._run_sync("mirror-ltr")
        )
        sync_menu.addAction("Mirror right → left…").triggered.connect(
            lambda: self._run_sync("mirror-rtl")
        )
        sync_menu.addAction("Update both (newer wins)…").triggered.connect(
            lambda: self._run_sync("update-both")
        )
        self._sync_btn.setMenu(sync_menu)

        profiles_btn = QPushButton("Profiles…")
        profiles_btn.clicked.connect(self._edit_profiles)
        self._compare_btn = QPushButton("Compare")
        self._compare_btn.clicked.connect(self._start)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel)

        self._folder_view = FolderCompareView()
        self._folder_view.open_diff_requested.connect(self._open_diff)
        self._folder_view.ops_requested.connect(self._enqueue_ops)

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
        options_row.addWidget(self._filters_btn)
        options_row.addStretch(1)
        options_row.addWidget(self._sync_btn)
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
        self._build_menus()

    # --- menus ------------------------------------------------------------------

    def _build_menus(self) -> None:
        bar = self.menuBar()
        bar.clear()

        session_menu = bar.addMenu("&Session")
        save_action = session_menu.addAction("Save current…")
        save_action.triggered.connect(self._save_session)
        if self._sessions:
            session_menu.addSeparator()
            for session in self._sessions:
                action = session_menu.addAction(session.name)
                action.triggered.connect(lambda _=False, s=session: self._load_session(s))
            session_menu.addSeparator()
            delete_action = session_menu.addAction("Delete…")
            delete_action.triggered.connect(self._delete_session)

        view_menu = bar.addMenu("&View")
        theme_menu = view_menu.addMenu("Theme")
        group = QActionGroup(self)
        for theme in THEMES:
            action = theme_menu.addAction(theme.capitalize())
            action.setCheckable(True)
            action.setChecked(theme == self._settings.theme)
            action.triggered.connect(lambda _=False, t=theme: self._set_theme(t))
            group.addAction(action)

        help_menu = bar.addMenu("&Help")
        manual_action = help_menu.addAction("User Manual")
        manual_action.triggered.connect(lambda: self._show_doc("User Manual", "MANUAL.md"))
        notes_action = help_menu.addAction("Release Notes")
        notes_action.triggered.connect(lambda: self._show_doc("Release Notes", "RELEASE-NOTES.md"))
        help_menu.addSeparator()
        about_action = help_menu.addAction("About shankompare")
        about_action.triggered.connect(self._show_about)

    def _show_doc(self, title: str, name: str) -> None:
        HelpDialog(title, doc_path(name), parent=self).show()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About shankompare",
            f"<b>shankompare {__version__}</b><br>"
            "Cross-platform folder and file comparison with SFTP support.<br>"
            "See Help → User Manual to get started.",
        )

    def _set_theme(self, theme: str) -> None:
        self._settings.theme = theme
        self._settings_store.save(self._settings)
        apply_theme(theme)
        # repaint views whose colors depend on the scheme
        self._folder_view.expand_differences()
        self._folder_view.update()
        for index in range(1, self._tabs.count()):
            widget = self._tabs.widget(index)
            if isinstance(widget, TextCompareView | HexCompareView):
                widget.refresh_theme()

    # --- sessions ---------------------------------------------------------------

    def _save_session(self) -> None:
        name, ok = QInputDialog.getText(self, "Save session", "Session name:")
        name = name.strip()
        if not ok or not name:
            return
        options = self._options()
        session = Session(
            name=name,
            left=self._left_picker.to_session_side(),
            right=self._right_picker.to_session_side(),
            use_size=options.use_size,
            use_mtime=options.use_mtime,
            mtime_tolerance=options.mtime_tolerance,
            content=options.content.value,
            case_sensitive=options.case_sensitive,
        )
        session.set_exclude_filters(self._exclude)
        self._sessions = [s for s in self._sessions if s.name != name] + [session]
        self._session_store.save(self._sessions)
        self._build_menus()
        self.statusBar().showMessage(f"Session '{name}' saved.")

    def _load_session(self, session: Session) -> None:
        ok_left = self._left_picker.apply_session_side(session.left)
        ok_right = self._right_picker.apply_session_side(session.right)
        self._size_check.setChecked(session.use_size)
        self._mtime_check.setChecked(session.use_mtime)
        self._tolerance.setValue(session.mtime_tolerance)
        index = self._content_combo.findData(ContentMode(session.content))
        self._content_combo.setCurrentIndex(max(index, 0))
        self._case_check.setChecked(session.case_sensitive)
        self._exclude = session.exclude_filters()
        self._update_filters_button()
        if not (ok_left and ok_right):
            QMessageBox.warning(
                self,
                "Session",
                "A profile referenced by this session no longer exists; "
                "that side was left unchanged.",
            )
        self.statusBar().showMessage(f"Session '{session.name}' loaded.")

    def _delete_session(self) -> None:
        names = [s.name for s in self._sessions]
        name, ok = QInputDialog.getItem(self, "Delete session", "Session:", names, 0, False)
        if ok and name:
            self._sessions = [s for s in self._sessions if s.name != name]
            self._session_store.save(self._sessions)
            self._build_menus()

    # --- profiles -------------------------------------------------------------

    def _edit_profiles(self) -> None:
        dialog = ProfileDialog(self._store, self._profiles, self)
        if dialog.exec():
            self._profiles = dialog.profiles
            self._left_picker.set_profiles(self._profiles)
            self._right_picker.set_profiles(self._profiles)

    # --- exclusion filters ---------------------------------------------------------

    def _edit_filters(self) -> None:
        dialog = FiltersDialog(self._exclude, self)
        if dialog.exec():
            self._exclude = dialog.filters()
            self._update_filters_button()

    def _update_filters_button(self) -> None:
        active = self._exclude != ExcludeFilters()
        self._filters_btn.setText("Filters ● …" if active else "Filters…")
        self._filters_btn.setToolTip(
            "Exclusion filters are active" if active else "No exclusion filters"
        )

    # --- folder comparison ------------------------------------------------------

    def _options(self) -> CompareOptions:
        return CompareOptions(
            use_size=self._size_check.isChecked(),
            use_mtime=self._mtime_check.isChecked(),
            mtime_tolerance=self._tolerance.value(),
            content=self._content_combo.currentData(),
            case_sensitive=self._case_check.isChecked(),
            exclude=self._exclude,
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
            self._last_root = root
            self._sync_btn.setEnabled(True)
            self._sync_btn.setToolTip("Synchronize the two sides")
            self.statusBar().showMessage("Comparison finished.")
        else:
            self.statusBar().showMessage("Comparison cancelled.")

    # --- synchronization ---------------------------------------------------------

    def _run_sync(self, kind: str) -> None:
        if self._last_root is None or self._sides is None:
            return
        if kind == "mirror-ltr":
            plan, title = plan_mirror(self._last_root, "ltr"), "Mirror left → right"
        elif kind == "mirror-rtl":
            plan, title = plan_mirror(self._last_root, "rtl"), "Mirror right → left"
        else:
            plan, title = plan_update_both(self._last_root), "Update both"
        if not plan.ops and not plan.warnings:
            QMessageBox.information(self, title, "The two sides are already in sync.")
            return
        if self._confirm_sync(title, plan):
            self._enqueue_ops(plan.ops, confirmed=True)

    def _confirm_sync(self, title: str, plan: SyncPlan) -> bool:
        lines = [f"Plan: {plan.summary()}", ""]
        lines += [op.describe() for op in plan.ops[:15]]
        if len(plan.ops) > 15:
            lines.append(f"… and {len(plan.ops) - 15} more operation(s)")
        if plan.warnings:
            lines += ["", "Warnings:"] + plan.warnings[:10]
            if len(plan.warnings) > 10:
                lines.append(f"… and {len(plan.warnings) - 10} more warning(s)")
        if not plan.ops:
            QMessageBox.warning(self, title, "\n".join(lines))
            return False
        answer = QMessageBox.question(
            self,
            title,
            "\n".join(lines) + "\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

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
            self._pending_relaunch = (left, right)
            thread.finished.connect(self._start_pending_relaunch)
        else:
            self._launch(left, right)

    def _start_pending_relaunch(self) -> None:
        pending, self._pending_relaunch = self._pending_relaunch, None
        if pending is not None:
            self._launch(*pending)

    def _on_compare_thread_done(self) -> None:
        self._compare_thread = None
        self._compare_worker = None
        self._compare_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)

    # --- file operations -------------------------------------------------------------

    def _enqueue_ops(self, ops: list[FileOp], confirmed: bool = False) -> None:
        if self._sides is None or not ops:
            return
        deletes = [op for op in ops if op.kind in (OpKind.DELETE_LEFT, OpKind.DELETE_RIGHT)]
        if deletes and not confirmed:
            summary = "\n".join(op.describe() for op in deletes[:10])
            if len(deletes) > 10:
                summary += f"\n… and {len(deletes) - 10} more"
            answer = QMessageBox.question(
                self,
                "Confirm delete",
                f"This will permanently delete:\n\n{summary}\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._ops_pending.extend(ops)
        self._maybe_start_ops()

    def _maybe_start_ops(self) -> None:
        if self._ops_thread is not None or not self._ops_pending or self._sides is None:
            return
        batch, self._ops_pending = self._ops_pending, []
        left, right = self._sides
        worker = FileOpsWorker(left, right, batch)
        worker.progress.connect(self.statusBar().showMessage)
        worker.finished.connect(self._on_ops_finished)
        worker.failed.connect(self._on_ops_failed)
        self._ops_worker = worker
        self._ops_thread = start_worker(worker, self, [worker.finished, worker.failed])
        self._ops_thread.finished.connect(self._on_ops_thread_done)

    def _on_ops_finished(self, completed: int, errors: list) -> None:
        if errors:
            QMessageBox.warning(
                self,
                "File operations",
                f"{completed} operation(s) completed, {len(errors)} problem(s):\n\n"
                + "\n".join(errors[:15]),
            )
        else:
            self.statusBar().showMessage(f"{completed} file operation(s) completed.")

    def _on_ops_failed(self, message: str) -> None:
        self._ops_pending.clear()
        QMessageBox.critical(self, "File operations failed", message)

    def _on_ops_thread_done(self) -> None:
        self._ops_thread = None
        self._ops_worker = None
        if self._ops_pending:
            self._maybe_start_ops()
        elif self._sides is not None and self._compare_thread is None:
            # refresh the tree so the result reflects the changes
            self._launch(*self._sides)

    # --- diff tabs (text and hex) ------------------------------------------------

    # NOTE: signals emitted from worker threads must connect to bound methods
    # of QObjects (queued to the receiver's thread), never to lambdas — a
    # lambda has no receiver, so Qt runs it on the worker thread, and touching
    # widgets from there crashes intermittently.

    def _open_diff(self, node: NodeResult, rel_path: str, mode: str = "auto") -> None:
        if self._sides is None:
            return
        placeholder = _LoadingTab(rel_path)
        index = self._tabs.addTab(placeholder, node.name)
        self._tabs.setCurrentIndex(index)
        self._start_diff_load(placeholder, rel_path, mode)

    def _start_diff_load(self, target: QWidget, rel_path: str, mode: str) -> None:
        """``target`` is either a _LoadingTab (first load) or an existing
        text/hex view being refreshed."""
        if self._sides is None:
            return
        left, right = self._sides
        worker = DiffLoadWorker(left, right, rel_path, mode)
        self._pending_diffs[worker] = (target, rel_path)
        worker.text_ready.connect(self._on_diff_text_ready)
        worker.hex_ready.connect(self._on_diff_hex_ready)
        worker.failed.connect(self._on_diff_failed)
        self._track_thread(
            start_worker(worker, self, [worker.text_ready, worker.hex_ready, worker.failed])
        )

    def _pop_pending(self) -> tuple[QWidget | None, str]:
        return self._pending_diffs.pop(self.sender(), (None, ""))

    def _on_diff_text_ready(self, data) -> None:
        target, rel_path = self._pop_pending()
        if target is None:
            return
        if isinstance(target, TextCompareView):  # refresh of an existing tab
            target.on_diff_loaded(data)
            return
        view = TextCompareView(f"Left: {rel_path}", f"Right: {rel_path}")
        view.save_requested.connect(  # emitted on the UI thread (button click)
            lambda side, blob, v=view, rel=rel_path: self._save_text(v, side, rel, blob)
        )
        view.refresh_requested.connect(  # emitted on the UI thread
            lambda v=view, rel=rel_path: self._start_diff_load(v, rel, "text")
        )
        view.set_data(data.left, data.right)
        self._swap_tab(target, view)

    def _on_diff_hex_ready(self, data) -> None:
        target, rel_path = self._pop_pending()
        if target is None:
            return
        if isinstance(target, HexCompareView):  # refresh of an existing tab
            target.on_hex_loaded(data)
            return
        view = HexCompareView(f"Left: {rel_path}", f"Right: {rel_path}")
        view.refresh_requested.connect(  # emitted on the UI thread
            lambda v=view, rel=rel_path: self._start_diff_load(v, rel, "hex")
        )
        view.on_hex_loaded(data)
        self._swap_tab(target, view)

    def _on_diff_failed(self, message: str) -> None:
        target, _ = self._pop_pending()
        if target is not None:
            target.show_error(message)

    def _swap_tab(self, old: QWidget, new: QWidget) -> None:
        index = self._tabs.indexOf(old)
        if index < 0:  # tab was closed while loading
            new.deleteLater()
            return
        label = self._tabs.tabText(index)
        was_current = self._tabs.currentIndex() == index
        self._tabs.removeTab(index)
        self._tabs.insertTab(index, new, label)
        if was_current:
            self._tabs.setCurrentIndex(index)
        old.deleteLater()

    def _save_text(self, view: TextCompareView, side: str, rel_path: str, data: bytes) -> None:
        if self._sides is None:
            return
        spec = self._sides[0] if side == "left" else self._sides[1]
        worker = TextSaveWorker(spec, rel_path, data, side)
        worker.finished.connect(view.mark_saved)
        worker.failed.connect(view.on_save_failed)
        self._track_thread(start_worker(worker, self, [worker.finished, worker.failed]))

    def _track_thread(self, thread: QThread) -> None:
        self._text_threads.append(thread)
        thread.finished.connect(self._prune_text_threads)

    def _prune_text_threads(self) -> None:
        self._text_threads = [t for t in self._text_threads if t.isRunning()]

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
        if self._ops_worker is not None:
            self._ops_worker.cancel_event.set()
        for thread in [self._compare_thread, self._ops_thread, *self._text_threads]:
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(3000)
        event.accept()
