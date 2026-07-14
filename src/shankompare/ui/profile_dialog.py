"""Dialog for managing SFTP connection profiles."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from shankompare.sessions import AUTH_KEY, AUTH_PASSWORD, ConnectionProfile, ProfileStore

from .remote_browse import RemoteBrowseDialog


class ProfileDialog(QDialog):
    """Edits a working copy of the profile list; saves on OK, discards on Cancel.

    Passwords are written to the keyring immediately via "Set password…" —
    they are never held in this dialog or in the JSON file.
    """

    def __init__(self, store: ProfileStore, profiles: list[ConnectionProfile], parent=None):
        super().__init__(parent)
        self.setWindowTitle("SFTP Profiles")
        self._store = store
        self.profiles = list(profiles)
        self._current = -1

        self._list = QListWidget()
        new_btn = QPushButton("New")
        delete_btn = QPushButton("Delete")

        self._name = QLineEdit()
        self._host = QLineEdit()
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(22)
        self._username = QLineEdit()
        self._auth = QComboBox()
        self._auth.addItem("Password", AUTH_PASSWORD)
        self._auth.addItem("Private key", AUTH_KEY)
        self._key_file = QLineEdit()
        key_browse = QPushButton("…")
        key_browse.setFixedWidth(30)
        self._initial_path = QLineEdit()
        self._initial_path.setPlaceholderText(".")
        path_browse = QPushButton("…")
        path_browse.setFixedWidth(30)
        path_browse.setToolTip("Browse the server for the initial path")
        password_btn = QPushButton("Set password / passphrase…")

        key_row = QHBoxLayout()
        key_row.addWidget(self._key_file)
        key_row.addWidget(key_browse)
        key_widget = QWidget()
        key_widget.setLayout(key_row)
        key_row.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.addRow("Name:", self._name)
        form.addRow("Host:", self._host)
        form.addRow("Port:", self._port)
        form.addRow("Username:", self._username)
        form.addRow("Authentication:", self._auth)
        form.addRow("Key file:", key_widget)
        path_row = QHBoxLayout()
        path_row.addWidget(self._initial_path)
        path_row.addWidget(path_browse)
        path_widget = QWidget()
        path_widget.setLayout(path_row)
        path_row.setContentsMargins(0, 0, 0, 0)
        form.addRow("Initial path:", path_widget)
        form.addRow("", password_btn)

        left_col = QVBoxLayout()
        left_col.addWidget(self._list)
        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(delete_btn)
        left_col.addLayout(btn_row)

        body = QHBoxLayout()
        body.addLayout(left_col, 1)
        body.addLayout(form, 2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(body)
        layout.addWidget(buttons)

        new_btn.clicked.connect(self._on_new)
        delete_btn.clicked.connect(self._on_delete)
        key_browse.clicked.connect(self._on_browse_key)
        path_browse.clicked.connect(self._on_browse_remote)
        password_btn.clicked.connect(self._on_set_password)
        self._list.currentRowChanged.connect(self._on_row_changed)

        self._reload_list()
        if self.profiles:
            self._list.setCurrentRow(0)
        else:
            self._set_form_enabled(False)

    # --- list management --------------------------------------------------

    def _reload_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for profile in self.profiles:
            self._list.addItem(profile.name)
        self._list.blockSignals(False)

    def _on_row_changed(self, row: int) -> None:
        self._commit_form()
        self._current = row
        if row >= 0:
            self._load_form(self.profiles[row])
            self._set_form_enabled(True)

    def _on_new(self) -> None:
        self._commit_form()
        self.profiles.append(ConnectionProfile(name=self._unique_name(), host=""))
        self._reload_list()
        self._list.setCurrentRow(len(self.profiles) - 1)

    def _unique_name(self) -> str:
        existing = {p.name for p in self.profiles}
        base = "new-profile"
        name, n = base, 2
        while name in existing:
            name = f"{base}-{n}"
            n += 1
        return name

    def _on_delete(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self._current = -1
        removed = self.profiles.pop(row)
        self._store.delete_secret(removed.name)
        self._reload_list()
        if self.profiles:
            self._list.setCurrentRow(min(row, len(self.profiles) - 1))
        else:
            self._set_form_enabled(False)

    # --- form -------------------------------------------------------------

    def _set_form_enabled(self, enabled: bool) -> None:
        for widget in (
            self._name,
            self._host,
            self._port,
            self._username,
            self._auth,
            self._key_file,
            self._initial_path,
        ):
            widget.setEnabled(enabled)

    def _load_form(self, profile: ConnectionProfile) -> None:
        self._name.setText(profile.name)
        self._host.setText(profile.host)
        self._port.setValue(profile.port)
        self._username.setText(profile.username)
        self._auth.setCurrentIndex(1 if profile.auth_method == AUTH_KEY else 0)
        self._key_file.setText(profile.key_file or "")
        self._initial_path.setText(profile.initial_path)

    def _commit_form(self) -> None:
        if self._current < 0 or self._current >= len(self.profiles):
            return
        old = self.profiles[self._current]
        new_name = self._name.text().strip() or old.name
        if new_name != old.name and self._store.get_secret(old.name) is not None:
            # keep the stored secret reachable under the new name
            secret = self._store.get_secret(old.name)
            if secret is not None:
                self._store.set_secret(new_name, secret)
            self._store.delete_secret(old.name)
        self.profiles[self._current] = ConnectionProfile(
            name=new_name,
            host=self._host.text().strip(),
            port=self._port.value(),
            username=self._username.text().strip(),
            auth_method=self._auth.currentData(),
            key_file=self._key_file.text().strip() or None,
            initial_path=self._initial_path.text().strip() or ".",
        )
        item = self._list.item(self._current)
        if item is not None:
            item.setText(new_name)

    def _on_browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select private key file")
        if path:
            self._key_file.setText(path)

    def _form_profile(self) -> ConnectionProfile:
        """The profile as currently described by the form (uncommitted)."""
        return ConnectionProfile(
            name=self._name.text().strip(),
            host=self._host.text().strip(),
            port=self._port.value(),
            username=self._username.text().strip(),
            auth_method=self._auth.currentData(),
            key_file=self._key_file.text().strip() or None,
            initial_path=self._initial_path.text().strip() or ".",
        )

    def _on_browse_remote(self) -> None:
        profile = self._form_profile()
        if not profile.host:
            return
        secret = self._store.get_secret(profile.name) if profile.name else None
        if secret is None and profile.auth_method == AUTH_PASSWORD:
            secret, ok = QInputDialog.getText(
                self,
                "Password required",
                f"Password for {profile.username}@{profile.host}:",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            secret = secret or None
        dialog = RemoteBrowseDialog(profile, secret, start_path=profile.initial_path, parent=self)
        if dialog.exec() and dialog.selected_path:
            self._initial_path.setText(dialog.selected_path)

    def _on_set_password(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        secret, ok = QInputDialog.getText(
            self,
            "Set secret",
            f"Password / key passphrase for profile '{name}':",
            QLineEdit.EchoMode.Password,
        )
        if ok and secret:
            self._store.set_secret(name, secret)

    def _on_accept(self) -> None:
        self._commit_form()
        self._store.save(self.profiles)
        self.accept()
